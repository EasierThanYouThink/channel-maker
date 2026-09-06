"""Portable file-lock + atomic-write helpers (Windows / macOS / Linux).

Single home for the two OS-sensitive primitives the engine needs:

- atomic JSON writes with an fsync that works everywhere (directory fsync is
  POSIX-only — skipped on Windows);
- an exclusive file lock for CHANNEL_STATE.json (fcntl on POSIX, msvcrt on
  Windows, with identical timeout semantics).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any


def _fsync_dir(directory: Path) -> None:
    """Best-effort directory fsync. No-op on Windows (os.open dir fails there)."""
    if os.name == "nt":
        return
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def write_json_atomic(path: Path, value: dict[str, Any], *, indent: int | None = None) -> None:
    """Atomically write canonical JSON (sorted keys) with file fsync.

    `indent=None` writes compact canonical bytes (state machine / memory index);
    pass `indent=2` for human-readable pilot/episode-style documents.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if indent is None:
        payload = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    else:
        payload = (json.dumps(value, indent=indent, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            with suppress(OSError):
                os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_bytes_atomic(path: Path, content: bytes) -> None:
    """Atomically write raw bytes (wiki pages) with portable fsync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            with suppress(OSError):
                os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def file_lock(lock_path: Path, timeout_s: float = 10.0) -> Iterator[None]:
    """Exclusive lock file, portable across POSIX (fcntl) and Windows (msvcrt)."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        import msvcrt

        deadline = time.monotonic() + timeout_s
        with lock_path.open("a+b") as handle:
            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            f"timed out waiting for channel state lock {lock_path}"
                        ) from exc
                    time.sleep(0.05)
            try:
                yield
            finally:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
    else:
        import fcntl

        with lock_path.open("a+b") as handle:
            deadline = time.monotonic() + timeout_s
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            f"timed out waiting for channel state lock {lock_path}"
                        ) from exc
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
