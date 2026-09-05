"""Run channel-maker's deterministic verification suite."""

from __future__ import annotations

import py_compile
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from tools._platform import project_python as _project_python
except ImportError:  # check.py run from a bare checkout without package path
    _project_python = None  # type: ignore[assignment]


@dataclass(frozen=True)
class CheckCommand:
    label: str
    args: list[str]
    cwd: Path


def run(label: str, args: list[str], cwd: Path = ROOT) -> bool:
    print(f"\n[{label}] {' '.join(args)}", flush=True)
    result = subprocess.run(args, cwd=cwd)
    if result.returncode:
        print(f"FAILED: {label} exited {result.returncode}")
        return False
    return True


def commands(root: Path, python: str) -> list[CheckCommand]:
    commands = [
        CheckCommand("channel memory", [python, "tools/channel_memory.py", "validate"], root),
        CheckCommand("niche intelligence contracts", [python, "tools/niche_intelligence.py", "validate-contracts"], root),
        CheckCommand("tests", [python, "-m", "pytest", "-q"], root),
    ]
    if any((root / "channels").glob("*/channel.yaml")):
        commands.insert(0, CheckCommand("channel packages", [python, "tools/validate_channel.py"], root))
    package = root / "remotion" / "package.json"
    if package.exists():
        commands.append(CheckCommand("remotion typecheck", ["npm", "run", "typecheck"], root / "remotion"))
    return commands


def main() -> int:
    failures = []
    if _project_python is not None:
        test_python = _project_python(ROOT)
    else:
        candidates = [ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"]
        test_python = next((str(p) for p in candidates if p.is_file()), sys.executable)

    for path in sorted((ROOT / "tools").glob("*.py")):
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            failures.append(str(exc))
        if path.name != "check.py" and "TODO:" in path.read_text(encoding="utf-8"):
            failures.append(f"executable placeholder remains in {path.relative_to(ROOT)}")

    for command in commands(ROOT, test_python):
        if command.args[0] == "npm" and not shutil.which("npm"):
            failures.append("npm is required because remotion/package.json exists")
            continue
        if not run(command.label, command.args, command.cwd):
            failures.append(command.label)

    if failures:
        print("\nCHECK FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("\nCHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
