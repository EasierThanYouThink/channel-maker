"""Channel Foundation: the conceptual identity layer for a Channel Package."""

from .acquisition import attach_foundation_decision, write_foundation
from .validation import FoundationValidationError, validate_foundation

__all__ = [
    "FoundationValidationError",
    "attach_foundation_decision",
    "validate_foundation",
    "write_foundation",
]
