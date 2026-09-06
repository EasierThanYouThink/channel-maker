"""Synthesize local-first narration audio plus measured timing evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.voiceover import (  # noqa: E402
    DEFAULT_SENTENCE_SILENCE_S,
    DEFAULT_VOICE,
    VOICES,
    VoiceoverValidationError,
    synthesize_script,
    validate_timing,
)


def _write_wav_atomic(path: Path, audio_int16: bytes, sample_rate_hz: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(descriptor)  # wave reopens by path below; never leak the mkstemp fd
    try:
        with wave.open(temporary_name, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate_hz)
            handle.writeframes(audio_int16)
        Path(temporary_name).replace(path)
    finally:
        leftover = Path(temporary_name)
        if leftover.exists():
            leftover.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    synth = subparsers.add_parser("synthesize")
    synth.add_argument("--text", default=None, help="Narration text (or use --script-path).")
    synth.add_argument("--script-path", type=Path, default=None, help="File holding the narration text.")
    synth.add_argument("--voice", default=DEFAULT_VOICE, choices=sorted(VOICES),
                       help="Voice identity; pick once per channel and reuse it.")
    synth.add_argument("--output-audio", type=Path, required=True)
    synth.add_argument("--output-timing", type=Path, required=True)
    synth.add_argument("--sentence-silence", type=float, default=DEFAULT_SENTENCE_SILENCE_S)
    synth.add_argument("--voice-model-dir", type=Path, default=None,
                       help="Voice model cache (default: data/local/piper-voices under --root).")

    check = subparsers.add_parser("validate")
    check.add_argument("timing_path", type=Path)
    check.add_argument("--audio-path", type=Path, default=None)
    check.add_argument("--target-duration-seconds", type=float, default=None)
    check.add_argument("--max-deviation", type=float, default=0.20)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "synthesize":
            if bool(args.text) == bool(args.script_path):
                raise VoiceoverValidationError("pass exactly one of --text or --script-path")
            text = args.text if args.text is not None else args.script_path.read_text(encoding="utf-8")
            root = args.root.resolve()
            model_dir = args.voice_model_dir or (root / "data" / "local" / "piper-voices")
            audio_path = args.output_audio if args.output_audio.is_absolute() else root / args.output_audio
            timing_path = args.output_timing if args.output_timing.is_absolute() else root / args.output_timing
            audio_rel = audio_path.relative_to(root).as_posix() if audio_path.is_relative_to(root) else str(audio_path)
            audio, sample_rate_hz, timing = synthesize_script(
                text, voice_name=args.voice, model_cache_dir=model_dir,
                sentence_silence_s=args.sentence_silence, audio_path=audio_rel,
            )
            _write_wav_atomic(audio_path, audio, sample_rate_hz)
            timing_path.parent.mkdir(parents=True, exist_ok=True)
            timing_path.write_text(json.dumps(timing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"{timing_path.relative_to(root).as_posix() if timing_path.is_relative_to(root) else timing_path}")
            print(f"{audio_path.relative_to(root).as_posix() if audio_path.is_relative_to(root) else audio_path}")
            print(f"DURATION {timing['total_duration_s']:.1f}s SENTENCES {len(timing['sentences'])} WORDS {len(timing['words'])}")
            return 0
        root = args.root.resolve()
        timing_path = args.timing_path if args.timing_path.is_absolute() else root / args.timing_path
        audio_path = args.audio_path
        if audio_path is not None and not audio_path.is_absolute():
            audio_path = (timing_path.parent / audio_path).resolve()
        report = validate_timing(
            timing_path, audio_path=audio_path,
            target_duration_s=args.target_duration_seconds, max_deviation=args.max_deviation,
        )
        print(f"VOICEOVER VALID {report['duration_s']:.1f}s "
              f"SENTENCES {report['sentence_count']} WORDS {report['word_count']} "
              f"MEASURED {report['measured_words']}")
        return 0
    except VoiceoverValidationError as exc:
        print(f"VOICEOVER ERROR\n{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
