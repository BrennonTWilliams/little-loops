"""Unified session store: a per-project SQLite + FTS5 database (FEAT-1112).

A single ``.ll/history.db`` is the per-project event history across all
Claude Code sessions: it indexes tool events, file modifications, issue
transitions, loop runs, and user corrections so cross-cutting queries
("which loops failed on issues touching file X?") can be answered in
milliseconds rather than re-parsing scattered JSON/markdown sources. The
``session_id`` column ties each row back to its originating session JSONL,
but the database itself is long-lived and never rotated.

The store is purely additive: it never replaces an existing data path. The
``SQLiteTransport`` sink subscribes to the EventBus alongside the other
transports, and the backfill routine seeds the database from on-disk sources
that the analyze-* skills already read.

Public API:
    DEFAULT_DB_PATH:             default database location (``.ll/history.db``)
    SCHEMA_VERSION:              current schema version integer
    ensure_db(path):             create the database and apply pending migrations
    connect(path):               open a connection (ensures schema first)
    SQLiteTransport:             EventBus Transport sink writing FSM events to
                                 ``loop_events`` and issue lifecycle events to
                                 ``issue_events`` (ENH-1690)
    backfill(db,...):            populate the database from existing on-disk sources
    backfill_incremental(db,...): incremental JSONL-only backfill filtered by mtime
    mine_corrections_from_messages(conn,...): scan message_events and insert corrections
    compact_session(session_id,...): summarize one session into summary_nodes/summary_spans
    prune(db,...):               prune raw event rows older than N days and VACUUM
    search(db,...):              FTS5 full-text query with BM25 ranking
    recent(db,...):              recent rows for a given event kind
    is_correction(text):         return True if text matches a user-correction signal
    record_correction(db,...):   write one row to ``user_corrections`` + search_index
    record_skill_event(db,...):  write one row to ``skill_events`` + search_index
    cli_event_context(db,...):   context manager: INSERT on enter, UPDATE exit_code+duration on exit
    skill_event_context(db,...): skill-host analogue of cli_event_context (ENH-2460)
    record_commit_event(db,...): write one row to ``commit_events`` + search_index (ENH-2458)
    record_test_run_event(db,...): write one row to ``test_run_events`` + search_index (ENH-2459)
    record_orchestration_run(db,...): UPSERT one per-issue batch outcome (ENH-2492)
    record_loop_run_summary(db,...): write one row to ``loop_runs`` + search_index (ENH-2463)
    update_loop_run_diagnostics(db,...): link a diagnostics artifact to its loop_runs row (ENH-2463)
    record_learning_test_event(db,...): UPSERT one Learning Test Registry record mirror (ENH-2466)
    record_hook_event(db,...):   write one row to ``hook_events`` + search_index (ENH-2506)
    hook_event_context(db,...):  hook-fire analogue of skill_event_context (ENH-2506)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import threading
import time
import zlib
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.host_runner import resolve_host

if TYPE_CHECKING:
    from little_loops.config.features import CompactionConfig

__all__ = [
    "DEFAULT_DB_PATH",
    "SCHEMA_VERSION",
    "VALID_KINDS",
    "ensure_db",
    "connect",
    "SQLiteTransport",
    "backfill",
    "backfill_snapshots",
    "backfill_incremental",
    "backfill_raw_events",
    "recompress_raw_events",
    "rebuild",
    "compact",
    "mine_corrections_from_messages",
    "compact_session",
    "export_history",
    "prune",
    "search",
    "recent",
    "is_correction",
    "record_correction",
    "record_skill_event",
    "record_issue_snapshot",
    "record_commit_event",
    "record_test_run_event",
    "record_orchestration_run",
    "cli_event_context",
    "skill_event_context",
    "SkillEventCompletion",
    "resolve_history_db",
    "record_retirement",
    "list_retirements",
    "record_learning_test_event",
    "record_session_lifecycle_event",
    "record_hook_event",
    "hook_event_context",
    "HookEventCompletion",
]

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(".ll/history.db")


def _is_default_shaped(path: Path | str | None) -> bool:
    """True when *path* names the default DB location (ENH-2623).

    Default-shaped means ``None``, ``DEFAULT_DB_PATH``, or a ``history.db`` under
    a ``.ll/`` directory (matched by basename + parent, not strict equality — so
    the cwd-*absolute* ``.ll/history.db`` that hooks construct still routes
    through the env → config → default chain). Any other path is a deliberate
    override and is returned verbatim by :func:`_resolve_db_path`.
    """
    if path is None:
        return True
    p = Path(path)
    if p == DEFAULT_DB_PATH:
        return True
    return p.name == "history.db" and p.parent.name == ".ll"


def _config_db_path() -> Path | None:
    """Best-effort read of ``history.db_path`` from the project config (ENH-2623).

    Returns the configured path (relative paths resolved against the project
    root, i.e. the current working directory), or ``None`` when the key is
    unset or the config is missing/malformed. Never raises — mirroring the
    guarded ``resolve_config_path`` + ``json.loads`` pattern the bootstrap hooks
    use — so the hot ``SessionStart`` / ``UserPromptSubmit`` path is never
    blocked by a bad config file.
    """
    try:
        from little_loops.config.core import resolve_config_path

        root = Path.cwd()
        cfg_path = resolve_config_path(root)
        if cfg_path is None:
            return None
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        raw = (data.get("history") or {}).get("db_path")
        if not raw:
            return None
        p = Path(raw)
        return p if p.is_absolute() else root / p
    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return None


def _resolve_db_path(path: Path | str | None = None) -> Path:
    """Unified DB-path resolution (ENH-2623): env → config → explicit/default.

    Precedence for a *default-shaped* *path* (see :func:`_is_default_shaped`):

    1. ``LL_HISTORY_DB`` env var — unconditional ephemeral override.
    2. ``history.db_path`` config key — persistent per-project setting.
    3. the explicit *path* argument, or ``DEFAULT_DB_PATH`` when ``None``.

    A deliberate (non-default-shaped) override path is returned verbatim, so
    callers that hand an explicit location (recompress maintenance, tests) are
    always honored — resolving the historical ``resolve_history_db`` /
    ``ensure_db`` divergence into one rule.
    """
    if not _is_default_shaped(path):
        return Path(path)  # type: ignore[arg-type]
    env_val = os.environ.get("LL_HISTORY_DB")
    if env_val:
        return Path(env_val)
    cfg = _config_db_path()
    if cfg is not None:
        return cfg
    return Path(path) if path is not None else DEFAULT_DB_PATH


def resolve_history_db(path: Path | str | None = None) -> Path:
    """Return the DB path via the unified env → config → default chain (ENH-2623).

    ``LL_HISTORY_DB`` takes precedence, then the ``history.db_path`` config key,
    then the explicit *path* / ``DEFAULT_DB_PATH`` — but only for a default-shaped
    *path*; a deliberate override is returned verbatim. Delegates to
    :func:`_resolve_db_path` so this and :func:`ensure_db` never diverge.
    """
    return _resolve_db_path(path)


# raw_events payload compression (ENH: shrink the source-of-truth table).
# ``raw_line``/``parsed_json`` are stored zlib-compressed as BLOBs. SQLite's
# dynamic typing lets a BLOB live in the existing (nominally TEXT) columns with
# no destructive DDL, and legacy uncompressed TEXT rows coexist with new BLOB
# rows: readers dispatch on the Python type (bytes → decompress, str → legacy
# passthrough), so a partially-recompressed table always reads correctly. Level
# 6 is stdlib zlib's default (good ratio/speed; ~2.9x on these JSONL payloads).
_PAYLOAD_ZLIB_LEVEL = 6


def _pack_payload(text: str) -> bytes:
    """Compress a payload string for storage in ``raw_events``."""
    return zlib.compress(text.encode("utf-8"), _PAYLOAD_ZLIB_LEVEL)


def _unpack_payload(value: str | bytes) -> str:
    """Return payload text: ``bytes`` → zlib-decompress, ``str`` → legacy passthrough.

    New rows store compressed BLOBs (read back as ``bytes``); rows written before
    the compression change are plain TEXT (read back as ``str``) and pass through
    unchanged. This keeps a partially-recompressed table fully readable.
    """
    if isinstance(value, bytes):
        return zlib.decompress(value).decode("utf-8")
    return value


SCHEMA_VERSION = 30

VALID_KINDS: tuple[str, ...] = (
    "tool",
    "file",
    "issue",
    "loop",
    "correction",
    "message",
    "skill",
    "cli",
    "snapshot",
    "commit",
    "test_run",
    "usage",
    "orchestration_run",
    "loop_run",
    "learning_test",
    "session_lifecycle",
    "subagent_run",
    "hook_event",
)
_KIND_TABLE = {
    "tool": "tool_events",
    "file": "file_events",
    "issue": "issue_events",
    "loop": "loop_events",
    "correction": "user_corrections",
    "message": "message_events",
    "skill": "skill_events",
    "cli": "cli_events",
    "snapshot": "issue_snapshots",
    "commit": "commit_events",
    "test_run": "test_run_events",
    "usage": "usage_events",
    "orchestration_run": "orchestration_runs",
    "loop_run": "loop_runs",
    "learning_test": "learning_test_events",
    "session_lifecycle": "session_lifecycle_events",
    "subagent_run": "subagent_runs",
    "hook_event": "hook_events",
}

# Cache tables that intentionally have no VALID_KINDS entry — support tables
# with no "recent by kind" concept (raw_events is the JSONL source-of-truth,
# not itself a queryable kind; sessions/assistant_messages/summary_nodes/
# summary_spans are structural, not event streams; meta/search_index are
# infrastructure). ll-verify-kinds (ENH-2581) checks every other CREATE TABLE
# in _MIGRATIONS has a _KIND_TABLE entry.
_KINDLESS_TABLES = frozenset(
    {
        "meta",
        "search_index",
        "sessions",
        "assistant_messages",
        "summary_nodes",
        "summary_spans",
        "raw_events",
        "correction_retirements",
    }
)

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
        "max_steps_summary",
        "max_iterations_reached_summary",
    }
)


_CORRECTION_RE = re.compile(
    r"^\s*(no[,!]|don'?t\s|stop\s|revert|that'?s\s+wrong|not\s+like\s+that)",
    re.IGNORECASE,
)

_PHRASE_RE = re.compile(
    r"\b(?:"
    r"instead"
    r"|actually\s+(?:that|this|it)\s"
    r"|you missed"
    r"|should be\s+(?!fine\b|ok\b|okay\b|good\b|great\b|alright\b|correct\b|right\b)"
    r"|wrong approach"
    r"|remember that"
    r"|always use"
    r"|never use"
    r"|from now on"
    r"|I meant\b.*\bnot\b"
    r"|not\b.*\buse\b"
    r")",
    re.IGNORECASE,
)
_REMEMBER_RE = re.compile(r"^!remember\b", re.IGNORECASE)


def is_correction(text: str, extra_patterns: Sequence[str] = ()) -> bool:
    """Return True if *text* matches a known user-correction signal.

    ``extra_patterns`` are raw regex strings appended to the built-in set
    (``analytics.capture.correction_patterns``). Built-ins always remain active.
    Invalid patterns are skipped with a warning.
    """
    t = text[:512]
    _extra_re: re.Pattern[str] | None = None
    if extra_patterns:
        parts: list[str] = []
        for p in extra_patterns:
            try:
                re.compile(p, re.IGNORECASE)
                parts.append(f"(?:{p})")
            except re.error:
                logger.warning("is_correction: skipping invalid extra_pattern %r", p)
        if parts:
            _extra_re = re.compile("|".join(parts), re.IGNORECASE)
    return bool(
        _REMEMBER_RE.match(t)
        or _CORRECTION_RE.match(t)
        or _PHRASE_RE.search(t)
        or (_extra_re and _extra_re.search(t))
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
    CREATE TABLE IF NOT EXISTS tool_events (
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
    CREATE TABLE IF NOT EXISTS file_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        path TEXT,
        op TEXT,
        issue_id TEXT,
        git_sha TEXT
    );
    CREATE TABLE IF NOT EXISTS issue_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        issue_id TEXT,
        transition TEXT,
        discovered_by TEXT
    );
    CREATE TABLE IF NOT EXISTS loop_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        loop_name TEXT,
        state TEXT,
        transition TEXT,
        retries INTEGER
    );
    CREATE TABLE IF NOT EXISTS user_corrections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        content TEXT,
        source TEXT
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
        content,
        kind UNINDEXED,
        ref UNINDEXED,
        anchor UNINDEXED,
        ts UNINDEXED
    );
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
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
    # v3 (ENH-1690): unique dedup index on issue_events so INSERT OR IGNORE
    # prevents duplicate rows when backfill() is called multiple times.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_events_dedup
        ON issue_events(issue_id, transition);
    """,
    # v4 (ENH-1710): sessions table maps session_id to its JSONL file path,
    # closing the broken link between event rows and their source log.
    """
    CREATE TABLE sessions (
        session_id TEXT PRIMARY KEY,
        jsonl_path TEXT NOT NULL,
        started_at TEXT,
        project_path TEXT
    );
    """,
    # v5 (ENH-1711): issue_sessions VIEW joins issue_events to message_events via
    # overlapping timestamps, making the implicit session→issue link explicit and
    # queryable. Requires captured_at IS NOT NULL; populated by _backfill_issues()
    # for historical rows and by issue_lifecycle.py emit sites (ENH-1839) for
    # live-emitted rows.
    """
    CREATE VIEW issue_sessions AS
    SELECT ie.issue_id,
           me.session_id,
           s.jsonl_path,
           MIN(me.ts) AS first_message_ts,
           MAX(me.ts) AS last_message_ts
    FROM issue_events ie
    JOIN message_events me
      ON me.ts >= ie.captured_at
     AND (ie.completed_at IS NULL OR me.ts <= ie.completed_at)
    LEFT JOIN sessions s ON s.session_id = me.session_id
    WHERE ie.captured_at IS NOT NULL
    GROUP BY ie.issue_id, me.session_id;
    """,
    # v6 (ENH-1830): last_backfill_ts meta key for incremental JSONL backfill at
    # session start. The meta table already holds arbitrary key/value pairs; this
    # initialises the sentinel so reads can distinguish "no prior run" (NULL) from
    # a real ISO 8601 timestamp string.
    """
    INSERT OR IGNORE INTO meta(key, value) VALUES('last_backfill_ts', NULL);
    """,
    # v7 (ENH-1833): skill_events table records /ll: skill invocations at dispatch
    # time via the user_prompt_submit hook so ll-session recent --kind skill works.
    """
    CREATE TABLE IF NOT EXISTS skill_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        skill_name TEXT,
        args TEXT
    );
    """,
    # v8 (ENH-1848): cli_events table records ll- CLI invocations via cli_event_context()
    """
    CREATE TABLE IF NOT EXISTS cli_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        binary TEXT NOT NULL,
        args TEXT NOT NULL,
        exit_code INTEGER,
        duration_ms INTEGER
    );
    """,
    # v9 (ENH-1904): unique dedup index on user_corrections so INSERT OR IGNORE
    # enforces idempotency during correction mining. Mirrors v3's
    # idx_issue_events_dedup pattern.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_corrections_dedup
        ON user_corrections(session_id, content);
    """,
    # v10 (FEAT-1712, v12 ENH-1953): LCM-style hierarchical summary DAG over
    # session history. summary_nodes holds LLM-generated summaries (via three-level
    # LCM Algorithm 3 escalation: normal → aggressive bullet-point → deterministic
    # truncation) at multiple levels: 'leaf' nodes cover a fixed token-budget block
    # of message_events; 'condensed' nodes summarise a session's leaves (level 0,
    # per-session) or cross-session nodes (level 1+, session_id IS NULL); the root
    # node sits at the maximum level. summary_spans links summary nodes back to the
    # originating message_events rows for lossless drill-down.
    # FK references are decorative (no PRAGMA foreign_keys; integrity enforced at
    # the application layer by compact_session's insert ordering + INSERT OR IGNORE).
    # Partial unique indexes prevent duplicate leaf and condensed nodes per session
    # (idx_summary_nodes_condensed_dedup) and duplicate cross-session nodes
    # (idx_summary_nodes_cross_dedup, added in v12) across repeated backfill() calls
    # (idempotency via INSERT OR IGNORE).
    """
    CREATE TABLE IF NOT EXISTS summary_nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        content TEXT NOT NULL,
        tokens INTEGER,
        parent_id INTEGER REFERENCES summary_nodes(id),
        session_id TEXT,
        ts_start TEXT,
        ts_end TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS summary_spans (
        summary_id INTEGER REFERENCES summary_nodes(id),
        message_event_id INTEGER REFERENCES message_events(id),
        PRIMARY KEY (summary_id, message_event_id)
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_summary_nodes_leaf_dedup
        ON summary_nodes(session_id, ts_start, ts_end) WHERE kind = 'leaf';
    CREATE UNIQUE INDEX IF NOT EXISTS idx_summary_nodes_condensed_dedup
        ON summary_nodes(session_id) WHERE kind = 'condensed';
    CREATE INDEX IF NOT EXISTS idx_summary_nodes_parent_id
        ON summary_nodes(parent_id);
    """,
    # v11 (ENH-1942): assistant_messages stores concatenated text blocks from
    # assistant responses so the SFT pipeline can read conversation turn-pairs
    # from the database instead of re-parsing JSONL. tool_use_count enables
    # filter predicates (e.g. min_tool_invocations) without a JOIN.
    # idx_assistant_messages_dedup mirrors v3's idx_issue_events_dedup pattern
    # so INSERT OR IGNORE enforces idempotency during backfill.
    """
    CREATE TABLE IF NOT EXISTS assistant_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT NOT NULL,
        content TEXT NOT NULL,
        tool_use_count INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_assistant_messages_session_ts
        ON assistant_messages(session_id, ts);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_assistant_messages_dedup
        ON assistant_messages(session_id, ts, content);
    """,
    # v12 (ENH-1953): add level column to summary_nodes for N-level DAG
    # traversal and a cross-session dedup index. level 0 = leaf/per-session
    # condensed, 1+ = cross-session condensed, max = root.
    # idx_summary_nodes_cross_dedup prevents duplicate cross-session condensed
    # nodes where session_id IS NULL (the existing idx_summary_nodes_condensed_dedup
    # only covers per-session rows and is unchanged).
    """
    ALTER TABLE summary_nodes ADD COLUMN level INTEGER DEFAULT 0;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_summary_nodes_cross_dedup
        ON summary_nodes(level, ts_start, ts_end)
        WHERE kind='condensed' AND session_id IS NULL;
    """,
    # v13 (ENH-2046): correction_retirements — records addressed correction clusters so
    # detect_recurring_feedback() excludes already-ruled topics from future runs.
    """
    CREATE TABLE IF NOT EXISTS correction_retirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic_fingerprint TEXT NOT NULL,
        rule_id TEXT,
        addressed_at TEXT NOT NULL,
        session_id TEXT
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_retirements_fingerprint
        ON correction_retirements(topic_fingerprint);
    """,
    # v14 (ENH-2151): issue_snapshots — stores full issue content at key lifecycle
    # transitions (captured, done, cancelled) so completed issue context is queryable
    # from the DB even after the source .md file is moved or deleted.
    # FTS via the existing autonomous search_index with kind="snapshot" (Decision 1).
    # Dedup index mirrors v3's idx_issue_events_dedup pattern.
    """
    CREATE TABLE IF NOT EXISTS issue_snapshots (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts          TEXT NOT NULL,
        issue_id    TEXT NOT NULL,
        transition  TEXT NOT NULL,
        title       TEXT,
        priority    TEXT,
        issue_type  TEXT,
        body        TEXT,
        frontmatter TEXT
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_snapshots_dedup
        ON issue_snapshots(issue_id, transition);
    """,
    # v15 (ENH-2460): completion-side columns on skill_events so skill hosts can
    # record exit_code/success/duration_ms via skill_event_context(), mirroring
    # cli_events (ENH-1834). Nullable so pre-migration dispatch-only rows remain
    # valid (NULL = "no completion signal recorded").
    """
    ALTER TABLE skill_events ADD COLUMN exit_code INTEGER;
    ALTER TABLE skill_events ADD COLUMN success INTEGER;
    ALTER TABLE skill_events ADD COLUMN duration_ms INTEGER;
    """,
    # v16 (ENH-2462): authoritative session_id column on issue_events, captured at
    # transition time by the EventBus producer. The timestamp-overlap heuristic
    # view is preserved as legacy_issue_sessions_ts_overlap (deprecated); the
    # issue_sessions relation is rebuilt to prefer exact session_id joins and
    # fall back to the legacy inference only for issues with no authoritative
    # rows, so pre-migration consumers keep working without a data backfill.
    """
    ALTER TABLE issue_events ADD COLUMN session_id TEXT;
    CREATE INDEX IF NOT EXISTS idx_issue_events_session_id ON issue_events(session_id);
    DROP VIEW IF EXISTS issue_sessions;
    CREATE VIEW legacy_issue_sessions_ts_overlap AS
    SELECT ie.issue_id,
           me.session_id,
           s.jsonl_path,
           MIN(me.ts) AS first_message_ts,
           MAX(me.ts) AS last_message_ts
    FROM issue_events ie
    JOIN message_events me
      ON me.ts >= ie.captured_at
     AND (ie.completed_at IS NULL OR me.ts <= ie.completed_at)
    LEFT JOIN sessions s ON s.session_id = me.session_id
    WHERE ie.captured_at IS NOT NULL
    GROUP BY ie.issue_id, me.session_id;
    CREATE VIEW issue_sessions AS
    SELECT ie.issue_id,
           ie.session_id,
           s.jsonl_path,
           MIN(ie.ts) AS first_message_ts,
           MAX(ie.ts) AS last_message_ts
    FROM issue_events ie
    LEFT JOIN sessions s ON s.session_id = ie.session_id
    WHERE ie.session_id IS NOT NULL
    GROUP BY ie.issue_id, ie.session_id
    UNION ALL
    SELECT l.issue_id, l.session_id, l.jsonl_path, l.first_message_ts, l.last_message_ts
    FROM legacy_issue_sessions_ts_overlap l
    WHERE l.issue_id NOT IN (
        SELECT issue_id FROM issue_events
        WHERE session_id IS NOT NULL AND issue_id IS NOT NULL
    );
    """,
    # v17 (ENH-2458): commit_events — ground-truth record of what actually
    # shipped. Populated live by record_commit_event() (post-commit hook or the
    # /ll:commit path) and retroactively by _backfill_commit_events() walking
    # ``git log --all``. commit_sha UNIQUE + INSERT OR IGNORE gives idempotency.
    """
    CREATE TABLE IF NOT EXISTS commit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        commit_sha TEXT NOT NULL UNIQUE,
        parent_sha TEXT,
        message TEXT NOT NULL,
        author TEXT,
        branch TEXT,
        issue_id TEXT,
        files_json TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_commit_events_issue_id ON commit_events(issue_id);
    CREATE INDEX IF NOT EXISTS idx_commit_events_branch ON commit_events(branch);
    CREATE INDEX IF NOT EXISTS idx_commit_events_sha ON commit_events(commit_sha);
    """,
    # v18 (ENH-2459): test_run_events — persisted pytest run results (the local
    # suite is this project's only CI gate). Written best-effort by the
    # little_loops.pytest_history_plugin pytest11 plugin via record_test_run_event().
    """
    CREATE TABLE IF NOT EXISTS test_run_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        ended_at TEXT,
        total INTEGER,
        passed INTEGER,
        failed INTEGER,
        errored INTEGER,
        skipped INTEGER,
        duration_s REAL,
        failing_names_json TEXT,
        env_label TEXT,
        head_sha TEXT,
        branch TEXT,
        command TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_test_run_events_head_sha ON test_run_events(head_sha);
    CREATE INDEX IF NOT EXISTS idx_test_run_events_branch ON test_run_events(branch);
    CREATE INDEX IF NOT EXISTS idx_test_run_events_failed_count ON test_run_events(failed);
    """,
    # v19 (ENH-2581): raw_events — verbatim JSONL line + parsed fields, the
    # source of truth for the JSONL-derived cache tables (tool_events,
    # message_events, assistant_messages, skill_events, sessions). backfill()
    # ingests here only; rebuild() wipes+re-derives the cache tables from this
    # table. compact()/prune() operate on raw_events for the retention
    # lifecycle (compacted=1 marks rows summarized and eligible for deletion).
    # The three per-table watermarks (last_backfill_ts,
    # last_backfill_ts_assistant_messages, last_backfill_ts_skill_events)
    # collapse to the single last_raw_event_ts meta key.
    """
    CREATE TABLE IF NOT EXISTS raw_events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts          TEXT NOT NULL,
        session_id  TEXT,
        host        TEXT NOT NULL,
        source_path TEXT NOT NULL,
        line_no     INTEGER NOT NULL,
        event_type  TEXT NOT NULL,
        -- raw_line/parsed_json are declared TEXT but store zlib-compressed
        -- BLOBs on write via SQLite dynamic typing (see _pack_payload,
        -- _unpack_payload, recompress_raw_events). Legacy uncompressed TEXT rows
        -- coexist and read back via the str/bytes dispatch in _unpack_payload.
        raw_line    TEXT NOT NULL,
        parsed_json TEXT NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_events_dedup
        ON raw_events(source_path, line_no);
    CREATE INDEX IF NOT EXISTS idx_raw_events_session_ts
        ON raw_events(session_id, ts);
    CREATE INDEX IF NOT EXISTS idx_raw_events_host_ts
        ON raw_events(host, ts);
    ALTER TABLE raw_events ADD COLUMN compacted INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE raw_events ADD COLUMN summary_node_id INTEGER
        REFERENCES summary_nodes(id);
    INSERT OR IGNORE INTO meta(key, value) VALUES('last_raw_event_ts', NULL);
    INSERT OR IGNORE INTO meta(key, value) VALUES('last_rebuild_version', NULL);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_summary_nodes_retention_dedup
        ON summary_nodes(session_id, ts_start, ts_end) WHERE kind = 'retention';
    """,
    # v20 (ENH-2461): usage_events — real LLM token counts (input/output/cache)
    # the API returned, plus derived cost_usd, one row per assistant turn.
    # Derived from raw_events by _backfill_usage_events(): the on-disk transcript
    # carries the usage block on ``type == "assistant"`` records at
    # ``message.usage`` (verified against live session files). ``state`` is a
    # forward-compat column, always NULL on parser-written rows (the transcript
    # carries no FSM-state boundary — see ENH-2461 Addendum 2); reserved for a
    # future live per-state writer. Column names mirror the Anthropic API usage
    # fields (underscore, not the dotted OTel form FEAT-2478 derives).
    """
    CREATE TABLE IF NOT EXISTS usage_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        model TEXT,
        state TEXT,
        input_tokens INTEGER,
        output_tokens INTEGER,
        cache_read_input_tokens INTEGER,
        cache_creation_input_tokens INTEGER,
        cost_usd REAL
    );
    CREATE INDEX IF NOT EXISTS idx_usage_events_session ON usage_events(session_id);
    CREATE INDEX IF NOT EXISTS idx_usage_events_model ON usage_events(model);
    """,
    # v21 (FEAT-2478): OTel gen_ai.* addenda on usage_events. invocation_id maps
    # to gen_ai.invocation.id (a per-CLI-invocation UUID enabling GROUP BY rollups
    # that match raw result-event usage totals row-for-row); provider_vendor maps
    # to gen_ai.provider.vendor (anthropic/openai/google/other). Both are
    # forward-compat NULL on parser-written rows — like `state`, reserved for a
    # future live per-invocation writer. Column names stay underscore/internal;
    # the dotted OTel spelling is derived on read by observability/tracing.py.
    """
    ALTER TABLE usage_events ADD COLUMN invocation_id TEXT;
    ALTER TABLE usage_events ADD COLUMN provider_vendor TEXT;
    """,
    # v22 (ENH-2492): per-issue outcomes from ll-auto, ll-parallel, and ll-sprint.
    # Direct-write execution ground truth; intentionally excluded from raw_events
    # rebuild because no transcript parser can reconstruct these batch results.
    """
    CREATE TABLE IF NOT EXISTS orchestration_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        driver TEXT NOT NULL,
        issue_id TEXT NOT NULL,
        status TEXT NOT NULL,
        failure_reason TEXT,
        duration_s REAL,
        wave TEXT,
        pr_url TEXT,
        started_at TEXT,
        ended_at TEXT,
        head_sha TEXT,
        branch TEXT,
        UNIQUE(run_id, issue_id)
    );
    CREATE INDEX IF NOT EXISTS idx_orchestration_runs_driver
        ON orchestration_runs(driver);
    CREATE INDEX IF NOT EXISTS idx_orchestration_runs_issue_id
        ON orchestration_runs(issue_id);
    CREATE INDEX IF NOT EXISTS idx_orchestration_runs_status
        ON orchestration_runs(status);
    """,
    # v23 (ENH-2463): one row per completed loop run — final state, iteration
    # count, evaluator score (nullable; extraction deferred to a follow-on),
    # and a diagnostics-artifact link. A producer-side direct-write sibling of
    # orchestration_runs (v22): written from FSMExecutor._finish() with its
    # locals, not derived from raw_events — rebuild() intentionally excludes
    # loop_events/loop_runs from materialization (see _REBUILD_TABLES below).
    """
    CREATE TABLE IF NOT EXISTS loop_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL UNIQUE,
        loop_name TEXT NOT NULL,
        started_at TEXT,
        ended_at TEXT,
        final_state TEXT,
        iterations INTEGER,
        terminated_by TEXT,
        error TEXT,
        evaluator_score REAL,
        diagnostics_path TEXT,
        head_sha TEXT,
        branch TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_loop_runs_loop_name ON loop_runs(loop_name);
    CREATE INDEX IF NOT EXISTS idx_loop_runs_terminated_by ON loop_runs(terminated_by);
    CREATE INDEX IF NOT EXISTS idx_loop_runs_evaluator_score ON loop_runs(evaluator_score);
    """,
    # v24 (ENH-2497): agent_type discriminator on tool_events for Task-tool
    # spawns, so subagent usage is first-class and joinable/groupable (parity
    # with the skill-health tooling ENH-2460 gave skill_events). Nullable so
    # non-Task rows and pre-migration rows remain valid (NULL = "not a
    # subagent spawn").
    """
    ALTER TABLE tool_events ADD COLUMN agent_type TEXT;
    CREATE INDEX IF NOT EXISTS idx_tool_events_agent ON tool_events(agent_type);
    """,
    # v25 (ENH-2511): mcp_server/mcp_tool/mcp_outcome/latency_ms on tool_events.
    # All nullable so pre-migration rows remain valid. mcp_server/mcp_tool are
    # parsed from the mcp__<server>__<tool> tool_name prefix; mcp_outcome and
    # latency_ms are only populated by the live post_tool_use write (backfill
    # from JSONL cannot recover the paired tool_result envelope or timing).
    """
    ALTER TABLE tool_events ADD COLUMN mcp_server TEXT;
    ALTER TABLE tool_events ADD COLUMN mcp_tool TEXT;
    ALTER TABLE tool_events ADD COLUMN mcp_outcome TEXT;
    ALTER TABLE tool_events ADD COLUMN latency_ms INTEGER;
    CREATE INDEX IF NOT EXISTS idx_tool_events_mcp_server ON tool_events(mcp_server);
    CREATE INDEX IF NOT EXISTS idx_tool_events_mcp_outcome ON tool_events(mcp_outcome);
    """,
    # v26 (ENH-2466): mirror of the Learning Test Registry (.ll/learning-tests/*.md,
    # owned by little_loops.learning_tests) into the DB so records are discoverable
    # via `ll-session search`/`recent`. record_id is the slugified target — the
    # registry's own file-stem identity — not an issue ID. A file/external-source
    # mirror written directly by producer code (record_learning_test_event) and
    # backfill (_backfill_learning_test_events), the same shape as orchestration_runs
    # (v22) and loop_runs (v23); intentionally excluded from raw_events rebuild.
    """
    CREATE TABLE IF NOT EXISTS learning_test_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        record_id TEXT NOT NULL UNIQUE,
        target TEXT,
        status TEXT,
        assertions_json TEXT,
        date TEXT,
        raw_output_path TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_learning_test_events_target ON learning_test_events(target);
    CREATE INDEX IF NOT EXISTS idx_learning_test_events_status ON learning_test_events(status);
    """,
    # v27 (ENH-2495/ENH-2509): session-lifecycle / handoff transitions. event is
    # an open TEXT discriminator (no CHECK constraint) so ENH-2509's worktree_*
    # values can share this table per the /ll:decide-issue Option A coordination.
    # No natural UNIQUE key — two lifecycle transitions in the same second are
    # improbable, so plain INSERT is sufficient (unlike learning_test_events'
    # UPSERT-on-record_id shape).
    """
    CREATE TABLE IF NOT EXISTS session_lifecycle_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        event TEXT NOT NULL,
        detail TEXT,
        head_sha TEXT,
        branch TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_lifecycle_event ON session_lifecycle_events(event);
    CREATE INDEX IF NOT EXISTS idx_lifecycle_session ON session_lifecycle_events(session_id);
    """,
    # v28 (ENH-2505): subagent spawn tree. agent_id is spawn-local (scoped to
    # its parent session, not a sessions.session_id) per SubagentStart/
    # SubagentStop's documented payload, so the UNIQUE constraint is the
    # composite (parent_session_id, agent_id) pair, not agent_id alone — two
    # different parents could otherwise reuse the same agent_id and collide.
    """
    CREATE TABLE IF NOT EXISTS subagent_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        parent_session_id TEXT,
        agent_id TEXT,
        agent_type TEXT,
        agent_transcript_path TEXT,
        started_at TEXT,
        ended_at TEXT,
        status TEXT,
        head_sha TEXT,
        branch TEXT,
        UNIQUE(parent_session_id, agent_id)
    );
    CREATE INDEX IF NOT EXISTS idx_subagent_parent ON subagent_runs(parent_session_id);
    CREATE INDEX IF NOT EXISTS idx_subagent_agent_id ON subagent_runs(agent_id);
    CREATE INDEX IF NOT EXISTS idx_subagent_agent ON subagent_runs(agent_type);
    CREATE INDEX IF NOT EXISTS idx_subagent_status ON subagent_runs(status);
    """,
    # v29 (ENH-2723): run_id column on usage_events, decomposed from ENH-2721.
    # Nullable, additive, no FK — usage_events is deliberately an independent
    # table joined at the application/query level (ARCHITECTURE-145, ENH-2461),
    # not FK-linked to loop_runs. Unpopulated until the live writer (ENH-2724)
    # and backfill (ENH-2725) land.
    """
    ALTER TABLE usage_events ADD COLUMN run_id TEXT;
    CREATE INDEX IF NOT EXISTS idx_usage_events_run_id ON usage_events(run_id);
    """,
    # v30 (ENH-2506): hook execution telemetry. Live-write-only (see the
    # Architectural Note in ENH-2506) — the Claude Code host does not emit hook
    # execution results (exit code, duration, stderr) into the transcript
    # JSONL, so there is no raw_events source to parse and no
    # _backfill_hook_events. Excluded from _REBUILD_TABLES for the same
    # reason a wipe would be unrecoverable.
    """
    CREATE TABLE IF NOT EXISTS hook_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        event_name TEXT NOT NULL,
        matcher TEXT,
        script TEXT,
        exit_code INTEGER,
        duration_ms INTEGER,
        stderr_preview TEXT,
        head_sha TEXT,
        branch TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_hook_event_name ON hook_events(event_name);
    CREATE INDEX IF NOT EXISTS idx_hook_session ON hook_events(session_id);
    CREATE INDEX IF NOT EXISTS idx_hook_exit ON hook_events(exit_code);
    """,
]


def _now() -> str:
    """Return the current UTC time as a Z-suffixed ISO 8601 string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# Milliseconds a contended open will wait for the write lock before giving up.
