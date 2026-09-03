"""Hook execution telemetry (ENH-2506) (ENH-2775 split from the former flat
``history_reader.py``).

Backing table: ``hook_events`` — one row per hook fire. ``HookEvent`` is
defined here rather than in ``models.py`` because it (like the other
region-local dataclasses in this split) is used only within its own domain,
mirroring how ``session_store/writers.py`` keeps its domain-local
dataclasses (``HookEventCompletion``, ``SkillEventCompletion``, ...)
alongside the functions that build them rather than in a shared file.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from little_loops.history_reader._base import (
    DEFAULT_DB_PATH,
    _connect_readonly,
    _row_to_dataclass,
    logger,
)

__all__ = [
    "HookEvent",
    "hook_failure_rate",
    "hook_latency_p95",
    "recent_hook_events",
]


@dataclass
class HookEvent:
    """A ``hook_events`` row — one per hook fire (ENH-2506)."""

    ts: str
    session_id: str | None
    event_name: str
    matcher: str | None
    script: str | None
    exit_code: int | None
    duration_ms: int | None
    stderr_preview: str | None
    head_sha: str | None
    branch: str | None


_HOOK_EVENT_COLUMNS = (
    "ts, session_id, event_name, matcher, script, exit_code, duration_ms, "
    "stderr_preview, head_sha, branch"
)


def recent_hook_events(
    event_name: str | None = None,
    *,
    exit_code: int | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[HookEvent]:
    """Return recent hook fires, newest first, optionally filtered (ENH-2506)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = f"SELECT {_HOOK_EVENT_COLUMNS} FROM hook_events "
        clauses: list[str] = []
        params: list[Any] = []
        if event_name is not None:
            clauses.append("event_name = ?")
            params.append(event_name)
        if exit_code is not None:
            clauses.append("exit_code = ?")
            params.append(exit_code)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_hook_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, HookEvent) for row in rows]


def hook_failure_rate(
    event_name: str,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> float | None:
    """Return the fraction of *event_name* fires with a non-zero exit code, or None if no fires."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        sql = (
            "SELECT AVG(CASE WHEN exit_code != 0 THEN 1.0 ELSE 0.0 END) AS failure_rate, "
            "COUNT(*) AS n FROM hook_events WHERE event_name = ? AND exit_code IS NOT NULL"
        )
        params: list[Any] = [event_name]
        if since is not None:
            sql += " AND ts >= ?"
            params.append(since)
        row = conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: hook_failure_rate query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None or not row["n"]:
        return None
    return row["failure_rate"]


def hook_latency_p95(
    event_name: str,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> float | None:
    """Return the p95 ``duration_ms`` for *event_name* fires, or None if no fires (ENH-2506).

    SQLite has no built-in percentile aggregate, so durations are fetched and
    ranked in Python (nearest-rank method) — fine at the scale hook telemetry
    accumulates (thousands, not millions, of rows per project).
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        sql = "SELECT duration_ms FROM hook_events WHERE event_name = ? AND duration_ms IS NOT NULL"
        params: list[Any] = [event_name]
        if since is not None:
            sql += " AND ts >= ?"
            params.append(since)
        sql += " ORDER BY duration_ms ASC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: hook_latency_p95 query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if not rows:
        return None
    durations = [row["duration_ms"] for row in rows]
    idx = max(0, int(len(durations) * 0.95) - 1)
    return float(durations[min(idx, len(durations) - 1)])
