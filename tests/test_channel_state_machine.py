from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.channel import (
    ChannelStateError,
    ChannelStateMachine,
    ChannelValidationError,
    validate_channel_package,
)
from engine.channel.workflow import completed_prefix_for


ROOT = Path(__file__).resolve().parents[1]
AT = "2026-08-23T12:00:00+00:00"


def write_runtime_package(
    root: Path,
    *,
    channel_id: str = "finance-demo",
    archetype: str = "DATA_STORY",
    state_name: str = "CHANNEL_INIT",
    status: str = "ACTIVE",
) -> Path:
    package = root / "channels" / channel_id
    package.mkdir(parents=True)
    identity = {
        "schema_version": "0.1.0",
        "id": channel_id,
        "name": channel_id.title(),
        "version": "0.1.0",
        "status": "DRAFT",
        "language": "en",
        "niche": {"primary": "synthetic-test"},
        "platform": {"primary": "YOUTUBE", "formats": ["SHORTS"]},
        "production": {"archetype": archetype, "renderer": "remotion"},
        "creation": {"mode": "ORIGINAL"},
        "canonical_sources": {"channel_state": f"channels/{channel_id}/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.2.0",
        "channel_id": channel_id,
        "revision": 0,
        "state": state_name,
        "status": status,
        "completed": completed_prefix_for(state_name),
        "active_experiment": None,
        "waiting_for": None,
        "blocker": None,
        "next_action": f"Continue {state_name}.",
        "resume_state": None,
        "source_refs": [f"channels/{channel_id}/channel.yaml"],
        "known_gaps": [],
        "legacy_mapping": False,
        "events": [],
        "updated_at": AT,
    }
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    return package


def load_state(package: Path) -> dict:
    return json.loads((package / "CHANNEL_STATE.json").read_text(encoding="utf-8"))


def evidence(root: Path, channel_id: str, name: str) -> str:
    relative = f"channels/{channel_id}/{name}.md"
    path = root / relative
    path.write_text(f"# {name}\n", encoding="utf-8")
    return relative


def test_finance_channel_advances_forward_and_rejects_skips(tmp_path: Path) -> None:
    package = write_runtime_package(tmp_path)
    runtime = ChannelStateMachine(package, tmp_path)
    with pytest.raises(ChannelStateError, match="illegal transition"):
        runtime.advance(
            "CHANNEL_READY", next_action="No.", actor="test", reason="skip",
            occurred_at=AT,
        )
    state = runtime.advance(
        "NICHE_INTELLIGENCE",
        next_action="Collect a market sample.",
        actor="test",
        reason="Identity fields validate.",
        occurred_at=AT,
        expected_revision=0,
    )
    assert state["completed"] == ["CHANNEL_INIT"]
    assert state["state"] == "NICHE_INTELLIGENCE"
    assert state["events"][0]["operation"] == "ADVANCE"

    niche_ref = evidence(tmp_path, "finance-demo", "niche-evidence")
    state = runtime.advance(
        "OPPORTUNITY_MAP",
        next_action="Build opportunity options.",
        actor="test",
        reason="Niche evidence recorded.",
        prerequisite_refs=[niche_ref],
        occurred_at="2026-08-23T12:01:00+00:00",
        expected_revision=1,
    )
    assert state["completed"] == ["CHANNEL_INIT", "NICHE_INTELLIGENCE"]
    assert niche_ref in state["source_refs"]


def test_transition_prerequisites_and_human_gate_are_enforced(tmp_path: Path) -> None:
    package = write_runtime_package(tmp_path, state_name="NICHE_INTELLIGENCE")
    runtime = ChannelStateMachine(package, tmp_path)
    with pytest.raises(ChannelStateError, match="prerequisite"):
        runtime.validate_transition("OPPORTUNITY_MAP")
    with pytest.raises(ChannelStateError, match="does not exist"):
        runtime.validate_transition(
            "OPPORTUNITY_MAP",
            prerequisite_refs=["channels/finance-demo/missing.md"],
        )

    package = write_runtime_package(tmp_path, channel_id="gate-demo", state_name="OPPORTUNITY_MAP")
    runtime = ChannelStateMachine(package, tmp_path)
    opportunity_ref = evidence(tmp_path, "gate-demo", "opportunity-map")
    with pytest.raises(ChannelStateError, match="human decision"):
        runtime.validate_transition("STRATEGY_SELECTION", prerequisite_refs=[opportunity_ref])
    rule = runtime.validate_transition(
        "STRATEGY_SELECTION",
        prerequisite_refs=[opportunity_ref],
        human_decision_ref="human-decision:strategy-001",
    )
    assert rule["requires_human_decision"] is True


def test_human_block_survives_restart_and_resume_requires_response(tmp_path: Path) -> None:
    package = write_runtime_package(tmp_path, channel_id="history-demo", archetype="MAP_STORY")
    runtime = ChannelStateMachine(package, tmp_path)
    blocked = runtime.block_on_human(
        reason_code="strategy_choice",
        summary="A strategy must be selected.",
        question="Choose A or B?",
        required_action="Record explicit A/B selection.",
        actor="test",
        occurred_at=AT,
    )
    assert blocked["status"] == "BLOCKED_ON_HUMAN"
    assert blocked["resume_state"] == "CHANNEL_INIT"
    assert blocked["blocker"]["question"] == "Choose A or B?"

    restarted = ChannelStateMachine(package, tmp_path)
    assert restarted.next_allowed_action().allowed_operations == ("resume",)
    with pytest.raises(ChannelStateError, match="human response"):
        restarted.resume(human_response_ref="", next_action="Continue.", actor="test")
    resumed = restarted.resume(
        human_response_ref="human-response:strategy-001",
        next_action="Continue initialization with choice A.",
        actor="test",
        occurred_at="2026-08-23T12:02:00+00:00",
        expected_revision=1,
    )
    assert resumed["status"] == "ACTIVE"
    assert resumed["blocker"] is None
    assert [item["operation"] for item in resumed["events"]] == ["BLOCK", "RESUME"]


def test_pilot_review_revision_invalidates_dependent_completion(tmp_path: Path) -> None:
    package = write_runtime_package(tmp_path, state_name="PILOT_REVIEW")
    runtime = ChannelStateMachine(package, tmp_path)
    revised = runtime.revise(
        "VISUAL_DNA_DISCOVERY",
        decision_ref="human-review:pilot-001-revise-visual",
        next_action="Revise Visual DNA candidates.",
        reason="Pilot visuals are inconsistent.",
        actor="test",
        occurred_at=AT,
    )
    assert revised["state"] == "VISUAL_DNA_DISCOVERY"
    assert revised["status"] == "REVISING"
    assert revised["completed"] == completed_prefix_for("VISUAL_DNA_DISCOVERY")
    invalidated = revised["events"][-1]["invalidated_states"]
    assert "VISUAL_DNA_DISCOVERY" in invalidated
    assert "PILOT_PRODUCTION" in invalidated
    assert "PILOT_REVIEW" in invalidated
    with pytest.raises(ChannelStateError, match="not allowed"):
        runtime.revise(
            "CHANNEL_INIT", decision_ref="human-review:x", next_action="No.",
            reason="No.", actor="test",
        )


def test_event_chain_corruption_and_missing_paths_fail_package_validation(tmp_path: Path) -> None:
    package = write_runtime_package(tmp_path)
    runtime = ChannelStateMachine(package, tmp_path)
    runtime.block_on_human(
        reason_code="choice", summary="Choose.", question="Which?",
        required_action="Answer.", actor="test", occurred_at=AT,
    )
    state = load_state(package)
    state["events"][0]["reason"] = "tampered"
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ChannelValidationError, match="event_id"):
        validate_channel_package(package, tmp_path)

    package = write_runtime_package(tmp_path, channel_id="missing-ref", state_name="NICHE_INTELLIGENCE")
    before = (package / "CHANNEL_STATE.json").read_bytes()
    with pytest.raises(ChannelStateError, match="does not exist"):
        ChannelStateMachine(package, tmp_path).advance(
            "OPPORTUNITY_MAP", next_action="Continue.", actor="test", reason="Evidence.",
            prerequisite_refs=["channels/missing-ref/not-there.md"], occurred_at=AT,
        )
    assert (package / "CHANNEL_STATE.json").read_bytes() == before


