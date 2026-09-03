"""Session metadata, issue events, issue effort/velocity, lifecycle/handoff,
and worktree-summary queries (ENH-2775 split from the former flat
``history_reader.py``).

Backing tables/views: ``issue_events``, the ``issue_sessions`` VIEW,
``session_lifecycle_events``, ``user_corrections``/``tool_events``/
``file_events`` (read by ``lookup_session_metadata``'s composite query), and
``message_events``/``assistant_messages`` (``conversation_turns``).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from little_loops.history_reader._base import (
    DEFAULT_DB_PATH,
    _connect_readonly,
    _row_to_dataclass,
    logger,
    normalize_issue_id,
)
from little_loops.history_reader.models import IssueEvent, LifecycleEvent, SessionRef

__all__ = [
    "conversation_turns",
    "find_session_for_issue_transition",
    "handoff_frequency",
    "issue_effort",
    "lookup_session_metadata",
    "recent_issue_velocity",
    "recent_lifecycle_events",
    "related_issue_events",
    "sessions_for_issue",
    "worktree_summary",
]


def related_issue_events(
    issue_id: str,
    *,
    session_id: str | None = None,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[IssueEvent]:
    """Return issue events for *issue_id*, ordered by most recent first.

    When *session_id* is given, only events recorded with that exact
    authoritative session ID are returned (ENH-2462); the default returns all
    rows regardless of session.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, issue_id, transition, discovered_by, issue_type, priority, session_id "
            "FROM issue_events WHERE issue_num = ? "
        )
        params: list[Any] = [normalize_issue_id(issue_id)]
        if session_id is not None:
            sql += "AND session_id = ? "
            params.append(session_id)
        sql += "ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: related_issue_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, IssueEvent) for row in rows]


def find_session_for_issue_transition(
    issue_id: str,
    transition: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> str | None:
    """Return the session_id recorded for an exact issue transition (ENH-2462).

    Reads the authoritative ``issue_events.session_id`` column; returns
    ``None`` for legacy rows written before the v16 migration, when the
    transition was emitted outside a session-known context, or when no such
    transition exists.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT session_id FROM issue_events "
            "WHERE issue_num = ? AND transition = ? AND session_id IS NOT NULL "
            "ORDER BY ts DESC LIMIT 1",
            (normalize_issue_id(issue_id), transition),
        ).fetchone()
    except sqlite3.Error:
        logger.warning(
            "history_reader: find_session_for_issue_transition query failed", exc_info=True
        )
        return None
    finally:
        conn.close()
    return row["session_id"] if row else None


def recent_lifecycle_events(
    *,
    event: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[LifecycleEvent]:
    """Return recent session-lifecycle events, newest first, optionally filtered (ENH-2495)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT id, ts, session_id, event, detail, head_sha, branch "
            "FROM session_lifecycle_events "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if event is not None:
            clauses.append("event = ?")
            params.append(event)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_lifecycle_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    results = []
    for row in rows:
        kwargs = dict(row)
        detail_raw = kwargs.get("detail")
        kwargs["detail"] = json.loads(detail_raw) if detail_raw else None
        results.append(LifecycleEvent(**kwargs))
    return results


def handoff_frequency(
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> int:
    """Count of ``handoff_needed`` lifecycle events, optionally since a timestamp (ENH-2495)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return 0
    try:
        sql = "SELECT COUNT(*) FROM session_lifecycle_events WHERE event = 'handoff_needed'"
        params: list[Any] = []
        if since is not None:
            sql += " AND ts >= ?"
            params.append(since)
        row = conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: handoff_frequency query failed", exc_info=True)
        return 0
    finally:
        conn.close()
    return int(row[0]) if row else 0


def worktree_summary(
    *,
    issue_id: str | None = None,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Per-issue worktree op counts from ``worktree_*`` lifecycle events (ENH-2509).

    Returns one dict per issue_id with ``created``/``merged``/``deleted`` counts,
    derived from ``json_extract(detail, '$.issue_id')``. Rows with no ``issue_id``
    in ``detail`` (e.g. orphan-sweep cleanups) group under ``issue_id=None``.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT json_extract(detail, '$.issue_id') AS issue_id, "
            "COUNT(*) FILTER (WHERE event = 'worktree_create') AS created, "
            "COUNT(*) FILTER (WHERE event = 'worktree_merge') AS merged, "
            "COUNT(*) FILTER (WHERE event = 'worktree_delete') AS deleted "
            "FROM session_lifecycle_events WHERE event LIKE 'worktree_%' "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if issue_id is not None:
            clauses.append("json_extract(detail, '$.issue_id') = ?")
            params.append(issue_id)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if clauses:
            sql += "AND " + " AND ".join(clauses) + " "
        sql += "GROUP BY 1 ORDER BY 1"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: worktree_summary query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [dict(row) for row in rows]


def sessions_for_issue(
    issue_id: str,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SessionRef]:
    """Return sessions that co-occurred with *issue_id*'s active period.

    Queries the ``issue_sessions`` VIEW. As of the v16 migration (ENH-2462)
    the view prefers exact joins on the authoritative
    ``issue_events.session_id`` column and falls back to the deprecated
    timestamp-overlap inference (``legacy_issue_sessions_ts_overlap``) only
    for issues with no authoritative rows. Live-emitted rows (from
    ``issue_lifecycle.py``'s 6 emit sites) populate ``captured_at`` and
    ``session_id`` directly; no prior ``backfill`` pass is needed for issues
    processed after ENH-1839.

    Returns an empty list when the view is absent (pre-v5 schema), the issue
    has no recorded sessions, or the database is unavailable.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT issue_id, session_id, jsonl_path, first_message_ts, last_message_ts "
            "FROM issue_sessions WHERE issue_num = ? "
            "ORDER BY first_message_ts DESC LIMIT ?",
            (normalize_issue_id(issue_id), limit),
        ).fetchall()
    except sqlite3.Error:
        logger.error(
            "history_reader: sessions_for_issue query failed (possible schema drift)",
            exc_info=True,
        )
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, SessionRef) for row in rows]


