"""File-backed batch-submission tracker for the Message Batches API request path.

FEAT-2710 (EPIC-2456 F1). Mirrors :class:`~little_loops.fsm.rate_limit_circuit.RateLimitCircuit`'s
atomic file-write mechanics (``tempfile.mkstemp`` + ``os.replace``) but tracks a
different concern: the outstanding ``batch_id`` for an in-flight
``client.messages.batches.create()`` submission, persisted under
``${context.run_dir}/batch_id.json`` so an interrupted run resumes polling the
existing batch instead of double-submitting.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BatchTracker:
    """Tracks one outstanding Message Batches API submission for a run.

    Constructor accepts an absolute path to the state file, conventionally
    ``Path(run_dir) / "batch_id.json"`` (mirrors how
    :class:`~little_loops.fsm.persistence.PersistentExecutor` locates
    ``usage.jsonl``/``messages.jsonl`` under ``run_dir``).
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def record_submitted(self, batch_id: str, custom_id: str) -> None:
        """Record a newly-submitted batch. Overwrites any prior record."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_atomic(
            {
                "batch_id": batch_id,
                "custom_id": custom_id,
                "submitted_at": time.time(),
            }
        )

    def get_batch_id(self) -> str | None:
        """Return the outstanding batch_id to resume polling, or None if absent."""
        current = self._read()
        if current is None:
            return None
        batch_id = current.get("batch_id")
        return str(batch_id) if batch_id is not None else None

    def get_custom_id(self) -> str | None:
        """Return the outstanding custom_id (for matching batch results), or None if absent."""
        current = self._read()
        if current is None:
            return None
        custom_id = current.get("custom_id")
        return str(custom_id) if custom_id is not None else None

    def clear(self) -> None:
        """Remove the state file once the batch has been retrieved. No-op if absent."""
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _read(self) -> dict[str, Any] | None:
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
            logger.warning("Corrupted batch tracker file %s; treating as absent", self.path)
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
