"""Skill walkthrough: execute the channel-maker skill's documented path literally.

Test A walks a synthetic channel from CHANNEL_INIT to CHANNEL_READY through
every documented state edge (including a REVISE loop), using only subprocess
CLI calls with the exact subcommands and flags the skill teaches. Any future
skill edit that breaks the documented path fails here first.

Test B covers the voice-first production procedure plus the Ongoing episode
loop; it needs the Piper voice model and skips cleanly when offline.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
CHANNEL_ID = "walk-channel"
REVIEWER = "Walkthrough Tester"


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
    }],
    "videos": [{
        "channel_source_id": "ucwalkthrough001", "source_id": "walkvid001",
        "url": "https://www.youtube.com/shorts/walkvid001", "title": "How caffeine works",
        "format": "SHORTS", "sample_role": "BREAKOUT",
        "sample_rationale": "Synthetic walkthrough fixture.",
        "public_fields": {"published_at": "2026-06-01T00:00:00+00:00", "duration_seconds": 25.0,
                          "views": 950000, "likes": None, "comment_count": None,
                          "description": None, "age_at_observation_days": 12.4},
    }],
}


def scaffold_channel(root: Path) -> Path:
    package = root / "channels" / CHANNEL_ID
    cli(root, "init_channel.py", CHANNEL_ID, "--name", "Walk Channel",
        "--niche-primary", "science", "--archetype", "ILLUSTRATED_EXPLAINER",
        "--renderer", "remotion")
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
    root = ROOT
    try:
        _walkthrough_init_to_ready(root, tmp_path)
    finally:
        _remove_scratch_channel(root)


def _remove_scratch_channel(root: Path) -> None:
    import shutil

    package = root / "channels" / CHANNEL_ID
    if package.is_dir():
        shutil.rmtree(package)


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

    strategy_note = write_note(root, "strategy.md", "# Strategy\n\nMechanism-first science shorts.\n")
    opportunity_ref = f"channels/{CHANNEL_ID}/intelligence/studies/s1/study.json"
    advance(root, package, "OPPORTUNITY_MAP", prerequisite_ref=opportunity_ref)
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
    script_note = write_note(root, "script-freeze.md", "# Script DNA freeze\n\nApproved.\n")
    cli(root, "script_dna.py", "freeze", str(package), "--decision-ref", script_note, "--yes")
    advance(root, package, "SCRIPT_DNA_DISCOVERY",
            prerequisite_ref=f"channels/{CHANNEL_ID}/script/script-dna.yaml")

    for kind in ("visual", "motion"):
        cli(root, "design_dna.py", kind, "init", str(package))
    exemplars = [
        ("visual_identity", "ref-visual.png"), ("typography", "ref-type.png"),
        ("color_language", "ref-color.png"), ("composition_grammar", "ref-comp.png"),
        ("scene_aesthetics", "ref-scene.png"), ("motion_identity", "ref-motion.png"),
    ]
    for domain, filename in exemplars:
        image = make_png(tmp_path / "src" / filename)
        kind = "motion" if domain == "motion_identity" else "visual"
        out = cli_json(root, "design_exemplars.py", "--channel", CHANNEL_ID, "add", str(image),
                       "--title", domain, "--domain", domain, "--provenance-kind", "human_supplied_original",
                       "--created-by", REVIEWER, "--source-ref", "walkthrough")
        exemplar_id = out["exemplar_id"]
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
    advance(root, package, "VISUAL_DNA_DISCOVERY",
            prerequisite_ref=f"channels/{CHANNEL_ID}/design/visual-dna-seed.yaml")
    advance(root, package, "MOTION_DNA_DISCOVERY",
            prerequisite_ref=f"channels/{CHANNEL_ID}/motion/motion-dna-seed.yaml")
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
            prerequisite_ref=f"channels/{CHANNEL_ID}/identity/channel-identity.yaml")
    advance(root, package, "STARTER_VISUAL_LIBRARY",
            prerequisite_ref=f"channels/{CHANNEL_ID}/identity/channel-identity.yaml")

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
    advance(root, package, "PILOT_PLAN", prerequisite_ref=str(component_record.relative_to(root)))

    cli(root, "pilot.py", "plan", str(package), "pilot-1", "--topic", "How caffeine works",
        "--target-duration-seconds", "25", "--integration-goal", "Prove Script DNA",
        "--integration-goal", "Prove Visual DNA")
    advance(root, package, "PILOT_PRODUCTION",
            prerequisite_ref=f"channels/{CHANNEL_ID}/pilots/pilot-1/pilot.json")
    script_path = package / "pilots" / "pilot-1" / "script.md"
    script_path.write_text("# How caffeine works\n\nCaffeine blocks adenosine.\n", encoding="utf-8")
    cli(root, "pilot.py", "record-production", str(package), "pilot-1",
        "--script-ref", f"channels/{CHANNEL_ID}/pilots/pilot-1/script.md",
        "--render-ref", f"channels/{CHANNEL_ID}/pilots/pilot-1/render.mp4")
    advance(root, package, "PILOT_REVIEW",
            prerequisite_ref=f"channels/{CHANNEL_ID}/pilots/pilot-1/pilot.json")

    revise_note = write_note(root, "pilot-revise.md", "# Pilot revise\n\nPacing is off; rework production.\n")
    cli(root, "pilot.py", "record-review", str(package), "pilot-1", "--decision", "REVISE",
        "--decided-by", REVIEWER, "--rationale", "Pacing.", "--decision-ref", revise_note,
        "--revise-target", "PILOT_PRODUCTION", "--yes")
    cli(root, "channel_state.py", "revise", str(package), "PILOT_PRODUCTION",
        "--actor", REVIEWER, "--decision-ref", revise_note, "--next-action", "Rework production.",
        "--reason", "Pacing.", "--yes")
    advance(root, package, "PILOT_REVIEW",
            prerequisite_ref=f"channels/{CHANNEL_ID}/pilots/pilot-1/pilot.json")
    go_note = write_note(root, "pilot-go.md", "# Pilot GO\n\nApproved.\n")
    cli(root, "pilot.py", "record-review", str(package), "pilot-1", "--decision", "GO",
        "--decided-by", REVIEWER, "--rationale", "Fixed pacing.", "--decision-ref", go_note, "--yes")
    cli(root, "pilot.py", "validate", str(package), "pilot-1")
    advance(root, package, "CHANNEL_FREEZE",
            prerequisite_ref=f"channels/{CHANNEL_ID}/pilots/pilot-1/pilot.json",
            human_decision_ref=go_note)
    cli(root, "pilot.py", "freeze", str(package), "pilot-1",
        "--new-channel-version", "0.2.0", "--frozen-by", REVIEWER, "--yes")

    cli(root, "channel_readiness.py", str(package), "--write")
    advance(root, package, "CHANNEL_READY",
            prerequisite_ref=f"channels/{CHANNEL_ID}/readiness-report.json")
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
    root = ROOT
    try:
        _walkthrough_voice_and_episode(root, tmp_path)
    finally:
        _remove_scratch_channel(root)


def _walkthrough_voice_and_episode(root: Path, tmp_path: Path) -> None:
    from engine.voiceover import VoiceoverValidationError, ensure_voice_model

    try:
        ensure_voice_model("lessac-medium", _shared_model_cache())
    except VoiceoverValidationError as exc:
        pytest.skip(f"voice model unavailable (offline?): {exc}")

    package = scaffold_channel(root)
    advance(root, package, "NICHE_INTELLIGENCE")
    advance(root, package, "OPPORTUNITY_MAP",
            prerequisite_ref=f"channels/{CHANNEL_ID}/channel.yaml")
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
    cli(root, "episode.py", "record-production", str(package), "ep-voice",
        "--script-ref", f"channels/{CHANNEL_ID}/episodes/ep-voice/script.md",
        "--voiceover-ref", voice_audio,
        "--render-ref", f"channels/{CHANNEL_ID}/episodes/ep-voice/render.mp4")
    go_note = write_note(root, "episode-go.md", "# Episode GO\n\nApproved.\n")
    cli(root, "episode.py", "record-review", str(package), "ep-voice", "--decision", "GO",
        "--decided-by", REVIEWER, "--rationale", "Good read.", "--decision-ref", go_note, "--yes")
    cli(root, "episode.py", "validate", str(package), "ep-voice")
    identity = yaml.safe_load((package / "channel.yaml").read_text(encoding="utf-8"))
    assert identity["version"] == "0.1.0"
