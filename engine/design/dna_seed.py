"""Discover and freeze a channel's Visual/Motion DNA seed, domain by domain."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from engine.channel import ChannelValidationError, validate_channel_package

from .exemplars import ChannelExemplarStore
from .validation import SEED_ARTIFACT_TYPE, SEED_DOMAINS, DesignValidationError, validate_dna_seed


STARTER_INPUTS: dict[str, list[str]] = {
    "visual_identity": [
        "overall illustration style reference", "geometry/dimensionality direction", "line weight and rendering approach",
    ],
    "typography": ["display typeface direction", "body/caption typeface direction"],
    "color_language": ["palette role definitions (not exact values)", "background treatment"],
    "composition_grammar": ["framing/camera default", "layering and depth approach"],
    "scene_aesthetics": ["texture/finish direction", "prop and set-dressing style"],
    "motion_identity": ["entrance/exit behavior", "camera philosophy", "tempo and stagger", "easing families"],
}

SEED_RELATIVE_PATH = {
    "visual": Path("design") / "visual-dna-seed.yaml",
    "motion": Path("motion") / "motion-dna-seed.yaml",
}


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


def seed_path(kind: str, package_root: Path) -> Path:
    return package_root / SEED_RELATIVE_PATH[kind]


def _load_package(package_root: Path, repository_root: Path):
    try:
        return validate_channel_package(package_root.resolve(), repository_root.resolve())
    except ChannelValidationError as exc:
        raise DesignValidationError(str(exc)) from exc


def init_seed(kind: str, package_root: Path, repository_root: Path) -> Path:
    package = _load_package(package_root, repository_root)
    path = seed_path(kind, package.root)
    if path.is_file():
        raise DesignValidationError(f"{kind} DNA seed already exists: {path}")
    domains = {
        domain: {
            "discovery_status": "UNPOPULATED", "authority_status": "UNFROZEN", "gate": "ACTIVE_DISCOVERY",
            "inputs_required": STARTER_INPUTS[domain], "reference_ids": [], "decision_refs": [],
        }
        for domain in SEED_DOMAINS[kind]
    }
    document = {
        "schema_version": "1.0.0", "artifact_type": SEED_ARTIFACT_TYPE[kind], "channel_id": package.identity["id"],
        "status": "ACTIVE_DISCOVERY", "domains": domains,
        "created_by": {
            "created_at": _timestamp(None), "creator": "TOOL",
            "tool": f"engine.design.dna_seed.init_seed[{kind}]", "version": "1.0.0",
        },
    }
    validate_dna_seed(kind, document, expected_channel_id=package.identity["id"])
    _write_yaml_atomic(path, document)
    return path


def add_reference(kind: str, package_root: Path, repository_root: Path, *, domain: str, exemplar_id: str) -> Path:
    package = _load_package(package_root, repository_root)
    if domain not in SEED_DOMAINS[kind]:
        raise DesignValidationError(f"{domain!r} is not a {kind} DNA domain")
    store = ChannelExemplarStore(repository_root, package.identity["id"])
    record_path = store.records / f"{exemplar_id.removeprefix('exemplar:')}.json"
    if not record_path.is_file():
        raise DesignValidationError(f"no exemplar record found for {exemplar_id}")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("domain") not in (None, domain):
        raise DesignValidationError(f"exemplar {exemplar_id} is tagged for domain {record.get('domain')!r}, not {domain!r}")
    if record.get("classification") != "approved":
        raise DesignValidationError(
            f"exemplar {exemplar_id} has classification {record.get('classification')!r}; "
            "only approved exemplars may be attached as DNA references"
        )

    path = seed_path(kind, package.root)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    gate = document["domains"][domain]
    if exemplar_id not in gate["reference_ids"]:
        gate["reference_ids"] = [*gate["reference_ids"], exemplar_id]
    if gate["discovery_status"] == "UNPOPULATED":
        gate["discovery_status"] = "ACTIVE"
    validate_dna_seed(kind, document, expected_channel_id=package.identity["id"])
    _write_yaml_atomic(path, document)
    return path


def freeze_domain(
    kind: str, package_root: Path, repository_root: Path, *, domain: str,
    human_confirmed: bool, decision_ref: str, force: bool = False,
) -> Path:
    if not human_confirmed:
        raise DesignValidationError(f"freezing a {kind} DNA domain requires an explicit human confirmation")
    if not decision_ref.strip():
        raise DesignValidationError(f"freezing a {kind} DNA domain requires a non-empty decision_ref")
    package = _load_package(package_root, repository_root)
    if domain not in SEED_DOMAINS[kind]:
        raise DesignValidationError(f"{domain!r} is not a {kind} DNA domain")
    repository_root = repository_root.resolve()
    resolved = (repository_root / decision_ref).resolve()
    if not resolved.is_relative_to(repository_root) or not resolved.exists():
        raise DesignValidationError(f"decision_ref does not resolve to an existing repository path: {decision_ref}")

    path = seed_path(kind, package.root)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    gate = document["domains"][domain]
    if gate["authority_status"] == "FROZEN" and not force:
        raise DesignValidationError(
            f"{kind} DNA domain {domain!r} is already frozen; pass force=True to re-freeze deliberately"
        )
    gate["discovery_status"] = "POPULATED"
    gate["authority_status"] = "FROZEN"
    gate["gate"] = "HUMAN_FROZEN"
    if decision_ref not in gate["decision_refs"]:
        gate["decision_refs"] = [*gate["decision_refs"], decision_ref]
    frozen_count = sum(1 for value in document["domains"].values() if value["authority_status"] == "FROZEN")
    document["status"] = "FROZEN" if frozen_count == len(document["domains"]) else "PARTIALLY_FROZEN"
    validate_dna_seed(kind, document, expected_channel_id=package.identity["id"])
    _write_yaml_atomic(path, document)
    return path


def all_domains_frozen(kind: str, seed_document: dict[str, Any]) -> bool:
    return all(gate["authority_status"] == "FROZEN" for gate in seed_document["domains"].values())
