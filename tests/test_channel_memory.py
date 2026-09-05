from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from engine.memory import ChannelMemoryRepository, initialize_channel_wiki
from engine.memory.wiki_pages import KnowledgeError


ROOT = Path(__file__).resolve().parents[1]
AT = "2026-08-23T12:00:00+00:00"


def memory_root(tmp_path: Path) -> Path:
    contracts = tmp_path / "engine" / "memory" / "contracts"
    contracts.mkdir(parents=True)
    shutil.copyfile(
        ROOT / "engine" / "memory" / "contracts" / "wiki-page.schema.json",
        contracts / "wiki-page.schema.json",
    )
    return tmp_path


def write_package(root: Path, channel_id: str, archetype: str = "DATA_STORY") -> Path:
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
        "creation": {"mode": "ORIGINAL"},
        "canonical_sources": {"channel_state": f"channels/{channel_id}/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.2.0",
        "channel_id": channel_id,
        "revision": 0,
        "state": "CHANNEL_INIT",
        "status": "ACTIVE",
        "completed": [],
        "active_experiment": None,
        "waiting_for": None,
        "blocker": None,
        "next_action": "Initialize durable channel memory.",
        "resume_state": None,
        "source_refs": [f"channels/{channel_id}/channel.yaml"],
        "known_gaps": [],
        "legacy_mapping": False,
        "events": [],
        "updated_at": AT,
    }
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    return package


def metadata(
    knowledge_id: str,
    title: str,
    *,
    scope: str,
    channel_id: str | None,
    video_id: str | None = None,
    kind: str = "observation",
    authority: str = "descriptive",
    provenance_ref: str = "engine/memory/contracts/wiki-page.schema.json",
) -> dict:
    return {
        "schema_version": "0.2.0",
        "knowledge_id": knowledge_id,
        "title": title,
        "kind": kind,
        "status": "active",
        "authority": authority,
        "scope": scope,
        "channel_id": channel_id,
        "video_id": video_id,
        "tags": ["memory", "synthetic"],
        "confidence": 0.8,
        "created_at": AT,
        "updated_at": AT,
        "related": [],
        "provenance": [{"kind": "repository", "ref": provenance_ref}],
    }


def test_wiki_initialization_is_minimal_idempotent_and_obsidian_compatible(tmp_path: Path) -> None:
    root = memory_root(tmp_path)
    package = write_package(root, "finance-demo")
    first = initialize_channel_wiki(package, root, created_at=AT)
    original = first.read_bytes()
    second = initialize_channel_wiki(package, root, created_at="2026-08-24T12:00:00+00:00")
    assert first == second
    assert second.read_bytes() == original
    assert first.name == "HOME.md"
    assert (package / "wiki" / "market" / "observations").is_dir()
    document = ChannelMemoryRepository(root).documents()[0]
    assert document.scope == "CHANNEL"
    assert document.channel_id == "finance-demo"


def test_wiki_initialization_validates_before_writing(tmp_path: Path) -> None:
    root = memory_root(tmp_path)
    package = write_package(root, "finance-demo")
    with pytest.raises(KnowledgeError, match="RFC 3339"):
        initialize_channel_wiki(package, root, created_at="not-a-date")
    assert not (package / "wiki" / "HOME.md").exists()


