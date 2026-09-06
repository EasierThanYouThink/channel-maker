from __future__ import annotations

import http.client
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from tools.dashboard.actions import ActionError, run_action
from tools.dashboard.markdown import render as render_markdown
from tools.dashboard.server import ACTION_TOKEN, ACTION_TOKEN_HEADER, Handler
from tools.dashboard.views import channel_detail, list_channels, review_queue

AT = "2026-09-05T12:00:00+00:00"


@contextmanager
def running_dashboard():
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def post_action(server, payload: dict, *, headers: dict[str, str] | None = None):
    connection = http.client.HTTPConnection(*server.server_address)
    body = json.dumps(payload)
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    connection.request("POST", "/action", body=body, headers=request_headers)
    response = connection.getresponse()
    response_body = json.loads(response.read())
    connection.close()
    return response.status, response_body


def raw_post_action(server, body: str, *, headers: dict[str, str]):
    connection = http.client.HTTPConnection(*server.server_address)
    connection.request("POST", "/action", body=body, headers=headers)
    response = connection.getresponse()
    response_body = json.loads(response.read())
    connection.close()
    return response.status, response_body


def write_package(root: Path, channel_id: str = "dash-channel") -> Path:
    package = root / "channels" / channel_id
    package.mkdir(parents=True)
    identity = {
        "schema_version": "0.1.0", "id": channel_id, "name": "Dash Channel", "version": "0.1.0",
        "status": "DRAFT", "language": "en", "niche": {"primary": "science"},
        "platform": {"primary": "YOUTUBE", "formats": ["SHORTS"]},
        "production": {"archetype": "ILLUSTRATED_EXPLAINER", "renderer": "remotion"},
        "creation": {"mode": "ORIGINAL"},
        "canonical_sources": {"channel_state": f"channels/{channel_id}/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.2.0", "channel_id": channel_id, "revision": 0, "state": "CHANNEL_INIT",
        "status": "ACTIVE", "completed": [], "active_experiment": None, "waiting_for": None,
        "blocker": None, "next_action": "test", "resume_state": None,
        "source_refs": [f"channels/{channel_id}/channel.yaml"], "known_gaps": [],
        "legacy_mapping": False, "events": [], "updated_at": AT,
    }
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    return package


def test_list_channels_and_channel_detail(tmp_path: Path) -> None:
    write_package(tmp_path)
    channels = list_channels(tmp_path)
    assert len(channels) == 1
    assert channels[0]["channel_id"] == "dash-channel"
    assert channels[0]["state"] == "CHANNEL_INIT"

    detail = channel_detail(tmp_path, "dash-channel")
    assert detail["identity"]["id"] == "dash-channel"
    assert "advance" in detail["next_allowed_action"]["allowed_operations"]


def test_review_queue_finds_experimental_records(tmp_path: Path) -> None:
    write_package(tmp_path)
    record_dir = tmp_path / "channels" / "dash-channel" / "script" / "examples" / "records"
    record_dir.mkdir(parents=True)
    (record_dir / "one.json").write_text(json.dumps({"classification": "experimental", "example_id": "script-example:one"}), encoding="utf-8")
    (record_dir / "two.json").write_text(json.dumps({"classification": "approved", "example_id": "script-example:two"}), encoding="utf-8")
    queue = review_queue(tmp_path)
    assert len(queue["script_examples"]) == 1
    assert queue["script_examples"][0]["example_id"] == "script-example:one"


def test_run_action_rejects_unknown_action() -> None:
    with pytest.raises(ActionError, match="unknown dashboard action"):
        run_action("does-not-exist", {}, confirmed=False)


def test_run_action_requires_confirmation_for_gated_actions() -> None:
    with pytest.raises(ActionError, match="requires explicit confirmation"):
        run_action("abandon", {"package_root": "channels/x", "decision_ref": "r", "reason": "r", "actor": "Seb"}, confirmed=False)


def test_run_action_requires_named_confirmer_for_gated_actions() -> None:
    with pytest.raises(ActionError, match="non-empty 'actor'"):
        run_action("abandon", {"package_root": "channels/x", "decision_ref": "r", "reason": "r", "actor": ""}, confirmed=True)


def test_run_action_never_uses_a_shell_string(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    result = run_action(
        "advance",
        {"package_root": str(package.relative_to(tmp_path)), "target": "NICHE_INTELLIGENCE", "next_action": "n", "actor": "Seb", "reason": "r"},
        confirmed=False,
        repository_root=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    document = json.loads((package / "CHANNEL_STATE.json").read_text(encoding="utf-8"))
    assert document["state"] == "NICHE_INTELLIGENCE"


def test_dashboard_rejects_action_without_process_token() -> None:
    result = SimpleNamespace(returncode=0, stdout="", stderr="")
    with (
        patch("tools.dashboard.server.run_action", return_value=result) as dispatch,
        running_dashboard() as server,
    ):
        status, body = post_action(
            server,
            {"action": "advance", "params": {}, "confirmed": True},
        )

    assert status == 403
    assert "token" in body["error"]
    dispatch.assert_not_called()


def test_dashboard_rejects_cross_origin_action_with_valid_token() -> None:
    result = SimpleNamespace(returncode=0, stdout="", stderr="")
    with (
        patch("tools.dashboard.server.run_action", return_value=result) as dispatch,
        running_dashboard() as server,
    ):
        status, body = post_action(
            server,
            {"action": "advance", "params": {}, "confirmed": True},
            headers={
                ACTION_TOKEN_HEADER: ACTION_TOKEN,
                "Origin": "https://attacker.example",
            },
        )

    assert status == 403
    assert "origin" in body["error"]
    dispatch.assert_not_called()


def test_dashboard_rejects_non_json_action_with_valid_token() -> None:
    result = SimpleNamespace(returncode=0, stdout="", stderr="")
    payload = json.dumps({"action": "advance", "params": {}, "confirmed": True})
    with (
        patch("tools.dashboard.server.run_action", return_value=result) as dispatch,
        running_dashboard() as server,
    ):
        status, body = raw_post_action(
            server,
            payload,
            headers={
                "Content-Type": "text/plain",
                ACTION_TOKEN_HEADER: ACTION_TOKEN,
            },
        )

    assert status == 415
    assert "application/json" in body["error"]
    dispatch.assert_not_called()


def test_render_markdown_handles_headings_lists_and_code() -> None:
    body = "# Title\n\nSome text.\n\n- one\n- two\n\n```\ncode line\n```\n"
    output = render_markdown(body)
    assert "<h1>Title</h1>" in output
    assert "<li>one</li>" in output
    assert "<pre>" in output and "code line" in output


def test_review_queue_keeps_revise_visible_until_resolved(tmp_path: Path) -> None:
    from engine.episode import episode_path, plan_episode
    from engine.pilot import pilot_path, plan_pilot

    package = write_package(tmp_path)
    plan_pilot(package, tmp_path, pilot_id="pilot-1", topic="t",
               target_duration_seconds=25.0, integration_goals=["g"])
    pilot_doc = json.loads(pilot_path(package, "pilot-1").read_text(encoding="utf-8"))
    pilot_doc["review"]["decision"] = "REVISE"
    pilot_doc["review"]["revise_target"] = "PILOT_PRODUCTION"
    (package / "pilots" / "pilot-1" / "pilot.json").write_text(json.dumps(pilot_doc), encoding="utf-8")
    plan_episode(package, tmp_path, episode_id="ep-1", topic="t", target_duration_seconds=25.0)
    episode_doc = json.loads(episode_path(package, "ep-1").read_text(encoding="utf-8"))
    episode_doc["review"]["decision"] = "REVISE"
    (package / "episodes" / "ep-1" / "episode.json").write_text(json.dumps(episode_doc), encoding="utf-8")
    queue = review_queue(tmp_path)
    assert [item["pilot_id"] for item in queue["pilots"]] == ["pilot-1"]
    assert [item["episode_id"] for item in queue["episodes"]] == ["ep-1"]
