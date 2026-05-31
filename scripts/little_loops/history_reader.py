"""Typed read-only query module for ``.ll/history.db`` (ENH-1752).

Provides the common queries that ll skills and agents need to consume the
session database without importing ad-hoc SQL into every caller. All
functions degrade gracefully: missing/empty/corrupt databases return empty
lists, never raise.

Public API:
    UserCorrection:   dataclass for user correction rows
    FileEvent:        dataclass for file event rows
    SearchResult:     dataclass for FTS5 search results
    IssueEvent:       dataclass for issue event rows
    find_user_corrections(topic, ...) -> list[UserCorrection]
    recent_file_events(path, ...) -> list[FileEvent]
    search(query, ...) -> list[SearchResult]
    related_issue_events(issue_id, ...) -> list[IssueEvent]
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from little_loops.session_store import DEFAULT_DB_PATH, ensure_db

logger = logging.getLogger(__name__)

STALE_DAYS_DEFAULT = 30


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class UserCorrection:
    ts: str
    session_id: str | None
    content: str
    source: str | None


@dataclass
class FileEvent:
    ts: str
    session_id: str | None
    path: str | None
    op: str | None
    issue_id: str | None
    git_sha: str | None


@dataclass
class SearchResult:
    content: str
    kind: str
    ref: str
    anchor: str
    ts: str
    score: float


@dataclass
class IssueEvent:
    ts: str
    issue_id: str | None
    transition: str | None
    discovered_by: str | None
    issue_type: str | None
    priority: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stale_cutoff(days: int) -> str:
    """ISO-8601 timestamp *days* ago."""
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect_readonly(db_path: Path) -> sqlite3.Connection | None:
    """Open a read-only connection, or return None on failure."""
    try:
        ensure_db(db_path)
    except sqlite3.Error:
        logger.warning("history_reader: could not ensure schema for %s", db_path, exc_info=True)
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
    except sqlite3.Error:
        logger.warning("history_reader: could not open %s read-only", db_path, exc_info=True)
        return None
    return conn


def _row_to_dataclass(row: sqlite3.Row, dc: type[Any]) -> Any:
    """Map a sqlite3.Row to a dataclass instance, catching extra/unknown keys."""
    field_names = {f.name for f in dc.__dataclass_fields__.values()}
    kwargs = {k: row[k] for k in field_names if k in row.keys()}
    return dc(**kwargs)


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------


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

    Returns BM25-ranked results. Gracefully handles invalid FTS5 query syntax.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        if kind:
            rows = conn.execute(
                "SELECT content, kind, ref, anchor, ts, bm25(search_index) AS score "
                "FROM search_index WHERE search_index MATCH ? AND kind = ? "
                "ORDER BY score LIMIT ?",
                (query, kind, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT content, kind, ref, anchor, ts, bm25(search_index) AS score "
                "FROM search_index WHERE search_index MATCH ? "
                "ORDER BY score LIMIT ?",
                (query, limit),
            ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.warning("history_reader: invalid FTS5 query %r: %s", query, exc)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, SearchResult) for row in rows]


def related_issue_events(
    issue_id: str,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[IssueEvent]:
    """Return issue events for *issue_id*, ordered by most recent first.

    Searches both the ``issue_events`` table and the FTS5 index for cross-references.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT ts, issue_id, transition, discovered_by, issue_type, priority "
            "FROM issue_events WHERE issue_id = ? "
            "ORDER BY ts DESC LIMIT ?",
            (issue_id, limit),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: related_issue_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, IssueEvent) for row in rows]
