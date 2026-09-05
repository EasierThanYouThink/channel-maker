from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.identity import (
    ChannelIdentityStore,
    IdentityValidationError,
    add_reference,
    all_domains_frozen,
    freeze_domain,
    identity_path,
    init_identity,
    resolve_domain_references,
)


AT = "2026-09-05T12:00:00+00:00"


def write_package(root: Path, channel_id: str = "identity-channel") -> Path:
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


def test_init_add_reference_and_freeze_both_domains(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    path = init_identity(package, tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["status"] == "ACTIVE_DISCOVERY"
    assert set(document["domains"]) == {"logo", "description"}

    with pytest.raises(IdentityValidationError, match="already exists"):
        init_identity(package, tmp_path)

    store = ChannelIdentityStore(tmp_path, "identity-channel")
    image = make_png(tmp_path / "src" / "mark.png")
    logo = store.add(
        domain="logo", title="Mark", image=image, provenance_kind="human_supplied_original",
        created_by="Seb", source_ref="manual upload",
    )
    description = store.add(
        domain="description", title="Bio v1", text="Short, clear science explainers.",
        provenance_kind="human_supplied_original", created_by="Seb", source_ref="draft",
    )
    store.review(
        logo["candidate_id"], decision="approved", reviewer="Seb",
        reason="Good mark.", created_at="2026-09-05T12:00:00+00:00",
        human_confirmed=True,
    )
    store.review(
        description["candidate_id"], decision="approved", reviewer="Seb",
        reason="Good bio.", created_at="2026-09-05T12:00:00+00:00",
        human_confirmed=True,
    )
    add_reference(package, tmp_path, domain="logo", candidate_id=logo["candidate_id"])
    add_reference(package, tmp_path, domain="description", candidate_id=description["candidate_id"])
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["domains"]["logo"]["reference_ids"] == [logo["candidate_id"]]
    assert document["domains"]["logo"]["discovery_status"] == "ACTIVE"
    assert document["domains"]["description"]["reference_ids"] == [description["candidate_id"]]

    with pytest.raises(IdentityValidationError, match="human confirmation"):
        freeze_domain(package, tmp_path, domain="logo", human_confirmed=False, decision_ref="channels/identity-channel/channel.yaml")
    with pytest.raises(IdentityValidationError, match="does not resolve"):
        freeze_domain(package, tmp_path, domain="logo", human_confirmed=True, decision_ref="nope.md")

    freeze_domain(package, tmp_path, domain="logo", human_confirmed=True, decision_ref="channels/identity-channel/channel.yaml")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["domains"]["logo"]["authority_status"] == "FROZEN"
    assert all_domains_frozen(document) is False
    assert document["status"] == "PARTIALLY_FROZEN"

    freeze_domain(package, tmp_path, domain="description", human_confirmed=True, decision_ref="channels/identity-channel/channel.yaml")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert all_domains_frozen(document) is True
    assert document["status"] == "FROZEN"


def test_add_reference_rejects_wrong_domain_candidate(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    init_identity(package, tmp_path)
    store = ChannelIdentityStore(tmp_path, "identity-channel")
    description = store.add(
        domain="description", title="Bio", text="A bio.", provenance_kind="human_supplied_original",
        created_by="Seb", source_ref="draft",
    )
    with pytest.raises(IdentityValidationError, match="tagged for domain"):
        add_reference(package, tmp_path, domain="logo", candidate_id=description["candidate_id"])


def test_resolve_domain_references_detects_missing_candidate(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    path = init_identity(package, tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["domains"]["logo"]["reference_ids"] = ["identity-candidate:ghost-00000000"]
    candidates_root = tmp_path / "channels" / "identity-channel" / "identity" / "candidates"
    with pytest.raises(IdentityValidationError, match="no candidate record"):
        resolve_domain_references(document, candidates_root)


def test_logo_candidate_requires_image_not_text(tmp_path: Path) -> None:
    store = ChannelIdentityStore(tmp_path, "identity-channel")
    with pytest.raises(IdentityValidationError, match="requires an image"):
        store.add(domain="logo", title="Mark", text="oops", provenance_kind="human_supplied_original", created_by="Seb", source_ref="x")


def test_description_candidate_requires_text_not_image(tmp_path: Path) -> None:
    store = ChannelIdentityStore(tmp_path, "identity-channel")
    image = make_png(tmp_path / "src" / "mark.png")
    with pytest.raises(IdentityValidationError, match="requires text"):
        store.add(domain="description", title="Bio", image=image, provenance_kind="human_supplied_original", created_by="Seb", source_ref="x")


def test_review_requires_human_confirmation(tmp_path: Path) -> None:
    store = ChannelIdentityStore(tmp_path, "identity-channel")
    description = store.add(
        domain="description", title="Bio", text="A bio.", provenance_kind="human_supplied_original",
        created_by="Seb", source_ref="draft",
    )
    with pytest.raises(IdentityValidationError, match="human confirmation"):
        store.review(description["candidate_id"], decision="approved", reviewer="Seb", reason="ok", created_at=AT, human_confirmed=False)


def test_ai_generated_requires_model_fields(tmp_path: Path) -> None:
    store = ChannelIdentityStore(tmp_path, "identity-channel")
    with pytest.raises(IdentityValidationError, match="AI-generated"):
        store.add(
            domain="description", title="Bio", text="A bio.", provenance_kind="ai_generated_original",
            created_by="Seb", source_ref="prompt-1",
        )


def test_list_filters_by_domain_and_classification(tmp_path: Path) -> None:
    store = ChannelIdentityStore(tmp_path, "identity-channel")
    image = make_png(tmp_path / "src" / "mark.png")
    store.add(domain="logo", title="Mark", image=image, provenance_kind="human_supplied_original", created_by="Seb", source_ref="a")
    store.add(domain="description", title="Bio", text="A bio.", provenance_kind="human_supplied_original", created_by="Seb", source_ref="b")
    assert len(store.list(domain="logo")) == 1
    assert len(store.list()) == 2
    assert len(store.list(classification="approved")) == 0

    description = store.list(domain="description")[0]
    review = store.review(description["candidate_id"], decision="approved", reviewer="Seb", reason="Good voice.", created_at=AT, human_confirmed=True)
    assert review["decision"] == "approved"
    assert len(store.list(classification="approved")) == 1
