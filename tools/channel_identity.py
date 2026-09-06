"""Discover, review, and freeze a channel's identity: a logo and an About-page description."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.identity import (  # noqa: E402
    ChannelIdentityStore,
    IdentityValidationError,
    add_reference,
    all_domains_frozen,
    freeze_domain,
    identity_path,
    init_identity,
    validate_channel_identity,
)


def _confirm(prompt: str, *, assume_yes: bool) -> None:
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise IdentityValidationError("this action requires --yes (non-interactive) or an interactive human terminal")
    if input(prompt).strip().lower() != "yes":
        raise IdentityValidationError("action cancelled")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("package_root", type=Path)

    add = subparsers.add_parser("add")
    add.add_argument("--channel", required=True)
    add.add_argument("--domain", required=True, choices=["logo", "description"])
    add.add_argument("--title", required=True)
    add.add_argument("--image", type=Path, default=None, help="Required for --domain logo.")
    add.add_argument("--text", default=None, help="Required for --domain description.")
    add.add_argument("--provenance-kind", required=True, choices=["human_supplied_original", "ai_generated_original", "project_original_render"])
    add.add_argument("--created-by", required=True)
    add.add_argument("--source-ref", required=True)
    add.add_argument("--model")
    add.add_argument("--model-version")
    add.add_argument("--prompt-ref")

    review = subparsers.add_parser("review")
    review.add_argument("--channel", required=True)
    review.add_argument("candidate_id")
    review.add_argument("--decision", required=True, choices=["approved", "rejected", "borderline"])
    review.add_argument("--reviewer", required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--created-at")
    review.add_argument("--yes", action="store_true")

    listing = subparsers.add_parser("list")
    listing.add_argument("--channel", required=True)
    listing.add_argument("--domain", choices=["logo", "description"], default=None)
    listing.add_argument("--classification", choices=["experimental", "approved", "rejected", "borderline"], default=None)

    add_ref = subparsers.add_parser("add-reference")
    add_ref.add_argument("package_root", type=Path)
    add_ref.add_argument("--domain", required=True, choices=["logo", "description"])
    add_ref.add_argument("--candidate-id", required=True)

    freeze = subparsers.add_parser("freeze-domain")
    freeze.add_argument("package_root", type=Path)
    freeze.add_argument("--domain", required=True, choices=["logo", "description"])
    freeze.add_argument("--decision-ref", required=True)
    freeze.add_argument("--yes", action="store_true")
    freeze.add_argument("--force", action="store_true", help="Re-freeze an already-frozen domain.")

    check_ready = subparsers.add_parser("check-ready")
    check_ready.add_argument("package_root", type=Path)

    validate = subparsers.add_parser("validate")
    validate.add_argument("package_root", type=Path)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "init":
            path = init_identity(args.package_root, args.root)
            print(path.relative_to(args.root.resolve()).as_posix())
            return 0
        if args.command == "add":
            store = ChannelIdentityStore(args.root, args.channel)
            result = store.add(
                domain=args.domain, title=args.title, provenance_kind=args.provenance_kind,
                created_by=args.created_by, source_ref=args.source_ref, image=args.image, text=args.text,
                model=args.model, model_version=args.model_version, prompt_ref=args.prompt_ref,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "review":
            store = ChannelIdentityStore(args.root, args.channel)
            if not args.yes:
                if not sys.stdin.isatty():
                    raise IdentityValidationError("identity candidate review requires --yes (non-interactive) or an interactive human terminal")
                confirmation = input(f"Record human {args.decision} decision for {args.candidate_id}? Type yes: ").strip().lower()
                if confirmation != "yes":
                    raise IdentityValidationError("human identity candidate review cancelled")
            result = store.review(
                args.candidate_id, decision=args.decision, reviewer=args.reviewer, reason=args.reason,
                created_at=args.created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                human_confirmed=True,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "list":
            store = ChannelIdentityStore(args.root, args.channel)
            print(json.dumps(store.list(domain=args.domain, classification=args.classification), indent=2, sort_keys=True))
            return 0
        if args.command == "add-reference":
            path = add_reference(args.package_root, args.root, domain=args.domain, candidate_id=args.candidate_id)
            print(path.relative_to(args.root.resolve()).as_posix())
            return 0
        if args.command == "freeze-domain":
            _confirm(f"Freeze identity domain {args.domain!r} for {args.package_root}? Type yes: ", assume_yes=args.yes)
            path = freeze_domain(args.package_root, args.root, domain=args.domain, human_confirmed=True, decision_ref=args.decision_ref, force=args.force)
            print(path.relative_to(args.root.resolve()).as_posix())
            return 0
        if args.command == "check-ready":
            resolved = args.package_root.resolve() if args.package_root.is_absolute() else args.root.resolve() / args.package_root
            document = yaml.safe_load(identity_path(resolved).read_text(encoding="utf-8"))
            if not all_domains_frozen(document):
                unfrozen = [d for d, g in document["domains"].items() if g["authority_status"] != "FROZEN"]
                print(f"NOT READY: unfrozen domains: {unfrozen}")
                return 2
            print("ALL IDENTITY DOMAINS FROZEN")
            return 0
        resolved = args.package_root.resolve() if args.package_root.is_absolute() else args.root.resolve() / args.package_root
        document = yaml.safe_load(identity_path(resolved).read_text(encoding="utf-8"))
        validate_channel_identity(document)
        print("CHANNEL IDENTITY VALID")
        return 0
    except IdentityValidationError as exc:
        print(f"CHANNEL IDENTITY ERROR\n{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