# Every ``ll-*`` invocation opens this DB on startup; under ll-auto / ll-loop /
# ll-parallel many processes contend at once, so without a busy_timeout an open
# fails instantly with ``OperationalError: database is locked``.
_BUSY_TIMEOUT_MS = 5000


def _configure_connection(conn: sqlite3.Connection) -> None:
    """Apply concurrency pragmas to a freshly opened connection.

    ``busy_timeout`` makes a contended open wait instead of failing instantly
    with ``database is locked``; WAL journal mode lets readers and writers
    proceed concurrently — critical for the multi-process ll-auto / ll-loop /
    ll-parallel workload, where rollback-journal mode otherwise serialises every
    reader behind any active writer. WAL is a persistent property of the database
    file, so re-applying it on every connection is idempotent. Both pragmas are
    best-effort: a read-only filesystem or an older SQLite that rejects one must
    not prevent the database from opening.
    """
    try:
        conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        logger.debug("session_store: could not apply connection pragmas", exc_info=True)


def _split_sql_statements(script: str) -> list[str]:
    """Split a migration's SQL into individual statements on ``;`` boundaries.

    Used instead of :meth:`sqlite3.Connection.executescript` because the latter
    issues an implicit ``COMMIT`` that would release the write lock held across
    the migration sequence (see :func:`_apply_migrations`). The migration SQL in
    ``_MIGRATIONS`` is fully controlled and contains no semicolons inside string
    literals or column definitions, so a plain ``;`` split is safe here; do not
    repurpose this for arbitrary user SQL.
    """
    return [stmt for raw in script.split(";") if (stmt := raw.strip())]


