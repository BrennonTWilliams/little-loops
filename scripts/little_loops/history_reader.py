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
    SessionRef:       dataclass for issue_sessions view rows (ENH-1711)
    SectionProvider:  config-addressable digest section (ENH-1907)
    ProjectDigest:    aggregated project-context snapshot (ENH-1907)
    SECTION_PROVIDERS: registry of v1 section providers (ENH-1907)
    find_user_corrections(topic, ...) -> list[UserCorrection]
    recent_file_events(path, ...) -> list[FileEvent]
    search(query, ...) -> list[SearchResult]
    related_issue_events(issue_id, ...) -> list[IssueEvent]
    sessions_for_issue(issue_id, ...) -> list[SessionRef]
    issue_effort(issue_id, ...) -> dict | None
    recent_issue_velocity(limit, ...) -> list[dict]
    project_digest(db_path, ...) -> ProjectDigest
    render_project_context(digest, ...) -> str
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
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


@dataclass
class SessionRef:
    """A session that co-occurred with an issue's active period (ENH-1711)."""

    issue_id: str | None
    session_id: str | None
    jsonl_path: str | None
    first_message_ts: str | None
    last_message_ts: str | None


@dataclass(frozen=True)
class SectionProvider:
    """Config-addressable digest section with query and render logic (ENH-1907)."""

    name: str
    query: Callable  # (conn, *, cutoff: str, cap: int) -> list
    default_cap: int
    render: Callable  # (rows: list) -> list[str]


@dataclass
class ProjectDigest:
    """Aggregated project-context snapshot from history.db (ENH-1907)."""

    sections: list[tuple[str, list[str]]]  # [(name, markdown_lines), ...] in config order
    days: int = 7

    @property
    def empty(self) -> bool:
        return all(not lines for _, lines in self.sections)


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


