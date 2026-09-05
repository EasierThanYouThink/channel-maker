"""Draft and freeze a channel's Script DNA document."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from engine.channel import ChannelValidationError, validate_channel_package

from .examples import ScriptExampleStore
from .validation import ScriptValidationError, validate_script_dna


def _timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_yaml_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(value, handle, sort_keys=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _dna_path(package_root: Path) -> Path:
    return package_root / "script" / "script-dna.yaml"


def write_script_dna(
    package_root: Path,
    repository_root: Path,
    *,
    hook_philosophy: str,
    narrator_personality: list[str],
    sentence_length_qualitative: str,
    sentence_length_target_words: int | None,
    words_per_second_target: float | None,
    words_per_second_range: list[float] | None,
    technical_depth: str,
    humor_level: str,
    information_density: str,
    question_usage: str,
    number_usage: str,
    story_structure: str,
    ending_behavior: str,
    cta_philosophy: str,
    preferred_cliches: list[str],
    forbidden_cliches: list[str],
    fact_verification_requirements: str,
    unresolved_variables: list[str],
    force: bool = False,
) -> Path:
    repository_root = repository_root.resolve()
    try:
        package = validate_channel_package(package_root.resolve(), repository_root)
    except ChannelValidationError as exc:
        raise ScriptValidationError(str(exc)) from exc
    draft_path = _dna_path(package.root)
    if draft_path.is_file() and not force:
        raise ScriptValidationError(
            f"Script DNA already drafted: {draft_path}; re-running write overwrites it and clears "
            f"frozen status and decision_refs — pass force=True to overwrite deliberately"
        )
    document = {
        "schema_version": "1.0.0", "artifact_type": "script_dna", "channel_id": package.identity["id"],
        "hook_philosophy": hook_philosophy, "narrator_personality": narrator_personality,
        "sentence_length": {"qualitative": sentence_length_qualitative, "target_words": sentence_length_target_words},
        "words_per_second": {"target": words_per_second_target, "range": words_per_second_range},
        "technical_depth": technical_depth, "humor_level": humor_level, "information_density": information_density,
        "question_usage": question_usage, "number_usage": number_usage, "story_structure": story_structure,
        "ending_behavior": ending_behavior, "cta_philosophy": cta_philosophy,
        "preferred_cliches": preferred_cliches, "forbidden_cliches": forbidden_cliches,
        "fact_verification_requirements": fact_verification_requirements,
        "unresolved_variables": unresolved_variables, "status": "ACTIVE_DISCOVERY", "decision_refs": [],
        "audition": None,
        "created_by": {
            "created_at": _timestamp(None), "creator": "MODEL_ASSISTED",
            "tool": "engine.script.dna.write_script_dna", "version": "1.0.0",
        },
    }
    validate_script_dna(document, expected_channel_id=package.identity["id"])
    path = _dna_path(package.root)
    _write_yaml_atomic(path, document)
    return path


def freeze_script_dna(
    package_root: Path,
    repository_root: Path,
    *,
    human_confirmed: bool,
    decision_ref: str,
    force: bool = False,
    audition_example_id: str | None = None,
    audition_timing_ref: str | None = None,
) -> Path:
    if not human_confirmed:
        raise ScriptValidationError("freezing Script DNA requires an explicit human confirmation")
    if not decision_ref.strip():
        raise ScriptValidationError("freezing Script DNA requires a non-empty decision_ref")
    repository_root = repository_root.resolve()
    try:
        package = validate_channel_package(package_root.resolve(), repository_root)
    except ChannelValidationError as exc:
        raise ScriptValidationError(str(exc)) from exc
    resolved = (repository_root / decision_ref).resolve()
    if not resolved.is_relative_to(repository_root) or not resolved.exists():
        raise ScriptValidationError(f"decision_ref does not resolve to an existing repository path: {decision_ref}")

    path = _dna_path(package.root)
    if not path.is_file():
        raise ScriptValidationError(f"no drafted Script DNA exists yet: {path}")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if document.get("status") == "FROZEN" and not force:
        raise ScriptValidationError(
            f"Script DNA is already frozen: {path}; pass force=True to re-freeze deliberately"
        )
    # Proof before adjectives: at least one human-approved example must show
    # the DNA working, not just describe it.
    store = ScriptExampleStore(repository_root, package.identity["id"])
    approved = store.list(classification="approved")
    if not approved:
        raise ScriptValidationError(
            "freezing Script DNA requires at least one approved example: "
            "add one with script_dna.py add-example, get it reviewed, then freeze"
        )
    audition = document.get("audition")
    if audition_example_id is not None or audition_timing_ref is not None:
        if not audition_example_id or not audition_timing_ref:
            raise ScriptValidationError("an audition needs both an example id and a timing ref")
        example_path = store.records / f"{audition_example_id.removeprefix('script-example:')}.json"
        if not example_path.is_file():
            raise ScriptValidationError(f"audition example does not exist: {audition_example_id}")
        import json as _json

        example = _json.loads(example_path.read_text(encoding="utf-8"))
        if example.get("classification") != "approved":
            raise ScriptValidationError(
                f"audition example {audition_example_id} is {example.get('classification')!r}, not approved"
            )
        timing_path = (repository_root / audition_timing_ref).resolve()
        if not timing_path.is_relative_to(repository_root) or not timing_path.is_file():
            raise ScriptValidationError(f"audition timing does not exist: {audition_timing_ref}")
        from engine.voiceover import VoiceoverValidationError
        from engine.voiceover import validate_timing as _validate_timing

        try:
            audition_doc = _json.loads(timing_path.read_text(encoding="utf-8"))
            audition_audio = (repository_root / audition_doc["audio"]["path"]).resolve()
            _validate_timing(timing_path, audio_path=audition_audio)
        except (VoiceoverValidationError, KeyError) as exc:
            raise ScriptValidationError(f"audition timing is invalid: {exc}") from exc
        audition = {"example_id": audition_example_id, "timing_ref": audition_timing_ref}
    document["status"] = "FROZEN"
    if decision_ref not in document["decision_refs"]:
        document["decision_refs"] = [*document["decision_refs"], decision_ref]
    if audition is not None:
        document["audition"] = audition
    validate_script_dna(document, expected_channel_id=package.identity["id"])
    _write_yaml_atomic(path, document)
    return path