def _current_version(conn: sqlite3.Connection) -> int:
    """Return the applied schema version, or 0 if the meta table is absent.

    Only a genuinely missing ``meta`` table means "fresh database, version 0".
    A transient ``database is locked`` (another process mid-write) is a different
    ``OperationalError`` and must propagate — misreading it as 0 makes the caller
    re-run migration 0 and crash with "table tool_events already exists".
    """
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return 0
        raise
    return int(row[0]) if row else 0


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply every migration newer than the database's current version.

    The whole sequence runs inside a single ``BEGIN IMMEDIATE`` transaction so
    concurrent processes serialise: the first to acquire the write lock migrates
    while the rest wait (``busy_timeout``), then re-read the now-current version
    and apply nothing. The version is re-checked *inside* the lock to close the
    fresh-database race where two processes both read version 0 and both try to
    create the bootstrap tables. ``executescript`` is avoided because its implicit
    leading ``COMMIT`` would drop the lock between migrations.

    Fast path: when the schema is already current, return without taking the
    write lock at all — in WAL mode this read never blocks on a concurrent
    writer, so the steady-state ``ll-*`` startup stays lock-free.
    """
    if _current_version(conn) >= len(_MIGRATIONS):
        return
    prior_isolation = conn.isolation_level
    conn.isolation_level = None  # manual transaction control
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            version = _current_version(conn)
            for index in range(version, len(_MIGRATIONS)):
                for statement in _split_sql_statements(_MIGRATIONS[index]):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(index + 1),),
                )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.isolation_level = prior_isolation


def ensure_db(path: Path | str = DEFAULT_DB_PATH) -> Path:
    """Create the database at *path* (if needed) and apply pending migrations.

    Idempotent: safe to call on every session start. The parent directory is
    created if absent. Returns the resolved database path.

    On the first call after the ENH-1635 rename, transparently migrates a
    pre-existing ``.ll/session.db`` (and any ``-shm``/``-wal`` sidecars) to
    the new ``.ll/history.db`` path. Each sidecar is renamed independently so
    a single failure does not abort the others; failures are logged at
    WARNING (the caller in ``hooks/session_start.py`` wraps the whole call
    in ``contextlib.suppress(Exception)``, which would otherwise silence
    diagnostic context).
    """
    db_path = _resolve_db_path(path)
    legacy = db_path.parent / "session.db"
    if legacy.exists() and not db_path.exists():
        for suffix in ("", "-shm", "-wal"):
            src = legacy.parent / f"session.db{suffix}"
            if src.exists():
                dst = db_path.parent / f"history.db{suffix}"
                try:
                    src.rename(dst)
                    logger.info("session_store: migrated %s -> %s", src, dst)
                except OSError:
                    logger.warning(
                        "session_store: legacy rename failed for %s; continuing with fresh db",
                        src,
                        exc_info=True,
                    )
                    break
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        _configure_connection(conn)
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
    _configure_connection(conn)
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


def write_file_event(
    db_path: Path | str,
    session_id: str | None,
    path: str,
    op: str,
    issue_id: str | None = None,
    config: dict | None = None,
) -> None:
    """Write one row to ``file_events`` and index it in ``search_index``.

    Gated by ``analytics.capture.file_events`` (ENH-1841): when ``config`` is
    provided and the flag is ``false``, the write is suppressed. Missing ``capture``
    key defaults to permissive (no behavior change).
    """
    if config is not None:
        from little_loops.config.features import AnalyticsCaptureConfig

        capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
        if not capture.file_events:
            return
    conn = connect(db_path)
    ts = _now()
    try:
        conn.execute(
            "INSERT INTO file_events(ts, session_id, path, op, issue_id, git_sha) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (ts, session_id, path, op, issue_id, None),
        )
        _index(conn, content=path, kind="file", ref=path, anchor=op, ts=ts)
        conn.commit()
    finally:
        conn.close()


def record_correction(
    db_path: Path | str,
    session_id: str | None,
    content: str,
    source: str,
    config: dict | None = None,
) -> None:
    """Write one row to ``user_corrections`` and index it in ``search_index``.

    Gated by ``analytics.capture.corrections`` (ENH-1841): when ``config`` is
    provided and the flag is ``false``, the write is suppressed. Missing ``capture``
    key defaults to permissive (no behavior change).
    """
    if config is not None:
        from little_loops.config.features import AnalyticsCaptureConfig

        capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
        if not capture.corrections:
            return
    content = content[:512]
    conn = connect(db_path)
    ts = _now()
    try:
        conn.execute(
            "INSERT INTO user_corrections(ts, session_id, content, source) VALUES(?, ?, ?, ?)",
            (ts, session_id, content, source),
        )
        _index(conn, content=content, kind="correction", ref=session_id or "", anchor=source, ts=ts)
        conn.commit()
    finally:
        conn.close()


def record_skill_event(
    db_path: Path | str,
    session_id: str | None,
    skill_name: str,
    args: str,
    config: dict | None = None,
) -> None:
    """Write one row to ``skill_events`` and index it in ``search_index``.

    The ``config`` parameter is a forward-compatibility stub for ENH-1835, which
    will inject a per-skill analytics gate without changing this signature.
    """
    args = args[:200]
    conn = connect(db_path)
    ts = _now()
    try:
        conn.execute(
            "INSERT INTO skill_events(ts, session_id, skill_name, args) VALUES(?, ?, ?, ?)",
            (ts, session_id, skill_name, args),
        )
        _index(
            conn, content=skill_name, kind="skill", ref=session_id or "", anchor=skill_name, ts=ts
        )
        conn.commit()
    finally:
        conn.close()


def record_issue_snapshot(
    db_path: Path | str,
    issue_id: str,
    transition: str,
    file_path: str,
) -> None:
    """Write one row to ``issue_snapshots`` and index it in ``search_index``.

    Reads the issue file at *file_path*, extracts frontmatter metadata and
    markdown body, then inserts into ``issue_snapshots`` using ``INSERT OR IGNORE``
    so repeated calls for the same ``(issue_id, transition)`` are idempotent.
    Also calls ``_index()`` with ``kind="snapshot"`` so FTS5 searches surface it.

    Silently returns if *file_path* does not exist or cannot be read.
    """
    from little_loops.frontmatter import parse_frontmatter, strip_frontmatter

    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return

    fm = parse_frontmatter(content)
    body = strip_frontmatter(content)
    title = fm.get("title") or fm.get("id") or issue_id
    priority = fm.get("priority")
    issue_type = fm.get("type")

    # Serialise frontmatter as JSON for storage.
    fm_json = json.dumps({k: str(v) for k, v in fm.items() if v is not None}, sort_keys=True)

    conn = connect(db_path)
    ts = _now()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO issue_snapshots"
            "(ts, issue_id, transition, title, priority, issue_type, body, frontmatter)"
            " VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, issue_id, transition, str(title), priority, issue_type, body, fm_json),
        )
        _index(
            conn,
            content=f"{issue_id} {title} {body or ''}".strip(),
            kind="snapshot",
            ref=issue_id,
            anchor=file_path,
            ts=ts,
        )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def cli_event_context(
    db_path: Path | str = DEFAULT_DB_PATH,
    binary: str = "",
    args: list[str] | None = None,
    config: dict | None = None,
) -> Generator[None, None, None]:
    """Insert a ``cli_events`` row on enter; update exit_code and duration_ms on exit.

    Best-effort per the EPIC-1707 graceful-degradation contract (matching
    :func:`skill_event_context`): a missing, locked, or otherwise unavailable
    database must never block the wrapped command. If the enter ``INSERT`` fails
    (e.g. ``OperationalError: database is locked`` under multi-writer contention),
    the analytics row is skipped and the command body still runs; a failure of the
    exit ``UPDATE`` never masks a successful command either. Only errors raised by
    the wrapped body propagate.

    The ``config`` parameter is a forward-compatibility stub for ENH-1835 gating;
    it is accepted but not yet used.
    """
    if args is None:
        args = []
    effective_path = resolve_history_db(db_path)
    conn: sqlite3.Connection | None = None
    row_id: int | None = None
    start = time.time()
    ts = _now()
    try:
        conn = connect(effective_path)
        cursor = conn.execute(
            "INSERT INTO cli_events(ts, binary, args) VALUES(?, ?, ?)",
            (ts, binary, json.dumps(args[:50])),
        )
        row_id = cursor.lastrowid
        conn.commit()
    except sqlite3.Error:
        logger.warning("cli_event_context: insert failed for %r", binary, exc_info=True)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        conn = None
        row_id = None
    exit_code = 0
    try:
        yield
    except BaseException:
        exit_code = 1
        raise
    finally:
        if conn is not None and row_id is not None:
            duration_ms = int((time.time() - start) * 1000)
            try:
                conn.execute(
                    "UPDATE cli_events SET exit_code=?, duration_ms=? WHERE id=?",
                    (exit_code, duration_ms, row_id),
                )
                conn.commit()
            except sqlite3.Error:
                logger.warning(
                    "cli_event_context: exit update failed for %r", binary, exc_info=True
                )
            finally:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass


@dataclass
class SkillEventCompletion:
    """Mutable completion handle yielded by :func:`skill_event_context` (ENH-2460).

    Hosts that observe a concrete process exit code (e.g. ``ll-action``) set
    ``exit_code`` before the ``with`` block exits; ``success`` is derived from
    it unless set explicitly. Left untouched, a clean exit records
    ``exit_code=0, success=1`` and a raise records ``exit_code=1, success=0``.
    """

    exit_code: int | None = None
    success: bool | None = None


@contextmanager
def skill_event_context(
    db_path: Path | str = DEFAULT_DB_PATH,
    session_id: str | None = None,
    skill_name: str = "",
    args: str = "",
    config: dict | None = None,
) -> Generator[SkillEventCompletion, None, None]:
    """Insert a ``skill_events`` row on enter; update completion columns on exit.

    Skill-host analogue of :func:`cli_event_context` (ENH-2460): records
    ``exit_code``, ``success`` and ``duration_ms`` when the wrapped skill body
    finishes. Unlike ``cli_event_context`` this is best-effort per the
    EPIC-1707 graceful-degradation contract — a missing or locked database
    never blocks the skill run (the body still executes; the row is skipped).

    The ``config`` parameter is a forward-compatibility stub for per-skill
    analytics gating (ENH-1835); it is accepted but not yet used.
    """
    args = args[:200]
    conn: sqlite3.Connection | None = None
    row_id: int | None = None
    effective_path = resolve_history_db(db_path)
    ts = _now()
    try:
        conn = connect(effective_path)
        cursor = conn.execute(
            "INSERT INTO skill_events(ts, session_id, skill_name, args) VALUES(?, ?, ?, ?)",
            (ts, session_id, skill_name, args),
        )
        row_id = cursor.lastrowid
        _index(
            conn, content=skill_name, kind="skill", ref=session_id or "", anchor=skill_name, ts=ts
        )
        conn.commit()
    except sqlite3.Error:
        logger.warning("skill_event_context: insert failed for %r", skill_name, exc_info=True)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        conn = None
        row_id = None
    start = time.time()
    completion = SkillEventCompletion()
    try:
        yield completion
        if completion.exit_code is None:
            completion.exit_code = 0
        if completion.success is None:
            completion.success = completion.exit_code == 0
    except BaseException:
        if completion.exit_code is None or completion.exit_code == 0:
            completion.exit_code = 1
        completion.success = False
        raise
    finally:
        if conn is not None and row_id is not None:
            duration_ms = int((time.time() - start) * 1000)
            exit_code = completion.exit_code if completion.exit_code is not None else 1
            success = completion.success if completion.success is not None else False
            try:
                conn.execute(
                    "UPDATE skill_events SET exit_code=?, success=?, duration_ms=? WHERE id=?",
                    (exit_code, 1 if success else 0, duration_ms, row_id),
                )
                conn.commit()
            except sqlite3.Error:
                logger.warning(
                    "skill_event_context: update failed for %r", skill_name, exc_info=True
                )
            finally:
                conn.close()


# ---------------------------------------------------------------------------
# Hook execution telemetry (ENH-2506)
# ---------------------------------------------------------------------------

_STDERR_PREVIEW_MAX = 512


def record_hook_event(
    db_path: Path | str,
    *,
    ts: str | None = None,
    session_id: str | None,
    event_name: str,
    matcher: str | None,
    script: str | None,
    exit_code: int | None,
    duration_ms: int | None,
    stderr_preview: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
) -> None:
    """Write one row to ``hook_events`` and index it in ``search_index``.

    Live-write-only (ENH-2506): the Claude Code host does not emit hook
    execution results into the transcript JSONL, so there is no backfill
    source and no ``_backfill_hook_events``. Best-effort per the EPIC-1707
    graceful-degradation contract — a missing or locked database is logged
    and swallowed, never raised, mirroring :func:`skill_event_context`.
    """
    if stderr_preview is not None:
        stderr_preview = stderr_preview[:_STDERR_PREVIEW_MAX]
    ts = ts or _now()
    effective_path = resolve_history_db(db_path)
    try:
        conn = connect(effective_path)
    except sqlite3.Error:
        logger.warning("record_hook_event: connect failed for %r", event_name, exc_info=True)
        return
    try:
        conn.execute(
            "INSERT INTO hook_events(ts, session_id, event_name, matcher, script, exit_code, "
            "duration_ms, stderr_preview, head_sha, branch) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                session_id,
                event_name,
                matcher,
                script,
                exit_code,
                duration_ms,
                stderr_preview,
                head_sha,
                branch,
            ),
        )
        _index(
            conn,
            content=f"{event_name} {matcher or ''}".strip(),
            kind="hook_event",
            ref=session_id or "",
            anchor=event_name,
            ts=ts,
        )
        conn.commit()
    except sqlite3.Error:
        logger.warning("record_hook_event: insert failed for %r", event_name, exc_info=True)
    finally:
        conn.close()


@dataclass
class HookEventCompletion:
    """Mutable completion handle yielded by :func:`hook_event_context` (ENH-2506).

    Callers that observe a concrete exit code (e.g. a bash shim capturing
    ``$?``) set ``exit_code`` before the ``with`` block exits. Left untouched,
    a clean exit records ``exit_code=0`` and a raised exception records
    ``exit_code=1`` — mirroring :class:`SkillEventCompletion`.
    """

    exit_code: int | None = None
    stderr_preview: str | None = None


@contextmanager
def hook_event_context(
    db_path: Path | str = DEFAULT_DB_PATH,
    session_id: str | None = None,
    event_name: str = "",
    matcher: str | None = None,
    script: str | None = None,
    config: dict | None = None,
) -> Generator[HookEventCompletion, None, None]:
    """Measure and record one hook fire: ``exit_code``, ``duration_ms``, ``stderr_preview``.

    Best-effort per the EPIC-1707 graceful-degradation contract (matching
    :func:`skill_event_context`): a missing or locked database never blocks
    the wrapped hook body, and this wrap must never alter the wrapped body's
    exit code or swallow behavior — it only observes and records. Uses
    ``time.monotonic()`` for duration (unlike ``cli_event_context``'s
    ``time.time()``), since this measures elapsed wall-clock duration of a
    single fire, not a timestamp.

    The ``config`` parameter is a forward-compatibility gate for
    ``analytics.capture.hooks``; the caller is expected to check the flag
    before entering (mirroring the ``skill_event_context`` stub pattern) —
    this function does not read config itself.
    """
    completion = HookEventCompletion()
    start = time.monotonic()
    ts = _now()
    try:
        yield completion
        if completion.exit_code is None:
            completion.exit_code = 0
    except BaseException:
        if completion.exit_code is None or completion.exit_code == 0:
            completion.exit_code = 1
        raise
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        record_hook_event(
            db_path,
            ts=ts,
            session_id=session_id,
            event_name=event_name,
            matcher=matcher,
            script=script,
            exit_code=completion.exit_code,
            duration_ms=duration_ms,
            stderr_preview=completion.stderr_preview,
        )


# ---------------------------------------------------------------------------
# Commit events (ENH-2458)
# ---------------------------------------------------------------------------

# Issue references in commit messages: "Closes #123", "Fixes ENH-2458",
# "Issue: BUG-99" trailers, plain "(ENH-2458)" mentions.
_COMMIT_MSG_ISSUE_RE = re.compile(
    r"\b(?:closes|fixes|resolves|issue:?)\s*:?\s*#?((?:BUG|ENH|FEAT|EPIC)-\d+|\d+)",
    re.IGNORECASE,
)
_COMMIT_ID_RE = re.compile(r"\b((?:BUG|ENH|FEAT|EPIC)-\d+)\b")
_BRANCH_ISSUE_RE = re.compile(r"((?:BUG|ENH|FEAT|EPIC)-\d+)", re.IGNORECASE)


def _infer_issue_id(message: str, branch: str | None = None) -> str | None:
    """Infer an issue ID from a commit *message* and optional *branch* name.

    Checks (in order): explicit ``Closes/Fixes/Resolves/Issue:`` references,
    any bare ``TYPE-NNN`` token in the message, then branch-name conventions
    (``feat/ENH-2458-...``). Returns ``None`` when nothing matches.
    """
    m = _COMMIT_MSG_ISSUE_RE.search(message)
    if m:
        ref = m.group(1).upper()
        if "-" in ref:
            return ref
        # Bare "#123" — cannot resolve the type prefix; fall through to
        # a typed token elsewhere in the message before giving up.
    m = _COMMIT_ID_RE.search(message)
    if m:
        return m.group(1).upper()
    if branch:
        m = _BRANCH_ISSUE_RE.search(branch)
        if m:
            return m.group(1).upper()
    return None


def record_commit_event(
    db_path: Path | str,
    commit_sha: str,
    message: str,
    *,
    author: str | None = None,
    branch: str | None = None,
    issue_id: str | None = None,
    files: Sequence[str] | None = None,
    parent_sha: str | None = None,
    ts: str | None = None,
    config: dict | None = None,
) -> bool:
    """Write one row to ``commit_events`` and index it in ``search_index``.

    ``issue_id`` is inferred from the message/branch when not given. Idempotent
    via ``INSERT OR IGNORE`` on the ``commit_sha`` UNIQUE constraint; the FTS
    row is only written when the insert actually lands, so repeated calls do
    not duplicate search results. Returns True when a new row was inserted.

    The ``config`` parameter is a forward-compatibility stub for an
    ``analytics.capture.commits`` gate; it is accepted but not yet used.
    """
    if not commit_sha:
        return False
    if issue_id is None:
        issue_id = _infer_issue_id(message, branch)
    files_json = json.dumps(list(files)) if files is not None else None
    conn = connect(db_path)
    ts = ts or _now()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO commit_events("
            "ts, commit_sha, parent_sha, message, author, branch, issue_id, files_json"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, commit_sha, parent_sha, message, author, branch, issue_id, files_json),
        )
        inserted = bool(cursor.rowcount)
        if inserted:
            _index(
                conn,
                content=f"{commit_sha[:12]} {issue_id or ''} {message}".strip()[:512],
                kind="commit",
                ref=commit_sha,
                anchor=issue_id or "",
                ts=ts,
            )
        conn.commit()
    finally:
        conn.close()
    return inserted


def _backfill_commit_events(conn: sqlite3.Connection, repo_root: Path) -> int:
    """Seed ``commit_events`` from ``git log --all`` under *repo_root*.

    Follows the ``_backfill_messages()`` pattern: idempotent via
    ``INSERT OR IGNORE`` on the ``commit_sha`` UNIQUE constraint (the FTS row
    is only written for genuinely new commits). Branch attribution is not
    reconstructed retroactively (``git log --all`` has no unambiguous branch
    per commit), so backfilled rows carry ``branch=NULL``.
    """
    # \x1e separates records, \x1f separates fields: sha, parents, author,
    # author-date (ISO), full message body. --name-only appends touched paths.
    fmt = "%x1e%H%x1f%P%x1f%an%x1f%aI%x1f%B%x1f"
    try:
        proc = subprocess.run(
            ["git", "log", "--all", "--name-only", f"--pretty=format:{fmt}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if proc.returncode != 0:
        return 0
    count = 0
    for record in proc.stdout.split("\x1e"):
        if not record.strip():
            continue
        parts = record.split("\x1f")
        if len(parts) < 6:
            continue
        sha, parents, author, author_date, message, tail = (
            parts[0].strip(),
            parts[1].strip(),
            parts[2].strip(),
            parts[3].strip(),
            parts[4],
            parts[5],
        )
        if not sha:
            continue
        files = [line.strip() for line in tail.splitlines() if line.strip()]
        message = message.strip()
        issue_id = _infer_issue_id(message)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO commit_events("
            "ts, commit_sha, parent_sha, message, author, branch, issue_id, files_json"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                author_date,
                sha,
                parents.split(" ")[0] if parents else None,
                message,
                author or None,
                None,
                issue_id,
                json.dumps(files),
            ),
        )
        if cursor.rowcount:
            _index(
                conn,
                content=f"{sha[:12]} {issue_id or ''} {message}".strip()[:512],
                kind="commit",
                ref=sha,
                anchor=issue_id or "",
                ts=author_date,
            )
            count += 1
    return count


# ---------------------------------------------------------------------------
# Test-run events (ENH-2459)
# ---------------------------------------------------------------------------


def record_test_run_event(
    db_path: Path | str,
    *,
    ts: str,
    ended_at: str | None = None,
    total: int = 0,
    passed: int = 0,
    failed: int = 0,
    errored: int = 0,
    skipped: int = 0,
    duration_s: float | None = None,
    failing_names: Sequence[str] | None = None,
    env_label: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    command: str | None = None,
    config: dict | None = None,
) -> None:
    """Write one row to ``test_run_events`` and index it in ``search_index``.

    ``failing_names`` (pytest node IDs) are stored as a JSON array and also
    fed into the FTS index so ``ll-session search --fts "<test name>"
    --kind test_run`` surfaces the runs where that test failed.

    The ``config`` parameter is a forward-compatibility stub for an
    ``analytics.capture.test_runs`` gate; it is accepted but not yet used.
    """
    names = list(failing_names) if failing_names else []
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO test_run_events("
            "ts, ended_at, total, passed, failed, errored, skipped, duration_s, "
            "failing_names_json, env_label, head_sha, branch, command"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                ended_at,
                total,
                passed,
                failed,
                errored,
                skipped,
                duration_s,
                json.dumps(names),
                env_label,
                head_sha,
                branch,
                command,
            ),
        )
        summary = f"{command or 'pytest'} passed={passed} failed={failed} " + " ".join(names)
        _index(
            conn,
            content=summary.strip()[:512],
            kind="test_run",
            ref=head_sha or "",
            anchor=branch or "",
            ts=ts,
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Orchestration-run events (ENH-2492)
# ---------------------------------------------------------------------------


def record_orchestration_run(
    db_path: Path | str,
    *,
    run_id: str,
    driver: str,
    issue_id: str,
    status: str,
    failure_reason: str | None = None,
    duration_s: float | None = None,
    wave: str | None = None,
    pr_url: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    config: dict | None = None,
) -> bool:
    """UPSERT one per-issue orchestration outcome and refresh its FTS row.

    ``run_id`` identifies the top-level ``ll-auto``, ``ll-parallel``, or
    ``ll-sprint`` invocation. Reusing the same ``(run_id, issue_id)`` for a retry
    replaces the initial result with the final outcome. The matching FTS row is
    deleted and recreated in the same transaction so stale failure text cannot
    remain searchable after a successful retry.

    The ``config`` parameter is a forward-compatibility stub for a future
    ``analytics.capture.orchestration_runs`` gate; it is accepted but unused.
    Returns ``False`` only when the required identity fields are empty.
    """
    if not run_id or not driver or not issue_id or not status:
        return False

    effective_ended_at = ended_at or _now()
    index_ts = effective_ended_at or started_at or _now()
    index_ref = f"{run_id}:{issue_id}"
    conn = connect(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO orchestration_runs("
            "run_id, driver, issue_id, status, failure_reason, duration_s, wave, pr_url, "
            "started_at, ended_at, head_sha, branch"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id, issue_id) DO UPDATE SET "
            "driver=excluded.driver, status=excluded.status, "
            "failure_reason=excluded.failure_reason, duration_s=excluded.duration_s, "
            "wave=excluded.wave, pr_url=excluded.pr_url, "
            "started_at=excluded.started_at, ended_at=excluded.ended_at, "
            "head_sha=excluded.head_sha, branch=excluded.branch",
            (
                run_id,
                driver,
                issue_id,
                status,
                failure_reason,
                duration_s,
                wave,
                pr_url,
                started_at,
                effective_ended_at,
                head_sha,
                branch,
            ),
        )
        conn.execute(
            "DELETE FROM search_index WHERE kind = ? AND ref = ?",
            ("orchestration_run", index_ref),
        )
        _index(
            conn,
            content=(f"{driver} {run_id} {issue_id} {status} {failure_reason or ''}").strip()[:512],
            kind="orchestration_run",
            ref=index_ref,
            anchor=issue_id,
            ts=index_ts,
        )
        conn.commit()
        return bool(cursor.rowcount)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Loop-run summary events (ENH-2463)
# ---------------------------------------------------------------------------


def record_loop_run_summary(
    db_path: Path | str,
    *,
    run_id: str,
    loop_name: str,
    started_at: str | None = None,
    ended_at: str | None = None,
    final_state: str | None = None,
    iterations: int | None = None,
    terminated_by: str | None = None,
    error: str | None = None,
    evaluator_score: float | None = None,
    diagnostics_path: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    config: dict | None = None,
) -> bool:
    """Write one row to ``loop_runs`` and index it in ``search_index`` (ENH-2463).

    ``run_id`` is the archive-time run identifier (see
    :meth:`little_loops.fsm.persistence.RunPersistence.archive_run` for the
    derivation) so this row JOINs cleanly to on-disk
    ``.loops/.history/<run_id>-<loop_name>/`` archives. Idempotent via
    ``INSERT OR IGNORE`` on the ``run_id`` UNIQUE constraint, mirroring
    :func:`record_commit_event` — a resumed-then-completed run contributes
    exactly one row. The FTS row is only written when the insert actually
    lands, so repeated calls do not duplicate search results.

    The ``config`` parameter is a forward-compatibility stub for a future
    ``analytics.capture.loop_runs`` gate; it is accepted but not yet used.
    Returns ``False`` only when the required identity fields are empty or the
    row already existed.
    """
    if not run_id or not loop_name:
        return False
    ts = ended_at or _now()
    conn = connect(db_path)
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO loop_runs("
            "run_id, loop_name, started_at, ended_at, final_state, iterations, "
            "terminated_by, error, evaluator_score, diagnostics_path, head_sha, branch"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                loop_name,
                started_at,
                ts,
                final_state,
                iterations,
                terminated_by,
                error,
                evaluator_score,
                diagnostics_path,
                head_sha,
                branch,
            ),
        )
        inserted = bool(cursor.rowcount)
        if inserted:
            _index(
                conn,
                content=f"{loop_name} {final_state or ''} {terminated_by or ''}".strip()[:512],
                kind="loop_run",
                ref=run_id,
                anchor=loop_name,
                ts=ts,
            )
        conn.commit()
    finally:
        conn.close()
    return inserted


# ---------------------------------------------------------------------------
# Live usage_events writer (ENH-2724)
# ---------------------------------------------------------------------------


def record_usage_event(
    db_path: Path | str,
    *,
    run_id: str,
    ts: str,
    state: str | None,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_creation_tokens: int,
) -> None:
    """Write one live per-invocation row to ``usage_events`` (ENH-2724).

    Unlike :func:`_backfill_usage_events` (post-hoc, ``state`` always ``NULL``),
    this is called at loop-run finish with the FSM state each invocation ran in
    already known. ``usage_events`` has no uniqueness constraint — plain
    ``INSERT``, one row per :class:`~little_loops.subprocess_utils.TokenUsage`.
    """
    from little_loops.pricing import estimate_cost_usd

    cost_usd = estimate_cost_usd(
        model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens
    )
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO usage_events(ts, model, state, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens, cost_usd, run_id) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                model,
                state,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_creation_tokens,
                cost_usd,
                run_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_loop_run_diagnostics(db_path: Path | str, run_id: str, diagnostics_path: str) -> bool:
    """Link a ``loop-specialist``-written diagnostics artifact to its ``loop_runs`` row.

    A single ``UPDATE ... WHERE run_id = ?``, mirroring the
    ``skill_event_context`` completion-UPDATE pattern. Best-effort by design:
    returns ``False`` (does not raise) when no matching row exists yet.
    """
    if not run_id or not diagnostics_path:
        return False
    conn = connect(db_path)
    try:
        cursor = conn.execute(
            "UPDATE loop_runs SET diagnostics_path = ? WHERE run_id = ?",
            (diagnostics_path, run_id),
        )
        conn.commit()
    finally:
        conn.close()
    return bool(cursor.rowcount)


# ---------------------------------------------------------------------------
# Learning Test Registry mirror (ENH-2466)
# ---------------------------------------------------------------------------


def record_learning_test_event(
    db_path: Path | str,
    target: str,
    file_path: str,
    config: dict | None = None,
) -> bool:
    """UPSERT one Learning Test Registry record mirror and refresh its FTS row.

    Reads the registry file at *file_path* (YAML frontmatter parsed the same
    way as :func:`little_loops.learning_tests._read_frontmatter_yaml`) and
    upserts it into ``learning_test_events`` keyed on ``record_id`` — the
    slugified *target*, matching the registry's own file-stem identity. A
    re-prove (or ``mark_stale``) overwrites the existing row's ``status``,
    ``assertions_json``, and ``date`` rather than inserting a duplicate. The
    matching FTS row is deleted and recreated in the same transaction so
    stale assertion text cannot remain searchable after a status change.

    Best-effort per the EPIC-1707 graceful-degradation contract: returns
    ``False`` (does not raise) when *file_path* is missing/unreadable or
    frontmatter fails to parse; callers should also wrap the call in
    ``try/except: pass`` or ``contextlib.suppress(Exception)`` per the
    ``record_issue_snapshot``/``record_commit_event`` precedent.

    The ``config`` parameter is a forward-compatibility stub for a future
    ``analytics.capture.learning_tests`` gate; it is accepted but not yet used.
    """
    from little_loops.issue_parser import slugify
    from little_loops.learning_tests import _read_frontmatter_yaml

    if not target:
        return False
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return False
    data = _read_frontmatter_yaml(content)
    if not data:
        return False

    record_id = slugify(target)
    status = data.get("status")
    date = data.get("date")
    raw_output_path = data.get("raw_output_path")
    assertions = data.get("assertions") or []
    assertions_json = json.dumps(assertions)
    claims = " ".join(str(a.get("claim", "")) for a in assertions if isinstance(a, dict))

    conn = connect(db_path)
    ts = _now()
    try:
        conn.execute(
            "INSERT INTO learning_test_events"
            "(ts, record_id, target, status, assertions_json, date, raw_output_path)"
            " VALUES(?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(record_id) DO UPDATE SET"
            " ts=excluded.ts, target=excluded.target, status=excluded.status,"
            " assertions_json=excluded.assertions_json, date=excluded.date,"
            " raw_output_path=excluded.raw_output_path",
            (ts, record_id, target, status, assertions_json, date, raw_output_path),
        )
        conn.execute(
            "DELETE FROM search_index WHERE kind = ? AND ref = ?",
            ("learning_test", record_id),
        )
        _index(
            conn,
            content=f"{target} {claims}".strip()[:512],
            kind="learning_test",
            ref=record_id,
            anchor=target,
            ts=ts,
        )
        conn.commit()
    finally:
        conn.close()
    return True


def _backfill_learning_test_events(conn: sqlite3.Connection, registry_dir: Path) -> int:
    """Seed ``learning_test_events`` from ``.ll/learning-tests/*.md`` (ENH-2466).

    Follows the ``_backfill_snapshots()`` pattern: iterates ``*.md`` files,
    reads frontmatter, inserts with ``INSERT OR IGNORE`` on the ``record_id``
    UNIQUE constraint so re-running the backfill (or a record already written
    by :func:`record_learning_test_event`) does not duplicate rows. This is a
    best-effort reconcile companion for registry files edited outside the
    ``ll-learning-tests`` CLI — it does not overwrite a live-written row's
    newer status, unlike the CLI-path UPSERT.
    """
    from little_loops.issue_parser import slugify
    from little_loops.learning_tests import _read_frontmatter_yaml

    if not registry_dir.is_dir():
        return 0
    count = 0
    ts = _now()
    for md_file in sorted(registry_dir.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
        data = _read_frontmatter_yaml(content)
        if not data:
            continue
        target = data.get("target")
        if not target:
            continue
        record_id = slugify(target)
        status = data.get("status")
        date = data.get("date")
        raw_output_path = data.get("raw_output_path")
        assertions = data.get("assertions") or []
        assertions_json = json.dumps(assertions)
        claims = " ".join(str(a.get("claim", "")) for a in assertions if isinstance(a, dict))
        cursor = conn.execute(
            "INSERT OR IGNORE INTO learning_test_events"
            "(ts, record_id, target, status, assertions_json, date, raw_output_path)"
            " VALUES(?, ?, ?, ?, ?, ?, ?)",
            (ts, record_id, target, status, assertions_json, date, raw_output_path),
        )
        if cursor.rowcount:
            _index(
                conn,
                content=f"{target} {claims}".strip()[:512],
                kind="learning_test",
                ref=record_id,
                anchor=target,
                ts=ts,
            )
        count += 1
    return count


# ---------------------------------------------------------------------------
# Session-lifecycle events (ENH-2495 / ENH-2509)
# ---------------------------------------------------------------------------


def record_session_lifecycle_event(
    db_path: Path | str,
    *,
    session_id: str | None,
    event: str,
    detail: dict | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    ts: str | None = None,
) -> bool:
    """Write one row to ``session_lifecycle_events`` and index it in ``search_index``.

    Records session-lifecycle / handoff transitions (``handoff_needed``,
    ``compaction``, ``stale_ref_sweep``, plus ENH-2509's ``worktree_*``
    discriminators). Best-effort per the EPIC-1707 graceful-degradation
    contract: returns ``False`` (never raises) on any ``sqlite3.Error`` so a
    hook's primary job is never blocked by a missing/locked database.
    """
    detail_json = json.dumps(detail) if detail is not None else None
    ts = ts or _now()
    conn: sqlite3.Connection | None = None
    try:
        conn = connect(db_path)
        conn.execute(
            "INSERT INTO session_lifecycle_events"
            "(ts, session_id, event, detail, head_sha, branch)"
            " VALUES(?, ?, ?, ?, ?, ?)",
            (ts, session_id, event, detail_json, head_sha, branch),
        )
        _index(
            conn,
            content=f"{event} {session_id or ''} {json.dumps(detail or {})}"[:512],
            kind="session_lifecycle",
            ref=session_id or "",
            anchor=event,
            ts=ts,
        )
        conn.commit()
    except sqlite3.Error:
        logger.warning(
            "record_session_lifecycle_event: insert failed for event=%r", event, exc_info=True
        )
        return False
    finally:
        if conn is not None:
            conn.close()
    return True


# ---------------------------------------------------------------------------
# Subagent-run events (ENH-2505)
# ---------------------------------------------------------------------------


def record_subagent_run_start(
    db_path: Path | str,
    *,
    parent_session_id: str | None,
    agent_id: str | None,
    agent_type: str | None,
    started_at: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    ts: str | None = None,
) -> bool:
    """Write one row to ``subagent_runs`` for a ``SubagentStart`` spawn.

    Idempotent via ``INSERT OR IGNORE`` on the ``(parent_session_id, agent_id)``
    UNIQUE constraint, mirroring :func:`record_commit_event` — a replayed
    SubagentStart (e.g. backfill re-run) contributes exactly one row. Best-effort
    per the EPIC-1707 contract: returns ``False`` (never raises) on any
    ``sqlite3.Error`` or a missing ``agent_id``.
    """
    if not agent_id:
        return False
    ts = ts or _now()
    started_at = started_at or ts
    conn: sqlite3.Connection | None = None
    try:
        conn = connect(db_path)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO subagent_runs("
            "ts, parent_session_id, agent_id, agent_type, started_at, status, "
            "head_sha, branch"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, parent_session_id, agent_id, agent_type, started_at, "running", head_sha, branch),
        )
        inserted = bool(cursor.rowcount)
        if inserted:
            _index(
                conn,
                content=f"{agent_type or ''} {agent_id} {parent_session_id or ''}".strip()[:512],
                kind="subagent_run",
                ref=agent_id,
                anchor=agent_type or "",
                ts=ts,
            )
        conn.commit()
    except sqlite3.Error:
        logger.warning(
            "record_subagent_run_start: insert failed for agent_id=%r", agent_id, exc_info=True
        )
        return False
    finally:
        if conn is not None:
            conn.close()
    return inserted


def record_subagent_run_stop(
    db_path: Path | str,
    *,
    parent_session_id: str | None,
    agent_id: str | None,
    agent_type: str | None = None,
    agent_transcript_path: str | None = None,
    status: str = "completed",
    ended_at: str | None = None,
) -> bool:
    """Update the matching ``subagent_runs`` row for a ``SubagentStop`` event.

    Matches on the ``(parent_session_id, agent_id)`` composite key. Best-effort:
    returns ``False`` (never raises) when no matching row exists yet, the
    ``agent_id`` is missing, or a ``sqlite3.Error`` occurs — mirroring
    :func:`update_loop_run_diagnostics`.
    """
    if not agent_id:
        return False
    ended_at = ended_at or _now()
    conn: sqlite3.Connection | None = None
    try:
        conn = connect(db_path)
        cursor = conn.execute(
            "UPDATE subagent_runs SET ended_at = ?, status = ?, "
            "agent_transcript_path = COALESCE(?, agent_transcript_path), "
            "agent_type = COALESCE(?, agent_type) "
            "WHERE agent_id = ? AND parent_session_id IS ?",
            (ended_at, status, agent_transcript_path, agent_type, agent_id, parent_session_id),
        )
        conn.commit()
    except sqlite3.Error:
        logger.warning(
            "record_subagent_run_stop: update failed for agent_id=%r", agent_id, exc_info=True
        )
        return False
    finally:
        if conn is not None:
            conn.close()
    return bool(cursor.rowcount)


def _backfill_subagent_runs(conn: sqlite3.Connection, sessions_root: Path) -> int:
    """Seed ``subagent_runs`` from nested ``subagents/agent-<id>.jsonl`` transcripts.

    Discovers subagent transcripts under each parent session's transcript
    directory (``<session-dir>/subagents/*.jsonl``) and writes one completed row
    per nested file found, since a persisted transcript implies the spawn ran to
    completion (the live ``SubagentStart``/``SubagentStop`` hooks capture
    ``running``/``failed``/``timeout`` states that backfill cannot reconstruct
    after the fact). Idempotent via the same ``INSERT OR IGNORE`` as the live
    writer.
    """
    count = 0
    for subagents_dir in sessions_root.glob("*/subagents"):
        parent_session_id = subagents_dir.parent.name
        for transcript in subagents_dir.glob("*.jsonl"):
            agent_id = transcript.stem
            try:
                mtime = datetime.fromtimestamp(transcript.stat().st_mtime, tz=UTC).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
            except OSError:
                continue
            cursor = conn.execute(
                "INSERT OR IGNORE INTO subagent_runs("
                "ts, parent_session_id, agent_id, agent_transcript_path, started_at, "
                "ended_at, status"
                ") VALUES(?, ?, ?, ?, ?, ?, ?)",
                (mtime, parent_session_id, agent_id, str(transcript), mtime, mtime, "completed"),
            )
            if cursor.rowcount:
                count += 1
    return count


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------


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
    conn = connect(db)
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
    test_run, usage, orchestration_run.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {sorted(VALID_KINDS)}")
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

