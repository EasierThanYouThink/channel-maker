"""Schema and cross-artifact validation for voiceover timing documents."""

from __future__ import annotations

import hashlib
import json
import wave
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .errors import VoiceoverValidationError
from .voiceover import VOICES, wav_duration_s


def _pcm_sha256(audio_path: Path) -> str:
    """Hash the raw PCM frames of a WAV file.

    The timing document's ``audio.sha256`` identifies PCM bytes, not the WAV
    container: headers, metadata, and encoding parameters are excluded so the
    digest binds the timing to the exact recorded samples. Scene evidence
    that hashes the WAV file is a different identity over the same recording;
    do not compare the two digests directly.
    """
    try:
        with wave.open(str(audio_path), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
    except (OSError, wave.Error, EOFError) as exc:
        raise VoiceoverValidationError(f"cannot read audio {audio_path}: {exc}") from exc
    return hashlib.sha256(frames).hexdigest()


def _check_spans(spans: list[dict[str, Any]], total_s: float, label: str) -> None:
    previous_end = 0.0
    for index, span in enumerate(spans):
        start = span.get("start_s")
        end = span.get("end_s")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            raise VoiceoverValidationError(f"{label} {index}: start_s/end_s must be numbers")
        if not end > start:
            raise VoiceoverValidationError(f"{label} {index}: end_s must exceed start_s")
        if start < 0 or end > total_s + 0.001:
            raise VoiceoverValidationError(
                f"{label} {index}: span [{start}, {end}] escapes the recording (0, {total_s})"
            )
        if start < previous_end - 0.001:
            raise VoiceoverValidationError(f"{label} {index}: spans must be ordered and non-overlapping")
        previous_end = max(previous_end, end)


CONTRACT_ROOT = Path(__file__).resolve().parent / "contracts"


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VoiceoverValidationError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VoiceoverValidationError(f"{path}: expected a JSON object")
    return value


def _schema() -> dict[str, Any]:
    return _load(CONTRACT_ROOT / "voiceover-timing.schema.json")


def validate_timing_document(document: dict[str, Any]) -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors
        )
        raise VoiceoverValidationError(f"voiceover timing violates its schema: {details}")
    voice_name = document["voice"]["name"]
    if voice_name not in VOICES:
        raise VoiceoverValidationError(f"unknown voice {voice_name!r}; known voices: {sorted(VOICES)}")


def validate_timing(
    timing_path: Path,
    *,
    audio_path: Path | None = None,
    target_duration_s: float | None = None,
    max_deviation: float = 0.20,
    header_tolerance_s: float = 0.05,
) -> dict[str, Any]:
    """Validate a timing file against its schema, its audio, and an optional duration target."""
    if not 0 < max_deviation <= 1:
        raise VoiceoverValidationError("max_deviation must be in (0, 1]")
    document = _load(timing_path)
    validate_timing_document(document)
    resolved_audio = Path(audio_path) if audio_path is not None else Path(document["audio"]["path"])
    if not resolved_audio.is_file():
        raise VoiceoverValidationError(f"voiceover audio does not exist: {resolved_audio}")
    measured_s = wav_duration_s(resolved_audio)
    claimed_s = document["total_duration_s"]
    if abs(measured_s - claimed_s) > header_tolerance_s:
        raise VoiceoverValidationError(
            f"audio measures {measured_s:.2f}s but timing claims {claimed_s:.2f}s"
        )
    actual_pcm_sha = _pcm_sha256(resolved_audio)
    claimed_pcm_sha = document["audio"].get("sha256")
    if actual_pcm_sha != claimed_pcm_sha:
        raise VoiceoverValidationError(
            "voiceover audio bytes do not match the timing document: "
            "a different recording of similar length cannot stand in for the timed one"
        )
    _check_spans(document["sentences"], claimed_s, "sentence")
    _check_spans(document["words"], claimed_s, "word")
    report: dict[str, Any] = {
        "timing": str(timing_path), "audio": str(resolved_audio),
        "duration_s": round(measured_s, 3),
        "sentence_count": len(document["sentences"]),
        "word_count": len(document["words"]),
        "measured_words": sum(1 for word in document["words"] if word["method"] == "measured_alignment"),
    }
    if target_duration_s is not None:
        deviation = abs(measured_s - target_duration_s) / target_duration_s
        report["target_duration_s"] = target_duration_s
        report["deviation"] = round(deviation, 3)
        if deviation > max_deviation:
            raise VoiceoverValidationError(
                f"voiceover is {measured_s:.1f}s vs target {target_duration_s:.1f}s "
                f"(deviation {deviation:.0%} exceeds {max_deviation:.0%})"
            )
    return report
