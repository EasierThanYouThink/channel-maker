"""Portable platform helpers: venv python resolution + service discovery.

All OS-specific path/shell assumptions live here so engine + tools stay clean.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def project_python(root: Path) -> str:
    """Return the project's venv python if present, else the current interpreter.

    Windows venvs use `.venv/Scripts/python.exe`; POSIX uses `.venv/bin/python`.
    """
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def python_run_args(root: Path) -> list[str]:
    """Argv prefix for running a tools/*.py script with the right interpreter."""
    return [project_python(root)]


def which(command: str) -> str | None:
    """Portable `which`/`where` lookup."""
    return shutil.which(command)


def hermes_config_path() -> Path:
    """Hermes config location (~/.hermes/config.yaml on all OSes)."""
    return Path.home() / ".hermes" / "config.yaml"


def ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")


def service_status() -> dict[str, dict[str, str | bool]]:
    """Best-effort presence checks for the combined-services stack.

    Never raises: each service reports {available, detail}. Used by the
    control-panel overview and `tools/setup.py --check-only`.
    """
    hermes = which("hermes")
    ollama = which("ollama")
    node = which("node")
    npm = which("npm")
    try:
        import piper  # noqa: F401
        piper_ok: bool | str = True
    except ImportError as exc:
        piper_ok = f"missing: {exc}"
    return {
        "hermes": {
            "available": bool(hermes),
            "detail": hermes or "not on PATH — install from hermes-agent.nousresearch.com",
        },
        "ollama": {
            "available": bool(ollama),
            "detail": ollama or "not on PATH — install from ollama.com",
        },
        "piper_tts": {
            "available": piper_ok is True,
            "detail": "installed" if piper_ok is True else str(piper_ok),
        },
        "node": {
            "available": bool(node),
            "detail": node or "optional — only needed for remotion renderers",
        },
        "npm": {
            "available": bool(npm),
            "detail": npm or "optional — only needed for remotion renderers",
        },
    }
