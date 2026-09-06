"""Shared handling for explicit human confirmations in command-line tools."""

from __future__ import annotations

import sys


def require_confirmation(
    *,
    assume_yes: bool,
    prompt: str,
    error_type: type[Exception],
    noninteractive_message: str,
    cancelled_message: str,
) -> None:
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise error_type(noninteractive_message)
    try:
        confirmation = input(prompt).strip().lower()
    except EOFError:
        # Windows can report the NUL device as a TTY even though reads end at EOF.
        raise error_type(noninteractive_message) from None
    if confirmation != "yes":
        raise error_type(cancelled_message)
