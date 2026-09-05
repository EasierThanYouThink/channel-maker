from __future__ import annotations

import json
from pathlib import Path

import pytest

from _core import ChannelMakerError
from run_hermes_job_queue import claim, complete, fail
from submit_hermes_job import submit


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def build_request(path: Path) -> Path:
    write_json(path, {
        "schema_version": "1.0.0", "artifact_type": "hermes_collection_request",
        "mode": "CREATE", "channel_id": "test-channel", "study_id": "test-study", "target": "science shorts",
    })
    return path


def test_submit_refuses_conflicting_job(tmp_path: Path) -> None:
    request = build_request(tmp_path / "request.json")
    queue = tmp_path / "queue"
    first = submit(request, queue, None, None)
    second = submit(request, queue, None, None)
    assert first == second

    # Force a job_id collision with genuinely different content by mutating the queued job in place.
    job = json.loads(first.read_text(encoding="utf-8"))
    job["status"] = "not-queued-anymore"
    first.write_text(json.dumps(job), encoding="utf-8")
    with pytest.raises(ChannelMakerError, match="refusing to overwrite"):
        submit(request, queue, None, None)


def test_claim_moves_pending_to_running_atomically(tmp_path: Path) -> None:
    request = build_request(tmp_path / "request.json")
    queue = tmp_path / "queue"
    submitted = submit(request, queue, None, None)
    job_id = submitted.stem

    claimed = claim(queue, job_id)
    assert claimed["status"] == "running"
    assert claimed["attempt"] == 1
    assert not (queue / "pending" / f"{job_id}.json").exists()
    assert (queue / "running" / f"{job_id}.json").exists()

    with pytest.raises(ChannelMakerError, match="no pending job available"):
        claim(queue, None)


def test_complete_requires_response_and_metadata_present(tmp_path: Path) -> None:
    request = build_request(tmp_path / "request.json")
    queue = tmp_path / "queue"
    submitted = submit(request, queue, None, None)
    job_id = submitted.stem
    claim(queue, job_id)

    with pytest.raises(ChannelMakerError, match="response is missing"):
        complete(queue, job_id)


def test_complete_never_calls_import(tmp_path: Path) -> None:
    """Regression: completing a job must never create CM3 evidence as a side effect."""

    request = build_request(tmp_path / "request.json")
    queue = tmp_path / "queue"
    submitted = submit(request, queue, None, None)
    job_id = submitted.stem
    claimed = claim(queue, job_id)

    write_json(Path(str(claimed["response_path"])), {
        "worker": "claude.hermes_agent", "model": "ornith-1.5:9b", "model_version": "abc",
        "prompt_version": "v1", "collected_at": "2026-06-30T12:00:00+00:00",
        "channels": [{"source_id": "uc-x", "url": "https://www.youtube.com/channel/uc-x", "channel_name": "X",
                      "sample_role": "GROWTH_CANDIDATE", "sample_rationale": "r",
                      "public_fields": {"subscriber_count": 1, "public_video_count": 1, "created_at": None,
                                        "observed_uploads_per_30d": 1.0, "shorts_fraction": 1.0}}],
        "videos": [],
    })
    write_json(Path(str(claimed["runtime_metadata_path"])), {
        "status": "complete", "worker": "claude.hermes_agent", "runtime": "hermes-agent",
        "model": "ornith-1.5:9b", "request_sha256": "x", "ended_at": "2026-06-30T12:05:00+00:00",
        "review_required": True,
    })

    completed = complete(queue, job_id)
    assert completed["status"] == "completed"
    assert (queue / "completed" / f"{job_id}.json").exists()
    # No evidence file should exist anywhere under tmp_path as a side effect of `complete`.
    assert not list(tmp_path.rglob("channel_evidence*.json"))
    assert not list(tmp_path.rglob("*evidence*"))


def test_fail_records_error_and_moves_to_failed(tmp_path: Path) -> None:
    request = build_request(tmp_path / "request.json")
    queue = tmp_path / "queue"
    submitted = submit(request, queue, None, None)
    job_id = submitted.stem
    claim(queue, job_id)

    failed = fail(queue, job_id, "hermes CLI returned a non-zero exit code")
    assert failed["status"] == "failed"
    assert failed["error"] == "hermes CLI returned a non-zero exit code"
    assert (queue / "failed" / f"{job_id}.json").exists()
