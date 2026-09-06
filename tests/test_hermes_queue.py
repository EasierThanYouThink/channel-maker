from __future__ import annotations

import hashlib
import json
import os
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


def submitted_job_id(path: Path) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["job_id"])


def test_submit_uses_portable_storage_name_without_changing_job_id(tmp_path: Path) -> None:
    request = build_request(tmp_path / "request.json")

    submitted = submit(request, tmp_path / "queue", None, None)
    job = json.loads(submitted.read_text(encoding="utf-8"))
    digest = hashlib.sha256(job["job_id"].encode("utf-8")).hexdigest()
    expected_name = f"hermes-job-{digest}.json"

    assert job["job_id"].startswith("hermes-collection:")
    assert submitted.name == expected_name
    assert Path(job["response_path"]).name == expected_name
    assert Path(job["runtime_metadata_path"]).name == expected_name


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
    job_id = submitted_job_id(submitted)

    claimed = claim(queue, job_id)
    assert claimed["status"] == "running"
    assert claimed["attempt"] == 1
    assert not submitted.exists()
    assert (queue / "running" / submitted.name).exists()

    with pytest.raises(ChannelMakerError, match="no pending job available"):
        claim(queue, None)


def test_complete_requires_response_and_metadata_present(tmp_path: Path) -> None:
    request = build_request(tmp_path / "request.json")
    queue = tmp_path / "queue"
    submitted = submit(request, queue, None, None)
    job_id = submitted_job_id(submitted)
    claim(queue, job_id)

    with pytest.raises(ChannelMakerError, match="response is missing"):
        complete(queue, job_id)


def test_complete_never_calls_import(tmp_path: Path) -> None:
    """Regression: completing a job must never create CM3 evidence as a side effect."""

    request = build_request(tmp_path / "request.json")
    queue = tmp_path / "queue"
    submitted = submit(request, queue, None, None)
    job_id = submitted_job_id(submitted)
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
    assert (queue / "completed" / submitted.name).exists()
    # No evidence file should exist anywhere under tmp_path as a side effect of `complete`.
    assert not list(tmp_path.rglob("channel_evidence*.json"))
    assert not list(tmp_path.rglob("*evidence*"))


def test_fail_records_error_and_moves_to_failed(tmp_path: Path) -> None:
    request = build_request(tmp_path / "request.json")
    queue = tmp_path / "queue"
    submitted = submit(request, queue, None, None)
    job_id = submitted_job_id(submitted)
    claim(queue, job_id)

    failed = fail(queue, job_id, "hermes CLI returned a non-zero exit code")
    assert failed["status"] == "failed"
    assert failed["error"] == "hermes CLI returned a non-zero exit code"
    assert (queue / "failed" / submitted.name).exists()


def test_claim_next_uses_stored_logical_job_id(tmp_path: Path) -> None:
    request = build_request(tmp_path / "request.json")
    submitted = submit(request, tmp_path / "queue", None, None)

    claimed = claim(tmp_path / "queue", None)

    assert claimed["job_id"] == submitted_job_id(tmp_path / "queue" / "running" / submitted.name)


def test_storage_name_is_bounded_for_hostile_identifiers(tmp_path: Path) -> None:
    request = build_request(tmp_path / "request.json")
    value = json.loads(request.read_text(encoding="utf-8"))
    value["channel_id"] = "../C:\\unsafe:channel?*" + "x" * 300
    value["study_id"] = "..\\study/with|bad<chars>"
    write_json(request, value)
    queue = tmp_path / "queue"

    submitted = submit(request, queue, None, None)
    job = json.loads(submitted.read_text(encoding="utf-8"))

    assert submitted.parent == queue / "pending"
    assert len(submitted.name) == len("hermes-job-") + 64 + len(".json")
    assert not set('<>:"/\\|?*').intersection(submitted.name)
    assert Path(job["response_path"]).parent == (queue / "responses").resolve()
    assert Path(job["runtime_metadata_path"]).parent == (queue / "runs").resolve()


@pytest.mark.skipif(os.name == "nt", reason="Windows cannot create the legacy colon-named file")
def test_legacy_colon_named_job_remains_resolvable(tmp_path: Path) -> None:
    request = build_request(tmp_path / "request.json")
    queue = tmp_path / "queue"
    submitted = submit(request, queue, None, None)
    job_id = submitted_job_id(submitted)
    legacy = queue / "pending" / f"{job_id}.json"
    submitted.replace(legacy)

    assert submit(request, queue, None, None) == legacy
    claimed = claim(queue, job_id)

    assert claimed["job_id"] == job_id
    assert (queue / "running" / legacy.name).is_file()
    write_json(Path(str(claimed["response_path"])), {
        "worker": "claude.hermes_agent",
        "model": "ornith-1.5:9b",
        "prompt_version": "v1",
        "collected_at": "2026-06-30T12:00:00+00:00",
    })
    write_json(Path(str(claimed["runtime_metadata_path"])), {
        "status": "complete",
        "worker": "claude.hermes_agent",
        "runtime": "hermes-agent",
        "model": "ornith-1.5:9b",
        "request_sha256": "x",
        "ended_at": "2026-06-30T12:05:00+00:00",
        "review_required": True,
    })

    completed = complete(queue, job_id)

    assert completed["status"] == "completed"
    assert (queue / "completed" / legacy.name).is_file()


def test_collection_request_supports_competitor_glance(tmp_path: Path) -> None:
    from build_niche_collection_request import build_request as build_collection_request

    output = tmp_path / "request.json"
    build_collection_request(
        channel_id="test-channel", study_id="test-study", target="science shorts",
        sample_size_hint=10,
        allowed_channel_roles=["GROWTH_CANDIDATE", "BASELINE_COMPARATOR"],
        allowed_video_roles=["BREAKOUT", "CHANNEL_BASELINE"],
        output=output,
        reference_channels=["https://www.youtube.com/@somechannel", "@anotherhandle"],
    )
    request = json.loads(output.read_text(encoding="utf-8"))
    assert request["mode"] == "CREATE"
    assert request["reference_channels"] == ["https://www.youtube.com/@somechannel", "@anotherhandle"]


def test_collection_request_caps_reference_channels(tmp_path: Path) -> None:
    from build_niche_collection_request import build_request as build_collection_request

    with pytest.raises(ChannelMakerError, match="at most 3 reference channels"):
        build_collection_request(
            channel_id="test-channel", study_id="test-study", target="science shorts",
            sample_size_hint=10,
            allowed_channel_roles=["GROWTH_CANDIDATE"],
            allowed_video_roles=["BREAKOUT"],
            output=tmp_path / "request.json",
            reference_channels=["@one", "@two", "@three", "@four"],
        )
    with pytest.raises(ChannelMakerError, match="must be a public https:// URL or an @handle"):
        build_collection_request(
            channel_id="test-channel", study_id="test-study", target="science shorts",
            sample_size_hint=10,
            allowed_channel_roles=["GROWTH_CANDIDATE"],
            allowed_video_roles=["BREAKOUT"],
            output=tmp_path / "request.json",
            reference_channels=["not a channel ref"],
        )
