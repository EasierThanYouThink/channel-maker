from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from engine.memory import initialize_channel_wiki
from engine.niche_intelligence import (
    NicheValidationError,
    add_hypothesis,
    add_observation,
    add_opportunity,
    import_evidence,
    init_study,
    validate_study,
)
from engine.niche_intelligence.repository import NicheIntelligenceRepository
from engine.niche_intelligence.validation import PRIVATE_METRICS

ROOT = Path(__file__).resolve().parents[1]
AT = "2026-06-30T12:00:00+00:00"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def build_package(root: Path, channel_id: str = "acq-channel") -> Path:
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


def build_empty_study(root: Path, package: Path, channel_id: str = "acq-channel", study_id: str = "acq-study"):
    return init_study(
        package, root, study_id=study_id, niche="science", sub_niches=[], archetype="ILLUSTRATED_EXPLAINER",
        fmt="SHORTS", language="en", geography=None,
        channel_roles=["GROWTH_CANDIDATE", "BASELINE_COMPARATOR"], video_roles=["BREAKOUT", "CHANNEL_BASELINE"],
        window_from="2026-01-01T00:00:00+00:00", window_to=AT,
    )


def hermes_response(**overrides) -> dict:
    base = {
        "worker": "claude.hermes_agent", "model": "ornith-1.5:9b", "model_version": "abc123",
        "prompt_version": "v1", "collected_at": AT,
        "channels": [{
            "source_id": "uc-target", "url": "https://www.youtube.com/channel/uc-target",
            "channel_name": "Target", "sample_role": "GROWTH_CANDIDATE", "sample_rationale": "growth",
            "public_fields": {"subscriber_count": 5000, "public_video_count": 20, "created_at": None,
                              "observed_uploads_per_30d": 4.0, "shorts_fraction": 1.0},
        }, {
            "source_id": "uc-baseline", "url": "https://www.youtube.com/channel/uc-baseline",
            "channel_name": "Baseline", "sample_role": "BASELINE_COMPARATOR", "sample_rationale": "ordinary comparator",
            "public_fields": {"subscriber_count": 4000, "public_video_count": 30, "created_at": None,
                              "observed_uploads_per_30d": 3.0, "shorts_fraction": 0.8},
        }],
        "videos": [{
            "channel_source_id": "uc-target", "source_id": "vid-breakout",
            "url": "https://www.youtube.com/shorts/vid-breakout", "title": "A mechanism explainer",
            "format": "SHORTS", "sample_role": "BREAKOUT", "sample_rationale": "10x median",
            "public_fields": {"published_at": "2026-06-01T00:00:00+00:00", "duration_seconds": 40.0,
                              "views": 900000, "likes": None, "comment_count": None, "description": None,
                              "age_at_observation_days": 29.0},
        }, {
            "channel_source_id": "uc-baseline", "source_id": "vid-ordinary",
            "url": "https://www.youtube.com/shorts/vid-ordinary", "title": "An ordinary topic",
            "format": "SHORTS", "sample_role": "CHANNEL_BASELINE", "sample_rationale": "typical output",
            "public_fields": {"published_at": "2026-05-01T00:00:00+00:00", "duration_seconds": 35.0,
                              "views": 5000, "likes": None, "comment_count": None, "description": None,
                              "age_at_observation_days": 60.0},
        }],
    }
    base.update(overrides)
    return base


def test_import_evidence_requires_reviewed_by(tmp_path: Path) -> None:
    package = build_package(tmp_path)
    validated = build_empty_study(tmp_path, package)
    response_path = tmp_path / "response.json"
    write_json(response_path, hermes_response())
    with pytest.raises(NicheValidationError, match="explicit human reviewer"):
        import_evidence(validated.root, response_path, reviewed_by="", repository_root=tmp_path)
    created = import_evidence(validated.root, response_path, reviewed_by="Seb", repository_root=tmp_path)
    assert len(created) == 4
    log = (tmp_path / "channels" / "acq-channel" / "intelligence" / "review-log.jsonl").read_text(encoding="utf-8")
    assert "Seb" in log


