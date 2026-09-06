"""Stdlib-only structural probing for production media files.

What each probe guarantees (and does not):
- WAV: fully decoded with the stdlib `wave` module — valid header, readable
  frames, real duration. A file that fails here is corrupt, not just honest.
- MP4: container-level only — an `ftyp` box with a plausible size and an
  ASCII major brand at the head of the file. This proves the bytes are an
  ISO-BMFF container, NOT that the video decodes or matches any duration.
  Decoded dimensions/duration still need a pinned probing tool.
- PNG: signature + IHDR parse (width/height) with CRC verification.
- Anything else: unprobed (`probed: False`, no problems) — hash binding in
  the manifest remains the evidence there.

The `encode_minimal_*` constructors below produce structurally valid but
content-synthetic bytes for tests: a 0.1 s silent WAV, an `ftyp`-headed MP4
stub, a 1x1 PNG. They exist so fixtures prove the gate instead of dodging it.
"""

from __future__ import annotations

import io
import json
import shutil
import struct
import subprocess
import wave
import zlib
from pathlib import Path
from typing import Any


def probe_wav(path: Path) -> dict[str, Any]:
    """Fully decode a WAV header; problems is empty iff the file is sound."""
    problems: list[str] = []
    details: dict[str, Any] = {"kind": "wav"}
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.getnframes()
            details.update({
                "channels": channels, "sample_width_bytes": width,
                "sample_rate_hz": rate, "frame_count": frames,
            })
            if channels < 1 or width < 1 or rate < 1:
                problems.append(f"{path}: WAV has non-positive audio params (channels={channels}, width={width}, rate={rate})")
            if frames < 1:
                problems.append(f"{path}: WAV contains no audio frames")
            else:
                details["duration_s"] = round(frames / rate, 3)
            # Prove the frames are actually readable, not just header claims.
            try:
                data = handle.readframes(frames)
                if len(data) != frames * channels * width:
                    problems.append(f"{path}: WAV frame data is truncated ({len(data)} bytes, expected {frames * channels * width})")
            except (wave.Error, EOFError) as exc:
                problems.append(f"{path}: WAV frames unreadable: {exc}")
    except (OSError, wave.Error, EOFError) as exc:
        problems.append(f"{path}: not a decodable WAV file: {exc}")
    return {"kind": "wav", "probed": True, "problems": problems, "details": details}


def probe_mp4(path: Path) -> dict[str, Any]:
    """Container-level check: a plausible `ftyp` box at the head of the file.

    Deliberately NOT a decode check — stdlib cannot decode video. A pass
    means ISO-BMFF container bytes, nothing about dimensions, duration, or
    audio presence.
    """
    problems: list[str] = []
    details: dict[str, Any] = {"kind": "mp4", "level": "container_only"}
    try:
        header = path.read_bytes()[:32]
    except OSError as exc:
        return {"kind": "mp4", "probed": True, "problems": [f"{path}: unreadable: {exc}"], "details": details}
    if len(header) < 12:
        problems.append(f"{path}: too short to be an MP4 container ({len(header)} bytes)")
    else:
        size = struct.unpack(">I", header[0:4])[0]
        box = header[4:8]
        brand = header[8:12]
        details.update({"box_size": size, "box": box.decode("ascii", "replace"), "major_brand": brand.decode("ascii", "replace")})
        if box != b"ftyp":
            problems.append(f"{path}: no ftyp box at offset 0 (found {box!r}); not an MP4 container")
        elif size < 8 or size % 4 != 0:
            problems.append(f"{path}: implausible ftyp box size {size}")
        elif not all(32 <= byte < 127 for byte in brand):
            problems.append(f"{path}: non-ASCII major brand {brand!r}")
    return {"kind": "mp4", "probed": True, "problems": problems, "details": details}


def probe_png(path: Path) -> dict[str, Any]:
    """Signature + IHDR parse with CRC verification."""
    problems: list[str] = []
    details: dict[str, Any] = {"kind": "png"}
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {"kind": "png", "probed": True, "problems": [f"{path}: unreadable: {exc}"], "details": details}
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        problems.append(f"{path}: bad PNG signature")
        return {"kind": "png", "probed": True, "problems": problems, "details": details}
    if len(data) < 33 or data[12:16] != b"IHDR":
        problems.append(f"{path}: missing IHDR chunk")
        return {"kind": "png", "probed": True, "problems": problems, "details": details}
    length = struct.unpack(">I", data[8:12])[0]
    if length != 13:
        problems.append(f"{path}: malformed IHDR length {length}")
        return {"kind": "png", "probed": True, "problems": problems, "details": details}
    chunk = data[12:12 + 4 + 13 + 4]
    stored_crc = struct.unpack(">I", chunk[-4:])[0]
    if zlib.crc32(chunk[:-4]) & 0xFFFFFFFF != stored_crc:
        problems.append(f"{path}: IHDR CRC mismatch")
    width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    details.update({"width": width, "height": height, "bit_depth": bit_depth, "color_type": color_type})
    if width < 1 or height < 1 or width > 16384 or height > 16384:
        problems.append(f"{path}: implausible PNG dimensions {width}x{height}")
    return {"kind": "png", "probed": True, "problems": problems, "details": details}


