"""Plan, produce, review, and freeze one channel Pilot."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from engine.channel import ChannelValidationError, validate_channel_package
from engine.library import list_components
from engine.production import (
    ProductionIncompleteError,
    production_revision,
    production_snapshot,
    require_complete,
)

from .release import (
    build_release_manifest,
    pointer_path,
    release_path,
    substantive_manifest,
)
from .validation import PilotValidationError, validate_pilot


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


def pilot_path(package_root: Path, pilot_id: str) -> Path:
    return package_root / "pilots" / pilot_id / "pilot.json"


def _load_package(package_root: Path, repository_root: Path):
    try:
        return validate_channel_package(package_root.resolve(), repository_root.resolve())
    except ChannelValidationError as exc:
        raise PilotValidationError(str(exc)) from exc


def _load_pilot(package_root: Path, pilot_id: str) -> tuple[Path, dict[str, Any]]:
    path = pilot_path(package_root, pilot_id)
    if not path.is_file():
        raise PilotValidationError(f"no pilot exists yet: {path}")
    return path, json.loads(path.read_text(encoding="utf-8"))


def plan_pilot(
    package_root: Path,
    repository_root: Path,
    *,
    pilot_id: str,
    topic: str,
    target_duration_seconds: float,
    integration_goals: list[str],
    no_reusable_components: bool = False,
) -> Path:
    package = _load_package(package_root, repository_root)
    path = pilot_path(package.root, pilot_id)
    if path.is_file():
        raise PilotValidationError(f"pilot already exists: {path}")
    document = {
        "schema_version": "1.0.0", "artifact_type": "pilot",
        "artifact_id": f"pilot:{package.identity['id']}:{pilot_id}",
        "channel_id": package.identity["id"], "pilot_id": pilot_id,
        "plan": {
            "topic": topic, "format": "SHORTS", "target_duration_seconds": target_duration_seconds,
            "integration_goals": integration_goals,
            "no_reusable_components": no_reusable_components,
        },
        "production": {
            "script_ref": None, "voiceover_ref": None, "voice_name": None,
            "scene_candidate_manifest_refs": [],
            "evaluation_result_refs": [], "render_ref": None, "production_log_ref": None,
            "revision": None,
        },
        "review": {
            "decision": None, "decided_by": None, "decided_at": None, "rationale": None,
            "decision_ref": None, "revise_target": None, "critic_summary_refs": [],
            "rev_id": None, "production_snapshot": None, "history": [],
        },
        "freeze": {
            "frozen": False, "previous_channel_version": None, "new_channel_version": None,
            "frozen_at": None, "frozen_by": None, "decision_ref": None,
        },
        "created_by": {
            "created_at": _timestamp(None), "creator": "MODEL_ASSISTED",
            "tool": "engine.pilot.pilot.plan_pilot", "version": "1.0.0",
        },
    }
    validate_pilot(document, repository_root=repository_root, expected_channel_id=package.identity["id"])
    _write_json_atomic(path, document)
    return path


def _evidence_ref(repository_root: Path, relative_path: str) -> dict[str, Any]:
    resolved = (repository_root / relative_path).resolve()
    if not resolved.is_relative_to(repository_root) or not resolved.is_file():
        raise PilotValidationError(f"evidence file does not exist: {relative_path}")
    document = json.loads(resolved.read_text(encoding="utf-8"))
    return {"artifact_id": document["artifact_id"], "path": relative_path, "sha256": _sha256(resolved)}


def record_production(
    package_root: Path,
    repository_root: Path,
    pilot_id: str,
    *,
    script_ref: str | None = None,
    voiceover_ref: str | None = None,
    voice: str | None = None,
    scene_candidate_manifest_paths: list[str] = (),
    evaluation_result_paths: list[str] = (),
    render_ref: str | None = None,
    production_log_ref: str | None = None,
) -> Path:
    package = _load_package(package_root, repository_root)
    path, document = _load_pilot(package.root, pilot_id)
    repository_root = repository_root.resolve()
    production = document["production"]
    if script_ref is not None:
        production["script_ref"] = script_ref
    if voiceover_ref is not None:
        production["voiceover_ref"] = voiceover_ref
        # One voice per channel: narration always arrives with its voice
        # named, and a second voice under one production is refused.
        if not (voice or "").strip():
            raise PilotValidationError(
                f"recording narration for pilot {pilot_id} requires --voice (one voice per channel)"
            )
        current = production.get("voice_name")
        if current is not None and current != voice.strip():
            raise PilotValidationError(
                f"pilot {pilot_id} already uses voice {current!r}; refusing second voice {voice.strip()!r}"
            )
        production["voice_name"] = voice.strip()
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
    new_revision = production_revision(production, repository_root=repository_root)
    old_revision = production.get("revision")
    production["revision"] = new_revision
    if old_revision is not None and new_revision != old_revision:
        if document["review"].get("decision") == "GO":
            # Production changed under a GO: the approval no longer describes
            # this content. Archive it and restore "needs review".
            document["review"] = _reset_review(document["review"])
        if document["freeze"].get("frozen"):
            # A frozen release pins exact bytes (preserved on disk under
            # releases/); changed content is no longer that release.
            document["freeze"] = {
                "frozen": False, "previous_channel_version": None,
                "new_channel_version": None, "frozen_at": None,
                "frozen_by": None, "decision_ref": None,
            }
    validate_pilot(document, repository_root=repository_root, expected_channel_id=package.identity["id"])
    _write_json_atomic(path, document)
    return path


def _archive_entry(review: dict[str, Any]) -> dict[str, Any]:
    """Copy a superseded review without its own history (kept alongside)."""
    return {key: value for key, value in review.items() if key != "history"}


def _reset_review(review: dict[str, Any]) -> dict[str, Any]:
    history = list(review.get("history") or [])
    history.append(_archive_entry(review))
    return {
        "decision": None, "decided_by": None, "decided_at": None, "rationale": None,
        "decision_ref": None, "revise_target": None,
        "critic_summary_refs": review.get("critic_summary_refs", []),
        "rev_id": None, "production_snapshot": None, "history": history,
    }


def record_review(
    package_root: Path,
    repository_root: Path,
    pilot_id: str,
    *,
    decision: str,
    decided_by: str,
    rationale: str,
    decision_ref: str,
    revise_target: str | None = None,
    decided_at: str | None = None,
    strict_media: bool = False,
) -> Path:
    if not decision_ref.strip():
        raise PilotValidationError("recording a pilot review decision requires a non-empty decision_ref")
    package = _load_package(package_root, repository_root)
    path, document = _load_pilot(package.root, pilot_id)
    repository_root = repository_root.resolve()
    resolved = (repository_root / decision_ref).resolve()
    if not resolved.is_relative_to(repository_root) or not resolved.exists():
        raise PilotValidationError(f"decision_ref does not resolve to an existing repository path: {decision_ref}")
    from engine.decisions import DecisionError, validate_record_file

    try:
        marked = validate_record_file(resolved, expected_kind=None)
    except DecisionError as exc:
        raise PilotValidationError(str(exc)) from exc
    if marked and marked.get("decision_record") == "review":
        if marked.get("decision") != decision:
            raise PilotValidationError(
                f"decision_ref records {marked.get('decision')!r} but the review says {decision!r}"
            )
        current_rev = production_revision(document["production"], repository_root=repository_root)
        if marked.get("rev") != current_rev:
            raise PilotValidationError(
                f"decision_ref approves rev {marked.get('rev')!r} but the production is "
                f"{current_rev!r}"
            )

    prior = document["review"]
    history = list(prior.get("history") or [])
    if prior.get("decision") is not None:
        history.append(_archive_entry(prior))
    current_rev = production_revision(document["production"], repository_root=repository_root)
    document["production"]["revision"] = current_rev
    document["review"] = {
        "decision": decision, "decided_by": decided_by.strip(), "decided_at": _timestamp(decided_at),
        "rationale": rationale, "decision_ref": decision_ref, "revise_target": revise_target,
        "critic_summary_refs": prior.get("critic_summary_refs", []),
        "rev_id": current_rev,
        "production_snapshot": production_snapshot(document["production"], repository_root=repository_root),
        "history": history,
    }
    if decision == "GO":
        try:
            require_complete(
                document["production"], repository_root=repository_root,
                label=f"pilot {pilot_id}", strict_media=strict_media,
            )
        except ProductionIncompleteError as exc:
            raise PilotValidationError(str(exc)) from exc
    validate_pilot(document, repository_root=repository_root, expected_channel_id=package.identity["id"])
    _write_json_atomic(path, document)
    return path


def freeze_pilot(
    package_root: Path,
    repository_root: Path,
    pilot_id: str,
    *,
    new_channel_version: str,
    frozen_by: str,
    force: bool = False,
) -> Path:
    package = _load_package(package_root, repository_root)
    path, document = _load_pilot(package.root, pilot_id)
    if document["review"]["decision"] != "GO":
        raise PilotValidationError("a pilot can only be frozen after a GO review decision")
    repository_root = repository_root.resolve()
    try:
        require_complete(
            document["production"], repository_root=repository_root,
            label=f"pilot {pilot_id}",
        )
    except ProductionIncompleteError as exc:
        raise PilotValidationError(str(exc)) from exc
    current_rev = production_revision(document["production"], repository_root=repository_root)
    if document["review"].get("rev_id") != current_rev:
        raise PilotValidationError(
            f"pilot {pilot_id} production changed since the GO review "
            f"(reviewed {document['review'].get('rev_id')}, now {current_rev}); "
            "record a new review before freezing"
        )

    previous_version = package.identity["version"]
    frozen_at = _timestamp(None)
    approved = list_components(
        repository_root, scope="CHANNEL",
        channel_id=package.identity["id"], status="approved",
    )
    manifest = build_release_manifest(
        channel_id=package.identity["id"], version=new_channel_version,
        previous_version=previous_version, pilot_id=pilot_id,
        pilot_rev_id=current_rev,
        production_snapshot=production_snapshot(document["production"], repository_root=repository_root),
        package_root=package.root, repository_root=repository_root,
        renderer=package.identity.get("production", {}).get("renderer", "unknown"),
        approved_components=approved, frozen_by=frozen_by.strip(), frozen_at=frozen_at,
    )
    if (
        document["freeze"]["frozen"] and not force
        and new_channel_version != document["freeze"]["new_channel_version"]
    ):
        raise PilotValidationError(
            f"pilot {pilot_id} is already frozen at version "
            f"{document['freeze']['new_channel_version']}; pass force=True to re-freeze deliberately"
        )
    # The same version string must always describe the same release.
    # Retrying an interrupted freeze lands here and completes it; evolving
    # content under an existing version needs a new version or force=True.
    existing_path = release_path(package.root, new_channel_version)
    if existing_path.is_file() and not force:
        existing = json.loads(existing_path.read_text(encoding="utf-8"))
        # The recorded upgrade path wins: a retry after the version bump
        # already landed necessarily sees a different "current" version.
        candidate = dict(manifest)
        candidate["previous_version"] = existing.get("previous_version")
        if substantive_manifest(existing) != substantive_manifest(candidate):
            raise PilotValidationError(
                f"version {new_channel_version} is already released with different content; "
                "freeze as a new version or pass force=True to replace it deliberately"
            )

    document["freeze"] = {
        "frozen": True, "previous_channel_version": previous_version, "new_channel_version": new_channel_version,
        "frozen_at": frozen_at, "frozen_by": frozen_by.strip(),
        "decision_ref": document["review"]["decision_ref"],
    }
    validate_pilot(document, repository_root=repository_root, expected_channel_id=package.identity["id"])
    _write_json_atomic(release_path(package.root, new_channel_version), manifest)
    _write_json_atomic(path, document)
    write_channel_version(package.root, repository_root, new_channel_version)
    _write_json_atomic(pointer_path(package.root), _release_pointer(
        package.identity["id"], new_channel_version, pilot_id, current_rev, frozen_at,
    ))
    return path


def _release_pointer(
    channel_id: str, version: str, pilot_id: str, pilot_rev_id: str, updated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "channel_id": channel_id,
        "version": version,
        "release": f"channels/{channel_id}/releases/{version}.json",
        "pilot_id": pilot_id,
        "pilot_rev_id": pilot_rev_id,
        "updated_at": updated_at,
    }


def write_channel_version(package_root: Path, repository_root: Path, new_version: str) -> Path:
    package = _load_package(package_root, repository_root)
    identity = dict(package.identity)
    identity["version"] = new_version
    identity_path = package.root / "channel.yaml"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".channel.yaml.", suffix=".tmp", dir=identity_path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(identity, handle, sort_keys=False)
        os.replace(temporary, identity_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    try:
        validate_channel_package(package.root, repository_root)
    except ChannelValidationError as exc:
        raise PilotValidationError(str(exc)) from exc
    return identity_path
