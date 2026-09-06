"""Schema and cross-artifact validation for offline Niche Intelligence studies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .metrics import MetricError, relative_views_same_channel_v1

CONTRACT_ROOT = Path(__file__).resolve().parent / "contracts"
REPORT_TYPES = {
    "channel_evidence": "channel_evidence",
    "video_evidence": "video_evidence",
    "relative_performance": "relative_performance",
    "content_annotations": "content_annotation",
    "script_annotations": "script_annotation",
    "visual_market_annotations": "visual_market_annotation",
    "audience_signals": "audience_signal",
    "observations": "niche_observation",
    "hypotheses": "niche_hypothesis",
    "opportunity_proposals": "opportunity_proposal",
}
SCHEMAS = {
    "niche_study": "niche-study.schema.json",
    "channel_evidence": "channel-evidence.schema.json",
    "video_evidence": "video-evidence.schema.json",
    "relative_performance": "relative-performance.schema.json",
    "content_annotation": "content-annotation.schema.json",
    "script_annotation": "script-annotation.schema.json",
    "visual_market_annotation": "visual-market-annotation.schema.json",
    "audience_signal": "audience-signal.schema.json",
    "niche_observation": "observation.schema.json",
    "niche_hypothesis": "hypothesis.schema.json",
    "opportunity_proposal": "opportunity-proposal.schema.json",
    "niche_study_report": "study-report.schema.json",
}
PRIVATE_METRICS = {
    "CTR", "RETENTION_CURVE", "SWIPE_AWAY_RATE", "AVERAGE_PERCENTAGE_VIEWED",
    "TRAFFIC_SOURCES", "SUBSCRIBER_CONVERSION",
}


class NicheValidationError(ValueError):
    """A Niche Intelligence contract or study bundle is invalid."""


@dataclass(frozen=True)
class ValidatedStudy:
    root: Path
    study: dict[str, Any]
    report: dict[str, Any]
    artifacts: dict[str, dict[str, Any]]
    paths: dict[str, Path]


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NicheValidationError(f"{path}: expected a JSON object")
    return value


def _contracts() -> tuple[dict[str, dict[str, Any]], Registry]:
    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for path in sorted(CONTRACT_ROOT.glob("*.schema.json")):
        schema = _load(path)
        Draft202012Validator.check_schema(schema)
        schemas[path.name] = schema
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return schemas, registry


def validate_contracts() -> int:
    """Validate every CM3 JSON Schema and return its count."""

    schemas, _ = _contracts()
    expected = {"common.schema.json", *SCHEMAS.values()}
    missing = expected - schemas.keys()
    if missing:
        raise NicheValidationError(f"missing Niche Intelligence contracts: {sorted(missing)}")
    return len(schemas)


def _schema_errors(value: dict[str, Any], schema_name: str, label: str) -> list[str]:
    schemas, registry = _contracts()
    validator = Draft202012Validator(
        schemas[schema_name], registry=registry, format_checker=FormatChecker()
    )
    errors = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{label} {location}: {error.message}")
    return errors


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _resolve(root: Path, relative: str, label: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise NicheValidationError(f"{label}: path escapes study root: {relative}")
    if not path.is_file():
        raise NicheValidationError(f"{label}: referenced artifact is missing: {relative}")
    return path


def _unknown_errors(document: dict[str, Any], label: str) -> list[str]:
    null_fields = {key for key, value in document["public_fields"].items() if value is None}
    declared = set(document["unknown_fields"])
    return [] if null_fields == declared else [
        f"{label}: unknown_fields must exactly match null public_fields; expected {sorted(null_fields)}"
    ]


def validate_study(
    study_root: Path,
    *,
    repository_root: Path | None = None,
    expected_channel_id: str | None = None,
) -> ValidatedStudy:
    """Validate a report-led study bundle, all references, and deterministic metrics."""

    root = study_root.resolve()
    report_path = root / "report.json"
    try:
        report = _load(report_path)
    except (OSError, json.JSONDecodeError) as exc:
        raise NicheValidationError(str(exc)) from exc
    errors = _schema_errors(report, SCHEMAS["niche_study_report"], "report.json")
    if errors:
        raise NicheValidationError("\n".join(errors))

    study_path = _resolve(root, report["study_ref"], "study_ref")
    try:
        study = _load(study_path)
    except (OSError, json.JSONDecodeError) as exc:
        raise NicheValidationError(str(exc)) from exc
    errors.extend(_schema_errors(study, SCHEMAS["niche_study"], report["study_ref"]))
    if errors:
        raise NicheValidationError("\n".join(errors))

    artifacts: dict[str, dict[str, Any]] = {study["artifact_id"]: study, report["artifact_id"]: report}
    paths: dict[str, Path] = {study["artifact_id"]: study_path, report["artifact_id"]: report_path}
    referenced_paths = {study_path, report_path}
    for category, expected_type in REPORT_TYPES.items():
        for index, relative in enumerate(report["components"][category]):
            path = _resolve(root, relative, f"components.{category}[{index}]")
            referenced_paths.add(path)
            try:
                document = _load(path)
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(str(exc))
                continue
            actual_type = document.get("artifact_type")
            if actual_type != expected_type:
                errors.append(f"{relative}: expected artifact_type {expected_type!r}, found {actual_type!r}")
                continue
            errors.extend(_schema_errors(document, SCHEMAS[actual_type], relative))
            artifact_id = document.get("artifact_id")
            if artifact_id in artifacts:
                errors.append(f"{relative}: duplicate artifact_id {artifact_id!r}")
            else:
                artifacts[artifact_id] = document
                paths[artifact_id] = path

    unreferenced = {
        path.resolve() for path in root.rglob("*.json") if path.resolve() not in referenced_paths
    }
    if unreferenced:
        errors.append(
            "study contains unreferenced JSON artifacts: "
            + ", ".join(sorted(path.relative_to(root).as_posix() for path in unreferenced))
        )
    if errors:
        raise NicheValidationError("\n".join(errors))

    study_id = study["study_id"]
    channel_id = study["channel_id"]
    if report["study_id"] != study_id or report["channel_id"] != channel_id:
        errors.append("report identity must match its study definition")
    if expected_channel_id is not None and channel_id != expected_channel_id:
        errors.append(f"study channel_id {channel_id!r} does not match expected channel {expected_channel_id!r}")
    if repository_root is not None:
        repository_root = repository_root.resolve()
        expected_parent = (repository_root / "channels" / channel_id / "intelligence" / "studies").resolve()
        if not root.is_relative_to(expected_parent):
            errors.append(f"study must be under channels/{channel_id}/intelligence/studies/")

    if _datetime(study["study_window"]["from"]) > _datetime(study["study_window"]["to"]):
        errors.append("study_window.from must not follow study_window.to")
    freshness = study["freshness"]
    if freshness["state"] == "SUPERSEDED" and not freshness.get("superseded_by"):
        errors.append("SUPERSEDED study freshness requires superseded_by")
    if freshness["state"] != "SUPERSEDED" and freshness.get("superseded_by"):
        errors.append("superseded_by is only legal for SUPERSEDED studies")
    if study.get("supersedes") == study_id:
        errors.append("a study cannot supersede itself")
    policy_version = study["sampling_policy"]["version"]
    if report["methodology"]["sampling_policy_version"] != policy_version:
        errors.append("report sampling policy version must match the study")

    for artifact_id, document in artifacts.items():
        if document["artifact_type"] in {"niche_study", "niche_study_report"}:
            continue
        if document["study_id"] != study_id or document["channel_id"] != channel_id:
            errors.append(f"{artifact_id}: study/channel identity does not match the study definition")
        if document["artifact_type"] in {"channel_evidence", "video_evidence"}:
            errors.extend(_unknown_errors(document, artifact_id))
            if document["sample"]["policy_version"] != policy_version:
                errors.append(f"{artifact_id}: sample policy version does not match the study")
            policy_key = "channel_roles" if document["artifact_type"] == "channel_evidence" else "video_roles"
            if document["sample"]["role"] not in study["sampling_policy"][policy_key]:
                errors.append(f"{artifact_id}: sample role is not enabled by the study policy")
        if document["artifact_type"] == "video_evidence" and set(document["unavailable_private_metrics"]) != PRIVATE_METRICS:
            errors.append(f"{artifact_id}: all public-unavailable private metrics must be explicit")

    channel_sources = {
        item["source"]["source_id"]: item
        for item in artifacts.values() if item["artifact_type"] == "channel_evidence"
    }
    video_artifacts = {
        key: item for key, item in artifacts.items() if item["artifact_type"] == "video_evidence"
    }
    for artifact_id, video in video_artifacts.items():
        if video["channel_source_id"] not in channel_sources:
            errors.append(f"{artifact_id}: channel_source_id has no channel evidence")

    annotation_types = {"content_annotation", "script_annotation", "visual_market_annotation", "audience_signal"}
    for artifact_id, document in artifacts.items():
        kind = document["artifact_type"]
        if kind in annotation_types:
            if document["video_evidence_id"] not in video_artifacts:
                errors.append(f"{artifact_id}: video_evidence_id is missing")
            if kind != "audience_signal" and document["video_evidence_id"] not in document["evidence_refs"]:
                errors.append(f"{artifact_id}: evidence_refs must include video_evidence_id")
        if kind == "script_annotation":
            timed = document["transcript"]["timing"] == "TIMED"
            if document["statistics"]["words_per_second"] is not None and not timed:
                errors.append(f"{artifact_id}: words_per_second requires a TIMED transcript")
            available = document["transcript"]["availability"] == "AVAILABLE"
            if available != (document["transcript"]["source_ref"] is not None):
                errors.append(f"{artifact_id}: transcript availability and source_ref disagree")

    for artifact_id, metric in ((key, value) for key, value in artifacts.items() if value["artifact_type"] == "relative_performance"):
        target = video_artifacts.get(metric["target_video_evidence_id"])
        comparison_ids = metric["comparison"]["population_video_evidence_ids"]
        comparison = [video_artifacts.get(key) for key in comparison_ids]
        if target is None or any(item is None for item in comparison):
            errors.append(f"{artifact_id}: metric references missing video evidence")
            continue
        if any(item["channel_source_id"] != target["channel_source_id"] for item in comparison):
            errors.append(f"{artifact_id}: comparison population must come from the target's channel")
        expected_views = [item["public_fields"]["views"] for item in comparison]
        if metric["inputs"]["target_views"] != target["public_fields"]["views"] or metric["inputs"]["baseline_views"] != expected_views:
            errors.append(f"{artifact_id}: metric inputs do not match referenced public evidence")
            continue
        try:
            expected = relative_views_same_channel_v1(
                artifact_id=artifact_id, study_id=study_id, channel_id=channel_id,
                target_video_evidence_id=metric["target_video_evidence_id"],
                target_views=metric["inputs"]["target_views"],
                comparison_video_evidence_ids=comparison_ids, baseline_views=metric["inputs"]["baseline_views"],
                window_from=metric["comparison"]["window"]["from"], window_to=metric["comparison"]["window"]["to"],
                created_by=metric["created_by"], metric_version=metric["metric_version"],
            )
            for field in ("inputs", "comparison", "missing_data_behavior", "status", "result"):
                if metric[field] != expected[field]:
                    errors.append(f"{artifact_id}: deterministic metric field {field!r} does not match v1")
        except MetricError as exc:
            errors.append(f"{artifact_id}: {exc}")

    allowed_observation_evidence = {
        "channel_evidence", "video_evidence", "relative_performance", "content_annotation",
        "script_annotation", "visual_market_annotation", "audience_signal",
    }
    for artifact_id, observation in ((key, value) for key, value in artifacts.items() if value["artifact_type"] == "niche_observation"):
        for ref in observation["evidence_refs"]:
            if ref not in artifacts or artifacts[ref]["artifact_type"] not in allowed_observation_evidence:
                errors.append(f"{artifact_id}: observation evidence ref is missing or has invalid authority: {ref}")
    for artifact_id, hypothesis in ((key, value) for key, value in artifacts.items() if value["artifact_type"] == "niche_hypothesis"):
        for ref in hypothesis["observation_refs"]:
            if ref not in artifacts or artifacts[ref]["artifact_type"] != "niche_observation":
                errors.append(f"{artifact_id}: hypothesis must reference observations: {ref}")
    for artifact_id, opportunity in ((key, value) for key, value in artifacts.items() if value["artifact_type"] == "opportunity_proposal"):
        for ref in opportunity["hypothesis_refs"]:
            if ref not in artifacts or artifacts[ref]["artifact_type"] != "niche_hypothesis":
                errors.append(f"{artifact_id}: opportunity must reference hypotheses: {ref}")
        for ref in opportunity["evidence_refs"]:
            if ref not in artifacts or artifacts[ref]["artifact_type"] not in allowed_observation_evidence | {"niche_observation"}:
                errors.append(f"{artifact_id}: opportunity evidence ref is invalid: {ref}")

    # Every "what works" claim needs an ordinary comparator: without a
    # baseline, a breakout sample looks more conclusive than it is. Empty
    # scaffolds are exempt — the rule bites once videos or interpretations
    # exist.
    baseline_channels = [
        key for key, item in artifacts.items()
        if item["artifact_type"] == "channel_evidence"
        and item["sample"]["role"] == "BASELINE_COMPARATOR"
    ]
    baseline_videos = [
        key for key, item in artifacts.items()
        if item["artifact_type"] == "video_evidence"
        and item["sample"]["role"] in {"CHANNEL_BASELINE", "RECENT_NORMAL", "UNDERPERFORMER"}
    ]
    claiming = any(
        item["artifact_type"] in {
            "video_evidence", "niche_observation", "niche_hypothesis",
            "opportunity_proposal",
        }
        for item in artifacts.values()
    )
    if claiming and not baseline_channels and not baseline_videos:
        errors.append(
            "study has no baseline comparator: add at least one BASELINE_COMPARATOR channel "
            "or one CHANNEL_BASELINE/RECENT_NORMAL/UNDERPERFORMER video before claiming what works"
        )

    if errors:
        raise NicheValidationError("\n".join(errors))
    return ValidatedStudy(root, study, report, artifacts, paths)


COMPARATOR_VIDEO_ROLES = frozenset({"CHANNEL_BASELINE", "RECENT_NORMAL", "UNDERPERFORMER"})


def study_coverage(validated: ValidatedStudy) -> dict[str, Any]:
    """Summarize what a study covers — and what it leaves out.

    Read-only: counts roles, formats, windows, missing fields, and chain
    depths so reviewers can see sampling gaps before trusting a claim.
    """
    channels = [item for item in validated.artifacts.values() if item["artifact_type"] == "channel_evidence"]
    videos = [item for item in validated.artifacts.values() if item["artifact_type"] == "video_evidence"]
    channel_roles: dict[str, int] = {}
    for item in channels:
        channel_roles[item["sample"]["role"]] = channel_roles.get(item["sample"]["role"], 0) + 1
    video_roles: dict[str, int] = {}
    video_formats: dict[str, int] = {}
    null_fields: dict[str, int] = {}
    published: list[str] = []
    for item in videos:
        video_roles[item["sample"]["role"]] = video_roles.get(item["sample"]["role"], 0) + 1
        video_formats[item["format"]] = video_formats.get(item["format"], 0) + 1
        for field, value in item["public_fields"].items():
            if value is None:
                null_fields[field] = null_fields.get(field, 0) + 1
        seen = item["public_fields"].get("published_at")
        if seen:
            published.append(seen)
    chain = {
        kind: sum(1 for item in validated.artifacts.values() if item["artifact_type"] == kind)
        for kind in (
            "niche_observation", "niche_hypothesis", "opportunity_proposal",
            "content_annotation", "script_annotation", "visual_market_annotation",
        )
    }
    return {
        "study_id": validated.study["study_id"],
        "channel_id": validated.study["channel_id"],
        "study_window": validated.study["study_window"],
        "channels": {"total": len(channels), "by_role": channel_roles},
        "videos": {
            "total": len(videos), "by_role": video_roles, "by_format": video_formats,
            "null_public_fields": null_fields,
            "published_range": [min(published), max(published)] if published else None,
        },
        "interpretive_chain": chain,
        "has_baseline_comparator": bool(
            channel_roles.get("BASELINE_COMPARATOR")
            or any(role in COMPARATOR_VIDEO_ROLES for role in video_roles)
        ),
        "limitations": validated.report["limitations"],
    }
