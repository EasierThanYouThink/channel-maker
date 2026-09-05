"""Local-first text-to-speech narration with measured timing evidence.

Synthesis runs fully offline through Piper (no API keys, no network at
synthesis time). Sentence boundaries in the timing record are measured from
real synthesized audio; word timings are measured phoneme alignments when the
phoneme stream maps cleanly onto the sentence's words, otherwise explicitly
labeled uniform estimates. Visual beats should key on sentence timings.
"""

from __future__ import annotations

import hashlib
import re
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import VoiceoverValidationError


TOOL_VERSION = "1.0.0"
TIMING_SCHEMA_VERSION = "1.0.0"
DEFAULT_VOICE = "lessac-medium"
DEFAULT_SENTENCE_SILENCE_S = 0.30

VOICES: dict[str, dict[str, Any]] = {
    "lessac-medium": {
        "language": "en_US",
        "description": "US English, calm — the default channel narrator.",
        "model_file": "en_US-lessac-medium.onnx",
        "model_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "model_bytes": 63201294,
        "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
        "sample_rate_hz": 22050,
    },
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Phoneme-stream tokens that carry no word content and are skipped when
# grouping phonemes into words. Content tokens (including ' ' word breaks
# and attached punctuation like '.') are kept verbatim.
_BOUNDARY_MARKERS = {"^", "$", "<", ">", "_", "#", "|", "‖", "sil"}


def split_sentences(text: str) -> list[str]:
    """Split narration text into sentences; raises on empty input."""
    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(text.strip()) if part.strip()]
    if not sentences:
        raise VoiceoverValidationError("no synthesizable sentences found in narration text")
    return sentences


def ensure_voice_model(voice_name: str, cache_dir: Path) -> tuple[Path, Path]:
    """Return (model, config) paths, downloading the voice on first use."""
    if voice_name not in VOICES:
        raise VoiceoverValidationError(
            f"unknown voice {voice_name!r}; known voices: {sorted(VOICES)}"
        )
    spec = VOICES[voice_name]
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_path = cache_dir / spec["model_file"]
    config_path = cache_dir / (spec["model_file"] + ".json")
    for path, url, expected in (
        (model_path, spec["model_url"], spec["model_bytes"]),
        (config_path, spec["config_url"], None),
    ):
        if path.is_file():
            if expected is not None and path.stat().st_size != expected:
                path.unlink()
            else:
                continue
        try:
            urllib.request.urlretrieve(url, path)
        except OSError as exc:
            if path.is_file():
                path.unlink()
            raise VoiceoverValidationError(
                f"could not download voice {voice_name!r} from {url}: {exc}"
            ) from exc
        if expected is not None and path.stat().st_size != expected:
            path.unlink()
            raise VoiceoverValidationError(
                f"downloaded voice {voice_name!r} has unexpected size "
                f"(got {path.stat().st_size if path.exists() else 0}, want {expected})"
            )
    return model_path, config_path


def load_voice(model_path: Path):
    """Load a Piper voice with alignment support; raises a clear error if piper is missing."""
    try:
        from piper import PiperVoice
    except ImportError as exc:
        raise VoiceoverValidationError(
            "piper-tts is not installed; run `.venv/bin/pip install -r requirements.txt`"
        ) from exc
    return PiperVoice.load(str(model_path), include_alignments=True)


@dataclass
class SentenceAudio:
    text: str
    audio_int16: bytes
    sample_rate_hz: int
    phonemes: list[str]
    alignment_tokens: list[str] | None
    alignment_samples: list[int] | None


