from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.script import ScriptExampleStore, ScriptValidationError, freeze_script_dna, write_script_dna


AT = "2026-09-05T12:00:00+00:00"


def write_package(root: Path, channel_id: str = "script-channel") -> Path:
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


def dna_kwargs() -> dict:
    return {
        "hook_philosophy": "Open with the surprising mechanism, not the topic name.",
        "narrator_personality": ["curious", "direct"],
        "sentence_length_qualitative": "Short, punchy sentences.",
        "sentence_length_target_words": 9,
        "words_per_second_target": 2.8,
        "words_per_second_range": [2.4, 3.2],
        "technical_depth": "Medium, one real term per video.",
        "humor_level": "Light, never at the topic's expense.",
        "information_density": "High.",
        "question_usage": "One rhetorical question mid-video.",
        "number_usage": "One striking specific number per video.",
        "story_structure": "Problem -> mechanism -> consequence.",
        "ending_behavior": "Implication, not a hard CTA.",
        "cta_philosophy": "Soft, at most once every few videos.",
        "preferred_cliches": [],
        "forbidden_cliches": ["Did you know"],
        "fact_verification_requirements": "Two independent sources for any numeric claim.",
        "unresolved_variables": ["Whether to use first or second person."],
    }


def test_write_script_dna_produces_schema_valid_draft(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    path = write_script_dna(package, tmp_path, **dna_kwargs())
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["status"] == "ACTIVE_DISCOVERY"
    assert document["decision_refs"] == []


def _approve_example(root: Path, channel_id: str = "script-channel") -> dict:
    store = ScriptExampleStore(root, channel_id)
    record = store.add(
        "Caffeine blocks the sleep signal. That is the whole trick.",
        tags=["cold-open"], provenance_kind="human_authored",
        created_by="Seb", source_ref="manual",
    )
    store.review(
        record["example_id"], decision="approved", reviewer="Seb",
        reason="Sounds like us.", created_at=AT, human_confirmed=True,
    )
    return record


def test_freeze_script_dna_requires_confirmation_and_real_decision_ref(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    write_script_dna(package, tmp_path, **dna_kwargs())
    with pytest.raises(ScriptValidationError, match="human confirmation"):
        freeze_script_dna(package, tmp_path, human_confirmed=False, decision_ref="channels/script-channel/channel.yaml")
    with pytest.raises(ScriptValidationError, match="does not resolve"):
        freeze_script_dna(package, tmp_path, human_confirmed=True, decision_ref="channels/script-channel/nope.md")

    _approve_example(tmp_path)
    path = freeze_script_dna(package, tmp_path, human_confirmed=True, decision_ref="channels/script-channel/channel.yaml")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["status"] == "FROZEN"
    assert document["decision_refs"] == ["channels/script-channel/channel.yaml"]


def test_freeze_script_dna_requires_an_approved_example(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    write_script_dna(package, tmp_path, **dna_kwargs())
    store = ScriptExampleStore(tmp_path, "script-channel")
    store.add(
        "An unreviewed line.", tags=[], provenance_kind="human_authored",
        created_by="Seb", source_ref="manual",
    )
    with pytest.raises(ScriptValidationError, match="at least one approved example"):
        freeze_script_dna(package, tmp_path, human_confirmed=True, decision_ref="channels/script-channel/channel.yaml")
    _approve_example(tmp_path)
    path = freeze_script_dna(package, tmp_path, human_confirmed=True, decision_ref="channels/script-channel/channel.yaml")
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["status"] == "FROZEN"


def test_freeze_script_dna_audition_binds_approved_audio(tmp_path: Path) -> None:
    import wave as _wave

    package = write_package(tmp_path)
    write_script_dna(package, tmp_path, **dna_kwargs())
    record = _approve_example(tmp_path)
    audio = tmp_path / "evidence" / "audition.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    with _wave.open(str(audio), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(22050)
        handle.writeframes(b"\x00\x00" * 22050)
    import hashlib as _hashlib
    import json as _json

    timing = tmp_path / "evidence" / "audition-timing.json"
    timing.write_text(_json.dumps({
        "schema_version": "1.0.0", "artifact_type": "voiceover_timing",
        "voice": {"name": "lessac-medium", "model": "en_US-lessac-medium.onnx", "sample_rate_hz": 22050},
        "text": "Caffeine blocks the sleep signal.",
        "sentences": [{"index": 0, "text": "Caffeine blocks the sleep signal.", "start_s": 0.0, "end_s": 1.0, "method": "measured_audio"}],
        "words": [{"text": "Caffeine", "start_s": 0.0, "end_s": 1.0, "method": "uniform_estimate"}],
        "total_duration_s": 1.0,
        "audio": {"path": "evidence/audition.wav", "sha256": _hashlib.sha256(b"\x00\x00" * 22050).hexdigest(), "duration_s": 1.0, "sample_rate_hz": 22050},
        "created_by": {"tool": "test", "version": "1.0.0"},
    }), encoding="utf-8")
    with pytest.raises(ScriptValidationError, match="both an example id and a timing ref"):
        freeze_script_dna(
            package, tmp_path, human_confirmed=True,
            decision_ref="channels/script-channel/channel.yaml",
            audition_example_id=record["example_id"],
        )
    path = freeze_script_dna(
        package, tmp_path, human_confirmed=True,
        decision_ref="channels/script-channel/channel.yaml",
        audition_example_id=record["example_id"],
        audition_timing_ref="evidence/audition-timing.json",
    )
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["audition"] == {
        "example_id": record["example_id"], "timing_ref": "evidence/audition-timing.json",
    }


def test_script_example_store_review_requires_human_confirmation(tmp_path: Path) -> None:
    store = ScriptExampleStore(tmp_path, "script-channel")
    record = store.add(
        "A single mosquito bite can carry a parasite that has killed more humans than any war.",
        tags=["cold-open"], provenance_kind="model_drafted", created_by="claude", source_ref="draft-1",
        model="claude-sonnet-5", model_version="1.0",
    )
    assert record["classification"] == "experimental"
    assert record["review_authority"] == "unreviewed"

    with pytest.raises(ScriptValidationError, match="human confirmation"):
        store.review(record["example_id"], decision="approved", reviewer="Seb", reason="Strong hook.", created_at=AT, human_confirmed=False)

    review = store.review(
        record["example_id"], decision="approved", reviewer="Seb", reason="Strong hook.",
        created_at=AT, human_confirmed=True,
    )
    assert review["decision"] == "approved"
    updated = store.list(classification="approved")
    assert len(updated) == 1
    assert updated[0]["example_id"] == record["example_id"]


def test_script_example_model_drafted_requires_model_fields(tmp_path: Path) -> None:
    store = ScriptExampleStore(tmp_path, "script-channel")
    with pytest.raises(ScriptValidationError, match="model_drafted"):
        store.add("Some draft text.", tags=[], provenance_kind="model_drafted", created_by="claude", source_ref="draft-2")
