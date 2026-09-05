from __future__ import annotations

from pathlib import Path

import pytest

from engine.design import DesignValidationError
from engine.design.exemplars import ChannelExemplarStore


def make_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic-original-image-fixture")
    return path


def test_add_and_review_are_channel_scoped_and_never_touch_radicat_legacy_paths(tmp_path: Path) -> None:
    store = ChannelExemplarStore(tmp_path, "exemplar-channel")
    image = make_png(tmp_path / "src" / "frame.png")
    record = store.add(
        image, title="Cold open frame", domain="visual_identity", tags=["cold-open"],
        provenance_kind="human_supplied_original", created_by="Seb", source_ref="manual upload",
    )
    assert record["classification"] == "experimental"
    assert record["asset"]["path"].startswith("channels/exemplar-channel/design/exemplars/assets/")

    review = store.review(
        record["exemplar_id"], decision="approved", reviewer="Seb", reason="Matches direction.",
        created_at="2026-09-05T12:00:00+00:00", human_confirmed=True,
    )
    assert review["decision"] == "approved"

    all_paths = list(tmp_path.rglob("*"))
    assert all(
        "studio" not in path.relative_to(tmp_path).parts for path in all_paths
    ), "ChannelExemplarStore must never write under studio/ (Radicat's legacy exemplar store)"


def test_review_requires_human_confirmation(tmp_path: Path) -> None:
    store = ChannelExemplarStore(tmp_path, "exemplar-channel")
    image = make_png(tmp_path / "src" / "frame.png")
    record = store.add(
        image, title="Frame", domain=None, tags=[], provenance_kind="human_supplied_original",
        created_by="Seb", source_ref="manual upload",
    )
    with pytest.raises(DesignValidationError, match="human confirmation"):
        store.review(record["exemplar_id"], decision="approved", reviewer="Seb", reason="ok", created_at="2026-09-05T12:00:00+00:00", human_confirmed=False)


def test_ai_generated_requires_model_fields(tmp_path: Path) -> None:
    store = ChannelExemplarStore(tmp_path, "exemplar-channel")
    image = make_png(tmp_path / "src" / "frame.png")
    with pytest.raises(DesignValidationError, match="AI-generated"):
        store.add(
            image, title="Frame", domain=None, tags=[], provenance_kind="ai_generated_original",
            created_by="Seb", source_ref="prompt-1",
        )


def test_list_filters_by_domain_and_classification(tmp_path: Path) -> None:
    store = ChannelExemplarStore(tmp_path, "exemplar-channel")
    image_a = make_png(tmp_path / "src" / "a.png")
    image_b = make_png(tmp_path / "src" / "b.png")
    store.add(image_a, title="Visual A", domain="visual_identity", tags=[], provenance_kind="human_supplied_original", created_by="Seb", source_ref="a")
    store.add(image_b, title="Typography B", domain="typography", tags=[], provenance_kind="human_supplied_original", created_by="Seb", source_ref="b")
    assert len(store.list(domain="visual_identity")) == 1
    assert len(store.list()) == 2
    assert len(store.list(classification="approved")) == 0
