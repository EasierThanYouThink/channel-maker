"""Schema validation for the per-channel Channel Foundation artifact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

CONTRACT_ROOT = Path(__file__).resolve().parent / "contracts"


class FoundationValidationError(ValueError):
    """A Channel Foundation artifact violates its schema or identity rules."""


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FoundationValidationError(f"{path}: expected a JSON object")
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


def validate_foundation(document: dict[str, Any], *, expected_channel_id: str | None = None) -> None:
    """Validate a channel-foundation document against its schema and identity."""

    schemas, registry = _contracts()
    validator = Draft202012Validator(
        schemas["channel-foundation.schema.json"], registry=registry, format_checker=FormatChecker()
    )
    errors = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
    ]
    if errors:
        raise FoundationValidationError("\n".join(errors))
    if expected_channel_id is not None and document["channel_id"] != expected_channel_id:
        raise FoundationValidationError(
            f"foundation channel_id {document['channel_id']!r} does not match expected channel {expected_channel_id!r}"
        )
