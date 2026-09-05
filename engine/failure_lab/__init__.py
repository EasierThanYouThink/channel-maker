"""Production failure replay lab: recurring failures as reproducible cases.

Each useful failure becomes a small case with its original inputs, visible
symptom, diagnosis, and verified repair. Voice, renderer, or component
changes must pass relevant replays; a human judges any changed perceptual
baseline. Cases enter the trusted collection only by reproducing first.
"""

from .store import (
    FailureLabError,
    file_case,
    lab_root,
    list_cases,
    record_repair,
    record_replay,
)

__all__ = [
    "FailureLabError",
    "file_case",
    "lab_root",
    "list_cases",
    "record_repair",
    "record_replay",
]
