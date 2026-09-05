from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.design import (
    DesignValidationError,
    add_reference,
    all_domains_frozen,
    freeze_domain,
    init_seed,
    resolve_domain_references,
    seed_path,
)
from engine.design.exemplars import ChannelExemplarStore


AT = "2026-09-05T12:00:00+00:00"


def write_package(root: Path, channel_id: str = "design-channel") -> Path:
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


def make_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic-original-image-fixture")
    return path


@pytest.mark.parametrize("kind,domain", [("visual", "visual_identity"), ("motion", "motion_identity")])
def test_init_add_reference_and_freeze_domain(tmp_path: Path, kind: str, domain: str) -> None:
    package = write_package(tmp_path)
    path = init_seed(kind, package, tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["status"] == "ACTIVE_DISCOVERY"
    assert set(document["domains"]) == (
        {"visual_identity", "typography", "color_language", "composition_grammar", "scene_aesthetics"}
        if kind == "visual" else {"motion_identity"}
    )

    with pytest.raises(DesignValidationError, match="already exists"):
        init_seed(kind, package, tmp_path)

    store = ChannelExemplarStore(tmp_path, "design-channel")
    image = make_png(tmp_path / "src" / "ref.png")
    record = store.add(
        image, title="Reference frame", domain=domain, tags=["ref"],
        provenance_kind="human_supplied_original", created_by="Seb", source_ref="manual upload",
    )
    add_reference(kind, package, tmp_path, domain=domain, exemplar_id=record["exemplar_id"])
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["domains"][domain]["reference_ids"] == [record["exemplar_id"]]
    assert document["domains"][domain]["discovery_status"] == "ACTIVE"

    with pytest.raises(DesignValidationError, match="human confirmation"):
        freeze_domain(kind, package, tmp_path, domain=domain, human_confirmed=False, decision_ref="channels/design-channel/channel.yaml")
    with pytest.raises(DesignValidationError, match="does not resolve"):
        freeze_domain(kind, package, tmp_path, domain=domain, human_confirmed=True, decision_ref="nope.md")

    freeze_domain(kind, package, tmp_path, domain=domain, human_confirmed=True, decision_ref="channels/design-channel/channel.yaml")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["domains"][domain]["authority_status"] == "FROZEN"

    if kind == "motion":
        assert all_domains_frozen(kind, document) is True
        assert document["status"] == "FROZEN"
    else:
        assert all_domains_frozen(kind, document) is False
        assert document["status"] == "PARTIALLY_FROZEN"


def test_add_reference_rejects_wrong_domain_exemplar(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    init_seed("visual", package, tmp_path)
    store = ChannelExemplarStore(tmp_path, "design-channel")
    image = make_png(tmp_path / "src" / "ref.png")
    record = store.add(
        image, title="Typography sample", domain="typography", tags=[],
        provenance_kind="human_supplied_original", created_by="Seb", source_ref="manual upload",
    )
    with pytest.raises(DesignValidationError, match="tagged for domain"):
        add_reference("visual", package, tmp_path, domain="visual_identity", exemplar_id=record["exemplar_id"])


def test_resolve_domain_references_detects_missing_exemplar(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    path = init_seed("visual", package, tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["domains"]["visual_identity"]["reference_ids"] = ["exemplar:ghost-00000000"]
    store_root = tmp_path / "channels" / "design-channel" / "design" / "exemplars"
    with pytest.raises(DesignValidationError, match="no exemplar record"):
        resolve_domain_references("visual", document, store_root)
