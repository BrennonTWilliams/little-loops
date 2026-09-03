"""Full-text search, correction, and file-event queries (ENH-2775 split from
the former flat ``history_reader.py``).

Backing sources: the ``search_index`` FTS5 virtual table (``search()``), the
``user_corrections`` table (``find_user_corrections()``), and the
``file_events`` table (``recent_file_events()``).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from little_loops.history_reader._base import (
    DEFAULT_DB_PATH,
    STALE_DAYS_DEFAULT,
    _connect_readonly,
    _row_to_dataclass,
    _stale_cutoff,
    fts_phrase,
    logger,
)
from little_loops.history_reader.models import FileEvent, SearchResult, UserCorrection

__all__ = [
    "find_user_corrections",
    "recent_file_events",
    "search",
]


def find_user_corrections(
    topic: str,
    *,
    limit: int = 10,
    include_stale: bool = False,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[UserCorrection]:
    """Return user corrections whose content matches *topic* (LIKE search).

    Stale rows (>30 days by default) are excluded unless *include_stale* is set.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        params: list[Any] = [f"%{topic}%"]
        where = "WHERE content LIKE ?"
        if not include_stale:
            where += " AND ts >= ?"
            params.append(_stale_cutoff(STALE_DAYS_DEFAULT))
        rows = conn.execute(
            f"SELECT ts, session_id, content, source FROM user_corrections {where} "
            f"ORDER BY ts DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: find_user_corrections query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, UserCorrection) for row in rows]


def recent_file_events(
    path: str,
    *,
    limit: int = 10,
    include_stale: bool = False,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[FileEvent]:
    """Return recent file events for *path* (LIKE pattern match).

    Stale rows (>30 days by default) are excluded unless *include_stale* is set.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        params: list[Any] = [f"%{path}%"]
        where = "WHERE path LIKE ?"
        if not include_stale:
            where += " AND ts >= ?"
            params.append(_stale_cutoff(STALE_DAYS_DEFAULT))
        rows = conn.execute(
            f"SELECT ts, session_id, path, op, issue_id, git_sha FROM file_events {where} "
            f"ORDER BY ts DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_file_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, FileEvent) for row in rows]


def search(
    query: str,
    *,
    kind: str | None = None,
    limit: int = 10,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SearchResult]:
    """FTS5 full-text search with optional *kind* filter (tool, file, issue, loop, correction, message).

    Returns BM25-ranked results. The *query* is matched as a literal FTS5 phrase
    (see :func:`little_loops.session_store.fts_phrase`), so hyphenated issue IDs
    (e.g. ``BUG-490``) match rather than being parsed as operators (BUG-2651).
    Gracefully handles invalid FTS5 query syntax.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    phrase = fts_phrase(query)
    try:
        if kind:
            rows = conn.execute(
                "SELECT content, kind, ref, anchor, ts, bm25(search_index) AS score "
                "FROM search_index WHERE search_index MATCH ? AND kind = ? "
                "ORDER BY score LIMIT ?",
                (phrase, kind, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT content, kind, ref, anchor, ts, bm25(search_index) AS score "
                "FROM search_index WHERE search_index MATCH ? "
                "ORDER BY score LIMIT ?",
                (phrase, limit),
            ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.warning("history_reader: invalid FTS5 query %r: %s", query, exc)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, SearchResult) for row in rows]
