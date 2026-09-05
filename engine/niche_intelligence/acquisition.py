"""CM4 study-mutation adapter: scaffold studies and write reviewed public evidence.

This module is the only writer that turns collected public YouTube facts, or an
interpretive observation/hypothesis/opportunity chain, into a validated CM3
study bundle. It never acts as the collecting worker itself (see
``docs/LOCAL_WORKERS.md``): callers must pass an already-collected response
document, and importing evidence always requires an explicit human reviewer.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.channel import ChannelValidationError, validate_channel_package

from .validation import PRIVATE_METRICS, NicheValidationError, validate_study


CHANNEL_ROLES = {"ESTABLISHED_LEADER", "GROWTH_CANDIDATE", "SMALL_BREAKOUT", "BASELINE_COMPARATOR", "OTHER", "UNKNOWN"}
VIDEO_ROLES = {"BREAKOUT", "CHANNEL_BASELINE", "RECENT_NORMAL", "UNDERPERFORMER", "OUTLIER", "OTHER", "UNKNOWN"}
CHANNEL_PUBLIC_FIELDS = ("subscriber_count", "public_video_count", "created_at", "observed_uploads_per_30d", "shorts_fraction")
VIDEO_PUBLIC_FIELDS = ("published_at", "duration_seconds", "views", "likes", "comment_count", "description", "age_at_observation_days")


def _timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-._")
    if not slug:
        raise NicheValidationError(f"cannot derive an artifact-id slug from {value!r}")
    if not re.match(r"^[a-z0-9]", slug):
        slug = f"s{slug}"
    return slug


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NicheValidationError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise NicheValidationError(f"{path}: top-level JSON value must be an object")
    return value


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def _creation_provenance(tool: str) -> dict[str, Any]:
    return {"created_at": _timestamp(None), "creator": "MODEL_ASSISTED", "tool": tool, "version": "1.0.0"}


def _commit_or_rollback(
    study_root: Path,
    *,
    repository_root: Path,
    expected_channel_id: str,
    report_path: Path,
    previous_report_bytes: bytes,
    new_files: list[Path],
):
    try:
        return validate_study(study_root, repository_root=repository_root, expected_channel_id=expected_channel_id)
    except NicheValidationError:
        report_path.write_bytes(previous_report_bytes)
        for path in new_files:
            path.unlink(missing_ok=True)
        raise


def init_study(
    package_root: Path,
    repository_root: Path,
    *,
    study_id: str,
    niche: str,
    sub_niches: list[str],
    archetype: str,
    fmt: str,
    language: str,
    geography: str | None,
    channel_roles: list[str],
    video_roles: list[str],
    window_from: str,
    window_to: str,
    sampling_policy_version: str = "1.0.0",
):
    """Scaffold a new, immediately-valid, evidence-empty CM3 study bundle."""

    repository_root = repository_root.resolve()
    try:
        package = validate_channel_package(package_root.resolve(), repository_root)
    except ChannelValidationError as exc:
        raise NicheValidationError(str(exc)) from exc
    channel_id = package.identity["id"]

    study_root = repository_root / "channels" / channel_id / "intelligence" / "studies" / study_id
    if study_root.exists():
        raise NicheValidationError(f"study already exists: {study_root}")

    now = _timestamp(None)
    study = {
        "schema_version": "1.0.0", "artifact_type": "niche_study",
        "artifact_id": f"niche:study:{study_id}",
        "study_id": study_id, "study_version": "1.0.0", "channel_id": channel_id,
        "scope": {
            "niche": niche, "sub_niches": sub_niches, "platform": "YOUTUBE", "format": fmt,
            "language": language, "geography": geography, "production_archetype": archetype,
        },
        "study_window": {"from": window_from, "to": window_to},
        "freshness": {"state": "CURRENT", "evaluated_at": now, "revalidate_after": None},
        "supersedes": None, "methodology_version": "niche-intelligence.v1",
        "sampling_policy": {
            "version": sampling_policy_version,
            "channel_roles": channel_roles, "video_roles": video_roles,
            "thresholds": {},
        },
        "created_by": _creation_provenance("engine.niche_intelligence.acquisition.init_study"),
    }
    report = {
        "schema_version": "1.0.0", "artifact_type": "niche_study_report",
        "artifact_id": f"niche:report:{study_id}", "study_id": study_id, "channel_id": channel_id,
        "authority": "DESCRIPTIVE_ONLY", "study_ref": "study.json",
        "components": {
            "channel_evidence": [], "video_evidence": [], "relative_performance": [],
            "content_annotations": [], "script_annotations": [], "visual_market_annotations": [],
            "audience_signals": [], "observations": [], "hypotheses": [], "opportunity_proposals": [],
        },
        "limitations": [
            "All records reflect a bounded public sample; no market-wide or causal claim is supported.",
        ],
        "methodology": {
            "study_contract_version": "1.0.0", "sampling_policy_version": sampling_policy_version,
            "metric_versions": [], "causality_claimed": False,
        },
        "created_by": _creation_provenance("engine.niche_intelligence.acquisition.init_study"),
    }
    _write_json_atomic(study_root / "study.json", study)
    _write_json_atomic(study_root / "report.json", report)
    return validate_study(study_root, repository_root=repository_root, expected_channel_id=channel_id)


def _channel_evidence_from_response(entry: dict[str, Any], response: dict[str, Any], study_id: str, channel_id: str, niche: str) -> tuple[str, dict[str, Any]]:
    public_fields = {key: entry.get("public_fields", {}).get(key) for key in CHANNEL_PUBLIC_FIELDS}
    unknown_fields = [key for key, value in public_fields.items() if value is None]
    artifact_id = f"niche:channel:{_slug(entry['source_id'])}"
    document = {
        "schema_version": "1.0.0", "artifact_type": "channel_evidence", "artifact_id": artifact_id,
        "study_id": study_id, "channel_id": channel_id,
        "source": {
            "platform": "YOUTUBE", "source_id": entry["source_id"], "url": entry["url"],
            "collected_at": response["collected_at"],
            "collector": {
                "kind": "MODEL_ASSISTED", "name": response["worker"],
                "version": response.get("model_version") or response.get("hermes_version") or "unversioned",
            },
            "evidence_class": "PUBLIC_MARKET_EVIDENCE", "reference_role": "MARKET_EVIDENCE",
            "representation": "RAW_PUBLIC_FACT",
        },
        "channel_name": entry.get("channel_name", entry["source_id"]),
        "sample": {
            "role": entry.get("sample_role", "UNKNOWN"),
            "rationale": entry.get("sample_rationale") or "No rationale provided by the collector.",
            "policy_version": entry.get("sample_policy_version", "1.0.0"),
        },
        "classifications": {"niches": entry.get("niches") or [niche]},
        "public_fields": public_fields, "unknown_fields": unknown_fields,
    }
    return artifact_id, document


def _video_evidence_from_response(entry: dict[str, Any], response: dict[str, Any], study_id: str, channel_id: str) -> tuple[str, dict[str, Any]]:
    public_fields = {key: entry.get("public_fields", {}).get(key) for key in VIDEO_PUBLIC_FIELDS}
    unknown_fields = [key for key, value in public_fields.items() if value is None]
    artifact_id = f"niche:video:{_slug(entry['source_id'])}"
    document = {
        "schema_version": "1.0.0", "artifact_type": "video_evidence", "artifact_id": artifact_id,
        "study_id": study_id, "channel_id": channel_id,
        "source": {
            "platform": "YOUTUBE", "source_id": entry["source_id"], "url": entry["url"],
            "collected_at": response["collected_at"],
            "collector": {
                "kind": "MODEL_ASSISTED", "name": response["worker"],
                "version": response.get("model_version") or response.get("hermes_version") or "unversioned",
            },
            "evidence_class": "PUBLIC_MARKET_EVIDENCE", "reference_role": "MARKET_EVIDENCE",
            "representation": "RAW_PUBLIC_FACT",
        },
        "channel_source_id": entry["channel_source_id"], "title": entry.get("title", entry["source_id"]),
        "format": entry.get("format", "UNKNOWN"),
        "sample": {
            "role": entry.get("sample_role", "UNKNOWN"),
            "rationale": entry.get("sample_rationale") or "No rationale provided by the collector.",
            "policy_version": entry.get("sample_policy_version", "1.0.0"),
        },
        "public_fields": public_fields, "unknown_fields": unknown_fields,
        "unavailable_private_metrics": sorted(PRIVATE_METRICS),
    }
    return artifact_id, document


def import_evidence(
    study_root: Path,
    response_path: Path,
    *,
    reviewed_by: str,
    repository_root: Path,
    reviewed_at: str | None = None,
) -> list[Path]:
    """Import a Hermes-collected response into validated CM3 evidence.

    Requires an explicit human reviewer: CM4 evidence is never self-imported by
    the collecting worker (see docs/NICHE_INTELLIGENCE.md's CM4 boundary).
    """

    if not reviewed_by.strip():
        raise NicheValidationError(
            "importing public channel/video evidence requires an explicit human reviewer "
            "(--reviewed-by); CM4 evidence is never self-imported by the collecting worker"
        )
    repository_root = repository_root.resolve()
    study_root = study_root.resolve()
    baseline = validate_study(study_root, repository_root=repository_root)
    study_id = baseline.study["study_id"]
    channel_id = baseline.study["channel_id"]
    niche = baseline.study["scope"]["niche"]

    response = _load(response_path)
    for key in ("worker", "model", "prompt_version", "collected_at"):
        if not response.get(key):
            raise NicheValidationError(f"Hermes response is missing required field: {key}")

    report_path = study_root / "report.json"
    report = json.loads(json.dumps(baseline.report))
    previous_report_bytes = report_path.read_bytes()
    new_files: list[Path] = []
    created: list[Path] = []
    existing_ids = set(baseline.artifacts)

    for entry in response.get("channels", []):
        artifact_id, document = _channel_evidence_from_response(entry, response, study_id, channel_id, niche)
        if artifact_id in existing_ids:
            continue
        path = study_root / "evidence" / f"channel-{_slug(entry['source_id'])}.json"
        _write_json_atomic(path, document)
        new_files.append(path)
        relative = path.relative_to(study_root).as_posix()
        if relative not in report["components"]["channel_evidence"]:
            report["components"]["channel_evidence"].append(relative)
        existing_ids.add(artifact_id)
        created.append(path)

    for entry in response.get("videos", []):
        artifact_id, document = _video_evidence_from_response(entry, response, study_id, channel_id)
        if artifact_id in existing_ids:
            continue
        path = study_root / "evidence" / f"video-{_slug(entry['source_id'])}.json"
        _write_json_atomic(path, document)
        new_files.append(path)
        relative = path.relative_to(study_root).as_posix()
        if relative not in report["components"]["video_evidence"]:
            report["components"]["video_evidence"].append(relative)
        existing_ids.add(artifact_id)
        created.append(path)

    if not new_files:
        return []

    _write_json_atomic(report_path, report)
    _commit_or_rollback(
        study_root, repository_root=repository_root, expected_channel_id=channel_id,
        report_path=report_path, previous_report_bytes=previous_report_bytes, new_files=new_files,
    )

    _append_jsonl(
        repository_root / "channels" / channel_id / "intelligence" / "review-log.jsonl",
        {
            "reviewed_by": reviewed_by.strip(),
            "reviewed_at": _timestamp(reviewed_at),
            "study_id": study_id,
            "response_path": response_path.resolve().relative_to(repository_root).as_posix(),
            "response_sha256": hashlib.sha256(response_path.read_bytes()).hexdigest(),
            "artifact_ids": sorted(existing_ids - (set(baseline.artifacts))),
        },
    )
    return created


def _add_component(
    study_root: Path,
    *,
    repository_root: Path,
    category: str,
    artifact_id_prefix: str,
    key: str,
    document_without_ids: dict[str, Any],
) -> Path:
    repository_root = repository_root.resolve()
    study_root = study_root.resolve()
    baseline = validate_study(study_root, repository_root=repository_root)
    study_id = baseline.study["study_id"]
    channel_id = baseline.study["channel_id"]
    artifact_id = f"niche:{artifact_id_prefix}:{_slug(key)}"
    if artifact_id in baseline.artifacts:
        raise NicheValidationError(f"artifact already exists: {artifact_id}")

    document = {
        "schema_version": "1.0.0", "study_id": study_id, "channel_id": channel_id,
        "artifact_id": artifact_id,
        **document_without_ids,
    }
    directory = {
        "niche_observation": "observations", "niche_hypothesis": "hypotheses",
        "opportunity_proposal": "opportunities",
    }[document["artifact_type"]]
    path = study_root / directory / f"{_slug(key)}.json"
    if path.exists():
        raise NicheValidationError(f"artifact file already exists: {path}")

    report_path = study_root / "report.json"
    previous_report_bytes = report_path.read_bytes()
    report = json.loads(json.dumps(baseline.report))
    relative = path.relative_to(study_root).as_posix()
    report["components"][category].append(relative)

    _write_json_atomic(path, document)
    _write_json_atomic(report_path, report)
    _commit_or_rollback(
        study_root, repository_root=repository_root, expected_channel_id=channel_id,
        report_path=report_path, previous_report_bytes=previous_report_bytes, new_files=[path],
    )
    return path


def add_observation(
    study_root: Path,
    *,
    key: str,
    statement: str,
    observation_type: str,
    scope: str,
    basis: str,
    evidence_refs: list[str],
    confidence: float | None,
    limitations: list[str],
    repository_root: Path,
) -> Path:
    document = {
        "artifact_type": "niche_observation", "authority": "DESCRIPTIVE_OBSERVATION",
        "statement": statement, "observation_type": observation_type, "scope": scope, "basis": basis,
        "evidence_refs": evidence_refs, "confidence": confidence, "limitations": limitations,
        "created_by": _creation_provenance("engine.niche_intelligence.acquisition.add_observation"),
    }
    return _add_component(
        study_root, repository_root=repository_root, category="observations",
        artifact_id_prefix="observation", key=key, document_without_ids=document,
    )


def add_hypothesis(
    study_root: Path,
    *,
    key: str,
    statement: str,
    predicted_effect: str,
    applicable_context: str,
    observation_refs: list[str],
    competing_explanations: list[str],
    confidence: float | None,
    test_idea: str | None,
    repository_root: Path,
) -> Path:
    document = {
        "artifact_type": "niche_hypothesis", "authority": "UNAPPROVED_HYPOTHESIS",
        "statement": statement, "predicted_effect": predicted_effect, "applicable_context": applicable_context,
        "observation_refs": observation_refs, "competing_explanations": competing_explanations,
        "confidence": confidence, "test_idea": test_idea, "status": "ACTIVE",
        "created_by": _creation_provenance("engine.niche_intelligence.acquisition.add_hypothesis"),
    }
    return _add_component(
        study_root, repository_root=repository_root, category="hypotheses",
        artifact_id_prefix="hypothesis", key=key, document_without_ids=document,
    )


def add_opportunity(
    study_root: Path,
    *,
    key: str,
    observed_market: str,
    underrepresented: str,
    proposal: str,
    hypothesis_refs: list[str],
    evidence_refs: list[str],
    risks: list[str],
    confidence: float | None,
    repository_root: Path,
) -> Path:
    document = {
        "artifact_type": "opportunity_proposal", "authority": "PROPOSED_OPPORTUNITY",
        "observed_market": observed_market, "underrepresented": underrepresented, "proposal": proposal,
        "hypothesis_refs": hypothesis_refs, "evidence_refs": evidence_refs, "risks": risks,
        "confidence": confidence, "human_strategy_decision_required": True, "status": "PROPOSED",
        "created_by": _creation_provenance("engine.niche_intelligence.acquisition.add_opportunity"),
    }
    return _add_component(
        study_root, repository_root=repository_root, category="opportunity_proposals",
        artifact_id_prefix="opportunity", key=key, document_without_ids=document,
    )
