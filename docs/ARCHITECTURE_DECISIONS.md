# Architecture Decisions

## AD-013: Canonical knowledge is not the retrieval index

The channel wiki's canonical files (Markdown pages under `engine/memory/wiki/`
and `channels/<id>/wiki/`) are authoritative. The search index
(`.memory-index/scoped-memory.json`) built by `ChannelMemoryRepository` is
derived, disposable, and replaceable — it can always be deleted and rebuilt
from the canonical files with identical results (see
`tests/test_channel_memory.py::test_search_is_deterministic_and_disposable_index_rebuilds_identically`).
Nothing should ever treat the index itself as a source of truth.
