"""Plan, produce, and review one channel Episode. No freeze step: episode production never
bumps the channel's version — that stays reserved for deliberate DNA/identity changes (see
`engine/pilot/pilot.py`'s `freeze_pilot`).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.channel import ChannelValidationError, validate_channel_package
from engine.production import ProductionIncompleteError, require_complete

from .validation import EpisodeValidationError, validate_episode


def _timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
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


def episode_path(package_root: Path, episode_id: str) -> Path:
    return package_root / "episodes" / episode_id / "episode.json"


def _load_package(package_root: Path, repository_root: Path):
    try:
        return validate_channel_package(package_root.resolve(), repository_root.resolve())
    except ChannelValidationError as exc:
        raise EpisodeValidationError(str(exc)) from exc


def _load_episode(package_root: Path, episode_id: str) -> tuple[Path, dict[str, Any]]:
    path = episode_path(package_root, episode_id)
    if not path.is_file():
        raise EpisodeValidationError(f"no episode exists yet: {path}")
    return path, json.loads(path.read_text(encoding="utf-8"))


def plan_episode(
    package_root: Path,
    repository_root: Path,
    *,
    episode_id: str,
    topic: str,
    target_duration_seconds: float,
    opportunity_ref: str | None = None,
) -> Path:
    package = _load_package(package_root, repository_root)
    path = episode_path(package.root, episode_id)
    if path.is_file():
        raise EpisodeValidationError(f"episode already exists: {path}")
    document = {
        "schema_version": "1.0.0", "artifact_type": "episode",
        "artifact_id": f"episode:{package.identity['id']}:{episode_id}",
        "channel_id": package.identity["id"], "episode_id": episode_id,
        "plan": {
            "topic": topic, "format": "SHORTS", "target_duration_seconds": target_duration_seconds,
            "opportunity_ref": opportunity_ref,
        },
        "production": {
            "script_ref": None, "voiceover_ref": None, "scene_candidate_manifest_refs": [],
            "evaluation_result_refs": [], "render_ref": None, "production_log_ref": None,
        },
        "review": {
            "decision": None, "decided_by": None, "decided_at": None, "rationale": None, "decision_ref": None,
        },
        "created_by": {
            "created_at": _timestamp(None), "creator": "MODEL_ASSISTED",
            "tool": "engine.episode.episode.plan_episode", "version": "1.0.0",
        },
    }
    validate_episode(document, repository_root=repository_root, expected_channel_id=package.identity["id"])
    _write_json_atomic(path, document)
    return path


def _evidence_ref(repository_root: Path, relative_path: str) -> dict[str, Any]:
    resolved = (repository_root / relative_path).resolve()
    if not resolved.is_relative_to(repository_root) or not resolved.is_file():
        raise EpisodeValidationError(f"evidence file does not exist: {relative_path}")
    document = json.loads(resolved.read_text(encoding="utf-8"))
    return {"artifact_id": document["artifact_id"], "path": relative_path, "sha256": _sha256(resolved)}


def record_production(
    package_root: Path,
    repository_root: Path,
    episode_id: str,
    *,
    script_ref: str | None = None,
    voiceover_ref: str | None = None,
    scene_candidate_manifest_paths: list[str] = (),
    evaluation_result_paths: list[str] = (),
    render_ref: str | None = None,
    production_log_ref: str | None = None,
) -> Path:
    package = _load_package(package_root, repository_root)
    path, document = _load_episode(package.root, episode_id)
    repository_root = repository_root.resolve()
    production = document["production"]
    if script_ref is not None:
        production["script_ref"] = script_ref
    if voiceover_ref is not None:
        production["voiceover_ref"] = voiceover_ref
    if render_ref is not None:
        production["render_ref"] = render_ref
    if production_log_ref is not None:
        production["production_log_ref"] = production_log_ref
    existing_scene_ids = {ref["artifact_id"] for ref in production["scene_candidate_manifest_refs"]}
    for relative_path in scene_candidate_manifest_paths:
        ref = _evidence_ref(repository_root, relative_path)
        if ref["artifact_id"] not in existing_scene_ids:
            production["scene_candidate_manifest_refs"].append(ref)
            existing_scene_ids.add(ref["artifact_id"])
    existing_eval_ids = {ref["artifact_id"] for ref in production["evaluation_result_refs"]}
    for relative_path in evaluation_result_paths:
        ref = _evidence_ref(repository_root, relative_path)
        if ref["artifact_id"] not in existing_eval_ids:
            production["evaluation_result_refs"].append(ref)
            existing_eval_ids.add(ref["artifact_id"])
    validate_episode(document, repository_root=repository_root, expected_channel_id=package.identity["id"])
    _write_json_atomic(path, document)
    return path


def record_review(
    package_root: Path,
    repository_root: Path,
    episode_id: str,
    *,
    decision: str,
    decided_by: str,
    rationale: str,
    decision_ref: str,
    decided_at: str | None = None,
) -> Path:
    if not decision_ref.strip():
        raise EpisodeValidationError("recording an episode review decision requires a non-empty decision_ref")
    package = _load_package(package_root, repository_root)
    path, document = _load_episode(package.root, episode_id)
    repository_root = repository_root.resolve()
    resolved = (repository_root / decision_ref).resolve()
    if not resolved.is_relative_to(repository_root) or not resolved.exists():
        raise EpisodeValidationError(f"decision_ref does not resolve to an existing repository path: {decision_ref}")

    document["review"] = {
        "decision": decision, "decided_by": decided_by.strip(), "decided_at": _timestamp(decided_at),
        "rationale": rationale, "decision_ref": decision_ref,
    }
    if decision == "GO":
        try:
            require_complete(
                document["production"], repository_root=repository_root,
                label=f"episode {episode_id}",
            )
        except ProductionIncompleteError as exc:
            raise EpisodeValidationError(str(exc)) from exc
    validate_episode(document, repository_root=repository_root, expected_channel_id=package.identity["id"])
    _write_json_atomic(path, document)
    return path