def test_engine_channel_and_video_metadata_scopes_are_represented(tmp_path: Path) -> None:
    root = memory_root(tmp_path)
    package = write_package(root, "history-map", "MAP_STORY")
    initialize_channel_wiki(package, root, created_at=AT)
    repository = ChannelMemoryRepository(root)
    (root / "engine" / "memory" / "wiki").mkdir(parents=True)
    engine_meta = metadata("wiki:engine/inspection", "Inspect Geometry", scope="ENGINE", channel_id=None)
    repository.write_page("inspection.md", engine_meta, "Render and visually inspect important geometry.")
    video_meta = metadata(
        "wiki:video/history-map/episode-004/dam",
        "Dam Metaphor",
        scope="VIDEO",
        channel_id="history-map",
        video_id="episode-004",
        provenance_ref="channels/history-map/channel.yaml",
    )
    repository.write_page("dam.md", video_meta, "Episode 004 uses a dam as its original metaphor.")
    scopes = {(item.scope, item.channel_id, item.video_id) for item in repository.documents()}
    assert ("ENGINE", None, None) in scopes
    assert ("CHANNEL", "history-map", None) in scopes
    assert ("VIDEO", "history-map", "episode-004") in scopes
    assert repository.search("dam metaphor", channel_id="history-map") == []
    video_results = repository.search("dam metaphor", channel_id="history-map", video_id="episode-004")
    assert video_results[0].knowledge_id == "wiki:video/history-map/episode-004/dam"


def test_malformed_metadata_and_unauthorized_approved_rule_are_rejected(tmp_path: Path) -> None:
    root = memory_root(tmp_path)
    write_package(root, "finance-demo")
    repository = ChannelMemoryRepository(root)
    invalid = metadata(
        "wiki:channel/finance-demo/fake-rule",
        "Fake Rule",
        scope="CHANNEL",
        channel_id="finance-demo",
        kind="approved_rule",
        authority="ai_proposed",
        provenance_ref="channels/finance-demo/channel.yaml",
    )
    invalid["approval_ref"] = "fabricated"
    with pytest.raises(KnowledgeError, match="invalid scoped Wiki metadata"):
        repository.write_page("rules/fake.md", invalid, "This must not be approved.")

    looks_human_approved = metadata(
        "wiki:channel/finance-demo/claimed-rule", "Claimed Rule", scope="CHANNEL",
        channel_id="finance-demo", kind="approved_rule", authority="human_approved",
        provenance_ref="channels/finance-demo/channel.yaml",
    )
    looks_human_approved["approval_ref"] = "human-decision:claimed"
    looks_human_approved["provenance"].append({
        "kind": "human_decision", "ref": "human-decision:claimed"
    })
    with pytest.raises(KnowledgeError, match="generic write-back cannot create"):
        repository.write_page("rules/claimed.md", looks_human_approved, "Still not allowed here.")

    wrong_scope_id = metadata(
        "wiki:engine/wrong", "Wrong Scope ID", scope="CHANNEL", channel_id="finance-demo",
        provenance_ref="channels/finance-demo/channel.yaml",
    )
    with pytest.raises(KnowledgeError, match="knowledge_id must start"):
        repository.write_page("observations/wrong.md", wrong_scope_id, "Wrong namespace.")

    wiki = root / "channels" / "finance-demo" / "wiki"
    wiki.mkdir()
    (wiki / "bad.md").write_text("# Missing frontmatter\n", encoding="utf-8")
    with pytest.raises(KnowledgeError, match="requires YAML frontmatter"):
        repository.documents()


def test_channel_isolation_and_engine_opt_in(tmp_path: Path) -> None:
    root = memory_root(tmp_path)
    finance = write_package(root, "finance-demo")
    history = write_package(root, "history-map", "MAP_STORY")
    initialize_channel_wiki(finance, root, created_at=AT)
    initialize_channel_wiki(history, root, created_at=AT)
    repository = ChannelMemoryRepository(root)
    (root / "engine" / "memory" / "wiki").mkdir(parents=True)
    repository.write_page(
        "geometry.md",
        metadata("wiki:engine/geometry", "Geometry Inspection", scope="ENGINE", channel_id=None),
        "Important geometry should be rendered and inspected.",
    )
    repository.write_page(
        "observations/liquidity.md",
        metadata(
            "wiki:channel/finance-demo/liquidity", "Liquidity Pulse", scope="CHANNEL",
            channel_id="finance-demo", provenance_ref="channels/finance-demo/channel.yaml",
        ),
        "The synthetic finance fixture mentions liquidity.",
    )
    repository.write_page(
        "observations/cartography.md",
        metadata(
            "wiki:channel/history-map/cartography", "Cartography Rhythm", scope="CHANNEL",
            channel_id="history-map", provenance_ref="channels/history-map/channel.yaml",
        ),
        "The synthetic history fixture mentions cartography.",
    )

    finance_results = repository.search("liquidity cartography geometry", channel_id="finance-demo")
    assert {item.knowledge_id for item in finance_results} == {"wiki:channel/finance-demo/liquidity"}
    with_engine = repository.search(
        "liquidity cartography geometry", channel_id="finance-demo", include_engine=True
    )
    assert {item.knowledge_id for item in with_engine} == {
        "wiki:channel/finance-demo/liquidity", "wiki:engine/geometry"
    }
    filtered = repository.search(
        "", channel_id="finance-demo", kinds={"observation"},
        authorities={"descriptive"}, tags={"synthetic"},
    )
    assert [item.knowledge_id for item in filtered] == ["wiki:channel/finance-demo/liquidity"]


