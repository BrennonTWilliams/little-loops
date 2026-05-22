"""Unified session store: a per-project SQLite + FTS5 database (FEAT-1112).

A single ``.ll/session.db`` indexes tool events, file modifications, issue
transitions, loop runs, and user corrections so cross-cutting queries
("which loops failed on issues touching file X?") can be answered in
milliseconds rather than re-parsing scattered JSON/markdown sources.

The store is purely additive: it never replaces an existing data path. The
``SQLiteTransport`` sink subscribes to the EventBus alongside the other
transports, and the backfill routine seeds the database from on-disk sources
that the analyze-* skills already read.

Public API:
    DEFAULT_DB_PATH:  default database location (``.ll/session.db``)
    SCHEMA_VERSION:   current schema version integer
    ensure_db(path):  create the database and apply pending migrations
    connect(path):    open a connection (ensures schema first)
    SQLiteTransport:  EventBus Transport sink writing FSM events to loop_events
    backfill(db,...): populate the database from existing on-disk sources
    search(db,...):   FTS5 full-text query with BM25 ranking
    recent(db,...):   recent rows for a given event kind
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(".ll/session.db")
SCHEMA_VERSION = 2

_VALID_KINDS = frozenset({"tool", "file", "issue", "loop", "correction", "message"})
_KIND_TABLE = {
    "tool": "tool_events",
    "file": "file_events",
    "issue": "issue_events",
    "loop": "loop_events",
    "correction": "user_corrections",
    "message": "message_events",
}

# FSM event types the SQLiteTransport records as loop_events rows.
_LOOP_EVENT_TYPES = frozenset(
    {
        "loop_start",
        "loop_resume",
        "loop_complete",
        "state_enter",
        "route",
        "retry_exhausted",
        "cycle_detected",
    }
)


# ---------------------------------------------------------------------------
# Schema + migrations
# ---------------------------------------------------------------------------

# Each entry is the full SQL applied to move the schema from version index to
# index+1. Migration 0 bootstraps the whole schema; append new entries to
# evolve it. ``bytes_in`` / ``bytes_out`` / ``cache_hit`` are reserved on
# ``tool_events`` for FEAT-1160 (Context Window Analytics) so that feature does
# not require a follow-up migration.
_MIGRATIONS: list[str] = [
    """
    CREATE TABLE tool_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        tool_name TEXT,
        args_hash TEXT,
        result_size INTEGER,
        bytes_in INTEGER,
        bytes_out INTEGER,
        cache_hit INTEGER
    );
    CREATE TABLE file_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        path TEXT,
        op TEXT,
        issue_id TEXT,
        git_sha TEXT
    );
    CREATE TABLE issue_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        issue_id TEXT,
        transition TEXT,
        discovered_by TEXT
    );
    CREATE TABLE loop_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        loop_name TEXT,
        state TEXT,
        transition TEXT,
        retries INTEGER
    );
    CREATE TABLE user_corrections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        content TEXT,
        source TEXT
    );
    CREATE VIRTUAL TABLE search_index USING fts5(
        content,
        kind UNINDEXED,
        ref UNINDEXED,
        anchor UNINDEXED,
        ts UNINDEXED
    );
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    """,
    # v2 (ENH-1621): widen issue_events with completion-summary columns so
    # ll-history `summary` can be answered from the DB; add message_events for
    # analyze_workflows() to read user message bodies without re-parsing JSONL.
    """
    ALTER TABLE issue_events ADD COLUMN issue_type TEXT;
    ALTER TABLE issue_events ADD COLUMN priority TEXT;
    ALTER TABLE issue_events ADD COLUMN completed_date TEXT;
    ALTER TABLE issue_events ADD COLUMN captured_at TEXT;
    ALTER TABLE issue_events ADD COLUMN completed_at TEXT;
    CREATE TABLE message_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        content TEXT
    );
    """,
]


def _now() -> str:
    """Return the current UTC time as a Z-suffixed ISO 8601 string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _current_version(conn: sqlite3.Connection) -> int:
    """Return the applied schema version, or 0 if the meta table is absent."""
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row[0]) if row else 0


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply every migration newer than the database's current version."""
    version = _current_version(conn)
    for index in range(version, len(_MIGRATIONS)):
        conn.executescript(_MIGRATIONS[index])
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(index + 1),),
        )
        conn.commit()


