"""Candidate Script DNA examples: content-addressed text with human classification."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .validation import ScriptValidationError, validate_script_example, validate_script_example_review


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ScriptValidationError(f"refusing to overwrite existing record {path}")


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ScriptValidationError("cannot derive a slug from empty/non-alphanumeric text")
    return slug


class ScriptExampleStore:
    """Channel-scoped store of candidate Script DNA examples, mirroring the exemplar review flow."""

    def __init__(self, root: Path, channel_id: str):
        self.root = root.resolve()
        self.channel_id = channel_id
        self.base = self.root / "channels" / channel_id / "script" / "examples"
        self.records = self.base / "records"
        self.reviews = self.base / "reviews"

    def add(
        self,
        text: str,
        *,
        tags: list[str],
        provenance_kind: str,
        created_by: str,
        source_ref: str,
        model: str | None = None,
        model_version: str | None = None,
        prompt_ref: str | None = None,
    ) -> dict[str, Any]:
        if not text.strip():
            raise ScriptValidationError("script example text must not be empty")
        if provenance_kind == "model_drafted" and not all((model, model_version)):
            raise ScriptValidationError("model_drafted examples require model and model_version")
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        example_id = f"script-example:{_slug(text[:40])}-{text_hash[:8]}"

        provenance: dict[str, Any] = {"kind": provenance_kind, "created_by": created_by, "source_ref": source_ref}
        if model:
            provenance["model"] = model
        if model_version:
            provenance["model_version"] = model_version
        if prompt_ref:
            provenance["prompt_ref"] = prompt_ref
        record = {
            "schema_version": "1.0.0", "artifact_type": "script_example", "example_id": example_id,
            "channel_id": self.channel_id, "text": text, "classification": "experimental",
            "review_authority": "unreviewed", "reasons": [], "tags": sorted(set(tags)),
            "provenance": provenance, "review_ids": [],
        }
        validate_script_example(record)
        _write_new(self.records / f"{example_id.removeprefix('script-example:')}.json", _canonical_bytes(record))
        return record

    def review(
        self,
        example_id: str,
        *,
        decision: str,
        reviewer: str,
        reason: str,
        created_at: str,
        human_confirmed: bool,
    ) -> dict[str, Any]:
        if not human_confirmed:
            raise ScriptValidationError("script example classification requires an explicit human confirmation")
        record_path = self.records / f"{example_id.removeprefix('script-example:')}.json"
        try:
            record_bytes = record_path.read_bytes()
            record = json.loads(record_bytes)
        except (OSError, json.JSONDecodeError) as exc:
            raise ScriptValidationError(f"cannot read script example {example_id}: {exc}") from exc
        validate_script_example(record)
        target_sha256 = hashlib.sha256(record_bytes).hexdigest()
        seed = {
            "schema_version": "1.0.0", "artifact_type": "script_example_review", "example_id": example_id,
            "target_sha256": target_sha256, "decision": decision, "reviewer": reviewer.strip(),
            "reason": reason.strip(), "created_at": created_at,
        }
        review_id = f"script-example-review:{hashlib.sha256(_canonical_bytes(seed)).hexdigest()[:16]}"
        review = {**seed, "review_id": review_id}
        validate_script_example_review(review)
        _write_new(self.reviews / f"{review_id.removeprefix('script-example-review:')}.json", _canonical_bytes(review))

        updated = dict(record)
        updated["classification"] = decision
        updated["review_authority"] = "human"
        updated["reasons"] = [*record["reasons"], reason.strip()]
        updated["review_ids"] = [*record["review_ids"], review_id]
        validate_script_example(updated)
        _write_atomic(record_path, _canonical_bytes(updated))
        return review

    def list(self, *, classification: str | None = None) -> list[dict[str, Any]]:
        if not self.records.is_dir():
            return []
        results = []
        for path in sorted(self.records.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if classification is not None and record["classification"] != classification:
                continue
            results.append(record)
        return results