def test_import_evidence_forces_model_assisted_collector_and_full_private_metric_set(tmp_path: Path) -> None:
    package = build_package(tmp_path)
    validated = build_empty_study(tmp_path, package)
    response_path = tmp_path / "response.json"
    write_json(response_path, hermes_response())
    import_evidence(validated.root, response_path, reviewed_by="Seb", repository_root=tmp_path)
    result = validate_study(validated.root, repository_root=tmp_path, expected_channel_id="acq-channel")
    video = next(item for item in result.artifacts.values() if item["artifact_type"] == "video_evidence")
    assert video["source"]["collector"]["kind"] == "MODEL_ASSISTED"
    assert video["source"]["collector"]["name"] == "claude.hermes_agent"
    assert set(video["unavailable_private_metrics"]) == PRIVATE_METRICS
    channel = next(item for item in result.artifacts.values() if item["artifact_type"] == "channel_evidence")
    assert channel["source"]["collector"]["kind"] == "MODEL_ASSISTED"


def test_import_evidence_computes_unknown_fields_from_nulls(tmp_path: Path) -> None:
    package = build_package(tmp_path)
    validated = build_empty_study(tmp_path, package)
    response_path = tmp_path / "response.json"
    write_json(response_path, hermes_response())
    import_evidence(validated.root, response_path, reviewed_by="Seb", repository_root=tmp_path)
    result = validate_study(validated.root, repository_root=tmp_path, expected_channel_id="acq-channel")
    channel = next(item for item in result.artifacts.values() if item["artifact_type"] == "channel_evidence")
    assert channel["unknown_fields"] == ["created_at"]
    video = next(item for item in result.artifacts.values() if item["artifact_type"] == "video_evidence")
    assert set(video["unknown_fields"]) == {"likes", "comment_count", "description"}


def test_import_evidence_updates_report_incrementally_without_duplicating(tmp_path: Path) -> None:
    package = build_package(tmp_path)
    validated = build_empty_study(tmp_path, package)
    response_path = tmp_path / "response.json"
    write_json(response_path, hermes_response())
    first = import_evidence(validated.root, response_path, reviewed_by="Seb", repository_root=tmp_path)
    assert len(first) == 4

    second_response = hermes_response(
        channels=[],
        videos=[{
            "channel_source_id": "uc-target", "source_id": "vid-baseline",
            "url": "https://www.youtube.com/shorts/vid-baseline", "title": "A normal topic",
            "format": "SHORTS", "sample_role": "CHANNEL_BASELINE", "sample_rationale": "typical",
            "public_fields": {"published_at": "2026-05-01T00:00:00+00:00", "duration_seconds": 35.0,
                              "views": 5000, "likes": None, "comment_count": None, "description": None,
                              "age_at_observation_days": 60.0},
        }],
    )
    second_path = tmp_path / "response2.json"
    write_json(second_path, second_response)
    second = import_evidence(validated.root, second_path, reviewed_by="Seb", repository_root=tmp_path)
    assert len(second) == 1

    # Re-importing the exact same first response again must be a no-op (no duplicates).
    replay = import_evidence(validated.root, response_path, reviewed_by="Seb", repository_root=tmp_path)
    assert replay == []

    result = validate_study(validated.root, repository_root=tmp_path, expected_channel_id="acq-channel")
    videos = [item for item in result.artifacts.values() if item["artifact_type"] == "video_evidence"]
    assert len(videos) == 3


