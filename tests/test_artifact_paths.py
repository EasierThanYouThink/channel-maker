from __future__ import annotations

from pathlib import Path

import pytest

from artifact_paths import ArtifactPathError, ArtifactPathResolver


def make_resolver(repo: Path, old_root: Path | None = None) -> ArtifactPathResolver:
    config = {
        "schema_version": "1.0.0",
        "roots": {"repo": {"kind": "repository"}},
        "legacy_rebases": [],
    }
    if old_root is not None:
        config["legacy_rebases"] = [{"old_root": str(old_root), "new_root": "repo"}]
    return ArtifactPathResolver(repo, config=config)


def test_portable_location_survives_repository_move(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    evidence = first / "work" / "evidence.bin"
    evidence.parent.mkdir()
    evidence.write_bytes(b"portable-evidence")
    location = make_resolver(first).portable_location(evidence)

    first.rename(second)
    resolved = make_resolver(second).resolve(location)
    assert resolved.path == second / "work" / "evidence.bin"
    assert resolved.legacy_rebased is False


def test_verified_legacy_root_rebase_is_explicit(tmp_path: Path) -> None:
    current = tmp_path / "current"
    current.mkdir()
    target = current / "vids" / "source.mp4"
    target.parent.mkdir()
    target.write_bytes(b"source")
    old = Path("/old/radicat")

    resolved = make_resolver(current, old).resolve(str(old / "vids" / "source.mp4"))
    assert resolved.path == target
    assert resolved.legacy_rebased is True
    assert resolved.original == str(old / "vids" / "source.mp4")


def test_legacy_resolution_never_searches_by_basename(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    elsewhere = repo / "elsewhere" / "source.mp4"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(b"wrong-location")
    resolver = make_resolver(repo, Path("/old/radicat"))

    with pytest.raises(ArtifactPathError, match="does not exist"):
        resolver.resolve("/old/radicat/vids/source.mp4")


def test_portable_location_rejects_escape_and_unknown_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    resolver = make_resolver(repo)
    with pytest.raises(ArtifactPathError, match="relative path"):
        resolver.resolve({"root": "repo", "path": "../outside"})
    with pytest.raises(ArtifactPathError, match="unknown artifact root"):
        resolver.resolve({"root": "missing", "path": "evidence.bin"})


def test_new_location_refuses_unbound_external_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    with pytest.raises(ArtifactPathError, match="not inside a configured artifact root"):
        make_resolver(repo).portable_location(outside)
