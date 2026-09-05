"""Scaffold a new, immediately-valid, evidence-empty CM3 Niche Intelligence study."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.niche_intelligence import NicheValidationError, init_study  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--study-id", required=True)
    parser.add_argument("--niche", required=True)
    parser.add_argument("--sub-niche", action="append", default=[], dest="sub_niches")
    parser.add_argument("--archetype", required=True, choices=["ILLUSTRATED_EXPLAINER", "DATA_STORY", "MAP_STORY"])
    parser.add_argument("--format", required=True, choices=["SHORTS", "LONG_FORM", "MIXED"], dest="fmt")
    parser.add_argument("--language", default="en")
    parser.add_argument("--geography", default=None)
    parser.add_argument(
        "--channel-role", action="append", required=True, dest="channel_roles",
        choices=["ESTABLISHED_LEADER", "GROWTH_CANDIDATE", "SMALL_BREAKOUT", "BASELINE_COMPARATOR", "OTHER", "UNKNOWN"],
    )
    parser.add_argument(
        "--video-role", action="append", required=True, dest="video_roles",
        choices=["BREAKOUT", "CHANNEL_BASELINE", "RECENT_NORMAL", "UNDERPERFORMER", "OUTLIER", "OTHER", "UNKNOWN"],
    )
    parser.add_argument("--window-from", required=True)
    parser.add_argument("--window-to", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validated = init_study(
            args.package_root, args.root, study_id=args.study_id, niche=args.niche,
            sub_niches=args.sub_niches, archetype=args.archetype, fmt=args.fmt,
            language=args.language, geography=args.geography,
            channel_roles=args.channel_roles, video_roles=args.video_roles,
            window_from=args.window_from, window_to=args.window_to,
        )
    except NicheValidationError as exc:
        print(f"NICHE INTELLIGENCE ERROR\n{exc}")
        return 2
    print(json.dumps({"study_root": str(validated.root), "artifact_count": len(validated.artifacts)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
