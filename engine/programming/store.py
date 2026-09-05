"""File-backed programming hypotheses, assignments, outcomes, and slates."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.channel import ChannelValidationError, validate_channel_package


class ProgrammingError(ValueError):
    """A programming record is missing, malformed, or not human-gated."""


def desk_root(package_root: Path) -> Path:
    return package_root / "programming"


def _timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _load_package(package_root: Path, repository_root: Path):
    try:
        return validate_channel_package(package_root.resolve(), repository_root.resolve())
    except ChannelValidationError as exc:
        raise ProgrammingError(str(exc)) from exc


def _check_ref(repository_root: Path, ref: str, label: str) -> None:
    if not ref.strip():
        raise ProgrammingError(f"{label} requires a non-empty reference")
    resolved = (repository_root.resolve() / ref).resolve()
    if not resolved.is_relative_to(repository_root.resolve()) or not resolved.exists():
        raise ProgrammingError(f"{label} does not resolve to an existing repository path: {ref}")


def _read(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProgrammingError(f"cannot read programming file {path}: {exc}") from exc


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_bytes(value))
    temporary.replace(path)


def init_desk(package_root: Path, repository_root: Path) -> Path:
    package = _load_package(package_root, repository_root)
    root = desk_root(package.root)
    root.mkdir(parents=True, exist_ok=True)
    for name, default in (
        ("hypotheses.json", []), ("assignments.json", {}),
        ("costs.json", []), ("outcomes.json", []), ("slates.json", []),
    ):
        path = root / name
        if not path.is_file():
            _write(path, default)
    return root


def propose_hypothesis(
    package_root: Path,
    repository_root: Path,
    *,
    hypothesis_id: str,
    statement: str,
    opportunity_ref: str | None = None,
    comparison_group: str = "explore",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Propose an editorial bet. Untested until episodes are assigned."""
    package = _load_package(package_root, repository_root)
    if not hypothesis_id.strip() or not statement.strip():
        raise ProgrammingError("a hypothesis needs an id and a statement")
    if comparison_group not in {"explore", "proven", "control"}:
        raise ProgrammingError(f"unknown comparison group {comparison_group!r}")
    path = desk_root(package.root) / "hypotheses.json"
    items = _read(path, [])
    if any(item["hypothesis_id"] == hypothesis_id for item in items):
        raise ProgrammingError(f"hypothesis already exists: {hypothesis_id}")
    record = {
        "hypothesis_id": hypothesis_id.strip(), "statement": statement.strip(),
        "opportunity_ref": opportunity_ref, "comparison_group": comparison_group,
        "status": "untested", "created_at": _timestamp(created_at),
    }
    items.append(record)
    _write(path, items)
    return record


def assign_episode(
    package_root: Path, repository_root: Path, *, hypothesis_id: str, episode_id: str,
) -> dict[str, str]:
    """Bind a topic use to an episode id: one episode tests one hypothesis."""
    package = _load_package(package_root, repository_root)
    root = desk_root(package.root)
    hypotheses = _read(root / "hypotheses.json", [])
    if not any(item["hypothesis_id"] == hypothesis_id for item in hypotheses):
        raise ProgrammingError(f"unknown hypothesis: {hypothesis_id}")
    assignments = _read(root / "assignments.json", {})
    if episode_id in assignments:
        raise ProgrammingError(
            f"episode {episode_id} already tests {assignments[episode_id]}; one episode, one hypothesis"
        )
    assignments[episode_id] = hypothesis_id
    _write(root / "assignments.json", assignments)
    for item in hypotheses:
        if item["hypothesis_id"] == hypothesis_id and item["status"] == "untested":
            item["status"] = "testing"
    _write(root / "hypotheses.json", hypotheses)
    return {"episode_id": episode_id, "hypothesis_id": hypothesis_id}


def record_cost(
    package_root: Path, repository_root: Path, *, episode_id: str,
    minutes: float, notes: str = "", created_at: str | None = None,
) -> dict[str, Any]:
    package = _load_package(package_root, repository_root)
    if minutes < 0:
        raise ProgrammingError("production cost cannot be negative")
    path = desk_root(package.root) / "costs.json"
    items = _read(path, [])
    record = {
        "episode_id": episode_id, "minutes": minutes, "notes": notes.strip(),
        "created_at": _timestamp(created_at),
    }
    items.append(record)
    _write(path, items)
    return record


