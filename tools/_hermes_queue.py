"""Portable storage paths for Hermes queue records."""

from __future__ import annotations

import hashlib
from pathlib import Path

from _core import ChannelMakerError, load_json


def job_filename(job_id: str) -> str:
    digest = hashlib.sha256(job_id.encode("utf-8")).hexdigest()
    return f"hermes-job-{digest}.json"


def job_path(directory: Path, job_id: str) -> Path:
    return directory / job_filename(job_id)


def find_job_path(directory: Path, job_id: str) -> Path | None:
    """Resolve a hashed record, falling back to legacy records by JSON identity."""

    primary = job_path(directory, job_id)
    if primary.is_file():
        return primary
    if not directory.is_dir():
        return None
    for candidate in sorted(directory.glob("*.json")):
        try:
            record = load_json(candidate)
        except ChannelMakerError:
            continue
        if record.get("job_id") == job_id:
            return candidate
    return None
