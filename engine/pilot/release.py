"""Immutable channel releases: one manifest per frozen version, one pointer.

A release manifest pins the exact approved dependencies behind a channel
version: pilot revision, production snapshot, DNA/identity seeds, approved
components, and renderer. The ``current-release.json`` pointer switches
atomically, so a crash between the pilot write and the version bump is
recoverable: retrying the same version completes the same release instead
of creating another one.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def releases_root(package_root: Path) -> Path:
    return package_root / "releases"


def release_path(package_root: Path, version: str) -> Path:
    return releases_root(package_root) / f"{version}.json"


def pointer_path(package_root: Path) -> Path:
    return package_root / "current-release.json"


def _file_digest(package_root: Path, repository_root: Path, relative: str | None) -> dict[str, Any]:
    if not relative:
        return {"path": None, "sha256": None}
    resolved = (repository_root / relative).resolve()
    if not resolved.is_relative_to(repository_root) or not resolved.is_file():
        return {"path": relative, "sha256": None}
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return {"path": relative, "sha256": digest.hexdigest()}


def _seed_rel(package_root: Path, *parts: str) -> str | None:
    candidate = package_root.joinpath(*parts)
    if not candidate.is_file():
        return None
    return candidate.relative_to(package_root).as_posix()


def build_release_manifest(
    *,
    channel_id: str,
    version: str,
    previous_version: str,
    pilot_id: str,
    pilot_rev_id: str,
    production_snapshot: dict[str, Any],
    package_root: Path,
    repository_root: Path,
    renderer: str,
    approved_components: list[dict[str, Any]],
    frozen_by: str,
    frozen_at: str,
) -> dict[str, Any]:
    """Assemble the release manifest. No timestamps besides ``frozen_at``."""
    channel_rel = f"channels/{channel_id}"
    seeds = {}
    for key, parts in (
        ("script_dna", ("script", "script-dna.yaml")),
        ("visual_dna_seed", ("design", "visual-dna-seed.yaml")),
        ("motion_dna_seed", ("motion", "motion-dna-seed.yaml")),
        ("channel_identity", ("identity", "channel-identity.yaml")),
    ):
        relative = _seed_rel(package_root, *parts)
        seeds[key] = _file_digest(
            package_root, repository_root,
            f"{channel_rel}/{relative}" if relative else None,
        )
    return {
        "schema_version": "1.0.0",
        "artifact_type": "release_manifest",
        "channel_id": channel_id,
        "version": version,
        "previous_version": previous_version,
        "pilot_id": pilot_id,
        "pilot_rev_id": pilot_rev_id,
        "production": production_snapshot,
        "dependencies": {
            **seeds,
            "components": [
                {"component_id": component.get("component_id"), "status": component.get("status")}
                for component in approved_components
            ],
        },
        "renderer": renderer,
        "frozen_by": frozen_by,
        "frozen_at": frozen_at,
    }


def substantive_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """The manifest minus volatile fields, for idempotent-retry comparison."""
    return {key: value for key, value in manifest.items() if key != "frozen_at"}