def record_publication(
    package_root: Path, repository_root: Path, *, episode_id: str,
    published_at: str | None = None, receipt_ref: str | None = None,
) -> dict[str, Any]:
    """Record the human's publication act. Publishing stays manual; the desk
    only files the receipt so outcomes can join planning later."""
    package = _load_package(package_root, repository_root)
    root = desk_root(package.root)
    assignments = _read(root / "assignments.json", {})
    if episode_id not in assignments:
        raise ProgrammingError(f"episode {episode_id} is not assigned to any hypothesis")
    if receipt_ref is not None:
        _check_ref(repository_root, receipt_ref, "receipt_ref")
    outcomes = _read(root / "outcomes.json", [])
    record = {
        "episode_id": episode_id, "hypothesis_id": assignments[episode_id],
        "kind": "publication", "published_at": _timestamp(published_at),
        "receipt_ref": receipt_ref, "measurements": None,
    }
    outcomes.append(record)
    _write(root / "outcomes.json", outcomes)
    return record


def record_outcome(
    package_root: Path,
    repository_root: Path,
    *,
    episode_id: str,
    measurements: dict[str, Any],
    provenance: str,
    window: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Record a manually imported outcome snapshot. Measurements require
    stated provenance and a comparable observation window; anything else
    stays unknown rather than becoming a guessed number."""
    package = _load_package(package_root, repository_root)
    root = desk_root(package.root)
    assignments = _read(root / "assignments.json", {})
    if episode_id not in assignments:
        raise ProgrammingError(f"episode {episode_id} is not assigned to any hypothesis")
    if not measurements:
        raise ProgrammingError("an outcome snapshot needs at least one measurement")
    if not provenance.strip() or not window.strip():
        raise ProgrammingError("an outcome snapshot needs provenance and a comparable window")
    outcomes = _read(root / "outcomes.json", [])
    record = {
        "episode_id": episode_id, "hypothesis_id": assignments[episode_id],
        "kind": "outcome", "measurements": measurements,
        "provenance": provenance.strip(), "window": window.strip(),
        "evidence_strength": "correlational",
        "created_at": _timestamp(created_at),
    }
    outcomes.append(record)
    _write(root / "outcomes.json", outcomes)
    return record


def propose_slate(
    package_root: Path, repository_root: Path, *, slate_id: str,
    episode_ids: list[str], rationale: str = "", created_at: str | None = None,
) -> dict[str, Any]:
    """Propose the next bounded episode slate. Approval is a human gate."""
    package = _load_package(package_root, repository_root)
    if not slate_id.strip() or not episode_ids:
        raise ProgrammingError("a slate needs an id and at least one episode")
    path = desk_root(package.root) / "slates.json"
    items = _read(path, [])
    if any(item["slate_id"] == slate_id for item in items):
        raise ProgrammingError(f"slate already exists: {slate_id}")
    record = {
        "slate_id": slate_id.strip(), "episode_ids": list(episode_ids),
        "rationale": rationale.strip(), "status": "proposed",
        "approved_by": None, "decision_ref": None, "created_at": _timestamp(created_at),
    }
    items.append(record)
    _write(path, items)
    return record


def approve_slate(
    package_root: Path, repository_root: Path, *, slate_id: str,
    approved_by: str, decision_ref: str, human_confirmed: bool,
) -> dict[str, Any]:
    package = _load_package(package_root, repository_root)
    if not human_confirmed:
        raise ProgrammingError("approving a slate requires an explicit human confirmation")
    _check_ref(repository_root, decision_ref, "decision_ref")
    if not approved_by.strip():
        raise ProgrammingError("approving a slate requires a named approver")
    path = desk_root(package.root) / "slates.json"
    items = _read(path, [])
    for item in items:
        if item["slate_id"] == slate_id:
            if item["status"] == "approved":
                raise ProgrammingError(f"slate {slate_id} is already approved")
            item["status"] = "approved"
            item["approved_by"] = approved_by.strip()
            item["decision_ref"] = decision_ref
            _write(path, items)
            return item
    raise ProgrammingError(f"unknown slate: {slate_id}")


def list_hypotheses(package_root: Path, repository_root: Path) -> list[dict[str, Any]]:
    package = _load_package(package_root, repository_root)
    return _read(desk_root(package.root) / "hypotheses.json", [])


def list_slates(package_root: Path, repository_root: Path) -> list[dict[str, Any]]:
    package = _load_package(package_root, repository_root)
    return _read(desk_root(package.root) / "slates.json", [])
