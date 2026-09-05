"""Schema and cross-artifact validation for voiceover timing documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .errors import VoiceoverValidationError
from .voiceover import VOICES, wav_duration_s


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
