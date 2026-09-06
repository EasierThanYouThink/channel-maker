"""Channel identity candidates: a logo (image) or an About-page description (text), each with
an approve/reject/borderline human review flow. See `docs/CHANNEL_IDENTITY.md`.
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
    IdentityValidationError,
    validate_identity_candidate,
    validate_identity_candidate_review,
)


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise IdentityValidationError("title must contain at least one letter or number")
    return slug


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        if path.read_bytes() != payload:
            raise IdentityValidationError(f"refusing to overwrite existing record {path}") from exc


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


class ChannelIdentityStore:
    """One channel's identity candidates, at `channels/<id>/identity/candidates/`."""

    def __init__(self, root: Path, channel_id: str):
        self.root = root.resolve()
        self.channel_id = channel_id
        self.base = self.root / "channels" / channel_id / "identity" / "candidates"
        self.assets = self.base / "assets"
        self.records = self.base / "records"
        self.reviews = self.base / "reviews"

    def add(
        self,
        *,
        domain: str,
        title: str,
        provenance_kind: str,
        created_by: str,
        source_ref: str,
        image: Path | None = None,
        text: str | None = None,
        model: str | None = None,
        model_version: str | None = None,
        prompt_ref: str | None = None,
    ) -> dict[str, Any]:
        if domain == "logo":
            if image is None or text is not None:
                raise IdentityValidationError("a logo candidate requires an image and no text")
            image = image.resolve()
            if not image.is_file():
                raise IdentityValidationError(f"identity candidate image does not exist: {image}")
            media_type, _ = mimetypes.guess_type(image.name)
            allowed = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
            if media_type not in allowed:
                raise IdentityValidationError("a logo candidate must be PNG, JPEG, or WebP")
            content_hash = _sha256_file(image)
        elif domain == "description":
            if text is None or image is not None:
                raise IdentityValidationError("a description candidate requires text and no image")
            text = text.strip()
            if not text:
                raise IdentityValidationError("a description candidate's text must not be empty")
            content_hash = _sha256_bytes(text.encode("utf-8"))
        else:
            raise IdentityValidationError(f"unknown identity domain: {domain!r}")
        if provenance_kind == "ai_generated_original" and not all((model, model_version, prompt_ref)):
            raise IdentityValidationError("AI-generated candidates require model, model_version, and prompt_ref")

        candidate_id = f"identity-candidate:{domain}-{_slug(title)}-{content_hash[:8]}"
        provenance: dict[str, Any] = {"kind": provenance_kind, "created_by": created_by, "source_ref": source_ref}
        if model:
            provenance["model"] = model
        if model_version:
            provenance["model_version"] = model_version
        if prompt_ref:
            provenance["prompt_ref"] = prompt_ref

        record: dict[str, Any] = {
            "schema_version": "1.0.0", "artifact_type": "identity_candidate", "candidate_id": candidate_id,
            "channel_id": self.channel_id, "domain": domain, "title": title.strip(),
            "classification": "experimental", "review_authority": "unreviewed", "reasons": [],
            "provenance": provenance, "review_ids": [],
        }
        if domain == "logo":
            asset_path = self.assets / f"{content_hash}{allowed[media_type]}"
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            if asset_path.exists() and _sha256_file(asset_path) != content_hash:
                raise IdentityValidationError(f"asset hash collision at {asset_path}")
            if not asset_path.exists():
                temporary = asset_path.with_suffix(asset_path.suffix + ".tmp")
                shutil.copyfile(image, temporary)
                temporary.replace(asset_path)
            record["asset"] = {"path": asset_path.relative_to(self.root).as_posix(), "sha256": content_hash, "media_type": media_type}
        else:
            record["text"] = text

        validate_identity_candidate(record)
        _write_new(self.records / f"{candidate_id.removeprefix('identity-candidate:')}.json", _canonical_bytes(record))
        return record

    def review(
        self,
        candidate_id: str,
        *,
        decision: str,
        reviewer: str,
        reason: str,
        created_at: str,
        human_confirmed: bool,
    ) -> dict[str, Any]:
        if not human_confirmed:
            raise IdentityValidationError("identity candidate classification requires an explicit human confirmation")
        record_path = self.records / f"{candidate_id.removeprefix('identity-candidate:')}.json"
        try:
            record_bytes = record_path.read_bytes()
            record = json.loads(record_bytes)
        except (OSError, json.JSONDecodeError) as exc:
            raise IdentityValidationError(f"cannot read identity candidate {candidate_id}: {exc}") from exc
        validate_identity_candidate(record)
        target_sha256 = hashlib.sha256(record_bytes).hexdigest()
        seed = {
            "schema_version": "1.0.0", "artifact_type": "identity_candidate_review", "candidate_id": candidate_id,
            "target_sha256": target_sha256, "decision": decision, "reviewer": reviewer.strip(),
            "reason": reason.strip(), "created_at": created_at,
        }
        review_id = f"identity-candidate-review:{hashlib.sha256(_canonical_bytes(seed)).hexdigest()[:16]}"
        review = {**seed, "review_id": review_id}
        validate_identity_candidate_review(review)
        _write_new(self.reviews / f"{review_id.removeprefix('identity-candidate-review:')}.json", _canonical_bytes(review))

        updated = dict(record)
        updated["classification"] = decision
        updated["review_authority"] = "human"
        updated["reasons"] = [*record["reasons"], reason.strip()]
        updated["review_ids"] = [*record["review_ids"], review_id]
        validate_identity_candidate(updated)
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
