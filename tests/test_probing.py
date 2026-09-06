"""Binary media probing: stdlib structural checks on production media.

WAV files fully decode; MP4 files prove an ftyp container (labeled
container-level — not a decode check); PNG files prove signature + IHDR.
Corrupt media blocks a GO via check_production; unknown suffixes stay
hash-bound only (probed False, never a failure).

Opt-in strict decode (ffprobe dimensions, duration, narrated audio) is
fail-open without ffprobe and blocking with it; fixtures stay stubs so the
default gate never needs a decoder.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from engine.production.completeness import check_production
from engine.production.probing import (
    encode_minimal_mp4,
    encode_minimal_png,
    encode_minimal_wav,
    ffprobe_available,
    probe_file,
    probe_mp4_decode,
)


def write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path.name


def test_probe_round_trips_minimal_encoders(tmp_path: Path) -> None:
    wav = tmp_path / "a.wav"
    wav.write_bytes(encode_minimal_wav())
    report = probe_file(wav)
    assert report["probed"] is True and report["problems"] == []
    assert report["details"]["duration_s"] == 0.1

    mp4 = tmp_path / "b.mp4"
    mp4.write_bytes(encode_minimal_mp4())
    report = probe_file(mp4)
    assert report["probed"] is True and report["problems"] == []
    assert report["details"]["level"] == "container_only"

    png = tmp_path / "c.png"
    png.write_bytes(encode_minimal_png(width=3, height=2))
    report = probe_file(png)
    assert report["probed"] is True and report["problems"] == []
    assert (report["details"]["width"], report["details"]["height"]) == (3, 2)


def test_probe_rejects_corrupt_media(tmp_path: Path) -> None:
    bad_wav = tmp_path / "bad.wav"
    bad_wav.write_bytes(b"RIFF" + b"\x00" * 100)
    report = probe_file(bad_wav)
    assert report["probed"] is True and report["problems"]

    bad_mp4 = tmp_path / "bad.mp4"
    bad_mp4.write_bytes(b"fake-video-bytes")
    report = probe_file(bad_mp4)
    assert report["probed"] is True and report["problems"]
    assert any("ftyp" in problem for problem in report["problems"])

    bad_png = tmp_path / "bad.png"
    bad_png.write_bytes(b"synthetic-original-image-fixture")
    report = probe_file(bad_png)
    assert report["probed"] is True and report["problems"]

    truncated = tmp_path / "short.wav"
    truncated.write_bytes(encode_minimal_wav()[:20])
    assert probe_file(truncated)["problems"]


def test_probe_leaves_unknown_suffixes_unprobed(tmp_path: Path) -> None:
    blob = tmp_path / "evidence.bin"
    blob.write_bytes(b"\x00\x01\x02")
    report = probe_file(blob)
    assert report["probed"] is False and report["problems"] == []


def _production(tmp_path: Path, *, voiceover: bytes, render: bytes) -> dict:
    (tmp_path / "script.md").write_text("# Script\n", encoding="utf-8")
    (tmp_path / "voiceover.wav").write_bytes(voiceover)
    (tmp_path / "render.mp4").write_bytes(render)
    (tmp_path / "scene.json").write_text(
        '{"artifact_type": "scene_candidate_manifest", "artifact_id": "scene-candidate:x:abc"}',
        encoding="utf-8",
    )
    (tmp_path / "eval.json").write_text(
        '{"artifact_type": "evaluation_result", "artifact_id": "evaluation-result:abc"}',
        encoding="utf-8",
    )
    return {
        "script_ref": "script.md",
        "voiceover_ref": "voiceover.wav",
        "scene_candidate_manifest_refs": [{"artifact_id": "scene-candidate:x:abc", "sha256": "x"}],
        "evaluation_result_refs": [{"artifact_id": "evaluation-result:abc", "sha256": "x"}],
        "render_ref": "render.mp4",
        "production_log_ref": None,
        "revision": None,
    }


def _real_mp4(path: Path) -> Path:
    """One second of test video + tone: a genuinely decodable fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-pix_fmt", "yuv420p", "-shortest", str(path)],
        check=True, capture_output=True,
    )
    return path


needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe required for decode tests",
)


@needs_ffmpeg
def test_decode_probe_accepts_real_render(tmp_path: Path) -> None:
    video = _real_mp4(tmp_path / "real.mp4")
    report = probe_mp4_decode(video)
    assert report["probed"] is True and report["problems"] == []
    assert (report["details"]["width"], report["details"]["height"]) == (64, 64)
    assert report["details"]["duration_s"] > 0
    assert report["details"]["has_audio"] is True


@needs_ffmpeg
def test_decode_probe_rejects_container_stub(tmp_path: Path) -> None:
    stub = tmp_path / "stub.mp4"
    stub.write_bytes(encode_minimal_mp4())
    report = probe_mp4_decode(stub)
    assert report["probed"] is True and report["problems"]


def test_decode_probe_is_fail_open_without_ffprobe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    assert not ffprobe_available()
    stub = tmp_path / "stub.mp4"
    stub.write_bytes(encode_minimal_mp4())
    report = probe_mp4_decode(stub)
    assert report == {"probed": False, "problems": [], "details": {"reason": "ffprobe unavailable"}}


@needs_ffmpeg
def test_strict_media_blocks_stub_but_passes_real_render(tmp_path: Path) -> None:
    production = _production(tmp_path, voiceover=encode_minimal_wav(), render=encode_minimal_mp4())
    assert check_production(production, repository_root=tmp_path, label="pilot x") == []
    strict = check_production(production, repository_root=tmp_path, label="pilot x", strict_media=True)
    assert strict

    production = _production(tmp_path, voiceover=encode_minimal_wav(), render=encode_minimal_mp4())
    (tmp_path / "render.mp4").write_bytes(_real_mp4(tmp_path / "fresh.mp4").read_bytes())
    assert check_production(production, repository_root=tmp_path, label="pilot x", strict_media=True) == []


def test_strict_media_refuses_without_decoder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    production = _production(tmp_path, voiceover=encode_minimal_wav(), render=encode_minimal_mp4())
    problems = check_production(production, repository_root=tmp_path, label="pilot x", strict_media=True)
    assert any("ffprobe" in problem for problem in problems)
    # Non-strict default is unaffected: stubs still pass without a decoder.
    assert check_production(production, repository_root=tmp_path, label="pilot x") == []


def test_check_production_blocks_corrupt_media_but_accepts_valid(tmp_path: Path) -> None:
    production = _production(tmp_path, voiceover=encode_minimal_wav(), render=encode_minimal_mp4())
    assert check_production(production, repository_root=tmp_path, label="pilot x") == []

    production = _production(tmp_path, voiceover=b"RIFF" + b"\x00" * 100, render=encode_minimal_mp4())
    problems = check_production(production, repository_root=tmp_path, label="pilot x")
    assert any("voiceover" in problem for problem in problems)

    production = _production(tmp_path, voiceover=encode_minimal_wav(), render=b"fake-video-bytes")
    problems = check_production(production, repository_root=tmp_path, label="pilot x")
    assert any("render" in problem for problem in problems)
