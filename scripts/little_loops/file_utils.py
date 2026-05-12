"""Shared file I/O utilities for little-loops."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write *content* to *path* atomically using tempfile + os.replace.

    Writes to a sibling temp file in the same directory (same filesystem),
    then renames it over the target so readers never observe a partial file.
    """
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, data: Any) -> None:
    """Atomically write *data* as JSON to *path* (Python port of ``atomic_write_json``).

    Mirrors ``hooks/scripts/lib/common.sh:atomic_write_json``: ensures the parent
    directory exists, validates the serialized JSON via a ``json.loads`` round-trip
    (the bash version uses ``jq empty``), then writes to a sibling tempfile and
    ``os.replace``-renames it over the target.

    Raises:
        ValueError: if the serialized payload fails the round-trip validation
            (e.g. NaN/Infinity rejected by ``json.loads``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False makes json.dumps raise ValueError on NaN/Infinity, matching
    # bash `jq empty`'s rejection of non-strict-JSON values.
    payload = json.dumps(data, indent=2, allow_nan=False)
    # Defensive round-trip: catches any divergence between dumps output and
    # strict-mode parse expectations (parity with `jq empty` validation).
    try:
        json.loads(payload)
    except json.JSONDecodeError as exc:  # pragma: no cover — defense in depth
        raise ValueError(f"atomic_write_json round-trip validation failed: {exc}") from exc
    atomic_write(path, payload)


@contextmanager
def acquire_lock(path: Path, timeout: float = 10.0) -> Generator[None, None, None]:
    """Acquire an exclusive advisory lock on *path*, polled up to *timeout* seconds.

    Python port of ``hooks/scripts/lib/common.sh:acquire_lock``. Uses
    ``fcntl.flock(LOCK_EX | LOCK_NB)`` in a 0.05s polling loop bounded by
    *timeout*; the lock is released when the file descriptor is closed on
    context-manager exit (no explicit ``release_lock`` needed).

    The bash adapter calls this with ``timeout=3.0`` from precompact and falls
    back to a best-effort unlocked write on ``TimeoutError`` to preserve the
    bash caller's existing semantics.

    Raises:
        TimeoutError: if the lock cannot be acquired within *timeout* seconds.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    poll_interval = 0.05
    with open(path, "w") as lock_fd:
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"acquire_lock: could not acquire {path} within {timeout}s"
                    ) from None
                time.sleep(poll_interval)
        try:
            yield
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
