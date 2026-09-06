#!/usr/bin/env python3
"""Validate one or all repository-owned YouTube Channel Maker packages."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.channel import (  # noqa: E402
    ChannelValidationError,
    validate_channel_package,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "packages",
        nargs="*",
        type=Path,
        help="Channel package directories; defaults to every channels/*/channel.yaml package.",
    )
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root used to resolve canonical paths.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    packages = [path if path.is_absolute() else root / path for path in args.packages]
    if not packages:
        packages = [path.parent for path in sorted((root / "channels").glob("*/channel.yaml"))]
    if not packages:
        print("CHANNEL PACKAGES INVALID\n- no channel packages found")
        return 2

    failures: list[str] = []
    for package in packages:
        try:
            value = validate_channel_package(package, root)
            print(f"CHANNEL VALID {value.identity['id']} ({value.state['state']} / {value.state['status']})")
        except ChannelValidationError as exc:
            failures.append(f"{package}: {exc}")
    if failures:
        print(f"CHANNEL PACKAGES INVALID ({len(failures)} package(s))")
        for failure in failures:
            print(f"- {failure}")
        return 2
    print(f"CHANNEL PACKAGES VALID ({len(packages)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
