"""Channel-scoped design exemplars: candidate reference images with an approve/reject/
borderline review flow. See `docs/CHANNEL_DESIGN_DNA.md`.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
from pathlib import Path
from typing import Any

from .validation import (
    DesignValidationError,
    validate_exemplar,
    validate_exemplar_review,
)


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise DesignValidationError("title must contain at least one letter or number")
    return slug


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        if path.read_bytes() != payload:
            raise DesignValidationError(f"refusing to overwrite existing record {path}") from exc


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


class ChannelExemplarStore:
    """One channel's design exemplars, at `channels/<id>/design/exemplars/`."""

    def __init__(self, root: Path, channel_id: str):
        self.root = root.resolve()
        self.channel_id = channel_id
        self.base = self.root / "channels" / channel_id / "design" / "exemplars"
        self.assets = self.base / "assets"
        self.records = self.base / "records"
        self.reviews = self.base / "reviews"

    def add(
        self,
        image: Path,
        *,
        title: str,
        domain: str | None,
        tags: list[str],
        provenance_kind: str,
        created_by: str,
        source_ref: str,
        model: str | None = None,
        model_version: str | None = None,
        prompt_ref: str | None = None,
    ) -> dict[str, Any]:
        image = image.resolve()
        if not image.is_file():
            raise DesignValidationError(f"design exemplar image does not exist: {image}")
        media_type, _ = mimetypes.guess_type(image.name)
        allowed = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
        if media_type not in allowed:
            raise DesignValidationError("design exemplar must be PNG, JPEG, or WebP")
        if provenance_kind == "ai_generated_original" and not all((model, model_version, prompt_ref)):
            raise DesignValidationError("AI-generated exemplars require model, model_version, and prompt_ref")

        asset_hash = _sha256(image)
        exemplar_id = f"exemplar:{_slug(title)}-{asset_hash[:8]}"
        asset_path = self.assets / f"{asset_hash}{allowed[media_type]}"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        if asset_path.exists() and _sha256(asset_path) != asset_hash:
            raise DesignValidationError(f"asset hash collision at {asset_path}")
        if not asset_path.exists():
            temporary = asset_path.with_suffix(asset_path.suffix + ".tmp")
            shutil.copyfile(image, temporary)
            temporary.replace(asset_path)

        provenance: dict[str, Any] = {"kind": provenance_kind, "created_by": created_by, "source_ref": source_ref}
        if model:
            provenance["model"] = model
        if model_version:
            provenance["model_version"] = model_version
        if prompt_ref:
            provenance["prompt_ref"] = prompt_ref
        record = {
            "schema_version": "1.0.0", "artifact_type": "design_exemplar", "exemplar_id": exemplar_id,
            "channel_id": self.channel_id, "domain": domain, "title": title.strip(),
            "asset": {"path": asset_path.relative_to(self.root).as_posix(), "sha256": asset_hash, "media_type": media_type},
            "classification": "experimental", "review_authority": "unreviewed", "reasons": [],
            "tags": sorted(set(tags)), "provenance": provenance, "review_ids": [],
        }
        validate_exemplar(record)
        _write_new(self.records / f"{exemplar_id.removeprefix('exemplar:')}.json", _canonical_bytes(record))
        return record

    def review(
        self,
        exemplar_id: str,
        *,
        decision: str,
        reviewer: str,
        reason: str,
        created_at: str,
        human_confirmed: bool,
    ) -> dict[str, Any]:
        if not human_confirmed:
            raise DesignValidationError("exemplar classification requires an explicit human confirmation")
        record_path = self.records / f"{exemplar_id.removeprefix('exemplar:')}.json"
        try:
            record_bytes = record_path.read_bytes()
            record = json.loads(record_bytes)
        except (OSError, json.JSONDecodeError) as exc:
            raise DesignValidationError(f"cannot read exemplar {exemplar_id}: {exc}") from exc
        validate_exemplar(record)
        target_sha256 = hashlib.sha256(record_bytes).hexdigest()
        seed = {
            "schema_version": "1.0.0", "artifact_type": "design_exemplar_review", "exemplar_id": exemplar_id,
            "target_sha256": target_sha256, "decision": decision, "reviewer": reviewer.strip(),
            "reason": reason.strip(), "created_at": created_at,
        }
        review_id = f"exemplar-review:{hashlib.sha256(_canonical_bytes(seed)).hexdigest()[:16]}"
        review = {**seed, "review_id": review_id}
        validate_exemplar_review(review)
        _write_new(self.reviews / f"{review_id.removeprefix('exemplar-review:')}.json", _canonical_bytes(review))

        updated = dict(record)
        updated["classification"] = decision
        updated["review_authority"] = "human"
        updated["reasons"] = [*record["reasons"], reason.strip()]
        updated["review_ids"] = [*record["review_ids"], review_id]
        validate_exemplar(updated)
        _write_atomic(record_path, _canonical_bytes(updated))
        return review

    def list(self, *, domain: str | None = None, classification: str | None = None) -> list[dict[str, Any]]:
        if not self.records.is_dir():
            return []
        results = []
        for path in sorted(self.records.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if domain is not None and record.get("domain") != domain:
                continue
            if classification is not None and record["classification"] != classification:
                continue
            results.append(record)
        return results
