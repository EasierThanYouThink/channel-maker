"""Schema validation for a channel's identity seed and candidates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


CONTRACT_ROOT = Path(__file__).resolve().parent / "contracts"

IDENTITY_DOMAINS = ("logo", "description")


class IdentityValidationError(ValueError):
    """A Channel Identity artifact violates its schema, identity, or cross-reference rules."""


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise IdentityValidationError(f"{path}: expected a JSON object")
    return value


def _contracts() -> tuple[dict[str, dict[str, Any]], Registry]:
    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for path in sorted(CONTRACT_ROOT.glob("*.schema.json")):
        schema = _load(path)
        Draft202012Validator.check_schema(schema)
        schemas[path.name] = schema
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return schemas, registry


def _validate(document: dict[str, Any], schema_name: str) -> None:
    schemas, registry = _contracts()
    validator = Draft202012Validator(schemas[schema_name], registry=registry, format_checker=FormatChecker())
    errors = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
    ]
    if errors:
        raise IdentityValidationError("\n".join(errors))


def validate_channel_identity(document: dict[str, Any], *, expected_channel_id: str | None = None) -> None:
    _validate(document, "channel-identity.schema.json")
    if expected_channel_id is not None and document["channel_id"] != expected_channel_id:
        raise IdentityValidationError(
            f"channel identity seed channel_id {document['channel_id']!r} does not match expected channel {expected_channel_id!r}"
        )


def validate_identity_candidate(document: dict[str, Any]) -> None:
    _validate(document, "identity-candidate.schema.json")


def validate_identity_candidate_review(document: dict[str, Any]) -> None:
    _validate(document, "identity-candidate-review.schema.json")


def resolve_domain_references(seed_document: dict[str, Any], candidates_root: Path) -> list[str]:
    """Raise if any domain's reference_ids do not correspond to a real candidate record tagged for that domain."""

    records_root = candidates_root / "records"
    problems: list[str] = []
    for domain, gate in seed_document["domains"].items():
        for candidate_id in gate["reference_ids"]:
            record_path = records_root / f"{candidate_id.removeprefix('identity-candidate:')}.json"
            if not record_path.is_file():
                problems.append(f"{domain}: reference_ids includes {candidate_id!r}, which has no candidate record")
                continue
            record = _load(record_path)
            if record.get("domain") != domain:
                problems.append(f"{domain}: reference {candidate_id!r} is tagged for domain {record.get('domain')!r}, not {domain!r}")
    if problems:
        raise IdentityValidationError("\n".join(problems))
    return sorted({ref for gate in seed_document["domains"].values() for ref in gate["reference_ids"]})
