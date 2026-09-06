"""Channel-scoped Niche Intelligence access and CM2 semantic-summary integration."""

from __future__ import annotations

import re
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
    "content_annotation": ("concept", "descriptive", "market/teardowns", None),
    "script_annotation": ("concept", "descriptive", "market/teardowns", None),
    "visual_market_annotation": ("concept", "descriptive", "market/teardowns", None),
}


def _teardown_summary(item: dict[str, Any]) -> str:
    """One-paragraph plain-text summary of a what-works teardown annotation."""
    video = item["video_evidence_id"]
    kind = item["artifact_type"]
    if kind == "content_annotation":
        ann = item["annotation"]
        chars = ann["characteristics"]
        return (
            f"Content teardown of {video}: hook {ann['hook_family']} "
            f"({ann['hook_text'] or 'no transcript excerpt'}), structure {ann['structure']}, "
            f"ending {ann['ending']}, promise {ann['viewer_promise'] or 'unstated'}, "
            f"density {chars['information_density']}, depth {chars['technical_depth']}, "
            f"numeric specificity {chars['numeric_specificity']}."
        )
    if kind == "script_annotation":
        stats = item["statistics"]
        anns = item["annotations"]
        return (
            f"Script teardown of {video}: {stats['word_count']} words "
            f"@ {stats['words_per_second']} wps, hook: {anns['hook'] or 'undescribed'}, "
            f"structure: {anns['narrative_structure'] or 'undescribed'}, "
            f"ending: {anns['ending_behavior'] or 'undescribed'}, "
            f"transcript {item['transcript']['availability']} "
            f"({item['transcript']['method']})."
        )
    ann = item["annotation"]
    return (
        f"Visual teardown of {video}: approaches {', '.join(ann['production_approaches'])}, "
        f"text density {ann['text_density_proxy']}, metaphors {ann['visual_metaphor_usage']}, "
        f"continuity {ann['continuity']}. Market evidence only — never design authority."
    )


def _summary_text(item: dict[str, Any], text_field: str | None) -> str:
    if text_field is not None:
        return item[text_field]
    return _teardown_summary(item)


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
        # Relevance before confidence: the query decides what matters; a
        # confident but irrelevant interpretation must not crowd out a
        # tentative but on-point one.
        query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        scored = []
        for item in validated.artifacts.values():
            if item["artifact_type"] not in SUMMARY_TYPES:
                continue
            _, _, _, text_field = SUMMARY_TYPES[item["artifact_type"]]
            full_text = _summary_text(item, text_field)
            hits = sum(full_text.lower().count(term) for term in query_terms) if query_terms else 0
            confidence = item["confidence"] if item["confidence"] is not None else -1
            scored.append((hits, confidence, item, full_text))
        scored.sort(key=lambda entry: (-entry[0], -entry[1], entry[2]["artifact_id"]))
        remaining = max_summary_chars
        selected = []
        for hits, _, item, full_text in scored[:artifact_limit]:
            text = full_text[:remaining]
            remaining -= len(text)
            selected.append({
                "artifact_id": item["artifact_id"],
                "artifact_type": item["artifact_type"],
                "authority": item["authority"],
                "confidence": item["confidence"],
                "relevance_hits": hits,
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
        """Create channel-scoped Wiki summaries that point to exact structured artifacts.

        Summaries are namespaced by study (``<directory>/<study-id>-<key>.md``)
        so reused keys across studies never collide, and publishing is
        idempotent: an identical summary already on disk is skipped, not an
        error.
        """

        validated = self._validated(package_root, study_root)
        study_id = validated.study["study_id"]
        created = []
        for artifact_id, item in sorted(validated.artifacts.items()):
            if item["artifact_type"] not in SUMMARY_TYPES:
                continue
            kind, authority, directory, text_field = SUMMARY_TYPES[item["artifact_type"]]
            suffix = artifact_id.rsplit(":", 1)[-1]
            namespaced = f"{study_id}-{suffix}"
            structured_path = validated.paths[artifact_id].relative_to(self.root).as_posix()
            created_at = item["created_by"]["created_at"]
            text = _summary_text(item, text_field)
            title = text.split(".", 1)[0][:100]
            metadata = {
                "schema_version": "0.3.0",
                "knowledge_id": f"wiki:channel/{item['channel_id']}/market/{kind}/{namespaced}",
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
                f"# {title}\n\n{text}\n\n"
                f"Authority: `{item['authority']}`. Exact structured source: `{structured_path}`. "
                "This summary does not create a channel, script, design, or Engine rule."
            )
            relative = f"{directory}/{namespaced}.md"
            existing = (
                self.memory.channels_root / item["channel_id"] / "wiki" / relative
            )
            if existing.is_file():
                continue
            try:
                created.append(self.memory.write_page(relative, metadata, body))
            except KnowledgeError as exc:
                raise NicheValidationError(str(exc)) from exc
        return created