def ensure_db(path: Path | str = DEFAULT_DB_PATH) -> Path:
    """Create the database at *path* (if needed) and apply pending migrations.

    Idempotent: safe to call on every session start. The parent directory is
    created if absent. Returns the resolved database path.
    """
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        _apply_migrations(conn)
    finally:
        conn.close()
    return db_path


def connect(path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a connection to the session database, ensuring the schema first.

    Rows are returned as :class:`sqlite3.Row` so callers can index by name.
    """
    db_path = ensure_db(path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _index(
    conn: sqlite3.Connection,
    *,
    content: str,
    kind: str,
    ref: str,
    anchor: str,
    ts: str,
) -> None:
    """Insert one row into the FTS5 ``search_index`` table."""
    conn.execute(
        "INSERT INTO search_index(content, kind, ref, anchor, ts) VALUES(?, ?, ?, ?, ?)",
        (content, kind, ref, anchor, ts),
    )


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------


def search(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Run an FTS5 full-text query, returning BM25-ranked results.

    Each result dict carries ``content``, ``kind``, ``ref``, ``anchor`` (a
    file:line-style pointer where available), ``ts`` and a numeric ``score``
    (lower BM25 score = better match).
    """
    conn = connect(db)
    try:
        rows = conn.execute(
            "SELECT content, kind, ref, anchor, ts, bm25(search_index) AS score "
            "FROM search_index WHERE search_index MATCH ? "
            "ORDER BY score LIMIT ?",
            (query, limit),
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
    """Return the most recent rows for *kind* (tool, file, issue, loop, correction)."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {sorted(_VALID_KINDS)}")
    table = _KIND_TABLE[kind]
    conn = connect(db)
    try:
        rows = conn.execute(
            f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?",  # noqa: S608 - table from fixed map
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# SQLiteTransport
# ---------------------------------------------------------------------------


class SQLiteTransport:
    """EventBus sink that records FSM loop events into the session database.

    A single connection is opened at construction with ``check_same_thread``
    disabled, since :meth:`send` may be called from the FSM thread while other
    transports run their own threads; a lock serialises writes. Every
    operation is best-effort — a database error is logged and swallowed so a
    failing sink never aborts a loop run (the four ``wire_transports`` call
    sites depend on this).
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        try:
            ensure_db(self._path)
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        except sqlite3.Error:
            logger.warning(
                "SQLiteTransport: could not open %s; sink disabled", self._path, exc_info=True
            )
            self._conn = None

    def send(self, event: dict[str, Any]) -> None:
        """Record a recognised FSM event as a ``loop_events`` row (best-effort)."""
        conn = self._conn
        if conn is None:
            return
        event_type = str(event.get("event", ""))
        if event_type not in _LOOP_EVENT_TYPES:
            return
        loop_name = str(event.get("loop_name", "")) or None
        state = event.get("state")
        if event_type == "loop_complete":
            state = event.get("outcome", state)
        retries = event.get("retries")
        ts = str(event.get("ts") or _now())
        try:
            with self._lock:
                conn.execute(
                    "INSERT INTO loop_events(ts, loop_name, state, transition, retries) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (
                        ts,
                        loop_name,
                        str(state) if state is not None else None,
                        event_type,
                        int(retries) if isinstance(retries, int) else None,
                    ),
                )
                _index(
                    conn,
                    content=" ".join(
                        str(p) for p in (loop_name, state, event_type) if p is not None
                    ),
                    kind="loop",
                    ref=loop_name or "",
                    anchor=f".loops/{loop_name}.yaml" if loop_name else "",
                    ts=ts,
                )
                conn.commit()
        except sqlite3.Error:
            logger.warning("SQLiteTransport: write failed for event %r", event_type, exc_info=True)

    def close(self) -> None:
        """Close the underlying connection (best-effort)."""
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------


def _hash_args(value: Any) -> str:
    """Return a short stable hash of a tool-call argument structure."""
    try:
        blob = json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        blob = repr(value)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


_FILENAME_TYPE_RE = re.compile(r"(BUG|ENH|FEAT|EPIC)-(\d+)")
_FILENAME_PRIORITY_RE = re.compile(r"^(P\d)")


def _derive_type_priority(filename: str, fm: dict[str, Any]) -> tuple[str | None, str | None]:
    """Derive (issue_type, priority) preferring frontmatter, falling back to filename.

    Mirrors :func:`little_loops.issue_history.parsing.parse_completed_issue`'s
    filename-parsing convention (``P[0-5]-[TYPE]-[NNN]-...``).
    """
    fm_type = fm.get("type")
    issue_type: str | None = str(fm_type) if isinstance(fm_type, str) and fm_type else None
    fm_priority = fm.get("priority")
    priority: str | None = (
        str(fm_priority) if isinstance(fm_priority, str) and fm_priority else None
    )
    if issue_type is None:
        m = _FILENAME_TYPE_RE.search(filename)
        if m:
            issue_type = m.group(1)
    if priority is None:
        m = _FILENAME_PRIORITY_RE.match(filename)
        if m:
            priority = m.group(1)
    return issue_type, priority


def _backfill_issues(conn: sqlite3.Connection, issues_dir: Path) -> int:
    """Seed ``issue_events`` from issue-file frontmatter under *issues_dir*.

    Populates the v2 summary columns (``issue_type``, ``priority``,
    ``completed_date``, ``captured_at``, ``completed_at``) so ``ll-history
    summary`` can be answered from the DB without re-reading the files
    (ENH-1621). ``completed_date`` is derived from ``completed_at`` (taking the
    date portion) when present, leaving file-mtime / Resolution-section
    inference to the file-parsing fallback path.
    """
    from little_loops.frontmatter import parse_frontmatter

    count = 0
    for issue_file in sorted(issues_dir.rglob("*.md")):
        try:
            fm = parse_frontmatter(issue_file.read_text(encoding="utf-8"))
        except OSError:
            continue
        issue_id = fm.get("id")
        if not issue_id:
            continue
        status = str(fm.get("status", "open"))
        discovered_by = fm.get("discovered_by")
        captured_at = fm.get("captured_at")
        completed_at = fm.get("completed_at")
        ts = str(completed_at or captured_at or fm.get("discovered_date") or "")
        issue_type, priority = _derive_type_priority(issue_file.name, fm)
        completed_date: str | None = None
        if isinstance(completed_at, str) and completed_at:
            completed_date = completed_at[:10]
        conn.execute(
            "INSERT INTO issue_events("
            "ts, issue_id, transition, discovered_by, "
            "issue_type, priority, completed_date, captured_at, completed_at"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                str(issue_id),
                status,
                str(discovered_by) if discovered_by else None,
                issue_type,
                priority,
                completed_date,
                str(captured_at) if captured_at else None,
                str(completed_at) if completed_at else None,
            ),
        )
        _index(
            conn,
            content=f"{issue_id} {status} {issue_type or ''}",
            kind="issue",
            ref=str(issue_id),
            anchor=str(issue_file),
            ts=ts,
        )
        count += 1
    return count