def sessions_for_issue(
    issue_id: str,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SessionRef]:
    """Return sessions that co-occurred with *issue_id*'s active period.

    Queries the ``issue_sessions`` VIEW (v5 migration, ENH-1711), which joins
    ``issue_events`` to ``message_events`` via overlapping timestamps.  Live-emitted
    rows (from ``issue_lifecycle.py````'s 6 emit sites) now populate ``captured_at``
    directly; no prior ``backfill`` pass is needed for issues processed after
    ENH-1839.

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
            "FROM issue_sessions WHERE issue_id = ? "
            "ORDER BY first_message_ts DESC LIMIT ?",
            (issue_id, limit),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: sessions_for_issue query failed", exc_info=True)
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
            "MAX(last_message_ts) AS last_ts FROM issue_sessions WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: issue_effort query failed", exc_info=True)
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
            "SELECT DISTINCT issue_id FROM issue_events "
            "WHERE completed_at IS NOT NULL "
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


# ---------------------------------------------------------------------------
# Project digest — section providers (ENH-1907)
# ---------------------------------------------------------------------------


def _query_touched_files(conn: sqlite3.Connection, *, cutoff: str, cap: int) -> list:
    try:
        return conn.execute(
            "SELECT path, COUNT(*) AS edit_count "
            "FROM file_events "
            "WHERE ts >= ? AND path IS NOT NULL "
            "GROUP BY path "
            "ORDER BY edit_count DESC, MAX(ts) DESC "
            "LIMIT ?",
            (cutoff, cap),
        ).fetchall()
    except sqlite3.Error:
        return []


def _render_touched_files(rows: list) -> list[str]:
    lines = []
    for row in rows:
        path = row["path"]
        count = row["edit_count"]
        noun = "edit" if count == 1 else "edits"
        lines.append(f"- {path} ({count} {noun})")
    return lines


def _query_completed_issues(conn: sqlite3.Connection, *, cutoff: str, cap: int) -> list:
    try:
        return conn.execute(
            "SELECT ts, issue_id, transition, issue_type, priority "
            "FROM issue_events "
            "WHERE transition IN ('done', 'cancelled') AND ts >= ? "
            "ORDER BY ts DESC "
            "LIMIT ?",
            (cutoff, cap),
        ).fetchall()
    except sqlite3.Error:
        return []


def _render_completed_issues(rows: list) -> list[str]:
    lines = []
    now = datetime.now(UTC)
    for row in rows:
        issue_id = row["issue_id"] or "unknown"
        ts_str = row["ts"] or ""
        time_ago = ""
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                delta_days = (now - ts).days
                if delta_days == 0:
                    time_ago = " (today)"
                elif delta_days == 1:
                    time_ago = " (1d ago)"
                else:
                    time_ago = f" ({delta_days}d ago)"
            except (ValueError, TypeError):
                pass
        lines.append(f"- {issue_id}{time_ago}")
    return lines


def _query_recurring_corrections(conn: sqlite3.Connection, *, cutoff: str, cap: int) -> list:
    try:
        return conn.execute(
            "SELECT content, COUNT(*) AS seen_count "
            "FROM user_corrections "
            "WHERE ts >= ? "
            "GROUP BY content "
            "ORDER BY seen_count DESC, MAX(ts) DESC "
            "LIMIT ?",
            (cutoff, cap),
        ).fetchall()
    except sqlite3.Error:
        return []


def _render_recurring_corrections(rows: list) -> list[str]:
    lines = []
    for row in rows:
        content = row["content"] or ""
        count = row["seen_count"]
        if len(content) > 80:
            content = content[:77] + "..."
        count_str = f" (seen {count}x)" if count > 1 else ""
        lines.append(f'- "{content}"{count_str}')
    return lines


SECTION_PROVIDERS: dict[str, SectionProvider] = {
    "touched_files": SectionProvider(
        name="touched_files",
        query=_query_touched_files,
        default_cap=10,
        render=_render_touched_files,
    ),
    "completed_issues": SectionProvider(
        name="completed_issues",
        query=_query_completed_issues,
        default_cap=5,
        render=_render_completed_issues,
    ),
    "recurring_corrections": SectionProvider(
        name="recurring_corrections",
        query=_query_recurring_corrections,
        default_cap=5,
        render=_render_recurring_corrections,
    ),
}

_SECTION_HEADERS: dict[str, str] = {
    "touched_files": "Recently touched (last {days} days)",
    "completed_issues": "Recently completed issues",
    "recurring_corrections": "Recurring corrections",
}


def project_digest(
    db_path: Path,
    *,
    days: int = 7,
    sections: list[str] | None = None,
) -> ProjectDigest:
    """Aggregate a project-wide context snapshot from history.db.

    Returns a :class:`ProjectDigest` with ``.empty == True`` on missing /
    empty / stale DB.  ``sections=None`` or ``sections=[]`` renders all
    registered providers in registry order; a non-empty list restricts and
    orders the output.
    """
    conn = _connect_readonly(db_path)
    if conn is None:
        return ProjectDigest(sections=[], days=days)

    cutoff = _stale_cutoff(days)
    provider_keys: list[str] = list(SECTION_PROVIDERS.keys()) if sections is None else sections

    result: list[tuple[str, list[str]]] = []
    try:
        for key in provider_keys:
            provider = SECTION_PROVIDERS.get(key)
            if provider is None:
                logger.warning("project_digest: unknown section %r — skipping", key)
                continue
            rows = provider.query(conn, cutoff=cutoff, cap=provider.default_cap)
            lines = provider.render(rows) if rows else []
            if lines:
                result.append((key, lines))
    finally:
        conn.close()

    return ProjectDigest(sections=result, days=days)


def render_project_context(
    digest: ProjectDigest,
    *,
    char_cap: int = 1200,
    days: int | None = None,
) -> str:
    """Render a ``<project_context>`` block from *digest*, capped at *char_cap* chars.

    Returns ``""`` when the digest is empty (no block injected).  Truncates
    with a ``+N more`` tail when content would exceed *char_cap*.
    """
    if digest.empty:
        return ""

    effective_days = days if days is not None else digest.days
    content_lines: list[str] = []
    for name, section_lines in digest.sections:
        raw_header = _SECTION_HEADERS.get(name, name.replace("_", " ").title())
        header = raw_header.format(days=effective_days)
        content_lines.append(f"## {header}")
        content_lines.extend(section_lines)

    open_tag = "<project_context>"
    close_tag = "</project_context>"

    full_block = "\n".join([open_tag] + content_lines + [close_tag])
    if len(full_block) <= char_cap:
        return full_block

    # Truncate: accumulate content lines under budget, append "+N more" tail.
    close_cost = len("\n" + close_tag)
    budget = char_cap - len(open_tag) - close_cost - 1  # -1 for opening newline
    accepted: list[str] = []
    dropped = 0
    for line in content_lines:
        line_cost = len(line) + 1  # +1 for the newline separator
        if budget >= line_cost:
            accepted.append(line)
            budget -= line_cost
        else:
            dropped += 1

    if dropped:
        tail = f"... +{dropped} more"
        if budget >= len(tail) + 1:
            accepted.append(tail)

    return "\n".join([open_tag] + accepted + [close_tag])
