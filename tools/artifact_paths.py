"""Resolve portable artifact locations and explicitly mapped legacy paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


class ArtifactPathError(RuntimeError):
    """An artifact location is invalid, ambiguous, or unavailable."""


@dataclass(frozen=True)
class ResolvedArtifact:
    path: Path
    legacy_rebased: bool
    original: str | dict[str, str]


def _relative_parts(value: str) -> tuple[str, ...]:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ArtifactPathError(f"artifact location requires a normalized relative path: {value!r}")
    return path.parts


class ArtifactPathResolver:
    """Resolve logical roots without basename searches or implicit guessing."""

    def __init__(
        self,
        repository_root: Path,
        *,
        config: dict[str, Any] | None = None,
        external_roots: dict[str, Path] | None = None,
    ) -> None:
        self.repository_root = repository_root.resolve()
        if config is None:
            config_path = self.repository_root / "config" / "artifact_roots.yaml"
            if config_path.is_file():
                loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    raise ArtifactPathError(f"artifact root config must be a mapping: {config_path}")
                config = loaded
            else:
                config = {"schema_version": "1.0.0", "roots": {"repo": {"kind": "repository"}}, "legacy_rebases": []}
        if config.get("schema_version") != "1.0.0":
            raise ArtifactPathError("unsupported artifact root config schema_version")
        roots = config.get("roots")
        if not isinstance(roots, dict) or "repo" not in roots:
            raise ArtifactPathError("artifact root config requires the repo root")
        self._roots: dict[str, Path] = {}
        supplied = {name: path.resolve() for name, path in (external_roots or {}).items()}
        for name, definition in roots.items():
            if not isinstance(definition, dict):
                raise ArtifactPathError(f"artifact root {name!r} must be a mapping")
            kind = definition.get("kind")
            if kind == "repository":
                self._roots[name] = self.repository_root
            elif kind == "external" and name in supplied:
                self._roots[name] = supplied[name]
            elif kind != "external":
                raise ArtifactPathError(f"artifact root {name!r} has unsupported kind {kind!r}")
        self._legacy_rebases = config.get("legacy_rebases", [])
        if not isinstance(self._legacy_rebases, list):
            raise ArtifactPathError("legacy_rebases must be an array")
        self.legacy_resolutions: list[ResolvedArtifact] = []
        self.verified_legacy_resolutions: list[ResolvedArtifact] = []

    def _under_root(self, root_name: str, relative: str) -> Path:
        base = self._roots.get(root_name)
        if base is None:
            raise ArtifactPathError(f"unknown artifact root {root_name!r} or no local binding is configured")
        candidate = base.joinpath(*_relative_parts(relative)).resolve()
        if not candidate.is_relative_to(base):
            raise ArtifactPathError(f"artifact location escapes root {root_name!r}: {relative!r}")
        if not candidate.is_file():
            raise ArtifactPathError(f"resolved artifact does not exist: {candidate}")
        return candidate

    def resolve(self, location: str | dict[str, str]) -> ResolvedArtifact:
        if isinstance(location, dict):
            if set(location) != {"root", "path"}:
                raise ArtifactPathError("portable artifact location requires exactly root and path")
            path = self._under_root(location["root"], location["path"])
            return ResolvedArtifact(path, False, location)
        if not isinstance(location, str) or not location:
            raise ArtifactPathError("artifact location must be a path string or portable location object")
        recorded = Path(location).expanduser()
        if recorded.is_file():
            return ResolvedArtifact(recorded.resolve(), False, location)
        matches: list[tuple[int, dict[str, str], Path]] = []
        for mapping in self._legacy_rebases:
            if not isinstance(mapping, dict) or set(mapping) != {"old_root", "new_root"}:
                raise ArtifactPathError("legacy rebase entries require exactly old_root and new_root")
            old_root = Path(mapping["old_root"])
            try:
                relative = recorded.relative_to(old_root)
            except ValueError:
                continue
            matches.append((len(old_root.parts), mapping, relative))
        if not matches:
            raise ArtifactPathError(f"recorded artifact path does not exist and has no explicit legacy rebase: {recorded}")
        _, mapping, relative = max(matches, key=lambda item: item[0])
        path = self._under_root(mapping["new_root"], PurePosixPath(*relative.parts).as_posix())
        resolved = ResolvedArtifact(path, True, location)
        self.legacy_resolutions.append(resolved)
        return resolved

    def mark_verified(self, resolved: ResolvedArtifact) -> None:
        if resolved.legacy_rebased and resolved not in self.verified_legacy_resolutions:
            self.verified_legacy_resolutions.append(resolved)

    def portable_location(self, path: Path) -> dict[str, str]:
        resolved = path.resolve()
        candidates: list[tuple[int, str, Path]] = []
        for name, base in self._roots.items():
            try:
                relative = resolved.relative_to(base)
            except ValueError:
                continue
            candidates.append((len(base.parts), name, relative))
        if not candidates:
            raise ArtifactPathError(f"artifact is not inside a configured artifact root: {resolved}")
        _, root_name, relative = max(candidates, key=lambda item: item[0])
        return {"root": root_name, "path": PurePosixPath(*relative.parts).as_posix()}
