"""File-backed taste comparisons and promotable policies for one channel."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.channel import ChannelValidationError, validate_channel_package


class TasteError(ValueError):
    """A taste record is missing, malformed, or not human-gated."""


def taste_root(package_root: Path) -> Path:
    return package_root / "taste"


def _timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _write_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_bytes(value)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise TasteError(f"refusing to overwrite existing taste record {path}")


def _load_package(package_root: Path, repository_root: Path):
    try:
        return validate_channel_package(package_root.resolve(), repository_root.resolve())
    except ChannelValidationError as exc:
        raise TasteError(str(exc)) from exc


def _check_decision_ref(repository_root: Path, decision_ref: str) -> None:
    if not decision_ref.strip():
        raise TasteError("taste decisions require a non-empty decision_ref")
    resolved = (repository_root.resolve() / decision_ref).resolve()
    if not resolved.is_relative_to(repository_root.resolve()) or not resolved.exists():
        raise TasteError(f"decision_ref does not resolve to an existing repository path: {decision_ref}")


def _comparisons_file(package_root: Path) -> Path:
    return taste_root(package_root) / "comparisons.json"


def _policies_file(package_root: Path) -> Path:
    return taste_root(package_root) / "policies.json"


def _read_list(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TasteError(f"cannot read taste file {path}: {exc}") from exc
    if not isinstance(value, list):
        raise TasteError(f"{path}: expected a JSON array")
    return value


def _write_list(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_bytes(items))
    temporary.replace(path)


def init_taste(package_root: Path, repository_root: Path) -> Path:
    package = _load_package(package_root, repository_root)
    root = taste_root(package.root)
    root.mkdir(parents=True, exist_ok=True)
    for path in (_comparisons_file(package.root), _policies_file(package.root)):
        if not path.is_file():
            _write_list(path, [])
    return root


def record_comparison(
    package_root: Path,
    repository_root: Path,
    *,
    preferred_ref: str,
    rejected_ref: str,
    reason: str,
    decided_by: str,
    decision_ref: str,
    context: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Record which of two actual productions the creator preferred, and why."""
    package = _load_package(package_root, repository_root)
    repository_root = repository_root.resolve()
    _check_decision_ref(repository_root, decision_ref)
    if not preferred_ref.strip() or not rejected_ref.strip():
        raise TasteError("a comparison needs both a preferred and a rejected ref")
    if preferred_ref == rejected_ref:
        raise TasteError("a comparison must distinguish two different productions")
    if not reason.strip() or not decided_by.strip():
        raise TasteError("a comparison needs a reason and a decider")
    seed = {
        "channel_id": package.identity["id"], "preferred_ref": preferred_ref,
        "rejected_ref": rejected_ref, "reason": reason.strip(),
        "decided_by": decided_by.strip(), "decision_ref": decision_ref,
        "context": context.strip(), "created_at": _timestamp(created_at),
    }
    record = {
        **seed,
        "comparison_id": f"taste-comparison-{hashlib.sha256(_canonical_bytes(seed)).hexdigest()[:12]}",
    }
    items = _read_list(_comparisons_file(package.root))
    if all(item["comparison_id"] != record["comparison_id"] for item in items):
        items.append(record)
        _write_list(_comparisons_file(package.root), items)
    return record


def propose_policy(
    package_root: Path,
    repository_root: Path,
    *,
    statement: str,
    scope: str,
    comparison_ids: list[str],
    uncertainty: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Propose a conditional preference. Proposals advise; only promotion governs."""
    package = _load_package(package_root, repository_root)
    if not statement.strip() or not scope.strip():
        raise TasteError("a policy needs a statement and a scope")
    known = {item["comparison_id"] for item in _read_list(_comparisons_file(package.root))}
    unknown = [key for key in comparison_ids if key not in known]
    if unknown:
        raise TasteError(f"policy cites unknown comparisons: {unknown}")
    if not comparison_ids:
        raise TasteError("a policy must cite at least one comparison")
    seed = {
        "channel_id": package.identity["id"], "statement": statement.strip(),
        "scope": scope.strip(), "comparison_ids": sorted(set(comparison_ids)),
        "uncertainty": uncertainty.strip(), "created_at": _timestamp(created_at),
    }
    record = {
        **seed,
        "policy_id": f"taste-policy-{hashlib.sha256(_canonical_bytes(seed)).hexdigest()[:12]}",
        "status": "proposed", "promoted_by": None, "promoted_at": None,
        "decision_ref": None, "heldout_ref": None,
    }
    items = _read_list(_policies_file(package.root))
    if all(item["policy_id"] != record["policy_id"] for item in items):
        items.append(record)
        _write_list(_policies_file(package.root), items)
    return record


def promote_policy(
    package_root: Path,
    repository_root: Path,
    *,
    policy_id: str,
    promoted_by: str,
    decision_ref: str,
    heldout_ref: str,
    human_confirmed: bool,
    promoted_at: str | None = None,
) -> dict[str, Any]:
    """Promote a policy to guidance after a human sees it on held-out examples.

    The gate: a non-empty decider, an existing decision file, an existing
    held-out evidence file, and an explicit human confirmation. Promoted
    guidance ranks and constrains — it never approves.
    """
    if not human_confirmed:
        raise TasteError("promoting a taste policy requires an explicit human confirmation")
    package = _load_package(package_root, repository_root)
    repository_root = repository_root.resolve()
    _check_decision_ref(repository_root, decision_ref)
    heldout = (repository_root / heldout_ref).resolve()
    if not heldout_ref.strip() or not heldout.is_relative_to(repository_root) or not heldout.exists():
        raise TasteError(f"heldout_ref does not resolve to an existing repository path: {heldout_ref}")
    if not promoted_by.strip():
        raise TasteError("promotion requires a named promoter")
    path = _policies_file(package.root)
    items = _read_list(path)
    for index, item in enumerate(items):
        if item["policy_id"] == policy_id:
            if item["status"] == "promoted":
                raise TasteError(f"policy {policy_id} is already promoted")
            updated = {
                **item, "status": "promoted", "promoted_by": promoted_by.strip(),
                "promoted_at": _timestamp(promoted_at), "decision_ref": decision_ref,
                "heldout_ref": heldout_ref,
            }
            items[index] = updated
            _write_list(path, items)
            return updated
    raise TasteError(f"unknown taste policy: {policy_id}")


def retire_policy(
    package_root: Path, repository_root: Path, *, policy_id: str, reason: str,
) -> dict[str, Any]:
    package = _load_package(package_root, repository_root)
    if not reason.strip():
        raise TasteError("retiring a policy requires a reason")
    path = _policies_file(package.root)
    items = _read_list(path)
    for index, item in enumerate(items):
        if item["policy_id"] == policy_id:
            updated = {**item, "status": "retired"}
            items[index] = updated
            _write_list(path, items)
            return updated
    raise TasteError(f"unknown taste policy: {policy_id}")


def list_comparisons(package_root: Path, repository_root: Path) -> list[dict[str, Any]]:
    package = _load_package(package_root, repository_root)
    return _read_list(_comparisons_file(package.root))


def list_policies(
    package_root: Path, repository_root: Path, *, status: str | None = None,
) -> list[dict[str, Any]]:
    package = _load_package(package_root, repository_root)
    items = _read_list(_policies_file(package.root))
    return [item for item in items if status is None or item["status"] == status]
