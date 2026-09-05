"""Deterministic, file-backed Channel Package workflow runtime."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ._portable import file_lock as _portable_lock
from ._portable import write_json_atomic as _write_json_atomic_portable

from .validation import (
    ChannelPackage,
    ChannelValidationError,
    validate_channel_package,
    validate_channel_state_document,
)
from .workflow import (
    FORWARD_TRANSITIONS,
    HUMAN_GATE_TRANSITIONS,
    REVISION_TARGETS,
    WORKFLOW_STATES,
    canonical_json_bytes,
    completed_prefix_for,
    event_id_for,
)


class ChannelStateError(RuntimeError):
    """A requested state operation is illegal or cannot be persisted safely."""


@dataclass(frozen=True)
class NextAllowedAction:
    channel_id: str
    state: str
    status: str
    allowed_operations: tuple[str, ...]
    forward_state: str | None
    requires_prerequisite_refs: bool
    requires_human_decision: bool
    next_action: str
    waiting_for: str | None


def _timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_atomic(path: Path, value: dict[str, Any]) -> None:
    _write_json_atomic_portable(path, value)


class ChannelStateMachine:
    """Own legal transitions and atomically persist one Channel Package state."""

    def __init__(self, package_root: Path, repository_root: Path):
        self.package_root = package_root.resolve()
        self.repository_root = repository_root.resolve()
        if not self.package_root.is_relative_to(self.repository_root):
            raise ChannelStateError(f"package escapes repository root: {self.package_root}")
        self.state_path = self.package_root / "CHANNEL_STATE.json"
        self.lock_path = self.package_root / ".channel-state.lock"

    @contextmanager
    def _write_lock(self, timeout_s: float = 10.0):
        try:
            with _portable_lock(self.lock_path, timeout_s):
                yield
        except RuntimeError as exc:
            raise ChannelStateError(str(exc)) from exc

    def load(self) -> ChannelPackage:
        try:
            return validate_channel_package(self.package_root, self.repository_root)
        except ChannelValidationError as exc:
            raise ChannelStateError(str(exc)) from exc

    def show(self) -> dict[str, Any]:
        package = self.load()
        return {"identity": package.identity, "state": package.state}

    def next_allowed_action(self) -> NextAllowedAction:
        state = self.load().state
        status = state["status"]
        forward = FORWARD_TRANSITIONS.get(state["state"])
        operations: list[str] = []
        if status == "BLOCKED_ON_HUMAN":
            operations = ["resume"]
            forward = None
        elif status in {"ACTIVE", "REVISING"}:
            if forward and not state.get("legacy_mapping", False):
                operations.append("advance")
            operations.extend(["block", "abandon"])
            if state["state"] == "PILOT_REVIEW" and not state.get("legacy_mapping", False):
                operations.append("revise")
        return NextAllowedAction(
            channel_id=state["channel_id"],
            state=state["state"],
            status=status,
            allowed_operations=tuple(operations),
            forward_state=forward if "advance" in operations else None,
            requires_prerequisite_refs=bool(
                "advance" in operations and state["state"] != "CHANNEL_INIT"
            ),
            requires_human_decision=bool(
                "advance" in operations and forward
                and (state["state"], forward) in HUMAN_GATE_TRANSITIONS
            ),
            next_action=state["next_action"],
            waiting_for=state["waiting_for"],
        )

    def _transition_requirements(
        self,
        state: dict[str, Any],
        target: str,
        prerequisite_refs: list[str],
        human_decision_ref: str | None,
    ) -> dict[str, Any]:
        if state["status"] not in {"ACTIVE", "REVISING"}:
            raise ChannelStateError(f"cannot advance while status is {state['status']}")
        if state.get("legacy_mapping", False):
            raise ChannelStateError("legacy-mapped channels require an explicit future migration before forward advance")
        expected = FORWARD_TRANSITIONS.get(state["state"])
        if expected is None:
            raise ChannelStateError(f"{state['state']} has no forward transition")
        if target != expected:
            raise ChannelStateError(f"illegal transition {state['state']} -> {target}; expected {expected}")
        refs = sorted(set(prerequisite_refs))
        if state["state"] != "CHANNEL_INIT" and not refs:
            raise ChannelStateError(f"{state['state']} -> {target} requires at least one prerequisite reference")
        requires_human = (state["state"], target) in HUMAN_GATE_TRANSITIONS
        if requires_human and not (human_decision_ref or "").strip():
            raise ChannelStateError(f"{state['state']} -> {target} requires an explicit human decision reference")
        if requires_human:
            resolved = (self.repository_root / human_decision_ref).resolve()
            if not resolved.is_relative_to(self.repository_root) or not resolved.exists():
                raise ChannelStateError(
                    f"{state['state']} -> {target} human decision reference does not resolve "
                    f"to an existing repository path: {human_decision_ref}"
                )
        return {
            "from_state": state["state"],
            "to_state": target,
            "requires_prerequisite_refs": state["state"] != "CHANNEL_INIT",
            "requires_human_decision": requires_human,
            "prerequisite_refs": refs,
        }

    def validate_transition(
        self,
        target: str,
        *,
        prerequisite_refs: list[str] | None = None,
        human_decision_ref: str | None = None,
    ) -> dict[str, Any]:
        state = self.load().state
        requirements = self._transition_requirements(
            state, target, prerequisite_refs or [], human_decision_ref
        )
        for reference in requirements["prerequisite_refs"]:
            path = (self.repository_root / reference).resolve()
            if not path.is_relative_to(self.repository_root):
                raise ChannelStateError(f"prerequisite path escapes repository root: {reference}")
            if not path.exists():
                raise ChannelStateError(f"prerequisite path does not exist: {reference}")
        return requirements

    @staticmethod
    def _upgrade(state: dict[str, Any]) -> dict[str, Any]:
        value = copy.deepcopy(state)
        if value["schema_version"] == "0.1.0":
            value["schema_version"] = "0.2.0"
            value["legacy_mapping"] = value["completed"] != completed_prefix_for(value["state"])
            value["events"] = []
        return value

    def _apply(
        self,
        operation: str,
        *,
        actor: str,
        occurred_at: str | None,
        reason: str,
        expected_revision: int | None,
        transform: Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]],
    ) -> dict[str, Any]:
        if not actor.strip() or not reason.strip():
            raise ChannelStateError("actor and reason are required")
        with self._write_lock():
            package = self.load()
            current = package.state
            if expected_revision is not None and current["revision"] != expected_revision:
                raise ChannelStateError(
                    f"channel state revision changed: expected {expected_revision}, found {current['revision']}"
                )
            new_state, event_details = transform(copy.deepcopy(current))
            new_state = self._upgrade(new_state)
            new_state["revision"] = current["revision"] + 1
            new_state["updated_at"] = _timestamp(occurred_at)
            refs = sorted(set(event_details.get("prerequisite_refs", [])))
            new_state["source_refs"] = list(dict.fromkeys([*new_state["source_refs"], *refs]))
            events = list(new_state["events"])
            seed = {
                "sequence": len(events) + 1,
                "channel_id": current["channel_id"],
                "operation": operation,
                "from_state": current["state"],
                "to_state": new_state["state"],
                "from_status": current["status"],
                "to_status": new_state["status"],
                "occurred_at": new_state["updated_at"],
                "actor": actor.strip(),
                "reason": reason.strip(),
                "prerequisite_refs": refs,
                "human_decision_ref": event_details.get("human_decision_ref"),
                "invalidated_states": event_details.get("invalidated_states", []),
                "state_revision": new_state["revision"],
                "previous_event_id": events[-1]["event_id"] if events else None,
            }
            events.append({"event_id": event_id_for(seed), **seed})
            new_state["events"] = events
            try:
                validate_channel_state_document(new_state, package.identity["id"], self.repository_root)
            except ChannelValidationError as exc:
                raise ChannelStateError(str(exc)) from exc
            _write_atomic(self.state_path, new_state)
            return new_state

    def advance(
        self,
        target: str,
        *,
        next_action: str,
        actor: str,
        reason: str,
        prerequisite_refs: list[str] | None = None,
        human_decision_ref: str | None = None,
        occurred_at: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        def transform(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            requirements = self._transition_requirements(
                state, target, prerequisite_refs or [], human_decision_ref
            )
            state["completed"] = [*state["completed"], state["state"]]
            state["state"] = target
            state["status"] = "COMPLETE" if target == "CHANNEL_READY" else "ACTIVE"
            state["active_experiment"] = None
            state["waiting_for"] = None
            state["blocker"] = None
            state["resume_state"] = None
            state["next_action"] = next_action.strip()
            return state, {
                "prerequisite_refs": requirements["prerequisite_refs"],
                "human_decision_ref": human_decision_ref,
            }

        return self._apply(
            "ADVANCE", actor=actor, occurred_at=occurred_at, reason=reason,
            expected_revision=expected_revision, transform=transform,
        )

    def block_on_human(
        self,
        *,
        reason_code: str,
        summary: str,
        question: str,
        required_action: str,
        actor: str,
        occurred_at: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        def transform(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            if state["status"] not in {"ACTIVE", "REVISING"}:
                raise ChannelStateError(f"cannot block while status is {state['status']}")
            resume_status = state["status"]
            state["status"] = "BLOCKED_ON_HUMAN"
            state["waiting_for"] = "human_decision"
            state["resume_state"] = state["state"]
            state["next_action"] = required_action.strip()
            state["blocker"] = {
                "kind": "HUMAN_DECISION",
                "reason_code": reason_code.strip(),
                "summary": summary.strip(),
                "question": question.strip(),
                "required_action": required_action.strip(),
                "resume_status": resume_status,
            }
            return state, {}

        return self._apply(
            "BLOCK", actor=actor, occurred_at=occurred_at, reason=summary,
            expected_revision=expected_revision, transform=transform,
        )

    def resume(
        self,
        *,
        human_response_ref: str,
        next_action: str,
        actor: str,
        occurred_at: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        if not human_response_ref.strip():
            raise ChannelStateError("resume requires an explicit human response reference")

        def transform(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            if state["status"] != "BLOCKED_ON_HUMAN" or not state["blocker"]:
                raise ChannelStateError("channel is not blocked on a human decision")
            state["state"] = state["resume_state"]
            state["status"] = state["blocker"].get("resume_status", "ACTIVE")
            state["waiting_for"] = None
            state["blocker"] = None
            state["resume_state"] = None
            state["next_action"] = next_action.strip()
            return state, {"human_decision_ref": human_response_ref.strip()}

        return self._apply(
            "RESUME", actor=actor, occurred_at=occurred_at,
            reason=f"Human response recorded: {human_response_ref.strip()}",
            expected_revision=expected_revision, transform=transform,
        )

    def revise(
        self,
        target: str,
        *,
        decision_ref: str,
        next_action: str,
        reason: str,
        actor: str,
        occurred_at: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        if target not in REVISION_TARGETS:
            raise ChannelStateError(f"revision target {target!r} is not allowed")
        if not decision_ref.strip():
            raise ChannelStateError("revision requires an explicit review decision reference")

        def transform(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            if state["state"] != "PILOT_REVIEW" or state["status"] != "ACTIVE":
                raise ChannelStateError("revision is allowed only from active PILOT_REVIEW")
            if state.get("legacy_mapping", False):
                raise ChannelStateError("legacy-mapped channels cannot use revision routing")
            target_index = WORKFLOW_STATES.index(target)
            invalidated = [item for item in state["completed"] if WORKFLOW_STATES.index(item) >= target_index]
            invalidated.append("PILOT_REVIEW")
            state["state"] = target
            state["status"] = "REVISING"
            state["completed"] = completed_prefix_for(target)
            state["waiting_for"] = None
            state["blocker"] = None
            state["resume_state"] = None
            state["next_action"] = next_action.strip()
            return state, {
                "human_decision_ref": decision_ref.strip(),
                "invalidated_states": invalidated,
            }

        return self._apply(
            "REVISE", actor=actor, occurred_at=occurred_at, reason=reason,
            expected_revision=expected_revision, transform=transform,
        )

    def abandon(
        self,
        *,
        reason: str,
        decision_ref: str,
        actor: str,
        occurred_at: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        if not decision_ref.strip():
            raise ChannelStateError("abandon requires an explicit decision reference")

        def transform(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            if state["status"] in {"COMPLETE", "ABANDONED"}:
                raise ChannelStateError(f"cannot abandon while status is {state['status']}")
            state["status"] = "ABANDONED"
            state["waiting_for"] = None
            state["blocker"] = None
            state["resume_state"] = None
            state["next_action"] = "No further action; channel direction was abandoned."
            return state, {"human_decision_ref": decision_ref.strip()}

        return self._apply(
            "ABANDON", actor=actor, occurred_at=occurred_at, reason=reason,
            expected_revision=expected_revision, transform=transform,
        )
