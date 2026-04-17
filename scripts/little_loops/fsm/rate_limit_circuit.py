"""Shared circuit-breaker state file for cross-worktree 429 coordination.

Provides :class:`RateLimitCircuit`: a file-backed record of the most recent
rate-limit event (observed backoff window and attempt count) that parallel
worktrees can read to avoid hammering an already-rate-limited endpoint.

The state file is a small JSON document guarded by an ``fcntl.flock``-held
sidecar lock, written atomically via ``tempfile.mkstemp`` + ``os.replace``.
Detection of a 429 stays in the executor
(see :func:`little_loops.issue_lifecycle.classify_failure`); this module only
owns the backoff-write side.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STALE_THRESHOLD_SECONDS = 3600.0


class RateLimitCircuit:
    """File-backed circuit-breaker for shared 429 backoff coordination.

    Constructor accepts an absolute path to the state file
    (e.g. ``.loops/tmp/rate-limit-circuit.json``). The default path
    source-of-truth is
    :attr:`little_loops.config.automation.RateLimitsConfig.circuit_breaker_path`;
    this module does not import config.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def record_rate_limit(self, backoff_seconds: float) -> None:
        """Record a rate-limit event with the observed backoff window.

        Increments ``attempts``, advances ``last_seen`` to now, and extends
        ``estimated_recovery_at`` monotonically so concurrent observers do
        not shrink an in-flight backoff window.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "w") as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            now = time.time()
            proposed_recovery = now + float(backoff_seconds)
            current = self._read_unlocked()
            if current is None:
                record = {
                    "first_seen": now,
                    "last_seen": now,
                    "attempts": 1,
                    "estimated_recovery_at": proposed_recovery,
                }
            else:
                record = {
                    "first_seen": current.get("first_seen", now),
                    "last_seen": now,
                    "attempts": int(current.get("attempts", 0)) + 1,
                    "estimated_recovery_at": max(
                        float(current.get("estimated_recovery_at", 0.0)),
                        proposed_recovery,
                    ),
                }
            self._write_atomic(record)

    def get_estimated_recovery(self) -> float | None:
        """Return epoch timestamp of estimated recovery, or None if stale/absent."""
        if self.is_stale():
            return None
        current = self._read_unlocked()
        if current is None:
            return None
        recovery = current.get("estimated_recovery_at")
        return float(recovery) if recovery is not None else None

    def is_stale(self) -> bool:
        """True if the stored entry's ``last_seen`` is >1h ago (or file absent)."""
        current = self._read_unlocked()
        if current is None:
            return False
        last_seen = current.get("last_seen")
        if last_seen is None:
            return True
        return (time.time() - float(last_seen)) > STALE_THRESHOLD_SECONDS

    def clear(self) -> None:
        """Remove the state file. No-op if already absent."""
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _read_unlocked(self) -> dict[str, Any] | None:
        """Read the state file, treating absent/corrupt as None."""
        if not self.path.exists():
            return None
        try:
            raw = self.path.read_text()
        except FileNotFoundError:
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Corrupted circuit file %s; treating as absent", self.path)
            return None
        return data if isinstance(data, dict) else None

    def _write_atomic(self, data: dict[str, Any]) -> None:
        """Atomically write ``data`` as JSON to ``self.path``."""
        payload = json.dumps(data, indent=2)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                f.write(payload)
            os.replace(tmp_path, self.path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise
