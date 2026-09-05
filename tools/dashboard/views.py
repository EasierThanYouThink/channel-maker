"""Pure, read-only view-model builders for the dashboard. Never writes anything."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from engine.channel import ChannelStateError, ChannelStateMachine, ChannelValidationError, validate_channel_package
from engine.memory import ChannelMemoryRepository


def list_channels(root: Path) -> list[dict[str, Any]]:
    channels_root = root / "channels"
    if not channels_root.is_dir():
        return []
    results = []
    for package_root in sorted(p for p in channels_root.iterdir() if p.is_dir()):
        try:
            package = validate_channel_package(package_root, root)
        except ChannelValidationError as exc:
            results.append({"channel_id": package_root.name, "error": str(exc)})
            continue
        results.append({
            "channel_id": package.identity["id"], "name": package.identity["name"],
            "state": package.state["state"], "status": package.state["status"],
            "waiting_for": package.state["waiting_for"], "next_action": package.state["next_action"],
            "legacy_mapping": package.state.get("legacy_mapping", False),
        })
    return results


def channel_detail(root: Path, channel_id: str) -> dict[str, Any]:
    package_root = root / "channels" / channel_id
    machine = ChannelStateMachine(package_root, root)
    package = machine.load(lenient=True)
    try:
        next_action = asdict(machine.next_allowed_action())
    except ChannelStateError as exc:
        next_action = {"error": str(exc)}
    return {
        "identity": package.identity, "state": package.state, "next_allowed_action": next_action,
        "recent_events": package.state["events"][-10:],
        "reference_warnings": machine.reference_warnings(),
    }


def wiki_pages(root: Path, channel_id: str) -> list[dict[str, Any]]:
    repository = ChannelMemoryRepository(root)
    return [
        {"knowledge_id": doc.knowledge_id, "title": doc.title, "kind": doc.kind, "authority": doc.authority,
          "path": doc.path, "body": doc.body}
        for doc in repository.documents()
        if doc.scope == "CHANNEL" and doc.channel_id == channel_id
    ]


def vault_snapshot(root: Path, channel_id: str, *, limit: int = 6) -> dict[str, Any]:
    """Obsidian-vault snapshot for the control panel: vault path, deep link,
    style presence, and the most recently updated wiki notes with excerpts."""
    from urllib.parse import quote

    package_root = root / "channels" / channel_id
    wiki = package_root / "wiki"
    pages: list[dict[str, Any]] = []
    if wiki.is_dir():
        candidates = sorted(
            (p for p in wiki.rglob("*.md") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]
        for path in candidates:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            lines = text.splitlines()
            title = path.stem.replace("-", " ").replace("_", " ")
            if lines and lines[0].strip() == "---":
                try:
                    end = lines.index("---", 1)
                    for line in lines[1:end]:
                        if line.startswith("title:"):
                            title = line.split(":", 1)[1].strip().strip("'\"") or title
                            break
                    body = " ".join(" ".join(lines[end + 1:]).split())
                except ValueError:
                    body = " ".join(" ".join(lines).split())
            else:
                body = " ".join(" ".join(lines).split())
            rel = path.relative_to(package_root).as_posix()
            pages.append({
                "title": title,
                "path": f"channels/{channel_id}/{rel}",
                "vault_file": rel,
                "excerpt": body[:220],
            })
    vault_path = f"channels/{channel_id}/"
    return {
        "vault_path": vault_path,
        "vault_name": channel_id,
        "obsidian_url": f"obsidian://open?vault={quote(channel_id)}",
        "style_pages": {
            name: (wiki / "style" / f"{name}.md").exists()
            for name in ("voice", "visual", "motion", "index")
        },
        "page_count": len(pages),
        "recent_pages": pages,
    }


def _json_records(directory: Path) -> list[dict[str, Any]]:
    if not directory.is_dir():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]


def review_queue_for(root: Path, channel_id: str) -> dict[str, list[dict[str, Any]]]:
    queue = review_queue(root)
    return {
        category: [item for item in items if item.get("channel_id") == channel_id]
        for category, items in queue.items()
    }


def channel_overview(root: Path, channel_id: str) -> dict[str, Any]:
    """Creator-dashboard snapshot (Stage 1.5): header, progress, next action,
    review queue, style snapshot, pilots/episodes, services, events, wiki links."""
    from engine.channel import ChannelStateMachine
    from engine.channel.workflow import WORKFLOW_STATES

    package_root = root / "channels" / channel_id
    machine = ChannelStateMachine(package_root, root)
    package = machine.load(lenient=True)
    try:
        from dataclasses import asdict

        next_action = asdict(machine.next_allowed_action())
    except Exception as exc:  # noqa: BLE001 — surfaced in the panel, not raised
        next_action = {"error": str(exc)}
    state_name = package.state["state"]
    progress = {
        "states": list(WORKFLOW_STATES),
        "current": state_name,
        "completed": list(package.state.get("completed", [])),
        "position": WORKFLOW_STATES.index(state_name) + 1 if state_name in WORKFLOW_STATES else None,
        "total": len(WORKFLOW_STATES),
    }
    queue = review_queue_for(root, channel_id)
    pilots = [
        {"pilot_id": p["artifact_id"].split(":")[-1], "decision": p["review"]["decision"],
         "frozen": bool(p["freeze"]["frozen"])}
        for p in queue["pilots"]
    ]
    # frozen pilots are not in the undecided queue — rescan for full pilot/episode status
    pilots_root = package_root / "pilots"
    all_pilots: list[dict[str, Any]] = []
    if pilots_root.is_dir():
        for pilot_dir in sorted(pilots_root.iterdir()):
            candidate = pilot_dir / "pilot.json"
            if candidate.is_file():
                document = json.loads(candidate.read_text(encoding="utf-8"))
                all_pilots.append({
                    "pilot_id": pilot_dir.name,
                    "decision": document["review"]["decision"],
                    "frozen": bool(document["freeze"]["frozen"]),
                })
    episodes_root = package_root / "episodes"
    all_episodes: list[dict[str, Any]] = []
    if episodes_root.is_dir():
        for episode_dir in sorted(episodes_root.iterdir()):
            candidate = episode_dir / "episode.json"
            if candidate.is_file():
                document = json.loads(candidate.read_text(encoding="utf-8"))
                all_episodes.append({"episode_id": episode_dir.name, "decision": document["review"]["decision"]})
    wiki = package_root / "wiki"
    style_pages = {
        name: (wiki / "style" / f"{name}.md").exists()
        for name in ("voice", "visual", "motion", "index")
    }
    try:
        from tools._platform import service_status

        services = service_status()
    except ImportError:
        services = {}
    return {
        "header": {
            "channel_id": package.identity["id"],
            "name": package.identity["name"],
            "version": package.identity.get("version"),
            "niche": package.identity.get("niche", {}).get("primary"),
            "archetype": package.identity.get("production", {}).get("archetype"),
            "renderer": package.identity.get("production", {}).get("renderer"),
            "state": package.state["state"],
            "status": package.state["status"],
        },
        "progress": progress,
        "next_allowed_action": next_action,
        "reference_warnings": machine.reference_warnings(),
        "waiting_for": package.state.get("waiting_for"),
        "next_action_text": package.state.get("next_action"),
        "review_counts": {category: len(items) for category, items in queue.items()},
        "review_queue": queue,
        "style_pages": style_pages,
        "vault": vault_snapshot(root, channel_id),
        "pilots": all_pilots or pilots,
        "episodes": all_episodes,
        "services": services,
        "recent_events": package.state["events"][-10:],
        "wiki_links": {
            "home": f"channels/{channel_id}/wiki/HOME.md",
            "style": f"channels/{channel_id}/wiki/style/index.md",
            "market": f"channels/{channel_id}/wiki/market/opportunities/",
            "decisions": f"channels/{channel_id}/wiki/decisions/",
        },
    }


def review_queue(root: Path) -> dict[str, list[dict[str, Any]]]:
    channels_root = root / "channels"
    queue: dict[str, list[dict[str, Any]]] = {
        "script_examples": [], "design_exemplars": [], "identity_candidates": [], "asset_components": [],
        "pilots": [], "episodes": [], "niche_opportunities": [],
    }
    if not channels_root.is_dir():
        return queue
    for package_root in sorted(p for p in channels_root.iterdir() if p.is_dir()):
        channel_id = package_root.name
        for record in _json_records(package_root / "script" / "examples" / "records"):
            if record.get("classification") == "experimental":
                queue["script_examples"].append({"channel_id": channel_id, **record})
        for record in _json_records(package_root / "design" / "exemplars" / "records"):
            if record.get("classification") == "experimental":
                queue["design_exemplars"].append({"channel_id": channel_id, **record})
        for record in _json_records(package_root / "identity" / "candidates" / "records"):
            if record.get("classification") == "experimental":
                queue["identity_candidates"].append({"channel_id": channel_id, **record})
        for record in _json_records(package_root / "assets" / "registry"):
            if record.get("status") == "experimental":
                queue["asset_components"].append({"channel_id": channel_id, **record})
        pilots_root = package_root / "pilots"
        if pilots_root.is_dir():
            for pilot_dir in sorted(pilots_root.iterdir()):
                candidate = pilot_dir / "pilot.json"
                if candidate.is_file():
                    document = json.loads(candidate.read_text(encoding="utf-8"))
                    # REVISE stays visible until reworked and re-reviewed:
                    # removing it would erase the outstanding obligation.
                    if document["review"]["decision"] in (None, "REVISE"):
                        queue["pilots"].append({"channel_id": channel_id, **document})
        episodes_root = package_root / "episodes"
        if episodes_root.is_dir():
            for episode_dir in sorted(episodes_root.iterdir()):
                candidate = episode_dir / "episode.json"
                if candidate.is_file():
                    document = json.loads(candidate.read_text(encoding="utf-8"))
                    if document["review"]["decision"] in (None, "REVISE"):
                        queue["episodes"].append({"channel_id": channel_id, **document})
        studies_root = package_root / "intelligence" / "studies"
        if studies_root.is_dir():
            for study_dir in sorted(studies_root.iterdir()):
                for record in _json_records(study_dir / "opportunities"):
                    if record.get("status") == "PROPOSED":
                        queue["niche_opportunities"].append({"channel_id": channel_id, "study_id": study_dir.name, **record})
    return queue
