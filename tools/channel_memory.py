#!/usr/bin/env python3
"""Initialize, validate, retrieve, and write scoped Channel Maker memory."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.memory import ChannelMemoryRepository, initialize_channel_wiki  # noqa: E402
from engine.memory.wiki_pages import KnowledgeError  # noqa: E402


def _scope_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--channel")
    parser.add_argument("--video")
    parser.add_argument("--include-engine", action="store_true")
    parser.add_argument("--kind", action="append")
    parser.add_argument("--authority", action="append")
    parser.add_argument("--tag", action="append")
    parser.add_argument("--limit", type=int, default=10)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)

    initialize = commands.add_parser("init")
    initialize.add_argument("package", type=Path)
    initialize.add_argument("--created-at")

    commands.add_parser("rebuild")
    commands.add_parser("validate")

    search = commands.add_parser("search")
    search.add_argument("query")
    _scope_filters(search)

    context = commands.add_parser("context")
    context.add_argument("package", type=Path)
    context.add_argument("query")
    context.add_argument("--video")
    context.add_argument("--include-engine", action="store_true")
    context.add_argument("--limit", type=int, default=8)
    context.add_argument("--max-body-chars", type=int, default=2400)

    write = commands.add_parser("write")
    write.add_argument("relative_path")
    write.add_argument("--metadata-json", type=Path, required=True)
    write.add_argument("--body-file", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    repository = ChannelMemoryRepository(root)
    try:
        if args.command == "init":
            package = args.package if args.package.is_absolute() else root / args.package
            value = {"home": initialize_channel_wiki(package, root, created_at=args.created_at).relative_to(root).as_posix()}
        elif args.command == "rebuild":
            index = repository.rebuild_index()
            value = {
                "index": repository.index_path.relative_to(root).as_posix(),
                "canonical_fingerprint": index["canonical_fingerprint"],
                "document_count": len(index["documents"]),
            }
        elif args.command == "validate":
            documents = repository.documents()
            value = {
                "document_count": len(documents),
                "canonical_fingerprint": repository.canonical_fingerprint(documents),
            }
        elif args.command == "search":
            value = [
                asdict(result)
                for result in repository.search(
                    args.query,
                    channel_id=args.channel,
                    video_id=args.video,
                    include_engine=args.include_engine,
                    kinds=set(args.kind) if args.kind else None,
                    authorities=set(args.authority) if args.authority else None,
                    tags=set(args.tag) if args.tag else None,
                    limit=args.limit,
                )
            ]
        elif args.command == "context":
            package = args.package if args.package.is_absolute() else root / args.package
            value = repository.build_context_bundle(
                package,
                args.query,
                video_id=args.video,
                include_engine=args.include_engine,
                limit=args.limit,
                max_body_chars=args.max_body_chars,
            )
        else:
            try:
                metadata = json.loads(args.metadata_json.read_text(encoding="utf-8"))
                body = args.body_file.read_text(encoding="utf-8")
            except (OSError, json.JSONDecodeError) as exc:
                raise KnowledgeError(f"cannot load write-back input: {exc}") from exc
            if not isinstance(metadata, dict):
                raise KnowledgeError("write-back metadata JSON must be an object")
            target = repository.write_page(args.relative_path, metadata, body)
            value = {"path": target.relative_to(root).as_posix(), "knowledge_id": metadata["knowledge_id"]}
        print(json.dumps(value, indent=2, sort_keys=True))
    except (KnowledgeError, KeyError) as exc:
        print(f"CHANNEL MEMORY ERROR\n- {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