def issue_effort(
    issue_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> dict | None:
    """Per-issue effort: session_count and cycle_time_days (first→last session).

    Returns None when the DB is absent, no sessions exist for the issue, or a
    query error occurs. Does NOT reuse sessions_for_issue() to avoid the LIMIT=20
    cap which would produce incorrect cycle_time_days for issues with >20 sessions.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS session_count, MIN(first_message_ts) AS first_ts, "
            "MAX(last_message_ts) AS last_ts FROM issue_sessions WHERE issue_num = ?",
            (normalize_issue_id(issue_id),),
        ).fetchone()
    except sqlite3.Error:
        logger.error(
            "history_reader: issue_effort query failed (possible schema drift)",
            exc_info=True,
        )
        return None
    finally:
        conn.close()
    if row is None or row["session_count"] == 0:
        return None
    cycle: float | None = None
    if row["first_ts"] and row["last_ts"]:
        delta = datetime.fromisoformat(row["last_ts"]) - datetime.fromisoformat(row["first_ts"])
        cycle = delta.total_seconds() / 86400
    return {"session_count": row["session_count"], "cycle_time_days": cycle}


def recent_issue_velocity(
    limit: int = 10,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Effort data for recently completed issues; empty list when DB has no data.

    Queries issue_events for recently-completed issues (non-NULL completed_at),
    then calls issue_effort() for each to produce per-issue effort dicts.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT issue_id, issue_num, MAX(completed_at) AS completed_at FROM issue_events "
            "WHERE completed_at IS NOT NULL "
            "GROUP BY COALESCE(issue_num, issue_id) "
            "ORDER BY completed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_issue_velocity query failed", exc_info=True)
        return []
    finally:
        conn.close()
    result = []
    for row in rows:
        effort = issue_effort(row["issue_id"], db=db)
        if effort is not None:
            result.append({"issue_id": row["issue_id"], **effort})
    return result


def lookup_session_metadata(
    session_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> dict:
    """Return session-quality metadata dict for a session ID (ENH-1943).

    Returns:
        dict with keys: ``has_corrections`` (bool), ``issue_outcome`` (str|None),
        ``tool_count`` (int), ``files_modified`` (int), ``loop_outcome`` (str|None).

        ``loop_outcome`` is always ``None`` until ``loop_events`` gains a
        ``session_id`` column (schema change out of scope).

    Returns empty dict ``{}`` when DB is missing, empty, or lacks relevant tables.
    """
    db_path = Path(db)
    if not db_path.exists():
        return {}
    conn = _connect_readonly(db_path)
    if conn is None:
        return {}
    try:
        # has_corrections: direct query on user_corrections
        row = conn.execute(
            "SELECT COUNT(*) > 0 AS has_corrections FROM user_corrections WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        has_corrections = bool(row["has_corrections"]) if row else False

        # issue_outcome: JOIN through issue_sessions VIEW (issue_events has no
        # session_id column; migration v5 bridges via the VIEW)
        row = conn.execute(
            "SELECT ie.transition "
            "FROM issue_sessions is2 "
            "JOIN issue_events ie ON is2.issue_id = ie.issue_id "
            "WHERE is2.session_id = ? AND ie.transition = 'done' "
            "ORDER BY ie.ts DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        issue_outcome: str | None = row["transition"] if row else None

        # tool_count: direct query on tool_events
        row = conn.execute(
            "SELECT COUNT(*) AS tool_count FROM tool_events WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        tool_count: int = row["tool_count"] if row else 0

        # files_modified: direct query on file_events; op values include both
        # hook-written tool names ('Write') and lowercase variants ('write', 'create')
        row = conn.execute(
            "SELECT COUNT(*) AS files_modified FROM file_events "
            "WHERE session_id = ? AND op IN ('write', 'create', 'Write')",
            (session_id,),
        ).fetchone()
        files_modified: int = row["files_modified"] if row else 0

        # loop_outcome: loop_events has no session_id column; always None
        loop_outcome: None = None

    except sqlite3.Error:
        logger.warning("history_reader: lookup_session_metadata query failed", exc_info=True)
        return {}
    finally:
        conn.close()

    return {
        "has_corrections": has_corrections,
        "issue_outcome": issue_outcome,
        "tool_count": tool_count,
        "files_modified": files_modified,
        "loop_outcome": loop_outcome,
    }


def conversation_turns(
    db_path: Path | str,
    since: datetime | None = None,
    context_window: int = 3,
) -> list[list[tuple[str, str]]]:
    """Return conversation turn-pair windows from ``history.db`` (ENH-1942).

    Queries ``message_events`` and ``assistant_messages``, pairs user messages
    with their assistant responses via temporal adjacency (same algorithm as
    ``_extract_turn_pairs()`` in ``user_messages.py``), and groups them into
    sliding windows of *context_window* turn-pairs each.

    Returns ``[]`` when the database is missing, empty, predates schema v11
    (no ``assistant_messages`` table), or when no turn-pairs match the *since*
    filter. Callers should fall back to JSONL parsing in that case.

    Args:
        db_path: Path to ``history.db``.
        since: Only include turns where the user message timestamp is >= this value.
        context_window: Number of (user, assistant) turn-pairs per output window.

    Returns:
        List of conversation windows; each window is a ``list[tuple[str, str]]``
        alternating between ``("user", text)`` and ``("assistant", text)``.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        # Check that assistant_messages table exists (schema >= v11)
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM sqlite_master "
            "WHERE type = 'table' AND name = 'assistant_messages'"
        ).fetchone()
        if not row or row["n"] == 0:
            return []

        # Pair each user message with assistant messages between it and the
        # NEXT user message (temporal-adjacency, matching _extract_turn_pairs).
        # The subquery finds the next user message timestamp per session;
        # COALESCE defaults to a far-future sentinel for the last message.
        base_sql = (
            "SELECT u.session_id, u.ts AS user_ts, u.content AS user_text, "
            "a.content AS assistant_text "
            "FROM message_events u "
            "JOIN assistant_messages a ON a.session_id = u.session_id "
            "AND a.ts > u.ts "
            "AND a.ts < COALESCE("
            "  (SELECT MIN(u2.ts) FROM message_events u2 "
            "   WHERE u2.session_id = u.session_id AND u2.ts > u.ts), "
            "  '9999-12-31'"
            ") "
        )
        params: list[Any] = []
        if since is not None:
            base_sql += "WHERE u.ts >= ? "
            params.append(since.strftime("%Y-%m-%dT%H:%M:%SZ"))
        base_sql += "ORDER BY u.session_id, u.ts, a.ts"

        rows = conn.execute(base_sql, params or ()).fetchall()

        if not rows:
            return []

        # Group assistant texts by user message.
        # The SQL already only includes assistant messages between consecutive
        # user messages, so simple grouping by (session_id, user_ts) suffices.
        turn_pairs: list[tuple[str, str]] = []
        current_key: tuple[str, str] | None = None
        current_user: str = ""
        assistant_texts: list[str] = []

        for row_ in rows:
            key = (row_["session_id"], row_["user_ts"])
            if key != current_key:
                if current_key is not None and assistant_texts:
                    turn_pairs.append((current_user, "\n\n".join(assistant_texts)))
                current_key = key
                current_user = row_["user_text"]
                assistant_texts = []
            assistant_texts.append(row_["assistant_text"])

        # Flush the final turn
        if current_key is not None and assistant_texts:
            turn_pairs.append((current_user, "\n\n".join(assistant_texts)))

        # Emit sliding windows of context_window turn-pairs
        windows: list[list[tuple[str, str]]] = []
        n = len(turn_pairs)
        if n == 0:
            return []
        for i in range(max(1, n - context_window + 1)):
            window_pairs = turn_pairs[i : i + context_window]
            window: list[tuple[str, str]] = []
            for user_text, assistant_text in window_pairs:
                window.append(("user", user_text))
                window.append(("assistant", assistant_text))
            windows.append(window)

        return windows

    except sqlite3.Error:
        logger.warning("history_reader: conversation_turns query failed", exc_info=True)
        return []
    finally:
        conn.close()
