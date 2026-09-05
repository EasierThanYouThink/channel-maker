from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.foundation import FoundationValidationError, attach_foundation_decision, write_foundation


AT = "2026-09-05T12:00:00+00:00"


def write_package(root: Path, channel_id: str = "found-channel") -> Path:
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


def write_kwargs() -> dict:
    return {
        "audience_description": "Curious adults who like short science explainers.",
        "audience_demographics": None,
        "promise": "One real mechanism explained in under 30 seconds.",
        "niche_primary": "science", "sub_niches": ["biology"],
        "personality": ["curious", "precise"],
        "education_entertainment_balance": "MOSTLY_EDUCATIONAL",
        "differentiation": "Always shows the actual mechanism, never just a fact.",
        "emotional_goal": "A satisfying 'oh, that's why' moment.",
        "content_boundaries": ["No medical advice."],
        "primary_format": "SHORTS",
        "deliberately_avoids": ["Clickbait titles."],
    }


def test_write_foundation_produces_schema_valid_draft(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    path = write_foundation(package, tmp_path, **write_kwargs())
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["channel_id"] == "found-channel"
    assert document["decision_refs"] == []
    assert path == package / "strategy" / "foundation.yaml"


def test_write_foundation_rejects_format_not_in_channel_platform(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    kwargs = write_kwargs()
    kwargs["primary_format"] = "LONG_FORM"
    with pytest.raises(FoundationValidationError, match="platform.formats"):
        write_foundation(package, tmp_path, **kwargs)


def test_attach_foundation_decision_requires_real_resolvable_ref(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    write_foundation(package, tmp_path, **write_kwargs())
    with pytest.raises(FoundationValidationError, match="non-empty"):
        attach_foundation_decision(package, tmp_path, decision_ref="")
    with pytest.raises(FoundationValidationError, match="does not resolve"):
        attach_foundation_decision(package, tmp_path, decision_ref="channels/found-channel/does-not-exist.md")

    path = attach_foundation_decision(package, tmp_path, decision_ref=f"channels/found-channel/channel.yaml")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["decision_refs"] == ["channels/found-channel/channel.yaml"]

    # Idempotent: attaching the same ref again does not duplicate it.
    attach_foundation_decision(package, tmp_path, decision_ref="channels/found-channel/channel.yaml")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["decision_refs"] == ["channels/found-channel/channel.yaml"]
