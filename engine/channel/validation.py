"""Deterministic validation for a repository-owned Channel Package."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from .workflow import (
    FORWARD_TRANSITIONS,
    HUMAN_GATE_TRANSITIONS,
    REVISION_TARGETS,
    WORKFLOW_STATES,
    completed_prefix_for,
    event_id_for,
)


CONTRACT_ROOT = Path(__file__).resolve().parent / "contracts"


class ChannelValidationError(ValueError):
    """A Channel Package violates its schema or repository integrity rules."""


@dataclass(frozen=True)
class ChannelPackage:
    root: Path
    identity: dict[str, Any]
    state: dict[str, Any]


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ChannelValidationError(f"{path}: expected an object")
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ChannelValidationError(f"{path}: expected a mapping")
    return value


def _schema_errors(value: dict[str, Any], schema_path: Path, label: str) -> list[str]:
    schema = _load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{label} {location}: {error.message}")
    return errors


def _repository_path_error(repository_root: Path, value: str, label: str) -> str | None:
    path = (repository_root / value).resolve()
    if not path.is_relative_to(repository_root):
        return f"{label}: path escapes repository root: {value}"
    if not path.exists():
        return f"{label}: referenced path does not exist: {value}"
    return None


def channel_state_semantic_errors(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if state["schema_version"] != "0.2.0":
        return errors
    expected_completed = completed_prefix_for(state["state"])
    if not state["legacy_mapping"] and state["completed"] != expected_completed:
        errors.append(
            f"completed stages must be the canonical prefix before {state['state']}: {expected_completed}"
        )
    if state["legacy_mapping"]:
        positions = [WORKFLOW_STATES.index(item) for item in state["completed"]]
        if positions != sorted(positions) or state["state"] in state["completed"]:
            errors.append("legacy completed stages must be ordered and exclude the current state")
    events = state["events"]
    previous = None
    previous_revision = None
    for index, event in enumerate(events, start=1):
        if event["sequence"] != index:
            errors.append(f"events[{index - 1}].sequence must be {index}")
        if event["previous_event_id"] != previous:
            errors.append(f"events[{index - 1}].previous_event_id does not match the event chain")
        if event["channel_id"] != state["channel_id"]:
            errors.append(f"events[{index - 1}].channel_id does not match channel state")
        seed = {key: value for key, value in event.items() if key != "event_id"}
        if event["event_id"] != event_id_for(seed):
            errors.append(f"events[{index - 1}].event_id does not match its content")
        if previous_revision is not None and event["state_revision"] != previous_revision + 1:
            errors.append(f"events[{index - 1}].state_revision must increment by one")
        if index > 1:
            prior = events[index - 2]
            if event["from_state"] != prior["to_state"] or event["from_status"] != prior["to_status"]:
                errors.append(f"events[{index - 1}] does not continue the prior state/status")
        operation = event["operation"]
        same_state = event["from_state"] == event["to_state"]
        has_human_ref = bool(event["human_decision_ref"])
        if operation == "ADVANCE":
            expected = FORWARD_TRANSITIONS.get(event["from_state"])
            expected_status = "COMPLETE" if event["to_state"] == "CHANNEL_READY" else "ACTIVE"
            if (
                event["from_status"] not in {"ACTIVE", "REVISING"}
                or event["to_state"] != expected
                or event["to_status"] != expected_status
            ):
                errors.append(f"events[{index - 1}] is not a legal forward transition")
            if event["from_state"] != "CHANNEL_INIT" and not event["prerequisite_refs"]:
                errors.append(f"events[{index - 1}] advance is missing prerequisite references")
            if (
                (event["from_state"], event["to_state"]) in HUMAN_GATE_TRANSITIONS
                and not has_human_ref
            ):
                errors.append(f"events[{index - 1}] human-gated advance is missing a decision reference")
        elif operation == "BLOCK":
            if not same_state or event["from_status"] not in {"ACTIVE", "REVISING"} or event["to_status"] != "BLOCKED_ON_HUMAN":
                errors.append(f"events[{index - 1}] is not a legal human block")
        elif operation == "RESUME":
            if not same_state or event["from_status"] != "BLOCKED_ON_HUMAN" or event["to_status"] not in {"ACTIVE", "REVISING"} or not has_human_ref:
                errors.append(f"events[{index - 1}] is not a legal human resume")
        elif operation == "REVISE":
            if (
                event["from_state"] != "PILOT_REVIEW"
                or event["from_status"] != "ACTIVE"
                or event["to_state"] not in REVISION_TARGETS
                or event["to_status"] != "REVISING"
                or not has_human_ref
                or not event["invalidated_states"]
            ):
                errors.append(f"events[{index - 1}] is not a legal pilot revision")
        elif operation == "ABANDON":
            if not same_state or event["from_status"] in {"COMPLETE", "ABANDONED"} or event["to_status"] != "ABANDONED" or not has_human_ref:
                errors.append(f"events[{index - 1}] is not a legal abandonment")
        previous = event["event_id"]
        previous_revision = event["state_revision"]
    if events:
        latest = events[-1]
        if latest["state_revision"] != state["revision"]:
            errors.append("latest event revision does not match channel state revision")
        if latest["to_state"] != state["state"] or latest["to_status"] != state["status"]:
            errors.append("latest event destination does not match current channel state/status")
    elif state["revision"] != 0:
        errors.append("a v0.2 state without events must have revision 0")
    return errors


def missing_historical_refs(state: dict[str, Any], repository_root: Path) -> list[str]:
    """Labels of historical references whose files no longer exist.

    Escapes are not reported here — they remain hard errors. A missing file
    means history degraded (usually a deleted note), not that the channel is
    unreadable: callers surface these as recoverable warnings.
    """
    repository_root = repository_root.resolve()
    warnings: list[str] = []
    references = [(f"source_refs[{index}]", value) for index, value in enumerate(state["source_refs"])]
    for event_index, event in enumerate(state.get("events", [])):
        references.extend(
            (f"events[{event_index}].prerequisite_refs[{ref_index}]", value)
            for ref_index, value in enumerate(event["prerequisite_refs"])
        )
    for label, value in references:
        path = (repository_root / value).resolve()
        if path.is_relative_to(repository_root) and not path.exists():
            warnings.append(f"{label}: referenced path no longer exists: {value}")
    return warnings


def validate_channel_state_document(
    state: dict[str, Any], channel_id: str, repository_root: Path,
    allow_missing_historical_refs: bool = False,
) -> None:
    errors = _schema_errors(state, CONTRACT_ROOT / "channel-state.schema.json", "channel state")
    if not errors and state["channel_id"] != channel_id:
        errors.append(f"channel state id {state['channel_id']!r} does not match identity id {channel_id!r}")
    if not errors:
        errors.extend(channel_state_semantic_errors(state))
    if not errors:
        references = [(f"source_refs[{index}]", value) for index, value in enumerate(state["source_refs"])]
        for event_index, event in enumerate(state.get("events", [])):
            references.extend(
                (f"events[{event_index}].prerequisite_refs[{ref_index}]", value)
                for ref_index, value in enumerate(event["prerequisite_refs"])
            )
        for label, value in references:
            path = (repository_root.resolve() / value).resolve()
            if not path.is_relative_to(repository_root.resolve()):
                errors.append(f"{label}: path escapes repository root: {value}")
            elif not path.exists() and not allow_missing_historical_refs:
                errors.append(f"{label}: referenced path does not exist: {value}")
    if errors:
        raise ChannelValidationError("\n".join(errors))


def validate_channel_package(
    package_root: Path, repository_root: Path, allow_missing_historical_refs: bool = False,
) -> ChannelPackage:
    """Load and validate one Channel Package, raising one aggregated error."""

    repository_root = repository_root.resolve()
    package_root = package_root.resolve()
    if not package_root.is_relative_to(repository_root):
        raise ChannelValidationError(f"package escapes repository root: {package_root}")

    identity_path = package_root / "channel.yaml"
    state_path = package_root / "CHANNEL_STATE.json"
    try:
        identity = _load_yaml(identity_path)
        state = _load_json(state_path)
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ChannelValidationError(str(exc)) from exc

    errors = _schema_errors(identity, CONTRACT_ROOT / "channel.schema.json", "channel identity")
    if errors:
        raise ChannelValidationError("\n".join(errors))

    channel_id = identity["id"]
    if package_root.name != channel_id:
        errors.append(f"package directory {package_root.name!r} does not match channel id {channel_id!r}")
    try:
        validate_channel_state_document(
            state, channel_id, repository_root,
            allow_missing_historical_refs=allow_missing_historical_refs,
        )
    except ChannelValidationError as exc:
        errors.append(str(exc))
    if state["state"] in state["completed"]:
        errors.append(f"active workflow state {state['state']!r} cannot also be completed")

    canonical = identity["canonical_sources"]
    references: list[tuple[str, str]] = []
    for key, value in canonical.items():
        if isinstance(value, list):
            references.extend((f"canonical_sources.{key}[{index}]", item) for index, item in enumerate(value))
        else:
            references.append((f"canonical_sources.{key}", value))
    for label, value in references:
        error = _repository_path_error(repository_root, value, label)
        if error:
            errors.append(error)

    expected_state = state_path.relative_to(repository_root).as_posix()
    if canonical["channel_state"] != expected_state:
        errors.append(
            "canonical_sources.channel_state must point to this package's CHANNEL_STATE.json "
            f"({expected_state})"
        )

    if errors:
        raise ChannelValidationError("\n".join(errors))
    return ChannelPackage(package_root, identity, state)
