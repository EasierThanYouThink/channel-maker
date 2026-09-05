"""Register, human-classify, and list one channel's design exemplars."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.design import ChannelExemplarStore, DesignValidationError  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--channel", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add")
    add.add_argument("image", type=Path)
    add.add_argument("--title", required=True)
    add.add_argument("--domain", choices=["visual_identity", "typography", "color_language", "composition_grammar", "scene_aesthetics", "motion_identity"], default=None)
    add.add_argument("--tag", action="append", default=[])
    add.add_argument("--provenance-kind", required=True, choices=["human_supplied_original", "ai_generated_original", "project_original_render"])
    add.add_argument("--created-by", required=True)
    add.add_argument("--source-ref", required=True)
    add.add_argument("--model")
    add.add_argument("--model-version")
    add.add_argument("--prompt-ref")

    review = subparsers.add_parser("review")
    review.add_argument("exemplar_id")
    review.add_argument("--decision", required=True, choices=["approved", "rejected", "borderline"])
    review.add_argument("--reviewer", required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--created-at")
    review.add_argument("--yes", action="store_true")

    listing = subparsers.add_parser("list")
    listing.add_argument("--domain", default=None)
    listing.add_argument("--classification", choices=["experimental", "approved", "rejected", "borderline"])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = ChannelExemplarStore(args.root, args.channel)
    try:
        if args.command == "add":
            result = store.add(
                args.image, title=args.title, domain=args.domain, tags=args.tag,
                provenance_kind=args.provenance_kind, created_by=args.created_by, source_ref=args.source_ref,
                model=args.model, model_version=args.model_version, prompt_ref=args.prompt_ref,
            )
        elif args.command == "review":
            if not args.yes:
                if not sys.stdin.isatty():
                    raise DesignValidationError("exemplar review requires --yes (non-interactive) or an interactive human terminal")
                confirmation = input(f"Record human {args.decision} decision for {args.exemplar_id}? Type yes: ").strip().lower()
                if confirmation != "yes":
                    raise DesignValidationError("human exemplar review cancelled")
            result = store.review(
                args.exemplar_id, decision=args.decision, reviewer=args.reviewer, reason=args.reason,
                created_at=args.created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                human_confirmed=True,
            )
        else:
            result = store.list(domain=args.domain, classification=args.classification)
        print(json.dumps(result, indent=2, sort_keys=True))
    except DesignValidationError as exc:
        print(f"DESIGN EXEMPLAR ERROR\n{exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
