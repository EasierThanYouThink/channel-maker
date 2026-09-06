from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.episode import (
    EpisodeValidationError,
    episode_path,
    plan_episode,
    record_production,
    record_review,
    validate_episode,
)

AT = "2026-09-05T12:00:00+00:00"


def write_package(root: Path, channel_id: str = "episode-channel") -> Path:
    package = root / "channels" / channel_id
    package.mkdir(parents=True)
    identity = {
        "schema_version": "0.1.0", "id": channel_id, "name": channel_id.title(), "version": "0.2.0",
        "status": "CHANNEL_READY", "language": "en", "niche": {"primary": "science"},
        "platform": {"primary": "YOUTUBE", "formats": ["SHORTS"]},
        "production": {"archetype": "ILLUSTRATED_EXPLAINER", "renderer": "remotion"},
        "creation": {"mode": "ORIGINAL"},
        "canonical_sources": {"channel_state": f"channels/{channel_id}/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.3.0", "channel_id": channel_id, "revision": 0, "state": "CHANNEL_READY",
        "status": "COMPLETE",
        "completed": [
            "CHANNEL_INIT", "NICHE_INTELLIGENCE", "STRATEGY_SELECTION",
            "CHANNEL_FOUNDATION", "SCRIPT_DNA_DISCOVERY", "DESIGN_DNA_DISCOVERY",
            "CHANNEL_IDENTITY", "PILOT_PRODUCTION", "PILOT_REVIEW",
        ],
        "active_experiment": None, "waiting_for": None,
        "blocker": None, "next_action": "Produce episodes.", "resume_state": None,
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


def write_production_media(root: Path, prefix: str = "evidence") -> dict[str, str]:
    """Create the real files a GO decision requires: script, audio, render."""
    from engine.production.probing import encode_minimal_mp4, encode_minimal_wav

    script = root / prefix / "script.md"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("# Script\n", encoding="utf-8")
    audio = root / prefix / "voiceover.wav"
    audio.write_bytes(encode_minimal_wav())
    render = root / prefix / "render.mp4"
    render.write_bytes(encode_minimal_mp4())
    return {
        "script_ref": script.relative_to(root).as_posix(),
        "voiceover_ref": audio.relative_to(root).as_posix(),
        "render_ref": render.relative_to(root).as_posix(),
    }


def test_plan_produce_review_go_lifecycle(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    plan_episode(
        package, tmp_path, episode_id="ep-001", topic="How caffeine works",
        target_duration_seconds=25.0, opportunity_ref="opportunity-proposal:science:abc123",
    )
    write_evidence(tmp_path, "evidence/scene.json", artifact_type="scene_candidate_manifest", artifact_id="scene-candidate:caffeine:abc123")
    write_evidence(tmp_path, "evidence/eval.json", artifact_type="evaluation_result", artifact_id="evaluation-result:abc123")
    media = write_production_media(tmp_path)
    record_production(
        package, tmp_path, "ep-001",
        scene_candidate_manifest_paths=["evidence/scene.json"], evaluation_result_paths=["evidence/eval.json"],
        script_ref=media["script_ref"], voiceover_ref=media["voiceover_ref"], voice="lessac-medium",
        render_ref=media["render_ref"],
    )
    path = episode_path(package, "ep-001")
    document = json.loads(path.read_text(encoding="utf-8"))
    assert len(document["production"]["scene_candidate_manifest_refs"]) == 1
    assert len(document["production"]["evaluation_result_refs"]) == 1
    assert document["plan"]["opportunity_ref"] == "opportunity-proposal:science:abc123"

    record_review(
        package, tmp_path, "ep-001", decision="GO", decided_by="Seb",
        rationale="Clear mechanism, good pacing.", decision_ref="channels/episode-channel/channel.yaml",
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["review"]["decision"] == "GO"
    assert "freeze" not in document


def test_multiple_episodes_never_touch_channel_version(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    original_channel_yaml = (package / "channel.yaml").read_bytes()

    for episode_id in ("ep-001", "ep-002", "ep-003"):
        plan_episode(package, tmp_path, episode_id=episode_id, topic="t", target_duration_seconds=25.0)
        prefix = f"evidence/{episode_id}"
        write_evidence(tmp_path, f"{prefix}-scene.json", artifact_type="scene_candidate_manifest", artifact_id=f"scene-candidate:{episode_id}:abc123")
        write_evidence(tmp_path, f"{prefix}-eval.json", artifact_type="evaluation_result", artifact_id=f"evaluation-result:{episode_id}:abc123")
        media = write_production_media(tmp_path, prefix=prefix)
        record_production(
            package, tmp_path, episode_id,
            scene_candidate_manifest_paths=[f"{prefix}-scene.json"],
            evaluation_result_paths=[f"{prefix}-eval.json"],
            script_ref=media["script_ref"], voiceover_ref=media["voiceover_ref"], voice="lessac-medium",
            render_ref=media["render_ref"],
        )
        record_review(
            package, tmp_path, episode_id, decision="GO", decided_by="Seb",
            rationale="Good.", decision_ref="channels/episode-channel/channel.yaml",
        )

    assert (package / "channel.yaml").read_bytes() == original_channel_yaml
    identity = yaml.safe_load((package / "channel.yaml").read_text(encoding="utf-8"))
    assert identity["version"] == "0.2.0"


def test_opportunity_ref_is_optional(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    path = plan_episode(package, tmp_path, episode_id="ep-001", topic="t", target_duration_seconds=25.0)
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["plan"]["opportunity_ref"] is None


def test_episode_voice_is_required_and_matches_frozen_pilot(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    plan_episode(package, tmp_path, episode_id="ep-001", topic="t", target_duration_seconds=25.0)
    media = write_production_media(tmp_path)
    with pytest.raises(EpisodeValidationError, match="requires --voice"):
        record_production(
            package, tmp_path, "ep-001",
            script_ref=media["script_ref"], voiceover_ref=media["voiceover_ref"],
            render_ref=media["render_ref"],
        )
    # No frozen pilot pinned yet: the episode's own voice is accepted.
    record_production(
        package, tmp_path, "ep-001",
        script_ref=media["script_ref"], voiceover_ref=media["voiceover_ref"],
        voice="lessac-medium", render_ref=media["render_ref"],
    )
    with pytest.raises(EpisodeValidationError, match="already uses voice"):
        record_production(
            package, tmp_path, "ep-001",
            voiceover_ref=media["voiceover_ref"], voice="other-voice",
        )
    # Once a frozen pilot pins the channel voice, episodes must reuse it.
    (package / "current-release.json").write_text(json.dumps({"pilot_id": "pilot-1"}), encoding="utf-8")
    pilot_dir = package / "pilots" / "pilot-1"
    pilot_dir.mkdir(parents=True, exist_ok=True)
    (pilot_dir / "pilot.json").write_text(json.dumps({"production": {"voice_name": "other-voice"}}), encoding="utf-8")
    plan_episode(package, tmp_path, episode_id="ep-002", topic="t", target_duration_seconds=25.0)
    with pytest.raises(EpisodeValidationError, match="frozen pilot uses voice"):
        record_production(
            package, tmp_path, "ep-002",
            script_ref=media["script_ref"], voiceover_ref=media["voiceover_ref"],
            voice="lessac-medium", render_ref=media["render_ref"],
        )


def test_record_review_rejects_empty_decision_ref(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    plan_episode(package, tmp_path, episode_id="ep-001", topic="t", target_duration_seconds=25.0)
    with pytest.raises(EpisodeValidationError, match="non-empty"):
        record_review(package, tmp_path, "ep-001", decision="GO", decided_by="Seb", rationale="r", decision_ref="")


def test_abandon_decision_is_legal_and_final(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    plan_episode(package, tmp_path, episode_id="ep-001", topic="t", target_duration_seconds=25.0)
    path = record_review(
        package, tmp_path, "ep-001", decision="ABANDON", decided_by="Seb",
        rationale="Wrong angle for this niche.", decision_ref="channels/episode-channel/channel.yaml",
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["review"]["decision"] == "ABANDON"


def test_validate_episode_detects_tampered_evidence(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    plan_episode(package, tmp_path, episode_id="ep-001", topic="t", target_duration_seconds=25.0)
    evidence_path = write_evidence(tmp_path, "evidence/scene.json", artifact_type="scene_candidate_manifest", artifact_id="scene-candidate:x:abc123")
    record_production(package, tmp_path, "ep-001", scene_candidate_manifest_paths=["evidence/scene.json"])

    evidence_path.write_text(json.dumps({"artifact_type": "scene_candidate_manifest", "artifact_id": "scene-candidate:x:abc123", "note": "TAMPERED"}), encoding="utf-8")
    document = json.loads(episode_path(package, "ep-001").read_text(encoding="utf-8"))
    with pytest.raises(EpisodeValidationError, match="sha256 mismatch"):
        validate_episode(document, repository_root=tmp_path)
