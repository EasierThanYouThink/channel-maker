"""System proofs: the composed visual frame and the narrated motion sample.

Per-domain exemplars can each look right and still clash as a system. Before
a DNA seed counts as ready, the channel must prove the whole system at once:

- visual: one composed frame showing the frozen domains together
  (`design/composition-check.json`), grounded in approved exemplars and
  human-approved;
- motion: one narrated sample (`motion/motion-sample.json`) — a container
  -valid video clip bound to an existing narration ref (script or timing),
  human-approved.

Both records mirror the exemplar review flow: experimental on record,
human-confirmed approve/reject/borderline bound to the record bytes, and
`check_ready` refuses to pass without an approval.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.channel import ChannelValidationError, validate_channel_package
from engine.production.probing import probe_file

from .exemplars import ChannelExemplarStore
from .validation import DesignValidationError


def _timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


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


def _load_package(package_root: Path, repository_root: Path):
    try:
        return validate_channel_package(package_root.resolve(), repository_root.resolve())
    except ChannelValidationError as exc:
        raise DesignValidationError(str(exc)) from exc


def composition_path(package_root: Path) -> Path:
    return package_root / "design" / "composition-check.json"


def motion_sample_path(package_root: Path) -> Path:
    return package_root / "motion" / "motion-sample.json"


def _read_record(path: Path, what: str) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DesignValidationError(f"cannot read {what} {path}: {exc}") from exc
    if not isinstance(record, dict):
        raise DesignValidationError(f"{what} {path} must be a JSON object")
    return record


def _copy_asset(source: Path, assets_dir: Path, *, suffix: str) -> tuple[str, str]:
    digest = _sha256(source)
    target = assets_dir / f"{digest}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and _sha256(target) != digest:
        raise DesignValidationError(f"asset hash collision at {target}")
    if not target.exists():
        temporary = target.with_suffix(target.suffix + ".tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(target)
    return digest, target


def record_composition(
    package_root: Path,
    repository_root: Path,
    *,
    image: Path,
    exemplar_ids: list[str],
    created_by: str,
    source_ref: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Record the composed system frame. Requires a structurally valid PNG
    and at least one approved exemplar grounding the composition."""
    package = _load_package(package_root, repository_root)
    repository_root = repository_root.resolve()
    image = image.resolve()
    if not image.is_file() or image.suffix.lower() != ".png":
        raise DesignValidationError(f"composition frame must be an existing PNG image: {image}")
    probe = probe_file(image)
    if probe["problems"]:
        raise DesignValidationError("; ".join(probe["problems"]))
    if not exemplar_ids:
        raise DesignValidationError("a composition check must ground at least one approved exemplar")
    if not created_by.strip() or not source_ref.strip():
        raise DesignValidationError("a composition check needs a creator and a source ref")
    store = ChannelExemplarStore(repository_root, package.identity["id"])
    for exemplar_id in exemplar_ids:
        record_path = store.records / f"{exemplar_id.removeprefix('exemplar:')}.json"
        if not record_path.is_file():
            raise DesignValidationError(f"no exemplar record found for {exemplar_id}")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("classification") != "approved":
            raise DesignValidationError(
                f"exemplar {exemplar_id} is {record.get('classification')!r}; "
                "a composition check grounds approved exemplars only"
            )
    digest, asset_path = _copy_asset(image, package.root / "design" / "composition-assets", suffix=".png")
    record = {
        "schema_version": "1.0.0", "artifact_type": "composition_check",
        "artifact_id": f"composition:{package.identity['id']}:{digest[:12]}",
        "channel_id": package.identity["id"],
        "asset": {"path": asset_path.relative_to(repository_root).as_posix(), "sha256": digest, "media_type": "image/png"},
        "exemplar_ids": sorted(set(exemplar_ids)),
        "classification": "experimental", "review_authority": "unreviewed", "reasons": [],
        "provenance": {"created_by": created_by.strip(), "source_ref": source_ref.strip()},
        "review_ids": [],
        "created_by": {
            "created_at": _timestamp(created_at), "creator": "TOOL",
            "tool": "engine.design.system_proof.record_composition", "version": "1.0.0",
        },
    }
    _write_new(composition_path(package.root), _canonical_bytes(record))
    return record


