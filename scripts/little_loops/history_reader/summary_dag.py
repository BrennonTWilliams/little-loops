"""Summary-DAG retrieval (FEAT-1712) (ENH-2775 split from the former flat
``history_reader.py``).

Backing tables: ``summary_nodes`` joined to the ``issue_sessions`` VIEW —
level-0 condensed per-session summary nodes for an issue.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from little_loops.history_reader._base import DEFAULT_DB_PATH, _connect_readonly, logger
from little_loops.history_reader.models import SummaryNode

__all__ = [
    "condensed_nodes_for_issue",
]


def condensed_nodes_for_issue(
    issue_id: str,
    *,
    limit: int = 3,
    node_char_cap: int = 500,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SummaryNode]:
    """Return level-0 condensed summary_nodes for an issue's sessions (ENH-2231).

    Joins the ``issue_sessions`` VIEW to ``summary_nodes`` filtering for
    ``kind='condensed'`` and ``level=0`` (per-session condensed nodes, one per
    session).  Returns nodes newest-first, limited to *limit*.  Each node's
    ``content`` is truncated to *node_char_cap* characters.

    Returns an empty list when the DB is absent, the issue has no recorded
    sessions, no condensed nodes have been generated, or any query error occurs.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT sn.id, sn.kind, sn.content, sn.tokens, sn.parent_id, sn.session_id,"
            " sn.ts_start, sn.ts_end, sn.created_at, sn.level"
            " FROM summary_nodes sn"
            " JOIN issue_sessions isl ON isl.session_id = sn.session_id"
            " WHERE isl.issue_id = ?"
            " AND sn.kind = 'condensed'"
            " AND sn.level = 0"
            " ORDER BY sn.ts_end DESC, sn.id DESC"
            " LIMIT ?",
            (issue_id, limit),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: condensed_nodes_for_issue query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [
        SummaryNode(
            id=row["id"],
            kind=row["kind"],
            content=(row["content"] or "")[:node_char_cap],
            tokens=row["tokens"],
            parent_id=row["parent_id"],
            session_id=row["session_id"],
            ts_start=row["ts_start"],
            ts_end=row["ts_end"],
            created_at=row["created_at"],
            level=row["level"],
        )
        for row in rows
    ]