def test_add_observation_hypothesis_opportunity_enforce_authority_ladder(tmp_path: Path) -> None:
    package = build_package(tmp_path)
    validated = build_empty_study(tmp_path, package)
    response_path = tmp_path / "response.json"
    write_json(response_path, hermes_response())
    import_evidence(validated.root, response_path, reviewed_by="Seb", repository_root=tmp_path)
    result = validate_study(validated.root, repository_root=tmp_path, expected_channel_id="acq-channel")
    video_id = next(k for k, v in result.artifacts.items() if v["artifact_type"] == "video_evidence")
    study_id = next(k for k, v in result.artifacts.items() if v["artifact_type"] == "niche_study")

    with pytest.raises(NicheValidationError):
        add_hypothesis(
            validated.root, key="bad-hyp", statement="s", predicted_effect="e", applicable_context="c",
            observation_refs=[video_id], competing_explanations=["x"], confidence=0.5, test_idea=None,
            repository_root=tmp_path,
        )

    obs_path = add_observation(
        validated.root, key="pattern", statement="Breakout used a mechanism-specific hook.",
        observation_type="PERFORMANCE_PATTERN", scope="Synthetic test", basis="PUBLIC_FACT",
        evidence_refs=[video_id], confidence=0.7, limitations=["Single-sample test."],
        repository_root=tmp_path,
    )
    assert obs_path.exists()

    with pytest.raises(NicheValidationError):
        add_opportunity(
            validated.root, key="bad-opp", observed_market="m", underrepresented="u", proposal="p",
            hypothesis_refs=[study_id], evidence_refs=[video_id], risks=["r"], confidence=0.4,
            repository_root=tmp_path,
        )

    result2 = validate_study(validated.root, repository_root=tmp_path, expected_channel_id="acq-channel")
    obs_id = next(k for k, v in result2.artifacts.items() if v["artifact_type"] == "niche_observation")
    hyp_path = add_hypothesis(
        validated.root, key="effect", statement="Mechanism hooks may drive higher relative views.",
        predicted_effect="Higher relative views.", applicable_context="Synthetic shorts",
        observation_refs=[obs_id], competing_explanations=["Timing effects."], confidence=0.5,
        test_idea="A/B test hooks.", repository_root=tmp_path,
    )
    assert hyp_path.exists()
    result3 = validate_study(validated.root, repository_root=tmp_path, expected_channel_id="acq-channel")
    hyp_id = next(k for k, v in result3.artifacts.items() if v["artifact_type"] == "niche_hypothesis")
    opp_path = add_opportunity(
        validated.root, key="gap", observed_market="Familiar formats dominate.",
        underrepresented="Mechanism-driven treatment.", proposal="Test an original format.",
        hypothesis_refs=[hyp_id], evidence_refs=[obs_id], risks=["Production cost."], confidence=0.4,
        repository_root=tmp_path,
    )
    assert opp_path.exists()
    final = validate_study(validated.root, repository_root=tmp_path, expected_channel_id="acq-channel")
    opportunity = next(v for v in final.artifacts.values() if v["artifact_type"] == "opportunity_proposal")
    assert opportunity["human_strategy_decision_required"] is True
    assert opportunity["status"] == "PROPOSED"


def test_full_study_via_new_tools_validates_and_publishes_summaries(tmp_path: Path) -> None:
    package = build_package(tmp_path)
    validated = build_empty_study(tmp_path, package)
    response_path = tmp_path / "response.json"
    write_json(response_path, hermes_response())
    import_evidence(validated.root, response_path, reviewed_by="Seb", repository_root=tmp_path)
    result = validate_study(validated.root, repository_root=tmp_path, expected_channel_id="acq-channel")
    video_id = next(k for k, v in result.artifacts.items() if v["artifact_type"] == "video_evidence")
    obs_path = add_observation(
        validated.root, key="pattern", statement="Breakout used a mechanism-specific hook.",
        observation_type="PERFORMANCE_PATTERN", scope="Synthetic test", basis="PUBLIC_FACT",
        evidence_refs=[video_id], confidence=0.7, limitations=["Single-sample test."],
        repository_root=tmp_path,
    )
    obs_id = json.loads(obs_path.read_text(encoding="utf-8"))["artifact_id"]
    hyp_path = add_hypothesis(
        validated.root, key="effect", statement="Mechanism hooks may drive higher relative views.",
        predicted_effect="Higher relative views.", applicable_context="Synthetic shorts",
        observation_refs=[obs_id], competing_explanations=["Timing effects."], confidence=0.5,
        test_idea="A/B test hooks.", repository_root=tmp_path,
    )
    hyp_id = json.loads(hyp_path.read_text(encoding="utf-8"))["artifact_id"]
    add_opportunity(
        validated.root, key="gap", observed_market="Familiar formats dominate.",
        underrepresented="Mechanism-driven treatment.", proposal="Test an original format.",
        hypothesis_refs=[hyp_id], evidence_refs=[obs_id], risks=["Production cost."], confidence=0.4,
        repository_root=tmp_path,
    )
    final = validate_study(validated.root, repository_root=tmp_path, expected_channel_id="acq-channel")
    assert len(final.artifacts) == 9  # study + report + 2 channels + 2 videos + observation + hypothesis + opportunity

    repository = NicheIntelligenceRepository(tmp_path)
    created = repository.publish_semantic_summaries(package, validated.root)
    assert len(created) == 3
    for path in created:
        assert path.is_file()


