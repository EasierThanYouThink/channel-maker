#!/usr/bin/env python3
"""Channel control-panel overview: one JSON snapshot for the dashboard + skill.

Creator-dashboard sections (decided for Stage 1.5):
  header, workflow progress, next action, review queue (this channel),
  style snapshot, pilots/episodes, services health, recent events, wiki shortcuts.

Read-only. Never writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.dashboard.views import channel_overview  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("channel_id")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        print(json.dumps(channel_overview(args.root.resolve(), args.channel_id), indent=2, sort_keys=True))
    except Exception as exc:  # noqa: BLE001 — CLI surfaces engine errors plainly
        print(f"CHANNEL OVERVIEW ERROR\n- {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
