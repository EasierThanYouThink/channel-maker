from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from engine.channel import ChannelValidationError, validate_channel_package


ROOT = Path(__file__).resolve().parents[1]


def write_package(
    root: Path,
    *,
    channel_id: str = "synthetic",
    archetype: str = "ILLUSTRATED_EXPLAINER",
    mode: str = "ORIGINAL",
) -> Path:
    package = root / "channels" / channel_id
    package.mkdir(parents=True)
    identity = {
        "schema_version": "0.1.0",
        "id": channel_id,
        "name": channel_id.title(),
        "version": "0.1.0",
        "status": "DRAFT",
        "language": "en",
        "niche": {"primary": "synthetic-test"},
        "platform": {"primary": "YOUTUBE", "formats": ["SHORTS"]},
        "production": {"archetype": archetype, "renderer": "remotion"},
        "creation": {"mode": mode},
        "canonical_sources": {"channel_state": f"channels/{channel_id}/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.1.0",
        "channel_id": channel_id,
        "revision": 0,
        "state": "CHANNEL_INIT",
        "status": "ACTIVE",
        "completed": [],
        "active_experiment": None,
        "waiting_for": None,
        "blocker": None,
        "next_action": "Collect minimum channel identity.",
        "resume_state": None,
        "source_refs": [f"channels/{channel_id}/channel.yaml"],
        "known_gaps": [],
        "updated_at": "2026-08-23T12:00:00+00:00",
    }
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    return package


def load_identity(package: Path) -> dict:
    return yaml.safe_load((package / "channel.yaml").read_text(encoding="utf-8"))


def load_state(package: Path) -> dict:
    return json.loads((package / "CHANNEL_STATE.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("channel_id", "archetype", "mode"),
    [
        ("science-demo", "ILLUSTRATED_EXPLAINER", "ORIGINAL"),
        ("finance-demo", "DATA_STORY", "ORIGINAL"),
        ("history-demo", "MAP_STORY", "ORIGINAL"),
    ],
)
def test_contract_is_not_radicat_specific(
    tmp_path: Path, channel_id: str, archetype: str, mode: str
) -> None:
    package = write_package(tmp_path, channel_id=channel_id, archetype=archetype, mode=mode)
    value = validate_channel_package(package, tmp_path)
    assert value.identity["id"] == channel_id


def test_blocked_channel_requires_human_blocker_and_resume_state(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    state = load_state(package)
    state.update({
        "status": "BLOCKED_ON_HUMAN",
        "waiting_for": "human choice",
        "resume_state": "CHANNEL_INIT",
    })
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ChannelValidationError, match="blocker"):
        validate_channel_package(package, tmp_path)


def test_package_and_state_ids_must_match_identity(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    state = load_state(package)
    state["channel_id"] = "different"
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ChannelValidationError, match="does not match identity"):
        validate_channel_package(package, tmp_path)


def test_canonical_paths_must_exist_inside_repository(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    identity = deepcopy(load_identity(package))
    identity["canonical_sources"]["knowledge_root"] = "channels/synthetic/missing"
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    with pytest.raises(ChannelValidationError, match="does not exist"):
        validate_channel_package(package, tmp_path)

    identity["canonical_sources"]["knowledge_root"] = "../outside"
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    with pytest.raises(ChannelValidationError, match="canonical_sources.knowledge_root"):
        validate_channel_package(package, tmp_path)


def test_optional_memory_wiki_reference_uses_package_path_integrity(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    identity = load_identity(package)
    identity["canonical_sources"]["memory_wiki"] = "channels/synthetic/wiki"
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    with pytest.raises(ChannelValidationError, match="canonical_sources.memory_wiki"):
        validate_channel_package(package, tmp_path)
    (package / "wiki").mkdir()
    assert validate_channel_package(package, tmp_path).identity["id"] == "synthetic"