def _backfill_loops(conn: sqlite3.Connection, loops_dir: Path) -> int:
    """Seed ``loop_events`` from FSM state JSON under ``.loops/.running`` + ``.history``."""
    count = 0
    for sub in (".running", ".history"):
        directory = loops_dir / sub
        if not directory.is_dir():
            continue
        for state_file in sorted(directory.glob("*.json")):
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            loop_name = str(data.get("loop_name") or state_file.stem)
            state = data.get("current_state") or data.get("state")
            ts = str(data.get("updated_at") or data.get("started_at") or "")
            conn.execute(
                "INSERT INTO loop_events(ts, loop_name, state, transition, retries) "
                "VALUES(?, ?, ?, ?, ?)",
                (ts, loop_name, str(state) if state else None, "backfill", None),
            )
            _index(
                conn,
                content=f"{loop_name} {state or ''}",
                kind="loop",
                ref=loop_name,
                anchor=str(state_file),
                ts=ts,
            )
            count += 1
    return count


def _backfill_tool_events(conn: sqlite3.Connection, jsonl_files: list[Path]) -> int:
    """Seed ``tool_events`` from assistant tool-use blocks in session JSONL files."""
    count = 0
    for jsonl_file in jsonl_files:
        try:
            handle = jsonl_file.open(encoding="utf-8")
        except OSError:
            continue
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") != "assistant":
                    continue
                session_id = record.get("sessionId")
                ts = str(record.get("timestamp") or "")
                content = record.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tool_name = str(block.get("name", ""))
                    args = block.get("input", {})
                    conn.execute(
                        "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, "
                        "result_size, bytes_in, bytes_out, cache_hit) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                        (ts, session_id, tool_name, _hash_args(args), None, None, None, None),
                    )
                    _index(
                        conn,
                        content=tool_name,
                        kind="tool",
                        ref=tool_name,
                        anchor=str(jsonl_file),
                        ts=ts,
                    )
                    count += 1
    return count


