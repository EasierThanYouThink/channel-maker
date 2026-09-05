#!/usr/bin/env python3
"""Write and validate structured human decision records for gates and reviews."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.decisions import DecisionError, validate_record_file, write_record  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)

    write = commands.add_parser("write")
    write.add_argument("path", type=Path)
    write.add_argument("--kind", required=True, choices=["strategy", "review"])
    write.add_argument("--title", required=True)
    write.add_argument("--summary", required=True)
    write.add_argument("--selected", action="append", default=[])
    write.add_argument("--rejected", action="append", default=[])
    write.add_argument("--constraint", default=None)
    write.add_argument("--revisit", default=None)
    write.add_argument("--decision", default=None)
    write.add_argument("--rev", default=None)
    write.add_argument("--author", default="human")

    validate = commands.add_parser("validate")
    validate.add_argument("path", type=Path)
    validate.add_argument("--kind", default=None, choices=["strategy", "review"])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    path = args.path if args.path.is_absolute() else root / args.path
    try:
        if args.command == "write":
            if not str(path.resolve()).startswith(str(root)):
                raise DecisionError(f"decision record escapes repository root: {args.path}")
            write_record(
                path, kind=args.kind, title=args.title, summary=args.summary,
                selected=args.selected or None, rejected=args.rejected or None,
                constraint=args.constraint, revisit=args.revisit,
                decision=args.decision, rev=args.rev, author=args.author,
            )
            print(path.relative_to(root).as_posix())
        else:
            metadata = validate_record_file(path, expected_kind=args.kind)
            print(json.dumps(metadata, indent=2, sort_keys=True, default=str))
    except DecisionError as exc:
        print(f"DECISION RECORD ERROR\n- {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