def test_study_coverage_reports_roles_gaps_and_baselines(tmp_path: Path) -> None:
    from engine.niche_intelligence import study_coverage

    package = build_package(tmp_path)
    validated = build_empty_study(tmp_path, package)
    response_path = tmp_path / "response.json"
    write_json(response_path, hermes_response())
    import_evidence(validated.root, response_path, reviewed_by="Seb", repository_root=tmp_path)
    result = validate_study(validated.root, repository_root=tmp_path, expected_channel_id="acq-channel")
    coverage = study_coverage(result)
    assert coverage["channels"] == {"total": 2, "by_role": {"GROWTH_CANDIDATE": 1, "BASELINE_COMPARATOR": 1}}
    assert coverage["videos"]["by_role"] == {"BREAKOUT": 1, "CHANNEL_BASELINE": 1}
    assert coverage["has_baseline_comparator"] is True
    assert coverage["videos"]["null_public_fields"]["likes"] == 2
    assert coverage["interpretive_chain"]["niche_observation"] == 0


def test_context_bundle_ranks_relevance_before_confidence(tmp_path: Path) -> None:
    from engine.niche_intelligence import NicheIntelligenceRepository

    package = build_package(tmp_path)
    validated = build_empty_study(tmp_path, package)
    response_path = tmp_path / "response.json"
    write_json(response_path, hermes_response())
    import_evidence(validated.root, response_path, reviewed_by="Seb", repository_root=tmp_path)
    result = validate_study(validated.root, repository_root=tmp_path, expected_channel_id="acq-channel")
    videos = [v for v in result.artifacts.values() if v["artifact_type"] == "video_evidence"]
    breakout = next(v["artifact_id"] for v in videos if v["sample"]["role"] == "BREAKOUT")
    baseline = next(v["artifact_id"] for v in videos if v["sample"]["role"] == "CHANNEL_BASELINE")
    add_observation(
        validated.root, key="confident-noise", statement="Unrelated production trivia.",
        observation_type="PERFORMANCE_PATTERN", scope="test", basis="PUBLIC_FACT",
        evidence_refs=[breakout], confidence=0.99, limitations=["none"],
        repository_root=tmp_path,
    )
    add_observation(
        validated.root, key="tentative-caffeine", statement="Caffeine mechanism hook pattern.",
        observation_type="CONTENT_PATTERN", scope="test", basis="PUBLIC_FACT",
        evidence_refs=[baseline], confidence=0.3, limitations=["single sample"],
        repository_root=tmp_path,
    )
    repository = NicheIntelligenceRepository(tmp_path)
    bundle = repository.build_context_bundle(package, validated.root, "caffeine mechanism")
    first, second = bundle["semantic_artifacts"][:2]
    assert "caffeine" in first["summary"].lower()
    assert first["relevance_hits"] > second["relevance_hits"]
