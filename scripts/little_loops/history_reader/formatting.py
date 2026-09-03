"""``ll-grep``/``ll-expand``/``ll-describe`` message-search formatting layer
(ENH-2775 split from the former flat ``history_reader.py``).

Backing tables: ``message_events``, ``summary_spans``, ``summary_nodes``
(FEAT-1712's LCM-style compaction DAG) — regex search over raw messages with
covering-summary-node context, plus expand/describe helpers for one node.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from little_loops.history_reader._base import DEFAULT_DB_PATH, _connect_readonly, logger
from little_loops.history_reader.models import GrepResult, SummaryNode

__all__ = [
    "ll_describe",
    "ll_expand",
    "ll_grep",
]


def ll_grep(
    pattern: str,
    *,
    summary_id: int | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[GrepResult]:
    """Regex search over message_events, with covering summary node context.

    Each result includes the summary_id and summary_kind of the leaf node covering the
    matched message (or None/None for messages not yet compacted). If *summary_id* is
    provided, restrict the search to messages covered by that specific node.

    When *summary_id* is a condensed node (kind='condensed'), uses a recursive CTE to
    walk the N-level DAG (condensed → … → leaves via parent_id → message_events via
    summary_spans) so that messages under all descendant leaves are searched regardless
    of condensation depth.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []

    def _regexp(pat: str, val: str | None) -> bool:
        try:
            return bool(re.search(pat, val or "", re.IGNORECASE))
        except re.error:
            return False

    try:
        conn.create_function("regexp_match", 2, _regexp)
        if summary_id is not None:
            # Recursive CTE walks the full N-level DAG from the starting node
            # through all descendants, terminating at leaf nodes that have
            # summary_spans entries.  Works uniformly for both kind='leaf'
            # (CTE = 1 row) and kind='condensed' at any depth.
            rows = conn.execute(
                "WITH RECURSIVE descendants AS ("
                "  SELECT id, kind FROM summary_nodes WHERE id = ?1"
                "  UNION ALL"
                "  SELECT sn.id, sn.kind"
                "  FROM summary_nodes sn"
                "  JOIN descendants d ON sn.parent_id = d.id"
                ")"
                "SELECT me.id, me.session_id, me.ts, me.content,"
                " sn.id AS summary_id, sn.kind AS summary_kind"
                " FROM message_events me"
                " JOIN summary_spans ss ON ss.message_event_id = me.id"
                " JOIN descendants leaf ON leaf.id = ss.summary_id"
                " JOIN summary_nodes sn ON sn.id = leaf.id"
                " WHERE regexp_match(?2, me.content)"
                " ORDER BY me.ts, me.id LIMIT ?3",
                (summary_id, pattern, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT me.id, me.session_id, me.ts, me.content,"
                " sn.id AS summary_id, sn.kind AS summary_kind"
                " FROM message_events me"
                " LEFT JOIN summary_spans ss ON ss.message_event_id = me.id"
                " LEFT JOIN summary_nodes sn ON sn.id = ss.summary_id"
                " WHERE regexp_match(?, me.content)"
                " ORDER BY me.ts, me.id LIMIT ?",
                (pattern, limit),
            ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: ll_grep query failed", exc_info=True)
        return []
    finally:
        conn.close()

    return [
        GrepResult(
            message_event_id=row["id"],
            session_id=row["session_id"],
            ts=row["ts"],
            content=row["content"] or "",
            summary_id=row["summary_id"],
            summary_kind=row["summary_kind"],
        )
        for row in rows
    ]


def ll_expand(
    summary_id: int,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Return the message_events covered by *summary_id*.

    Uses a recursive CTE to walk the N-level summary DAG from the starting
    node through all descendants, terminating at leaf nodes that have
    ``summary_spans`` entries.  Works uniformly for both ``kind='leaf'``
    (CTE = 1 row, direct span join) and ``kind='condensed'`` at any
    condensation depth (CTE descends through intermediate condensed nodes
    to reach the leaves).

    Returns dicts with keys ``id``, ``session_id``, ``ts``, ``content``.
    Empty list when the summary node does not exist or has no spans.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        # Recursive CTE handles leaf and condensed nodes uniformly at any depth.
        # For a leaf node, descendants = {itself} and the summary_spans join is direct.
        # For a condensed node, descendants = {condensed, children, grandchildren, …}
        # and the summary_spans join only matches the leaf-descendant rows.
        rows = conn.execute(
            "WITH RECURSIVE descendants AS ("
            "  SELECT id, kind FROM summary_nodes WHERE id = ?1"
            "  UNION ALL"
            "  SELECT sn.id, sn.kind"
            "  FROM summary_nodes sn"
            "  JOIN descendants d ON sn.parent_id = d.id"
            ")"
            "SELECT me.id, me.session_id, me.ts, me.content"
            " FROM message_events me"
            " JOIN summary_spans ss ON ss.message_event_id = me.id"
            " JOIN descendants leaf ON leaf.id = ss.summary_id"
            " ORDER BY me.ts, me.id",
            (summary_id,),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: ll_expand query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [dict(row) for row in rows]


def ll_describe(
    node_id: int,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> SummaryNode | None:
    """Return metadata for a summary_nodes row.

    Returns ``None`` when the node does not exist or the database is unavailable.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT id, kind, content, tokens, parent_id, session_id,"
            " ts_start, ts_end, created_at, level"
            " FROM summary_nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: ll_describe query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None:
        return None
    return SummaryNode(
        id=row["id"],
        kind=row["kind"],
        content=row["content"],
        tokens=row["tokens"],
        parent_id=row["parent_id"],
        session_id=row["session_id"],
        ts_start=row["ts_start"],
        ts_end=row["ts_end"],
        created_at=row["created_at"],
        level=row["level"],
    )
