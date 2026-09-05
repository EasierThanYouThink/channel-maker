"""Claim and complete Hermes Agent collection jobs.

Unlike the persistent Ollama annotation queue, this queue has no `--watch`
daemon: the worker is a live conversational agent (Claude driving Hermes Agent
via Bash), not a background subprocess. `claim` hands a job to that agent,
`complete`/`fail` record the outcome. Neither ever imports the response into a
canonical CM3 artifact — see `tools/niche_intelligence.py import-evidence`,
which is always a second, separately-invoked, human-reviewed step.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from _core import ROOT, ChannelMakerError, load_json, write_json_atomic


RESPONSE_REQUIRED_FIELDS = ("worker", "model", "prompt_version", "collected_at")
METADATA_REQUIRED_FIELDS = ("status", "worker", "runtime", "model", "request_sha256", "ended_at", "review_required")


def claim(queue_dir: Path, job_id: str | None) -> dict[str, object]:
    pending = queue_dir / "pending"
    running = queue_dir / "running"
    pending.mkdir(parents=True, exist_ok=True)
    running.mkdir(parents=True, exist_ok=True)
    if job_id is not None:
        candidates = [pending / f"{job_id}.json"]
    else:
        candidates = sorted(pending.glob("*.json"))
    for candidate in candidates:
        if not candidate.is_file():
            continue
        claimed = running / candidate.name
        try:
            os.replace(candidate, claimed)
        except FileNotFoundError:
            continue
        job = load_json(claimed)
        job.update({
            "status": "running",
            "attempt": int(job.get("attempt", 0)) + 1,
            "started_at": datetime.now(UTC).isoformat(),
        })
        write_json_atomic(claimed, job)
        return job
    raise ChannelMakerError("no pending job available to claim" if job_id is None else f"pending job not found: {job_id}")


def complete(queue_dir: Path, job_id: str) -> dict[str, object]:
    running_path = queue_dir / "running" / f"{job_id}.json"
    if not running_path.is_file():
        raise ChannelMakerError(f"job is not running: {job_id}")
    job = load_json(running_path)

    response_path = Path(str(job["response_path"]))
    metadata_path = Path(str(job["runtime_metadata_path"]))
    if not response_path.is_file():
        raise ChannelMakerError(f"job response is missing: {response_path}")
    if not metadata_path.is_file():
        raise ChannelMakerError(f"job runtime metadata is missing: {metadata_path}")
    response = load_json(response_path)
    metadata = load_json(metadata_path)
    missing_response = [key for key in RESPONSE_REQUIRED_FIELDS if not response.get(key)]
    if missing_response:
        raise ChannelMakerError(f"job response is missing required fields: {missing_response}")
    missing_metadata = [key for key in METADATA_REQUIRED_FIELDS if key not in metadata]
    if missing_metadata:
        raise ChannelMakerError(f"job runtime metadata is missing required fields: {missing_metadata}")

    job.update({"status": "completed", "ended_at": datetime.now(UTC).isoformat(), "error": None})
    terminal = queue_dir / "completed" / running_path.name
    terminal.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(running_path, job)
    os.replace(running_path, terminal)
    return job


def fail(queue_dir: Path, job_id: str, error: str) -> dict[str, object]:
    running_path = queue_dir / "running" / f"{job_id}.json"
    if not running_path.is_file():
        raise ChannelMakerError(f"job is not running: {job_id}")
    job = load_json(running_path)
    job.update({"status": "failed", "ended_at": datetime.now(UTC).isoformat(), "error": error})
    terminal = queue_dir / "failed" / running_path.name
    terminal.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(running_path, job)
    os.replace(running_path, terminal)
    return job


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-dir", type=Path, default=ROOT / "data" / "local" / "hermes-queue")
    subparsers = parser.add_subparsers(dest="command", required=True)

    claim_parser = subparsers.add_parser("claim")
    group = claim_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--job-id")
    group.add_argument("--next", action="store_true")

    complete_parser = subparsers.add_parser("complete")
    complete_parser.add_argument("job_id")

    fail_parser = subparsers.add_parser("fail")
    fail_parser.add_argument("job_id")
    fail_parser.add_argument("--error", required=True)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "claim":
            job = claim(args.queue_dir, None if args.next else args.job_id)
        elif args.command == "complete":
            job = complete(args.queue_dir, args.job_id)
        else:
            job = fail(args.queue_dir, args.job_id, args.error)
    except ChannelMakerError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps(job, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
