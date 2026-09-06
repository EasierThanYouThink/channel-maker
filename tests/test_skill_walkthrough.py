"""Skill walkthrough: execute the channel-maker skill's documented path literally.

Test A walks a synthetic channel from CHANNEL_INIT to CHANNEL_READY through
every documented state edge (including a REVISE loop), using only subprocess
CLI calls with the exact subcommands and flags the skill teaches. Any future
skill edit that breaks the documented path fails here first.

Test B covers the voice-first production procedure plus the Ongoing episode
loop; it needs the Piper voice model and skips cleanly when offline.

Both tests run fully isolated in a seeded tmp repository root (channels,
memory contracts, and engine wiki copied in): nothing touches the real
checkout's channels/ tree, and pytest's tmp_path owns cleanup.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
CHANNEL_ID = "walk-channel"
REVIEWER = "Walkthrough Tester"


def isolated_root(tmp_path: Path) -> Path:
    """Build a seeded tmp repository root for one walkthrough run.

    Only the static engine inputs travel: the memory contract, the engine
    wiki, and an empty channels/ tree. Everything the walkthrough writes
    (packages, evidence, index) lands under tmp_path.
    """
    iso = tmp_path / "iso-root"
    (iso / "channels").mkdir(parents=True)
    shutil.copytree(ROOT / "engine" / "memory" / "contracts", iso / "engine" / "memory" / "contracts")
    shutil.copytree(ROOT / "engine" / "memory" / "wiki", iso / "engine" / "memory" / "wiki")
    return iso


def cli(root: Path, script: str, *argv: str) -> str:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / script), "--root", str(root), *argv],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, cwd=ROOT,
    )
    assert completed.returncode == 0, f"{script} {' '.join(argv)}\n{completed.stdout}\n{completed.stderr}"
    return completed.stdout


def cli_json(root: Path, script: str, *argv: str):
    return json.loads(cli(root, script, *argv))


def write_note(root: Path, name: str, body: str) -> str:
    relative = f"channels/{CHANNEL_ID}/strategy/{name}"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return relative


def make_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic-original-image-fixture")
    return path


RESPONSE = {
    "worker": "walkthrough", "model": "synthetic", "model_version": "walkthrough-v1",
    "prompt_version": "walkthrough-v1", "hermes_version": "walkthrough",
    "collected_at": "2026-09-05T12:00:00+00:00",
    "channels": [{
        "source_id": "ucwalkthrough001", "url": "https://www.youtube.com/channel/UCwalkthrough001",
        "channel_name": "Synthetic Science", "sample_role": "GROWTH_CANDIDATE",
        "sample_rationale": "Synthetic walkthrough fixture.",
        "public_fields": {"subscriber_count": 84000, "public_video_count": 212, "created_at": None,
                          "observed_uploads_per_30d": 6.0, "shorts_fraction": 0.9},
    }, {
        "source_id": "ucwalkthrough002", "url": "https://www.youtube.com/channel/UCwalkthrough002",
        "channel_name": "Ordinary Science", "sample_role": "BASELINE_COMPARATOR",
        "sample_rationale": "Ordinary comparator for what-works claims.",
        "public_fields": {"subscriber_count": 40000, "public_video_count": 150, "created_at": None,
                          "observed_uploads_per_30d": 4.0, "shorts_fraction": 0.8},
    }],
    "videos": [{
        "channel_source_id": "ucwalkthrough001", "source_id": "walkvid001",
        "url": "https://www.youtube.com/shorts/walkvid001", "title": "How caffeine works",
        "format": "SHORTS", "sample_role": "BREAKOUT",
        "sample_rationale": "Synthetic walkthrough fixture.",
        "public_fields": {"published_at": "2026-06-01T00:00:00+00:00", "duration_seconds": 25.0,
                          "views": 950000, "likes": None, "comment_count": None,
                          "description": None, "age_at_observation_days": 12.4},
    }, {
        "channel_source_id": "ucwalkthrough002", "source_id": "walkvid002",
        "url": "https://www.youtube.com/shorts/walkvid002", "title": "A normal science topic",
        "format": "SHORTS", "sample_role": "CHANNEL_BASELINE",
        "sample_rationale": "Ordinary comparator output.",
        "public_fields": {"published_at": "2026-05-01T00:00:00+00:00", "duration_seconds": 24.0,
                          "views": 8000, "likes": None, "comment_count": None,
                          "description": None, "age_at_observation_days": 30.0},
    }],
}


SCRATCH_MARKER = ".walkthrough-scratch"


def scaffold_channel(root: Path) -> Path:
    package = root / "channels" / CHANNEL_ID
    if package.exists() and not (package / SCRATCH_MARKER).is_file():
        raise AssertionError(
            f"refusing to use pre-existing channel {package}: "
            "it was not created by this walkthrough (missing scratch marker)"
        )
    cli(root, "init_channel.py", CHANNEL_ID, "--name", "Walk Channel",
        "--niche-primary", "science", "--archetype", "ILLUSTRATED_EXPLAINER",
        "--renderer", "remotion")
    (package / SCRATCH_MARKER).write_text("walkthrough scratch channel\n", encoding="utf-8")
    cli(root, "validate_channel.py", str(package))
    state = cli_json(root, "channel_state.py", "show", str(package))
    assert state["state"]["state"] == "CHANNEL_INIT"
    nxt = cli_json(root, "channel_state.py", "next", str(package))
    assert nxt["forward_state"] == "NICHE_INTELLIGENCE"
    return package


def advance(root: Path, package: Path, target: str, **flags: str) -> None:
    argv = ["advance", str(package), target, "--next-action", "Walkthrough.",
            "--actor", REVIEWER, "--reason", "Walkthrough step."]
    for key, value in flags.items():
        argv.extend([f"--{key.replace('_', '-')}", value])
    cli(root, "channel_state.py", *argv)


def test_skill_walkthrough_init_to_ready_with_revise_loop(tmp_path: Path) -> None:
    _walkthrough_init_to_ready(isolated_root(tmp_path), tmp_path)


def _build_evidence(
    root: Path, *, evidence_dir: str, scene_id: str, voice_audio: str,
    voice_timing: str, render_ref: str, suffix: str,
) -> tuple[str, str]:
    """Build one scene manifest + evaluation for real production artifacts.

    The render bytes stand in for the channel renderer's export: the gate
    proves the files exist, are content-bound, and score against a contract.
    Byte-level media probing (dimensions, decoded duration) is future work
    pending a pinned probing tool.
    """
    manifest_rel = f"{evidence_dir}/scene-manifest-{suffix}.json"
    eval_rel = f"{evidence_dir}/eval-result-{suffix}.json"
    # build_scene_candidate resolves --input/--output against the subprocess
    # cwd, not --root: pass absolute paths. Recorded manifest locations stay
    # portable (repo-relative) via the resolver.
    absolute = lambda relative: str((root / relative).resolve())
    cli(root, "build_scene_candidate.py", "--scene-id", f"{scene_id}-{suffix}",
        "--generator-agent", "walkthrough", "--model", "synthetic",
        "--prompt-version", "walkthrough-v1",
        "--input", f"audio={absolute(voice_audio)}",
        "--input", f"narration_timing={absolute(voice_timing)}",
        "--input", f"video={absolute(render_ref)}",
        "--output", absolute(manifest_rel))
    manifest = json.loads((root / manifest_rel).read_text(encoding="utf-8"))
    contract_rel = f"{evidence_dir}/eval-contract.json"
    contract_path = root / contract_rel
    if not contract_path.is_file():
        contract_path.write_text(json.dumps({
            "schema_version": "1.0.0", "artifact_type": "evaluation_contract",
            "artifact_id": "evaluation-contract:walkthrough:0123456789ab",
            "lifecycle_state": "complete", "contract_id": "walkthrough-contract",
            "scope": "general",
            "dimensions": [{
                "dimension_id": "craft", "label": "Craft", "points": 100,
                "requirements": [{
                    "requirement_id": "holds_attention",
                    "description": "The scene holds attention.",
                    "points": 100, "assessment_method": "human",
                    "required_evidence_kinds": ["video"],
                    "anchors": {"pass": "holds", "partial": "partly", "fail": "loses"},
                }],
            }],
            "hard_gates": [{
                "gate_id": "no_broken_media", "description": "Media plays.",
                "allowed_assessors": ["human_reviewer"],
                "required_evidence_kinds": ["video"],
            }],
            "thresholds": {"pass": 80, "needs_revision": 50},
            "authority": "human_owned_weights_and_requirements",
        }), encoding="utf-8")
    assessment_rel = f"{evidence_dir}/assessment-{suffix}.json"
    (root / assessment_rel).write_text(json.dumps({
        "schema_version": "1.0.0", "artifact_type": "critic_assessment",
        "artifact_id": f"critic-assessment:{scene_id}-{suffix}",
        "lifecycle_state": "complete",
        "candidate_artifact_id": manifest["artifact_id"],
        "contract_artifact_id": "evaluation-contract:walkthrough:0123456789ab",
        "assessor": {"kind": "human_reviewer"},
        "requirement_findings": [{
            "requirement_id": "holds_attention", "outcome": "pass",
            "rationale": "Walkthrough approval.",
            "evidence": [{"candidate_evidence_id": "evidence-003"}],
        }],
        "gate_findings": [{
            "gate_id": "no_broken_media", "outcome": "pass",
            "rationale": "Walkthrough approval.",
            "evidence": [{"candidate_evidence_id": "evidence-003"}],
        }],
        "created_by": {"tool": "walkthrough", "version": "1.0.0"},
    }), encoding="utf-8")
    cli(root, "evaluate_scene.py", absolute(manifest_rel), absolute(contract_rel),
        absolute(assessment_rel), absolute(eval_rel))
    return manifest_rel, eval_rel


def _build_pilot_evidence(
    root: Path, package: Path, voice_audio: str, voice_timing: str,
    render_ref: str, suffix: str,
) -> tuple[str, str]:
    return _build_evidence(
        root, evidence_dir=f"channels/{CHANNEL_ID}/pilots/pilot-1",
        scene_id="pilot-1-scene", voice_audio=voice_audio,
        voice_timing=voice_timing, render_ref=render_ref, suffix=suffix,
    )


def _walkthrough_init_to_ready(root: Path, tmp_path: Path) -> None:
    package = scaffold_channel(root)
    advance(root, package, "NICHE_INTELLIGENCE")

    study = root / "channels" / CHANNEL_ID / "intelligence" / "studies" / "s1"
    cli(root, "init_niche_study.py", str(package), "--study-id", "s1",
        "--niche", "science", "--archetype", "ILLUSTRATED_EXPLAINER", "--format", "SHORTS",
        "--language", "en", "--channel-role", "GROWTH_CANDIDATE", "--channel-role", "BASELINE_COMPARATOR",
        "--video-role", "BREAKOUT", "--video-role", "CHANNEL_BASELINE",
        "--window-from", "2026-01-01T00:00:00+00:00", "--window-to", "2026-06-01T00:00:00+00:00")
    response_path = package / "strategy" / "hermes-response.json"
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(json.dumps(RESPONSE), encoding="utf-8")
    cli(root, "niche_intelligence.py", "import-evidence", str(study), str(response_path),
        "--reviewed-by", REVIEWER)
    video_artifact_id = None
    for candidate in sorted(study.rglob("*.json")):
        document = json.loads(candidate.read_text(encoding="utf-8"))
        if document.get("artifact_type") == "video_evidence":
            video_artifact_id = document["artifact_id"]
    assert video_artifact_id is not None

    def study_artifact_id(artifact_type: str, key: str) -> str:
        for candidate in sorted(study.rglob("*.json")):
            document = json.loads(candidate.read_text(encoding="utf-8"))
            if document.get("artifact_type") == artifact_type and candidate.stem == key:
                return document["artifact_id"]
        raise AssertionError(f"{artifact_type}/{key} not found under {study}")
    cli(root, "niche_intelligence.py", "add-observation", str(study), "--key", "obs-1",
        "--statement", "Breakouts open with the mechanism.", "--observation-type", "CONTENT_PATTERN",
        "--scope", "synthetic walkthrough", "--basis", "PUBLIC_FACT",
        "--evidence-ref", video_artifact_id, "--confidence", "0.7", "--limitation", "Single synthetic video.")
    cli(root, "niche_intelligence.py", "add-hypothesis", str(study), "--key", "hyp-1",
        "--statement", "Mechanism-first hooks outperform.", "--predicted-effect", "Higher completion.",
        "--applicable-context", "Science shorts.",
        "--observation-ref", study_artifact_id("niche_observation", "obs-1"),
        "--competing-explanation", "Topic effects.", "--confidence", "0.5")
    cli(root, "niche_intelligence.py", "add-opportunity", str(study), "--key", "opp-1",
        "--observed-market", "Mechanism explainers.", "--underrepresented", "Caffeine chemistry.",
        "--proposal", "A caffeine mechanism short.",
        "--hypothesis-ref", study_artifact_id("niche_hypothesis", "hyp-1"),
        "--evidence-ref", study_artifact_id("niche_observation", "obs-1"),
        "--risk", "Niche fatigue.", "--confidence", "0.4")
    cli(root, "niche_intelligence.py", "validate", str(study))
    cli(root, "niche_intelligence.py", "publish-summaries", str(package), str(study))

    cli(root, "decision_record.py", "write", f"channels/{CHANNEL_ID}/strategy/strategy.md",
        "--kind", "strategy", "--title", "Mechanism-first science shorts",
        "--summary", "Own the caffeine-mechanism niche the teardowns surfaced.",
        "--selected", study_artifact_id("opportunity_proposal", "opp-1"),
        "--rejected", "General science news",
        "--constraint", "One pilot, one voice.",
        "--revisit", "Revisit after 3 episodes without traction.",
        "--author", REVIEWER)
    strategy_note = f"channels/{CHANNEL_ID}/strategy/strategy.md"
    opportunity_ref = f"channels/{CHANNEL_ID}/intelligence/studies/s1/study.json"
    advance(root, package, "STRATEGY_SELECTION", prerequisite_ref=opportunity_ref,
            human_decision_ref=strategy_note)
    nxt = cli_json(root, "channel_state.py", "next", str(package))
    assert nxt["forward_state"] == "CHANNEL_FOUNDATION"

    cli(root, "channel_foundation.py", "write", str(package),
        "--audience-description", "Curious adults.", "--promise", "One mechanism, fast.",
        "--niche-primary", "science", "--personality", "curious", "--balance", "MOSTLY_EDUCATIONAL",
        "--differentiation", "Shows the mechanism.", "--emotional-goal", "Aha moment.",
        "--content-boundary", "No medical advice.", "--primary-format", "SHORTS", "--avoids", "Clickbait.")
    signoff = write_note(root, "foundation-signoff.md", "# Foundation sign-off\n\nApproved.\n")
    cli(root, "channel_foundation.py", "attach-decision", str(package), "--decision-ref", signoff)
    cli(root, "channel_foundation.py", "validate", str(package))
    advance(root, package, "CHANNEL_FOUNDATION",
            prerequisite_ref=f"channels/{CHANNEL_ID}/strategy/foundation.yaml")

    cli(root, "script_dna.py", "write", str(package), "--hook-philosophy", "Mechanism first.",
        "--narrator-personality", "curious", "--sentence-length-qualitative", "Short.",
        "--technical-depth", "Medium.", "--humor-level", "Light.", "--information-density", "High.",
        "--question-usage", "One mid-video.", "--number-usage", "One number.",
        "--story-structure", "Problem, mechanism, consequence.", "--ending-behavior", "Implication.",
        "--cta-philosophy", "Soft.", "--fact-verification-requirements", "Two sources.")
    # Proof before adjectives: an approved example plus a heard audition.
    example_out = cli_json(root, "script_dna.py", "add-example", str(package),
        "--text", "Caffeine blocks the sleep signal. That is the whole trick.",
        "--provenance-kind", "human_authored", "--created-by", REVIEWER,
        "--source-ref", "walkthrough")
    example_id = example_out["example_id"]
    cli(root, "script_dna.py", "review-example", str(package), example_id,
        "--decision", "approved", "--reviewer", REVIEWER,
        "--reason", "Sounds like us.", "--yes")
    audition_text = package / "script" / "audition.txt"
    audition_text.write_text("Caffeine blocks the sleep signal. That is the whole trick.\n", encoding="utf-8")
    audition_audio = f"channels/{CHANNEL_ID}/script/audition.wav"
    audition_timing = f"channels/{CHANNEL_ID}/script/audition-timing.json"
    cli(root, "voiceover.py", "synthesize", "--script-path", str(audition_text),
        "--output-audio", audition_audio, "--output-timing", audition_timing,
        "--voice-model-dir", str(_shared_model_cache()))
    script_note = write_note(root, "script-freeze.md", "# Script DNA freeze\n\nApproved.\n")
    cli(root, "script_dna.py", "freeze", str(package), "--decision-ref", script_note,
        "--audition-example", example_id, "--audition-timing", audition_timing, "--yes")
    advance(root, package, "SCRIPT_DNA_DISCOVERY",
            prerequisite_ref=f"channels/{CHANNEL_ID}/script/script-dna.yaml")

    for kind in ("visual", "motion"):
        cli(root, "design_dna.py", kind, "init", str(package))
    exemplars = [
        ("visual_identity", "ref-visual.png"), ("typography", "ref-type.png"),
        ("color_language", "ref-color.png"), ("composition_grammar", "ref-comp.png"),
        ("scene_aesthetics", "ref-scene.png"), ("motion_identity", "ref-motion.png"),
    ]
    visual_exemplar_id = None
    for domain, filename in exemplars:
        image = make_png(tmp_path / "src" / filename)
        kind = "motion" if domain == "motion_identity" else "visual"
        out = cli_json(root, "design_exemplars.py", "--channel", CHANNEL_ID, "add", str(image),
                       "--title", domain, "--domain", domain, "--provenance-kind", "human_supplied_original",
                       "--created-by", REVIEWER, "--source-ref", "walkthrough")
        exemplar_id = out["exemplar_id"]
        if domain == "visual_identity":
            visual_exemplar_id = exemplar_id
        cli(root, "design_exemplars.py", "--channel", CHANNEL_ID, "review", exemplar_id,
            "--decision", "approved", "--reviewer", REVIEWER, "--reason", "Walkthrough approval.", "--yes")
        cli(root, "design_dna.py", kind, "add-reference", str(package),
            "--domain", domain, "--exemplar-id", exemplar_id)
    design_note = write_note(root, "design-freeze.md", "# Design freeze\n\nApproved.\n")
    for domain in ("visual_identity", "typography", "color_language", "composition_grammar", "scene_aesthetics"):
        cli(root, "design_dna.py", "visual", "freeze-domain", str(package),
            "--domain", domain, "--decision-ref", design_note, "--yes")
    cli(root, "design_dna.py", "motion", "freeze-domain", str(package),
        "--domain", "motion_identity", "--decision-ref", design_note, "--yes")
    # System proofs: the composed frame and the narrated sample are enforced
    # artifacts — check-ready refuses without their approvals.
    from engine.production.probing import encode_minimal_mp4, encode_minimal_png

    composed = tmp_path / "src" / "composed.png"
    composed.write_bytes(encode_minimal_png(width=8, height=4))
    cli(root, "design_dna.py", "visual", "record-composition", str(package),
        "--image", str(composed), "--exemplar-id", visual_exemplar_id,
        "--created-by", REVIEWER, "--source-ref", "walkthrough")
    cli(root, "design_dna.py", "visual", "review-composition", str(package),
        "--decision", "approved", "--reviewer", REVIEWER,
        "--reason", "System holds together.", "--yes")
    sample_video = tmp_path / "src" / "motion-sample.mp4"
    sample_video.write_bytes(encode_minimal_mp4())
    cli(root, "design_dna.py", "motion", "record-sample", str(package),
        "--video", str(sample_video),
        "--narration-ref", f"channels/{CHANNEL_ID}/script/audition-timing.json",
        "--created-by", REVIEWER, "--source-ref", "walkthrough")
    cli(root, "design_dna.py", "motion", "review-sample", str(package),
        "--decision", "approved", "--reviewer", REVIEWER,
        "--reason", "Moves like us.", "--yes")
    cli(root, "design_dna.py", "visual", "check-ready", str(package))
    cli(root, "design_dna.py", "motion", "check-ready", str(package))
    advance(root, package, "DESIGN_DNA_DISCOVERY",
            prerequisite_ref=f"channels/{CHANNEL_ID}/script/script-dna.yaml")
    nxt = cli_json(root, "channel_state.py", "next", str(package))
    assert nxt["forward_state"] == "CHANNEL_IDENTITY"

    cli(root, "channel_identity.py", "init", str(package))
    logo = make_png(tmp_path / "src" / "logo.png")
    logo_out = cli_json(root, "channel_identity.py", "add", "--channel", CHANNEL_ID,
                        "--domain", "logo", "--title", "Mark", "--image", str(logo),
                        "--provenance-kind", "human_supplied_original",
                        "--created-by", REVIEWER, "--source-ref", "walkthrough")
    bio_out = cli_json(root, "channel_identity.py", "add", "--channel", CHANNEL_ID,
                       "--domain", "description", "--title", "Bio", "--text", "Short science explainers.",
                       "--provenance-kind", "human_supplied_original",
                       "--created-by", REVIEWER, "--source-ref", "walkthrough")
    identity_note = write_note(root, "identity-freeze.md", "# Identity freeze\n\nApproved.\n")
    for candidate_id in (logo_out["candidate_id"], bio_out["candidate_id"]):
        cli(root, "channel_identity.py", "review", "--channel", CHANNEL_ID, candidate_id,
            "--decision", "approved", "--reviewer", REVIEWER, "--reason", "Walkthrough approval.", "--yes")
    cli(root, "channel_identity.py", "add-reference", str(package),
        "--domain", "logo", "--candidate-id", logo_out["candidate_id"])
    cli(root, "channel_identity.py", "add-reference", str(package),
        "--domain", "description", "--candidate-id", bio_out["candidate_id"])
    for domain in ("logo", "description"):
        cli(root, "channel_identity.py", "freeze-domain", str(package),
            "--domain", domain, "--decision-ref", identity_note, "--yes")
    advance(root, package, "CHANNEL_IDENTITY",
            prerequisite_ref=f"channels/{CHANNEL_ID}/motion/motion-dna-seed.yaml")

    component = package / "components" / "Arrow.tsx"
    component.parent.mkdir(parents=True, exist_ok=True)
    component.write_text("export const Arrow = () => null;\n", encoding="utf-8")
    cli(root, "asset_registry.py", "register", "--scope", "CHANNEL", "--channel-id", CHANNEL_ID,
        "--category", "primitive", "--name", "Arrow", "--description", "A directional arrow.",
        "--renderer", "remotion", "--source-kind", "tsx",
        "--source-path", f"channels/{CHANNEL_ID}/components/Arrow.tsx", "--export", "Arrow",
        "--justification", "Walkthrough needs an arrow.")
    component_record = sorted((package / "assets" / "registry").glob("*.json"))[0]
    cli(root, "asset_registry.py", "review", str(component_record), "--decision", "approved",
        "--reviewer", REVIEWER, "--reason", "Walkthrough approval.", "--yes")

    cli(root, "pilot.py", "plan", str(package), "pilot-1", "--topic", "How caffeine works",
        "--target-duration-seconds", "25", "--integration-goal", "Prove Script DNA",
        "--integration-goal", "Prove Visual DNA")
    # No PILOT_PLAN state: the approved component and the pilot plan arrive
    # together as prerequisite refs on the CHANNEL_IDENTITY -> PILOT_PRODUCTION edge.
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "channel_state.py"), "--root", str(root),
         "advance", str(package), "PILOT_PRODUCTION", "--next-action", "Walkthrough.",
         "--actor", REVIEWER, "--reason", "Walkthrough step.",
         "--prerequisite-ref", str(component_record.relative_to(root)),
         "--prerequisite-ref", f"channels/{CHANNEL_ID}/pilots/pilot-1/pilot.json"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, cwd=ROOT,
    )
    assert completed.returncode == 0, f"advance PILOT_PRODUCTION\n{completed.stdout}\n{completed.stderr}"
    # Honest production: the walkthrough proves the full voice-first path —
    # script, synthesized narration, validated timing, scene manifest,
    # evaluation, and render — instead of standing strings in for a video.
    try:
        from engine.voiceover import VoiceoverValidationError as _VVE
        from engine.voiceover import ensure_voice_model as _ensure_voice

        _ensure_voice("lessac-medium", _shared_model_cache())
    except _VVE as exc:
        pytest.skip(f"voice model unavailable (offline?): {exc}")
    script_path = package / "pilots" / "pilot-1" / "script.md"
    script_path.write_text(VOICE_SCRIPT, encoding="utf-8")
    voice_audio = f"channels/{CHANNEL_ID}/pilots/pilot-1/voiceover.wav"
    voice_timing = f"channels/{CHANNEL_ID}/pilots/pilot-1/voiceover-timing.json"
    render_ref = f"channels/{CHANNEL_ID}/pilots/pilot-1/render.mp4"
    from engine.production.probing import encode_minimal_mp4 as _encode_mp4

    (package / "pilots" / "pilot-1" / "render.mp4").write_bytes(_encode_mp4(major_brand=b"isom"))
    cli(root, "voiceover.py", "synthesize", "--script-path", str(script_path),
        "--output-audio", voice_audio, "--output-timing", voice_timing,
        "--voice-model-dir", str(_shared_model_cache()))
    cli(root, "voiceover.py", "validate", voice_timing,
        "--audio-path", str(package / "pilots" / "pilot-1" / "voiceover.wav"),
        "--target-duration-seconds", "25", "--max-deviation", "0.35")
    manifest_rel, eval_rel = _build_pilot_evidence(
        root, package, voice_audio, voice_timing, render_ref, "v1")
    cli(root, "pilot.py", "record-production", str(package), "pilot-1",
        "--script-ref", f"channels/{CHANNEL_ID}/pilots/pilot-1/script.md",
        "--voiceover-ref", voice_audio,
        "--scene-candidate-manifest", manifest_rel,
        "--evaluation-result", eval_rel,
        "--render-ref", render_ref)
    advance(root, package, "PILOT_REVIEW",
            prerequisite_ref=f"channels/{CHANNEL_ID}/pilots/pilot-1/pilot.json")

    revise_note = write_note(root, "pilot-revise.md", "# Pilot revise\n\nPacing is off; rework production.\n")
    cli(root, "pilot.py", "record-review", str(package), "pilot-1", "--decision", "REVISE",
        "--decided-by", REVIEWER, "--rationale", "Pacing.", "--decision-ref", revise_note,
        "--revise-target", "PILOT_PRODUCTION", "--yes")
    cli(root, "channel_state.py", "revise", str(package), "PILOT_PRODUCTION",
        "--actor", REVIEWER, "--decision-ref", revise_note, "--next-action", "Rework production.",
        "--reason", "Pacing.", "--yes")
    # The REVISE loop reworks production for real: new render bytes, a rebuilt
    # manifest, a fresh evaluation, and a re-record before the next review.
    (package / "pilots" / "pilot-1" / "render.mp4").write_bytes(_encode_mp4(major_brand=b"iso2"))
    manifest_rel, eval_rel = _build_pilot_evidence(
        root, package, voice_audio, voice_timing, render_ref, "v2")
    cli(root, "pilot.py", "record-production", str(package), "pilot-1",
        "--script-ref", f"channels/{CHANNEL_ID}/pilots/pilot-1/script.md",
        "--voiceover-ref", voice_audio,
        "--scene-candidate-manifest", manifest_rel,
        "--evaluation-result", eval_rel,
        "--render-ref", render_ref)
    advance(root, package, "PILOT_REVIEW",
            prerequisite_ref=f"channels/{CHANNEL_ID}/pilots/pilot-1/pilot.json")
    go_production = json.loads((package / "pilots" / "pilot-1" / "pilot.json").read_text(encoding="utf-8"))
    cli(root, "decision_record.py", "write", f"channels/{CHANNEL_ID}/pilots/pilot-1/review-go.md",
        "--kind", "review", "--title", "Pilot GO",
        "--summary", "Fixed pacing; narration, scenes, and render approved.",
        "--decision", "GO", "--rev", go_production["production"]["revision"],
        "--author", REVIEWER)
    go_note = f"channels/{CHANNEL_ID}/pilots/pilot-1/review-go.md"
    cli(root, "pilot.py", "record-review", str(package), "pilot-1", "--decision", "GO",
        "--decided-by", REVIEWER, "--rationale", "Fixed pacing.", "--decision-ref", go_note, "--yes")
    cli(root, "pilot.py", "validate", str(package), "pilot-1")
    cli(root, "pilot.py", "freeze", str(package), "pilot-1",
        "--new-channel-version", "0.2.0", "--frozen-by", REVIEWER, "--yes")

    cli(root, "channel_readiness.py", str(package), "--write")
    advance(root, package, "CHANNEL_READY",
            prerequisite_ref=f"channels/{CHANNEL_ID}/readiness-report.json",
            human_decision_ref=go_note)
    final = cli_json(root, "channel_state.py", "show", str(package))
    assert final["state"]["state"] == "CHANNEL_READY"
    assert final["state"]["status"] == "COMPLETE"
    cli(root, "validate_channel.py", str(package))


def _shared_model_cache() -> Path:
    cache = Path(tempfile.gettempdir()) / "channel-maker-test-voices"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


VOICE_SCRIPT = (
    "Caffeine wakes you up by blocking adenosine. Adenosine builds up while you are awake "
    "and tells your brain it is time to sleep. Caffeine looks enough like adenosine to sit "
    "in the same receptors without switching them on. Your brain keeps firing at full speed "
    "while the sleep signal waits outside. That is the whole trick behind your morning cup."
)


def test_skill_walkthrough_voice_and_episode_loop(tmp_path: Path) -> None:
    """Voice-first mechanics + episode loop mechanics (not lifecycle order).

    This exercises synthesis, timing validation, episode plan/produce/review,
    and the version-untouched invariant at an early workflow state for speed.
    Real episodes run only after CHANNEL_READY (see the skill's Ongoing
    section and test_skill_walkthrough_init_to_ready_with_revise_loop); the
    early state here is a mechanics fixture, not a lifecycle claim.
    """
    _walkthrough_voice_and_episode(isolated_root(tmp_path), tmp_path)


def _walkthrough_voice_and_episode(root: Path, tmp_path: Path) -> None:
    from engine.voiceover import VoiceoverValidationError, ensure_voice_model

    try:
        ensure_voice_model("lessac-medium", _shared_model_cache())
    except VoiceoverValidationError as exc:
        pytest.skip(f"voice model unavailable (offline?): {exc}")

    package = scaffold_channel(root)
    advance(root, package, "NICHE_INTELLIGENCE")
    strategy_note = write_note(root, "strategy.md", "# Strategy\n\nMechanism-first.\n")
    advance(root, package, "STRATEGY_SELECTION",
            prerequisite_ref=f"channels/{CHANNEL_ID}/channel.yaml", human_decision_ref=strategy_note)

    script_path = package / "episodes" / "ep-voice" / "script.md"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(VOICE_SCRIPT, encoding="utf-8")
    voice_audio = f"channels/{CHANNEL_ID}/episodes/ep-voice/voiceover.wav"
    voice_timing = f"channels/{CHANNEL_ID}/episodes/ep-voice/voiceover-timing.json"
    cli(root, "voiceover.py", "synthesize", "--script-path", str(script_path),
        "--output-audio", voice_audio, "--output-timing", voice_timing,
        "--voice-model-dir", str(_shared_model_cache()))
    cli(root, "voiceover.py", "validate", voice_timing,
        "--audio-path", str(package / "episodes" / "ep-voice" / "voiceover.wav"),
        "--target-duration-seconds", "25", "--max-deviation", "0.35")

    cli(root, "episode.py", "plan", str(package), "ep-voice", "--topic", "How caffeine works",
        "--target-duration-seconds", "25")
    # Complete production, like the pilot path: the episode GO gate requires
    # it. The render bytes stand in for the channel renderer's export.
    from engine.production.probing import encode_minimal_mp4 as _encode_mp4_ep

    ep_render = f"channels/{CHANNEL_ID}/episodes/ep-voice/render.mp4"
    (package / "episodes" / "ep-voice" / "render.mp4").write_bytes(_encode_mp4_ep(major_brand=b"isom"))
    ep_manifest, ep_eval = _build_evidence(
        root, evidence_dir=f"channels/{CHANNEL_ID}/episodes/ep-voice",
        scene_id="ep-voice-scene", voice_audio=voice_audio,
        voice_timing=voice_timing, render_ref=ep_render, suffix="v1",
    )
    cli(root, "episode.py", "record-production", str(package), "ep-voice",
        "--script-ref", f"channels/{CHANNEL_ID}/episodes/ep-voice/script.md",
        "--voiceover-ref", voice_audio,
        "--scene-candidate-manifest", ep_manifest,
        "--evaluation-result", ep_eval,
        "--render-ref", ep_render)
    go_note = write_note(root, "episode-go.md", "# Episode GO\n\nApproved.\n")
    cli(root, "episode.py", "record-review", str(package), "ep-voice", "--decision", "GO",
        "--decided-by", REVIEWER, "--rationale", "Good read.", "--decision-ref", go_note, "--yes")
    cli(root, "episode.py", "validate", str(package), "ep-voice")
    identity = yaml.safe_load((package / "channel.yaml").read_text(encoding="utf-8"))
    assert identity["version"] == "0.1.0"
