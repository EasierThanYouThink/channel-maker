"""One shared definition of "a real, exact production" for pilots and episodes."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ProductionIncompleteError(ValueError):
    """A production was presented as complete but its evidence is missing."""


def _exists(repository_root: Path, ref: str | None) -> bool:
    if not ref:
        return False
    resolved = (repository_root / ref).resolve()
    return resolved.is_relative_to(repository_root) and resolved.is_file()


def check_production(
    production: dict[str, Any], *, repository_root: Path, label: str,
) -> list[str]:
    """Return a list of missing-production problems; empty means complete.

    Manifest/evaluation *hashes* are verified by pilot/episode validation, not
    here — this check establishes that the production exists at all. Render
    media is required to exist and be non-empty; byte-level media probing
    (dimensions, duration, audio presence) is future work pending a pinned
    probing tool (see docs/RENDER_CONTRACT.md).
    """
    repository_root = repository_root.resolve()
    problems: list[str] = []
    if not production.get("script_ref"):
        problems.append(f"{label}: no script_ref recorded; no narration script exists")
    elif not _exists(repository_root, production["script_ref"]):
        problems.append(f"{label}: script file is missing: {production['script_ref']}")
    if not production.get("voiceover_ref"):
        problems.append(f"{label}: no voiceover_ref recorded; no narration audio exists")
    elif not _exists(repository_root, production["voiceover_ref"]):
        problems.append(f"{label}: voiceover audio is missing: {production['voiceover_ref']}")
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
    return problems


def require_complete(
    production: dict[str, Any], *, repository_root: Path, label: str,
) -> None:
    problems = check_production(production, repository_root=repository_root, label=label)
    if problems:
        raise ProductionIncompleteError(
            "production is not complete; a GO decision requires a real, exact production:\n"
            + "\n".join(f"- {problem}" for problem in problems)
        )
