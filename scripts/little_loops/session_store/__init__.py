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

Package layout (ENH-2890 split from the former flat ``session_store.py``):
    schema.py:    DDL migrations, ``ensure_db``/``connect``, kind/table maps
    db.py:        DB path resolution (env -> config -> default)
    queries.py:   FTS5 search/recent + JSONL export
    lifecycle.py: retention lifecycle (backfill/rebuild/compact/prune) and
                  LCM session-summary compaction
    writers.py:   every ``record_*``/``*_event_context`` writer, the paired
                  ``_backfill_*`` helpers, and ``SQLiteTransport``

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
    record_issue_event(db,...):  write one row to ``issue_events`` + search_index (BUG-2770)
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
    record_harness_event(db,...): write one row to ``harness_events`` + search_index (ENH-2739)
    record_prompt_opt_event(db,...): write one row to ``prompt_opt_events`` + search_index (ENH-2498)
    record_verdict_event(db,...): write one row to ``verdict_events`` + search_index (ENH-2504)
"""

from __future__ import annotations

import sqlite3
import subprocess

from little_loops.session_store.db import DEFAULT_DB_PATH, resolve_history_db
from little_loops.session_store.lifecycle import (
    _REBUILD_SEARCH_KINDS,
    _REBUILD_TABLES,
    _call_llm_for_summary,
    _compact_session_conn,
    _compact_session_conn_with_reasoning,
    _compact_sessions,
    _estimate_tokens,
    _maybe_soft_threshold_summary,
    _summarize_block,
    backfill,
    backfill_incremental,
    backfill_raw_events,
    backfill_snapshots,
    compact,
    compact_session,
    compact_session_with_reasoning,
    list_retirements,
    prune,
    rebuild,
    recompress_raw_events,
    record_retirement,
)
from little_loops.session_store.queries import export_history, fts_phrase, recent, search
from little_loops.session_store.schema import (
    _BUSY_TIMEOUT_MS,
    _KIND_TABLE,
    _KINDLESS_TABLES,
    _LOOP_EVENT_TYPES,
    _MIGRATIONS,
    SCHEMA_VERSION,
    VALID_KINDS,
    _apply_migrations,
    _configure_connection,
    _current_version,
    _split_sql_statements,
    connect,
    ensure_db,
)
from little_loops.session_store.writers import (
    HookEventCompletion,
    SkillEventCompletion,
    SQLiteTransport,
    _backfill_assistant_messages,
    _backfill_messages,
    _backfill_snapshots,
    _backfill_subagent_runs,
    _derive_transition,
    _hash_args,
    _index,
    _infer_issue_id,
    _normalize_agent_type,
    _now,
    _pack_payload,
    _parse_mcp_tool_name,
    _unpack_payload,
    canonicalize_issue_id,
    cli_event_context,
    hook_event_context,
    is_correction,
    mine_corrections_from_messages,
    normalize_issue_id,
    record_commit_event,
    record_context_pressure_event,
    record_correction,
    record_harness_event,
    record_hook_event,
    record_issue_event,
    record_issue_snapshot,
    record_learning_test_event,
    record_loop_run_summary,
    record_orchestration_run,
    record_prompt_opt_event,
    record_review_event,
    record_session_lifecycle_event,
    record_skill_event,
    record_subagent_run_start,
    record_subagent_run_stop,
    record_test_run_event,
    record_usage_event,
    record_verdict_event,
    skill_event_context,
    update_loop_run_diagnostics,
    write_file_event,
)

__all__ = [
    "DEFAULT_DB_PATH",
    "SCHEMA_VERSION",
    "VALID_KINDS",
    "ensure_db",
    "connect",
    "normalize_issue_id",
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
    "compact_session_with_reasoning",
    "export_history",
    "prune",
    "search",
    "recent",
    "fts_phrase",
    "is_correction",
    "record_correction",
    "record_skill_event",
    "record_issue_snapshot",
    "record_issue_event",
    "record_commit_event",
    "record_test_run_event",
    "record_orchestration_run",
    "record_loop_run_summary",
    "update_loop_run_diagnostics",
    "record_usage_event",
    "record_review_event",
    "record_context_pressure_event",
    "record_subagent_run_start",
    "record_subagent_run_stop",
    "canonicalize_issue_id",
    "write_file_event",
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
    "record_harness_event",
    "record_prompt_opt_event",
    "record_verdict_event",
    # Private functions re-exported for test access
    "_MIGRATIONS",
    "_KIND_TABLE",
    "_KINDLESS_TABLES",
    "_split_sql_statements",
    "_call_llm_for_summary",
    "_estimate_tokens",
    "_summarize_block",
    "_derive_transition",
    "_pack_payload",
    "_unpack_payload",
    "_backfill_snapshots",
    "_backfill_assistant_messages",
    "_backfill_messages",
    "_backfill_subagent_runs",
    "_apply_migrations",
    "_configure_connection",
    "_current_version",
    "_BUSY_TIMEOUT_MS",
    "_LOOP_EVENT_TYPES",
    "_compact_session_conn",
    "_compact_session_conn_with_reasoning",
    "_compact_sessions",
    "_maybe_soft_threshold_summary",
    "_REBUILD_TABLES",
    "_REBUILD_SEARCH_KINDS",
    "_hash_args",
    "_index",
    "_infer_issue_id",
    "_normalize_agent_type",
    "_now",
    "_parse_mcp_tool_name",
    "sqlite3",
    "subprocess",
]
