"""Shared deterministic helpers for the Phase 1 command-line tools."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
TOOL_VERSION = "1.0.0"

# Only the Stage-9 renderer-evidence path is live. Legacy entries
# (source_manifest, transcripts, shots, evaluation_request, …) were pruned:
# they pointed at schema files that do not exist under schemas/, so any
# schema_for() call for them failed with a confusing file-read error
# instead of a clean unknown-type error. See docs/RENDER_CONTRACT.md.
ARTIFACT_SCHEMAS = {
    "scene_candidate_manifest": "scene_candidate_manifest.schema.json",
    "evaluation_contract": "evaluation_contract.schema.json",
    "critic_assessment": "critic_assessment.schema.json",
    "evaluation_result": "evaluation_result.schema.json",
}


class ChannelMakerError(RuntimeError):
    """Expected user-facing pipeline failure."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChannelMakerError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ChannelMakerError(f"{path}: top-level JSON value must be an object")
    return value


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(canonical_json_bytes(value))
    temporary.replace(path)


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ChannelMakerError(f"cannot read YAML {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ChannelMakerError(f"{path}: top-level YAML value must be a mapping")
    return value


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-._")
    if not slug:
        raise ChannelMakerError(f"cannot derive an ID from {value!r}")
    return slug


def command_version(command: str) -> str:
    try:
        result = subprocess.run([command, "-version"], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ChannelMakerError(f"required command {command!r} is unavailable: {exc}") from exc
    first_line = (result.stdout or result.stderr).splitlines()
    if not first_line:
        raise ChannelMakerError(f"required command {command!r} returned no version")
    return first_line[0].strip()


def run_command(args: list[str], *, binary: bool = False) -> bytes | str:
    try:
        result = subprocess.run(args, check=True, capture_output=True, text=not binary)
    except OSError as exc:
        raise ChannelMakerError(f"cannot execute {args[0]!r}: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if binary and isinstance(exc.stderr, bytes) else exc.stderr
        raise ChannelMakerError(f"command failed ({exc.returncode}): {' '.join(args)}\n{stderr or ''}".rstrip()) from exc
    return result.stdout


def schema_for(artifact_type: str) -> dict[str, Any]:
    filename = ARTIFACT_SCHEMAS.get(artifact_type)
    if filename is None:
        raise ChannelMakerError(f"unknown artifact_type {artifact_type!r}")
    return load_json(SCHEMA_DIR / filename)


def schema_errors(record: dict[str, Any]) -> list[str]:
    artifact_type = record.get("artifact_type")
    if not isinstance(artifact_type, str):
        return ["artifact_type is required and must be a string"]
    try:
        validator = Draft202012Validator(schema_for(artifact_type), format_checker=FormatChecker())
    except Exception as exc:  # schema faults are fatal and should be visible
        return [f"cannot load schema for {artifact_type}: {exc}"]
    errors: list[str] = []
    for error in sorted(validator.iter_errors(record), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{location}: {error.message}")
    return errors


def semantic_errors(record: dict[str, Any], taxonomies: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    artifact_type = record.get("artifact_type")

    if artifact_type == "transcript":
        previous_end = -1.0
        seen: set[str] = set()
        for segment in record.get("segments", []):
            start = segment.get("start_s")
            end = segment.get("end_s")
            segment_id = segment.get("segment_id")
            if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                if end <= start:
                    errors.append(f"segment {segment_id}: end_s must be greater than start_s")
                if start < previous_end - 1e-6:
                    errors.append(f"segment {segment_id}: segments must be ordered and non-overlapping")
                previous_end = max(previous_end, end)
            if segment_id in seen:
                errors.append(f"duplicate transcript segment ID {segment_id}")
            seen.add(segment_id)

    if artifact_type == "shot_measurement":
        start = record.get("start_s")
        end = record.get("end_s")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            if end <= start:
                errors.append("end_s must be greater than start_s")
            measured = record.get("measurement", {}).get("duration_s")
            if isinstance(measured, (int, float)) and abs(measured - (end - start)) > 0.002:
                errors.append("measurement.duration_s must equal end_s - start_s within 2 ms")
            for frame in record.get("keyframes", []):
                timestamp = frame.get("timestamp_s")
                if isinstance(timestamp, (int, float)) and not (start <= timestamp <= end):
                    errors.append(f"keyframe {frame.get('frame_id')}: timestamp is outside the shot interval")
        fractions = [item.get("fraction") for item in record.get("measurement", {}).get("dominant_colors", [])]
        if fractions and all(isinstance(value, (int, float)) for value in fractions) and sum(fractions) > 1.001:
            errors.append("dominant color fractions must not sum above 1")

    if artifact_type == "shot_interpretation" and taxonomies:
        vocabulary = taxonomies.get("taxonomies", {})
        for claim in record.get("claims", []):
            claim_type = claim.get("claim_type")
            value = claim.get("value")
            allowed = vocabulary.get(claim_type)
            if isinstance(allowed, list) and value not in allowed:
                errors.append(f"claim {claim.get('claim_id')}: unknown {claim_type} value {value!r}; record a schema gap")
            for evidence in claim.get("evidence", []):
                start = evidence.get("start_s")
                end = evidence.get("end_s")
                if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end <= start:
                    errors.append(f"claim {claim.get('claim_id')}: evidence end_s must exceed start_s")

    if artifact_type == "scene_candidate_manifest":
        evidence_ids = [item.get("evidence_id") for item in record.get("artifacts", [])]
        if len(evidence_ids) != len(set(evidence_ids)):
            errors.append("candidate artifact evidence_id values must be unique")

    if artifact_type == "evaluation_contract":
        dimensions = record.get("dimensions", [])
        dimension_ids = [item.get("dimension_id") for item in dimensions]
        if len(dimension_ids) != len(set(dimension_ids)):
            errors.append("evaluation dimension_id values must be unique")
        requirement_ids: list[Any] = []
        total_points = 0
        for dimension in dimensions:
            requirements = dimension.get("requirements", [])
            points = sum(item.get("points", 0) for item in requirements if isinstance(item.get("points"), int))
            if points != dimension.get("points"):
                errors.append(
                    f"dimension {dimension.get('dimension_id')}: requirement points must sum to dimension points"
                )
            total_points += dimension.get("points", 0) if isinstance(dimension.get("points"), int) else 0
            requirement_ids.extend(item.get("requirement_id") for item in requirements)
        if total_points != 100:
            errors.append("evaluation contract dimension points must sum to exactly 100")
        if len(requirement_ids) != len(set(requirement_ids)):
            errors.append("evaluation requirement_id values must be unique across the contract")
        gate_ids = [item.get("gate_id") for item in record.get("hard_gates", [])]
        if len(gate_ids) != len(set(gate_ids)):
            errors.append("evaluation gate_id values must be unique")
        if record.get("scope") == "scene_specific" and not record.get("scene_id"):
            errors.append("scene_specific evaluation contracts require scene_id")
        thresholds = record.get("thresholds", {})
        if thresholds.get("pass", 0) <= thresholds.get("needs_revision", 0):
            errors.append("evaluation pass threshold must exceed needs_revision threshold")

    if artifact_type == "critic_assessment":
        requirement_ids = [item.get("requirement_id") for item in record.get("requirement_findings", [])]
        if len(requirement_ids) != len(set(requirement_ids)):
            errors.append("critic requirement findings must have unique requirement_id values")
        gate_ids = [item.get("gate_id") for item in record.get("gate_findings", [])]
        if len(gate_ids) != len(set(gate_ids)):
            errors.append("critic gate findings must have unique gate_id values")
        for finding in record.get("requirement_findings", []) + record.get("gate_findings", []):
            evidence = finding.get("evidence", [])
            finding_id = finding.get("requirement_id") or finding.get("gate_id")
            if finding.get("outcome") == "not_assessable" and evidence:
                errors.append(f"finding {finding_id}: not_assessable cannot cite evidence")
            if finding.get("outcome") != "not_assessable" and not evidence:
                errors.append(f"finding {finding_id}: assessed outcomes require evidence")

    if artifact_type == "evaluation_result":
        dimension_scores = record.get("dimension_scores", [])
        awarded = sum(item.get("awarded_points", 0) for item in dimension_scores)
        if abs(awarded - record.get("score_100", -1)) > 0.001:
            errors.append("evaluation result score_100 must equal the sum of dimension awarded_points")
        if record.get("authority") != "advisory_only":
            errors.append("evaluation results must remain advisory_only")

    forbidden = _find_value(record, "human_approved")
    if forbidden and artifact_type != "approved_rule":
        errors.append("human_approved may exist only in a separately authenticated approved_rule artifact")
    return errors


def validate_record(record: dict[str, Any], taxonomies: dict[str, Any] | None = None) -> list[str]:
    return schema_errors(record) + semantic_errors(record, taxonomies)


def _find_value(value: Any, target: str) -> bool:
    if value == target:
        return True
    if isinstance(value, dict):
        return any(_find_value(item, target) for item in value.values())
    if isinstance(value, list):
        return any(_find_value(item, target) for item in value)
    return False


def require_valid(record: dict[str, Any], *, label: str = "record") -> None:
    taxonomies_path = ROOT / "config" / "taxonomies.yaml"
    taxonomies = load_yaml(taxonomies_path) if taxonomies_path.is_file() else None
    errors = validate_record(record, taxonomies)
    if errors:
        raise ChannelMakerError(f"invalid {label}:\n" + "\n".join(f"- {error}" for error in errors))


def existing_json_files(paths: Iterable[Path]) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        if path.is_file() and path.suffix.lower() == ".json":
            files.add(path)
        elif path.is_dir():
            files.update(item for item in path.rglob("*.json") if item.is_file())
    return sorted(files)
