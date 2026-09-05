"""Plan, produce, and review one channel Episode (ongoing content, after CHANNEL_READY)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.episode import (  # noqa: E402
    EpisodeValidationError,
    episode_path,
    plan_episode,
    record_production,
    record_review,
    validate_episode,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan")
    plan.add_argument("package_root", type=Path)
    plan.add_argument("episode_id")
    plan.add_argument("--topic", required=True)
    plan.add_argument("--target-duration-seconds", type=float, required=True)
    plan.add_argument("--opportunity-ref", default=None)

    production = subparsers.add_parser("record-production")
    production.add_argument("package_root", type=Path)
    production.add_argument("episode_id")
    production.add_argument("--script-ref", default=None)
    production.add_argument("--voiceover-ref", default=None)
    production.add_argument("--scene-candidate-manifest", action="append", default=[], dest="scene_candidate_manifest_paths")
    production.add_argument("--evaluation-result", action="append", default=[], dest="evaluation_result_paths")
    production.add_argument("--render-ref", default=None)
    production.add_argument("--production-log-ref", default=None)

    review = subparsers.add_parser("record-review")
    review.add_argument("package_root", type=Path)
    review.add_argument("episode_id")
    review.add_argument("--decision", required=True, choices=["GO", "REVISE", "ABANDON"])
    review.add_argument("--decided-by", required=True)
    review.add_argument("--rationale", required=True)
    review.add_argument("--decision-ref", required=True)
    review.add_argument("--decided-at", default=None)

    validate = subparsers.add_parser("validate")
    validate.add_argument("package_root", type=Path)
    validate.add_argument("episode_id")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "plan":
            path = plan_episode(
                args.package_root, args.root, episode_id=args.episode_id, topic=args.topic,
                target_duration_seconds=args.target_duration_seconds, opportunity_ref=args.opportunity_ref,
            )
        elif args.command == "record-production":
            path = record_production(
                args.package_root, args.root, args.episode_id, script_ref=args.script_ref,
                voiceover_ref=args.voiceover_ref, scene_candidate_manifest_paths=args.scene_candidate_manifest_paths,
                evaluation_result_paths=args.evaluation_result_paths, render_ref=args.render_ref,
                production_log_ref=args.production_log_ref,
            )
        elif args.command == "record-review":
            path = record_review(
                args.package_root, args.root, args.episode_id, decision=args.decision, decided_by=args.decided_by,
                rationale=args.rationale, decision_ref=args.decision_ref, decided_at=args.decided_at,
            )
        else:
            resolved = args.package_root.resolve() if args.package_root.is_absolute() else args.root.resolve() / args.package_root
            document = json.loads(episode_path(resolved, args.episode_id).read_text(encoding="utf-8"))
            validate_episode(document, repository_root=args.root)
            print("EPISODE VALID")
            return 0
    except EpisodeValidationError as exc:
        print(f"EPISODE ERROR\n{exc}")
        return 2
    print(path.relative_to(args.root.resolve()).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
