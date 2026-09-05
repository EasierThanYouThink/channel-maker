"""Write and validate structured human decision records (Markdown + frontmatter)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


class DecisionError(ValueError):
    """A decision record is missing or malformed."""


STRATEGY_KIND = "strategy"
REVIEW_KIND = "review"


def _timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _render(kind: str, title: str, fields: dict[str, Any], body: str) -> str:
    frontmatter = yaml.safe_dump(
        {"decision_record": kind, **fields}, sort_keys=False, allow_unicode=True
    ).strip()
    return f"---\n{frontmatter}\n---\n\n# {title.strip()}\n\n{body.strip()}\n"


def write_record(
    path: Path,
    *,
    kind: str,
    title: str,
    summary: str,
    selected: list[str] | None = None,
    rejected: list[str] | None = None,
    constraint: str | None = None,
    revisit: str | None = None,
    decision: str | None = None,
    rev: str | None = None,
    author: str = "human",
    created_at: str | None = None,
) -> Path:
    """Write a structured decision record. Strategy and review kinds below."""
    if kind == STRATEGY_KIND:
        if not (selected or []):
            raise DecisionError("a strategy record requires at least one selected opportunity")
        if not (rejected or []):
            raise DecisionError("a strategy record requires a rejected alternative")
        if not (revisit or "").strip():
            raise DecisionError("a strategy record requires a revisit condition")
        fields: dict[str, Any] = {
            "selected": selected, "rejected": rejected, "revisit": revisit.strip(),
            "author": author.strip(), "created_at": _timestamp(created_at),
        }
        if (constraint or "").strip():
            fields["constraint"] = constraint.strip()
    elif kind == REVIEW_KIND:
        if (decision or "").strip() not in {"GO", "REVISE", "ABANDON", "ABANDON_DIRECTION"}:
            raise DecisionError("a review record requires a decision (GO, REVISE, ABANDON, or ABANDON_DIRECTION)")
        if not (rev or "").strip():
            raise DecisionError("a review record requires the production rev it approves")
        fields = {
            "decision": decision.strip(), "rev": rev.strip(),
            "author": author.strip(), "created_at": _timestamp(created_at),
        }
        if rejected:
            fields["rejected"] = rejected
        if (revisit or "").strip():
            fields["revisit"] = revisit.strip()
    else:
        raise DecisionError(f"unknown decision record kind {kind!r}; expected 'strategy' or 'review'")
    if not summary.strip():
        raise DecisionError("a decision record requires a summary")
    if path.exists():
        raise DecisionError(f"decision record already exists (never overwrite one): {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render(kind, title, fields, summary), encoding="utf-8")
    return path


def read_frontmatter(path: Path) -> dict[str, Any] | None:
    """Return the frontmatter mapping if the file is a marked record, else None."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DecisionError(f"cannot read decision record {path}: {exc}") from exc
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = lines.index("---", 1)
    except ValueError:
        return None
    try:
        metadata = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise DecisionError(f"{path}: decision frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(metadata, dict) or "decision_record" not in metadata:
        return None
    return metadata


def validate_record_file(path: Path, *, expected_kind: str | None = None) -> dict[str, Any]:
    """Validate a marked record's shape. Unmarked files pass (backward compat)."""
    metadata = read_frontmatter(path)
    if metadata is None:
        return {}
    kind = metadata.get("decision_record")
    if expected_kind is not None and kind != expected_kind:
        raise DecisionError(
            f"{path}: expected a {expected_kind} decision record, found {kind!r}"
        )
    problems: list[str] = []
    if kind == STRATEGY_KIND:
        if not metadata.get("selected"):
            problems.append("strategy record needs 'selected' (opportunity ids)")
        if not metadata.get("rejected"):
            problems.append("strategy record needs 'rejected' (the declined alternative)")
        if not (metadata.get("revisit") or "").strip():
            problems.append("strategy record needs 'revisit' (when to reconsider)")
    elif kind == REVIEW_KIND:
        if metadata.get("decision") not in {"GO", "REVISE", "ABANDON", "ABANDON_DIRECTION"}:
            problems.append("review record needs 'decision' (GO, REVISE, ABANDON, or ABANDON_DIRECTION)")
        if not (metadata.get("rev") or "").strip():
            problems.append("review record needs 'rev' (the production revision it approves)")
    else:
        problems.append(f"unknown decision record kind {kind!r}")
    body = path.read_text(encoding="utf-8").split("---", 2)
    if len(body) < 3 or not body[2].strip():
        problems.append("decision record needs a non-empty summary body")
    if problems:
        raise DecisionError(f"{path}: " + "; ".join(problems))
    return metadata
