"""Read-path queries for the session store (ENH-2890 split from session_store.py).

FTS5 search/recent lookups and the JSONL export walker. Depends on
:mod:`little_loops.session_store.schema` (``connect``, ``VALID_KINDS``,
``_KIND_TABLE``) and :mod:`little_loops.session_store.db` (``DEFAULT_DB_PATH``).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Any

import little_loops.session_store as _pkg
from little_loops.session_store.db import DEFAULT_DB_PATH
from little_loops.session_store.schema import _KIND_TABLE, VALID_KINDS

logger = logging.getLogger(__name__)


def fts_phrase(query: str) -> str:
    """Wrap *query* as an FTS5 quoted phrase so operator characters (``-``, ``*``,
    ``:``, ``"`` …) are matched literally (BUG-2651).

    Hyphenated issue IDs (e.g. ``BUG-490``) are otherwise parsed by FTS5 as a
    column-filter/negation expression and raise ``no such column``. Escaping the
    embedded double-quotes (``"`` → ``""``) and wrapping the whole string in
    double-quotes turns any input into a single literal phrase.
    """
    return '"' + query.replace('"', '""') + '"'


def search(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Run an FTS5 full-text query, returning BM25-ranked results.

    Each result dict carries ``content``, ``kind``, ``ref``, ``anchor`` (a
    file:line-style pointer where available), ``ts`` and a numeric ``score``
    (lower BM25 score = better match). The *query* is matched as a literal FTS5
    phrase (see :func:`fts_phrase`), so hyphenated IDs match rather than raise.
    """
    conn = _pkg.connect(db)
    try:
        rows = conn.execute(
            "SELECT content, kind, ref, anchor, ts, bm25(search_index) AS score "
            "FROM search_index WHERE search_index MATCH ? "
            "ORDER BY score LIMIT ?",
            (fts_phrase(query), limit),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError(f"invalid FTS query {query!r}: {exc}") from exc
    finally:
        conn.close()
    return [dict(row) for row in rows]


def recent(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    kind: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return the most recent rows for *kind*.

    Kinds: tool, file, issue, loop, correction, message, skill, cli, commit,
    test_run, usage, orchestration_run, prompt_opt.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {sorted(VALID_KINDS)}")
    table = _KIND_TABLE[kind]
    conn = _pkg.connect(db)
    try:
        rows = conn.execute(
            f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?",  # noqa: S608 - table from fixed map
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


# Maps the public type name used in exported records to (table, timestamp_column).
_EXPORT_TABLE_MAP: dict[str, tuple[str, str]] = {
    "session": ("sessions", "started_at"),
    "issue_event": ("issue_events", "ts"),
    "issue_snapshot": ("issue_snapshots", "ts"),
    "skill_event": ("skill_events", "ts"),
    "loop_event": ("loop_events", "ts"),
    "correction": ("user_corrections", "ts"),
    "summary_node": ("summary_nodes", "created_at"),
    "message_event": ("message_events", "ts"),
    "commit_event": ("commit_events", "ts"),
    "test_run_event": ("test_run_events", "ts"),
    "usage_event": ("usage_events", "ts"),
    "orchestration_run": ("orchestration_runs", "ended_at"),
    "loop_run": ("loop_runs", "ended_at"),
    "session_lifecycle_event": ("session_lifecycle_events", "ts"),
    "harness_event": ("harness_events", "ts"),
    "prompt_opt_event": ("prompt_opt_events", "ts"),
    "verdict_event": ("verdict_events", "ts"),
    "context_pressure_event": ("context_pressure_events", "ts"),
    "review_event": ("review_events", "ts"),
    "advisor_consult_event": ("advisor_consults", "ts"),
}

_EXPORT_DEFAULT_TABLES = [
    "session",
    "issue_event",
    "issue_snapshot",
    "skill_event",
    "loop_event",
    "correction",
    "summary_node",
    "commit_event",
    "test_run_event",
    "usage_event",
    "orchestration_run",
    "loop_run",
    "session_lifecycle_event",
    "harness_event",
    "prompt_opt_event",
    "verdict_event",
    "context_pressure_event",
    "review_event",
    "advisor_consult_event",
]


def export_tables_help() -> str:
    """Build the ``--tables`` help text for ``ll-session export`` (BUG-3197).

    Derived from :data:`_EXPORT_TABLE_MAP` and :data:`_EXPORT_DEFAULT_TABLES` so
    the advertised choice set cannot drift from the accepted one — adding a key
    to the map updates ``--help`` with no second edit.  Public despite reading
    two private lists: ``cli/session.py`` imports it across a package boundary.
    """
    choices = ", ".join(_EXPORT_TABLE_MAP)
    excluded = sorted(set(_EXPORT_TABLE_MAP) - set(_EXPORT_DEFAULT_TABLES))
    default_note = (
        f"default: all types except {', '.join(excluded)}" if excluded else "default: all types"
    )
    return f"Types to include ({default_note}). Choices: {choices}"


def export_history(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    tables: list[str] | None = None,
    since: str | None = None,
    include_messages: bool = False,
) -> Generator[dict, None, None]:
    """Yield rows from history.db as dicts with a ``type`` key (JSONL export).

    Each yielded dict has a ``"type"`` field identifying the source table so
    records from multiple tables can be mixed in a single stream and later
    distinguished by a visualizer.

    Args:
        db: Path to the history database (default: ``.ll/history.db``).
        tables: Type names to include.  Defaults to all non-message tables.
            The valid values are the keys of :data:`_EXPORT_TABLE_MAP`; they are
            deliberately not restated here, since a docstring cannot be derived
            and this list had drifted three entries behind the map (BUG-3197).
            Unknown names are logged and skipped rather than raising.
        since: ISO 8601 datetime string; only rows at or after this timestamp are
            returned, filtered per-table using the relevant timestamp column.
        include_messages: When ``True`` and *tables* is not given, also include
            ``message_events`` (~46 K rows by default).  Ignored when *tables*
            is specified explicitly.
    """
    db_path = Path(db)
    if not db_path.exists():
        return

    if tables is None:
        selected = list(_EXPORT_DEFAULT_TABLES)
        if include_messages:
            selected.append("message_event")
    else:
        selected = list(tables)

    conn = _pkg.connect(db_path)
    try:
        for type_name in selected:
            entry = _EXPORT_TABLE_MAP.get(type_name)
            if entry is None:
                logger.warning("export_history: unknown type %r — skipped", type_name)
                continue
            table, ts_col = entry
            try:
                if since:
                    cursor = conn.execute(
                        f"SELECT * FROM {table} WHERE {ts_col} >= ? ORDER BY {ts_col}",
                        (since,),
                    )
                else:
                    cursor = conn.execute(f"SELECT * FROM {table} ORDER BY {ts_col}")
                for row in cursor:
                    d = dict(row)
                    d["type"] = type_name
                    yield d
            except sqlite3.OperationalError as exc:
                logger.warning("export_history: skipping %s: %s", table, exc)
    finally:
        conn.close()
