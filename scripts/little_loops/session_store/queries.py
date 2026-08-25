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


# ENH-075 shareable export allowlist (FEAT-3304 D12) — keyed by PHYSICAL table
# name, not the _EXPORT_TABLE_MAP type-name vocabulary. Columns not listed are
# excluded from a `mode=shareable` export: `loop_runs.error` is free text and
# `loop_runs.diagnostics_path` is an absolute filesystem path, neither of which
# may ever appear in a shareable snapshot.
#
# Any edit to this constant MUST bump _SHAREABLE_ALLOWLIST_VERSION in the same
# commit. A test enforces the lockstep by pinning a hash of the constant against
# the version — without it, "stamped with the allowlist version" stamps an
# unmanaged string and provides no control at all.
_SHAREABLE_COLUMNS: dict[str, list[str]] = {
    "loop_runs": [
        "run_id",
        "loop_name",
        "started_at",
        "ended_at",
        "final_state",
        "iterations",
        "terminated_by",
        "evaluator_score",
        "failure_terminal",
        "branch",
        "head_sha",
    ],
    "usage_events": [
        "ts",
        "session_id",
        "model",
        "state",
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "cost_usd",
        "provider_vendor",
        "run_id",
        "invocation_id",
    ],
}

_SHAREABLE_ALLOWLIST_VERSION: int = 1

# The export types the shareable allowlist covers — the default `--tables` set
# for `ll-artifact dashboard` in BOTH modes (D16/D22). Deliberately NOT
# _EXPORT_DEFAULT_TABLES, which is 20 types, 18 of them with no allowlist entry.
_SHAREABLE_EXPORT_TYPES: list[str] = sorted(
    type_name
    for type_name, (table, _ts) in _EXPORT_TABLE_MAP.items()
    if table in _SHAREABLE_COLUMNS
)


def _connect_readonly(db: Path) -> sqlite3.Connection:
    """Open *db* through a raw ``file:…?mode=ro`` URI, bypassing the store's opener.

    Deliberately not ``session_store.connect()``: the store's normal open path
    **migrates on open** (schema.py), so routing a read-only export through it
    would mutate the user's live history.db as a side effect of generating an
    artifact (D19). ``mode=ro`` scopes read-only to the *main* database only — a
    writable scratch DB can still be ATTACHed, which is what makes D2 work.
    """
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def read_schema_version(conn: sqlite3.Connection) -> str | None:
    """Read the DB's recorded ``schema_version`` from ``meta`` (D19).

    There is no public accessor: ``_current_version()`` is private and the
    public schema-report dict that wraps it walks ``PRAGMA index_list`` for every
    table — far too heavy for one integer. Returns None if the row is absent.
    """
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    return None if row[0] is None else str(row[0])


def _snapshot_select(table: str, ts_col: str, local_mode: bool, since: str | None) -> str:
    """Build the ``CREATE TABLE snap.<table> AS SELECT …`` statement for one type."""
    # Local mode lifts the column projection entirely (D22) — it is for personal
    # use, and a half-redacted local export would only be confusing.
    if local_mode:
        projection = "*"
    else:
        columns = _SHAREABLE_COLUMNS.get(table)
        if columns is None:
            raise ValueError(
                f"table {table!r} has no shareable column allowlist; "
                "use --local to export it without a column projection"
            )
        projection = ", ".join(columns)

    # D13: a loop_runs row that is still executing (or crashed without writing an
    # end timestamp) has ended_at IS NULL and would be silently dropped by any
    # `ended_at >= ?` predicate. COALESCE keeps runs that *started* in the window.
    predicate_col = "COALESCE(ended_at, started_at)" if table == "loop_runs" else ts_col

    # noqa: S608 — table/column names come only from _EXPORT_TABLE_MAP and
    # _SHAREABLE_COLUMNS, never from raw user text; the one user-supplied value
    # (`since`) is bound as a parameter.
    sql = f"CREATE TABLE snap.{table} AS SELECT {projection} FROM main.{table}"  # noqa: S608
    if since:
        sql += f" WHERE {predicate_col} >= ?"  # noqa: S608
    return sql


def build_snapshot_db(
    db: Path,
    dest: Path,
    *,
    tables: list[str],
    since: str | None = None,
    local_mode: bool = False,
) -> str | None:
    """ATTACH + ``CREATE TABLE … AS SELECT`` a filtered/redacted snapshot (D2).

    A **sibling** of :func:`export_history`, not a wrapper: ``export_history``
    yields dicts for JSONL, while sql.js needs a SQLite *file*, and there is no
    path from one to the other short of re-inserting every row.

    Opens *db* read-only via a raw ``file:…?mode=ro`` URI (never
    ``session_store.connect()``, which migrates on open — D19) and ATTACHes
    *dest* as a writable scratch database. No VACUUM or index stripping is
    needed: a freshly created attached DB carries no indexes and no free pages.

    Args:
        db: Path to the source history database.
        dest: Path the scratch snapshot is written to. Must not already exist.
        tables: :data:`_EXPORT_TABLE_MAP` type names to materialize.
        since: ISO 8601 timestamp; rows at or after it are kept. Filters on
            ``COALESCE(ended_at, started_at)`` for ``loop_run`` (D13) and on the
            type's :data:`_EXPORT_TABLE_MAP` timestamp column otherwise.
        local_mode: When False (shareable), every selected type must have a
            :data:`_SHAREABLE_COLUMNS` entry and is projected to it. When True,
            types without an entry export all columns (D22).

    Returns:
        The source DB's recorded ``schema_version``, read on the same read-only
        connection (D19), or None when it cannot be determined.
    """
    unknown = [t for t in tables if t not in _EXPORT_TABLE_MAP]
    if unknown:
        raise ValueError(
            f"unknown export type(s) {sorted(unknown)}; choices: {', '.join(_EXPORT_TABLE_MAP)}"
        )

    conn = _connect_readonly(Path(db))
    try:
        schema_version = read_schema_version(conn)
        conn.execute("ATTACH DATABASE ? AS snap", (str(dest),))
        try:
            for type_name in tables:
                table, ts_col = _EXPORT_TABLE_MAP[type_name]
                sql = _snapshot_select(table, ts_col, local_mode, since)
                params = (since,) if since else ()
                conn.execute(sql, params)
            conn.commit()
        finally:
            conn.execute("DETACH DATABASE snap")
    finally:
        conn.close()
    return schema_version


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
