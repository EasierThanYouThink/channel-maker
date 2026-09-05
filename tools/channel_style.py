#!/usr/bin/env python3
"""Obsidian style-learning loop: snapshot frozen channel style into the wiki.

The channel wiki (`channels/<id>/wiki/`) is a plain-Markdown Obsidian vault.
This tool rebuilds the derived `wiki/style/` pages from the frozen sources of
truth (foundation, Script/Visual/Motion DNA, identity) plus accumulated
`lessons/` + `failures/` notes — the AI learns the channel style and writes it
where both humans (Obsidian graph) and agents (memory search) can read it.

Sources of truth stay in their YAML/JSON artifacts; style pages are
`ai_proposed` derivatives with `provenance` pointing back. Never hand-edit a
style page to change the channel — change the DNA artifact, freeze it, re-sync.

Usage:
  python tools/channel_style.py status channels/<id>
  python tools/channel_style.py sync channels/<id> [--force]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.channel import ChannelValidationError, validate_channel_package  # noqa: E402
from engine.memory.wiki_pages import KnowledgeError, parse_wiki_page  # noqa: E402

STYLE_PAGES = ("index", "voice", "visual", "motion")
KINDS = {"index": "index", "voice": "storytelling", "visual": "visual", "motion": "motion"}


def _load_yaml(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    return value if isinstance(value, dict) else None


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _approved_count(records_dir: Path, key: str = "classification", want: str = "approved") -> tuple[int, int]:
    if not records_dir.is_dir():
        return (0, 0)
    total = approved = 0
    for path in sorted(records_dir.glob("*.json")):
        doc = _load_json(path)
        if doc is None:
            continue
        total += 1
        if doc.get(key) == want:
            approved += 1
    return (approved, total)


def _wiki_notes(package: Path, subdir: str) -> list[str]:
    directory = package / "wiki" / subdir
    if not directory.is_dir():
        return []
    return sorted(p.relative_to(package).as_posix() for p in directory.glob("*.md"))


def _provenance(package: Path, root: Path, candidates: list[str]) -> list[dict[str, str]]:
    refs = [{"kind": "repository", "ref": candidate} for candidate in candidates if (root / candidate).is_file()]
    # Fallback: channel.yaml always exists for a valid package.
    if not refs:
        refs.append({"kind": "repository", "ref": f"channels/{package.name}/channel.yaml"})
    return refs


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def collect(package: Path, root: Path) -> dict[str, Any]:
    """Gather style facts from frozen artifacts + wiki notes (no writes)."""
    try:
        validated = validate_channel_package(package.resolve(), root.resolve())
    except ChannelValidationError as exc:
        raise KnowledgeError(str(exc)) from exc
    channel_id = validated.identity["id"]
    foundation = _load_yaml(package / "strategy" / "foundation.yaml")
    script = _load_yaml(package / "script" / "script-dna.yaml")
    visual = _load_yaml(package / "design" / "visual-dna-seed.yaml")
    motion = _load_yaml(package / "motion" / "motion-dna-seed.yaml")
    identity = _load_yaml(package / "identity" / "channel-identity.yaml")
    approved_examples, total_examples = _approved_count(package / "script" / "examples" / "records")
    approved_exemplars, total_exemplars = _approved_count(package / "design" / "exemplars" / "records")
    approved_candidates, total_candidates = _approved_count(package / "identity" / "candidates" / "records")
    return {
        "channel_id": channel_id,
        "name": validated.identity["name"],
        "state": validated.state["state"],
        "foundation": foundation,
        "script": script,
        "visual": visual,
        "motion": motion,
        "identity": identity,
        "approved_examples": approved_examples,
        "total_examples": total_examples,
        "approved_exemplars": approved_exemplars,
        "total_exemplars": total_exemplars,
        "approved_candidates": approved_candidates,
        "total_candidates": total_candidates,
        "lessons": _wiki_notes(package, "lessons"),
        "failures": _wiki_notes(package, "failures"),
    }


def _summarize_dna(doc: dict[str, Any] | None, *, frozen_key: str = "status") -> str:
    if doc is None:
        return "_Not yet drafted._"
    status = doc.get(frozen_key, doc.get("authority_status", "unknown"))
    return f"status `{status}`"


def render_facts_to_pages(facts: dict[str, Any], root: Path) -> dict[str, tuple[dict[str, Any], str]]:
    """Return {page_name: (metadata, body)} for the four style pages."""
    channel_id = facts["channel_id"]
    now = _timestamp()
    script = facts["script"] or {}
    visual = facts["visual"] or {}
    motion_doc = facts["motion"] or {}
    foundation = facts["foundation"] or {}
    identity = facts["identity"] or {}
    lessons = "\n".join(f"- [[{ref}]]" for ref in facts["lessons"]) or "_No lessons yet._"
    failures = "\n".join(f"- [[{ref}]]" for ref in facts["failures"]) or "_No failures recorded._"

    def meta(name: str, title: str, tags: list[str], related: list[str], provenance: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "schema_version": "0.3.0",
            "knowledge_id": f"wiki:channel/{channel_id}/style-{name}",
            "title": title,
            "kind": KINDS[name],
            "status": "active",
            "authority": "ai_proposed",
            "scope": "CHANNEL",
            "channel_id": channel_id,
            "video_id": None,
            "tags": tags,
            "confidence": None,
            "created_at": now,
            "updated_at": now,
            "related": related,
            "provenance": provenance,
        }

    base = f"channels/{channel_id}"
    index_body = (
        f"# {facts['name']} — Style Index\n\n"
        f"Channel state `{facts['state']}`. This index links the learned style wildly simply: "
        f"voice, look, and movement. Sources of truth are the frozen DNA artifacts; "
        f"these pages are derived (`ai_proposed`) and re-synced with "
        f"`python tools/channel_style.py sync {base}`.\n\n"
        f"- [[{base}/wiki/style/voice|Voice]] — how the channel sounds "
        f"({_summarize_dna(facts['script'])}; {facts['approved_examples']}/{facts['total_examples']} approved examples)\n"
        f"- [[{base}/wiki/style/visual|Visual]] — how the channel looks "
        f"({_summarize_dna(facts['visual'])}; {facts['approved_exemplars']}/{facts['total_exemplars']} approved exemplars)\n"
        f"- [[{base}/wiki/style/motion|Motion]] — how the channel moves "
        f"({_summarize_dna(facts['motion'])}; identity candidates {facts['approved_candidates']}/{facts['total_candidates']} approved)\n\n"
        f"## Lessons feeding the style\n\n{lessons}\n\n## Failures (what the style avoids)\n\n{failures}\n"
    )
    sentence_length = script.get("sentence_length", {}) or {}
    words_per_second = script.get("words_per_second", {}) or {}
    audition = script.get("audition") or {}
    voice_body = (
        f"# {facts['name']} — Voice\n\n"
        f"Script DNA {_summarize_dna(facts['script'])} "
        f"(`{base}/script/script-dna.yaml`).\n\n"
        f"- Hook: {script.get('hook_philosophy', '_—_')}\n"
        f"- Narrator: {', '.join(script.get('narrator_personality', [])) or '_—_'}\n"
        f"- Sentence: {sentence_length.get('qualitative', '_—_')} "
        f"(~{sentence_length.get('target_words', '—')} words @ {words_per_second.get('target', '—')} wps)\n"
        f"- Audition: {audition.get('example_id', '_no recorded audition_')} "
        f"({audition.get('timing_ref', 'no timing evidence')})\n"
        f"- Depth / humor / density: {script.get('technical_depth', '—')} / "
        f"{script.get('humor_level', '—')} / {script.get('information_density', '—')}\n"
        f"- Story: {script.get('story_structure', '_—_')} → {script.get('ending_behavior', '_—_')}\n"
        f"- CTA: {script.get('cta_philosophy', '_—_')}\n"
        f"- Forbidden cliches: {', '.join(script.get('forbidden_cliches', [])) or '—'}\n"
        f"- Verification: {script.get('fact_verification_requirements', '_—_')}\n\n"
        f"Promise (foundation): {foundation.get('promise', '_—_')}\n\n"
        f"See also: [[{base}/wiki/style/index|Style index]], "
        f"[[{base}/wiki/style/visual|Visual]], [[{base}/wiki/style/motion|Motion]].\n"
    )
    visual_body = (
        f"# {facts['name']} — Visual\n\n"
        f"Visual DNA {_summarize_dna(facts['visual'])} "
        f"(`{base}/design/visual-dna-seed.yaml`); "
        f"identity {_summarize_dna(identity)}.\n\n"
        + "".join(
            f"- `{domain}`: {info.get('authority_status', info.get('discovery_status', '—'))}\n"
            if isinstance(info, dict) else ""
            for domain, info in (visual.get("domains", {}) or {}).items()
        )
        + f"\nApproved exemplars: {facts['approved_exemplars']}/{facts['total_exemplars']}.\n\n"
        f"See also: [[{base}/wiki/style/index|Style index]], "
        f"[[{base}/wiki/style/voice|Voice]], [[{base}/wiki/style/motion|Motion]].\n"
    )
    motion_body = (
        f"# {facts['name']} — Motion\n\n"
        f"Motion DNA {_summarize_dna(facts['motion'])} "
        f"(`{base}/motion/motion-dna-seed.yaml`).\n\n"
        + "".join(
            f"- `{domain}`: {info.get('authority_status', info.get('discovery_status', '—'))}\n"
            if isinstance(info, dict) else ""
            for domain, info in (motion_doc.get("domains", {}) or {}).items()
        )
        + f"\n## What episodes taught the movement\n\n{lessons}\n\n"
        f"See also: [[{base}/wiki/style/index|Style index]], "
        f"[[{base}/wiki/style/voice|Voice]], [[{base}/wiki/style/visual|Visual]].\n"
    )
    related_base = [f"wiki:channel/{channel_id}/home"]
    prov = {
        "index": _provenance(package=Path(base), root=root, candidates=[
            f"{base}/channel.yaml",
        ]),
        "voice": _provenance(package=Path(base), root=root, candidates=[
            f"{base}/script/script-dna.yaml", f"{base}/strategy/foundation.yaml",
        ]),
        "visual": _provenance(package=Path(base), root=root, candidates=[
            f"{base}/design/visual-dna-seed.yaml", f"{base}/identity/channel-identity.yaml",
        ]),
        "motion": _provenance(package=Path(base), root=root, candidates=[
            f"{base}/motion/motion-dna-seed.yaml",
        ]),
    }
    return {
        "index": (meta("index", f"{facts['name']} Style Index", ["channel", "style", "index"], related_base, prov["index"]), index_body),
        "voice": (meta("voice", f"{facts['name']} Voice", ["channel", "style", "voice"], related_base, prov["voice"]), voice_body),
        "visual": (meta("visual", f"{facts['name']} Visual Style", ["channel", "style", "visual"], related_base, prov["visual"]), visual_body),
        "motion": (meta("motion", f"{facts['name']} Motion Style", ["channel", "style", "motion"], related_base, prov["motion"]), motion_body),
    }


def sync(package: Path, root: Path, *, force: bool = False) -> dict[str, str]:
    """Write missing style pages (or all with --force). Returns {page: outcome}."""
    from engine.channel._portable import write_bytes_atomic
    from engine.memory.wiki_pages import validate_metadata

    facts = collect(package, root)
    pages = render_facts_to_pages(facts, root)
    contract = root / "engine" / "memory" / "contracts" / "wiki-page.schema.json"
    outcomes: dict[str, str] = {}
    style_dir = package / "wiki" / "style"
    style_dir.mkdir(parents=True, exist_ok=True)
    for name, (metadata, body) in pages.items():
        target = style_dir / f"{name}.md"
        validate_metadata(metadata, contract, f"style page {name}")
        if target.is_file() and not force:
            # Validate existing page still parses; report skip.
            try:
                parse_wiki_page(target, contract)
                outcomes[name] = "exists (use --force to refresh)"
            except KnowledgeError as exc:
                outcomes[name] = f"exists but INVALID: {exc}"
            continue
        if target.is_file():
            try:
                existing = parse_wiki_page(target, contract)
                metadata = {**metadata, "created_at": existing.metadata["created_at"]}
            except KnowledgeError:
                pass
        import yaml as _yaml

        frontmatter = _yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip()
        write_bytes_atomic(target, f"---\n{frontmatter}\n---\n\n{body.strip()}\n".encode("utf-8"))
        outcomes[name] = "wrote" if not force else "refreshed"
    # Rebuild the disposable index so search sees the new pages immediately.
    from engine.memory import ChannelMemoryRepository

    ChannelMemoryRepository(root).rebuild_index()
    return outcomes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status")
    status.add_argument("package", type=Path)
    sync_p = sub.add_parser("sync")
    sync_p.add_argument("package", type=Path)
    sync_p.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    package = args.package if args.package.is_absolute() else root / args.package
    try:
        if args.command == "status":
            facts = collect(package, root)
            style_dir = package / "wiki" / "style"
            print(json.dumps({
                "channel_id": facts["channel_id"],
                "state": facts["state"],
                "pages": {name: (style_dir / f"{name}.md").is_file() for name in STYLE_PAGES},
                "approved_examples": f"{facts['approved_examples']}/{facts['total_examples']}",
                "approved_exemplars": f"{facts['approved_exemplars']}/{facts['total_exemplars']}",
                "lessons": len(facts["lessons"]),
                "failures": len(facts["failures"]),
            }, indent=2, sort_keys=True))
        else:
            print(json.dumps(sync(package, root, force=args.force), indent=2, sort_keys=True))
    except (KnowledgeError, ChannelValidationError) as exc:
        print(f"CHANNEL STYLE ERROR\n- {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
