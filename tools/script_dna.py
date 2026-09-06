"""Draft, freeze, and manage candidate examples for a channel's Script DNA."""

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

from _confirmation import require_confirmation  # noqa: E402

from engine.script import (  # noqa: E402
    ScriptExampleStore,
    ScriptValidationError,
    freeze_script_dna,
    validate_script_dna,
    write_script_dna,
)


def _confirm(prompt: str, *, assume_yes: bool) -> None:
    require_confirmation(
        assume_yes=assume_yes,
        prompt=prompt,
        error_type=ScriptValidationError,
        noninteractive_message="this action requires --yes (non-interactive) or an interactive human terminal",
        cancelled_message="action cancelled",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    write = subparsers.add_parser("write")
    write.add_argument("package_root", type=Path)
    write.add_argument("--hook-philosophy", required=True)
    write.add_argument("--narrator-personality", action="append", required=True, dest="narrator_personality")
    write.add_argument("--sentence-length-qualitative", required=True)
    write.add_argument("--sentence-length-target-words", type=int, default=None)
    write.add_argument("--words-per-second-target", type=float, default=None)
    write.add_argument("--words-per-second-range", type=float, nargs=2, default=None)
    write.add_argument("--technical-depth", required=True)
    write.add_argument("--humor-level", required=True)
    write.add_argument("--information-density", required=True)
    write.add_argument("--question-usage", required=True)
    write.add_argument("--number-usage", required=True)
    write.add_argument("--story-structure", required=True)
    write.add_argument("--ending-behavior", required=True)
    write.add_argument("--cta-philosophy", required=True)
    write.add_argument("--preferred-cliche", action="append", default=[], dest="preferred_cliches")
    write.add_argument("--forbidden-cliche", action="append", default=[], dest="forbidden_cliches")
    write.add_argument("--fact-verification-requirements", required=True)
    write.add_argument("--unresolved-variable", action="append", default=[], dest="unresolved_variables")
    write.add_argument("--force", action="store_true", help="Overwrite an existing draft (clears frozen status and decision_refs).")

    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("package_root", type=Path)
    freeze.add_argument("--decision-ref", required=True)
    freeze.add_argument("--yes", action="store_true")
    freeze.add_argument("--force", action="store_true", help="Re-freeze already-frozen Script DNA.")
    freeze.add_argument("--audition-example", default=None, help="Approved example id heard as audio before freezing.")
    freeze.add_argument("--audition-timing", default=None, help="Voiceover timing JSON for the auditioned example.")

    add_example = subparsers.add_parser("add-example")
    add_example.add_argument("package_root", type=Path)
    add_example.add_argument("--text", required=True)
    add_example.add_argument("--tag", action="append", default=[], dest="tags")
    add_example.add_argument("--provenance-kind", required=True, choices=["human_authored", "model_drafted", "adapted_from_evidence"])
    add_example.add_argument("--created-by", required=True)
    add_example.add_argument("--source-ref", required=True)
    add_example.add_argument("--model")
    add_example.add_argument("--model-version")
    add_example.add_argument("--prompt-ref")

    review_example = subparsers.add_parser("review-example")
    review_example.add_argument("package_root", type=Path)
    review_example.add_argument("example_id")
    review_example.add_argument("--decision", required=True, choices=["approved", "rejected", "borderline"])
    review_example.add_argument("--reviewer", required=True)
    review_example.add_argument("--reason", required=True)
    review_example.add_argument("--created-at")
    review_example.add_argument("--yes", action="store_true")

    list_examples = subparsers.add_parser("list-examples")
    list_examples.add_argument("package_root", type=Path)
    list_examples.add_argument("--classification", choices=["experimental", "approved", "rejected", "borderline"])

    validate = subparsers.add_parser("validate")
    validate.add_argument("package_root", type=Path)

    return parser.parse_args()


def _channel_id(root: Path, package_root: Path) -> str:
    resolved = package_root.resolve() if package_root.is_absolute() else (root.resolve() / package_root)
    identity = yaml.safe_load((resolved / "channel.yaml").read_text(encoding="utf-8"))
    return identity["id"]


def main() -> int:
    args = parse_args()
    try:
        if args.command == "write":
            path = write_script_dna(
                args.package_root, args.root, hook_philosophy=args.hook_philosophy,
                narrator_personality=args.narrator_personality,
                sentence_length_qualitative=args.sentence_length_qualitative,
                sentence_length_target_words=args.sentence_length_target_words,
                words_per_second_target=args.words_per_second_target,
                words_per_second_range=list(args.words_per_second_range) if args.words_per_second_range else None,
                technical_depth=args.technical_depth, humor_level=args.humor_level,
                information_density=args.information_density, question_usage=args.question_usage,
                number_usage=args.number_usage, story_structure=args.story_structure,
                ending_behavior=args.ending_behavior, cta_philosophy=args.cta_philosophy,
                preferred_cliches=args.preferred_cliches, forbidden_cliches=args.forbidden_cliches,
                fact_verification_requirements=args.fact_verification_requirements,
                unresolved_variables=args.unresolved_variables, force=args.force,
            )
            print(path.relative_to(args.root.resolve()).as_posix())
        elif args.command == "freeze":
            _confirm(f"Freeze Script DNA for {args.package_root}? Type yes: ", assume_yes=args.yes)
            path = freeze_script_dna(
                args.package_root, args.root, human_confirmed=True, decision_ref=args.decision_ref,
                force=args.force, audition_example_id=args.audition_example,
                audition_timing_ref=args.audition_timing,
            )
            print(path.relative_to(args.root.resolve()).as_posix())
        elif args.command == "add-example":
            store = ScriptExampleStore(args.root, _channel_id(args.root, args.package_root))
            result = store.add(
                args.text, tags=args.tags, provenance_kind=args.provenance_kind, created_by=args.created_by,
                source_ref=args.source_ref, model=args.model, model_version=args.model_version, prompt_ref=args.prompt_ref,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.command == "review-example":
            _confirm(f"Record human {args.decision} decision for {args.example_id}? Type yes: ", assume_yes=args.yes)
            store = ScriptExampleStore(args.root, _channel_id(args.root, args.package_root))
            result = store.review(
                args.example_id, decision=args.decision, reviewer=args.reviewer, reason=args.reason,
                created_at=args.created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                human_confirmed=True,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.command == "list-examples":
            store = ScriptExampleStore(args.root, _channel_id(args.root, args.package_root))
            print(json.dumps(store.list(classification=args.classification), indent=2, sort_keys=True))
        else:
            resolved = args.package_root.resolve() if args.package_root.is_absolute() else args.root.resolve() / args.package_root
            document = yaml.safe_load((resolved / "script" / "script-dna.yaml").read_text(encoding="utf-8"))
            validate_script_dna(document)
            print("SCRIPT DNA VALID")
    except ScriptValidationError as exc:
        print(f"SCRIPT DNA ERROR\n{exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
