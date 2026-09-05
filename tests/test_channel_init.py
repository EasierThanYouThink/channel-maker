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
        formats=["SHORTS"], renderer="remotion",
    )
    validated = validate_channel_package(package, root)
    assert validated.identity["id"] == "new-channel"
    assert validated.identity["canonical_sources"] == {"channel_state": "channels/new-channel/CHANNEL_STATE.json"}
    assert validated.identity["creation"] == {"mode": "ORIGINAL"}
    assert validated.state["state"] == "CHANNEL_INIT"
    assert validated.state["status"] == "ACTIVE"
    assert (package / "wiki" / "HOME.md").is_file()


def test_init_channel_refuses_to_overwrite_existing_package(tmp_path: Path) -> None:
    root = root_with_memory(tmp_path)
    init_channel(
        root, "dup-channel", name="Dup", niche_primary="science", topic_family=None,
        archetype="ILLUSTRATED_EXPLAINER", language="en", formats=["SHORTS"],
        renderer="remotion",
    )
    with pytest.raises(InitChannelError, match="already exists"):
        init_channel(
            root, "dup-channel", name="Dup Again", niche_primary="science", topic_family=None,
            archetype="ILLUSTRATED_EXPLAINER", language="en", formats=["SHORTS"],
            renderer="remotion",
        )


def test_init_channel_refuses_when_thesis_written_before_scaffold(tmp_path: Path) -> None:
    # Regression for the thesis-before-scaffold ordering bug: creating files
    # under channels/<id>/ before scaffolding must fail with guidance, not
    # with a bare "already exists".
    root = root_with_memory(tmp_path)
    premature = root / "channels" / "early-channel" / "strategy"
    premature.mkdir(parents=True)
    (premature / "channel-thesis.md").write_text("# Thesis\n", encoding="utf-8")
    with pytest.raises(InitChannelError, match="only after init_channel succeeds"):
        init_channel(
            root, "early-channel", name="Early", niche_primary="science",
            topic_family=None, archetype="ILLUSTRATED_EXPLAINER", language="en",
            formats=["SHORTS"], renderer="remotion",
        )


def test_init_channel_is_always_original_in_v1(tmp_path: Path) -> None:
    # Clone mode (EXISTING_CHANNEL) was cut for v1 and returns in v2: every
    # channel scaffolds as ORIGINAL, no creation-mode flag exists.
    root = root_with_memory(tmp_path)
    package = init_channel(
        root, "create-mode", name="Create", niche_primary="science", topic_family="mechanisms",
        archetype="ILLUSTRATED_EXPLAINER", language="en", formats=["SHORTS"],
        renderer="remotion",
    )
    identity = validate_channel_package(package, root).identity
    assert identity["creation"]["mode"] == "ORIGINAL"
    assert identity["niche"]["topic_family"] == "mechanisms"
