"""Local-first narration: offline Piper TTS plus measured timing evidence.

One voice per channel, chosen once and reused for consistency. Sentence
timings are measured from real audio; word timings are measured alignments
where the phoneme stream maps cleanly, otherwise labeled estimates.
"""

from .errors import VoiceoverValidationError
from .validation import validate_timing, validate_timing_document
from .voiceover import (
    DEFAULT_SENTENCE_SILENCE_S,
    DEFAULT_VOICE,
    TOOL_VERSION,
    VOICES,
    align_words,
    ensure_voice_model,
    split_sentences,
    synthesize_script,
    wav_duration_s,
)

__all__ = [
    "DEFAULT_SENTENCE_SILENCE_S",
    "DEFAULT_VOICE",
    "TOOL_VERSION",
    "VOICES",
    "VoiceoverValidationError",
    "align_words",
    "ensure_voice_model",
    "split_sentences",
    "synthesize_script",
    "validate_timing",
    "validate_timing_document",
    "wav_duration_s",
]
