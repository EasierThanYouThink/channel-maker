"""Check and (if passing) persist a channel's CHANNEL_READY readiness report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.readiness import (  # noqa: E402
    ReadinessError,
    check_readiness,
    write_readiness_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true", help="Persist readiness-report.json if every item passes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = check_readiness(args.package_root, args.root)
        print(json.dumps(report, indent=2, sort_keys=True))
        if not report["overall_passed"]:
            return 2
        if args.write:
            path = write_readiness_report(args.package_root, args.root)
            print(f"WROTE {path}")
    except ReadinessError as exc:
        print(f"READINESS ERROR\n{exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
