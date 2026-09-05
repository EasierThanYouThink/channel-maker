"""File-backed failure cases and replay results for one channel."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.channel import ChannelValidationError, validate_channel_package


class FailureLabError(ValueError):
    """A failure case is missing, malformed, or not properly gated."""


def lab_root(package_root: Path) -> Path:
    return package_root / "failure-lab"


def _timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _load_package(package_root: Path, repository_root: Path):
    try:
        return validate_channel_package(package_root.resolve(), repository_root.resolve())
    except ChannelValidationError as exc:
        raise FailureLabError(str(exc)) from exc


def _check_ref(repository_root: Path, ref: str, label: str) -> Path:
    resolved = (repository_root.resolve() / ref).resolve()
    if not ref.strip() or not resolved.is_relative_to(repository_root.resolve()) or not resolved.exists():
        raise FailureLabError(f"{label} does not resolve to an existing repository path: {ref}")
    return resolved


def _case_path(package_root: Path, case_id: str) -> Path:
    return lab_root(package_root) / "cases" / f"{case_id}.json"


def _read_case(package_root: Path, case_id: str) -> tuple[Path, dict[str, Any]]:
    path = _case_path(package_root, case_id)
    if not path.is_file():
        raise FailureLabError(f"no failure case exists yet: {case_id}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FailureLabError(f"cannot read failure case {case_id}: {exc}") from exc
    return path, document


def _write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_bytes(document))
    temporary.replace(path)


def init_lab(package_root: Path, repository_root: Path) -> Path:
    package = _load_package(package_root, repository_root)
    root = lab_root(package.root)
    (root / "cases").mkdir(parents=True, exist_ok=True)
    (root / "replays").mkdir(parents=True, exist_ok=True)
    return root


def file_case(
    package_root: Path,
    repository_root: Path,
    *,
    case_id: str,
    symptom: str,
    input_refs: list[str],
    reproduction_ref: str,
    diagnosis: str = "",
    tool_versions: dict[str, str] | None = None,
    release: str | None = None,
    created_at: str | None = None,
) -> Path:
    """File a failure case. The gate: it must reproduce — a reproduction
    evidence file is required before the case enters the trusted collection."""
    package = _load_package(package_root, repository_root)
    repository_root = repository_root.resolve()
    if not case_id.strip():
        raise FailureLabError("a failure case needs an id")
    if not symptom.strip():
        raise FailureLabError("a failure case needs a visible symptom")
    if not input_refs:
        raise FailureLabError("a failure case needs its original inputs")
    for ref in input_refs:
        _check_ref(repository_root, ref, "input_ref")
    _check_ref(repository_root, reproduction_ref, "reproduction_ref")
    path = _case_path(package.root, case_id.strip())
    if path.is_file():
        raise FailureLabError(f"failure case already exists: {case_id}")
    _write(path, {
        "schema_version": "1.0.0", "case_id": case_id.strip(),
        "channel_id": package.identity["id"], "symptom": symptom.strip(),
        "input_refs": sorted(set(input_refs)), "reproduction_ref": reproduction_ref,
        "diagnosis": diagnosis.strip(), "repair": None, "repair_verified": False,
        "tool_versions": tool_versions or {}, "release": release,
        "created_at": _timestamp(created_at),
    })
    return path


def record_repair(
    package_root: Path,
    repository_root: Path,
    *,
    case_id: str,
    repair: str,
    repair_ref: str,
    verified: bool,
) -> Path:
    """Record the verified repair for a case. Unverified repairs stay marked."""
    package = _load_package(package_root, repository_root)
    _check_ref(repository_root.resolve(), repair_ref, "repair_ref")
    if not repair.strip():
        raise FailureLabError("a repair needs a description")
    path, document = _read_case(package.root, case_id)
    document["repair"] = repair.strip()
    document["repair_ref"] = repair_ref
    document["repair_verified"] = bool(verified)
    _write(path, document)
    return path


def record_replay(
    package_root: Path,
    repository_root: Path,
    *,
    case_id: str,
    passed: bool,
    tool_versions: dict[str, str] | None = None,
    notes: str = "",
    created_at: str | None = None,
) -> Path:
    """Record one replay of a case against current tool versions."""
    package = _load_package(package_root, repository_root)
    _read_case(package.root, case_id)
    seed = {
        "case_id": case_id, "passed": bool(passed),
        "tool_versions": tool_versions or {}, "notes": notes.strip(),
        "created_at": _timestamp(created_at),
    }
    replay_id = f"replay-{hashlib.sha256(_canonical_bytes(seed)).hexdigest()[:12]}"
    path = lab_root(package.root) / "replays" / f"{case_id}-{replay_id}.json"
    if path.is_file():
        return path
    _write(path, {"schema_version": "1.0.0", "replay_id": replay_id, **seed})
    return path


def list_cases(package_root: Path, repository_root: Path) -> list[dict[str, Any]]:
    package = _load_package(package_root, repository_root)
    cases_dir = lab_root(package.root) / "cases"
    if not cases_dir.is_dir():
        return []
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(cases_dir.glob("*.json"))
    ]