def record_motion_sample(
    package_root: Path,
    repository_root: Path,
    *,
    video: Path,
    narration_ref: str,
    created_by: str,
    source_ref: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Record the narrated motion sample. Requires a container-valid MP4 and
    a narration ref resolving to an existing repo file (script or timing) —
    a silent clip is not a motion proof."""
    package = _load_package(package_root, repository_root)
    repository_root = repository_root.resolve()
    video = video.resolve()
    if not video.is_file() or video.suffix.lower() != ".mp4":
        raise DesignValidationError(f"motion sample must be an existing MP4 file: {video}")
    probe = probe_file(video)
    if probe["problems"]:
        raise DesignValidationError("; ".join(probe["problems"]))
    if not narration_ref.strip():
        raise DesignValidationError("a motion sample requires a narration ref (script or timing)")
    resolved = (repository_root / narration_ref).resolve()
    if not resolved.is_relative_to(repository_root) or not resolved.is_file():
        raise DesignValidationError(f"narration_ref does not resolve to an existing repository file: {narration_ref}")
    if not created_by.strip() or not source_ref.strip():
        raise DesignValidationError("a motion sample needs a creator and a source ref")
    digest, asset_path = _copy_asset(video, package.root / "motion" / "sample-assets", suffix=".mp4")
    record = {
        "schema_version": "1.0.0", "artifact_type": "motion_sample",
        "artifact_id": f"motion-sample:{package.identity['id']}:{digest[:12]}",
        "channel_id": package.identity["id"],
        "asset": {"path": asset_path.relative_to(repository_root).as_posix(), "sha256": digest, "media_type": "video/mp4"},
        "narration_ref": narration_ref,
        "classification": "experimental", "review_authority": "unreviewed", "reasons": [],
        "provenance": {"created_by": created_by.strip(), "source_ref": source_ref.strip()},
        "review_ids": [],
        "created_by": {
            "created_at": _timestamp(created_at), "creator": "TOOL",
            "tool": "engine.design.system_proof.record_motion_sample", "version": "1.0.0",
        },
    }
    _write_new(motion_sample_path(package.root), _canonical_bytes(record))
    return record


def _review(
    package_root: Path,
    repository_root: Path,
    record_path: Path,
    *,
    decision: str,
    reviewer: str,
    reason: str,
    created_at: str | None,
    human_confirmed: bool,
) -> dict[str, Any]:
    if decision not in {"approved", "rejected", "borderline"}:
        raise DesignValidationError(f"unknown system-proof decision {decision!r}")
    if not human_confirmed:
        raise DesignValidationError("system-proof classification requires an explicit human confirmation")
    if not reviewer.strip() or not reason.strip():
        raise DesignValidationError("a system-proof review needs a reviewer and a reason")
    _load_package(package_root, repository_root)
    try:
        record_bytes = record_path.read_bytes()
        record = json.loads(record_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise DesignValidationError(f"cannot read system proof {record_path}: {exc}") from exc
    if record.get("classification") == "approved":
        raise DesignValidationError(f"system proof {record_path} is already approved")
    seed = {
        "schema_version": "1.0.0", "artifact_type": "system_proof_review",
        "target": record["artifact_id"], "target_sha256": hashlib.sha256(record_bytes).hexdigest(),
        "decision": decision, "reviewer": reviewer.strip(), "reason": reason.strip(),
        "created_at": _timestamp(created_at),
    }
    review_id = f"system-proof-review:{hashlib.sha256(_canonical_bytes(seed)).hexdigest()[:16]}"
    review = {**seed, "review_id": review_id}
    _write_new(record_path.parent / "reviews" / f"{review_id.removeprefix('system-proof-review:')}.json", _canonical_bytes(review))
    updated = dict(record)
    updated["classification"] = decision
    updated["review_authority"] = "human"
    updated["reasons"] = [*record.get("reasons", []), reason.strip()]
    updated["review_ids"] = [*record.get("review_ids", []), review_id]
    _write_atomic(record_path, _canonical_bytes(updated))
    return review


def review_composition(
    package_root: Path, repository_root: Path, *, decision: str, reviewer: str,
    reason: str, created_at: str | None = None, human_confirmed: bool = False,
) -> dict[str, Any]:
    package = _load_package(package_root, repository_root)
    return _review(
        package.root, repository_root, composition_path(package.root),
        decision=decision, reviewer=reviewer, reason=reason,
        created_at=created_at, human_confirmed=human_confirmed,
    )


def review_motion_sample(
    package_root: Path, repository_root: Path, *, decision: str, reviewer: str,
    reason: str, created_at: str | None = None, human_confirmed: bool = False,
) -> dict[str, Any]:
    package = _load_package(package_root, repository_root)
    return _review(
        package.root, repository_root, motion_sample_path(package.root),
        decision=decision, reviewer=reviewer, reason=reason,
        created_at=created_at, human_confirmed=human_confirmed,
    )


def approved_composition(package_root: Path) -> bool:
    path = composition_path(package_root)
    if not path.is_file():
        return False
    try:
        return _read_record(path, "composition check").get("classification") == "approved"
    except DesignValidationError:
        return False


def approved_motion_sample(package_root: Path) -> bool:
    path = motion_sample_path(package_root)
    if not path.is_file():
        return False
    try:
        return _read_record(path, "motion sample").get("classification") == "approved"
    except DesignValidationError:
        return False


def check_ready_problems(kind: str, package_root: Path, repository_root: Path) -> list[str]:
    """System-level readiness beyond per-domain freezes: visual needs the
    approved composed frame, motion needs the approved narrated sample."""
    import yaml

    from .dna_seed import all_domains_frozen as _frozen
    from .dna_seed import seed_path as _seed_path

    package = _load_package(package_root, repository_root)
    problems: list[str] = []
    seed_file = _seed_path(kind, package.root)
    if not seed_file.is_file():
        return [f"{kind} DNA seed is missing: run design_dna.py {kind} init first"]
    document = yaml.safe_load(seed_file.read_text(encoding="utf-8"))
    unfrozen = [domain for domain, gate in document["domains"].items() if gate["authority_status"] != "FROZEN"]
    if unfrozen:
        problems.append(f"unfrozen {kind} domains: {unfrozen}")
    if kind == "visual" and _frozen(kind, document) and not approved_composition(package.root):
        problems.append("no approved composed system frame: record and review the composition check first")
    if kind == "motion" and _frozen(kind, document) and not approved_motion_sample(package.root):
        problems.append("no approved narrated motion sample: record and review the motion sample first")
    return problems
