"""Latency-budget state for best-effort telemetry against a remote store (FEAT-3535).

Hooks have a 5s timeout and every ``ll-*`` CLI is wrapped by ``cli_event_context``, so a
slow or dead endpoint must not cost every invocation the full wait. Two small files under
the project's ``.ll/`` directory (both named ``*.lock`` so the existing ``.ll/*.lock``
gitignore entry covers them, and neither ever holding a token; the endpoint is keyed by
hash):

- ``libsql-<hash>.unreachable.lock`` -- written on a connect failure or timeout in a
  telemetry path; while it is fresh (TTL 60s) later telemetry writes skip immediately with
  no network attempt and no repeated warning.
- ``libsql-<hash>.verified.lock`` -- the recorded schema version and ``project_id`` (TTL
  300s), so a hook process (one per event) does not re-verify the schema on every write.
  A schema or constraint failure invalidates it.

Explicit reads, ``ll-session migrate`` and ``ll-doctor`` ignore both files. Dropped
telemetry is never buffered or replayed.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.session_store.remote_schema import RemoteState

logger = logging.getLogger(__name__)

UNREACHABLE_TTL_S = 60.0
VERIFIED_TTL_S = 300.0

_WARNED: set[str] = set()
_LOCK = threading.Lock()


_SCOPE = threading.local()


@contextlib.contextmanager
def telemetry_scope() -> Iterator[None]:
    """Mark the ``schema.connect`` calls inside the block as best-effort telemetry.

    The event writers open their connections through the same seam as explicit CLI
    operations, so the seam cannot tell them apart on its own; the writers wrap their
    opens in this scope and a remote backend then applies the telemetry budget.
    """
    prior = getattr(_SCOPE, "active", False)
    _SCOPE.active = True
    try:
        yield
    finally:
        _SCOPE.active = prior


def in_telemetry_scope() -> bool:
    return bool(getattr(_SCOPE, "active", False))


def _now() -> float:
    return time.time()


def endpoint_hash(endpoint: str) -> str:
    """Stable short key for an endpoint. The token is never an input."""
    return hashlib.sha256(endpoint.rstrip("/").encode()).hexdigest()[:12]


def _ll_dir() -> Path | None:
    try:
        from little_loops.paths import resolve_ll_dir

        return resolve_ll_dir()
    except (OSError, ValueError):
        return None


def _path(endpoint: str, kind: str) -> Path | None:
    ll_dir = _ll_dir()
    return None if ll_dir is None else ll_dir / f"libsql-{endpoint_hash(endpoint)}.{kind}.lock"


def _read(path: Path | None) -> dict | None:
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write(path: Path | None, payload: dict) -> None:
    if path is None or not path.parent.is_dir():
        return
    try:
        tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        logger.debug("remote_telemetry: could not write %s", path, exc_info=True)


def _remove(path: Path | None) -> None:
    if path is not None:
        try:
            path.unlink()
        except OSError:
            pass


def mark_unreachable(endpoint: str) -> None:
    _write(_path(endpoint, "unreachable"), {"at": _now()})


def clear_unreachable(endpoint: str) -> None:
    _remove(_path(endpoint, "unreachable"))


def unreachable_active(endpoint: str) -> bool:
    data = _read(_path(endpoint, "unreachable"))
    return bool(data) and _now() - float(data.get("at", 0)) < UNREACHABLE_TTL_S  # type: ignore[union-attr]


def store_verified(endpoint: str, project_id: str | None, state: RemoteState) -> None:
    _write(
        _path(endpoint, "verified"),
        {
            "at": _now(),
            "project_id": project_id,
            "version": state.version,
            "stamped_project_id": state.project_id,
        },
    )


def load_verified(endpoint: str, project_id: str | None) -> RemoteState | None:
    from little_loops.session_store.remote_schema import RemoteState

    data = _read(_path(endpoint, "verified"))
    if not data or data.get("project_id") != project_id:
        return None
    if _now() - float(data.get("at", 0)) >= VERIFIED_TTL_S:
        return None
    try:
        return RemoteState(int(data["version"]), data.get("stamped_project_id"))
    except (KeyError, TypeError, ValueError):
        return None


def invalidate_verified(endpoint: str) -> None:
    _remove(_path(endpoint, "verified"))


def warn_once(key: str, message: str) -> bool:
    """Log *message* at WARNING the first time *key* is seen in this process."""
    with _LOCK:
        if key in _WARNED:
            return False
        _WARNED.add(key)
    logger.warning(message)
    return True


def reset_for_tests() -> None:
    with _LOCK:
        _WARNED.clear()