_ISSUE_TRANSITION_MAP: dict[str, str] = {
    "issue.completed": "done",
    "issue.closed": "done",
    "issue.deferred": "deferred",
    "issue.skipped": "cancelled",
    "issue.created": "open",
    "issue.started": "in_progress",
}


def _derive_transition(event_type: str) -> str:
    """Map an ``issue.*`` event type to the canonical transition/status string."""
    return _ISSUE_TRANSITION_MAP.get(event_type, event_type.split(".", 1)[1])


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
        self._path = resolve_history_db(db_path)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        try:
            ensure_db(self._path)
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
            _configure_connection(self._conn)
        except sqlite3.Error:
            logger.warning(
                "SQLiteTransport: could not open %s; sink disabled", self._path, exc_info=True
            )
            self._conn = None

    def send(self, event: dict[str, Any]) -> None:
        """Record a recognised event as a ``loop_events`` or ``issue_events`` row (best-effort)."""
        conn = self._conn
        if conn is None:
            return
        event_type = str(event.get("event", ""))
        ts = str(event.get("ts") or _now())
        try:
            with self._lock:
                if event_type in _LOOP_EVENT_TYPES:
                    loop_name = str(event.get("loop_name", "")) or None
                    state = event.get("state")
                    if event_type == "loop_complete":
                        state = event.get("outcome", state)
                    retries = event.get("retries")
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
                elif event_type.startswith("issue."):
                    issue_id = event.get("issue_id")
                    transition = _derive_transition(event_type)
                    # Authoritative session linkage (ENH-2462): producers put the
                    # emitting session's ID in the payload; both snake_case and
                    # the host JSONL camelCase spelling are accepted.
                    session_id = event.get("session_id") or event.get("sessionId")
                    conn.execute(
                        "INSERT OR IGNORE INTO issue_events("
                        "ts, issue_id, transition, discovered_by, "
                        "issue_type, priority, captured_at, completed_at, session_id"
                        ") VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            ts,
                            issue_id,
                            transition,
                            event.get("discovered_by"),
                            event.get("issue_type"),
                            event.get("priority"),
                            event.get("captured_at"),
                            event.get("completed_at"),
                            str(session_id) if session_id else None,
                        ),
                    )
                    _index(
                        conn,
                        content=f"{issue_id or ''} {event.get('issue_type', '')}".strip(),
                        kind="issue",
                        ref=str(issue_id or ""),
                        anchor=event.get("issue_file", ""),
                        ts=ts,
                    )
                    # Side-effect: write content snapshot when the event carries a file path.
                    file_path = event.get("file_path")
                    if file_path and issue_id and transition in ("done", "open", "cancelled"):
                        try:
                            conn.commit()  # flush issue_events before spawning new conn
                        except sqlite3.Error:
                            pass
                        record_issue_snapshot(self._path, str(issue_id), transition, str(file_path))
                        return  # skip second commit below; record_issue_snapshot committed
                else:
                    return
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


