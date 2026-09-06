#!/usr/bin/env python3
"""Failure replay lab: file cases, record repairs, replay against upgrades."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.failure_lab import (  # noqa: E402
    FailureLabError,
    file_case,
    list_cases,
    record_repair,
    record_replay,
)
from engine.failure_lab.store import init_lab  # noqa: E402


def _versions(values: list[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for value in values:
        try:
            name, version = value.split("=", 1)
        except ValueError as exc:
            raise FailureLabError(f"versions must use NAME=VERSION: {value!r}") from exc
        versions[name.strip()] = version.strip()
    return versions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("package_root", type=Path)

    file_ = commands.add_parser("file")
    file_.add_argument("package_root", type=Path)
    file_.add_argument("case_id")
    file_.add_argument("--symptom", required=True)
    file_.add_argument("--input-ref", action="append", default=[], dest="input_refs")
    file_.add_argument("--reproduction-ref", required=True)
    file_.add_argument("--diagnosis", default="")
    file_.add_argument("--tool-version", action="append", default=[], dest="tool_versions")
    file_.add_argument("--release", default=None)

    repair = commands.add_parser("repair")
    repair.add_argument("package_root", type=Path)
    repair.add_argument("case_id")
    repair.add_argument("--repair", required=True)
    repair.add_argument("--repair-ref", required=True)
    repair.add_argument("--verified", action="store_true")

    replay = commands.add_parser("replay")
    replay.add_argument("package_root", type=Path)
    replay.add_argument("case_id")
    replay.add_argument("--passed", action="store_true")
    replay.add_argument("--failed", action="store_true")
    replay.add_argument("--tool-version", action="append", default=[], dest="tool_versions")
    replay.add_argument("--notes", default="")

    show = commands.add_parser("list")
    show.add_argument("package_root", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "init":
            print(init_lab(args.package_root, args.root))
        elif args.command == "file":
            print(file_case(
                args.package_root, args.root, case_id=args.case_id, symptom=args.symptom,
                input_refs=args.input_refs, reproduction_ref=args.reproduction_ref,
                diagnosis=args.diagnosis, tool_versions=_versions(args.tool_versions),
                release=args.release,
            ))
        elif args.command == "repair":
            print(record_repair(
                args.package_root, args.root, case_id=args.case_id, repair=args.repair,
                repair_ref=args.repair_ref, verified=args.verified,
            ))
        elif args.command == "replay":
            if args.passed == args.failed:
                raise FailureLabError("replay needs exactly one of --passed or --failed")
            print(record_replay(
                args.package_root, args.root, case_id=args.case_id, passed=args.passed,
                tool_versions=_versions(args.tool_versions), notes=args.notes,
            ))
        else:
            print(json.dumps(list_cases(args.package_root, args.root), indent=2, sort_keys=True))
    except FailureLabError as exc:
        print(f"FAILURE LAB ERROR\n- {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
