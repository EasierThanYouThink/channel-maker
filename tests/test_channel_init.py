from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from engine.channel import validate_channel_package
from init_channel import InitChannelError, init_channel


ROOT = Path(__file__).resolve().parents[1]


def root_with_memory(tmp_path: Path) -> Path:
    contracts = tmp_path / "engine" / "memory" / "contracts"
    contracts.mkdir(parents=True)
    shutil.copyfile(ROOT / "engine/memory/contracts/wiki-page.schema.json", contracts / "wiki-page.schema.json")
    return tmp_path


def test_init_channel_creates_minimal_valid_package(tmp_path: Path) -> None:
    root = root_with_memory(tmp_path)
    package = init_channel(
        root, "new-channel", name="New Channel", niche_primary="science",
        topic_family=None, archetype="ILLUSTRATED_EXPLAINER", language="en",
        formats=["SHORTS"], creation_mode="ORIGINAL", renderer="remotion",
    )
    validated = validate_channel_package(package, root)
    assert validated.identity["id"] == "new-channel"
    assert validated.identity["canonical_sources"] == {"channel_state": "channels/new-channel/CHANNEL_STATE.json"}
    assert validated.state["state"] == "CHANNEL_INIT"
    assert validated.state["status"] == "ACTIVE"
    assert (package / "wiki" / "HOME.md").is_file()


def test_init_channel_refuses_to_overwrite_existing_package(tmp_path: Path) -> None:
    root = root_with_memory(tmp_path)
    init_channel(
        root, "dup-channel", name="Dup", niche_primary="science", topic_family=None,
        archetype="ILLUSTRATED_EXPLAINER", language="en", formats=["SHORTS"], creation_mode="ORIGINAL",
        renderer="remotion",
    )
    with pytest.raises(InitChannelError, match="already exists"):
        init_channel(
            root, "dup-channel", name="Dup Again", niche_primary="science", topic_family=None,
            archetype="ILLUSTRATED_EXPLAINER", language="en", formats=["SHORTS"], creation_mode="ORIGINAL",
            renderer="remotion",
        )


def test_create_mode_sets_original_clone_mode_sets_existing_channel(tmp_path: Path) -> None:
    root = root_with_memory(tmp_path)
    original = init_channel(
        root, "create-mode", name="Create", niche_primary="science", topic_family=None,
        archetype="ILLUSTRATED_EXPLAINER", language="en", formats=["SHORTS"], creation_mode="ORIGINAL",
        renderer="remotion",
    )
    cloned = init_channel(
        root, "clone-mode", name="Clone", niche_primary="science", topic_family="mechanisms",
        archetype="ILLUSTRATED_EXPLAINER", language="en", formats=["SHORTS"], creation_mode="EXISTING_CHANNEL",
        renderer="remotion",
    )
    original_identity = validate_channel_package(original, root).identity
    cloned_identity = validate_channel_package(cloned, root).identity
    assert original_identity["creation"]["mode"] == "ORIGINAL"
    assert cloned_identity["creation"]["mode"] == "EXISTING_CHANNEL"
    assert cloned_identity["niche"]["topic_family"] == "mechanisms"