def probe_file(path: Path) -> dict[str, Any]:
    """Dispatch by suffix; unknown suffixes are unprobed (never a failure)."""
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return probe_wav(path)
    if suffix == ".mp4":
        return probe_mp4(path)
    if suffix == ".png":
        return probe_png(path)
    return {"kind": suffix.lstrip(".") or "unknown", "probed": False, "problems": [], "details": {}}


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def probe_mp4_decode(path: Path, *, timeout_s: float = 30.0) -> dict[str, Any]:
    """Decode-level MP4 probe via ffprobe (dimensions, duration, audio).

    Fail-open by design: without ffprobe nothing is learned (`probed` False,
    no problems — the container check in probe_mp4 remains the gate). With
    ffprobe, an undecodable file, a missing video stream, implausible
    dimensions, zero duration, or a missing audio track (voice-first renders
    are always narrated) are all problems.
    """
    if not ffprobe_available():
        return {"probed": False, "problems": [], "details": {"reason": "ffprobe unavailable"}}
    try:
        completed = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=timeout_s, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"probed": True, "problems": [f"{path}: ffprobe failed: {exc}"], "details": {}}
    if completed.returncode != 0:
        tail = (completed.stderr or "").strip().splitlines()[-1:]
        return {
            "probed": True,
            "problems": [f"{path}: ffprobe cannot decode this file" + (f": {tail[0]}" if tail else "")],
            "details": {},
        }
    try:
        document = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        return {"probed": True, "problems": [f"{path}: ffprobe output unreadable: {exc}"], "details": {}}
    problems: list[str] = []
    details: dict[str, Any] = {}
    streams = document.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not videos:
        problems.append(f"{path}: decodes, but has no video stream")
    else:
        width = videos[0].get("width", 0) or 0
        height = videos[0].get("height", 0) or 0
        details.update({"width": width, "height": height, "video_codec": videos[0].get("codec_name")})
        if width < 1 or height < 1 or width > 16384 or height > 16384:
            problems.append(f"{path}: implausible decoded dimensions {width}x{height}")
    duration = document.get("format", {}).get("duration")
    try:
        duration_s = float(duration) if duration is not None else 0.0
    except (TypeError, ValueError):
        duration_s = 0.0
    details["duration_s"] = round(duration_s, 3)
    if duration_s <= 0:
        problems.append(f"{path}: decoded duration is not positive ({duration_s})")
    details["has_audio"] = bool(audios)
    if audios:
        details["audio_codec"] = audios[0].get("codec_name")
    else:
        problems.append(f"{path}: no audio stream (voice-first renders are always narrated)")
    return {"probed": True, "problems": problems, "details": details}


def encode_minimal_wav(*, sample_rate_hz: int = 22050, duration_s: float = 0.1) -> bytes:
    """Structurally valid silent WAV bytes for fixtures (content-synthetic)."""
    frames = max(1, int(sample_rate_hz * duration_s))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate_hz)
        handle.writeframes(b"\x00" * frames * 2)
    return buffer.getvalue()


def encode_minimal_mp4(*, major_brand: bytes = b"isom") -> bytes:
    """Container-plausible MP4 bytes for fixtures: ftyp + free boxes.

    Decodes as a container, carries no samples — content-synthetic, like
    every other fixture in this repo, but no longer magic-agnostic.
    """
    ftyp = struct.pack(">I4s4sI4s", 20, b"ftyp", major_brand, 0, b"isom")
    free = struct.pack(">I4s", 8, b"free")
    return ftyp + free + b"\x00" * 64


def encode_minimal_png(*, width: int = 1, height: int = 1) -> bytes:
    """Structurally valid 1x1 (default) truecolor PNG bytes for fixtures."""
    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        body = chunk_type + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"\x00" + b"\x00" * width * height * 3
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
