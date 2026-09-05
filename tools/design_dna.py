"""Discover and freeze a channel's Visual or Motion DNA seed, domain by domain."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.design import (  # noqa: E402
    DesignValidationError,
    add_reference,
    all_domains_frozen,
    freeze_domain,
    init_seed,
    seed_path,
    validate_dna_seed,
)


def _confirm(prompt: str, *, assume_yes: bool) -> None:
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise DesignValidationError("this action requires --yes (non-interactive) or an interactive human terminal")
    if input(prompt).strip().lower() != "yes":
        raise DesignValidationError("action cancelled")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["visual", "motion"])
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("package_root", type=Path)

    add_ref = subparsers.add_parser("add-reference")
    add_ref.add_argument("package_root", type=Path)
    add_ref.add_argument("--domain", required=True)
    add_ref.add_argument("--exemplar-id", required=True)

    freeze = subparsers.add_parser("freeze-domain")
    freeze.add_argument("package_root", type=Path)
    freeze.add_argument("--domain", required=True)
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
            path = init_seed(args.kind, args.package_root, args.root)
        elif args.command == "add-reference":
            path = add_reference(args.kind, args.package_root, args.root, domain=args.domain, exemplar_id=args.exemplar_id)
        elif args.command == "freeze-domain":
            _confirm(f"Freeze {args.kind} domain {args.domain!r} for {args.package_root}? Type yes: ", assume_yes=args.yes)
            path = freeze_domain(
                args.kind, args.package_root, args.root, domain=args.domain,
                human_confirmed=True, decision_ref=args.decision_ref, force=args.force,
            )
        elif args.command == "check-ready":
            resolved = args.package_root.resolve() if args.package_root.is_absolute() else args.root.resolve() / args.package_root
            document = yaml.safe_load(seed_path(args.kind, resolved).read_text(encoding="utf-8"))
            if not all_domains_frozen(args.kind, document):
                unfrozen = [d for d, g in document["domains"].items() if g["authority_status"] != "FROZEN"]
                print(f"NOT READY: unfrozen domains: {unfrozen}")
                return 2
            print(f"ALL {args.kind.upper()} DOMAINS FROZEN")
            return 0
        else:
            resolved = args.package_root.resolve() if args.package_root.is_absolute() else args.root.resolve() / args.package_root
            document = yaml.safe_load(seed_path(args.kind, resolved).read_text(encoding="utf-8"))
            validate_dna_seed(args.kind, document)
            print(f"{args.kind.upper()} DNA SEED VALID")
            return 0
    except DesignValidationError as exc:
        print(f"DESIGN DNA ERROR\n{exc}")
        return 2
    print(path.relative_to(args.root.resolve()).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
