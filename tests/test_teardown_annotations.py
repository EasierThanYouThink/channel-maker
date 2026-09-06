"""What-works teardown annotations: write path, validation, and wiki publishing."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from engine.memory import initialize_channel_wiki
from engine.niche_intelligence import (
    NicheValidationError,
    add_content_annotation,
    add_observation,
    add_script_annotation,
    add_visual_market_annotation,
    import_evidence,
    init_study,
    validate_study,
)
from engine.niche_intelligence.repository import NicheIntelligenceRepository

ROOT = Path(__file__).resolve().parents[1]
AT = "2026-06-30T12:00:00+00:00"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def build_package(root: Path, channel_id: str = "teardown-channel") -> Path:
    contracts = root / "engine" / "memory" / "contracts"
    contracts.mkdir(parents=True)
    shutil.copyfile(ROOT / "engine/memory/contracts/wiki-page.schema.json", contracts / "wiki-page.schema.json")
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
    write_json(package / "CHANNEL_STATE.json", state)
    initialize_channel_wiki(package, root)
    return package


def build_study_with_video(root: Path, package: Path) -> tuple[Path, str]:
    validated = init_study(
        package, root, study_id="teardown-study", niche="science", sub_niches=[],
        archetype="ILLUSTRATED_EXPLAINER", fmt="SHORTS", language="en", geography=None,
        channel_roles=["GROWTH_CANDIDATE", "BASELINE_COMPARATOR"], video_roles=["BREAKOUT", "CHANNEL_BASELINE"],
        window_from="2026-01-01T00:00:00+00:00", window_to=AT,
    )
    response_path = root / "response.json"
    write_json(response_path, {
        "worker": "claude.hermes_agent", "model": "ornith-1.5:9b", "model_version": "abc123",
        "prompt_version": "v1", "collected_at": AT,
        "channels": [{
            "source_id": "uc-target", "url": "https://www.youtube.com/channel/uc-target",
            "channel_name": "Target", "sample_role": "BASELINE_COMPARATOR", "sample_rationale": "competitor",
            "public_fields": {"subscriber_count": 5000, "public_video_count": 20, "created_at": None,
                              "observed_uploads_per_30d": 4.0, "shorts_fraction": 1.0},
        }],
        "videos": [{
            "channel_source_id": "uc-target", "source_id": "vid-breakout",
            "url": "https://www.youtube.com/shorts/vid-breakout", "title": "A mechanism explainer",
            "format": "SHORTS", "sample_role": "BREAKOUT", "sample_rationale": "10x median",
            "public_fields": {"published_at": "2026-06-01T00:00:00+00:00", "duration_seconds": 40.0,
                              "views": 900000, "likes": None, "comment_count": None, "description": None,
                              "age_at_observation_days": 29.0},
        }],
    })
    import_evidence(validated.root, response_path, reviewed_by="Seb", repository_root=root)
    result = validate_study(validated.root, repository_root=root, expected_channel_id=package.name)
    video_id = next(key for key, item in result.artifacts.items() if item["artifact_type"] == "video_evidence")
    return validated.root, video_id


def content_payload() -> dict:
    return {
        "primary_topic": "caffeine mechanism", "subtopics": ["adenosine"], "entities": ["caffeine"],
        "trend_dependence": "EVERGREEN", "hook_family": "QUESTION",
        "hook_text": "Why does coffee wake you up?", "viewer_promise": "The 30-second mechanism",
        "structure": "QUESTION_EXPLANATION_REVEAL",
        "characteristics": {
            "information_density": "HIGH", "technical_depth": "MEDIUM", "numeric_specificity": "MEDIUM",
            "emotional_framing": None, "novelty": "MEDIUM",
            "recognizable_entities": True, "examples_or_metaphors": True,
        },
        "ending": "IMPLICATION",
    }


def script_payload() -> tuple[dict, dict, dict]:
    transcript = {
        "availability": "AVAILABLE", "timing": "TIMED",
        "source_ref": "https://www.youtube.com/shorts/vid-breakout",
        "method": "PUBLIC_CAPTION", "language": "en",
    }
    statistics = {
        "word_count": 100, "words_per_second": 2.5,
        "opening_excerpt": "Why does coffee wake you up?",
        "sentence_length_mean": 9.0, "question_count": 2, "numeric_reference_count": 1,
    }
    annotations = {
        "hook": "Opens with a direct question.",
        "narrative_structure": "Question, mechanism, implication.",
        "information_density_hypothesis": "High density sustains retention.",
        "ending_behavior": "Ends on implication, no CTA.",
    }
    return transcript, statistics, annotations


def visual_payload() -> dict:
    return {
        "production_approaches": ["FULL_ANIMATION", "SUBTITLES_TEXT_FIRST"],
        "scene_change_frequency_proxy": 0.8, "text_density_proxy": "MEDIUM",
        "visual_metaphor_usage": "FREQUENT", "continuity": "CONTINUOUS_SCENES",
    }


def test_teardown_write_path_and_observation_chain(tmp_path: Path) -> None:
    package = build_package(tmp_path)
    study_root, video_id = build_study_with_video(tmp_path, package)
    content = add_content_annotation(
        study_root, key="vid-breakout", video_evidence_id=video_id,
        annotation=content_payload(), confidence=0.6, repository_root=tmp_path,
    )
    transcript, statistics, annotations = script_payload()
    script = add_script_annotation(
        study_root, key="vid-breakout-script", video_evidence_id=video_id,
        transcript=transcript, statistics=statistics, annotations=annotations,
        confidence=0.6, repository_root=tmp_path,
    )
    visual = add_visual_market_annotation(
        study_root, key="vid-breakout-visual", video_evidence_id=video_id,
        annotation=visual_payload(), confidence=0.5, repository_root=tmp_path,
    )
    assert content.parent.name == "annotations"
    result = validate_study(study_root, repository_root=tmp_path, expected_channel_id=package.name)
    visual_doc = result.artifacts["niche:visual-annotation:vid-breakout-visual"]
    assert visual_doc["design_authority"] == "PROHIBITED"
    assert visual_doc["renderer_eligible"] is False
    # Observations may cite teardowns with ANNOTATION basis.
    content_id = "niche:content-annotation:vid-breakout"
    script_id = "niche:script-annotation:vid-breakout-script"
    add_observation(
        study_root, key="hook-pattern", statement="Question hooks open every breakout.",
        observation_type="SCRIPT_PATTERN", scope="competitor", basis="ANNOTATION",
        evidence_refs=[content_id, script_id], confidence=0.6,
        limitations=["Single video."], repository_root=tmp_path,
    )
    assert visual.is_file() and script.is_file()


def test_teardown_rejects_unknown_video(tmp_path: Path) -> None:
    package = build_package(tmp_path)
    study_root, _ = build_study_with_video(tmp_path, package)
    with pytest.raises(NicheValidationError, match="video_evidence_id is missing"):
        add_content_annotation(
            study_root, key="ghost", video_evidence_id="niche:video:ghost",
            annotation=content_payload(), confidence=0.5, repository_root=tmp_path,
        )


def test_teardowns_publish_to_wiki(tmp_path: Path) -> None:
    package = build_package(tmp_path)
    study_root, video_id = build_study_with_video(tmp_path, package)
    add_content_annotation(
        study_root, key="vid-breakout", video_evidence_id=video_id,
        annotation=content_payload(), confidence=0.6, repository_root=tmp_path,
    )
    repository = NicheIntelligenceRepository(tmp_path)
    created = repository.publish_semantic_summaries(package, study_root)
    assert any("market/teardowns/" in path.relative_to(tmp_path).as_posix() for path in created)