def synthesize_sentence(voice, sentence: str) -> SentenceAudio:
    """Synthesize one sentence; returns raw audio plus the phoneme stream for alignment."""
    chunks = list(voice.synthesize(sentence, include_alignments=True))
    if not chunks:
        raise VoiceoverValidationError(f"synthesis produced no audio for: {sentence!r}")
    rate = chunks[0].sample_rate
    audio = b""
    phonemes: list[str] = []
    alignment_tokens: list[str] | None = []
    alignment_samples: list[int] | None = []
    for chunk in chunks:
        if chunk.sample_rate != rate or chunk.sample_channels != 1 or chunk.sample_width != 2:
            raise VoiceoverValidationError(
                "unexpected chunk audio format "
                f"(rate={chunk.sample_rate}, channels={chunk.sample_channels}, width={chunk.sample_width})"
            )
        audio += chunk.audio_int16_bytes
        phonemes.extend(chunk.phonemes)
        if chunk.phoneme_alignments is None:
            alignment_tokens = None
            alignment_samples = None
        elif alignment_tokens is not None and alignment_samples is not None:
            alignment_tokens.extend(str(entry.phoneme) for entry in chunk.phoneme_alignments)
            alignment_samples.extend(int(entry.num_samples) for entry in chunk.phoneme_alignments)
    return SentenceAudio(
        text=sentence,
        audio_int16=audio,
        sample_rate_hz=rate,
        phonemes=phonemes,
        alignment_tokens=alignment_tokens,
        alignment_samples=alignment_samples,
    )


def align_words(
    words: list[str],
    phonemes: list[str],
    alignment_tokens: list[str] | None,
    alignment_samples: list[int] | None,
    sample_rate_hz: int,
    sentence_offset_s: float,
) -> tuple[list[dict[str, Any]], str]:
    """Map words onto measured phoneme durations.

    Returns (word_records, method). Falls back to a labeled uniform estimate
    whenever the phoneme stream does not map cleanly onto the words (e.g. a
    number the phonemizer expanded into several spoken words).
    """
    measured = _measured_word_spans(words, phonemes, alignment_tokens, alignment_samples, sample_rate_hz)
    if measured is not None:
        records = [
            {"text": word, "start_s": round(sentence_offset_s + start, 3),
             "end_s": round(sentence_offset_s + end, 3), "method": "measured_alignment"}
            for word, (start, end) in zip(words, measured)
        ]
        return records, "measured_alignment"
    total_weights = [max(len(word), 1) for word in words]
    return _uniform_words(words, total_weights, sentence_offset_s), "uniform_estimate"


def _measured_word_spans(
    words: list[str],
    phonemes: list[str],
    alignment_tokens: list[str] | None,
    alignment_samples: list[int] | None,
    sample_rate_hz: int,
) -> list[tuple[float, float]] | None:
    if (
        alignment_tokens is None
        or alignment_samples is None
        or len(alignment_tokens) != len(alignment_samples)
    ):
        return None
    # The alignment stream may carry boundary markers ('^', '$', ...) the
    # phoneme list lacks. Compare content streams with markers stripped.
    content_phonemes = [phoneme for phoneme in phonemes if phoneme not in _BOUNDARY_MARKERS]
    content_stream = [
        (token, samples)
        for token, samples in zip(alignment_tokens, alignment_samples)
        if token not in _BOUNDARY_MARKERS
    ]
    if [token for token, _ in content_stream] != content_phonemes:
        return None
    stream = content_stream
    spans: list[tuple[float, float]] = []
    cursor = 0
    word_start: float | None = None
    for phoneme, samples in stream:
        if phoneme == " ":
            if word_start is not None:
                spans.append((word_start, cursor / sample_rate_hz))
                word_start = None
            cursor += samples
        else:
            if word_start is None:
                word_start = cursor / sample_rate_hz
            cursor += samples
    if word_start is not None:
        spans.append((word_start, cursor / sample_rate_hz))
    if len(spans) != len(words) or any(end <= start for start, end in spans):
        return None
    return spans


def _uniform_words(
    words: list[str], weights: list[int], sentence_offset_s: float,
) -> list[dict[str, Any]]:
    # Caller scales these placeholder spans onto the sentence's measured span.
    return [
        {"text": word, "start_s": 0.0, "end_s": 0.0, "method": "uniform_estimate", "_weight": weight}
        for word, weight in zip(words, weights)
    ]


