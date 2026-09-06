"""Discover and freeze a channel's Visual or Motion DNA seed, domain by domain."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from _confirmation import require_confirmation  # noqa: E402

from engine.design import (  # noqa: E402
    DesignValidationError,
    add_reference,
    check_ready_problems,
    freeze_domain,
    init_seed,
    record_composition,
    record_motion_sample,
    review_composition,
    review_motion_sample,
    seed_path,
    validate_dna_seed,
)


def _confirm(prompt: str, *, assume_yes: bool) -> None:
    require_confirmation(
        assume_yes=assume_yes,
        prompt=prompt,
        error_type=DesignValidationError,
        noninteractive_message="this action requires --yes (non-interactive) or an interactive human terminal",
        cancelled_message="action cancelled",
    )


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

    record_comp = subparsers.add_parser("record-composition")
    record_comp.add_argument("package_root", type=Path)
    record_comp.add_argument("--image", type=Path, required=True)
    record_comp.add_argument("--exemplar-id", action="append", default=[], dest="exemplar_ids")
    record_comp.add_argument("--created-by", required=True)
    record_comp.add_argument("--source-ref", required=True)

    review_comp = subparsers.add_parser("review-composition")
    review_comp.add_argument("package_root", type=Path)
    review_comp.add_argument("--decision", required=True, choices=["approved", "rejected", "borderline"])
    review_comp.add_argument("--reviewer", required=True)
    review_comp.add_argument("--reason", required=True)
    review_comp.add_argument("--yes", action="store_true")

    record_sample = subparsers.add_parser("record-sample")
    record_sample.add_argument("package_root", type=Path)
    record_sample.add_argument("--video", type=Path, required=True)
    record_sample.add_argument("--narration-ref", required=True)
    record_sample.add_argument("--created-by", required=True)
    record_sample.add_argument("--source-ref", required=True)

    review_sample = subparsers.add_parser("review-sample")
    review_sample.add_argument("package_root", type=Path)
    review_sample.add_argument("--decision", required=True, choices=["approved", "rejected", "borderline"])
    review_sample.add_argument("--reviewer", required=True)
    review_sample.add_argument("--reason", required=True)
    review_sample.add_argument("--yes", action="store_true")

    check_ready = subparsers.add_parser("check-ready")
    check_ready.add_argument("package_root", type=Path)

    validate = subparsers.add_parser("validate")
    validate.add_argument("package_root", type=Path)

    return parser.parse_args()


def _resolve_package(package_root: Path, root: Path) -> Path:
    return package_root.resolve() if package_root.is_absolute() else root.resolve() / package_root


def composition_path_record(package_root: Path, root: Path, args: argparse.Namespace) -> Path:
    from engine.design import composition_path

    record_composition(
        _resolve_package(package_root, root), root,
        image=args.image, exemplar_ids=args.exemplar_ids,
        created_by=args.created_by, source_ref=args.source_ref,
    )
    package = _resolve_package(package_root, root)
    return composition_path(package)


def sample_path_record(package_root: Path, root: Path, args: argparse.Namespace) -> Path:
    from engine.design import motion_sample_path

    record_motion_sample(
        _resolve_package(package_root, root), root,
        video=args.video, narration_ref=args.narration_ref,
        created_by=args.created_by, source_ref=args.source_ref,
    )
    package = _resolve_package(package_root, root)
    return motion_sample_path(package)


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
        elif args.command == "record-composition":
            if args.kind != "visual":
                raise DesignValidationError("composition frames belong to visual DNA")
            path = composition_path_record(args.package_root, args.root, args)
            print(path.relative_to(args.root.resolve()).as_posix())
            return 0
        elif args.command == "review-composition":
            if args.kind != "visual":
                raise DesignValidationError("composition frames belong to visual DNA")
            _confirm(f"Record human composition {args.decision!r} for {args.package_root}? Type yes: ", assume_yes=args.yes)
            review = review_composition(
                args.package_root, args.root, decision=args.decision,
                reviewer=args.reviewer, reason=args.reason, human_confirmed=True,
            )
            print(review["review_id"])
            return 0
        elif args.command == "record-sample":
            if args.kind != "motion":
                raise DesignValidationError("motion samples belong to motion DNA")
            path = sample_path_record(args.package_root, args.root, args)
            print(path.relative_to(args.root.resolve()).as_posix())
            return 0
        elif args.command == "review-sample":
            if args.kind != "motion":
                raise DesignValidationError("motion samples belong to motion DNA")
            _confirm(f"Record human motion-sample {args.decision!r} for {args.package_root}? Type yes: ", assume_yes=args.yes)
            review = review_motion_sample(
                args.package_root, args.root, decision=args.decision,
                reviewer=args.reviewer, reason=args.reason, human_confirmed=True,
            )
            print(review["review_id"])
            return 0
        elif args.command == "check-ready":
            resolved = args.package_root.resolve() if args.package_root.is_absolute() else args.root.resolve() / args.package_root
            problems = check_ready_problems(args.kind, resolved, args.root)
            if problems:
                print("NOT READY:")
                for problem in problems:
                    print(f"- {problem}")
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