def _normalize_agent_type(subagent_type: Any) -> str | None:
    """Strip the ``ll:`` plugin prefix so built-in and plugin agent names group together.

    ``Task`` tool spawns carry ``subagent_type`` as either a bare name
    (``Explore``) or an ``ll:``-prefixed plugin agent (``ll:codebase-locator``);
    without normalization these count as distinct agents in aggregation.
    """
    if not isinstance(subagent_type, str) or not subagent_type:
        return None
    normalized = subagent_type.removeprefix("ll:")
    return normalized or None


_MCP_TOOL_NAME_RE = re.compile(r"^mcp__(.+?)__(.+)$")


def _parse_mcp_tool_name(tool_name: str) -> tuple[str | None, str | None]:
    """Split ``mcp__<server>__<tool>`` into ``(server, tool)``, else ``(None, None)``."""
    match = _MCP_TOOL_NAME_RE.match(tool_name)
    if not match:
        return None, None
    return match.group(1), match.group(2)


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
            m = _FILENAME_TYPE_RE.search(issue_file.name)
            if m:
                issue_id = f"{m.group(1)}-{m.group(2)}"
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
            "INSERT OR IGNORE INTO issue_events("
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


def _backfill_snapshots(conn: sqlite3.Connection, issues_dir: Path) -> int:
    """Seed ``issue_snapshots`` and ``search_index`` from issue files under *issues_dir*.

    Follows the ``_backfill_issues()`` pattern: iterates ``*.md`` files, reads
    frontmatter + body, inserts with ``INSERT OR IGNORE`` for idempotency.
    Uses the issue's current ``status`` as the ``transition`` value.
    """
    from little_loops.frontmatter import parse_frontmatter, strip_frontmatter

    count = 0
    ts = _now()
    for issue_file in sorted(issues_dir.rglob("*.md")):
        try:
            content = issue_file.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = parse_frontmatter(content)
        issue_id = fm.get("id")
        if not issue_id:
            m = _FILENAME_TYPE_RE.search(issue_file.name)
            if m:
                issue_id = f"{m.group(1)}-{m.group(2)}"
        if not issue_id:
            continue
        transition = str(fm.get("status", "open"))
        title = fm.get("title") or fm.get("id") or issue_id
        priority = fm.get("priority")
        issue_type = fm.get("type")
        body = strip_frontmatter(content)
        fm_json = json.dumps({k: str(v) for k, v in fm.items() if v is not None}, sort_keys=True)
        conn.execute(
            "INSERT OR IGNORE INTO issue_snapshots"
            "(ts, issue_id, transition, title, priority, issue_type, body, frontmatter)"
            " VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, str(issue_id), transition, str(title), priority, issue_type, body, fm_json),
        )
        _index(
            conn,
            content=f"{issue_id} {title} {body or ''}".strip(),
            kind="snapshot",
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


def _iter_events(source: list[Path] | sqlite3.Cursor) -> Generator[tuple[str, str], None, None]:
    """Yield ``(raw_line, source_label)`` pairs from JSONL files or a raw_events cursor.

    Lets the JSONL-derived ``_backfill_*`` functions accept either a legacy
    ``list[Path]`` (re-reads files line-by-line) or a ``raw_events`` cursor
    selecting ``(raw_line, source_path)`` rows in that order — the
    :func:`rebuild` path, replaying previously-ingested lines instead of
    re-reading the filesystem (ENH-2581). Cursor-sourced ``raw_line`` values pass
    through :func:`_unpack_payload` (compressed BLOB → text; legacy TEXT unchanged).
    """
    if isinstance(source, sqlite3.Cursor):
        for row in source:
            yield _unpack_payload(row[0]), row[1]
        return
    for jsonl_file in source:
        try:
            handle = jsonl_file.open(encoding="utf-8")
        except OSError:
            continue
        with handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield line, str(jsonl_file)


def _backfill_tool_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int:
    """Seed ``tool_events`` from assistant tool-use blocks in session JSONL files.

    *source* is either a list of on-disk JSONL files (legacy) or a
    ``raw_events`` cursor (the :func:`rebuild` path) — see :func:`_iter_events`.
    """
    count = 0
    for line, source_label in _iter_events(source):
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
            agent_type = (
                _normalize_agent_type(args.get("subagent_type"))
                if tool_name == "Task" and isinstance(args, dict)
                else None
            )
            mcp_server, mcp_tool = _parse_mcp_tool_name(tool_name)
            conn.execute(
                "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, "
                "result_size, bytes_in, bytes_out, cache_hit, agent_type, "
                "mcp_server, mcp_tool) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ts,
                    session_id,
                    tool_name,
                    _hash_args(args),
                    None,
                    None,
                    None,
                    None,
                    agent_type,
                    mcp_server,
                    mcp_tool,
                ),
            )
            _index(
                conn,
                content=f"{tool_name} {agent_type or ''}".strip(),
                kind="tool",
                ref=tool_name,
                anchor=source_label,
                ts=ts,
            )
            count += 1
    return count


