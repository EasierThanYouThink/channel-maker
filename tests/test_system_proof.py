"""System proofs: composed visual frame + narrated motion sample are enforced.

check-ready refuses fully-frozen seeds without their approvals; recording
validates media structure (PNG/MP4) and grounding (approved exemplars,
existing narration ref); reviews require explicit human confirmation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.design import (
    DesignValidationError,
    check_ready_problems,
    freeze_domain,
    init_seed,
    record_composition,
    record_motion_sample,
    review_composition,
    review_motion_sample,
)
from engine.design.exemplars import ChannelExemplarStore
from engine.production.probing import encode_minimal_mp4, encode_minimal_png

AT = "2026-09-05T12:00:00+00:00"
CHANNEL_ID = "proof-channel"


def write_package(root: Path) -> Path:
    package = root / "channels" / CHANNEL_ID
    package.mkdir(parents=True)
    identity = {
        "schema_version": "0.1.0", "id": CHANNEL_ID, "name": "Proof Channel",
        "version": "0.1.0", "status": "DRAFT", "language": "en",
        "niche": {"primary": "science"},
        "platform": {"primary": "YOUTUBE", "formats": ["SHORTS"]},
        "production": {"archetype": "ILLUSTRATED_EXPLAINER", "renderer": "remotion"},
        "creation": {"mode": "ORIGINAL"},
        "canonical_sources": {"channel_state": f"channels/{CHANNEL_ID}/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.3.0", "channel_id": CHANNEL_ID, "revision": 0,
        "state": "CHANNEL_INIT", "status": "ACTIVE", "completed": [],
        "active_experiment": None, "waiting_for": None, "blocker": None,
        "next_action": "test", "resume_state": None,
        "source_refs": [f"channels/{CHANNEL_ID}/channel.yaml"], "known_gaps": [],
        "legacy_mapping": False, "events": [], "updated_at": AT,
    }
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    return package


def approved_exemplar_id(root: Path, domain: str = "visual_identity") -> str:
    store = ChannelExemplarStore(root, CHANNEL_ID)
    image = root / "src" / f"{domain}.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(encode_minimal_png())
    record = store.add(
        image, title=f"Ref {domain}", domain=domain, tags=[],
        provenance_kind="human_supplied_original", created_by="Seb", source_ref="manual",
    )
    store.review(
        record["exemplar_id"], decision="approved", reviewer="Seb",
        reason="Good.", created_at=AT, human_confirmed=True,
    )
    return record["exemplar_id"]


def freeze_all_visual(package: Path, root: Path, ref: str) -> None:
    from engine.design import add_reference

    init_seed("visual", package, root)
    for domain in ("visual_identity", "typography", "color_language", "composition_grammar", "scene_aesthetics"):
        exemplar_id = approved_exemplar_id(root, domain)
        add_reference("visual", package, root, domain=domain, exemplar_id=exemplar_id)
        freeze_domain("visual", package, root, domain=domain, human_confirmed=True, decision_ref=ref)


def test_check_ready_demands_the_system_proof(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    ref = f"channels/{CHANNEL_ID}/channel.yaml"
    freeze_all_visual(package, tmp_path, ref)
    problems = check_ready_problems("visual", package, tmp_path)
    assert any("composition" in problem for problem in problems)

    composed = tmp_path / "composed.png"
    composed.write_bytes(encode_minimal_png(width=8, height=4))
    store_ids = ChannelExemplarStore(tmp_path, CHANNEL_ID).list(classification="approved")
    record_composition(
        package, tmp_path, image=composed,
        exemplar_ids=[store_ids[0]["exemplar_id"]],
        created_by="Seb", source_ref="manual",
    )
    # Recorded but unreviewed still blocks.
    assert check_ready_problems("visual", package, tmp_path)
    review_composition(
        package, tmp_path, decision="approved", reviewer="Seb",
        reason="Holds together.", human_confirmed=True,
    )
    assert check_ready_problems("visual", package, tmp_path) == []


def test_composition_rejects_bad_media_and_ungrounded_refs(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    init_seed("visual", package, tmp_path)
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not-a-png")
    with pytest.raises(DesignValidationError, match="PNG"):
        record_composition(
            package, tmp_path, image=bad, exemplar_ids=["exemplar:nope"],
            created_by="Seb", source_ref="manual",
        )
    good = tmp_path / "good.png"
    good.write_bytes(encode_minimal_png())
    with pytest.raises(DesignValidationError, match="no exemplar record"):
        record_composition(
            package, tmp_path, image=good, exemplar_ids=["exemplar:nope"],
            created_by="Seb", source_ref="manual",
        )
    with pytest.raises(DesignValidationError, match="at least one"):
        record_composition(
            package, tmp_path, image=good, exemplar_ids=[],
            created_by="Seb", source_ref="manual",
        )


def test_motion_sample_requires_narration_and_review(tmp_path: Path) -> None:
    from engine.design import init_seed as _init

    package = write_package(tmp_path)
    _init("motion", package, tmp_path)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(encode_minimal_mp4())
    with pytest.raises(DesignValidationError, match="narration ref"):
        record_motion_sample(
            package, tmp_path, video=clip, narration_ref="",
            created_by="Seb", source_ref="manual",
        )
    with pytest.raises(DesignValidationError, match="narration_ref"):
        record_motion_sample(
            package, tmp_path, video=clip, narration_ref="missing.md",
            created_by="Seb", source_ref="manual",
        )
    narration = tmp_path / "narration.md"
    narration.write_text("# Lines\n", encoding="utf-8")
    record_motion_sample(
        package, tmp_path, video=clip, narration_ref="narration.md",
        created_by="Seb", source_ref="manual",
    )
    with pytest.raises(DesignValidationError, match="explicit human confirmation"):
        review_motion_sample(package, tmp_path, decision="approved", reviewer="Seb", reason="Good.")
    review_motion_sample(
        package, tmp_path, decision="approved", reviewer="Seb",
        reason="Good.", human_confirmed=True,
    )
    with pytest.raises(DesignValidationError, match="already approved"):
        review_motion_sample(
            package, tmp_path, decision="approved", reviewer="Seb",
            reason="Again.", human_confirmed=True,
        )


def test_system_proofs_surface_in_review_queue(tmp_path: Path) -> None:
    from tools.dashboard.views import review_queue

    package = write_package(tmp_path)
    init_seed("visual", package, tmp_path)
    exemplar_id = approved_exemplar_id(tmp_path)
    composed = tmp_path / "composed.png"
    composed.write_bytes(encode_minimal_png())
    record_composition(
        package, tmp_path, image=composed, exemplar_ids=[exemplar_id],
        created_by="Seb", source_ref="manual",
    )
    queue = review_queue(tmp_path)
    assert len(queue["design_system_proofs"]) == 1
    review_composition(
        package, tmp_path, decision="approved", reviewer="Seb",
        reason="Good.", human_confirmed=True,
    )
    assert review_queue(tmp_path)["design_system_proofs"] == []
