"""Write and attach human decisions to a channel's Foundation artifact."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from engine.channel import ChannelValidationError, validate_channel_package

from .validation import FoundationValidationError, validate_foundation


def _timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_yaml_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(value, handle, sort_keys=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _foundation_path(package_root: Path) -> Path:
    return package_root / "strategy" / "foundation.yaml"


def write_foundation(
    package_root: Path,
    repository_root: Path,
    *,
    audience_description: str,
    audience_demographics: str | None,
    promise: str,
    niche_primary: str,
    sub_niches: list[str],
    personality: list[str],
    education_entertainment_balance: str,
    differentiation: str,
    emotional_goal: str,
    content_boundaries: list[str],
    primary_format: str,
    deliberately_avoids: list[str],
) -> Path:
    """Draft a channel's Foundation document. Not yet advance-eligible until a decision is attached."""

    repository_root = repository_root.resolve()
    try:
        package = validate_channel_package(package_root.resolve(), repository_root)
    except ChannelValidationError as exc:
        raise FoundationValidationError(str(exc)) from exc
    channel_id = package.identity["id"]
    if primary_format not in package.identity["platform"]["formats"]:
        raise FoundationValidationError(
            f"primary_format {primary_format!r} is not among the channel's platform.formats"
        )

    document = {
        "schema_version": "1.0.0",
        "artifact_type": "channel_foundation",
        "channel_id": channel_id,
        "audience": {"description": audience_description, "demographics": audience_demographics},
        "promise": promise,
        "niche": {"primary": niche_primary, "sub_niches": sub_niches},
        "personality": personality,
        "education_entertainment_balance": education_entertainment_balance,
        "differentiation": differentiation,
        "emotional_goal": emotional_goal,
        "content_boundaries": content_boundaries,
        "primary_format": primary_format,
        "deliberately_avoids": deliberately_avoids,
        "decision_refs": [],
        "created_by": {
            "created_at": _timestamp(None), "creator": "MODEL_ASSISTED",
            "tool": "engine.foundation.acquisition.write_foundation", "version": "1.0.0",
        },
    }
    validate_foundation(document, expected_channel_id=channel_id)
    path = _foundation_path(package.root)
    _write_yaml_atomic(path, document)
    return path


def attach_foundation_decision(package_root: Path, repository_root: Path, *, decision_ref: str) -> Path:
    """Attach a real, resolvable human decision reference to the drafted Foundation."""

    if not decision_ref.strip():
        raise FoundationValidationError("attaching a foundation decision requires a non-empty decision_ref")
    repository_root = repository_root.resolve()
    try:
        package = validate_channel_package(package_root.resolve(), repository_root)
    except ChannelValidationError as exc:
        raise FoundationValidationError(str(exc)) from exc
    path = _foundation_path(package.root)
    if not path.is_file():
        raise FoundationValidationError(f"no drafted foundation exists yet: {path}")

    resolved = (repository_root / decision_ref).resolve()
    if not resolved.is_relative_to(repository_root) or not resolved.exists():
        raise FoundationValidationError(f"decision_ref does not resolve to an existing repository path: {decision_ref}")

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if decision_ref not in document["decision_refs"]:
        document["decision_refs"] = [*document["decision_refs"], decision_ref]
    validate_foundation(document, expected_channel_id=package.identity["id"])
    _write_yaml_atomic(path, document)
    return path
