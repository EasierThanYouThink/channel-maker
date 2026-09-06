"""Repository-level safety policies that protect local user data."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", path],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def test_generated_channel_packages_are_ignored_but_placeholder_is_trackable() -> None:
    assert _is_ignored("channels/private-channel/channel.yaml")
    assert not _is_ignored("channels/.gitkeep")
