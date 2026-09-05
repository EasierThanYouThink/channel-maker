"""Schema validation for the code-first asset component registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


CONTRACT_ROOT = Path(__file__).resolve().parent / "contracts"
CHANNEL_SCOPE_CONVENTION = "{renderer}/src/channels/{channel_id}/"
ENGINE_SCOPE_CONVENTION = "{renderer}/src/engine/"


class LibraryValidationError(ValueError):
    """An asset component record violates its schema or identity rules."""


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LibraryValidationError(f"{path}: expected a JSON object")
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
        raise LibraryValidationError("\n".join(errors))


def validate_component(document: dict[str, Any], *, repository_root: Path | None = None) -> list[str]:
    """Validate a component record; returns non-fatal convention warnings (does not raise for them)."""

    _validate(document, "asset-component.schema.json")
    warnings: list[str] = []
    if repository_root is not None:
        repository_root = repository_root.resolve()
        source_path = (repository_root / document["source"]["path"]).resolve()
        if not source_path.is_relative_to(repository_root) or not source_path.exists():
            raise LibraryValidationError(f"component source.path does not exist: {document['source']['path']}")
        expected_prefix = (
            ENGINE_SCOPE_CONVENTION.format(renderer=document["renderer"])
            if document["scope"] == "ENGINE"
            else CHANNEL_SCOPE_CONVENTION.format(renderer=document["renderer"], channel_id=document["channel_id"])
        )
        if not document["source"]["path"].startswith(expected_prefix):
            warnings.append(
                f"{document['component_id']}: source.path {document['source']['path']!r} is outside the "
                f"conventional {expected_prefix!r} location for its scope; this is a warning, not a hard failure"
            )
    return warnings


def validate_component_review(document: dict[str, Any]) -> None:
    _validate(document, "asset-component-review.schema.json")
