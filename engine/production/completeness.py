"""One shared definition of "a real, exact production" for pilots and episodes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ProductionIncompleteError(ValueError):
    """A production was presented as complete but its evidence is missing."""


def _file_sha256(repository_root: Path, ref: str | None) -> str | None:
    if not ref:
        return None
    resolved = (repository_root / ref).resolve()
    if not resolved.is_relative_to(repository_root) or not resolved.is_file():
        return None
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def production_revision(production: dict[str, Any], *, repository_root: Path) -> str:
    """Compute the immutable revision id of a production's current content.

    The id is a content hash over every referenced file (by bytes, not path
    strings) plus the recorded evidence ids/hashes. Identical content yields
    an identical revision; any byte change yields a new one.
    """
    repository_root = repository_root.resolve()
    payload = {
        "script": [production.get("script_ref"), _file_sha256(repository_root, production.get("script_ref"))],
        "voiceover": [production.get("voiceover_ref"), _file_sha256(repository_root, production.get("voiceover_ref"))],
        "render": [production.get("render_ref"), _file_sha256(repository_root, production.get("render_ref"))],
        "production_log": [production.get("production_log_ref"), _file_sha256(repository_root, production.get("production_log_ref"))],
        "manifests": sorted(
            (ref.get("artifact_id"), ref.get("sha256"))
            for ref in production.get("scene_candidate_manifest_refs", [])
        ),
        "evaluations": sorted(
            (ref.get("artifact_id"), ref.get("sha256"))
            for ref in production.get("evaluation_result_refs", [])
        ),
    }
    digest = hashlib.sha256(
        (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    ).hexdigest()
    return f"rev-{digest[:12]}"


def production_snapshot(production: dict[str, Any], *, repository_root: Path) -> dict[str, Any]:
    """Capture exactly what a review decision approves: rev id plus file bytes."""
    repository_root = repository_root.resolve()
    return {
        "rev_id": production_revision(production, repository_root=repository_root),
        "script_ref": production.get("script_ref"),
        "script_sha256": _file_sha256(repository_root, production.get("script_ref")),
        "voiceover_ref": production.get("voiceover_ref"),
        "voiceover_sha256": _file_sha256(repository_root, production.get("voiceover_ref")),
        "render_ref": production.get("render_ref"),
        "render_sha256": _file_sha256(repository_root, production.get("render_ref")),
        "scene_candidate_manifest_refs": [
            {"artifact_id": ref.get("artifact_id"), "sha256": ref.get("sha256")}
            for ref in production.get("scene_candidate_manifest_refs", [])
        ],
        "evaluation_result_refs": [
            {"artifact_id": ref.get("artifact_id"), "sha256": ref.get("sha256")}
            for ref in production.get("evaluation_result_refs", [])
        ],
    }


def _exists(repository_root: Path, ref: str | None) -> bool:
    if not ref:
        return False
    resolved = (repository_root / ref).resolve()
    return resolved.is_relative_to(repository_root) and resolved.is_file()


def check_production(
    production: dict[str, Any], *, repository_root: Path, label: str,
    strict_media: bool = False,
) -> list[str]:
    """Return a list of missing-production problems; empty means complete.

    Manifest/evaluation *hashes* are verified by pilot/episode validation, not
    here — this check establishes that the production exists at all, and that
    its media files are structurally sound per engine.production.probing
    (WAV fully decoded; MP4 container-level; other suffixes existence-only).
    With strict_media=True the render additionally decode-probes via ffprobe
    (dimensions, positive duration, narrated audio track) when ffprobe is
    available — and fails loudly when it is not (see docs/RENDER_CONTRACT.md).
    """
    from engine.production.probing import (
        ffprobe_available,
        probe_file,
        probe_mp4_decode,
    )

    repository_root = repository_root.resolve()
    problems: list[str] = []

    def probe_media(ref: str) -> None:
        if not ref:
            return
        resolved = (repository_root / ref).resolve()
        if not resolved.is_relative_to(repository_root) or not resolved.is_file():
            return  # missing-file problems are reported by the caller below
        report = probe_file(resolved)
        problems.extend(f"{label}: {problem}" for problem in report["problems"])

    if not production.get("script_ref"):
        problems.append(f"{label}: no script_ref recorded; no narration script exists")
    elif not _exists(repository_root, production["script_ref"]):
        problems.append(f"{label}: script file is missing: {production['script_ref']}")
    if not production.get("voiceover_ref"):
        problems.append(f"{label}: no voiceover_ref recorded; no narration audio exists")
    elif not _exists(repository_root, production["voiceover_ref"]):
        problems.append(f"{label}: voiceover audio is missing: {production['voiceover_ref']}")
    else:
        probe_media(production["voiceover_ref"])
    if not production.get("scene_candidate_manifest_refs"):
        problems.append(f"{label}: no scene candidate manifest attached; no scene evidence exists")
    if not production.get("evaluation_result_refs"):
        problems.append(f"{label}: no evaluation result attached; no scene review evidence exists")
    render_ref = production.get("render_ref")
    if not render_ref:
        problems.append(f"{label}: no render_ref recorded; no export exists")
    else:
        resolved = (repository_root / render_ref).resolve()
        if not resolved.is_relative_to(repository_root) or not resolved.is_file():
            problems.append(f"{label}: render file is missing: {render_ref}")
        elif resolved.stat().st_size == 0:
            problems.append(f"{label}: render file is empty: {render_ref}")
        else:
            probe_media(render_ref)
            if strict_media and resolved.suffix.lower() == ".mp4":
                # Strict decode is opt-in and explicit: without ffprobe it
                # cannot verify, so it refuses instead of silently passing.
                if not ffprobe_available():
                    problems.append(f"{label}: strict media demands ffprobe, which is not installed")
                else:
                    decode = probe_mp4_decode(resolved)
                    problems.extend(f"{label}: {problem}" for problem in decode["problems"])
    return problems


def require_complete(
    production: dict[str, Any], *, repository_root: Path, label: str,
    strict_media: bool = False,
) -> None:
    problems = check_production(production, repository_root=repository_root, label=label, strict_media=strict_media)
    if problems:
        raise ProductionIncompleteError(
            "production is not complete; a GO decision requires a real, exact production:\n"
            + "\n".join(f"- {problem}" for problem in problems)
        )