def _fit_uniform_words(
    records: list[dict[str, Any]], start_s: float, end_s: float,
) -> list[dict[str, Any]]:
    """Lay placeholder word spans proportionally across a measured sentence span."""
    for record in records:
        record.pop("_weight", None)
    # Straightforward proportional layout using the precomputed total.
    cursor = start_s
    weights = [max(len(record["text"]), 1) for record in records]
    total = sum(weights)
    for record, weight in zip(records, weights):
        span = (end_s - start_s) * weight / total
        record["start_s"] = round(cursor, 3)
        cursor += span
        record["end_s"] = round(cursor if record is not records[-1] else end_s, 3)
    records[-1]["end_s"] = round(end_s, 3)
    return records


def synthesize_script(
    text: str,
    *,
    voice_name: str = DEFAULT_VOICE,
    model_cache_dir: Path,
    sentence_silence_s: float = DEFAULT_SENTENCE_SILENCE_S,
    audio_path: str = "",
) -> tuple[bytes, int, dict[str, Any]]:
    """Synthesize full narration; returns (wav_audio, sample_rate_hz, timing_document)."""
    if sentence_silence_s < 0:
        raise VoiceoverValidationError("sentence silence must be non-negative")
    sentences = split_sentences(text)
    if voice_name not in VOICES:
        raise VoiceoverValidationError(f"unknown voice {voice_name!r}; known voices: {sorted(VOICES)}")
    model_path, _ = ensure_voice_model(voice_name, model_cache_dir)
    voice = load_voice(model_path)

    rendered = [synthesize_sentence(voice, sentence) for sentence in sentences]
    sample_rate_hz = rendered[0].sample_rate_hz
    silence = b"\x00" * int(sample_rate_hz * sentence_silence_s) * 2

    audio = b""
    sentence_records: list[dict[str, Any]] = []
    word_records: list[dict[str, Any]] = []
    cursor_s = 0.0
    for index, (sentence, track) in enumerate(zip(sentences, rendered)):
        if index:
            audio += silence
            cursor_s += sentence_silence_s
        start_s = cursor_s
        duration_s = len(track.audio_int16) / 2 / sample_rate_hz
        audio += track.audio_int16
        cursor_s += duration_s
        sentence_records.append({
            "index": index, "text": sentence,
            "start_s": round(start_s, 3), "end_s": round(cursor_s, 3),
            "method": "measured_audio",
        })
        words = sentence.split()
        aligned, method = align_words(
            words, track.phonemes, track.alignment_tokens, track.alignment_samples,
            sample_rate_hz, start_s,
        )
        if method == "uniform_estimate":
            aligned = _fit_uniform_words(aligned, start_s, cursor_s)
        word_records.extend(aligned)

    timing = {
        "schema_version": TIMING_SCHEMA_VERSION,
        "artifact_type": "voiceover_timing",
        "voice": {
            "name": voice_name,
            "model": VOICES[voice_name]["model_file"],
            "sample_rate_hz": sample_rate_hz,
        },
        "text": text,
        "sentences": sentence_records,
        "words": word_records,
        "total_duration_s": round(cursor_s, 3),
        "audio": {"path": audio_path, "sha256": hashlib.sha256(audio).hexdigest(),
                  "duration_s": round(cursor_s, 3), "sample_rate_hz": sample_rate_hz},
        "created_by": {"tool": "engine.voiceover.synthesize_script", "version": TOOL_VERSION},
    }
    return audio, sample_rate_hz, timing


def wav_duration_s(path: Path) -> float:
    """Measure real audio duration from the WAV header."""
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() / handle.getframerate()
    except (OSError, wave.Error, EOFError) as exc:
        raise VoiceoverValidationError(f"cannot read audio {path}: {exc}") from exc
