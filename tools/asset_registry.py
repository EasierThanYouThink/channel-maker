"""Register, review, and list code-first asset components (the starter visual library)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.library import (  # noqa: E402
    LibraryValidationError,
    list_components,
    register_component,
    review_component,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser("register")
    register.add_argument("--scope", required=True, choices=["ENGINE", "CHANNEL"])
    register.add_argument("--channel-id", default=None)
    register.add_argument("--category", required=True, choices=["primitive", "object", "character", "diagram", "mechanism", "effect"])
    register.add_argument("--name", required=True)
    register.add_argument("--description", required=True)
    register.add_argument("--renderer", required=True, help="Name of the rendering pipeline that consumes this component, e.g. 'remotion'. See docs/RENDER_CONTRACT.md.")
    register.add_argument("--source-kind", required=True, choices=["tsx", "svg", "raster"])
    register.add_argument("--source-path", required=True)
    register.add_argument("--export", action="append", default=[], dest="exports")
    register.add_argument("--interface-json", default="{}")
    register.add_argument("--justification", required=True)
    register.add_argument("--produced-for-pilot-ref", default=None)

    review = subparsers.add_parser("review")
    review.add_argument("component_path", type=Path)
    review.add_argument("--decision", required=True, choices=["approved", "rejected", "deprecated"])
    review.add_argument("--reviewer", required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--created-at")
    review.add_argument("--yes", action="store_true")

    listing = subparsers.add_parser("list")
    listing.add_argument("--scope", choices=["ENGINE", "CHANNEL"], default=None)
    listing.add_argument("--channel-id", default=None)
    listing.add_argument("--category", default=None)
    listing.add_argument("--status", choices=["experimental", "approved", "deprecated"], default=None)

    return parser.parse_args()


def _confirm(prompt: str, *, assume_yes: bool) -> None:
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise LibraryValidationError("this action requires --yes (non-interactive) or an interactive human terminal")
    if input(prompt).strip().lower() != "yes":
        raise LibraryValidationError("action cancelled")


def main() -> int:
    args = parse_args()
    try:
        if args.command == "register":
            path = register_component(
                args.root, scope=args.scope, channel_id=args.channel_id, category=args.category,
                name=args.name, description=args.description, renderer=args.renderer, source_kind=args.source_kind,
                source_path=args.source_path, exports=args.exports, interface=json.loads(args.interface_json),
                justification=args.justification, produced_for_pilot_ref=args.produced_for_pilot_ref,
            )
            print(path.relative_to(args.root.resolve()).as_posix())
        elif args.command == "review":
            _confirm(f"Record human {args.decision} decision for {args.component_path}? Type yes: ", assume_yes=args.yes)
            result = review_component(
                args.root, args.component_path, decision=args.decision, reviewer=args.reviewer,
                reason=args.reason, created_at=args.created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                human_confirmed=True,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            result = list_components(
                args.root, scope=args.scope, category=args.category, status=args.status, channel_id=args.channel_id,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
    except LibraryValidationError as exc:
        print(f"ASSET LIBRARY ERROR\n{exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
