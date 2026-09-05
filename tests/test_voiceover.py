"""Tests for local-first narration: splitting, alignment, validation, end-to-end synthesis."""

from __future__ import annotations

import json
import tempfile
import wave
from pathlib import Path

import pytest

from engine.voiceover import (
    VoiceoverValidationError,
    align_words,
    ensure_voice_model,
    split_sentences,
    synthesize_script,
    validate_timing,
    validate_timing_document,
    wav_duration_s,
)


def test_split_sentences_basic() -> None:
    assert split_sentences("Hello world. How are you? Fine!") == ["Hello world.", "How are you?", "Fine!"]
    assert split_sentences("  One.  ") == ["One."]


def test_split_sentences_rejects_empty() -> None:
    with pytest.raises(VoiceoverValidationError, match="no synthesizable sentences"):
        split_sentences("   ")


def test_align_words_measured_from_phoneme_stream() -> None:
    phonemes = ["h", "ə", "l", "o", " ", "w", "ɜ", "l", "d"]
    tokens = ["^", *phonemes, "$"]
    samples = [200, 100, 100, 100, 100, 50, 100, 100, 100, 100, 300]
    records, method = align_words(["hello", "world"], phonemes, tokens, samples, 1000, 1.0)
    assert method == "measured_alignment"
    assert [record["text"] for record in records] == ["hello", "world"]
    assert records[0]["start_s"] == 1.0
    assert records[0]["end_s"] == pytest.approx(1.4)
    assert records[1]["start_s"] == pytest.approx(1.45)
    assert records[1]["end_s"] == pytest.approx(1.85)
    assert all(record["method"] == "measured_alignment" for record in records)


def test_align_words_falls_back_to_labeled_estimate() -> None:
    records, method = align_words(["twenty", "things", "extra"], ["t", "w", " ", "θ"], ["t", "w", " ", "θ"], [100, 100, 50, 100], 1000, 0.0)
    assert method == "uniform_estimate"
    assert all(record["method"] == "uniform_estimate" for record in records)
    records, method = align_words(["hello"], ["h", "o"], None, None, 1000, 0.0)
    assert method == "uniform_estimate"


def _write_wav(path: Path, *, frames: int, rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * frames)


def _timing_doc(audio_path: Path, duration_s: float) -> dict:
    return {
        "schema_version": "1.0.0", "artifact_type": "voiceover_timing",
        "voice": {"name": "lessac-medium", "model": "en_US-lessac-medium.onnx", "sample_rate_hz": 22050},
        "text": "Hello world.",
        "sentences": [{"index": 0, "text": "Hello world.", "start_s": 0.0, "end_s": duration_s, "method": "measured_audio"}],
        "words": [
            {"text": "Hello", "start_s": 0.0, "end_s": duration_s / 2, "method": "measured_alignment"},
            {"text": "world", "start_s": duration_s / 2, "end_s": duration_s, "method": "measured_alignment"},
        ],
        "total_duration_s": duration_s,
        "audio": {"path": str(audio_path), "sha256": "0" * 64, "duration_s": duration_s, "sample_rate_hz": 22050},
        "created_by": {"tool": "test", "version": "1.0.0"},
    }


def test_validate_timing_accepts_matching_audio(tmp_path: Path) -> None:
    audio = tmp_path / "voice.wav"
    _write_wav(audio, frames=22050)
    timing = tmp_path / "timing.json"
    timing.write_text(json.dumps(_timing_doc(audio, 1.0)), encoding="utf-8")
    report = validate_timing(timing, target_duration_s=1.0)
    assert report["duration_s"] == pytest.approx(1.0)
    assert report["measured_words"] == 2


def test_validate_timing_rejects_duration_mismatch(tmp_path: Path) -> None:
    audio = tmp_path / "voice.wav"
    _write_wav(audio, frames=22050)
    timing = tmp_path / "timing.json"
    timing.write_text(json.dumps(_timing_doc(audio, 5.0)), encoding="utf-8")
    with pytest.raises(VoiceoverValidationError, match="measures .* but timing claims"):
        validate_timing(timing)


def test_validate_timing_rejects_missing_audio_and_bad_target(tmp_path: Path) -> None:
    timing = tmp_path / "timing.json"
    timing.write_text(json.dumps(_timing_doc(tmp_path / "nope.wav", 1.0)), encoding="utf-8")
    with pytest.raises(VoiceoverValidationError, match="does not exist"):
        validate_timing(timing)
    audio = tmp_path / "voice.wav"
    _write_wav(audio, frames=22050)
    timing.write_text(json.dumps(_timing_doc(audio, 1.0)), encoding="utf-8")
    with pytest.raises(VoiceoverValidationError, match="exceeds"):
        validate_timing(timing, target_duration_s=25.0)


def test_validate_timing_document_rejects_unknown_voice(tmp_path: Path) -> None:
    audio = tmp_path / "voice.wav"
    _write_wav(audio, frames=22050)
    document = _timing_doc(audio, 1.0)
    document["voice"]["name"] = "morgan-freeman"
    timing = tmp_path / "timing.json"
    timing.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(VoiceoverValidationError, match="unknown voice"):
        validate_timing(timing)


def _shared_model_cache() -> Path:
    cache = Path(tempfile.gettempdir()) / "channel-maker-test-voices"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def test_synthesize_script_end_to_end() -> None:
    try:
        cache = _shared_model_cache()
        ensure_voice_model("lessac-medium", cache)
    except VoiceoverValidationError as exc:
        pytest.skip(f"voice model unavailable (offline?): {exc}")
    audio, rate, timing = synthesize_script(
        "Hello world. This is a second sentence.", model_cache_dir=cache, sentence_silence_s=0.1,
        audio_path="voice/test.wav",
    )
    assert rate == 22050
    assert len(audio) > 0
    validate_timing_document(timing)
    assert len(timing["sentences"]) == 2
    assert all(sentence["method"] == "measured_audio" for sentence in timing["sentences"])
    assert timing["sentences"][1]["start_s"] > timing["sentences"][0]["end_s"]
    assert timing["total_duration_s"] > 1.0
    assert len(timing["words"]) >= 4
    assert {word["method"] for word in timing["words"]} <= {"measured_alignment", "uniform_estimate"}
