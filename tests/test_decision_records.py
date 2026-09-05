"""Phase 3b: structured decision records on human gates and reviews."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.channel import ChannelStateError, ChannelStateMachine
from engine.decisions import DecisionError, validate_record_file, write_record
from engine.pilot import PilotValidationError, plan_pilot, record_production, record_review


AT = "2026-08-23T12:00:00+00:00"


def write_package(root: Path, channel_id: str = "decide-demo") -> Path:
    package = root / "channels" / channel_id
    package.mkdir(parents=True)
    identity = {
        "schema_version": "0.1.0", "id": channel_id, "name": channel_id.title(),
        "version": "0.1.0", "status": "DRAFT", "language": "en",
        "niche": {"primary": "science"},
        "platform": {"primary": "YOUTUBE", "formats": ["SHORTS"]},
        "production": {"archetype": "ILLUSTRATED_EXPLAINER", "renderer": "remotion"},
        "creation": {"mode": "ORIGINAL"},
        "canonical_sources": {"channel_state": f"channels/{channel_id}/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.2.0", "channel_id": channel_id, "revision": 0,
        "state": "CHANNEL_INIT", "status": "ACTIVE", "completed": [],
        "active_experiment": None, "waiting_for": None, "blocker": None,
        "next_action": "x", "resume_state": None,
        "source_refs": [f"channels/{channel_id}/channel.yaml"], "known_gaps": [],
        "legacy_mapping": False, "events": [], "updated_at": AT,
    }
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    return package


def test_strategy_record_requires_selection_rejection_revisit(tmp_path: Path) -> None:
    path = tmp_path / "strategy.md"
    with pytest.raises(DecisionError, match="rejected alternative"):
        write_record(
            path, kind="strategy", title="Strategy", summary="Go mechanism-first.",
            selected=["opportunity:abc"], author="Seb",
        )
    assert not path.exists()
    write_record(
        path, kind="strategy", title="Strategy", summary="Go mechanism-first.",
        selected=["opportunity:abc"], rejected=["opportunity:xyz"],
        constraint="One pilot.", revisit="Revisit after 3 episodes.", author="Seb",
    )
    metadata = validate_record_file(path, expected_kind="strategy")
    assert metadata["selected"] == ["opportunity:abc"]
    with pytest.raises(DecisionError, match="already exists"):
        write_record(
            path, kind="strategy", title="Again", summary="x",
            selected=["a"], rejected=["b"], revisit="later",
        )


def test_review_record_requires_decision_and_rev(tmp_path: Path) -> None:
    path = tmp_path / "review.md"
    with pytest.raises(DecisionError, match="production rev"):
        write_record(
            path, kind="review", title="Pilot GO", summary="Good.",
            decision="GO", author="Seb",
        )
    write_record(
        path.parent / "review-ok.md", kind="review", title="Pilot GO",
        summary="Good pacing.", decision="GO", rev="rev-0123456789ab", author="Seb",
    )
    with pytest.raises(DecisionError, match="expected a strategy"):
        validate_record_file(path.parent / "review-ok.md", expected_kind="strategy")


def test_unmarked_files_keep_working(tmp_path: Path) -> None:
    path = tmp_path / "note.md"
    path.write_text("# Just a note\n\nApproved.\n", encoding="utf-8")
    assert validate_record_file(path, expected_kind="strategy") == {}


def test_strategy_gate_accepts_structured_or_plain_notes(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    runtime = ChannelStateMachine(package, tmp_path)
    prereq = tmp_path / "channels" / "decide-demo" / "evidence.md"
    prereq.write_text("# Evidence\n", encoding="utf-8")
    ref = prereq.relative_to(tmp_path).as_posix()
    runtime.advance("NICHE_INTELLIGENCE", next_action="n", actor="a", reason="r")
    runtime.advance("OPPORTUNITY_MAP", next_action="n", actor="a", reason="r", prerequisite_refs=[ref])

    # A marked record of the wrong kind is refused ...
    review_note = tmp_path / "channels" / "decide-demo" / "review.md"
    write_record(
        review_note, kind="review", title="X", summary="Y",
        decision="GO", rev="rev-0123456789ab",
    )
    with pytest.raises(ChannelStateError, match="expected a strategy"):
        runtime.advance(
            "STRATEGY_SELECTION", next_action="n", actor="a", reason="r",
            prerequisite_refs=[ref],
            human_decision_ref=review_note.relative_to(tmp_path).as_posix(),
        )
    # ... a valid strategy record and a plain note both pass.
    strategy_note = tmp_path / "channels" / "decide-demo" / "strategy.md"
    write_record(
        strategy_note, kind="strategy", title="Strategy", summary="Mechanism-first.",
        selected=["opportunity:abc"], rejected=["opportunity:xyz"],
        revisit="After 3 episodes.",
    )
    runtime.advance(
        "STRATEGY_SELECTION", next_action="n", actor="a", reason="r",
        prerequisite_refs=[ref],
        human_decision_ref=strategy_note.relative_to(tmp_path).as_posix(),
    )


def _pilot_media(root: Path) -> None:
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "script.md").write_text("# Script\n", encoding="utf-8")
    (root / "evidence" / "voiceover.wav").write_bytes(b"RIFF" + b"\x00" * 10)
    (root / "evidence" / "render.mp4").write_bytes(b"video")
    for relative, artifact_type, artifact_id in (
        ("evidence/scene.json", "scene_candidate_manifest", "scene-candidate:x:abc123"),
        ("evidence/eval.json", "evaluation_result", "evaluation-result:abc123"),
    ):
        (root / relative).write_text(
            json.dumps({"artifact_type": artifact_type, "artifact_id": artifact_id}),
            encoding="utf-8",
        )


def test_pilot_review_binds_marked_note_to_decision_and_rev(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    _pilot_media(tmp_path)
    plan_pilot(package, tmp_path, pilot_id="pilot-1", topic="t",
               target_duration_seconds=25.0, integration_goals=["g"])
    record_production(
        package, tmp_path, "pilot-1",
        scene_candidate_manifest_paths=["evidence/scene.json"],
        evaluation_result_paths=["evidence/eval.json"],
        script_ref="evidence/script.md", voiceover_ref="evidence/voiceover.wav",
        render_ref="evidence/render.mp4",
    )
    from engine.production import production_revision
    from engine.pilot import pilot_path

    document = json.loads(pilot_path(package, "pilot-1").read_text(encoding="utf-8"))
    rev = production_revision(document["production"], repository_root=tmp_path)

    note = tmp_path / "channels" / "decide-demo" / "go.md"
    write_record(
        note, kind="review", title="Pilot GO", summary="Fixed pacing.",
        decision="REVISE", rev=rev,
    )
    with pytest.raises(PilotValidationError, match="records 'REVISE' but the review says 'GO'"):
        record_review(
            package, tmp_path, "pilot-1", decision="GO", decided_by="Seb",
            rationale="Good.", decision_ref=note.relative_to(tmp_path).as_posix(),
        )
    note.unlink()
    write_record(
        note, kind="review", title="Pilot GO", summary="Fixed pacing.",
        decision="GO", rev=rev,
    )
    record_review(
        package, tmp_path, "pilot-1", decision="GO", decided_by="Seb",
        rationale="Good.", decision_ref=note.relative_to(tmp_path).as_posix(),
    )
