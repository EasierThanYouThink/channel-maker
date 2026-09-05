"""Channel-scoped Niche Intelligence access and CM2 semantic-summary integration."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from engine.channel import ChannelValidationError, validate_channel_package
from engine.memory import ChannelMemoryRepository
from engine.memory.wiki_pages import KnowledgeError

from .validation import NicheValidationError, ValidatedStudy, validate_study


SUMMARY_TYPES = {
    "niche_observation": ("observation", "descriptive", "market/observations", "statement"),
    "niche_hypothesis": ("hypothesis", "ai_proposed", "market/hypotheses", "statement"),
    "opportunity_proposal": ("opportunity_proposal", "ai_proposed", "market/opportunities", "proposal"),
}


class NicheIntelligenceRepository:
    """Read validated structured studies through one Channel Package boundary."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.memory = ChannelMemoryRepository(self.root)

    def _validated(self, package_root: Path, study_root: Path) -> ValidatedStudy:
        try:
            package = validate_channel_package(package_root.resolve(), self.root)
        except ChannelValidationError as exc:
            raise NicheValidationError(str(exc)) from exc
        return validate_study(
            study_root,
            repository_root=self.root,
            expected_channel_id=package.identity["id"],
        )

    def build_context_bundle(
        self,
        package_root: Path,
        study_root: Path,
        query: str,
        *,
        include_engine: bool = False,
        artifact_limit: int = 6,
        memory_limit: int = 6,
        max_summary_chars: int = 2400,
    ) -> dict[str, Any]:
        """Return bounded semantic study context plus CM2 memory, never raw evidence."""

        if artifact_limit < 1 or memory_limit < 1 or max_summary_chars < 0:
            raise NicheValidationError("context bounds must be positive (summary chars may be zero)")
        validated = self._validated(package_root, study_root)
        candidates = [
            item for item in validated.artifacts.values()
            if item["artifact_type"] in SUMMARY_TYPES
        ]
        candidates.sort(
            key=lambda item: (
                -(item["confidence"] if item["confidence"] is not None else -1),
                item["artifact_id"],
            )
        )
        remaining = max_summary_chars
        selected = []
        for item in candidates[:artifact_limit]:
            _, _, _, text_field = SUMMARY_TYPES[item["artifact_type"]]
            text = item[text_field][:remaining]
            remaining -= len(text)
            selected.append({
                "artifact_id": item["artifact_id"],
                "artifact_type": item["artifact_type"],
                "authority": item["authority"],
                "confidence": item["confidence"],
                "summary": text,
                "path": validated.paths[item["artifact_id"]].relative_to(self.root).as_posix(),
            })
            if remaining == 0:
                break
        memory = self.memory.build_context_bundle(
            package_root, query, include_engine=include_engine,
            limit=memory_limit, max_body_chars=max_summary_chars,
        )
        study = validated.study
        return {
            "schema_version": "1.0.0",
            "channel_id": study["channel_id"],
            "study": {
                "study_id": study["study_id"], "study_version": study["study_version"],
                "scope": study["scope"], "study_window": study["study_window"],
                "freshness": study["freshness"], "methodology_version": study["methodology_version"],
            },
            "semantic_artifacts": selected,
            "limitations": validated.report["limitations"],
            "memory": memory["memory"],
            "channel_state": memory["channel_state"],
            "bounds": {
                "artifact_limit": artifact_limit, "memory_limit": memory_limit,
                "max_summary_chars": max_summary_chars,
            },
        }

    def publish_semantic_summaries(self, package_root: Path, study_root: Path) -> list[Path]:
        """Create channel-scoped Wiki summaries that point to exact structured artifacts."""

        validated = self._validated(package_root, study_root)
        created = []
        for artifact_id, item in sorted(validated.artifacts.items()):
            if item["artifact_type"] not in SUMMARY_TYPES:
                continue
            kind, authority, directory, text_field = SUMMARY_TYPES[item["artifact_type"]]
            suffix = artifact_id.rsplit(":", 1)[-1]
            structured_path = validated.paths[artifact_id].relative_to(self.root).as_posix()
            created_at = item["created_by"]["created_at"]
            title = item[text_field].split(".", 1)[0][:100]
            metadata = {
                "schema_version": "0.3.0",
                "knowledge_id": f"wiki:channel/{item['channel_id']}/market/{kind}/{suffix}",
                "title": title,
                "kind": kind,
                "status": "active" if item.get("status", "ACTIVE") in {"ACTIVE", "PROPOSED"} else "superseded",
                "authority": authority,
                "scope": "CHANNEL",
                "channel_id": item["channel_id"],
                "video_id": None,
                "tags": ["market", "niche_intelligence", kind],
                "confidence": item["confidence"],
                "created_at": created_at,
                "updated_at": created_at,
                "related": [f"evidence:{artifact_id}"],
                "provenance": [{"kind": "repository", "ref": structured_path}],
            }
            body = (
                f"# {title}\n\n{item[text_field]}\n\n"
                f"Authority: `{item['authority']}`. Exact structured source: `{structured_path}`. "
                "This summary does not create a channel, script, design, or Engine rule."
            )
            try:
                created.append(self.memory.write_page(f"{directory}/{suffix}.md", metadata, body))
            except KnowledgeError as exc:
                raise NicheValidationError(str(exc)) from exc
        return created
