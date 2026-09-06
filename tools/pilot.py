"""Plan, produce, review, and freeze one channel Pilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from _confirmation import require_confirmation  # noqa: E402

from engine.pilot import (  # noqa: E402
    PilotValidationError,
    freeze_pilot,
    pilot_path,
    plan_pilot,
    record_production,
    record_review,
    validate_pilot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan")
    plan.add_argument("package_root", type=Path)
    plan.add_argument("pilot_id")
    plan.add_argument("--topic", required=True)
    plan.add_argument("--target-duration-seconds", type=float, required=True)
    plan.add_argument("--integration-goal", action="append", required=True, dest="integration_goals")
    plan.add_argument("--no-reusable-components", action="store_true", help="Declare honestly that this pilot needs no reusable component (scene-local construction).")

    production = subparsers.add_parser("record-production")
    production.add_argument("package_root", type=Path)
    production.add_argument("pilot_id")
    production.add_argument("--script-ref", default=None)
    production.add_argument("--voiceover-ref", default=None)
    production.add_argument("--voice", default=None, help="Narration voice identity (required with --voiceover-ref; one voice per channel).")
    production.add_argument("--scene-candidate-manifest", action="append", default=[], dest="scene_candidate_manifest_paths")
    production.add_argument("--evaluation-result", action="append", default=[], dest="evaluation_result_paths")
    production.add_argument("--render-ref", default=None)
    production.add_argument("--production-log-ref", default=None)

    review = subparsers.add_parser("record-review")
    review.add_argument("package_root", type=Path)
    review.add_argument("pilot_id")
    review.add_argument("--decision", required=True, choices=["GO", "REVISE", "ABANDON_DIRECTION"])
    review.add_argument("--decided-by", required=True)
    review.add_argument("--rationale", required=True)
    review.add_argument("--decision-ref", required=True)
    review.add_argument("--revise-target", default=None)
    review.add_argument("--decided-at", default=None)
    review.add_argument("--strict-media", action="store_true", help="Decode-probe the render via ffprobe (dimensions, duration, narrated audio); refuses when ffprobe is missing.")
    review.add_argument("--yes", action="store_true")

    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("package_root", type=Path)
    freeze.add_argument("pilot_id")
    freeze.add_argument("--new-channel-version", required=True)
    freeze.add_argument("--frozen-by", required=True)
    freeze.add_argument("--yes", action="store_true")
    freeze.add_argument("--force", action="store_true", help="Re-freeze an already-frozen pilot (bumps the channel version again).")

    validate = subparsers.add_parser("validate")
    validate.add_argument("package_root", type=Path)
    validate.add_argument("pilot_id")

    return parser.parse_args()


def _require_human_confirm(args: argparse.Namespace, what: str) -> None:
    require_confirmation(
        assume_yes=args.yes,
        prompt=f"Record human pilot {what}? Type yes: ",
        error_type=PilotValidationError,
        noninteractive_message=(
            f"pilot {what} requires --yes (non-interactive) or an interactive human terminal"
        ),
        cancelled_message=f"human pilot {what} cancelled",
    )


def main() -> int:
    args = parse_args()
    try:
        if args.command == "plan":
            path = plan_pilot(
                args.package_root, args.root, pilot_id=args.pilot_id, topic=args.topic,
                target_duration_seconds=args.target_duration_seconds, integration_goals=args.integration_goals,
                no_reusable_components=args.no_reusable_components,
            )
        elif args.command == "record-production":
            path = record_production(
                args.package_root, args.root, args.pilot_id, script_ref=args.script_ref,
                voiceover_ref=args.voiceover_ref, voice=args.voice,
                scene_candidate_manifest_paths=args.scene_candidate_manifest_paths,
                evaluation_result_paths=args.evaluation_result_paths, render_ref=args.render_ref,
                production_log_ref=args.production_log_ref,
            )
        elif args.command == "record-review":
            _require_human_confirm(args, f"{args.decision} review for {args.pilot_id}")
            path = record_review(
                args.package_root, args.root, args.pilot_id, decision=args.decision, decided_by=args.decided_by,
                rationale=args.rationale, decision_ref=args.decision_ref, revise_target=args.revise_target,
                decided_at=args.decided_at, strict_media=args.strict_media,
            )
        elif args.command == "freeze":
            _require_human_confirm(args, f"freeze for {args.pilot_id}")
            path = freeze_pilot(
                args.package_root, args.root, args.pilot_id,
                new_channel_version=args.new_channel_version, frozen_by=args.frozen_by, force=args.force,
            )
        else:
            resolved = args.package_root.resolve() if args.package_root.is_absolute() else args.root.resolve() / args.package_root
            document = json.loads(pilot_path(resolved, args.pilot_id).read_text(encoding="utf-8"))
            validate_pilot(document, repository_root=args.root)
            print("PILOT VALID")
            return 0
    except PilotValidationError as exc:
        print(f"PILOT ERROR\n{exc}")
        return 2
    print(path.relative_to(args.root.resolve()).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
