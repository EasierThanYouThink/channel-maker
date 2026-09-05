"""Phase 5: taste compiler, failure lab, and programming desk gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


AT = "2026-09-05T12:00:00+00:00"


def write_package(root: Path, channel_id: str = "lab-channel") -> Path:
    package = root / "channels" / channel_id
    package.mkdir(parents=True)
    identity = {
        "schema_version": "0.1.0", "id": channel_id, "name": channel_id.title(),
        "version": "0.2.0", "status": "CHANNEL_READY", "language": "en",
        "niche": {"primary": "science"},
        "platform": {"primary": "YOUTUBE", "formats": ["SHORTS"]},
        "production": {"archetype": "ILLUSTRATED_EXPLAINER", "renderer": "remotion"},
        "creation": {"mode": "ORIGINAL"},
        "canonical_sources": {"channel_state": f"channels/{channel_id}/CHANNEL_STATE.json"},
    }
    state = {
        "schema_version": "0.2.0", "channel_id": channel_id, "revision": 0,
        "state": "CHANNEL_READY", "status": "COMPLETE",
        "completed": [
            "CHANNEL_INIT", "NICHE_INTELLIGENCE", "OPPORTUNITY_MAP", "STRATEGY_SELECTION",
            "CHANNEL_FOUNDATION", "SCRIPT_DNA_DISCOVERY", "VISUAL_DNA_DISCOVERY", "MOTION_DNA_DISCOVERY",
            "CHANNEL_IDENTITY", "STARTER_VISUAL_LIBRARY", "PILOT_PLAN", "PILOT_PRODUCTION",
            "PILOT_REVIEW", "CHANNEL_FREEZE",
        ], "active_experiment": None,
        "waiting_for": None, "blocker": None, "next_action": "Produce.",
        "resume_state": None, "source_refs": [f"channels/{channel_id}/channel.yaml"],
        "known_gaps": [], "legacy_mapping": False, "events": [], "updated_at": AT,
    }
    (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
    (package / "CHANNEL_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    return package


def write_note(root: Path, name: str) -> str:
    relative = f"channels/lab-channel/strategy/{name}"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Note\n\nHuman words.\n", encoding="utf-8")
    return relative


def test_taste_compare_propose_promote_gates(tmp_path: Path) -> None:
    from engine.taste import (
        TasteError,
        list_policies,
        promote_policy,
        propose_policy,
        record_comparison,
    )
    from engine.taste.store import init_taste

    package = write_package(tmp_path)
    init_taste(package, tmp_path)
    decision_ref = write_note(tmp_path, "taste-decision.md")
    comparison = record_comparison(
        package, tmp_path, preferred_ref="ep-2", rejected_ref="ep-1",
        reason="Denser hook.", decided_by="Seb", decision_ref=decision_ref,
        context="pilot",
    )
    assert comparison["comparison_id"].startswith("taste-comparison-")
    with pytest.raises(TasteError, match="unknown comparisons"):
        propose_policy(
            package, tmp_path, statement="x", scope="hooks",
            comparison_ids=["taste-comparison-nope"],
        )
    policy = propose_policy(
        package, tmp_path, statement="Lead with the mechanism.",
        scope="hooks", comparison_ids=[comparison["comparison_id"]],
        uncertainty="One comparison only.",
    )
    assert policy["status"] == "proposed"
    with pytest.raises(TasteError, match="human confirmation"):
        promote_policy(
            package, tmp_path, policy_id=policy["policy_id"], promoted_by="Seb",
            decision_ref=decision_ref, heldout_ref=decision_ref, human_confirmed=False,
        )
    heldout = write_note(tmp_path, "heldout.md")
    promoted = promote_policy(
        package, tmp_path, policy_id=policy["policy_id"], promoted_by="Seb",
        decision_ref=decision_ref, heldout_ref=heldout, human_confirmed=True,
    )
    assert promoted["status"] == "promoted"
    assert [item["status"] for item in list_policies(package, tmp_path)] == ["promoted"]


def test_failure_lab_files_reproducible_cases_and_replays(tmp_path: Path) -> None:
    from engine.failure_lab import (
        FailureLabError,
        file_case,
        list_cases,
        record_repair,
        record_replay,
    )
    from engine.failure_lab.store import init_lab

    package = write_package(tmp_path)
    init_lab(package, tmp_path)
    inputs = write_note(tmp_path, "inputs.md")
    with pytest.raises(FailureLabError, match="reproduction_ref"):
        file_case(
            package, tmp_path, case_id="flat-voice", symptom="Robot read.",
            input_refs=[inputs], reproduction_ref="channels/lab-channel/missing.md",
        )
    repro = write_note(tmp_path, "repro.md")
    path = file_case(
        package, tmp_path, case_id="flat-voice", symptom="Robot read.",
        input_refs=[inputs], reproduction_ref=repro, diagnosis="No pauses.",
        tool_versions={"piper": "1.8.0"}, release="0.2.0",
    )
    assert path.is_file()
    with pytest.raises(FailureLabError, match="already exists"):
        file_case(
            package, tmp_path, case_id="flat-voice", symptom="Again.",
            input_refs=[inputs], reproduction_ref=repro,
        )
    fix = write_note(tmp_path, "fix.md")
    record_repair(package, tmp_path, case_id="flat-voice", repair="Add pauses.",
                  repair_ref=fix, verified=True)
    replay = record_replay(package, tmp_path, case_id="flat-voice", passed=True,
                           tool_versions={"piper": "1.8.0"}, notes="Still fixed.")
    assert replay.is_file()
    assert list_cases(package, tmp_path)[0]["repair_verified"] is True


def test_programming_desk_tracks_bets_costs_and_slates(tmp_path: Path) -> None:
    from engine.programming import (
        ProgrammingError,
        approve_slate,
        assign_episode,
        propose_hypothesis,
        propose_slate,
        record_cost,
        record_outcome,
        record_publication,
    )
    from engine.programming.store import init_desk

    package = write_package(tmp_path)
    init_desk(package, tmp_path)
    propose_hypothesis(package, tmp_path, hypothesis_id="h1", statement="Mechanisms win.")
    with pytest.raises(ProgrammingError, match="one episode, one hypothesis"):
        assign_episode(package, tmp_path, hypothesis_id="h1", episode_id="ep-1")
        assign_episode(package, tmp_path, hypothesis_id="h1", episode_id="ep-1")
    assign_episode(package, tmp_path, hypothesis_id="h1", episode_id="ep-2")
    record_cost(package, tmp_path, episode_id="ep-2", minutes=45.0, notes="Render farm.")
    with pytest.raises(ProgrammingError, match="not assigned"):
        record_publication(package, tmp_path, episode_id="ep-9")
    record_publication(package, tmp_path, episode_id="ep-2")
    with pytest.raises(ProgrammingError, match="provenance"):
        record_outcome(package, tmp_path, episode_id="ep-2", measurements={"views": "9000"},
                       provenance="", window="7d")
    outcome = record_outcome(
        package, tmp_path, episode_id="ep-2", measurements={"views": "9000"},
        provenance="manual YouTube Studio export", window="first 7 days",
    )
    assert outcome["evidence_strength"] == "correlational"
    propose_slate(package, tmp_path, slate_id="s1", episode_ids=["ep-2", "ep-3"], rationale="More mechanisms.")
    with pytest.raises(ProgrammingError, match="human confirmation"):
        approve_slate(package, tmp_path, slate_id="s1", approved_by="Seb",
                      decision_ref=write_note(tmp_path, "slate.md"), human_confirmed=False)
    approved = approve_slate(package, tmp_path, slate_id="s1", approved_by="Seb",
                             decision_ref=write_note(tmp_path, "slate2.md"), human_confirmed=True)
    assert approved["status"] == "approved"
