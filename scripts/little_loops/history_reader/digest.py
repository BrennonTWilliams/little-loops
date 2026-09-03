"""Project-digest section providers (ENH-1907) (ENH-2775 split from the
former flat ``history_reader.py``).

Aggregates a project-wide ``<project_context>`` snapshot from three
independent tables (``file_events``, ``issue_events``, ``user_corrections``)
via a small config-addressable ``SectionProvider`` registry. Despite
"aggregating," none of its providers call another submodule's query
functions — each queries its own table directly — so this module needs no
DAG exception and imports only from ``_base``/``models`` like every sibling.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from little_loops.history_reader._base import _connect_readonly, _stale_cutoff, logger
from little_loops.history_reader.models import ProjectDigest, SectionProvider

__all__ = [
    "SECTION_PROVIDERS",
    "project_digest",
    "render_project_context",
]


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
    provider_keys: list[str] = list(SECTION_PROVIDERS.keys()) if not sections else sections

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
