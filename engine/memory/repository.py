"""Scoped Markdown memory with a disposable deterministic lexical index."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

import yaml

from engine.channel import ChannelValidationError, validate_channel_package
from engine.memory.wiki_pages import KnowledgeError, parse_wiki_page, validate_metadata


TOKEN = re.compile(r"[a-z0-9]+")
RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
WIKI_DIRECTORIES = (
    "strategy",
    "market/observations",
    "market/hypotheses",
    "market/opportunities",
    "market/teardowns",
    "script",
    "visual",
    "motion",
    "assets",
    "decisions",
    "experiments",
    "lessons",
    "failures",
    "style",
)


@dataclass(frozen=True)
class MemoryDocument:
    knowledge_id: str
    title: str
    kind: str
    status: str
    authority: str
    scope: str
    channel_id: str | None
    video_id: str | None
    tags: tuple[str, ...]
    confidence: float | None
    path: str
    body: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class MemorySearchResult:
    knowledge_id: str
    title: str
    kind: str
    authority: str
    scope: str
    channel_id: str | None
    video_id: str | None
    score: int
    path: str
    excerpt: str


class ScopedMemoryAPI(Protocol):
    """Provider-neutral read boundary for future lexical or vector implementations."""

    def search(
        self,
        query: str,
        *,
        channel_id: str | None = None,
        video_id: str | None = None,
        include_engine: bool = False,
        kinds: set[str] | None = None,
        authorities: set[str] | None = None,
        tags: set[str] | None = None,
        limit: int = 10,
    ) -> list[MemorySearchResult]: ...

    def build_context_bundle(
        self,
        package_root: Path,
        query: str,
        *,
        video_id: str | None = None,
        include_engine: bool = False,
        limit: int = 8,
        max_body_chars: int = 2400,
    ) -> dict[str, Any]: ...


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _write_atomic(path: Path, content: bytes) -> None:
    from engine.channel._portable import write_bytes_atomic

    write_bytes_atomic(path, content)


def _timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _datetime(value: str, label: str = "timestamp") -> datetime:
    try:
        if not RFC3339.fullmatch(value):
            raise ValueError("not RFC 3339")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone is required")
        return parsed
    except (TypeError, ValueError) as exc:
        raise KnowledgeError(f"{label} must be an RFC 3339 date-time: {value!r}") from exc


def _render_page(metadata: dict[str, Any], body: str) -> bytes:
    frontmatter = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{frontmatter}\n---\n\n{body.strip()}\n".encode("utf-8")


class ChannelMemoryRepository:
    """One scoped view over canonical Engine, Channel, Video, and legacy Radicat Markdown."""

    INDEX_SCHEMA_VERSION = "0.1.0"

    def __init__(self, root: Path, *, index_path: Path | None = None):
        self.root = root.resolve()
        self.contract = self.root / "engine" / "memory" / "contracts" / "wiki-page.schema.json"
        self.engine_wiki = self.root / "engine" / "memory" / "wiki"
        self.channels_root = self.root / "channels"
        self.legacy_radicat_wiki = self.root / "studio" / "knowledge" / "wiki"
        self.index_path = (index_path or self.root / ".memory-index" / "scoped-memory.json").resolve()
        if not self.index_path.is_relative_to(self.root):
            raise KnowledgeError(f"memory index escapes repository root: {self.index_path}")

    def _validate_repository_provenance(self, document: MemoryDocument) -> None:
        for source in document.metadata.get("provenance", []):
            if source["kind"] != "repository":
                continue
            relative = source["ref"].split("#", 1)[0]
            path = (self.root / relative).resolve()
            if not path.is_relative_to(self.root):
                raise KnowledgeError(f"{document.path}: repository provenance escapes root: {source['ref']}")
            if not path.exists():
                raise KnowledgeError(f"{document.path}: repository provenance is missing: {source['ref']}")

    @staticmethod
    def _validate_scope_identity(metadata: dict[str, Any], label: str) -> None:
        scope = metadata["scope"]
        if scope == "ENGINE":
            prefix = "wiki:engine/"
        elif scope == "CHANNEL":
            prefix = f"wiki:channel/{metadata['channel_id']}/"
        else:
            prefix = f"wiki:video/{metadata['channel_id']}/{metadata['video_id']}/"
        if not metadata["knowledge_id"].startswith(prefix):
            raise KnowledgeError(f"{label}: knowledge_id must start with {prefix!r} for {scope} scope")

    def _document(self, path: Path, *, expected_scope: str, channel_id: str | None = None) -> MemoryDocument:
        if not path.resolve().is_relative_to(self.root):
            raise KnowledgeError(f"Wiki page escapes repository root: {path}")
        page = parse_wiki_page(path, self.contract)
        metadata = page.metadata
        if metadata["schema_version"] not in {"0.2.0", "0.3.0"}:
            raise KnowledgeError(f"{path}: scoped Wiki roots require metadata schema 0.2.0 or 0.3.0")
        if metadata["scope"] != expected_scope:
            raise KnowledgeError(f"{path}: expected {expected_scope} scope, found {metadata['scope']}")
        if metadata["channel_id"] != channel_id:
            raise KnowledgeError(f"{path}: channel_id does not match its Wiki root")
        self._validate_scope_identity(metadata, str(path))
        if _datetime(metadata["updated_at"], "updated_at") < _datetime(metadata["created_at"], "created_at"):
            raise KnowledgeError(f"{path}: updated_at precedes created_at")
        if expected_scope == "VIDEO":
            relative_parts = path.relative_to(self.channels_root / channel_id / "wiki").parts
            if len(relative_parts) < 3 or relative_parts[0] != "videos" or relative_parts[1] != metadata["video_id"]:
                raise KnowledgeError(f"{path}: VIDEO memory must be under wiki/videos/<video_id>/")
        document = MemoryDocument(
            page.knowledge_id,
            metadata["title"],
            metadata["kind"],
            metadata["status"],
            metadata["authority"],
            metadata["scope"],
            metadata["channel_id"],
            metadata["video_id"],
            tuple(metadata["tags"]),
            metadata["confidence"],
            path.relative_to(self.root).as_posix(),
            page.body,
            metadata,
        )
        self._validate_repository_provenance(document)
        return document

    def _legacy_documents(self) -> list[MemoryDocument]:
        if not self.legacy_radicat_wiki.exists():
            return []
        documents = []
        for path in sorted(self.legacy_radicat_wiki.rglob("*.md")):
            page = parse_wiki_page(path, self.contract)
            metadata = page.metadata
            document = MemoryDocument(
                page.knowledge_id,
                metadata["title"],
                metadata["kind"],
                metadata["status"],
                metadata["authority"],
                "CHANNEL",
                "radicat",
                None,
                tuple(metadata["tags"]),
                None,
                path.relative_to(self.root).as_posix(),
                page.body,
                metadata,
            )
            self._validate_repository_provenance(document)
            documents.append(document)
        return documents

    def documents(self) -> list[MemoryDocument]:
        documents: list[MemoryDocument] = []
        for path in sorted(self.engine_wiki.rglob("*.md")) if self.engine_wiki.exists() else []:
            documents.append(self._document(path, expected_scope="ENGINE"))
        if self.channels_root.exists():
            for channel_root in sorted(path for path in self.channels_root.iterdir() if path.is_dir()):
                wiki = channel_root / "wiki"
                for path in sorted(wiki.rglob("*.md")) if wiki.exists() else []:
                    relative = path.relative_to(wiki)
                    expected_scope = "VIDEO" if relative.parts and relative.parts[0] == "videos" else "CHANNEL"
                    documents.append(
                        self._document(path, expected_scope=expected_scope, channel_id=channel_root.name)
                    )
        documents.extend(self._legacy_documents())
        by_id: dict[str, list[str]] = {}
        for document in documents:
            by_id.setdefault(document.knowledge_id, []).append(document.path)
        duplicates = {key: value for key, value in by_id.items() if len(value) > 1}
        if duplicates:
            raise KnowledgeError(f"duplicate scoped knowledge IDs: {duplicates}")
        return sorted(documents, key=lambda item: item.knowledge_id)

    def canonical_fingerprint(self, documents: Iterable[MemoryDocument] | None = None) -> str:
        digest = hashlib.sha256()
        digest.update(self.contract.read_bytes())
        for document in documents or self.documents():
            digest.update(document.path.encode("utf-8"))
            digest.update(b"\0")
            digest.update((self.root / document.path).read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _indexed_documents(documents: Iterable[MemoryDocument]) -> list[dict[str, Any]]:
        return [
            {
                **asdict(document),
                "tags": list(document.tags),
            }
            for document in documents
        ]

    def rebuild_index(self) -> dict[str, Any]:
        documents = self.documents()
        payload = {
            "schema_version": self.INDEX_SCHEMA_VERSION,
            "canonical_fingerprint": self.canonical_fingerprint(documents),
            "documents": self._indexed_documents(documents),
        }
        _write_atomic(self.index_path, _canonical_bytes(payload))
        return payload

    def _index(self) -> dict[str, Any]:
        canonical_documents = self.documents()
        canonical_fingerprint = self.canonical_fingerprint(canonical_documents)
        indexed_documents = self._indexed_documents(canonical_documents)
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema_version") != self.INDEX_SCHEMA_VERSION:
                raise ValueError("unsupported memory index")
            if (
                payload.get("canonical_fingerprint") != canonical_fingerprint
                or payload.get("documents") != indexed_documents
            ):
                return self.rebuild_index()
            return payload
        except (OSError, json.JSONDecodeError, ValueError):
            return self.rebuild_index()

    def search(
        self,
        query: str,
        *,
        channel_id: str | None = None,
        video_id: str | None = None,
        include_engine: bool = False,
        kinds: set[str] | None = None,
        authorities: set[str] | None = None,
        tags: set[str] | None = None,
        limit: int = 10,
    ) -> list[MemorySearchResult]:
        if limit < 1:
            raise KnowledgeError("search limit must be positive")
        if video_id and not channel_id:
            raise KnowledgeError("video-scoped search requires channel_id")
        terms = TOKEN.findall(query.lower())
        results = []
        for document in self._index()["documents"]:
            scope = document["scope"]
            visible = (
                (scope == "ENGINE" and include_engine)
                or (scope == "CHANNEL" and channel_id is not None and document["channel_id"] == channel_id)
                or (
                    scope == "VIDEO" and channel_id is not None and video_id is not None
                    and document["channel_id"] == channel_id and document["video_id"] == video_id
                )
            )
            if not visible:
                continue
            if kinds and document["kind"] not in kinds:
                continue
            if authorities and document["authority"] not in authorities:
                continue
            if tags and not tags.issubset(set(document["tags"])):
                continue
            title = document["title"].lower()
            tag_text = " ".join(document["tags"]).lower()
            body = document["body"].lower()
            score = sum(title.count(term) * 5 + tag_text.count(term) * 3 + body.count(term) for term in terms)
            if terms and score == 0:
                continue
            excerpt = " ".join(document["body"].split())[:240]
            results.append(
                MemorySearchResult(
                    document["knowledge_id"], document["title"], document["kind"],
                    document["authority"], scope, document["channel_id"], document["video_id"],
                    score, document["path"], excerpt,
                )
            )
        return sorted(results, key=lambda item: (-item.score, item.knowledge_id))[:limit]

    def get(
        self,
        knowledge_id: str,
        *,
        channel_id: str | None = None,
        video_id: str | None = None,
        include_engine: bool = False,
    ) -> MemoryDocument | None:
        visible = {result.knowledge_id for result in self.search(
            "", channel_id=channel_id, video_id=video_id, include_engine=include_engine, limit=100000
        )}
        return next(
            (document for document in self.documents() if document.knowledge_id == knowledge_id and document.knowledge_id in visible),
            None,
        )

    def build_context_bundle(
        self,
        package_root: Path,
        query: str,
        *,
        video_id: str | None = None,
        include_engine: bool = False,
        limit: int = 8,
        max_body_chars: int = 2400,
    ) -> dict[str, Any]:
        try:
            package = validate_channel_package(package_root.resolve(), self.root)
        except ChannelValidationError as exc:
            raise KnowledgeError(str(exc)) from exc
        results = self.search(
            query,
            channel_id=package.identity["id"],
            video_id=video_id,
            include_engine=include_engine,
            limit=limit,
        )
        documents = {document.knowledge_id: document for document in self.documents()}
        remaining = max(0, max_body_chars)
        selected = []
        for result in results:
            document = documents[result.knowledge_id]
            body = document.body[:remaining]
            remaining -= len(body)
            selected.append({**asdict(result), "body": body})
            if remaining == 0:
                break
        state = package.state
        return {
            "schema_version": "0.1.0",
            "channel_id": package.identity["id"],
            "video_id": video_id,
            "query": query,
            "channel_state": {
                "revision": state["revision"],
                "state": state["state"],
                "status": state["status"],
                "waiting_for": state["waiting_for"],
                "next_action": state["next_action"],
                "known_gaps": state["known_gaps"],
            },
            "memory": selected,
            "bounds": {"result_limit": limit, "max_body_chars": max_body_chars},
        }

    def write_page(self, relative_path: str, metadata: dict[str, Any], body: str) -> Path:
        validate_metadata(metadata, self.contract, "scoped Wiki metadata")
        if metadata.get("schema_version") not in {"0.2.0", "0.3.0"}:
            raise KnowledgeError("new memory write-back requires metadata schema 0.2.0 or 0.3.0")
        self._validate_scope_identity(metadata, "scoped Wiki metadata")
        if _datetime(metadata["updated_at"], "updated_at") < _datetime(metadata["created_at"], "created_at"):
            raise KnowledgeError("scoped Wiki metadata updated_at precedes created_at")
        if not body.strip():
            raise KnowledgeError("memory write-back body must not be empty")
        if metadata["authority"] not in {"descriptive", "ai_proposed", "provisional"}:
            raise KnowledgeError(
                "generic write-back cannot create canonical or human-authority memory; "
                "use a future governed human promotion path"
            )
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".md":
            raise KnowledgeError(f"invalid memory relative path: {relative_path}")
        scope = metadata["scope"]
        if scope == "ENGINE":
            base = self.engine_wiki
        else:
            channel_id = metadata["channel_id"]
            package_root = self.channels_root / channel_id
            try:
                validate_channel_package(package_root, self.root)
            except ChannelValidationError as exc:
                raise KnowledgeError(str(exc)) from exc
            base = package_root / "wiki"
            if scope == "VIDEO":
                base = base / "videos" / metadata["video_id"]
        target = (base / relative).resolve()
        resolved_base = base.resolve()
        if not resolved_base.is_relative_to(self.root) or not target.is_relative_to(resolved_base):
            raise KnowledgeError(f"memory write-back escapes its scope root: {relative_path}")
        if target.exists():
            raise KnowledgeError(f"memory write-back will not overwrite existing page: {target}")
        candidate = MemoryDocument(
            metadata["knowledge_id"], metadata["title"], metadata["kind"], metadata["status"],
            metadata["authority"], metadata["scope"], metadata["channel_id"], metadata["video_id"],
            tuple(metadata["tags"]), metadata["confidence"], target.relative_to(self.root).as_posix(),
            body.strip(), metadata,
        )
        self._validate_repository_provenance(candidate)
        if any(document.knowledge_id == candidate.knowledge_id for document in self.documents()):
            raise KnowledgeError(f"duplicate scoped knowledge ID: {candidate.knowledge_id}")
        _write_atomic(target, _render_page(metadata, body))
        return target


def initialize_channel_wiki(
    package_root: Path,
    repository_root: Path,
    *,
    created_at: str | None = None,
) -> Path:
    """Create the minimal Obsidian-compatible Wiki skeleton for one valid Channel Package."""

    repository_root = repository_root.resolve()
    try:
        package = validate_channel_package(package_root.resolve(), repository_root)
    except ChannelValidationError as exc:
        raise KnowledgeError(str(exc)) from exc
    wiki = package.root / "wiki"
    for relative in WIKI_DIRECTORIES:
        target = (wiki / relative).resolve()
        if not target.is_relative_to(repository_root) or not target.is_relative_to(wiki.resolve()):
            raise KnowledgeError(f"channel Wiki directory escapes repository root: {target}")
        target.mkdir(parents=True, exist_ok=True)
    home = wiki / "HOME.md"
    if home.exists():
        page = parse_wiki_page(home, repository_root / "engine" / "memory" / "contracts" / "wiki-page.schema.json")
        if page.metadata.get("scope") != "CHANNEL" or page.metadata.get("channel_id") != package.identity["id"]:
            raise KnowledgeError(f"{home}: existing HOME metadata does not match Channel Package")
        ChannelMemoryRepository._validate_scope_identity(page.metadata, str(home))
        return home
    timestamp = _timestamp(created_at)
    _datetime(timestamp, "created_at")
    metadata = {
        "schema_version": "0.2.0",
        "knowledge_id": f"wiki:channel/{package.identity['id']}/home",
        "title": f"{package.identity['name']} Channel Memory",
        "kind": "index",
        "status": "active",
        "authority": "canonical",
        "scope": "CHANNEL",
        "channel_id": package.identity["id"],
        "video_id": None,
        "tags": ["channel", "memory"],
        "confidence": None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "related": [],
        "provenance": [{
            "kind": "repository",
            "ref": f"channels/{package.identity['id']}/channel.yaml",
        }],
    }
    body = (
        f"# {package.identity['name']} Channel Memory\n\n"
        "This ordinary Markdown Wiki is the canonical home for channel-scoped semantic memory. "
        "Retrieval indexes are derived and disposable; narrower knowledge never promotes itself."
    )
    repository = ChannelMemoryRepository(repository_root)
    validate_metadata(metadata, repository.contract, "initialized Channel Wiki metadata")
    candidate = MemoryDocument(
        metadata["knowledge_id"], metadata["title"], metadata["kind"], metadata["status"],
        metadata["authority"], metadata["scope"], metadata["channel_id"], metadata["video_id"],
        tuple(metadata["tags"]), metadata["confidence"], home.relative_to(repository_root).as_posix(),
        body, metadata,
    )
    repository._validate_repository_provenance(candidate)
    _write_atomic(home, _render_page(metadata, body))
    return home
