"""Submit one validated collection request to the Hermes Agent job queue."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from _core import (
    ROOT,
    ChannelMakerError,
    content_hash,
    load_json,
    sha256_file,
    write_json_atomic,
)
from _hermes_queue import find_job_path, job_path

REQUIRED_REQUEST_FIELDS = ("mode", "channel_id", "study_id", "target")


def submit(request_path: Path, queue_dir: Path, output: Path | None, metadata: Path | None) -> Path:
    request = load_json(request_path)
    missing = [key for key in REQUIRED_REQUEST_FIELDS if key not in request]
    if missing:
        raise ChannelMakerError(f"collection request is missing required fields: {missing}")
    digest = content_hash({"request_sha256": sha256_file(request_path), "worker": "hermes-agent"})
    job_id = f"hermes-collection:{request['channel_id']}:{request['study_id']}:{digest[:12]}"
    target = job_path(queue_dir / "pending", job_id)
    response = output or job_path(queue_dir / "responses", job_id)
    run_metadata = metadata or job_path(queue_dir / "runs", job_id)
    job = {
        "schema_version": "1.0.0",
        "artifact_type": "hermes_collection_job",
        "job_id": job_id,
        "status": "queued",
        "request_path": str(request_path.resolve()),
        "request_sha256": sha256_file(request_path),
        "response_path": str(response.resolve()),
        "runtime_metadata_path": str(run_metadata.resolve()),
        "submitted_at": datetime.now(UTC).isoformat(),
        "attempt": 0,
    }
    existing_path = find_job_path(queue_dir / "pending", job_id)
    if existing_path is not None:
        existing = load_json(existing_path)
        comparable_keys = job.keys() - {"submitted_at"}
        if {key: existing.get(key) for key in comparable_keys} != {key: job[key] for key in comparable_keys}:
            raise ChannelMakerError(f"refusing to overwrite a different queued job: {existing_path}")
        return existing_path
    write_json_atomic(target, job)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("--queue-dir", type=Path, default=ROOT / "data" / "local" / "hermes-queue")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()
    try:
        print(submit(args.request, args.queue_dir, args.output, args.metadata))
    except ChannelMakerError as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
