"""Shared voiceover error type (kept separate to avoid a validation/engine import cycle)."""

from __future__ import annotations


class VoiceoverValidationError(ValueError):
    """A voiceover artifact violates its schema, audio, or duration rules."""
