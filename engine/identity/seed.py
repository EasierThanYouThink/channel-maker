"""Discover and freeze a channel's identity (logo + About-page description), domain by domain."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from engine.channel import ChannelValidationError, validate_channel_package

from .store import ChannelIdentityStore
from .validation import IDENTITY_DOMAINS, IdentityValidationError, validate_channel_identity


STARTER_INPUTS: dict[str, list[str]] = {
    "logo": [
        "a square profile-picture-ready mark or icon",
        "consistent with the frozen Visual DNA color language and visual identity",
    ],
    "description": [
        "a short About-page bio in the frozen Script DNA voice",
    ],
}

IDENTITY_RELATIVE_PATH = Path("identity") / "channel-identity.yaml"


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


def identity_path(package_root: Path) -> Path:
    return package_root / IDENTITY_RELATIVE_PATH


def _load_package(package_root: Path, repository_root: Path):
    try:
        return validate_channel_package(package_root.resolve(), repository_root.resolve())
    except ChannelValidationError as exc:
        raise IdentityValidationError(str(exc)) from exc


def init_identity(package_root: Path, repository_root: Path) -> Path:
    package = _load_package(package_root, repository_root)
    path = identity_path(package.root)
    if path.is_file():
        raise IdentityValidationError(f"channel identity seed already exists: {path}")
    domains = {
        domain: {
            "discovery_status": "UNPOPULATED", "authority_status": "UNFROZEN", "gate": "ACTIVE_DISCOVERY",
            "inputs_required": STARTER_INPUTS[domain], "reference_ids": [], "decision_refs": [],
        }
        for domain in IDENTITY_DOMAINS
    }
    document = {
        "schema_version": "1.0.0", "artifact_type": "channel_identity", "channel_id": package.identity["id"],
        "status": "ACTIVE_DISCOVERY", "domains": domains,
        "created_by": {
            "created_at": _timestamp(None), "creator": "TOOL",
            "tool": "engine.identity.seed.init_identity", "version": "1.0.0",
        },
    }
    validate_channel_identity(document, expected_channel_id=package.identity["id"])
    _write_yaml_atomic(path, document)
    return path


def add_reference(package_root: Path, repository_root: Path, *, domain: str, candidate_id: str) -> Path:
    package = _load_package(package_root, repository_root)
    if domain not in IDENTITY_DOMAINS:
        raise IdentityValidationError(f"{domain!r} is not a channel identity domain")
    store = ChannelIdentityStore(repository_root, package.identity["id"])
    record_path = store.records / f"{candidate_id.removeprefix('identity-candidate:')}.json"
    if not record_path.is_file():
        raise IdentityValidationError(f"no identity candidate record found for {candidate_id}")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record["domain"] != domain:
        raise IdentityValidationError(f"candidate {candidate_id} is tagged for domain {record['domain']!r}, not {domain!r}")

    path = identity_path(package.root)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    gate = document["domains"][domain]
    if candidate_id not in gate["reference_ids"]:
        gate["reference_ids"] = [*gate["reference_ids"], candidate_id]
    if gate["discovery_status"] == "UNPOPULATED":
        gate["discovery_status"] = "ACTIVE"
    validate_channel_identity(document, expected_channel_id=package.identity["id"])
    _write_yaml_atomic(path, document)
    return path


def freeze_domain(
    package_root: Path, repository_root: Path, *, domain: str,
    human_confirmed: bool, decision_ref: str, force: bool = False,
) -> Path:
    if not human_confirmed:
        raise IdentityValidationError("freezing a channel identity domain requires an explicit human confirmation")
    if not decision_ref.strip():
        raise IdentityValidationError("freezing a channel identity domain requires a non-empty decision_ref")
    package = _load_package(package_root, repository_root)
    if domain not in IDENTITY_DOMAINS:
        raise IdentityValidationError(f"{domain!r} is not a channel identity domain")
    repository_root = repository_root.resolve()
    resolved = (repository_root / decision_ref).resolve()
    if not resolved.is_relative_to(repository_root) or not resolved.exists():
        raise IdentityValidationError(f"decision_ref does not resolve to an existing repository path: {decision_ref}")

    path = identity_path(package.root)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    gate = document["domains"][domain]
    if gate["authority_status"] == "FROZEN" and not force:
        raise IdentityValidationError(
            f"channel identity domain {domain!r} is already frozen; pass force=True to re-freeze deliberately"
        )
    gate["discovery_status"] = "POPULATED"
    gate["authority_status"] = "FROZEN"
    gate["gate"] = "HUMAN_FROZEN"
    if decision_ref not in gate["decision_refs"]:
        gate["decision_refs"] = [*gate["decision_refs"], decision_ref]
    frozen_count = sum(1 for value in document["domains"].values() if value["authority_status"] == "FROZEN")
    document["status"] = "FROZEN" if frozen_count == len(document["domains"]) else "PARTIALLY_FROZEN"
    validate_channel_identity(document, expected_channel_id=package.identity["id"])
    _write_yaml_atomic(path, document)
    return path


def all_domains_frozen(seed_document: dict[str, Any]) -> bool:
    return all(gate["authority_status"] == "FROZEN" for gate in seed_document["domains"].values())
