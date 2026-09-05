"""Register, review, and list code-first asset components (the starter visual library)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.channel import ChannelValidationError, validate_channel_package

from .validation import LibraryValidationError, validate_component, validate_component_review


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise LibraryValidationError(f"refusing to overwrite existing record {path}")


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise LibraryValidationError("component name must contain at least one letter or number")
    return slug


def _registry_root(repository_root: Path, *, scope: str, channel_id: str | None) -> Path:
    if scope == "ENGINE":
        return repository_root / "engine" / "library" / "registry"
    return repository_root / "channels" / channel_id / "assets" / "registry"


def register_component(
    repository_root: Path,
    *,
    scope: str,
    channel_id: str | None,
    category: str,
    name: str,
    description: str,
    renderer: str,
    source_kind: str,
    source_path: str,
    exports: list[str],
    interface: dict[str, Any],
    justification: str,
    produced_for_pilot_ref: str | None,
) -> Path:
    repository_root = repository_root.resolve()
    if scope == "CHANNEL":
        if not channel_id:
            raise LibraryValidationError("CHANNEL-scope components require a channel_id")
        try:
            validate_channel_package(repository_root / "channels" / channel_id, repository_root)
        except ChannelValidationError as exc:
            raise LibraryValidationError(str(exc)) from exc
        owner = channel_id
    elif scope == "ENGINE":
        if channel_id:
            raise LibraryValidationError("ENGINE-scope components must not set channel_id")
        owner = "engine"
    else:
        raise LibraryValidationError(f"unknown component scope: {scope!r}")

    component_id = f"component:{owner}:{_slug(name)}"
    record = {
        "schema_version": "1.0.0", "artifact_type": "asset_component", "component_id": component_id,
        "scope": scope, "channel_id": channel_id, "category": category, "name": name.strip(),
        "description": description, "renderer": renderer,
        "source": {"kind": source_kind, "path": source_path, "exports": exports},
        "interface": interface, "justification": justification,
        "produced_for_pilot_ref": produced_for_pilot_ref, "status": "experimental", "review_ids": [],
        "created_by": {
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "creator": "MODEL_ASSISTED",
            "tool": "engine.library.registry.register_component", "version": "1.0.0",
        },
    }
    warnings = validate_component(record, repository_root=repository_root)
    for warning in warnings:
        print(f"WARNING: {warning}")
    path = _registry_root(repository_root, scope=scope, channel_id=channel_id) / f"{_slug(name)}.json"
    _write_new(path, _canonical_bytes(record))
    return path


def review_component(
    repository_root: Path,
    component_path: Path,
    *,
    decision: str,
    reviewer: str,
    reason: str,
    created_at: str,
    human_confirmed: bool,
) -> dict[str, Any]:
    if not human_confirmed:
        raise LibraryValidationError("asset component classification requires an explicit human confirmation")
    try:
        record_bytes = component_path.read_bytes()
        record = json.loads(record_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise LibraryValidationError(f"cannot read component record {component_path}: {exc}") from exc
    validate_component(record)
    target_sha256 = hashlib.sha256(record_bytes).hexdigest()
    seed = {
        "schema_version": "1.0.0", "artifact_type": "asset_component_review", "component_id": record["component_id"],
        "target_sha256": target_sha256, "decision": decision, "reviewer": reviewer.strip(),
        "reason": reason.strip(), "created_at": created_at,
    }
    review_id = f"component-review:{hashlib.sha256(_canonical_bytes(seed)).hexdigest()[:16]}"
    review = {**seed, "review_id": review_id}
    validate_component_review(review)
    reviews_dir = component_path.parent.parent / "reviews"
    _write_new(reviews_dir / f"{review_id.removeprefix('component-review:')}.json", _canonical_bytes(review))

    updated = dict(record)
    updated["status"] = {"approved": "approved", "deprecated": "deprecated"}.get(decision, "experimental")
    updated["review_ids"] = [*record["review_ids"], review_id]
    validate_component(updated)
    _write_atomic(component_path, _canonical_bytes(updated))
    return review


def list_components(
    repository_root: Path,
    *,
    scope: str | None = None,
    category: str | None = None,
    status: str | None = None,
    channel_id: str | None = None,
) -> list[dict[str, Any]]:
    repository_root = repository_root.resolve()
    roots: list[Path] = []
    if scope in (None, "ENGINE"):
        roots.append(repository_root / "engine" / "library" / "registry")
    if scope in (None, "CHANNEL"):
        channels_root = repository_root / "channels"
        if channel_id:
            roots.append(channels_root / channel_id / "assets" / "registry")
        elif channels_root.is_dir():
            roots.extend(path / "assets" / "registry" for path in sorted(channels_root.iterdir()) if path.is_dir())
    results = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if category is not None and record["category"] != category:
                continue
            if status is not None and record["status"] != status:
                continue
            results.append(record)
    return results
