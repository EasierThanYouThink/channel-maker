"""Schema validation for channel-scoped Visual/Motion DNA seeds and exemplars."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

CONTRACT_ROOT = Path(__file__).resolve().parent / "contracts"

SEED_SCHEMA = {"visual": "visual-dna-seed.schema.json", "motion": "motion-dna-seed.schema.json"}
SEED_ARTIFACT_TYPE = {"visual": "visual_dna_seed", "motion": "motion_dna_seed"}
SEED_DOMAINS = {
    "visual": ("visual_identity", "typography", "color_language", "composition_grammar", "scene_aesthetics"),
    "motion": ("motion_identity",),
}


class DesignValidationError(ValueError):
    """A Design DNA artifact violates its schema, identity, or cross-reference rules."""


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DesignValidationError(f"{path}: expected a JSON object")
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
        raise DesignValidationError("\n".join(errors))


def _check_kind(kind: str) -> None:
    if kind not in SEED_SCHEMA:
        raise DesignValidationError(f"unknown DNA seed kind {kind!r}; expected 'visual' or 'motion'")


def validate_dna_seed(kind: str, document: dict[str, Any], *, expected_channel_id: str | None = None) -> None:
    _check_kind(kind)
    _validate(document, SEED_SCHEMA[kind])
    if expected_channel_id is not None and document["channel_id"] != expected_channel_id:
        raise DesignValidationError(
            f"{kind} DNA seed channel_id {document['channel_id']!r} does not match expected channel {expected_channel_id!r}"
        )


def validate_exemplar(document: dict[str, Any]) -> None:
    _validate(document, "exemplar.schema.json")


def validate_exemplar_review(document: dict[str, Any]) -> None:
    _validate(document, "exemplar-review.schema.json")


def resolve_domain_references(kind: str, seed_document: dict[str, Any], exemplars_root: Path) -> list[str]:
    """Raise if any domain's reference_ids do not correspond to a real exemplar tagged for that domain."""

    _check_kind(kind)
    records_root = exemplars_root / "records"
    problems: list[str] = []
    for domain, gate in seed_document["domains"].items():
        for exemplar_id in gate["reference_ids"]:
            record_path = records_root / f"{exemplar_id.removeprefix('exemplar:')}.json"
            if not record_path.is_file():
                problems.append(f"{domain}: reference_ids includes {exemplar_id!r}, which has no exemplar record")
                continue
            record = _load(record_path)
            if record.get("domain") not in (None, domain):
                problems.append(f"{domain}: reference {exemplar_id!r} is tagged for domain {record.get('domain')!r}, not {domain!r}")
            elif record.get("classification") != "approved":
                problems.append(
                    f"{domain}: reference {exemplar_id!r} has classification "
                    f"{record.get('classification')!r}, not 'approved'"
                )
    if problems:
        raise DesignValidationError("\n".join(problems))
    return sorted({ref for gate in seed_document["domains"].values() for ref in gate["reference_ids"]})
