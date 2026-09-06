#!/usr/bin/env python3
"""Cross-platform setup for channel-maker (Windows / macOS / Linux).

Creates `.venv`, installs `requirements.txt`, and reports the status of the
combined-services stack (Hermes, Ollama, Piper, Node/npm). Never installs
external services automatically — it prints the per-OS next step instead.

Usage:
  python tools/setup.py                  # full setup (venv + deps + report)
  python tools/setup.py --check-only     # report only, change nothing
  python tools/setup.py --no-venv        # install deps into current interpreter
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools._platform import project_python, service_status  # noqa: E402

MIN_PYTHON = (3, 10)


def _venv_python(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _run(args: list[str]) -> int:
    print(f"$ {' '.join(args)}", flush=True)
    return subprocess.run(args).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--no-venv", action="store_true")
    parser.add_argument("--json", action="store_true",
                        help="With --check-only: emit the report as JSON (for agents to parse).")
    args = parser.parse_args()

    if sys.version_info < MIN_PYTHON:
        print(f"ERROR: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required, found {sys.version.split()[0]}")
        return 1

    venv = ROOT / ".venv"
    python = _venv_python(venv) if not args.no_venv else Path(sys.executable)

    if args.check_only:
        import json as _json

        report = {
            "repo": str(ROOT),
            "python": sys.version.split()[0],
            "python_executable": sys.executable,
            "venv_present": _venv_python(venv).is_file(),
            "venv_python": str(_venv_python(venv)),
            "project_python": project_python(ROOT),
            "services": service_status(),
            "ornith_gpu_check": "python tools/ollama_gpu.py --json",
            "docs": "docs/SETUP.md for per-OS install steps for MISS services",
        }
        if args.json:
            print(_json.dumps(report, indent=2, sort_keys=True))
        else:
            print(f"repo: {report['repo']}")
            print(f"python: {report['python']} ({report['python_executable']})")
            print(f"venv: {'present' if report['venv_present'] else 'missing'} ({report['venv_python']})")
            print(f"project python: {report['project_python']}")
            for name, info in report["services"].items():
                mark = "OK " if info["available"] else "MISS"
                print(f"[{mark}] {name}: {info['detail']}")
            print(f"ornith processor check: {report['ornith_gpu_check']}")
            print("\nSee docs/SETUP.md for per-OS install steps for MISS services.")
        return 0

    if not args.no_venv and not _venv_python(venv).is_file():
        print(f"Creating venv at {venv} ...")
        if _run([sys.executable, "-m", "venv", str(venv)]):
            return 1
    print("Upgrading pip ...")
    if _run([str(python), "-m", "pip", "install", "--upgrade", "pip"]):
        return 1
    print("Installing requirements ...")
    if _run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")]):
        return 1

    print("\nSetup complete. Service status:")
    for name, info in service_status().items():
        mark = "OK " if info["available"] else "MISS"
        print(f"[{mark}] {name}: {info['detail']}")
    print("\nNext:")
    if sys.platform == "win32":
        print(r"  .venv\Scripts\Activate.ps1   # activate (PowerShell)")
    else:
        print("  source .venv/bin/activate     # activate (bash/zsh)")
    print("  python tools/check.py           # verify (works on all OSes)")
    print("  python tools/ollama_gpu.py       # preload Ornith + report CPU/GPU split")
    print("  See docs/SETUP.md for Hermes + Ollama per-OS steps.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
