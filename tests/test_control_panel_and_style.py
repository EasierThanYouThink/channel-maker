"""Tests for the creator control panel, style loop, and portable platform helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def write_package(root: Path, channel_id: str = "panel-chan") -> Path:
    package = root / "channels" / channel_id
    package.mkdir(parents=True)
    identity = {
        "schema_version": "0.1.0", "id": channel_id, "name": channel_id.title(), "version": "0.1.0",
        "status": "DRAFT", "language": "en", "niche": {"primary": "science"},
        "platform": {"primary": "YOUTUBE", "formats": ["SHORTS"]},
        "production": {"archetype": "ILLUSTRATED_EXPLAINER", "renderer": "remotion"},
        "creation": {"mode": "ORIGINAL"},
        "canonical_sources": {"channel_state": f"channels/{channel_id}/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.2.0", "channel_id": channel_id, "revision": 0, "state": "CHANNEL_INIT",
        "status": "ACTIVE", "completed": [], "active_experiment": None, "waiting_for": None,
        "blocker": None, "next_action": "Begin.", "resume_state": None,
        "source_refs": [f"channels/{channel_id}/channel.yaml"], "known_gaps": [],
        "legacy_mapping": False, "events": [], "updated_at": "2026-09-05T12:00:00+00:00",
    }
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    contracts = root / "engine" / "memory" / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        ROOT / "engine" / "memory" / "contracts" / "wiki-page.schema.json",
        contracts / "wiki-page.schema.json",
    )
    return package


def test_channel_overview_snapshot(tmp_path: Path) -> None:
    from tools.dashboard.views import channel_overview

    package = write_package(tmp_path)
    overview = channel_overview(tmp_path, package.name)
    assert overview["header"]["channel_id"] == "panel-chan"
    assert overview["progress"]["position"] == 1
    assert overview["progress"]["total"] == 15
    assert overview["next_allowed_action"]["forward_state"] == "NICHE_INTELLIGENCE"
    assert overview["review_counts"]["script_examples"] == 0
    assert overview["style_pages"] == {"voice": False, "visual": False, "motion": False, "index": False}
    assert overview["vault"]["vault_path"] == f"channels/{package.name}/"
    assert overview["vault"]["obsidian_url"] == f"obsidian://open?vault={package.name}"
    assert overview["vault"]["recent_pages"] == []
    assert overview["pilots"] == [] and overview["episodes"] == []
    assert "hermes" in overview["services"]
    assert overview["wiki_links"]["style"] == f"channels/{package.name}/wiki/style/index.md"


def test_style_sync_and_status(tmp_path: Path) -> None:
    from tools.channel_style import collect, sync

    package = write_package(tmp_path)
    outcomes = sync(package, tmp_path)
    assert set(outcomes) == {"index", "voice", "visual", "motion"}
    assert all(value == "wrote" for value in outcomes.values())
    # Second run without --force skips.
    again = sync(package, tmp_path)
    assert all("exists" in value for value in again.values())
    # --force refreshes.
    refreshed = sync(package, tmp_path, force=True)
    assert all(value == "refreshed" for value in refreshed.values())
    facts = collect(package, tmp_path)
    assert facts["channel_id"] == "panel-chan"
    # Style pages validate as channel memory.
    from engine.memory import ChannelMemoryRepository

    docs = ChannelMemoryRepository(tmp_path).documents()
    assert {d.knowledge_id for d in docs} >= {
        f"wiki:channel/{package.name}/style-{name}" for name in ("index", "voice", "visual", "motion")
    }


def test_portable_lock_and_write(tmp_path: Path) -> None:
    from engine.channel._portable import file_lock, write_bytes_atomic, write_json_atomic

    target = tmp_path / "doc.json"
    write_json_atomic(target, {"b": 1, "a": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2, "b": 1}
    lock = tmp_path / "test.lock"
    with file_lock(lock):
        write_bytes_atomic(tmp_path / "note.bin", b"hello")


def test_setup_check_only() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "setup.py"), "--check-only"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0
    assert "hermes" in result.stdout and "ollama" in result.stdout


def test_setup_check_only_json() -> None:
    import json as _json

    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "setup.py"), "--check-only", "--json"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0
    report = _json.loads(result.stdout)
    assert report["services"]["hermes"]["available"] in (True, False)
    assert "ollama" in report["services"] and "piper_tts" in report["services"]
    assert "venv_present" in report and "project_python" in report


def test_dashboard_overview_page(tmp_path: Path) -> None:
    write_package(tmp_path, "panel-chan")
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.');"
         "from pathlib import Path;"
         "import tools.dashboard.server as server;"
         f"server.ROOT = Path({str(tmp_path)!r});"
         "print(len(server._overview_page('panel-chan')))"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) > 1000
