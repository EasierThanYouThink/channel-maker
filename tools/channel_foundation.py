"""Write and confirm a channel's Foundation (conceptual identity layer)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.foundation import (  # noqa: E402
    FoundationValidationError,
    attach_foundation_decision,
    validate_foundation,
    write_foundation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    write = subparsers.add_parser("write")
    write.add_argument("package_root", type=Path)
    write.add_argument("--audience-description", required=True)
    write.add_argument("--audience-demographics", default=None)
    write.add_argument("--promise", required=True)
    write.add_argument("--niche-primary", required=True)
    write.add_argument("--sub-niche", action="append", default=[], dest="sub_niches")
    write.add_argument("--personality", action="append", required=True, dest="personality")
    write.add_argument("--balance", required=True, choices=["MOSTLY_EDUCATIONAL", "BALANCED", "MOSTLY_ENTERTAINMENT"])
    write.add_argument("--differentiation", required=True)
    write.add_argument("--emotional-goal", required=True)
    write.add_argument("--content-boundary", action="append", required=True, dest="content_boundaries")
    write.add_argument("--primary-format", required=True, choices=["SHORTS", "LONG_FORM"])
    write.add_argument("--avoids", action="append", required=True, dest="deliberately_avoids")
    write.add_argument("--force", action="store_true", help="Overwrite an existing draft (clears attached decision_refs).")

    attach = subparsers.add_parser("attach-decision")
    attach.add_argument("package_root", type=Path)
    attach.add_argument("--decision-ref", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("package_root", type=Path)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "write":
            path = write_foundation(
                args.package_root, args.root,
                audience_description=args.audience_description, audience_demographics=args.audience_demographics,
                promise=args.promise, niche_primary=args.niche_primary, sub_niches=args.sub_niches,
                personality=args.personality, education_entertainment_balance=args.balance,
                differentiation=args.differentiation, emotional_goal=args.emotional_goal,
                content_boundaries=args.content_boundaries, primary_format=args.primary_format,
                deliberately_avoids=args.deliberately_avoids, force=args.force,
            )
        elif args.command == "attach-decision":
            path = attach_foundation_decision(args.package_root, args.root, decision_ref=args.decision_ref)
        else:
            path = (args.package_root.resolve() if args.package_root.is_absolute() else args.root.resolve() / args.package_root) / "strategy" / "foundation.yaml"
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            validate_foundation(document)
            print(f"CHANNEL FOUNDATION VALID {path}")
            return 0
    except FoundationValidationError as exc:
        print(f"CHANNEL FOUNDATION ERROR\n{exc}")
        return 2
    print(path.relative_to(args.root.resolve()).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
