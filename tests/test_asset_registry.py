from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.library import LibraryValidationError, list_components, register_component, review_component


AT = "2026-09-05T12:00:00+00:00"


def write_package(root: Path, channel_id: str = "library-channel") -> Path:
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
        "blocker": None, "next_action": "test", "resume_state": None,
        "source_refs": [f"channels/{channel_id}/channel.yaml"], "known_gaps": [],
        "legacy_mapping": False, "events": [], "updated_at": AT,
    }
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    return package


def make_component_source(root: Path, path: str) -> None:
    source = root / path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("export const BottleneckFlow = () => null;\n", encoding="utf-8")


def test_register_channel_scope_component(tmp_path: Path) -> None:
    write_package(tmp_path)
    make_component_source(tmp_path, "remotion/src/channels/library-channel/BottleneckFlow.tsx")
    path = register_component(
        tmp_path, scope="CHANNEL", channel_id="library-channel", category="mechanism",
        name="Bottleneck Flow", description="A queue-narrowing mechanism diagram.", renderer="remotion",
        source_kind="tsx", source_path="remotion/src/channels/library-channel/BottleneckFlow.tsx",
        exports=["BottleneckFlow"], interface={"itemsPerSecond": "number"},
        justification="Needed for the first pilot's core visual metaphor.", produced_for_pilot_ref=None,
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["component_id"] == "component:library-channel:bottleneck-flow"
    assert record["status"] == "experimental"


def test_register_engine_scope_rejects_channel_id(tmp_path: Path) -> None:
    make_component_source(tmp_path, "remotion/src/engine/Arrow.tsx")
    with pytest.raises(LibraryValidationError, match="must not set channel_id"):
        register_component(
            tmp_path, scope="ENGINE", channel_id="library-channel", category="primitive",
            name="Arrow", description="A directional arrow primitive.", renderer="remotion", source_kind="tsx",
            source_path="remotion/src/engine/Arrow.tsx", exports=["Arrow"], interface={},
            justification="Shared across every channel.", produced_for_pilot_ref=None,
        )


def test_register_warns_but_does_not_fail_outside_convention(tmp_path: Path, capsys) -> None:
    write_package(tmp_path)
    make_component_source(tmp_path, "remotion/src/BottleneckFlow.tsx")
    register_component(
        tmp_path, scope="CHANNEL", channel_id="library-channel", category="mechanism",
        name="Bottleneck Flow", description="d", renderer="remotion", source_kind="tsx",
        source_path="remotion/src/BottleneckFlow.tsx", exports=["BottleneckFlow"], interface={},
        justification="j", produced_for_pilot_ref=None,
    )
    assert "outside the conventional" in capsys.readouterr().out


def test_review_component_requires_human_confirmation_and_updates_status(tmp_path: Path) -> None:
    write_package(tmp_path)
    make_component_source(tmp_path, "remotion/src/channels/library-channel/Arrow.tsx")
    path = register_component(
        tmp_path, scope="CHANNEL", channel_id="library-channel", category="primitive",
        name="Arrow", description="d", renderer="remotion", source_kind="tsx",
        source_path="remotion/src/channels/library-channel/Arrow.tsx", exports=["Arrow"], interface={},
        justification="j", produced_for_pilot_ref=None,
    )
    with pytest.raises(LibraryValidationError, match="human confirmation"):
        review_component(tmp_path, path, decision="approved", reviewer="Seb", reason="Clean, reusable.", created_at=AT, human_confirmed=False)
    review_component(tmp_path, path, decision="approved", reviewer="Seb", reason="Clean, reusable.", created_at=AT, human_confirmed=True)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["status"] == "approved"
    assert len(record["review_ids"]) == 1


def test_list_components_filters_by_scope_category_status(tmp_path: Path) -> None:
    write_package(tmp_path)
    make_component_source(tmp_path, "remotion/src/channels/library-channel/Arrow.tsx")
    make_component_source(tmp_path, "remotion/src/engine/Label.tsx")
    register_component(
        tmp_path, scope="CHANNEL", channel_id="library-channel", category="primitive", name="Arrow",
        description="d", renderer="remotion", source_kind="tsx", source_path="remotion/src/channels/library-channel/Arrow.tsx",
        exports=["Arrow"], interface={}, justification="j", produced_for_pilot_ref=None,
    )
    register_component(
        tmp_path, scope="ENGINE", channel_id=None, category="primitive", name="Label",
        description="d", renderer="remotion", source_kind="tsx", source_path="remotion/src/engine/Label.tsx",
        exports=["Label"], interface={}, justification="j", produced_for_pilot_ref=None,
    )
    assert len(list_components(tmp_path)) == 2
    assert len(list_components(tmp_path, scope="ENGINE")) == 1
    assert len(list_components(tmp_path, scope="CHANNEL", channel_id="library-channel")) == 1
    assert len(list_components(tmp_path, status="approved")) == 0
