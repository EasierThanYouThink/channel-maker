"""Regression tests for P4 hardening: overwrite guards, --force escapes, CLI --yes gates."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from engine.design import (
    DesignValidationError,
    add_reference as add_design_reference,
    freeze_domain as freeze_design_domain,
    init_seed,
)
from engine.design.exemplars import ChannelExemplarStore
from engine.foundation import FoundationValidationError, write_foundation
from engine.identity import (
    ChannelIdentityStore,
    IdentityValidationError,
)
from engine.identity import (
    add_reference as add_identity_reference,
)
from engine.identity import (
    freeze_domain as freeze_identity_domain,
)
from engine.identity import (
    init_identity,
)
from engine.pilot import (
    PilotValidationError,
    freeze_pilot,
    plan_pilot,
    record_production,
    record_review,
)
from engine.script import ScriptExampleStore, ScriptValidationError, freeze_script_dna, write_script_dna


AT = "2026-09-05T12:00:00+00:00"
ROOT = Path(__file__).resolve().parents[1]


def write_package(root: Path, channel_id: str = "harden-channel") -> Path:
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


def foundation_kwargs() -> dict:
    return {
        "audience_description": "Curious adults.", "audience_demographics": None,
        "promise": "One mechanism, fast.", "niche_primary": "science", "sub_niches": [],
        "personality": ["curious"], "education_entertainment_balance": "MOSTLY_EDUCATIONAL",
        "differentiation": "Shows the mechanism.", "emotional_goal": "Aha moment.",
        "content_boundaries": ["No medical advice."], "primary_format": "SHORTS",
        "deliberately_avoids": ["Clickbait."],
    }


def script_kwargs() -> dict:
    return {
        "hook_philosophy": "Open with the mechanism.", "narrator_personality": ["curious"],
        "sentence_length_qualitative": "Short.", "sentence_length_target_words": 9,
        "words_per_second_target": 2.8, "words_per_second_range": [2.4, 3.2],
        "technical_depth": "Medium.", "humor_level": "Light.", "information_density": "High.",
        "question_usage": "One mid-video.", "number_usage": "One number.",
        "story_structure": "Problem -> mechanism.", "ending_behavior": "Implication.",
        "cta_philosophy": "Soft.", "preferred_cliches": [], "forbidden_cliches": ["Did you know"],
        "fact_verification_requirements": "Two sources.", "unresolved_variables": [],
    }


def make_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic-original-image-fixture")
    return path


def write_evidence(root: Path, relative: str, *, artifact_type: str, artifact_id: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"artifact_type": artifact_type, "artifact_id": artifact_id}), encoding="utf-8")
    return path


def test_foundation_rewrite_refuses_without_force(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    write_foundation(package, tmp_path, **foundation_kwargs())
    with pytest.raises(FoundationValidationError, match="already drafted"):
        write_foundation(package, tmp_path, **foundation_kwargs())
    write_foundation(package, tmp_path, **foundation_kwargs(), force=True)


def test_script_dna_rewrite_refuses_without_force(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    write_script_dna(package, tmp_path, **script_kwargs())
    with pytest.raises(ScriptValidationError, match="already drafted"):
        write_script_dna(package, tmp_path, **script_kwargs())
    write_script_dna(package, tmp_path, **script_kwargs(), force=True)


def test_script_dna_refreeze_refuses_without_force(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    ref = "channels/harden-channel/channel.yaml"
    write_script_dna(package, tmp_path, **script_kwargs())
    store = ScriptExampleStore(tmp_path, "harden-channel")
    record = store.add(
        "A proven line.", tags=[], provenance_kind="human_authored",
        created_by="Seb", source_ref="manual",
    )
    store.review(
        record["example_id"], decision="approved", reviewer="Seb",
        reason="Good.", created_at=AT, human_confirmed=True,
    )
    freeze_script_dna(package, tmp_path, human_confirmed=True, decision_ref=ref)
    with pytest.raises(ScriptValidationError, match="already frozen"):
        freeze_script_dna(package, tmp_path, human_confirmed=True, decision_ref=ref)
    freeze_script_dna(package, tmp_path, human_confirmed=True, decision_ref=ref, force=True)


def test_design_domain_refreeze_refuses_without_force(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    ref = "channels/harden-channel/channel.yaml"
    init_seed("motion", package, tmp_path)
    store = ChannelExemplarStore(tmp_path, "harden-channel")
    image = make_png(tmp_path / "src" / "ref.png")
    record = store.add(
        image, title="Reference", domain="motion_identity", tags=[],
        provenance_kind="human_supplied_original", created_by="Seb", source_ref="manual",
    )
    store.review(
        record["exemplar_id"], decision="approved", reviewer="Seb",
        reason="Good.", created_at=AT, human_confirmed=True,
    )
    add_design_reference("motion", package, tmp_path, domain="motion_identity", exemplar_id=record["exemplar_id"])
    freeze_design_domain("motion", package, tmp_path, domain="motion_identity", human_confirmed=True, decision_ref=ref)
    with pytest.raises(DesignValidationError, match="already frozen"):
        freeze_design_domain("motion", package, tmp_path, domain="motion_identity", human_confirmed=True, decision_ref=ref)
    freeze_design_domain("motion", package, tmp_path, domain="motion_identity", human_confirmed=True, decision_ref=ref, force=True)


def test_identity_domain_refreeze_refuses_without_force(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    ref = "channels/harden-channel/channel.yaml"
    init_identity(package, tmp_path)
    store = ChannelIdentityStore(tmp_path, "harden-channel")
    image = make_png(tmp_path / "src" / "mark.png")
    logo = store.add(
        domain="logo", title="Mark", image=image, provenance_kind="human_supplied_original",
        created_by="Seb", source_ref="manual",
    )
    store.review(
        logo["candidate_id"], decision="approved", reviewer="Seb",
        reason="Good.", created_at=AT, human_confirmed=True,
    )
    add_identity_reference(package, tmp_path, domain="logo", candidate_id=logo["candidate_id"])
    freeze_identity_domain(package, tmp_path, domain="logo", human_confirmed=True, decision_ref=ref)
    with pytest.raises(IdentityValidationError, match="already frozen"):
        freeze_identity_domain(package, tmp_path, domain="logo", human_confirmed=True, decision_ref=ref)
    freeze_identity_domain(package, tmp_path, domain="logo", human_confirmed=True, decision_ref=ref, force=True)


def test_pilot_refreeze_refuses_without_force(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    ref = "channels/harden-channel/channel.yaml"
    plan_pilot(package, tmp_path, pilot_id="pilot-1", topic="How caffeine works",
               target_duration_seconds=25.0, integration_goals=["Prove Script DNA"])
    write_evidence(tmp_path, "evidence/scene.json", artifact_type="scene_candidate_manifest", artifact_id="scene-candidate:x:abc123")
    write_evidence(tmp_path, "evidence/eval.json", artifact_type="evaluation_result", artifact_id="evaluation-result:abc123")
    (tmp_path / "evidence" / "script.md").write_text("# Script\n", encoding="utf-8")
    from engine.production.probing import encode_minimal_mp4, encode_minimal_wav

    (tmp_path / "evidence" / "voiceover.wav").write_bytes(encode_minimal_wav())
    (tmp_path / "evidence" / "render.mp4").write_bytes(encode_minimal_mp4())
    record_production(
        package, tmp_path, "pilot-1",
        scene_candidate_manifest_paths=["evidence/scene.json"], evaluation_result_paths=["evidence/eval.json"],
        script_ref="evidence/script.md", voiceover_ref="evidence/voiceover.wav",
        render_ref="evidence/render.mp4",
    )
    record_review(package, tmp_path, "pilot-1", decision="GO", decided_by="Seb", rationale="Good.", decision_ref=ref)
    freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.2.0", frozen_by="Seb")
    # Same version + identical release retries idempotently ...
    freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.2.0", frozen_by="Seb")
    identity = yaml.safe_load((package / "channel.yaml").read_text(encoding="utf-8"))
    assert identity["version"] == "0.2.0"
    # ... while a version bump on identical content is refused without force.
    with pytest.raises(PilotValidationError, match="already frozen"):
        freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.3.0", frozen_by="Seb")
    freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.3.0", frozen_by="Seb", force=True)
    identity = yaml.safe_load((package / "channel.yaml").read_text(encoding="utf-8"))
    assert identity["version"] == "0.3.0"


def _pilot_cli(tmp_path: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "pilot.py"), "--root", str(tmp_path), *argv],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, cwd=ROOT,
    )


def test_pilot_record_review_cli_requires_yes_when_non_interactive(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    ref = "channels/harden-channel/channel.yaml"
    plan_pilot(package, tmp_path, pilot_id="pilot-1", topic="How caffeine works",
               target_duration_seconds=25.0, integration_goals=["Prove Script DNA"])
    write_evidence(tmp_path, "evidence/scene.json", artifact_type="scene_candidate_manifest", artifact_id="scene-candidate:x:abc123")
    write_evidence(tmp_path, "evidence/eval.json", artifact_type="evaluation_result", artifact_id="evaluation-result:abc123")
    (tmp_path / "evidence" / "script.md").write_text("# Script\n", encoding="utf-8")
    from engine.production.probing import encode_minimal_mp4, encode_minimal_wav

    (tmp_path / "evidence" / "voiceover.wav").write_bytes(encode_minimal_wav())
    (tmp_path / "evidence" / "render.mp4").write_bytes(encode_minimal_mp4())
    record_production(
        package, tmp_path, "pilot-1",
        scene_candidate_manifest_paths=["evidence/scene.json"], evaluation_result_paths=["evidence/eval.json"],
        script_ref="evidence/script.md", voiceover_ref="evidence/voiceover.wav",
        render_ref="evidence/render.mp4",
    )
    base = ["record-review", str(package), "pilot-1", "--decision", "GO",
            "--decided-by", "Seb", "--rationale", "Good.", "--decision-ref", ref]
    denied = _pilot_cli(tmp_path, *base)
    assert denied.returncode == 2
    assert "requires --yes" in denied.stdout
    allowed = _pilot_cli(tmp_path, *base, "--yes")
    assert allowed.returncode == 0, allowed.stdout
