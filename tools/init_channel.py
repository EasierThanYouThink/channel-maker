"""Scaffold a minimal, immediately-valid new Channel Package at CHANNEL_INIT."""

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

from engine.channel import ChannelValidationError, validate_channel_package  # noqa: E402
from engine.memory import initialize_channel_wiki  # noqa: E402
from engine.memory.wiki_pages import KnowledgeError  # noqa: E402


class InitChannelError(RuntimeError):
    """A new Channel Package could not be scaffolded."""


def init_channel(
    root: Path,
    channel_id: str,
    *,
    name: str,
    niche_primary: str,
    topic_family: str | None,
    archetype: str,
    language: str,
    formats: list[str],
    renderer: str,
) -> Path:
    # v1 is CREATE-only: every channel is ORIGINAL. Clone mode (EXISTING_CHANNEL)
    # was cut for v1 and returns in v2 — see the skill's Stage 1.
    creation_mode = "ORIGINAL"
    root = root.resolve()
    package = root / "channels" / channel_id
    if package.exists():
        raise InitChannelError(
            f"channel package already exists: {package} "
            "(do not create files under channels/<id>/ before scaffolding; "
            "write the channel thesis only after init_channel succeeds)"
        )

    niche: dict[str, str] = {"primary": niche_primary}
    if topic_family:
        niche["topic_family"] = topic_family

    identity = {
        "schema_version": "0.1.0",
        "id": channel_id,
        "name": name,
        "version": "0.1.0",
        "status": "DRAFT",
        "language": language,
        "niche": niche,
        "platform": {"primary": "YOUTUBE", "formats": formats},
        "production": {"archetype": archetype, "renderer": renderer},
        "creation": {"mode": creation_mode},
        "canonical_sources": {"channel_state": f"channels/{channel_id}/CHANNEL_STATE.json"},
    }
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state = {
        "schema_version": "0.2.0",
        "channel_id": channel_id,
        "revision": 0,
        "state": "CHANNEL_INIT",
        "status": "ACTIVE",
        "completed": [],
        "active_experiment": None,
        "waiting_for": None,
        "blocker": None,
        "next_action": "Begin CM1 NICHE_INTELLIGENCE for this channel.",
        "resume_state": None,
        "source_refs": [f"channels/{channel_id}/channel.yaml"],
        "known_gaps": [],
        "legacy_mapping": False,
        "events": [],
        "updated_at": now,
    }

    package.mkdir(parents=True)
    try:
        (package / "channel.yaml").write_text(yaml.safe_dump(identity, sort_keys=False), encoding="utf-8")
        (package / "CHANNEL_STATE.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        validate_channel_package(package, root)
        initialize_channel_wiki(package, root, created_at=now)
    except Exception:
        import shutil

        shutil.rmtree(package, ignore_errors=True)
        raise
    return package


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel_id")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--name", required=True)
    parser.add_argument("--niche-primary", required=True)
    parser.add_argument("--topic-family", default=None)
    parser.add_argument("--archetype", required=True, choices=["ILLUSTRATED_EXPLAINER", "DATA_STORY", "MAP_STORY"])
    parser.add_argument("--language", default="en")
    parser.add_argument("--formats", action="append", default=[], choices=["SHORTS", "LONG_FORM"])
    parser.add_argument("--renderer", required=True, help="Name of the rendering pipeline this channel's pilots will use, e.g. 'remotion'. See docs/RENDER_CONTRACT.md.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        package = init_channel(
            args.root, args.channel_id, name=args.name, niche_primary=args.niche_primary,
            topic_family=args.topic_family, archetype=args.archetype, language=args.language,
            formats=args.formats or ["SHORTS"], renderer=args.renderer,
        )
    except (InitChannelError, ChannelValidationError, KnowledgeError) as exc:
        print(f"INIT CHANNEL ERROR\n{exc}")
        return 2
    print(f"CHANNEL PACKAGE CREATED {package}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