def test_state_mutation_is_deterministic_for_identical_inputs(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = write_runtime_package(first_root, channel_id="same")
    second = write_runtime_package(second_root, channel_id="same")
    kwargs = {
        "target": "NICHE_INTELLIGENCE",
        "next_action": "Collect market evidence.",
        "actor": "test",
        "reason": "Identity validates.",
        "occurred_at": AT,
    }
    first_state = ChannelStateMachine(first, first_root).advance(**kwargs)
    second_state = ChannelStateMachine(second, second_root).advance(**kwargs)
    assert first_state == second_state
    assert first_state["events"][0]["event_id"] == second_state["events"][0]["event_id"]


def test_abandon_requires_explicit_decision_and_is_terminal(tmp_path: Path) -> None:
    package = write_runtime_package(tmp_path)
    runtime = ChannelStateMachine(package, tmp_path)
    with pytest.raises(ChannelStateError, match="decision reference"):
        runtime.abandon(reason="Stop.", decision_ref="", actor="test")
    abandoned = runtime.abandon(
        reason="Owner abandoned direction.", decision_ref="human-decision:abandon-001",
        actor="test", occurred_at=AT,
    )
    assert abandoned["status"] == "ABANDONED"
    assert runtime.next_allowed_action().allowed_operations == ()
