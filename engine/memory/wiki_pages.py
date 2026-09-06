from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


class KnowledgeError(RuntimeError):
    """Canonical knowledge is missing, malformed, or ambiguous."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KnowledgeError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise KnowledgeError(f"{path}: top-level JSON value must be an object")
    return value


def _schema_errors(value: dict[str, Any], schema_path: Path) -> list[str]:
    schema = _load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{location}: {error.message}")
    return errors


def validate_metadata(value: dict[str, Any], schema_path: Path, label: str) -> None:
    errors = _schema_errors(value, schema_path)
    if errors:
        raise KnowledgeError(f"invalid {label}:\n" + "\n".join(f"- {item}" for item in errors))


def parse_wiki_page(path: Path, schema_path: Path) -> WikiPage:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise KnowledgeError(f"cannot read Wiki page {path}: {exc}") from exc
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise KnowledgeError(f"{path}: Wiki page requires YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise KnowledgeError(f"{path}: Wiki frontmatter is not closed") from exc
    try:
        metadata = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise KnowledgeError(f"{path}: invalid Wiki YAML: {exc}") from exc
    if not isinstance(metadata, dict):
        raise KnowledgeError(f"{path}: Wiki metadata must be a mapping")
    validate_metadata(metadata, schema_path, f"Wiki metadata in {path}")
    body = "\n".join(lines[end + 1 :]).strip()
    if not body:
        raise KnowledgeError(f"{path}: Wiki page body must not be empty")
    return WikiPage(metadata["knowledge_id"], metadata, body, path)


@dataclass(frozen=True)
class WikiPage:
    knowledge_id: str
    metadata: dict[str, Any]
    body: str
    path: Path
