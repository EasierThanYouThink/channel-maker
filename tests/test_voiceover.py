"""Tests for local-first narration: splitting, alignment, validation, end-to-end synthesis."""

from __future__ import annotations

import hashlib
import json
import tempfile
import wave
from pathlib import Path

import pytest

from engine.voiceover import (
    VOICES,
    VoiceoverValidationError,
    align_words,
    ensure_voice_model,
    split_sentences,
    synthesize_script,
    validate_timing,
    validate_timing_document,
)


def test_split_sentences_basic() -> None:
    assert split_sentences("Hello world. How are you? Fine!") == ["Hello world.", "How are you?", "Fine!"]
    assert split_sentences("  One.  ") == ["One."]


def test_split_sentences_rejects_empty() -> None:
    with pytest.raises(VoiceoverValidationError, match="no synthesizable sentences"):
        split_sentences("   ")


def test_ensure_voice_model_replaces_same_size_corrupt_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    model_bytes = b"good"
    config_bytes = b'{"audio": {}}'
    monkeypatch.setitem(
        VOICES,
        "test-voice",
        {
            "model_file": "test.onnx",
            "model_url": "https://example.invalid/test.onnx",
            "model_bytes": len(model_bytes),
            "model_sha256": hashlib.sha256(model_bytes).hexdigest(),
            "config_url": "https://example.invalid/test.onnx.json",
            "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
            "sample_rate_hz": 22050,
        },
    )
    model_path = tmp_path / "test.onnx"
    model_path.write_bytes(b"evil")
    downloads: list[Path] = []

    def download(url: str, target: str | Path):
        path = Path(target)
        downloads.append(path)
        path.write_bytes(config_bytes if url.endswith(".json") else model_bytes)
        return str(path), None

    monkeypatch.setattr("urllib.request.urlretrieve", download)

    model, config = ensure_voice_model("test-voice", tmp_path)

    assert model.read_bytes() == model_bytes
    assert config.read_bytes() == config_bytes
    assert downloads


def test_ensure_voice_model_stages_verified_download_before_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    model_bytes = b"model"
    config_bytes = b"config"
    monkeypatch.setitem(
        VOICES,
        "atomic-voice",
        {
            "model_file": "atomic.onnx",
            "model_url": "https://example.invalid/atomic.onnx",
            "model_sha256": hashlib.sha256(model_bytes).hexdigest(),
            "config_url": "https://example.invalid/atomic.onnx.json",
            "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
            "sample_rate_hz": 22050,
        },
    )
    final_paths = {tmp_path / "atomic.onnx", tmp_path / "atomic.onnx.json"}
    download_paths: list[Path] = []

    def download(url: str, target: str | Path):
        path = Path(target)
        download_paths.append(path)
        assert path not in final_paths
        assert path.parent == tmp_path
        path.write_bytes(config_bytes if url.endswith(".json") else model_bytes)
        return str(path), None

    monkeypatch.setattr("urllib.request.urlretrieve", download)

    model, config = ensure_voice_model("atomic-voice", tmp_path)

    assert model.read_bytes() == model_bytes
    assert config.read_bytes() == config_bytes
    assert len(download_paths) == 2
    assert not list(tmp_path.glob("*.download"))


def test_align_words_measured_from_phoneme_stream() -> None:
    phonemes = ["h", "ə", "l", "o", " ", "w", "ɜ", "l", "d"]
    tokens = ["^", *phonemes, "$"]
    samples = [200, 100, 100, 100, 100, 50, 100, 100, 100, 100, 300]
    records, method = align_words(["hello", "world"], phonemes, tokens, samples, 1000, 1.0)
    assert method == "measured_alignment"
    assert [record["text"] for record in records] == ["hello", "world"]
    # Boundary markers '^' (200 samples) and '$' (300) occupy real audio time,
    # so the cursor advances through them: hello spans 1.2-1.6, world 1.65-2.05.
    assert records[0]["start_s"] == pytest.approx(1.2)
    assert records[0]["end_s"] == pytest.approx(1.6)
    assert records[1]["start_s"] == pytest.approx(1.65)
    assert records[1]["end_s"] == pytest.approx(2.05)
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
    import hashlib

    # Fixture audio is always 22050 frames of silence; bind the timing doc to
    # those exact PCM bytes the way synthesize_script does for real narration.
    pcm_sha = hashlib.sha256(b"\x00\x00" * 22050).hexdigest()
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
        "audio": {"path": str(audio_path), "sha256": pcm_sha, "duration_s": duration_s, "sample_rate_hz": 22050},
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
    with pytest.raises(VoiceoverValidationError, match=r"measures .* but timing claims"):
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


def test_validate_timing_rejects_swapped_recording_with_same_duration(tmp_path: Path) -> None:
    audio = tmp_path / "voice.wav"
    _write_wav(audio, frames=22050)
    timing = tmp_path / "timing.json"
    document = _timing_doc(audio, 1.0)
    document["audio"]["sha256"] = "1" * 64
    timing.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(VoiceoverValidationError, match="do not match the timing document"):
        validate_timing(timing)


def test_validate_timing_rejects_overlapping_spans(tmp_path: Path) -> None:
    audio = tmp_path / "voice.wav"
    _write_wav(audio, frames=22050)
    timing = tmp_path / "timing.json"
    document = _timing_doc(audio, 1.0)
    document["words"][1]["start_s"] = 0.1
    timing.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(VoiceoverValidationError, match="ordered and non-overlapping"):
        validate_timing(timing)


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
