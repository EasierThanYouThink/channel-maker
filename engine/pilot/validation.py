"""Schema and cross-artifact validation for a channel's Pilot lifecycle documents."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from engine.channel.workflow import REVISION_TARGETS


CONTRACT_ROOT = Path(__file__).resolve().parent / "contracts"
EVIDENCE_ARTIFACT_TYPES = {"scene_candidate_manifest", "evaluation_result"}


class PilotValidationError(ValueError):
    """A Pilot lifecycle artifact violates its schema, identity, or evidence rules."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotValidationError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PilotValidationError(f"{path}: expected a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _contracts() -> tuple[dict[str, dict[str, Any]], Registry]:
    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for path in sorted(CONTRACT_ROOT.glob("*.schema.json")):
        schema = _load(path)
        Draft202012Validator.check_schema(schema)
        schemas[path.name] = schema
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return schemas, registry


def _schema_errors(document: dict[str, Any]) -> list[str]:
    schemas, registry = _contracts()
    validator = Draft202012Validator(schemas["pilot.schema.json"], registry=registry, format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
    ]


def _validate_evidence_ref(ref: dict[str, Any], *, repository_root: Path, label: str) -> None:
    path = (repository_root / ref["path"]).resolve()
    if not path.is_relative_to(repository_root) or not path.is_file():
        raise PilotValidationError(f"{label}: referenced evidence file is missing: {ref['path']}")
    actual_sha256 = _sha256(path)
    if actual_sha256 != ref["sha256"]:
        raise PilotValidationError(
            f"{label}: evidence file has been modified since it was recorded (sha256 mismatch): {ref['path']}"
        )
    document = _load(path)
    if document.get("artifact_type") not in EVIDENCE_ARTIFACT_TYPES:
        raise PilotValidationError(f"{label}: referenced file is not a recognized evidence artifact: {ref['path']}")
    if document.get("artifact_id") != ref["artifact_id"]:
        raise PilotValidationError(f"{label}: evidence artifact_id does not match the referenced file: {ref['path']}")


def validate_pilot(
    document: dict[str, Any],
    *,
    repository_root: Path,
    expected_channel_id: str | None = None,
) -> None:
    errors = _schema_errors(document)
    if errors:
        raise PilotValidationError("\n".join(errors))
    if expected_channel_id is not None and document["channel_id"] != expected_channel_id:
        raise PilotValidationError(
            f"pilot channel_id {document['channel_id']!r} does not match expected channel {expected_channel_id!r}"
        )

    repository_root = repository_root.resolve()
    for ref in [*document["production"]["scene_candidate_manifest_refs"], *document["production"]["evaluation_result_refs"], *document["review"]["critic_summary_refs"]]:
        _validate_evidence_ref(ref, repository_root=repository_root, label=document["artifact_id"])

    review = document["review"]
    decision = review["decision"]
    if decision is not None and not review["decision_ref"]:
        raise PilotValidationError("a pilot review decision requires a non-empty decision_ref")
    if decision == "REVISE":
        if not review["revise_target"] or review["revise_target"] not in REVISION_TARGETS:
            raise PilotValidationError(
                f"REVISE requires revise_target to be one of {sorted(REVISION_TARGETS)}, got {review['revise_target']!r}"
            )
    elif review["revise_target"] is not None:
        raise PilotValidationError("revise_target is only legal when decision is REVISE")

    freeze = document["freeze"]
    if freeze["frozen"] and decision != "GO":
        raise PilotValidationError("a pilot cannot be frozen unless its review decision is GO")
    if freeze["frozen"] and not freeze["decision_ref"]:
        raise PilotValidationError("freezing a pilot requires a non-empty decision_ref")
