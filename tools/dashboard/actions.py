"""A fixed whitelist of dashboard-triggerable actions, each shelling out to an existing CLI tool.

No action here re-implements CLI logic, and no action ever passes through a shell string —
every invocation builds an explicit argv list. Gated actions (a human decision point) require
the caller to have already passed a browser-side confirm step; this module additionally
requires a non-empty `confirmed_by` for those and appends `--yes` itself.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


class ActionError(ValueError):
    """A requested dashboard action is unknown, missing a required parameter, or was refused."""


class ActionSpec:
    def __init__(
        self,
        *,
        argv: list[str],
        flags: dict[str, str] | None = None,
        repeatable_flags: dict[str, str] | None = None,
        gated: bool = False,
        confirmed_by_field: str | None = None,
    ):
        self.argv = argv
        self.flags = flags or {}
        self.repeatable_flags = repeatable_flags or {}
        self.gated = gated
        self.confirmed_by_field = confirmed_by_field


ACTIONS: dict[str, ActionSpec] = {
    "advance": ActionSpec(
        argv=["tools/channel_state.py", "advance", "{package_root}", "{target}"],
        flags={"next_action": "--next-action", "actor": "--actor", "reason": "--reason", "human_decision_ref": "--human-decision-ref"},
        repeatable_flags={"prerequisite_ref": "--prerequisite-ref"},
        gated=False,
    ),
    "block": ActionSpec(
        argv=["tools/channel_state.py", "block", "{package_root}"],
        flags={"reason_code": "--reason-code", "summary": "--summary", "question": "--question", "required_action": "--required-action", "actor": "--actor"},
    ),
    "resume": ActionSpec(
        argv=["tools/channel_state.py", "resume", "{package_root}"],
        flags={"human_response_ref": "--human-response-ref", "next_action": "--next-action", "actor": "--actor"},
    ),
    "revise": ActionSpec(
        argv=["tools/channel_state.py", "revise", "{package_root}", "{target}"],
        flags={"decision_ref": "--decision-ref", "next_action": "--next-action", "reason": "--reason", "actor": "--actor"},
        gated=True, confirmed_by_field="actor",
    ),
    "abandon": ActionSpec(
        argv=["tools/channel_state.py", "abandon", "{package_root}"],
        flags={"decision_ref": "--decision-ref", "reason": "--reason", "actor": "--actor"},
        gated=True, confirmed_by_field="actor",
    ),
    "attach_foundation_decision": ActionSpec(
        argv=["tools/channel_foundation.py", "attach-decision", "{package_root}"],
        flags={"decision_ref": "--decision-ref"},
    ),
    "freeze_script_dna": ActionSpec(
        argv=["tools/script_dna.py", "freeze", "{package_root}"],
        flags={
            "decision_ref": "--decision-ref",
            "audition_example": "--audition-example",
            "audition_timing": "--audition-timing",
        },
        gated=True,
    ),
    "review_script_example": ActionSpec(
        argv=["tools/script_dna.py", "review-example", "{package_root}", "{example_id}"],
        flags={"decision": "--decision", "reviewer": "--reviewer", "reason": "--reason"},
        gated=True, confirmed_by_field="reviewer",
    ),
    "freeze_design_domain": ActionSpec(
        argv=["tools/design_dna.py", "{kind}", "freeze-domain", "{package_root}"],
        flags={"domain": "--domain", "decision_ref": "--decision-ref"},
        gated=True,
    ),
    "review_design_exemplar": ActionSpec(
        argv=["tools/design_exemplars.py", "--channel", "{channel_id}", "review", "{exemplar_id}"],
        flags={"decision": "--decision", "reviewer": "--reviewer", "reason": "--reason"},
        gated=True, confirmed_by_field="reviewer",
    ),
    "review_composition": ActionSpec(
        argv=["tools/design_dna.py", "visual", "review-composition", "{package_root}"],
        flags={"decision": "--decision", "reviewer": "--reviewer", "reason": "--reason"},
        gated=True, confirmed_by_field="reviewer",
    ),
    "review_motion_sample": ActionSpec(
        argv=["tools/design_dna.py", "motion", "review-sample", "{package_root}"],
        flags={"decision": "--decision", "reviewer": "--reviewer", "reason": "--reason"},
        gated=True, confirmed_by_field="reviewer",
    ),
    "freeze_identity_domain": ActionSpec(
        argv=["tools/channel_identity.py", "freeze-domain", "{package_root}"],
        flags={"domain": "--domain", "decision_ref": "--decision-ref"},
        gated=True,
    ),
    "review_identity_candidate": ActionSpec(
        argv=["tools/channel_identity.py", "review", "--channel", "{channel_id}", "{candidate_id}"],
        flags={"decision": "--decision", "reviewer": "--reviewer", "reason": "--reason"},
        gated=True, confirmed_by_field="reviewer",
    ),
    "review_asset_component": ActionSpec(
        argv=["tools/asset_registry.py", "review", "{component_path}"],
        flags={"decision": "--decision", "reviewer": "--reviewer", "reason": "--reason"},
        gated=True, confirmed_by_field="reviewer",
    ),
    "record_pilot_review": ActionSpec(
        argv=["tools/pilot.py", "record-review", "{package_root}", "{pilot_id}"],
        flags={"decision": "--decision", "decided_by": "--decided-by", "rationale": "--rationale", "decision_ref": "--decision-ref", "revise_target": "--revise-target"},
        gated=True, confirmed_by_field="decided_by",
    ),
    "freeze_pilot": ActionSpec(
        argv=["tools/pilot.py", "freeze", "{package_root}", "{pilot_id}"],
        flags={"new_channel_version": "--new-channel-version", "frozen_by": "--frozen-by"},
        gated=True, confirmed_by_field="frozen_by",
    ),
    "record_episode_review": ActionSpec(
        argv=["tools/episode.py", "record-review", "{package_root}", "{episode_id}"],
        flags={"decision": "--decision", "decided_by": "--decided-by", "rationale": "--rationale", "decision_ref": "--decision-ref"},
        gated=True, confirmed_by_field="decided_by",
    ),
}


def _substitute(token: str, params: dict[str, Any]) -> str:
    if token.startswith("{") and token.endswith("}"):
        key = token[1:-1]
        if key not in params:
            raise ActionError(f"missing required parameter: {key}")
        return str(params[key])
    return token


def run_action(
    action_name: str, params: dict[str, Any], *, confirmed: bool, repository_root: Path | None = None,
) -> subprocess.CompletedProcess:
    """Run a whitelisted action. `repository_root` (default: the real repo) is passed to the
    underlying CLI as `--root`, letting tests target an isolated directory without ever
    touching the real repository's channels/ tree; the CLI *scripts* themselves always come
    from this module's own `ROOT`, since that's where the actual .py files live."""

    spec = ACTIONS.get(action_name)
    if spec is None:
        raise ActionError(f"unknown dashboard action: {action_name!r}")
    if spec.gated:
        if not confirmed:
            raise ActionError(f"action {action_name!r} requires explicit confirmation")
        if spec.confirmed_by_field and not str(params.get(spec.confirmed_by_field, "")).strip():
            raise ActionError(f"action {action_name!r} requires a non-empty {spec.confirmed_by_field!r}")

    script_path = str(ROOT / _substitute(spec.argv[0], params))
    rest = [_substitute(token, params) for token in spec.argv[1:]]
    # `--root` MUST come immediately after the script and before any subcommand token: once
    # argparse's subparsers action consumes the subcommand, everything after belongs to the
    # subparser, which does not know about `--root`.
    argv = [sys.executable, script_path, "--root", str((repository_root or ROOT).resolve()), *rest]
    for key, flag in spec.flags.items():
        if key in params and params[key] not in (None, ""):
            argv.extend([flag, str(params[key])])
    for key, flag in spec.repeatable_flags.items():
        for value in params.get(key, []) or []:
            argv.extend([flag, str(value)])
    if spec.gated:
        argv.append("--yes")

    return subprocess.run(argv, capture_output=True, text=True, cwd=ROOT)