def _backfill_messages(conn: sqlite3.Connection, jsonl_files: list[Path]) -> int:
    """Seed ``message_events`` from user blocks in session JSONL files.

    Mirrors :func:`_backfill_tool_events` but selects ``type == "user"`` records
    and inserts the user's textual content. Used by analyze_workflows() so
    workflow analysis can read message bodies from the DB instead of a JSONL
    file (ENH-1621).
    """
    count = 0
    for jsonl_file in jsonl_files:
        try:
            handle = jsonl_file.open(encoding="utf-8")
        except OSError:
            continue
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") != "user":
                    continue
                session_id = record.get("sessionId")
                ts = str(record.get("timestamp") or "")
                # The user message body lives at message.content; it may be a
                # plain string or a list of content blocks. We persist a text
                # rendering — list blocks are concatenated by their "text"
                # field so analyze_workflows() can run its regexes over it.
                content = record.get("message", {}).get("content", "")
                if isinstance(content, list):
                    parts: list[str] = []
                    for block in content:
                        if isinstance(block, dict) and isinstance(block.get("text"), str):
                            parts.append(block["text"])
                    text = "\n".join(parts)
                elif isinstance(content, str):
                    text = content
                else:
                    text = ""
                if not text.strip():
                    continue
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    (ts, str(session_id) if session_id else None, text),
                )
                _index(
                    conn,
                    content=text[:512],
                    kind="message",
                    ref=str(session_id) if session_id else "",
                    anchor=str(jsonl_file),
                    ts=ts,
                )
                count += 1
    return count


def backfill(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    issues_dir: Path | None = None,
    loops_dir: Path | None = None,
    jsonl_files: list[Path] | None = None,
) -> dict[str, int]:
    """Populate the database from existing on-disk sources.

    Reads issue-file frontmatter, FSM loop-state JSON, and (optionally) session
    JSONL tool-use blocks plus user-message blocks. Returns a per-kind count of
    rows inserted. Sources that are absent are skipped silently.
    """
    issues_dir = issues_dir if issues_dir is not None else Path(".issues")
    loops_dir = loops_dir if loops_dir is not None else Path(".loops")
    conn = connect(db)
    counts: dict[str, int] = {"issues": 0, "loops": 0, "tools": 0, "messages": 0}
    try:
        if issues_dir.is_dir():
            counts["issues"] = _backfill_issues(conn, issues_dir)
        if loops_dir.is_dir():
            counts["loops"] = _backfill_loops(conn, loops_dir)
        if jsonl_files:
            counts["tools"] = _backfill_tool_events(conn, jsonl_files)
            counts["messages"] = _backfill_messages(conn, jsonl_files)
        conn.commit()
    finally:
        conn.close()
    return counts
