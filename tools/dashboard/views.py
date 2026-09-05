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
    package = machine.load()
    try:
        next_action = asdict(machine.next_allowed_action())
    except ChannelStateError as exc:
        next_action = {"error": str(exc)}
    return {
        "identity": package.identity, "state": package.state, "next_allowed_action": next_action,
        "recent_events": package.state["events"][-10:],
    }


def wiki_pages(root: Path, channel_id: str) -> list[dict[str, Any]]:
    repository = ChannelMemoryRepository(root)
    return [
        {"knowledge_id": doc.knowledge_id, "title": doc.title, "kind": doc.kind, "authority": doc.authority,
         "path": doc.path, "body": doc.body}
        for doc in repository.documents()
        if doc.scope == "CHANNEL" and doc.channel_id == channel_id
    ]


def _json_records(directory: Path) -> list[dict[str, Any]]:
    if not directory.is_dir():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]


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
                    if document["review"]["decision"] is None:
                        queue["pilots"].append({"channel_id": channel_id, **document})
        episodes_root = package_root / "episodes"
        if episodes_root.is_dir():
            for episode_dir in sorted(episodes_root.iterdir()):
                candidate = episode_dir / "episode.json"
                if candidate.is_file():
                    document = json.loads(candidate.read_text(encoding="utf-8"))
                    if document["review"]["decision"] is None:
                        queue["episodes"].append({"channel_id": channel_id, **document})
        studies_root = package_root / "intelligence" / "studies"
        if studies_root.is_dir():
            for study_dir in sorted(studies_root.iterdir()):
                for record in _json_records(study_dir / "opportunities"):
                    if record.get("status") == "PROPOSED":
                        queue["niche_opportunities"].append({"channel_id": channel_id, "study_id": study_dir.name, **record})
    return queue
