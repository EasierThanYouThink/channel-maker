from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.channel import ChannelStateError, ChannelStateMachine, validate_channel_package
from engine.design import add_reference, freeze_domain, init_seed
from engine.design.exemplars import ChannelExemplarStore
from engine.foundation import attach_foundation_decision, write_foundation
from engine.identity import ChannelIdentityStore
from engine.identity import add_reference as add_identity_reference
from engine.identity import freeze_domain as freeze_identity_domain
from engine.identity import init_identity
from engine.library import register_component, review_component
from engine.pilot import freeze_pilot, plan_pilot, record_production, record_review
from engine.readiness import ReadinessError, check_readiness, write_readiness_report
from engine.script import ScriptExampleStore, freeze_script_dna, write_script_dna


AT = "2026-09-05T12:00:00+00:00"
CHANNEL_ID = "ready-channel"


def write_package(root: Path) -> Path:
    package = root / "channels" / CHANNEL_ID
    package.mkdir(parents=True)
    identity = {
        "schema_version": "0.1.0", "id": CHANNEL_ID, "name": "Ready Channel", "version": "0.1.0",
        "status": "DRAFT", "language": "en", "niche": {"primary": "science"},
        "platform": {"primary": "YOUTUBE", "formats": ["SHORTS"]},
        "production": {"archetype": "ILLUSTRATED_EXPLAINER", "renderer": "remotion"},
        "creation": {"mode": "ORIGINAL"},
        "canonical_sources": {"channel_state": f"channels/{CHANNEL_ID}/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.2.0", "channel_id": CHANNEL_ID, "revision": 0, "state": "CHANNEL_INIT",
        "status": "ACTIVE", "completed": [], "active_experiment": None, "waiting_for": None,
        "blocker": None, "next_action": "test", "resume_state": None,
        "source_refs": [f"channels/{CHANNEL_ID}/channel.yaml"], "known_gaps": [],
        "legacy_mapping": False, "events": [], "updated_at": AT,
    }
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    return package


def item_status(report: dict, item_id: str) -> bool:
    return next(item["passed"] for item in report["items"] if item["item_id"] == item_id)


def failing_items(report: dict) -> list[str]:
    return [item["item_id"] for item in report["items"] if not item["passed"]]


def make_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic-original-image-fixture")
    return path


def test_write_readiness_report_never_writes_until_every_item_passes(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    with pytest.raises(ReadinessError):
        write_readiness_report(package, tmp_path)
    assert not (package / "readiness-report.json").exists()


def test_full_incremental_build_flips_every_item_and_persists_at_the_end(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    machine = ChannelStateMachine(package, tmp_path)
    any_ref = f"channels/{CHANNEL_ID}/channel.yaml"

    report = check_readiness(package, tmp_path)
    assert not item_status(report, "strategy_selected")

    machine.advance("NICHE_INTELLIGENCE", next_action="n", actor="a", reason="r")
    machine.advance("OPPORTUNITY_MAP", next_action="n", actor="a", reason="r", prerequisite_refs=[any_ref])
    # Human gate: STRATEGY_SELECTION requires a human_decision_ref.
    machine.advance(
        "STRATEGY_SELECTION", next_action="n", actor="a", reason="r",
        prerequisite_refs=[any_ref], human_decision_ref=any_ref,
    )
    report = check_readiness(package, tmp_path)
    assert item_status(report, "strategy_selected")
    assert not item_status(report, "audience_promise")

    write_foundation(
        package, tmp_path, audience_description="Curious adults", audience_demographics=None,
        promise="One mechanism, fast.", niche_primary="science", sub_niches=[], personality=["curious"],
        education_entertainment_balance="MOSTLY_EDUCATIONAL", differentiation="Shows the mechanism",
        emotional_goal="Aha moment", content_boundaries=["No medical advice"], primary_format="SHORTS",
        deliberately_avoids=["Clickbait"],
    )
    attach_foundation_decision(package, tmp_path, decision_ref=any_ref)
    machine.advance("CHANNEL_FOUNDATION", next_action="n", actor="a", reason="r", prerequisite_refs=[any_ref])
    report = check_readiness(package, tmp_path)
    assert item_status(report, "audience_promise")
    assert not item_status(report, "script_dna_frozen")

    write_script_dna(
        package, tmp_path, hook_philosophy="h", narrator_personality=["curious"],
        sentence_length_qualitative="short", sentence_length_target_words=9,
        words_per_second_target=2.8, words_per_second_range=[2.4, 3.2], technical_depth="medium",
        humor_level="light", information_density="high", question_usage="one", number_usage="one",
        story_structure="p->m->c", ending_behavior="implication", cta_philosophy="soft",
        preferred_cliches=[], forbidden_cliches=[], fact_verification_requirements="two sources",
        unresolved_variables=[],
    )
    script_store = ScriptExampleStore(tmp_path, CHANNEL_ID)
    script_example = script_store.add(
        "A proven line.", tags=[], provenance_kind="human_authored",
        created_by="Seb", source_ref="manual",
    )
    script_store.review(
        script_example["example_id"], decision="approved", reviewer="Seb",
        reason="Good.", created_at=AT, human_confirmed=True,
    )
    freeze_script_dna(package, tmp_path, human_confirmed=True, decision_ref=any_ref)
    machine.advance("SCRIPT_DNA_DISCOVERY", next_action="n", actor="a", reason="r", prerequisite_refs=[any_ref])
    report = check_readiness(package, tmp_path)
    assert item_status(report, "script_dna_frozen")
    assert not item_status(report, "visual_dna_frozen")

    init_seed("visual", package, tmp_path)
    exemplar_store = ChannelExemplarStore(tmp_path, CHANNEL_ID)
    for domain in ("visual_identity", "typography", "color_language", "composition_grammar", "scene_aesthetics"):
        image = make_png(tmp_path / "src" / f"{domain}.png")
        record = exemplar_store.add(
            image, title=f"Ref {domain}", domain=domain, tags=[],
            provenance_kind="human_supplied_original", created_by="Seb", source_ref="manual upload",
        )
        exemplar_store.review(record["exemplar_id"], decision="approved", reviewer="Seb", reason="Matches direction.", created_at=AT, human_confirmed=True)
        add_reference("visual", package, tmp_path, domain=domain, exemplar_id=record["exemplar_id"])
    for domain in ("visual_identity", "typography", "color_language", "composition_grammar", "scene_aesthetics"):
        freeze_domain("visual", package, tmp_path, domain=domain, human_confirmed=True, decision_ref=any_ref)
    report = check_readiness(package, tmp_path)
    assert item_status(report, "visual_dna_frozen")
    assert item_status(report, "approved_exemplar")
    machine.advance("VISUAL_DNA_DISCOVERY", next_action="n", actor="a", reason="r", prerequisite_refs=[any_ref])

    init_seed("motion", package, tmp_path)
    motion_image = make_png(tmp_path / "src" / "motion.png")
    motion_record = exemplar_store.add(
        motion_image, title="Ref motion", domain="motion_identity", tags=[],
        provenance_kind="human_supplied_original", created_by="Seb", source_ref="manual upload",
    )
    exemplar_store.review(motion_record["exemplar_id"], decision="approved", reviewer="Seb", reason="Matches.", created_at=AT, human_confirmed=True)
    add_reference("motion", package, tmp_path, domain="motion_identity", exemplar_id=motion_record["exemplar_id"])
    freeze_domain("motion", package, tmp_path, domain="motion_identity", human_confirmed=True, decision_ref=any_ref)
    machine.advance("MOTION_DNA_DISCOVERY", next_action="n", actor="a", reason="r", prerequisite_refs=[any_ref])
    report = check_readiness(package, tmp_path)
    assert item_status(report, "motion_dna_frozen")
    assert not item_status(report, "identity_frozen")

    init_identity(package, tmp_path)
    identity_store = ChannelIdentityStore(tmp_path, CHANNEL_ID)
    logo_image = make_png(tmp_path / "src" / "mark.png")
    logo = identity_store.add(
        domain="logo", title="Mark", image=logo_image, provenance_kind="human_supplied_original",
        created_by="Seb", source_ref="manual upload",
    )
    description = identity_store.add(
        domain="description", title="Bio", text="Short, clear science explainers.",
        provenance_kind="human_supplied_original", created_by="Seb", source_ref="draft",
    )
    identity_store.review(
        logo["candidate_id"], decision="approved", reviewer="Seb",
        reason="Good mark.", created_at=AT, human_confirmed=True,
    )
    identity_store.review(
        description["candidate_id"], decision="approved", reviewer="Seb",
        reason="Good bio.", created_at=AT, human_confirmed=True,
    )
    add_identity_reference(package, tmp_path, domain="logo", candidate_id=logo["candidate_id"])
    add_identity_reference(package, tmp_path, domain="description", candidate_id=description["candidate_id"])
    freeze_identity_domain(package, tmp_path, domain="logo", human_confirmed=True, decision_ref=any_ref)
    freeze_identity_domain(package, tmp_path, domain="description", human_confirmed=True, decision_ref=any_ref)
    machine.advance("CHANNEL_IDENTITY", next_action="n", actor="a", reason="r", prerequisite_refs=[any_ref])
    report = check_readiness(package, tmp_path)
    assert item_status(report, "identity_frozen")
    assert not item_status(report, "approved_component")

    make_png(tmp_path / "remotion" / "src" / "channels" / CHANNEL_ID / "Arrow.tsx")
    component_path = register_component(
        tmp_path, scope="CHANNEL", channel_id=CHANNEL_ID, category="primitive", name="Arrow",
        description="d", renderer="remotion", source_kind="tsx", source_path=f"remotion/src/channels/{CHANNEL_ID}/Arrow.tsx",
        exports=["Arrow"], interface={}, justification="Needed for the pilot.", produced_for_pilot_ref=None,
    )
    review_component(tmp_path, component_path, decision="approved", reviewer="Seb", reason="Clean.", created_at=AT, human_confirmed=True)
    machine.advance("STARTER_VISUAL_LIBRARY", next_action="n", actor="a", reason="r", prerequisite_refs=[any_ref])
    report = check_readiness(package, tmp_path)
    assert item_status(report, "approved_component")
    assert not item_status(report, "reviewed_pilot")

    plan_pilot(package, tmp_path, pilot_id="pilot-1", topic="t", target_duration_seconds=25.0, integration_goals=["g"])
    for relative, artifact_type, artifact_id in (
        ("evidence/pilot-scene.json", "scene_candidate_manifest", "scene-candidate:pilot:abc123"),
        ("evidence/pilot-eval.json", "evaluation_result", "evaluation-result:pilot:abc123"),
    ):
        evidence_path = tmp_path / relative
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps({"artifact_type": artifact_type, "artifact_id": artifact_id}), encoding="utf-8")
    (tmp_path / "evidence" / "pilot-script.md").write_text("# Script\n", encoding="utf-8")
    (tmp_path / "evidence" / "pilot-voiceover.wav").write_bytes(b"RIFF" + b"\x00" * 100)
    (tmp_path / "evidence" / "pilot-render.mp4").write_bytes(b"fake-video-bytes")
    record_production(
        package, tmp_path, "pilot-1",
        scene_candidate_manifest_paths=["evidence/pilot-scene.json"],
        evaluation_result_paths=["evidence/pilot-eval.json"],
        script_ref="evidence/pilot-script.md", voiceover_ref="evidence/pilot-voiceover.wav",
        render_ref="evidence/pilot-render.mp4",
    )
    machine.advance("PILOT_PLAN", next_action="n", actor="a", reason="r", prerequisite_refs=[any_ref])
    machine.advance("PILOT_PRODUCTION", next_action="n", actor="a", reason="r", prerequisite_refs=[any_ref])
    machine.advance("PILOT_REVIEW", next_action="n", actor="a", reason="r", prerequisite_refs=[any_ref])
    record_review(package, tmp_path, "pilot-1", decision="GO", decided_by="Seb", rationale="Good.", decision_ref=any_ref)
    report = check_readiness(package, tmp_path)
    assert item_status(report, "reviewed_pilot")
    assert not item_status(report, "explicit_human_go")

    # Human gate: PILOT_REVIEW -> CHANNEL_FREEZE requires a human_decision_ref.
    machine.advance("CHANNEL_FREEZE", next_action="n", actor="a", reason="r", prerequisite_refs=[any_ref], human_decision_ref=any_ref)
    report = check_readiness(package, tmp_path)
    assert not item_status(report, "explicit_human_go"), "still not ready: the pilot has not been frozen yet"

    freeze_pilot(package, tmp_path, "pilot-1", new_channel_version="0.2.0", frozen_by="Seb")
    report = check_readiness(package, tmp_path)
    for item in report["items"]:
        assert item["passed"], f"expected all items to pass, but {item['item_id']} failed: {item['explanation']}"
    assert report["overall_passed"] is True

    path = write_readiness_report(package, tmp_path)
    assert path.is_file()
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["overall_passed"] is True

    machine.advance("CHANNEL_READY", next_action="Channel is ready.", actor="a", reason="r", prerequisite_refs=[str(path.relative_to(tmp_path))])
    final_state = json.loads((package / "CHANNEL_STATE.json").read_text(encoding="utf-8"))
    assert final_state["state"] == "CHANNEL_READY"
    assert final_state["status"] == "COMPLETE"

    # The whole CHANNEL_INIT -> CHANNEL_READY walk must still validate as one legal Channel Package.
    validated = validate_channel_package(package, tmp_path)
    assert validated.state["state"] == "CHANNEL_READY"

    # A completed channel cannot advance further (there is no forward transition from CHANNEL_READY).
    with pytest.raises(ChannelStateError):
        machine.advance("CHANNEL_INIT", next_action="n", actor="a", reason="r")
