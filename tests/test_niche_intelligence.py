from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from engine.memory import ChannelMemoryRepository, initialize_channel_wiki
from engine.niche_intelligence import (
    MetricError,
    NicheIntelligenceRepository,
    NicheValidationError,
    relative_views_same_channel_v1,
    validate_contracts,
    validate_study,
)

ROOT = Path(__file__).resolve().parents[1]
AT = "2026-06-30T12:00:00+00:00"
PRIVATE = [
    "CTR", "RETENTION_CURVE", "SWIPE_AWAY_RATE", "AVERAGE_PERCENTAGE_VIEWED",
    "TRAFFIC_SOURCES", "SUBSCRIBER_CONVERSION",
]
ARCHETYPES = {
    "finance-demo": ("finance", "DATA_STORY"),
    "science-demo": ("science", "ILLUSTRATED_EXPLAINER"),
    "history-demo": ("history", "MAP_STORY"),
}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def root_with_memory(tmp_path: Path) -> Path:
    contracts = tmp_path / "engine" / "memory" / "contracts"
    contracts.mkdir(parents=True)
    shutil.copyfile(ROOT / "engine/memory/contracts/wiki-page.schema.json", contracts / "wiki-page.schema.json")
    return tmp_path


def write_package(root: Path, channel_id: str, archetype: str) -> Path:
    package = root / "channels" / channel_id
    package.mkdir(parents=True, exist_ok=True)
    identity = {
        "schema_version": "0.1.0", "id": channel_id, "name": channel_id.title(), "version": "0.1.0",
        "status": "DRAFT", "language": "en", "niche": {"primary": "synthetic"},
        "platform": {"primary": "YOUTUBE", "formats": ["SHORTS"]},
        "production": {"archetype": archetype, "renderer": "remotion"}, "creation": {"mode": "ORIGINAL"},
        "canonical_sources": {"channel_state": f"channels/{channel_id}/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.2.0", "channel_id": channel_id, "revision": 0, "state": "CHANNEL_INIT",
        "status": "ACTIVE", "completed": [], "active_experiment": None, "waiting_for": None,
        "blocker": None, "next_action": "Study synthetic evidence.", "resume_state": None,
        "source_refs": [f"channels/{channel_id}/channel.yaml"], "known_gaps": [],
        "legacy_mapping": False, "events": [], "updated_at": AT,
    }
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    write_json(package / "CHANNEL_STATE.json", state)
    return package


def provenance() -> dict:
    return {"created_at": AT, "creator": "TOOL", "tool": "synthetic.fixture", "version": "1.0.0"}


def public_source(source_id: str, kind: str) -> dict:
    return {
        "platform": "YOUTUBE", "source_id": source_id,
        "url": f"https://synthetic.invalid/{kind}/{source_id}", "collected_at": AT,
        "collector": {"kind": "TOOL", "name": "synthetic.fixture", "version": "1.0.0"},
        "evidence_class": "PUBLIC_MARKET_EVIDENCE", "reference_role": "MARKET_EVIDENCE",
        "representation": "RAW_PUBLIC_FACT",
    }


def build_study(
    root: Path,
    channel_id: str,
    *,
    study_id: str | None = None,
    study_version: str = "1.0.0",
    supersedes: str | None = None,
) -> tuple[Path, dict[str, dict], dict[str, str]]:
    niche, archetype = ARCHETYPES[channel_id]
    write_package(root, channel_id, archetype)
    study_id = study_id or f"{channel_id}-study-v1"
    study_root = root / "channels" / channel_id / "intelligence" / "studies" / study_id
    source_channel_id = f"synthetic-{niche}-channel"
    ids = {
        "study": f"niche:study:{study_id}", "channel": f"niche:channel:{channel_id}-sample",
        "target": f"niche:video:{channel_id}-breakout", "base1": f"niche:video:{channel_id}-baseline-a",
        "base2": f"niche:video:{channel_id}-baseline-b", "metric": f"niche:metric:{channel_id}-relative",
        "content": f"niche:content:{channel_id}-content", "script": f"niche:script:{channel_id}-script",
        "visual": f"niche:visual:{channel_id}-visual", "audience": f"niche:audience:{channel_id}-signal",
        "observation": f"niche:observation:{channel_id}-pattern", "hypothesis": f"niche:hypothesis:{channel_id}-effect",
        "opportunity": f"niche:opportunity:{channel_id}-gap", "report": f"niche:report:{study_id}",
    }
    study = {
        "schema_version": "1.0.0", "artifact_type": "niche_study", "artifact_id": ids["study"],
        "study_id": study_id, "study_version": study_version, "channel_id": channel_id,
        "scope": {"niche": niche, "sub_niches": [f"{niche}-education"], "platform": "YOUTUBE", "format": "SHORTS", "language": "en", "geography": None, "production_archetype": archetype},
        "study_window": {"from": "2026-01-01T00:00:00+00:00", "to": AT},
        "freshness": {"state": "CURRENT", "evaluated_at": AT, "revalidate_after": "2026-09-30T00:00:00+00:00"},
        "supersedes": supersedes, "methodology_version": "niche-intelligence.v1",
        "sampling_policy": {
            "version": "1.0.0",
            "channel_roles": ["ESTABLISHED_LEADER", "GROWTH_CANDIDATE", "SMALL_BREAKOUT", "BASELINE_COMPARATOR", "OTHER", "UNKNOWN"],
            "video_roles": ["BREAKOUT", "CHANNEL_BASELINE", "RECENT_NORMAL", "UNDERPERFORMER", "OUTLIER", "OTHER", "UNKNOWN"],
            "thresholds": {"breakout_relative_views": 3.0, "note": "synthetic and configurable"},
        },
        "created_by": provenance(),
    }
    channel = {
        "schema_version": "1.0.0", "artifact_type": "channel_evidence", "artifact_id": ids["channel"],
        "study_id": study_id, "channel_id": channel_id, "source": public_source(source_channel_id, "channel"),
        "channel_name": f"Synthetic {niche.title()} Channel",
        "sample": {"role": "BASELINE_COMPARATOR", "rationale": "Provides a same-channel synthetic baseline.", "policy_version": "1.0.0"},
        "classifications": {"niches": [niche, "education"]},
        "public_fields": {"subscriber_count": None, "public_video_count": 50, "created_at": None, "observed_uploads_per_30d": 8.0, "shorts_fraction": None},
        "unknown_fields": ["subscriber_count", "created_at", "shorts_fraction"],
    }

    def video(key: str, source_id: str, title: str, role: str, views: int | None) -> dict:
        fields = {
            "published_at": "2026-06-01T00:00:00+00:00", "duration_seconds": 45.0,
            "views": views, "likes": None, "comment_count": None, "description": None,
            "age_at_observation_days": 29.5,
        }
        return {
            "schema_version": "1.0.0", "artifact_type": "video_evidence", "artifact_id": ids[key],
            "study_id": study_id, "channel_id": channel_id, "source": public_source(source_id, "video"),
            "channel_source_id": source_channel_id, "title": title, "format": "SHORTS",
            "sample": {"role": role, "rationale": f"Synthetic {role.lower()} assignment.", "policy_version": "1.0.0"},
            "public_fields": fields, "unknown_fields": [name for name, value in fields.items() if value is None],
            "unavailable_private_metrics": list(PRIVATE),
        }

    target = video("target", f"{niche}-breakout", f"A specific {niche} mechanism", "BREAKOUT", 1500)
    base1 = video("base1", f"{niche}-base-a", f"A normal {niche} topic", "CHANNEL_BASELINE", 100)
    base2 = video("base2", f"{niche}-base-b", f"Another normal {niche} topic", "RECENT_NORMAL", 200)
    metric = relative_views_same_channel_v1(
        artifact_id=ids["metric"], study_id=study_id, channel_id=channel_id,
        target_video_evidence_id=ids["target"], target_views=1500,
        comparison_video_evidence_ids=[ids["base1"], ids["base2"]], baseline_views=[100, 200],
        window_from="2026-01-01T00:00:00+00:00", window_to=AT, created_by=provenance(),
    )
    content = {
        "schema_version": "1.0.0", "artifact_type": "content_annotation", "artifact_id": ids["content"],
        "study_id": study_id, "channel_id": channel_id, "video_evidence_id": ids["target"], "authority": "ANNOTATION", "evidence_refs": [ids["target"]],
        "annotation": {
            "primary_topic": niche, "subtopics": ["mechanism"], "entities": [], "trend_dependence": "EVERGREEN",
            "hook_family": "SPECIFIC_NUMBER", "hook_text": "A synthetic number", "viewer_promise": "Explain one mechanism.",
            "structure": "PROBLEM_MECHANISM_CONSEQUENCE",
            "characteristics": {"information_density": "HIGH", "technical_depth": "MEDIUM", "numeric_specificity": "HIGH", "emotional_framing": None, "novelty": "MEDIUM", "recognizable_entities": False, "examples_or_metaphors": True},
            "ending": "IMPLICATION",
        }, "confidence": 0.8, "created_by": provenance(),
    }
    script = {
        "schema_version": "1.0.0", "artifact_type": "script_annotation", "artifact_id": ids["script"],
        "study_id": study_id, "channel_id": channel_id, "video_evidence_id": ids["target"], "authority": "ANNOTATION", "evidence_refs": [ids["target"]],
        "transcript": {"availability": "AVAILABLE", "timing": "UNTIMED", "source_ref": "synthetic-transcript", "method": "MANUAL", "language": "en"},
        "statistics": {"word_count": 90, "words_per_second": None, "opening_excerpt": "Synthetic opening.", "sentence_length_mean": 9.0, "question_count": 1, "numeric_reference_count": 2},
        "annotations": {"hook": "Specific-number opening", "narrative_structure": "Mechanism", "information_density_hypothesis": "Potentially dense", "ending_behavior": "Implication"},
        "confidence": 0.7, "created_by": provenance(),
    }
    visual = {
        "schema_version": "1.0.0", "artifact_type": "visual_market_annotation", "artifact_id": ids["visual"],
        "study_id": study_id, "channel_id": channel_id, "video_evidence_id": ids["target"], "authority": "ANNOTATION",
        "reference_role": "MARKET_EVIDENCE", "design_authority": "PROHIBITED", "renderer_eligible": False, "evidence_refs": [ids["target"]],
        "annotation": {"production_approaches": ["CHARTS_DATA_GRAPHICS" if archetype == "DATA_STORY" else "ILLUSTRATED_SCENES" if archetype == "ILLUSTRATED_EXPLAINER" else "MAPS"], "scene_change_frequency_proxy": None, "text_density_proxy": "MEDIUM", "visual_metaphor_usage": "OCCASIONAL", "continuity": "CONTINUOUS_SCENES"},
        "confidence": 0.75, "created_by": provenance(),
    }
    audience = {
        "schema_version": "1.0.0", "artifact_type": "audience_signal", "artifact_id": ids["audience"],
        "study_id": study_id, "channel_id": channel_id, "video_evidence_id": ids["target"], "authority": "ANNOTATION",
        "signal_mode": "PATTERN_ACROSS_COMMENTS", "category": "REPEATED_QUESTION", "summary": f"Some sampled comments ask for more {niche} mechanisms.",
        "source_refs": ["synthetic-comment-1", "synthetic-comment-2"], "sampling_method": "Two deliberately synthetic comments.", "frequency": 2,
        "limitations": ["Synthetic comments are not representative of an audience."], "confidence": 0.4, "created_by": provenance(),
    }
    observation = {
        "schema_version": "1.0.0", "artifact_type": "niche_observation", "artifact_id": ids["observation"],
        "study_id": study_id, "channel_id": channel_id, "authority": "DESCRIPTIVE_OBSERVATION",
        "statement": f"In this synthetic {niche} sample, the specific-mechanism video had higher relative views than its same-channel baseline.",
        "observation_type": "PERFORMANCE_PATTERN", "scope": f"Synthetic English {niche} Shorts", "basis": "MIXED",
        "evidence_refs": [ids["metric"], ids["content"]], "confidence": 0.8,
        "limitations": ["Synthetic evidence cannot establish real market prevalence or causality."], "created_by": provenance(),
    }
    hypothesis = {
        "schema_version": "1.0.0", "artifact_type": "niche_hypothesis", "artifact_id": ids["hypothesis"],
        "study_id": study_id, "channel_id": channel_id, "authority": "UNAPPROVED_HYPOTHESIS",
        "statement": f"Mechanism-specific openings may improve initial interest in {niche} Shorts.", "predicted_effect": "Higher same-channel relative views.",
        "applicable_context": f"English {niche} Shorts", "observation_refs": [ids["observation"]],
        "competing_explanations": ["Topic timing or distribution may explain the difference."], "confidence": 0.5,
        "test_idea": "Compare multiple original openings while holding the format stable.", "status": "ACTIVE", "created_by": provenance(),
    }
    opportunity = {
        "schema_version": "1.0.0", "artifact_type": "opportunity_proposal", "artifact_id": ids["opportunity"],
        "study_id": study_id, "channel_id": channel_id, "authority": "PROPOSED_OPPORTUNITY",
        "observed_market": f"The synthetic {niche} sample contains familiar explanatory formats.",
        "underrepresented": f"Original mechanism-driven {archetype.lower()} treatment.",
        "proposal": f"Human strategy review could test an original mechanism-driven {niche} format.",
        "hypothesis_refs": [ids["hypothesis"]], "evidence_refs": [ids["observation"], ids["metric"]],
        "risks": ["Production cost", "Synthetic evidence has no market validity"], "confidence": 0.4,
        "human_strategy_decision_required": True, "status": "PROPOSED", "created_by": provenance(),
    }
    documents = {"study": study, "channel": channel, "target": target, "base1": base1, "base2": base2, "metric": metric, "content": content, "script": script, "visual": visual, "audience": audience, "observation": observation, "hypothesis": hypothesis, "opportunity": opportunity}
    paths = {
        "study": "study.json", "channel": "evidence/channel.json", "target": "evidence/target.json", "base1": "evidence/base-a.json", "base2": "evidence/base-b.json",
        "metric": "metrics/relative.json", "content": "annotations/content.json", "script": "annotations/script.json", "visual": "annotations/visual.json", "audience": "annotations/audience.json",
        "observation": "observations/pattern.json", "hypothesis": "hypotheses/effect.json", "opportunity": "opportunities/gap.json",
    }
    for key, document in documents.items():
        write_json(study_root / paths[key], document)
    report = {
        "schema_version": "1.0.0", "artifact_type": "niche_study_report", "artifact_id": ids["report"], "study_id": study_id, "channel_id": channel_id,
        "authority": "DESCRIPTIVE_ONLY", "study_ref": paths["study"],
        "components": {
            "channel_evidence": [paths["channel"]], "video_evidence": [paths["target"], paths["base1"], paths["base2"]],
            "relative_performance": [paths["metric"]], "content_annotations": [paths["content"]], "script_annotations": [paths["script"]],
            "visual_market_annotations": [paths["visual"]], "audience_signals": [paths["audience"]], "observations": [paths["observation"]],
            "hypotheses": [paths["hypothesis"]], "opportunity_proposals": [paths["opportunity"]],
        },
        "limitations": ["All records are synthetic; no live market conclusion is supported."],
        "methodology": {"study_contract_version": "1.0.0", "sampling_policy_version": "1.0.0", "metric_versions": ["relative_views_same_channel.v1"], "causality_claimed": False},
        "created_by": provenance(),
    }
    write_json(study_root / "report.json", report)
    documents["report"] = report
    paths["report"] = "report.json"
    return study_root, documents, paths


def test_contracts_and_three_generic_synthetic_studies_validate(tmp_path: Path) -> None:
    assert validate_contracts() == 13
    root = root_with_memory(tmp_path)
    for channel_id, (_, archetype) in ARCHETYPES.items():
        study_root, _, _ = build_study(root, channel_id)
        validated = validate_study(study_root, repository_root=root, expected_channel_id=channel_id)
        assert validated.study["scope"]["production_archetype"] == archetype
        assert len(validated.artifacts) == 14


def test_explicit_unknowns_relationships_and_private_boundary_are_enforced(tmp_path: Path) -> None:
    root = root_with_memory(tmp_path)
    study_root, documents, paths = build_study(root, "finance-demo")
    documents["target"]["unknown_fields"].remove("likes")
    write_json(study_root / paths["target"], documents["target"])
    with pytest.raises(NicheValidationError, match="unknown_fields must exactly match"):
        validate_study(study_root)
    documents["target"]["unknown_fields"].append("likes")
    documents["target"]["unavailable_private_metrics"].remove("CTR")
    write_json(study_root / paths["target"], documents["target"])
    with pytest.raises(NicheValidationError, match="private metrics"):
        validate_study(study_root)
    documents["target"]["unavailable_private_metrics"] = list(PRIVATE)
    documents["target"]["channel_source_id"] = "missing-channel"
    write_json(study_root / paths["target"], documents["target"])
    with pytest.raises(NicheValidationError, match="has no channel evidence"):
        validate_study(study_root)


def test_same_channel_metric_is_deterministic_transparent_and_versioned() -> None:
    kwargs = {
        "artifact_id": "niche:metric:test", "study_id": "test-study", "channel_id": "finance-demo",
        "target_video_evidence_id": "niche:video:target", "target_views": 1500,
        "comparison_video_evidence_ids": ["niche:video:a", "niche:video:b"], "baseline_views": [100, 200],
        "window_from": "2026-01-01T00:00:00+00:00", "window_to": AT, "created_by": provenance(),
    }
    first = relative_views_same_channel_v1(**kwargs)
    assert first == relative_views_same_channel_v1(**kwargs)
    assert first["result"] == {"baseline_median_views": 150.0, "relative_views_ratio": 10.0, "percentile_within_comparison": 1.0, "breakout_magnitude": 9.0, "reason": None}
    assert first["comparison"]["baseline_quality"] == "LOW"
    missing = relative_views_same_channel_v1(**{**kwargs, "target_views": None})
    assert missing["status"] == "NOT_COMPUTABLE" and missing["result"]["reason"] == "target views are unknown"
    zero = relative_views_same_channel_v1(**{**kwargs, "baseline_views": [0, 0]})
    assert zero["status"] == "NOT_COMPUTABLE" and zero["result"]["relative_views_ratio"] is None
    with pytest.raises(MetricError, match="unsupported"):
        relative_views_same_channel_v1(**kwargs, metric_version="relative_views_same_channel.v2")


def test_metric_recomputation_and_same_channel_integrity_are_enforced(tmp_path: Path) -> None:
    root = root_with_memory(tmp_path)
    study_root, documents, paths = build_study(root, "science-demo")
    documents["metric"]["result"]["relative_views_ratio"] = 999
    write_json(study_root / paths["metric"], documents["metric"])
    with pytest.raises(NicheValidationError, match="deterministic metric"):
        validate_study(study_root)
    documents["metric"] = relative_views_same_channel_v1(
        artifact_id=documents["metric"]["artifact_id"], study_id=documents["study"]["study_id"], channel_id="science-demo",
        target_video_evidence_id=documents["target"]["artifact_id"], target_views=1500,
        comparison_video_evidence_ids=[documents["base1"]["artifact_id"], documents["base2"]["artifact_id"]],
        baseline_views=[100, 200], window_from="2026-01-01T00:00:00+00:00", window_to=AT, created_by=provenance(),
    )
    write_json(study_root / paths["metric"], documents["metric"])
    documents["base2"]["channel_source_id"] = "another-source"
    write_json(study_root / paths["base2"], documents["base2"])
    with pytest.raises(NicheValidationError, match=r"(?:has no channel evidence|target's channel)"):
        validate_study(study_root)


def test_authority_reference_roles_and_transcript_precision_cannot_masquerade(tmp_path: Path) -> None:
    root = root_with_memory(tmp_path)
    study_root, documents, paths = build_study(root, "history-demo")
    documents["observation"]["authority"] = "human_approved"
    write_json(study_root / paths["observation"], documents["observation"])
    with pytest.raises(NicheValidationError, match="DESCRIPTIVE_OBSERVATION"):
        validate_study(study_root)
    documents["observation"]["authority"] = "DESCRIPTIVE_OBSERVATION"
    write_json(study_root / paths["observation"], documents["observation"])
    documents["visual"]["reference_role"] = "CREATIVE_REFERENCE"
    write_json(study_root / paths["visual"], documents["visual"])
    with pytest.raises(NicheValidationError, match="MARKET_EVIDENCE"):
        validate_study(study_root)
    documents["visual"]["reference_role"] = "MARKET_EVIDENCE"
    write_json(study_root / paths["visual"], documents["visual"])
    documents["script"]["statistics"]["words_per_second"] = 2.0
    write_json(study_root / paths["script"], documents["script"])
    with pytest.raises(NicheValidationError, match="requires a TIMED transcript"):
        validate_study(study_root)


def test_authority_ladder_references_are_enforced(tmp_path: Path) -> None:
    root = root_with_memory(tmp_path)
    study_root, documents, paths = build_study(root, "finance-demo")
    documents["hypothesis"]["observation_refs"] = [documents["metric"]["artifact_id"]]
    write_json(study_root / paths["hypothesis"], documents["hypothesis"])
    with pytest.raises(NicheValidationError, match="hypothesis must reference observations"):
        validate_study(study_root)
    documents["hypothesis"]["observation_refs"] = [documents["observation"]["artifact_id"]]
    write_json(study_root / paths["hypothesis"], documents["hypothesis"])
    documents["opportunity"]["hypothesis_refs"] = [documents["observation"]["artifact_id"]]
    write_json(study_root / paths["opportunity"], documents["opportunity"])
    with pytest.raises(NicheValidationError, match="opportunity must reference hypotheses"):
        validate_study(study_root)


def test_study_versions_are_append_only_compatible_artifacts(tmp_path: Path) -> None:
    root = root_with_memory(tmp_path)
    first_root, _, _ = build_study(root, "finance-demo", study_id="finance-2026-q2")
    second_root, second, paths = build_study(root, "finance-demo", study_id="finance-2026-q3", study_version="2.0.0", supersedes="finance-2026-q2")
    assert validate_study(first_root).study["study_version"] == "1.0.0"
    assert validate_study(second_root).study["supersedes"] == "finance-2026-q2"
    second["study"]["freshness"] = {"state": "SUPERSEDED", "evaluated_at": AT, "revalidate_after": None}
    write_json(second_root / paths["study"], second["study"])
    with pytest.raises(NicheValidationError, match="requires superseded_by"):
        validate_study(second_root)


def test_cm2_memory_summary_integration_is_scoped_opt_in_and_bounded(tmp_path: Path) -> None:
    root = root_with_memory(tmp_path)
    finance_root, _, _ = build_study(root, "finance-demo")
    science_root, _, _ = build_study(root, "science-demo")
    radicat = write_package(root, "radicat", "ILLUSTRATED_EXPLAINER")
    finance = root / "channels" / "finance-demo"
    science = root / "channels" / "science-demo"
    for package in (finance, science, radicat):
        initialize_channel_wiki(package, root, created_at=AT)
    repository = NicheIntelligenceRepository(root)
    # 3 interpretive summaries (observation/hypothesis/opportunity) + 3 what-works
    # teardown summaries (content/script/visual) published to market/teardowns/.
    assert len(repository.publish_semantic_summaries(finance, finance_root)) == 6
    assert len(repository.publish_semantic_summaries(science, science_root)) == 6
    memory = ChannelMemoryRepository(root)
    memory.write_page("method.md", {
        "schema_version": "0.3.0", "knowledge_id": "wiki:engine/niche-method", "title": "Niche Evidence Method",
        "kind": "procedure", "status": "active", "authority": "descriptive", "scope": "ENGINE", "channel_id": None,
        "video_id": None, "tags": ["market", "niche_intelligence"], "confidence": None, "created_at": AT, "updated_at": AT,
        "related": [], "provenance": [{"kind": "repository", "ref": "engine/memory/contracts/wiki-page.schema.json"}],
    }, "Use the evidence ladder for every niche study.")
    memory.write_page("market/observations/vacuum.md", {
        "schema_version": "0.3.0", "knowledge_id": "wiki:channel/radicat/market/observation/vacuum", "title": "Vacuum Market Note",
        "kind": "observation", "status": "active", "authority": "descriptive", "scope": "CHANNEL", "channel_id": "radicat",
        "video_id": None, "tags": ["market", "vacuum"], "confidence": 0.5, "created_at": AT, "updated_at": AT,
        "related": [], "provenance": [{"kind": "repository", "ref": "channels/radicat/channel.yaml"}],
    }, "Radicat-only synthetic vacuum note.")
    bundle = repository.build_context_bundle(finance, finance_root, "mechanism niche vacuum", artifact_limit=2, memory_limit=8, max_summary_chars=240)
    assert bundle["channel_id"] == "finance-demo"
    # Teardown summaries sort highest by confidence and are long: the 240-char
    # budget is consumed by the first, so fewer than artifact_limit fit. The
    # bound — not the count — is the invariant under test.
    assert len(bundle["semantic_artifacts"]) <= 2
    assert sum(len(item["summary"]) for item in bundle["semantic_artifacts"]) <= 240
    assert any(item["artifact_type"] == "content_annotation" for item in bundle["semantic_artifacts"])
    memory_ids = {item["knowledge_id"] for item in bundle["memory"]}
    assert not any("radicat" in item for item in memory_ids)
    assert "wiki:engine/niche-method" not in memory_ids
    with_engine = repository.build_context_bundle(finance, finance_root, "niche method", include_engine=True)
    assert "wiki:engine/niche-method" in {item["knowledge_id"] for item in with_engine["memory"]}
    with pytest.raises(NicheValidationError, match="does not match expected channel"):
        repository.build_context_bundle(science, finance_root, "niche")


def test_cli_validates_contracts_and_a_synthetic_study(tmp_path: Path) -> None:
    root = root_with_memory(tmp_path)
    study_root, _, _ = build_study(root, "history-demo")
    contracts = subprocess.run(
        [sys.executable, "tools/niche_intelligence.py", "validate-contracts"], cwd=ROOT,
        text=True, capture_output=True, check=False,
    )
    assert contracts.returncode == 0 and "CONTRACTS VALID" in contracts.stdout
    study = subprocess.run(
        [sys.executable, "tools/niche_intelligence.py", "validate", str(study_root)], cwd=ROOT,
        text=True, capture_output=True, check=False,
    )
    assert study.returncode == 0 and '"study_id": "history-demo-study-v1"' in study.stdout
