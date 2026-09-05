from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.pilot import (
    PilotValidationError,
    freeze_pilot,
    pilot_path,
    plan_pilot,
    record_production,
    record_review,
)


AT = "2026-09-05T12:00:00+00:00"


def write_package(root: Path, channel_id: str = "pilot-channel") -> Path:
    package = root / "channels" / channel_id
    package.mkdir(parents=True)
    identity = {
        "schema_version": "0.1.0", "id": channel_id, "name": channel_id.title(), "version": "0.1.0",
        "status": "DRAFT", "language": "en", "niche": {"primary": "science"},
        "platform": {"primary": "YOUTUBE", "formats": ["SHORTS"]},
        "production": {"archetype": "ILLUSTRATED_EXPLAINER", "renderer": "remotion"},
        "creation": {"mode": "ORIGINAL"},
        "canonical_sources": {"channel_state": f"channels/{channel_id}/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.2.0", "channel_id": channel_id, "revision": 0, "state": "CHANNEL_INIT",
        "status": "ACTIVE", "completed": [], "active_experiment": None, "waiting_for": None,
        "blocker": None, "next_action": "test", "resume_state": None,
        "source_refs": [f"channels/{channel_id}/channel.yaml"], "known_gaps": [],
        "legacy_mapping": False, "events": [], "updated_at": AT,
    }
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    return package


def write_evidence(root: Path, relative: str, *, artifact_type: str, artifact_id: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"artifact_type": artifact_type, "artifact_id": artifact_id, "note": "synthetic"}), encoding="utf-8")
    return path


def test_plan_produce_review_go_freeze_lifecycle(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    plan_pilot(
        package, tmp_path, pilot_id="pilot-1", topic="How caffeine works",
        target_duration_seconds=25.0, integration_goals=["Prove Script DNA", "Prove Visual DNA"],
    )
    write_evidence(tmp_path, "evidence/scene.json", artifact_type="scene_candidate_manifest", artifact_id="scene-candidate:caffeine:abc123")
    write_evidence(tmp_path, "evidence/eval.json", artifact_type="evaluation_result", artifact_id="evaluation-result:abc123")
    record_production(
        package, tmp_path, "pilot-1",
        scene_candidate_manifest_paths=["evidence/scene.json"], evaluation_result_paths=["evidence/eval.json"],
        render_ref="evidence/render.mp4",
    )
    path = pilot_path(package, "pilot-1")
    document = json.loads(path.read_text(encoding="utf-8"))
    assert len(document["production"]["scene_candidate_manifest_refs"]) == 1
    assert len(document["production"]["evaluation_result_refs"]) == 1

    record_review(
        package, tmp_path, "pilot-1", decision="GO", decided_by="Seb",
        rationale="Clear mechanism, good pacing.", decision_ref="channels/pilot-channel/channel.yaml",
    )
    freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.2.0", frozen_by="Seb")
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["freeze"]["frozen"] is True
    assert document["freeze"]["new_channel_version"] == "0.2.0"
    identity = yaml.safe_load((package / "channel.yaml").read_text(encoding="utf-8"))
    assert identity["version"] == "0.2.0"


def test_record_review_rejects_empty_decision_ref(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    plan_pilot(package, tmp_path, pilot_id="pilot-1", topic="t", target_duration_seconds=25.0, integration_goals=["g"])
    with pytest.raises(PilotValidationError, match="non-empty"):
        record_review(package, tmp_path, "pilot-1", decision="GO", decided_by="Seb", rationale="r", decision_ref="")


def test_revise_requires_valid_revise_target(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    plan_pilot(package, tmp_path, pilot_id="pilot-1", topic="t", target_duration_seconds=25.0, integration_goals=["g"])
    with pytest.raises(PilotValidationError, match="REVISE requires revise_target"):
        record_review(
            package, tmp_path, "pilot-1", decision="REVISE", decided_by="Seb", rationale="Needs a stronger hook.",
            decision_ref="channels/pilot-channel/channel.yaml", revise_target=None,
        )
    with pytest.raises(PilotValidationError, match="REVISE requires revise_target"):
        record_review(
            package, tmp_path, "pilot-1", decision="REVISE", decided_by="Seb", rationale="Needs a stronger hook.",
            decision_ref="channels/pilot-channel/channel.yaml", revise_target="NOT_A_REAL_STATE",
        )
    record_review(
        package, tmp_path, "pilot-1", decision="REVISE", decided_by="Seb", rationale="Needs a stronger hook.",
        decision_ref="channels/pilot-channel/channel.yaml", revise_target="VISUAL_DNA_DISCOVERY",
    )


def test_freeze_requires_go_decision(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    plan_pilot(package, tmp_path, pilot_id="pilot-1", topic="t", target_duration_seconds=25.0, integration_goals=["g"])
    record_review(
        package, tmp_path, "pilot-1", decision="ABANDON_DIRECTION", decided_by="Seb",
        rationale="Wrong niche entirely.", decision_ref="channels/pilot-channel/channel.yaml",
    )
    with pytest.raises(PilotValidationError, match="only be frozen after a GO"):
        freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.2.0", frozen_by="Seb")


def test_validate_pilot_detects_tampered_evidence(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    plan_pilot(package, tmp_path, pilot_id="pilot-1", topic="t", target_duration_seconds=25.0, integration_goals=["g"])
    evidence_path = write_evidence(tmp_path, "evidence/scene.json", artifact_type="scene_candidate_manifest", artifact_id="scene-candidate:x:abc123")
    record_production(package, tmp_path, "pilot-1", scene_candidate_manifest_paths=["evidence/scene.json"])

    # Tamper with the referenced evidence file after it was recorded.
    evidence_path.write_text(json.dumps({"artifact_type": "scene_candidate_manifest", "artifact_id": "scene-candidate:x:abc123", "note": "TAMPERED"}), encoding="utf-8")
    from engine.pilot import validate_pilot

    document = json.loads(pilot_path(package, "pilot-1").read_text(encoding="utf-8"))
    with pytest.raises(PilotValidationError, match="sha256 mismatch"):
        validate_pilot(document, repository_root=tmp_path)