def test_search_is_deterministic_and_disposable_index_rebuilds_identically(tmp_path: Path) -> None:
    root = memory_root(tmp_path)
    package = write_package(root, "finance-demo")
    initialize_channel_wiki(package, root, created_at=AT)
    repository = ChannelMemoryRepository(root)
    repository.write_page(
        "observations/inflation.md",
        metadata(
            "wiki:channel/finance-demo/inflation", "Inflation Number Treatment", scope="CHANNEL",
            channel_id="finance-demo", provenance_ref="channels/finance-demo/channel.yaml",
        ),
        "Inflation is physicalized with a large restrained number.",
    )
    first = repository.search("inflation number", channel_id="finance-demo")
    first_index = repository.index_path.read_bytes()
    repository.index_path.unlink()
    second = ChannelMemoryRepository(root).search("inflation number", channel_id="finance-demo")
    assert first == second
    assert second[0].knowledge_id == "wiki:channel/finance-demo/inflation"
    assert repository.index_path.read_bytes() == first_index

    tampered = json.loads(first_index)
    injected = dict(tampered["documents"][0])
    injected.update({
        "knowledge_id": "wiki:channel/finance-demo/injected",
        "channel_id": "finance-demo",
        "body": "injected noncanonical memory",
        "title": "Injected",
    })
    tampered["documents"].append(injected)
    repository.index_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert repository.search("injected", channel_id="finance-demo") == []
    assert repository.index_path.read_bytes() == first_index


def test_context_bundle_is_bounded_and_reconstructs_channel_state(tmp_path: Path) -> None:
    root = memory_root(tmp_path)
    package = write_package(root, "history-map", "MAP_STORY")
    initialize_channel_wiki(package, root, created_at=AT)
    repository = ChannelMemoryRepository(root)
    repository.write_page(
        "lessons/map.md",
        metadata(
            "wiki:channel/history-map/map-lesson", "Map Route Lesson", scope="CHANNEL",
            channel_id="history-map", kind="lesson", provenance_ref="channels/history-map/channel.yaml",
        ),
        "A" * 500,
    )
    bundle = repository.build_context_bundle(package, "map route", limit=2, max_body_chars=80)
    assert bundle["channel_state"]["state"] == "CHANNEL_INIT"
    assert bundle["channel_state"]["next_action"] == "Initialize durable channel memory."
    assert sum(len(item["body"]) for item in bundle["memory"]) <= 80


def test_fresh_process_reconstructs_search_from_canonical_files(tmp_path: Path) -> None:
    root = memory_root(tmp_path)
    package = write_package(root, "finance-demo")
    initialize_channel_wiki(package, root, created_at=AT)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "channel_memory.py"),
            "--root", str(root),
            "search", "channel memory", "--channel", "finance-demo",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    values = json.loads(result.stdout)
    assert values[0]["knowledge_id"] == "wiki:channel/finance-demo/home"
