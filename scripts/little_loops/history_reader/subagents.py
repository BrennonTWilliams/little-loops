"""Subagent-run queries (ENH-2775 split from the former flat
``history_reader.py``).

Backing table: ``subagent_runs`` (ENH-2505) — direct spawn tree, oscillation
(re-spawn) detection, and per-parent duration budgets.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from little_loops.history_reader._base import (
    DEFAULT_DB_PATH,
    _connect_readonly,
    _row_to_dataclass,
    logger,
)
from little_loops.history_reader.models import SubagentRun

__all__ = [
    "subagent_budget",
    "subagent_retries",
    "subagent_tree",
]


def subagent_tree(
    session_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SubagentRun]:
    """Direct ``agent_id`` spawns for a parent session (ENH-2505).

    Recursion into grandchildren is not performed here — a subagent's own
    spawns live in its nested transcript
    (``agent_transcript_path``), not a joinable ``sessions`` row, so walking
    the full tree requires re-parsing that transcript rather than a SQL join.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT ts, parent_session_id, agent_id, agent_type, agent_transcript_path, "
            "started_at, ended_at, status FROM subagent_runs "
            "WHERE parent_session_id = ? ORDER BY started_at",
            (session_id,),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: subagent_tree query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, SubagentRun) for row in rows]


def subagent_retries(
    agent_type: str,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Per-parent re-spawn counts for *agent_type* — the "oscillation" signal (ENH-2505).

    Returns one dict per ``parent_session_id`` with a ``spawn_count`` for that
    agent type, restricted to parents that spawned it more than once.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT parent_session_id, COUNT(*) AS spawn_count FROM subagent_runs "
            "WHERE agent_type = ? "
        )
        params: list[Any] = [agent_type]
        if since is not None:
            sql += "AND started_at >= ? "
            params.append(since)
        sql += "GROUP BY parent_session_id HAVING COUNT(*) > 1 ORDER BY spawn_count DESC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: subagent_retries query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [dict(row) for row in rows]


def subagent_budget(
    session_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> dict | None:
    """Total subagent-run duration rollup for a parent session — the "burn budget" signal (ENH-2505).

    Returns ``None`` when the DB is absent or no subagent rows exist for
    *session_id*. ``total_duration_s`` only accounts for rows with both
    ``started_at`` and ``ended_at`` set; still-running or malformed rows are
    excluded from the sum but counted in ``spawn_count``.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS spawn_count, "
            "SUM(CASE WHEN started_at IS NOT NULL AND ended_at IS NOT NULL "
            "THEN (julianday(ended_at) - julianday(started_at)) * 86400 ELSE 0 END) "
            "AS total_duration_s "
            "FROM subagent_runs WHERE parent_session_id = ?",
            (session_id,),
        ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: subagent_budget query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None or not row["spawn_count"]:
        return None
    return {
        "spawn_count": row["spawn_count"],
        "total_duration_s": row["total_duration_s"] or 0.0,
    }
