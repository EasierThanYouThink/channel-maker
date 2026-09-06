"""Phase 2: immutable releases, append-only reviews, revision binding.

- A production change under GO restores "needs review" and archives the
  superseded decision instead of silently keeping it.
- Re-recording a review appends history instead of erasing it.
- Freeze binds the GO to the exact production revision.
- Freeze retry with the same version completes the same release (crash-safe)
  instead of demanding another version.
- Episode GO pins the channel release it was produced against.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.episode import (
    episode_path,
    plan_episode,
)
from engine.episode import (
    record_production as record_episode_production,
)
from engine.episode import (
    record_review as record_episode_review,
)
from engine.pilot import (
    PilotValidationError,
    freeze_pilot,
    pilot_path,
    plan_pilot,
    record_production,
    record_review,
)

AT = "2026-09-05T12:00:00+00:00"
REF = "channels/release-channel/channel.yaml"


def write_package(root: Path) -> Path:
    package = root / "channels" / "release-channel"
    package.mkdir(parents=True)
    identity = {
        "schema_version": "0.1.0", "id": "release-channel", "name": "Release",
        "version": "0.1.0", "status": "DRAFT", "language": "en",
        "niche": {"primary": "science"},
        "platform": {"primary": "YOUTUBE", "formats": ["SHORTS"]},
        "production": {"archetype": "ILLUSTRATED_EXPLAINER", "renderer": "remotion"},
        "creation": {"mode": "ORIGINAL"},
        "canonical_sources": {"channel_state": "channels/release-channel/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.2.0", "channel_id": "release-channel", "revision": 0,
        "state": "CHANNEL_INIT", "status": "ACTIVE", "completed": [],
        "active_experiment": None, "waiting_for": None, "blocker": None,
        "next_action": "test", "resume_state": None,
        "source_refs": ["channels/release-channel/channel.yaml"], "known_gaps": [],
        "legacy_mapping": False, "events": [], "updated_at": AT,
    }
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    return package


def write_evidence(root: Path, relative: str, *, artifact_type: str, artifact_id: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"artifact_type": artifact_type, "artifact_id": artifact_id}), encoding="utf-8")


def write_media(root: Path, tag: bytes = b"v1") -> None:
    from engine.production.probing import encode_minimal_mp4, encode_minimal_wav

    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "script.md").write_text("# Script\n", encoding="utf-8")
    # Structurally valid media whose bytes still differ per tag (drives revisions).
    (root / "evidence" / "voiceover.wav").write_bytes(
        encode_minimal_wav(duration_s=0.1 if tag == b"v1" else 0.2)
    )
    (root / "evidence" / "render.mp4").write_bytes(
        encode_minimal_mp4(major_brand=b"isom" if tag == b"v1" else b"iso2")
    )


def produce_pilot(package: Path, root: Path) -> None:
    plan_pilot(package, root, pilot_id="pilot-1", topic="t",
               target_duration_seconds=25.0, integration_goals=["g"])
    write_evidence(root, "evidence/scene.json", artifact_type="scene_candidate_manifest", artifact_id="scene-candidate:x:abc123")
    write_evidence(root, "evidence/eval.json", artifact_type="evaluation_result", artifact_id="evaluation-result:abc123")
    record_production(
        package, root, "pilot-1",
        scene_candidate_manifest_paths=["evidence/scene.json"],
        evaluation_result_paths=["evidence/eval.json"],
        script_ref="evidence/script.md", voiceover_ref="evidence/voiceover.wav",
        render_ref="evidence/render.mp4",
    )


def pilot_doc(package: Path) -> dict:
    return json.loads(pilot_path(package, "pilot-1").read_text(encoding="utf-8"))


def test_production_change_under_go_restores_needs_review(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    write_media(tmp_path, b"v1")
    produce_pilot(package, tmp_path)
    record_review(package, tmp_path, "pilot-1", decision="GO", decided_by="Seb",
                  rationale="Good.", decision_ref=REF)
    assert pilot_doc(package)["review"]["decision"] == "GO"
    first_rev = pilot_doc(package)["review"]["rev_id"]
    assert first_rev is not None

    # Change one production byte: the GO must not survive it.
    write_media(tmp_path, b"v2")
    record_production(package, tmp_path, "pilot-1", render_ref="evidence/render.mp4")
    document = pilot_doc(package)
    assert document["review"]["decision"] is None
    assert document["review"]["rev_id"] is None
    assert document["production"]["revision"] != first_rev
    archived = document["review"]["history"]
    assert len(archived) == 1
    assert archived[0]["decision"] == "GO"
    assert archived[0]["rev_id"] == first_rev
    assert "history" not in archived[0]

    with pytest.raises(PilotValidationError, match="only be frozen after a GO"):
        freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.2.0", frozen_by="Seb")


def test_rerecorded_review_appends_history(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    write_media(tmp_path, b"v1")
    produce_pilot(package, tmp_path)
    record_review(package, tmp_path, "pilot-1", decision="REVISE", decided_by="Seb",
                  rationale="Rework.", decision_ref=REF, revise_target="PILOT_PRODUCTION")
    record_review(package, tmp_path, "pilot-1", decision="GO", decided_by="Seb",
                  rationale="Fixed.", decision_ref=REF)
    document = pilot_doc(package)
    assert document["review"]["decision"] == "GO"
    assert len(document["review"]["history"]) == 1
    assert document["review"]["history"][0]["decision"] == "REVISE"


def test_freeze_writes_release_and_pointer(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    write_media(tmp_path, b"v1")
    produce_pilot(package, tmp_path)
    record_review(package, tmp_path, "pilot-1", decision="GO", decided_by="Seb",
                  rationale="Good.", decision_ref=REF)
    freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.2.0", frozen_by="Seb")
    release = json.loads((package / "releases" / "0.2.0.json").read_text(encoding="utf-8"))
    assert release["artifact_type"] == "release_manifest"
    assert release["version"] == "0.2.0"
    assert release["pilot_rev_id"] == pilot_doc(package)["review"]["rev_id"]
    assert release["dependencies"]["script_dna"]["path"] is None  # no DNA seeds in this fixture
    pointer = json.loads((package / "current-release.json").read_text(encoding="utf-8"))
    assert pointer["version"] == "0.2.0"
    assert pointer["pilot_rev_id"] == release["pilot_rev_id"]


def test_freeze_retry_completes_same_release_after_crash(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    write_media(tmp_path, b"v1")
    produce_pilot(package, tmp_path)
    record_review(package, tmp_path, "pilot-1", decision="GO", decided_by="Seb",
                  rationale="Good.", decision_ref=REF)
    freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.2.0", frozen_by="Seb")

    # Simulate a crash between the pilot write and the version bump: the
    # pilot reads frozen, but the version and pointer never landed.
    identity = yaml.safe_load((package / "channel.yaml").read_text(encoding="utf-8"))
    identity["version"] = "0.1.0"
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    (package / "current-release.json").unlink()

    freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.2.0", frozen_by="Seb")
    identity = yaml.safe_load((package / "channel.yaml").read_text(encoding="utf-8"))
    assert identity["version"] == "0.2.0"
    assert (package / "current-release.json").is_file()


def test_freeze_refuses_changed_production_at_same_version(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    write_media(tmp_path, b"v1")
    produce_pilot(package, tmp_path)
    record_review(package, tmp_path, "pilot-1", decision="GO", decided_by="Seb",
                  rationale="Good.", decision_ref=REF)
    freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.2.0", frozen_by="Seb")

    # New production + new GO is a different release: same-version retry must
    # refuse (the pilot was unfrozen by the content change), while a new
    # version freezes cleanly.
    write_media(tmp_path, b"v2")
    record_production(package, tmp_path, "pilot-1", render_ref="evidence/render.mp4")
    assert pilot_doc(package)["freeze"]["frozen"] is False
    record_review(package, tmp_path, "pilot-1", decision="GO", decided_by="Seb",
                  rationale="Better.", decision_ref=REF)
    with pytest.raises(PilotValidationError, match="already released with different content"):
        freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.2.0", frozen_by="Seb")
    freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.3.0", frozen_by="Seb")
    assert (package / "releases" / "0.3.0.json").is_file()


def test_episode_go_pins_current_release(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    write_media(tmp_path, b"v1")
    produce_pilot(package, tmp_path)
    record_review(package, tmp_path, "pilot-1", decision="GO", decided_by="Seb",
                  rationale="Good.", decision_ref=REF)
    freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.2.0", frozen_by="Seb")

    plan_episode(package, tmp_path, episode_id="ep-1", topic="t", target_duration_seconds=25.0)
    record_episode_production(
        package, tmp_path, "ep-1",
        scene_candidate_manifest_paths=["evidence/scene.json"],
        evaluation_result_paths=["evidence/eval.json"],
        script_ref="evidence/script.md", voiceover_ref="evidence/voiceover.wav",
        render_ref="evidence/render.mp4",
    )
    record_episode_review(package, tmp_path, "ep-1", decision="GO", decided_by="Seb",
                          rationale="Good.", decision_ref=REF)
    document = json.loads(episode_path(package, "ep-1").read_text(encoding="utf-8"))
    assert document["review"]["release_ref"] == "0.2.0"
    assert document["review"]["rev_id"] == document["production"]["revision"]


def test_episode_go_without_release_pins_null(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    write_media(tmp_path, b"v1")
    plan_episode(package, tmp_path, episode_id="ep-1", topic="t", target_duration_seconds=25.0)
    write_evidence(tmp_path, "evidence/scene.json", artifact_type="scene_candidate_manifest", artifact_id="scene-candidate:x:abc123")
    write_evidence(tmp_path, "evidence/eval.json", artifact_type="evaluation_result", artifact_id="evaluation-result:abc123")
    record_episode_production(
        package, tmp_path, "ep-1",
        scene_candidate_manifest_paths=["evidence/scene.json"],
        evaluation_result_paths=["evidence/eval.json"],
        script_ref="evidence/script.md", voiceover_ref="evidence/voiceover.wav",
        render_ref="evidence/render.mp4",
    )
    record_episode_review(package, tmp_path, "ep-1", decision="GO", decided_by="Seb",
                          rationale="Good.", decision_ref=REF)
    document = json.loads(episode_path(package, "ep-1").read_text(encoding="utf-8"))
    assert document["review"]["release_ref"] is None
