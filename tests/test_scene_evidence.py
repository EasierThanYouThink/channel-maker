"""Phase 0: scene/evaluation evidence tooling actually validates.

Regression coverage for the renderer-evidence path the skill teaches in
Stage 9: manifests must build and validate without a (nonexistent)
config/taxonomies.yaml, and DNA/identity attachment must refuse
unapproved references.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.design import DesignValidationError, add_reference, init_seed
from engine.design.exemplars import ChannelExemplarStore
from engine.identity import IdentityValidationError, init_identity
from engine.identity import add_reference as add_identity_reference
from engine.identity.store import ChannelIdentityStore


AT = "2026-09-05T12:00:00+00:00"


def write_package(root: Path, channel_id: str = "scene-channel") -> Path:
    package = root / "channels" / channel_id
    package.mkdir(parents=True)
    identity = {
        "schema_version": "0.1.0", "id": channel_id, "name": channel_id.title(),
        "version": "0.1.0", "status": "DRAFT", "language": "en",
        "niche": {"primary": "science"},
        "platform": {"primary": "YOUTUBE", "formats": ["SHORTS"]},
        "production": {"archetype": "ILLUSTRATED_EXPLAINER", "renderer": "remotion"},
        "creation": {"mode": "ORIGINAL"},
        "canonical_sources": {"channel_state": f"channels/{channel_id}/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.2.0", "channel_id": channel_id, "revision": 0,
        "state": "CHANNEL_INIT", "status": "ACTIVE", "completed": [],
        "active_experiment": None, "waiting_for": None, "blocker": None,
        "next_action": "test", "resume_state": None,
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


def test_require_valid_needs_no_taxonomies_config() -> None:
    # The repo ships no config/taxonomies.yaml; validation of scene/eval
    # artifacts must not crash on its absence.
    from tools._core import ChannelMakerError, require_valid

    with pytest.raises(ChannelMakerError, match="invalid"):
        require_valid({"artifact_type": "evaluation_result", "dummy": True}, label="t")


def test_build_candidate_manifest_validates(tmp_path: Path) -> None:
    import sys

    tools_dir = Path(__file__).resolve().parents[1] / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from build_scene_candidate import build_candidate

    still = tmp_path / "evidence" / "still.png"
    still.parent.mkdir(parents=True, exist_ok=True)
    still.write_bytes(b"fake-still-bytes")
    record = build_candidate(
        "scene-1", "walkthrough", "synthetic", "v1",
        [("still", still)], repository_root=tmp_path,
    )
    assert record["artifact_type"] == "scene_candidate_manifest"
    assert record["artifact_id"].startswith("scene-candidate:scene-1:")
    assert record["artifacts"][0]["sha256"]
    assert record["artifacts"][0]["location"] == {
        "root": "repo", "path": "evidence/still.png",
    }


def test_design_add_reference_rejects_unapproved(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    init_seed("visual", package, tmp_path)
    store = ChannelExemplarStore(tmp_path, "scene-channel")
    image = make_png(tmp_path / "src" / "ref.png")
    record = store.add(
        image, title="Ref", domain="visual_identity", tags=[],
        provenance_kind="human_supplied_original", created_by="Seb",
        source_ref="manual",
    )
    with pytest.raises(DesignValidationError, match="only approved"):
        add_reference(
            "visual", package, tmp_path, domain="visual_identity",
            exemplar_id=record["exemplar_id"],
        )
    store.review(
        record["exemplar_id"], decision="approved", reviewer="Seb",
        reason="Good.", created_at=AT, human_confirmed=True,
    )
    path = add_reference(
        "visual", package, tmp_path, domain="visual_identity",
        exemplar_id=record["exemplar_id"],
    )
    assert path.is_file()


def test_identity_add_reference_rejects_unapproved(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    init_identity(package, tmp_path)
    store = ChannelIdentityStore(tmp_path, "scene-channel")
    candidate = store.add(
        domain="description", title="Bio", text="Short, clear science explainers.",
        provenance_kind="human_supplied_original", created_by="Seb",
        source_ref="draft",
    )
    with pytest.raises(IdentityValidationError, match="only approved"):
        add_identity_reference(
            package, tmp_path, domain="description",
            candidate_id=candidate["candidate_id"],
        )