def _load_loop_run_windows(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Return ``(started_at, ended_at, run_id)`` triples for run_id backfill joins.

    ``loop_runs`` has no ``session_id`` (ENH-2725 research), so this is the only
    correlation available between a ``usage_events`` row and its owning run: a
    timestamp-window join. Rows with a NULL boundary can't participate in a
    window comparison and are excluded up front.
    """
    rows = conn.execute(
        "SELECT started_at, ended_at, run_id FROM loop_runs "
        "WHERE started_at IS NOT NULL AND ended_at IS NOT NULL"
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def _derive_run_id_for_ts(ts: str, windows: list[tuple[str, str, str]]) -> str | None:
    """Stamp ``run_id`` only when exactly one ``loop_runs`` window contains *ts*.

    Concurrent/overlapping ``loop_runs`` (e.g. ``ll-parallel`` worktree runs)
    make the join ambiguous; per the ENH-2725 decision, ambiguous or
    zero-match rows stay ``NULL`` rather than guessing (Option A).
    """
    if not ts:
        return None
    matches = [run_id for started_at, ended_at, run_id in windows if started_at <= ts <= ended_at]
    return matches[0] if len(matches) == 1 else None


def _backfill_usage_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int:
    """Seed ``usage_events`` from assistant ``message.usage`` blocks (ENH-2461).

    Persists the real LLM token counts the API returned (``input_tokens``,
    ``output_tokens``, ``cache_read_input_tokens``,
    ``cache_creation_input_tokens``) plus a derived ``cost_usd``, one row per
    assistant turn. The on-disk transcript carries the usage block on
    ``type == "assistant"`` records at ``message.usage`` — verified against live
    session files. (The ``type == "result"`` shape referenced in earlier issue
    research only exists in the *live* subprocess stdout stream, which
    ``raw_events`` never ingests.) The ``state`` column is always ``NULL`` here:
    the transcript stream carries no FSM-state boundary, so per-state grain is
    not derivable from this source (ENH-2461 Addendum 2). *source* accepts either
    JSONL files or a ``raw_events`` cursor — see :func:`_iter_events`.

    ``run_id`` is backfilled via a timestamp-window join against ``loop_runs``
    (ENH-2725) — see :func:`_derive_run_id_for_ts`. Rows with no derivable
    ``run_id`` stay ``NULL``, matching the live-writer path's behavior for
    non-loop sessions.
    """
    from little_loops.pricing import estimate_cost_usd

    count = 0
    windows = _load_loop_run_windows(conn)
    for line, source_label in _iter_events(source):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        cache_read = usage.get("cache_read_input_tokens")
        cache_creation = usage.get("cache_creation_input_tokens")
        # Every real usage block carries at least input/output; skip rows with
        # no token signal at all (defensive against malformed/partial records).
        if input_tokens is None and output_tokens is None:
            continue
        session_id = record.get("sessionId")
        ts = str(record.get("timestamp") or "")
        model = message.get("model")
        cost_usd = estimate_cost_usd(
            str(model or ""),
            int(input_tokens or 0),
            int(output_tokens or 0),
            int(cache_read or 0),
            int(cache_creation or 0),
        )
        run_id = _derive_run_id_for_ts(ts, windows)
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, model, state, input_tokens, "
            "output_tokens, cache_read_input_tokens, cache_creation_input_tokens, cost_usd, "
            "run_id) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                session_id,
                model,
                None,
                input_tokens,
                output_tokens,
                cache_read,
                cache_creation,
                cost_usd,
                run_id,
            ),
        )
        _index(
            conn,
            content=f"{model or ''} usage",
            kind="usage",
            ref=str(model or ""),
            anchor=source_label,
            ts=ts,
        )
        count += 1
    return count


def _backfill_messages(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int:
    """Seed ``message_events`` from user blocks in session JSONL files.

    Mirrors :func:`_backfill_tool_events` but selects ``type == "user"`` records
    and inserts the user's textual content. Used by analyze_workflows() so
    workflow analysis can read message bodies from the DB instead of a JSONL
    file (ENH-1621). *source* accepts either JSONL files or a raw_events
    cursor — see :func:`_iter_events`.
    """
    count = 0
    for line, source_label in _iter_events(source):
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
            anchor=source_label,
            ts=ts,
        )
        count += 1
    return count


def _backfill_assistant_messages(
    conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor
) -> int:
    """Seed ``assistant_messages`` from assistant blocks in session JSONL files.

    Mirrors :func:`_backfill_messages` but selects ``type == "assistant"`` records
    and concatenates text blocks with ``"\\n\\n"`` — matching the output shape of
    ``_extract_turn_pairs()`` in ``user_messages.py``. Also counts ``tool_use``
    blocks and stores the count in ``tool_use_count`` so filter predicates like
    ``min_tool_invocations`` (ENH-1941) can operate without a JOIN.

    Idempotent: INSERT OR IGNORE prevents duplicate rows on repeated backfill.
    Depends on the ``sessions`` table (v4 / ENH-1710) for the session_id→JSONL
    mapping used by ``conversation_turns()`` to JOIN on session_id. *source*
    accepts either JSONL files or a raw_events cursor — see :func:`_iter_events`.
    """
    count = 0
    for line, source_label in _iter_events(source):
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
        # Collect text blocks and count tool_use blocks
        text_blocks: list[str] = []
        tool_use_count = 0
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    txt = block.get("text", "").strip()
                    if txt:
                        text_blocks.append(txt)
                elif block.get("type") == "tool_use":
                    tool_use_count += 1
        if not text_blocks:
            continue
        concatenated = "\n\n".join(text_blocks)
        conn.execute(
            "INSERT OR IGNORE INTO assistant_messages(ts, session_id, content, tool_use_count)"
            " VALUES(?, ?, ?, ?)",
            (ts, str(session_id) if session_id else None, concatenated, tool_use_count),
        )
        _index(
            conn,
            content=concatenated[:512],
            kind="message",
            ref=str(session_id) if session_id else "",
            anchor=source_label,
            ts=ts,
        )
        count += 1
    return count


_BACKFILL_SKILL_RE = re.compile(r"<command-name>/ll:(\S+)")
_BACKFILL_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)


def _backfill_skill_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int:
    """Seed ``skill_events`` from /ll: invocations in user blocks of session JSONL files.

    Mirrors :func:`_backfill_messages` but selects ``type == "user"`` records and
    matches the ``<command-name>/ll:<name></command-name>`` signal. Populates the
    ``skill_events`` table that was added in schema v7 (ENH-1833) but never extended
    to include a backfill path (BUG-2283). Used by ``ll-logs stats`` so pre-init
    invocations are reflected in skill invocation counts. *source* accepts either
    JSONL files or a raw_events cursor — see :func:`_iter_events`.
    """
    count = 0
    for line, source_label in _iter_events(source):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "user":
            continue
        session_id = record.get("sessionId")
        ts = str(record.get("timestamp") or "")
        content = record.get("message", {}).get("content", "")
        if isinstance(content, list):
            text = ""
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if text:
                        break
        elif isinstance(content, str):
            text = content
        else:
            text = ""
        if not text:
            continue
        m = _BACKFILL_SKILL_RE.search(text)
        if not m:
            continue
        skill_name = m.group(1)
        if skill_name.endswith("</command-name>"):
            skill_name = skill_name[: -len("</command-name>")]
        args_m = _BACKFILL_ARGS_RE.search(text)
        args = args_m.group(1).strip()[:200] if args_m else ""
        conn.execute(
            "INSERT INTO skill_events(ts, session_id, skill_name, args) VALUES(?, ?, ?, ?)",
            (ts, str(session_id) if session_id else None, skill_name, args),
        )
        _index(
            conn,
            content=skill_name,
            kind="skill",
            ref=str(session_id) if session_id else "",
            anchor=source_label,
            ts=ts,
        )
        count += 1
    return count


def mine_corrections_from_messages(conn: sqlite3.Connection, config: dict | None = None) -> int:
    """Scan ``message_events`` and insert matching rows into ``user_corrections``.

    Designed for both the one-time retroactive pass over existing rows and
    repeated calls during backfill; idempotent via ``INSERT OR IGNORE`` +
    ``idx_corrections_dedup``. Only writes a ``search_index`` entry when the
    row is actually inserted (rowcount == 1) to avoid duplicate FTS rows.
    Gated by ``analytics.capture.corrections`` (ENH-1841).

    Returns the count of newly inserted correction rows.
    """
    extra_patterns: list[str] = []
    if config is not None:
        from little_loops.config.features import AnalyticsCaptureConfig

        capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
        if not capture.corrections:
            return 0
        extra_patterns = capture.correction_patterns

    count = 0
    rows = conn.execute("SELECT ts, session_id, content FROM message_events").fetchall()
    for ts, session_id, content in rows:
        if not content or not is_correction(content, extra_patterns=extra_patterns):
            continue
        text = content[:512]
        cursor = conn.execute(
            "INSERT OR IGNORE INTO user_corrections(ts, session_id, content, source)"
            " VALUES(?, ?, ?, 'backfill')",
            (ts, session_id, text),
        )
        if cursor.rowcount:
            _index(
                conn,
                content=text,
                kind="correction",
                ref=session_id or "",
                anchor="backfill",
                ts=ts,
            )
            count += 1
    return count


# ---------------------------------------------------------------------------
# Compaction — LCM-style summary DAG (FEAT-1712)
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Rough token estimate using the LCM convention: 4 characters per token."""
    return len(text) // 4


def _summarize_block(
    messages: list[str],
    budget: int,
    *,
    model: str | None = None,
    timeout: int = 60,
) -> str:
    """Summarize block_text to fit within budget tokens, with convergence guarantee.

    LCM Algorithm 3 three-level escalation:

    1. **Level 1**: Normal LLM summary (preserve details), target = budget.
       Accepted only if ``_estimate_tokens(result) < _estimate_tokens(input)``.
    2. **Level 2**: Aggressive bullet-point LLM summary at ``budget // 2``.
       Triggered when level-1 output is not smaller than input.
    3. **Level 3**: Deterministic truncation — ``min(budget * 4, 2048)`` characters.
       Guaranteed to produce output ≤ input by construction.
    Escalations are logged at WARNING level for operator visibility.
    """

    block_text = "\n---\n".join(messages)

    est_input = _estimate_tokens(block_text)

    # Short-circuit: for very small inputs an LLM summary cannot be meaningfully
    # smaller than the input — skip directly to deterministic truncation.
    if est_input < 25:
        return block_text[: min(budget * 4, 2048)]

    # -- Level 1: normal prose summary -------------------------------------------------
    level1_prompt = (
        "Summarize these session messages concisely (2-3 paragraphs), capturing key "
        "topics, decisions, and outcomes. Target approximately "
        f"{budget} tokens:\n\n" + block_text
    )
    result = _call_llm_for_summary(level1_prompt, model=model, timeout=timeout)
    if result and _estimate_tokens(result) < est_input:
        return result

    # -- Level 2: aggressive bullet-point summary at half budget -----------------------
    if result:
        logger.warning(
            "_summarize_block: level-1 summary not smaller than input "
            "(est_output=%d >= est_input=%d); escalating to level 2",
            _estimate_tokens(result),
            est_input,
        )
    else:
        logger.warning("_summarize_block: level-1 LLM call failed; escalating to level 2")
    level2_budget = max(budget // 2, 64)
    level2_prompt = (
        "Summarize these session messages as a compact bullet list. Be extremely terse: "
        "one line per key point, no preamble or commentary. Target approximately "
        f"{level2_budget} tokens:\n\n" + block_text
    )
    result = _call_llm_for_summary(level2_prompt, model=model, timeout=timeout)
    if result and _estimate_tokens(result) < est_input:
        return result

    # -- Level 3: deterministic truncation (guaranteed convergence) --------------------
    if result:
        logger.warning(
            "_summarize_block: level-2 summary not smaller than input "
            "(est_output=%d >= est_input=%d); escalating to level 3",
            _estimate_tokens(result),
            est_input,
        )
    else:
        logger.warning("_summarize_block: level-2 LLM call failed; escalating to level 3")
    # Truncation: min(budget * 4, 2048) chars. The 2048 cap (~512 tokens at 4 chars/token)
    # follows the LCM paper's level-3 constant, providing a strict convergence guarantee.
    max_chars = min(budget * 4, 2048)
    return block_text[:max_chars]


def _call_llm_for_summary(
    prompt: str,
    *,
    model: str | None = None,
    timeout: int = 60,
) -> str | None:
    """Call the host LLM for a summary and extract the prose ``result`` field.

    Returns the extracted prose string on success, or ``None`` if the LLM call
    failed or produced an unparseable response (allowing escalation logic to
    fall through to the next level).
    """

    try:
        inv = resolve_host().build_blocking_json(prompt=prompt, model=model)
        proc = subprocess.run(
            [inv.binary, *inv.args],
            env={**os.environ, **inv.env},
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("_call_llm_for_summary: LLM call timed out after %ds", timeout)
        return None
    except FileNotFoundError:
        logger.error(
            "_call_llm_for_summary: %s CLI not found. Install the active host CLI "
            "(see LL_HOST_CLI).",
            inv.binary,
        )
        return None

    if proc.returncode != 0:
        stderr_preview = proc.stderr.strip()[:200] if proc.stderr else "(no stderr)"
        logger.error(
            "_call_llm_for_summary: %s CLI returned exit code %d (stderr: %s)",
            inv.binary,
            proc.returncode,
            stderr_preview,
        )
        return None

    if not proc.stdout.strip():
        stderr_info = proc.stderr.strip()[:200] if proc.stderr else ""
        logger.error(
            "_call_llm_for_summary: %s CLI returned empty stdout on exit 0"
            + (f" (stderr: {stderr_info})" if stderr_info else "")
        )
        return None

    # Parse the JSON envelope and extract the 'result' field — see
    # evaluate_llm_structured() at fsm/evaluators.py:832-880 for the
    # canonical envelope-parsing pattern.
    try:
        stdout = proc.stdout.strip()
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            # Try JSONL: take the last non-empty line
            lines = [line for line in stdout.split("\n") if line.strip()]
            if not lines:
                raise
            envelope = json.loads(lines[-1])

        # Check for structured-output retry exhaustion or legacy is_error
        if envelope.get("subtype") == "error_max_structured_output_retries":
            logger.error(
                "_call_llm_for_summary: %s CLI could not produce valid output after retries",
                inv.binary,
            )
            return None
        if envelope.get("is_error", False):
            err_text = str(envelope.get("result", "") or "")[:200]
            logger.error(
                "_call_llm_for_summary: %s CLI reported error: %s",
                inv.binary,
                err_text,
            )
            return None

        # Extract the result field (plain prose; no --json-schema here)
        result = envelope.get("result", "")
        if not result:
            logger.error(
                "_call_llm_for_summary: empty result field in %s CLI response",
                inv.binary,
            )
            return None
        return str(result)

    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raw_preview = proc.stdout[:300] if proc.stdout else "(empty)"
        logger.error(
            "_call_llm_for_summary: failed to parse LLM response: %s (raw: %s)",
            e,
            raw_preview,
        )
        return None


def _compact_session_conn(
    conn: sqlite3.Connection,
    session_id: str,
    budget: int = 4096,
    *,
    model: str | None = None,
    timeout: int = 60,
) -> int:
    """Compact one session using an existing connection. Returns new leaf node count.

    Greedy single-pass block grouping: token estimate ``len(s) // 4``. Each block
    gets one ``leaf`` summary_node; if the session accumulates ≥ 2 leaves a single
    ``condensed`` node is inserted (or silently skipped if one already exists via
    ``INSERT OR IGNORE`` + ``idx_summary_nodes_condensed_dedup``). Leaf dedup is
    handled by ``idx_summary_nodes_leaf_dedup`` on ``(session_id, ts_start, ts_end)``.
    """
    rows = conn.execute(
        "SELECT id, ts, content FROM message_events WHERE session_id = ? ORDER BY ts, id",
        (session_id,),
    ).fetchall()

    if not rows:
        return 0

    # Greedy block accumulation
    blocks: list[list[tuple[int, str, str]]] = []
    current: list[tuple[int, str, str]] = []
    current_tokens = 0

    for row in rows:
        msg_id, ts, content = row[0], row[1], row[2] or ""
        tok = _estimate_tokens(content)
        if current_tokens + tok > budget and current:
            blocks.append(current)
            current = [(msg_id, ts, content)]
            current_tokens = tok
        else:
            current.append((msg_id, ts, content))
            current_tokens += tok
    if current:
        blocks.append(current)

    now = _now()
    new_leaves = 0

    for block in blocks:
        ts_start = block[0][1]
        ts_end = block[-1][1]
        msg_ids = [r[0] for r in block]
        contents = [r[2] for r in block]

        summary = _summarize_block(contents, budget, model=model, timeout=timeout)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO summary_nodes"
            "(kind, content, tokens, session_id, ts_start, ts_end, created_at)"
            " VALUES('leaf', ?, ?, ?, ?, ?, ?)",
            (summary, _estimate_tokens(summary), session_id, ts_start, ts_end, now),
        )
        if cursor.rowcount:
            leaf_id = cursor.lastrowid
            conn.executemany(
                "INSERT OR IGNORE INTO summary_spans(summary_id, message_event_id) VALUES(?, ?)",
                [(leaf_id, mid) for mid in msg_ids],
            )
            new_leaves += 1

    # Condensed node: one per session, summarises all leaves.
    all_leaves = conn.execute(
        "SELECT id, content FROM summary_nodes"
        " WHERE kind='leaf' AND session_id=? ORDER BY ts_start",
        (session_id,),
    ).fetchall()

    if len(all_leaves) >= 2:
        leaf_summaries = [r[1] for r in all_leaves]
        condensed_text = _summarize_block(leaf_summaries, budget, model=model, timeout=timeout)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO summary_nodes"
            "(kind, content, tokens, session_id, ts_start, ts_end, created_at)"
            " VALUES('condensed', ?, ?, ?, NULL, NULL, ?)",
            (condensed_text, _estimate_tokens(condensed_text), session_id, now),
        )
        if cursor.rowcount:
            condensed_id = cursor.lastrowid
            conn.execute(
                "UPDATE summary_nodes SET parent_id = ?"
                " WHERE session_id = ? AND kind = 'leaf' AND parent_id IS NULL",
                (condensed_id, session_id),
            )

    return new_leaves


def _maybe_soft_threshold_summary(
    conn: sqlite3.Connection,
    session_id: str,
    db: Path | str,
    compact_cfg: CompactionConfig,
) -> threading.Thread | None:
    """Fire a background 6-section summary once the soft token threshold is crossed (FEAT-2598).

    Gated on ``CompactionConfig.enabled`` — summarization is the opt-in LLM-cost
    path (unlike the always-on structural eviction pass in
    ``compaction.instant.evict_sink_and_window``, applied here to bound the
    summarizer's input). Updates the session's existing per-session condensed
    ``summary_nodes`` row (``kind='condensed'``, ``level=0``) in place — no new
    node kind, no schema change, and no change to
    ``history_reader.condensed_nodes_for_issue()``'s query semantics.

    Does not touch ``_compact_session_conn``'s purely-additive contract: this
    function only ever reads ``message_events`` and writes to ``summary_nodes``
    from a background thread using its own connection (sqlite3 connections are
    not thread-safe across threads).
    """
    if not compact_cfg.enabled:
        return None

    from little_loops.compaction.instant import SOFT_THRESHOLD_TOKENS, evict_sink_and_window

    rows = conn.execute(
        "SELECT content FROM message_events WHERE session_id = ? ORDER BY ts, id",
        (session_id,),
    ).fetchall()
    if not rows:
        return None

    contents = [r[0] or "" for r in rows]
    if sum(_estimate_tokens(c) for c in contents) < SOFT_THRESHOLD_TOKENS:
        return None

    bounded = evict_sink_and_window([{"role": "user", "content": c} for c in contents])
    bounded_contents = [m["content"] for m in bounded]

    def _run() -> None:
        from little_loops.compaction.instant import summarize_6_section

        summary_text = summarize_6_section(
            bounded_contents, model=compact_cfg.model, timeout=compact_cfg.timeout
        )
        thread_conn = connect(db)
        try:
            existing = thread_conn.execute(
                "SELECT id FROM summary_nodes"
                " WHERE session_id = ? AND kind = 'condensed' AND level = 0",
                (session_id,),
            ).fetchone()
            tokens = _estimate_tokens(summary_text)
            if existing:
                thread_conn.execute(
                    "UPDATE summary_nodes SET content = ?, tokens = ? WHERE id = ?",
                    (summary_text, tokens, existing[0]),
                )
            else:
                thread_conn.execute(
                    "INSERT OR IGNORE INTO summary_nodes"
                    "(kind, content, tokens, session_id, ts_start, ts_end, created_at, level)"
                    " VALUES('condensed', ?, ?, ?, NULL, NULL, ?, 0)",
                    (summary_text, tokens, session_id, _now()),
                )
            thread_conn.commit()
        finally:
            thread_conn.close()

    thread = threading.Thread(target=_run, name=f"compact-6section-{session_id}", daemon=True)
    thread.start()
    return thread


def _compact_sessions(
    conn: sqlite3.Connection,
    config: dict | None = None,
    max_sessions: int | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> int:
    """Compact all sessions in the sessions table; returns total new leaf nodes created.

    Gated by ``history.compaction.enabled`` (default ``false``). Skips silently when
    disabled so backfill() callers that omit config are unaffected.

    When ``cross_session_enabled`` is True (default), runs a recursive cross-session
    condensation pass after per-session compaction: existing condensed nodes are
    grouped level-by-level by token budget, summarised, and inserted as higher-order
    condensed nodes (``session_id=NULL``, ``level=1+``) until exactly one project-root
    summary node remains (ENH-1954).

    Args:
        max_sessions: When set, caps the number of sessions compacted in this run
            (useful for incremental first-time backfills on large databases).
        db: Path passed through to the soft-threshold background summarizer
            (FEAT-2598), which needs its own connection to the same database.
    """
    from little_loops.config.features import CompactionConfig

    raw = config.get("history", {}).get("compaction", {}) if config else {}
    compact_cfg = CompactionConfig.from_dict(raw)
    if not compact_cfg.enabled:
        return 0

    rows = conn.execute("SELECT session_id FROM sessions ORDER BY started_at DESC").fetchall()
    if max_sessions is not None:
        rows = rows[:max_sessions]
    total = 0
    for row in rows:
        total += _compact_session_conn(
            conn,
            row[0],
            budget=compact_cfg.budget_tokens,
            model=compact_cfg.model,
            timeout=compact_cfg.timeout,
        )
        _maybe_soft_threshold_summary(conn, row[0], db, compact_cfg)

    # -- Cross-session condensation (ENH-1954) ---------------------------------
    if not compact_cfg.cross_session_enabled:
        return total

    now = _now()
    level = 1
    max_level = compact_cfg.max_level  # None = unlimited

    while True:
        # Collect condensed nodes at the current level.
        # Level 0 = per-session condensed; level 1+ = cross-session.
        condensed = conn.execute(
            "SELECT id, content, tokens, session_id FROM summary_nodes"
            " WHERE kind='condensed' AND level = ?"
            " ORDER BY id",
            (level - 1,),
        ).fetchall()

        if len(condensed) <= 1:
            break  # nothing to roll up, or already at root

        # Group by token budget — same greedy algorithm as _compact_session_conn
        groups: list[list[tuple[int, str, int, str | None]]] = []
        current: list[tuple[int, str, int, str | None]] = []
        current_tokens = 0

        for row in condensed:
            node_id, content, tokens, sess_id = (
                row[0],
                row[1],
                row[2] or 0,
                row[3],
            )
            if current_tokens + tokens > compact_cfg.budget_tokens and current:
                groups.append(current)
                current = [(node_id, content, tokens, sess_id)]
                current_tokens = tokens
            else:
                current.append((node_id, content, tokens, sess_id))
                current_tokens += tokens
        if current:
            groups.append(current)

        for group in groups:
            member_ids = [g[0] for g in group]
            contents = [g[1] for g in group]

            summary = _summarize_block(
                contents,
                compact_cfg.budget_tokens,
                model=compact_cfg.model,
                timeout=compact_cfg.timeout,
            )

            # Compute ts_start/ts_end for the dedup index.
            # Level-1 members are per-session condensed nodes (session_id NOT NULL
            # but ts_start=NULL). Query leaf descendants via session_id to get
            # real timestamps. Level-2+ members already have ts_start/ts_end set.
            if level == 1:
                sess_ids = [g[3] for g in group if g[3] is not None]
                if sess_ids:
                    ph = ",".join(["?"] * len(sess_ids))
                    ts_row = conn.execute(
                        f"SELECT MIN(ts_start), MAX(ts_end) FROM summary_nodes"
                        f" WHERE kind='leaf' AND session_id IN ({ph})",
                        sess_ids,
                    ).fetchone()
                    ts_start = ts_row[0] if ts_row else None
                    ts_end = ts_row[1] if ts_row else None
                else:
                    ts_start, ts_end = None, None
            else:
                ph = ",".join(["?"] * len(member_ids))
                ts_row = conn.execute(
                    f"SELECT MIN(ts_start), MAX(ts_end) FROM summary_nodes WHERE id IN ({ph})",
                    member_ids,
                ).fetchone()
                ts_start = ts_row[0] if ts_row else None
                ts_end = ts_row[1] if ts_row else None

            cursor = conn.execute(
                "INSERT OR IGNORE INTO summary_nodes"
                "(kind, content, tokens, session_id, ts_start, ts_end, created_at, level)"
                " VALUES('condensed', ?, ?, NULL, ?, ?, ?, ?)",
                (summary, _estimate_tokens(summary), ts_start, ts_end, now, level),
            )
            if cursor.rowcount:
                parent_id: int | None = cursor.lastrowid
            else:
                # Node already exists (idempotent re-run) — look up its id
                existing = conn.execute(
                    "SELECT id FROM summary_nodes"
                    " WHERE kind='condensed' AND session_id IS NULL"
                    " AND level = ? AND ts_start = ? AND ts_end = ?",
                    (level, ts_start, ts_end),
                ).fetchone()
                parent_id = existing[0] if existing else None

            if parent_id is not None:
                ph = ",".join(["?"] * len(member_ids))
                conn.execute(
                    f"UPDATE summary_nodes SET parent_id = ?"
                    f" WHERE id IN ({ph}) AND parent_id IS NULL",
                    [parent_id] + member_ids,
                )

        # Depth-limit check
        if max_level is not None and level >= max_level:
            break

        level += 1

    return total


def compact_session(
    session_id: str,
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
) -> int:
    """Summarize message_events for one session into summary_nodes and summary_spans.

    Idempotent: repeated calls do not create duplicate nodes (INSERT OR IGNORE +
    partial unique indexes). Uses LCM Algorithm 3 three-level escalation (level 1:
    normal LLM summary → level 2: aggressive bullet-point LLM summary → level 3:
    deterministic truncation) so a leaf node is always produced. Returns the count
    of new leaf nodes created.
    """
    from little_loops.config.features import CompactionConfig

    raw = config.get("history", {}).get("compaction", {}) if config else {}
    compact_cfg = CompactionConfig.from_dict(raw)
    conn = connect(db)
    try:
        result = _compact_session_conn(
            conn,
            session_id,
            budget=compact_cfg.budget_tokens,
            model=compact_cfg.model,
            timeout=compact_cfg.timeout,
        )
        conn.commit()
        _maybe_soft_threshold_summary(conn, session_id, db, compact_cfg)
    finally:
        conn.close()
    return result


def _backfill_sessions(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int:
    """Seed ``sessions`` table by mapping each JSONL file to its session_id.

    Reads just enough of each source to extract the first ``sessionId`` value,
    then inserts one row per unique source. ``INSERT OR IGNORE`` + PRIMARY KEY
    makes repeated calls idempotent (ENH-1710). *source* accepts either JSONL
    files or a raw_events cursor — see :func:`_iter_events`. Unlike the legacy
    per-file loop this no longer short-circuits to the next physical file on
    the first hit (the cursor path has no file boundary), instead skipping
    further parse attempts for a source once its session_id is known.
    """
    count = 0
    seen: set[str] = set()
    for line, source_label in _iter_events(source):
        if source_label in seen:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        session_id = record.get("sessionId")
        if session_id:
            cur = conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (str(session_id), source_label),
            )
            count += cur.rowcount
            seen.add(source_label)
    return count


def _mtime(path: Path) -> float:
    """Return file modification time as a Unix float, or 0.0 if inaccessible."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _backfill_raw_events(conn: sqlite3.Connection, jsonl_files: list[Path]) -> int:
    """Parse *jsonl_files* and INSERT OR IGNORE one row per line into raw_events.

    Idempotent via the ``(source_path, line_no)`` dedup index. ``event_type``
    is the record's own ``type`` field (``"user"``, ``"assistant"``, ...) —
    one JSONL line can feed multiple derived cache rows (e.g. an assistant
    line yields both an assistant_messages row and zero-or-more tool_events
    rows), so raw_events stores the source line verbatim rather than a
    cache-table kind (ENH-2581).
    """
    host = resolve_host().name
    count = 0
    for jsonl_file in jsonl_files:
        try:
            handle = jsonl_file.open(encoding="utf-8")
        except OSError:
            continue
        source_path = str(jsonl_file)
        with handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cur = conn.execute(
                    "INSERT OR IGNORE INTO raw_events"
                    "(ts, session_id, host, source_path, line_no, event_type, raw_line, parsed_json)"
                    " VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(record.get("timestamp") or ""),
                        record.get("sessionId"),
                        host,
                        source_path,
                        line_no,
                        str(record.get("type") or "unknown"),
                        _pack_payload(line),
                        _pack_payload(json.dumps(record)),
                    ),
                )
                count += cur.rowcount
    return count


def backfill_raw_events(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    jsonl_files: list[Path],
    since_ts: float | None = None,
) -> int:
    """Parse JSONL files and INSERT OR IGNORE rows into raw_events.

    Idempotent via ``INSERT OR IGNORE`` on ``(source_path, line_no)``. Filters
    *jsonl_files* by mtime >= *since_ts* when given (``None`` processes every
    provided file). Updates the ``last_raw_event_ts`` meta key on success —
    the single watermark that replaces ``last_backfill_ts`` /
    ``last_backfill_ts_assistant_messages`` / ``last_backfill_ts_skill_events``
    (ENH-2581). Returns the count of new rows inserted.
    """
    conn = connect(db)
    try:
        filtered = (
            [f for f in jsonl_files if _mtime(f) >= since_ts]
            if since_ts is not None
            else jsonl_files
        )
        count = _backfill_raw_events(conn, filtered)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('last_raw_event_ts', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_now(),),
        )
        conn.commit()
    finally:
        conn.close()
    return count


def recompress_raw_events(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    batch_size: int = 2000,
) -> dict[str, Any]:
    """Rewrite legacy uncompressed ``raw_events`` payloads as compressed BLOBs.

    New rows are written compressed by :func:`_backfill_raw_events`; this backfills
    the one-time conversion of pre-existing TEXT rows. Runs in short per-batch
    transactions (not one giant lock) so it does not freeze the interactive hook
    write path, then ``VACUUM`` reclaims the freed pages. Idempotent and resumable
    via ``typeof(...) = 'text'`` — already-compressed rows are BLOBs and skipped.

    Returns ``{"recompressed": int, "size_before_mb": float, "size_after_mb": float}``.
    """
    db_path = ensure_db(db)  # unified env→config→default resolution + schema (ENH-2623)
    size_before = db_path.stat().st_size if db_path.exists() else 0
    conn = connect(db_path)
    recompressed = 0
    try:
        while True:
            rows = conn.execute(
                "SELECT id, raw_line, parsed_json FROM raw_events "
                "WHERE typeof(raw_line) = 'text' OR typeof(parsed_json) = 'text' "
                "LIMIT ?",
                (batch_size,),
            ).fetchall()
            if not rows:
                break
            conn.execute("BEGIN")
            for row in rows:
                raw_line = row["raw_line"]
                parsed_json = row["parsed_json"]
                packed_raw = raw_line if isinstance(raw_line, bytes) else _pack_payload(raw_line)
                packed_parsed = (
                    parsed_json if isinstance(parsed_json, bytes) else _pack_payload(parsed_json)
                )
                conn.execute(
                    "UPDATE raw_events SET raw_line = ?, parsed_json = ? WHERE id = ?",
                    (packed_raw, packed_parsed, row["id"]),
                )
            conn.commit()
            recompressed += len(rows)
    finally:
        conn.close()
    if recompressed:
        vac = sqlite3.connect(str(db_path))
        try:
            vac.execute("VACUUM")
        finally:
            vac.close()
    size_after = db_path.stat().st_size if db_path.exists() else 0
    return {
        "recompressed": recompressed,
        "size_before_mb": round(size_before / 1_000_000, 1),
        "size_after_mb": round(size_after / 1_000_000, 1),
    }


# Cache tables re-derived from raw_events by rebuild(). Deliberately excludes
# cli_events/file_events/test_run_events/issue_events/loop_events/commit_events/
# issue_snapshots/hook_events — those have no raw_events-backed _backfill_*
# path (they're either live-write-only or sourced from .issues/.loops/git log,
# out of this issue's scope; see ENH-2581 management plan). Wiping them here
# with no re-derivation path would be unrecoverable data loss. hook_events in
# particular has no transcript-JSONL source at all (ENH-2506).
_REBUILD_TABLES = (
    "tool_events",
    "message_events",
    "assistant_messages",
    "skill_events",
    "sessions",
    "user_corrections",
    "summary_nodes",
    "summary_spans",
    "usage_events",
)
_REBUILD_SEARCH_KINDS = ("tool", "message", "skill", "correction", "usage")


def rebuild(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
    max_sessions: int | None = None,
) -> dict[str, int]:
    """Wipe and re-derive the JSONL-sourced cache tables from ``raw_events``.

    Wipes ``_REBUILD_TABLES`` plus the ``search_index`` rows for
    ``_REBUILD_SEARCH_KINDS``, then re-derives them by replaying every
    ``raw_events`` row through the same ``_backfill_*`` parsers the legacy
    JSONL path uses (via :func:`_iter_events`). Idempotent — safe to call
    repeatedly. Updates the ``last_rebuild_version`` meta key to
    ``SCHEMA_VERSION`` on success.

    Issue/loop/commit/cli/file/test_run tables are outside ``raw_events``'s
    scope for this issue (ENH-2581) and are left untouched.
    """
    conn = connect(db)
    counts: dict[str, int] = {
        "sessions": 0,
        "tools": 0,
        "messages": 0,
        "assistant_messages": 0,
        "skill_events": 0,
        "corrections": 0,
        "summaries": 0,
        "usage_events": 0,
    }
    try:
        for table in _REBUILD_TABLES:
            conn.execute(f"DELETE FROM {table}")
        placeholders = ",".join(["?"] * len(_REBUILD_SEARCH_KINDS))
        conn.execute(
            f"DELETE FROM search_index WHERE kind IN ({placeholders})",
            _REBUILD_SEARCH_KINDS,
        )

        def _raw_events_cursor() -> sqlite3.Cursor:
            return conn.execute("SELECT raw_line, source_path FROM raw_events ORDER BY id")

        # sessions first: assistant_messages/backfill order elsewhere relies on
        # the sessions table already being populated (ENH-1710).
        counts["sessions"] = _backfill_sessions(conn, _raw_events_cursor())
        counts["tools"] = _backfill_tool_events(conn, _raw_events_cursor())
        counts["messages"] = _backfill_messages(conn, _raw_events_cursor())
        counts["assistant_messages"] = _backfill_assistant_messages(conn, _raw_events_cursor())
        counts["skill_events"] = _backfill_skill_events(conn, _raw_events_cursor())
        counts["usage_events"] = _backfill_usage_events(conn, _raw_events_cursor())
        counts["corrections"] = mine_corrections_from_messages(conn, config)
        counts["summaries"] = _compact_sessions(conn, config, max_sessions=max_sessions, db=db)

        conn.execute(
            "INSERT INTO meta(key, value) VALUES('last_rebuild_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
    finally:
        conn.close()
    return counts


def backfill_snapshots(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    issues_dir: Path | None = None,
) -> int:
    """Hydrate ``issue_snapshots`` from all ``.md`` files under *issues_dir*.

    Idempotent via ``INSERT OR IGNORE`` on the ``(issue_id, transition)`` dedup
    index.  Also indexes each snapshot in ``search_index`` with ``kind="snapshot"``.
    Returns the number of rows inserted (0 when *issues_dir* is absent or empty).
    """
    issues_dir = issues_dir if issues_dir is not None else Path(".issues")
    if not issues_dir.is_dir():
        return 0
    conn = connect(db)
    try:
        count = _backfill_snapshots(conn, issues_dir)
        conn.commit()
    finally:
        conn.close()
    return count


def backfill(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    issues_dir: Path | None = None,
    loops_dir: Path | None = None,
    jsonl_files: list[Path] | None = None,
    config: dict | None = None,
    max_sessions: int | None = None,
    repo_root: Path | None = None,
    registry_dir: Path | None = None,
    sessions_root: Path | None = None,
    also_rebuild: bool = False,
) -> dict[str, int]:
    """Populate the database from existing on-disk sources.

    Reads issue-file frontmatter, FSM loop-state JSON, git commit history
    (ENH-2458; only when *repo_root* is given and contains ``.git``), the
    Learning Test Registry (ENH-2466; only when *registry_dir* is given and is
    a directory), and nested subagent transcripts (ENH-2505; only when
    *sessions_root* is given and is a directory) directly. Session JSONL lines
    are ingested into ``raw_events`` only (ENH-2581) — the JSONL-derived cache
    tables (``tool_events``, ``message_events``, ``assistant_messages``,
    ``skill_events``, ``sessions``) are **not** populated here; call
    :func:`rebuild` (or pass ``also_rebuild=True`` to do both in one call) to
    materialize them from ``raw_events``.

    Returns a per-kind count of rows inserted/derived. Sources that are
    absent are skipped silently.
    """
    issues_dir = issues_dir if issues_dir is not None else Path(".issues")
    loops_dir = loops_dir if loops_dir is not None else Path(".loops")
    if registry_dir is None:
        registry_dir = Path(".ll") / "learning-tests"
    conn = connect(db)
    counts: dict[str, int] = {
        "issues": 0,
        "loops": 0,
        "snapshots": 0,
        "commits": 0,
        "raw_events": 0,
        "learning_tests": 0,
        "subagent_runs": 0,
    }
    try:
        if issues_dir.is_dir():
            counts["issues"] = _backfill_issues(conn, issues_dir)
            counts["snapshots"] = _backfill_snapshots(conn, issues_dir)
        if loops_dir.is_dir():
            counts["loops"] = _backfill_loops(conn, loops_dir)
        if repo_root is not None and (repo_root / ".git").exists():
            counts["commits"] = _backfill_commit_events(conn, repo_root)
        if jsonl_files:
            counts["raw_events"] = _backfill_raw_events(conn, jsonl_files)
        if registry_dir.is_dir():
            counts["learning_tests"] = _backfill_learning_test_events(conn, registry_dir)
        if sessions_root is not None and sessions_root.is_dir():
            counts["subagent_runs"] = _backfill_subagent_runs(conn, sessions_root)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('last_raw_event_ts', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_now(),),
        )
        conn.commit()
    finally:
        conn.close()

    if also_rebuild:
        counts.update(rebuild(db, config=config, max_sessions=max_sessions))

    return counts


def backfill_incremental(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    jsonl_files: list[Path],
    since_ts: float | None = None,
    config: dict | None = None,
    also_rebuild: bool = False,
) -> dict[str, int]:
    """Ingest JSONL files modified after *since_ts* into ``raw_events``.

    Thin wrapper over :func:`backfill_raw_events` (ENH-2581): ingest only.
    The three legacy per-table watermarks (``last_backfill_ts``,
    ``last_backfill_ts_assistant_messages``, ``last_backfill_ts_skill_events``)
    collapse to the single ``last_raw_event_ts`` key maintained by
    :func:`backfill_raw_events`.

    If *since_ts* is ``None``, reads ``last_raw_event_ts`` from the ``meta``
    table (defaults to 0.0 — all files — when the key is absent or NULL).

    Pass ``also_rebuild=True`` to materialize the JSONL-derived cache tables
    from ``raw_events`` afterward in the same call — used by the
    ``SessionStart`` hook worker when ``SCHEMA_VERSION`` has changed (see
    ``cli/backfill_worker.py --rebuild``).

    Issues and loop-state JSON are NOT backfilled here; this variant is
    JSONL-only and designed for low-latency background use in session hooks.
    Errors are not suppressed — the caller (session hook) catches them and
    logs a warning.
    """
    if since_ts is None:
        conn = connect(db)
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'last_raw_event_ts'").fetchone()
        finally:
            conn.close()
        raw = row[0] if (row and row[0]) else None
        if raw:
            try:
                since_ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
            except ValueError:
                since_ts = 0.0
        else:
            since_ts = 0.0

    raw_count = backfill_raw_events(db, jsonl_files=jsonl_files, since_ts=since_ts)
    counts: dict[str, int] = {"raw_events": raw_count}
    if also_rebuild:
        counts.update(rebuild(db, config=config))
    return counts


def compact(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
    and_prune: bool = False,
) -> dict[str, int]:
    """Sweep old ``raw_events`` rows into per-session retention summaries.

    Reads ``analytics.retention.raw_event_max_age_days`` (default 90) from
    *config*. Groups eligible (uncompacted, past-cutoff) ``raw_events`` rows by
    ``session_id`` and inserts one ``kind='retention'`` ``summary_nodes`` row
    per session — a deterministic one-liner; this lifecycle path makes no
    host-CLI call, unlike the LLM-backed ``history.compaction`` feature
    (:func:`_compact_sessions`, which uses ``kind='condensed'`` — a distinct
    kind so the two features' dedup indexes never collide). Marks the swept
    rows ``compacted=1`` with ``summary_node_id`` set so :func:`prune` can
    delete them safely later. Idempotent via
    ``idx_summary_nodes_retention_dedup``.

    If *and_prune*, calls :func:`prune` afterward and folds its deleted-row
    count into the return value.
    """
    from little_loops.config.features import RetentionConfig

    raw = (config or {}).get("analytics", {}).get("retention", {})
    retention_cfg = RetentionConfig.from_dict(raw)
    result: dict[str, int] = {"compacted_rows": 0, "summary_nodes": 0, "pruned_rows": 0}

    if retention_cfg.raw_event_max_age_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=retention_cfg.raw_event_max_age_days)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT id, ts, session_id FROM raw_events"
                " WHERE ts < ? AND compacted = 0 ORDER BY session_id, ts",
                (cutoff_str,),
            ).fetchall()

            by_session: dict[str | None, list[sqlite3.Row]] = {}
            for row in rows:
                by_session.setdefault(row["session_id"], []).append(row)

            now = _now()
            for session_id, session_rows in by_session.items():
                ts_start = session_rows[0]["ts"]
                ts_end = session_rows[-1]["ts"]
                summary = (
                    f"Compacted {len(session_rows)} raw event(s) for session "
                    f"{session_id or '(unknown)'} between {ts_start} and {ts_end}."
                )
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO summary_nodes"
                    "(kind, content, tokens, session_id, ts_start, ts_end, created_at)"
                    " VALUES('retention', ?, ?, ?, ?, ?, ?)",
                    (summary, _estimate_tokens(summary), session_id, ts_start, ts_end, now),
                )
                if cursor.rowcount:
                    summary_node_id = cursor.lastrowid
                    result["summary_nodes"] += 1
                else:
                    existing = conn.execute(
                        "SELECT id FROM summary_nodes"
                        " WHERE kind='retention' AND session_id IS ?"
                        " AND ts_start = ? AND ts_end = ?",
                        (session_id, ts_start, ts_end),
                    ).fetchone()
                    summary_node_id = existing[0] if existing else None

                ids = [r["id"] for r in session_rows]
                placeholders = ",".join(["?"] * len(ids))
                conn.execute(
                    f"UPDATE raw_events SET compacted = 1, summary_node_id = ?"
                    f" WHERE id IN ({placeholders})",
                    [summary_node_id, *ids],
                )
                result["compacted_rows"] += len(ids)

            conn.commit()
        finally:
            conn.close()

    if and_prune:
        prune_result = prune(db, config=config)
        result["pruned_rows"] = sum(prune_result.get("deleted", {}).values())

    return result


def prune(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Delete compacted ``raw_events`` rows older than max-age, then VACUUM.

    Operates on ``raw_events`` only (ENH-2581): rows must already be marked
    ``compacted=1`` by :func:`compact` before ``prune()`` will delete them.
    ``prune()`` never mutates ``search_index`` or the cache tables —
    :func:`rebuild` owns re-deriving those. ``cli_events``/``file_events``/
    ``test_run_events`` are outside ``raw_events``'s scope for this issue and
    are no longer pruned by this path.

    Both dual gates must be exceeded before any rows are deleted:
    - ``min_project_age_days``: project age (MIN(started_at) from sessions table)
    - ``min_db_size_mb``: DB file size on disk

    Args:
        db: Path to the history database.
        config: Project config dict (reads ``analytics.retention``). ``None`` uses defaults.
        dry_run: Count rows that would be deleted without deleting them.

    Returns:
        dict with keys:
        - ``pruned`` (bool): whether pruning ran (gates met and rows eligible)
        - ``gate_unmet`` (list[str]): human-readable reason for each unmet gate
        - ``project_age_days`` (int): measured project age
        - ``db_size_mb`` (float): DB file size in MB
        - ``deleted`` (dict[str, int]): ``{"raw_events": count}`` (actual or projected)
        - ``vacuumed`` (bool): whether VACUUM ran (always False in dry_run)
    """
    from little_loops.config.features import RetentionConfig

    raw = (config or {}).get("analytics", {}).get("retention", {})
    retention_cfg = RetentionConfig.from_dict(raw)

    db_path = Path(db)
    result: dict = {
        "pruned": False,
        "gate_unmet": [],
        "project_age_days": 0,
        "db_size_mb": 0.0,
        "deleted": {},
        "vacuumed": False,
    }

    conn = connect(db)
    try:
        # Gate 1: project age — MIN(started_at) from sessions
        row = conn.execute("SELECT MIN(started_at) FROM sessions").fetchone()
        oldest_ts = row[0] if row and row[0] else None
        if oldest_ts:
            try:
                oldest_dt = datetime.fromisoformat(oldest_ts.replace("Z", "+00:00"))
                project_age_days = (datetime.now(UTC) - oldest_dt).days
            except ValueError:
                project_age_days = 0
        else:
            project_age_days = 0
        result["project_age_days"] = project_age_days

        # Gate 2: DB file size
        db_size_mb = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0.0
        result["db_size_mb"] = round(db_size_mb, 2)

        # Evaluate gates
        gates_unmet: list[str] = []
        if project_age_days < retention_cfg.min_project_age_days:
            gates_unmet.append(
                f"project age {project_age_days}d < {retention_cfg.min_project_age_days}d"
            )
        if db_size_mb < retention_cfg.min_db_size_mb:
            gates_unmet.append(f"db size {db_size_mb:.1f}MB < {retention_cfg.min_db_size_mb}MB")
        result["gate_unmet"] = gates_unmet

        if gates_unmet:
            return result

        if retention_cfg.raw_event_max_age_days is None:
            result["pruned"] = True
            return result

        cutoff = datetime.now(UTC) - timedelta(days=retention_cfg.raw_event_max_age_days)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        count_row = conn.execute(
            "SELECT COUNT(*) FROM raw_events WHERE ts < ? AND compacted = 1", (cutoff_str,)
        ).fetchone()
        deleted_count = count_row[0] if count_row else 0
        if not dry_run and deleted_count > 0:
            conn.execute("DELETE FROM raw_events WHERE ts < ? AND compacted = 1", (cutoff_str,))

        result["deleted"] = {"raw_events": deleted_count}
        result["pruned"] = True

        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    # VACUUM outside the original connection to avoid transaction conflicts
    if result["pruned"] and not dry_run:
        try:
            vac_conn = sqlite3.connect(str(db_path))
            _configure_connection(vac_conn)
            vac_conn.isolation_level = None
            try:
                vac_conn.execute("VACUUM")
                result["vacuumed"] = True
            finally:
                vac_conn.close()
        except sqlite3.Error as exc:
            logger.warning("prune: VACUUM failed: %s", exc)

    return result


# ---------------------------------------------------------------------------
# Correction retirement (ENH-2046)
# ---------------------------------------------------------------------------


def record_retirement(
    db: Path | str = DEFAULT_DB_PATH,
    topic_fingerprint: str = "",
    rule_id: str = "",
    session_id: str = "",
) -> None:
    """Mark a recurring-correction cluster as addressed.

    Uses INSERT OR REPLACE so a second call for the same fingerprint updates
    the record rather than duplicating it.  ``rule_id`` should be the
    ``decisions.yaml`` entry ID (e.g. ``BEHAVIOR-001``) or ``"claude-md"``
    when the rule was written directly into CLAUDE.md.
    """
    if not topic_fingerprint:
        return
    conn = connect(db)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO correction_retirements"
            "(topic_fingerprint, rule_id, addressed_at, session_id) VALUES (?, ?, ?, ?)",
            (topic_fingerprint, rule_id or None, _now(), session_id or None),
        )
        conn.commit()
    finally:
        conn.close()


def list_retirements(
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Return all correction retirement records, newest first.

    Returns an empty list when the DB does not exist or the
    ``correction_retirements`` table has not yet been created.
    """
    db_path = Path(db)
    if not db_path.exists():
        return []
    conn = connect(db)
    try:
        rows = conn.execute(
            "SELECT topic_fingerprint, rule_id, addressed_at, session_id"
            " FROM correction_retirements ORDER BY addressed_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# JSONL export (for visualization / external tooling)
# ---------------------------------------------------------------------------

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
    "session_lifecycle_event",
]


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
            Valid values: ``session``, ``issue_event``, ``issue_snapshot``,
            ``skill_event``, ``loop_event``, ``correction``, ``summary_node``,
            ``message_event``, ``commit_event``, ``test_run_event``,
            ``usage_event``, ``orchestration_run``.
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

    conn = connect(db_path)
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
