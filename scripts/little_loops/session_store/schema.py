"""SQLite schema, migrations, and connection helpers for the session store
(ENH-2890 split from session_store.py).

Owns ``_MIGRATIONS`` (the ordered DDL sequence), ``ensure_db``/``connect``
(the two schema-aware entry points every other submodule opens the database
through), and the kind/table lookup constants. Depends on
:mod:`little_loops.session_store.db` for path resolution; nothing in
``db.py`` imports back from here.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from little_loops.session_store.db import DEFAULT_DB_PATH, _resolve_db_path

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 40

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
    "harness",
    "prompt_opt",
    "verdict",
    "context_pressure",
    "review",
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
    "harness": "harness_events",
    "prompt_opt": "prompt_opt_events",
    "verdict": "verdict_events",
    "context_pressure": "context_pressure_events",
    "review": "review_events",
}

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
        # (ENH-2997) keyed by issue_id, not session_id — readers take the most
        # recent row for an issue, so there is no "recent by kind" concept to
        # register. See record_prepatch_evidence/read_prepatch_evidence.
        "prepatch_evidence",
    }
)

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

# Every ``ll-*`` invocation opens this DB on startup; under ll-auto / ll-loop /
# ll-parallel many processes contend at once, so without a busy_timeout an open
# fails instantly with ``OperationalError: database is locked``.
_BUSY_TIMEOUT_MS = 5000

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
    # queryable. Requires captured_at IS NOT NULL; populated by
    # _backfill_issues_and_snapshots() for historical rows and by
    # issue_lifecycle.py emit sites (ENH-1839) for live-emitted rows.
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
    # v31 (ENH-2739): ll-harness / eval outcome telemetry. Live-write-only,
    # like hook_events (v30) — no raw_events source to parse, so excluded from
    # _REBUILD_TABLES. parent_id links DSL per-task rows to their parent
    # harness run (ENH-2740); the semantic_* columns capture check_semantic
    # verdict detail alongside the pass/fail exit_code path.
    """
    CREATE TABLE IF NOT EXISTS harness_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        runner TEXT,
        target TEXT,
        exit_code INTEGER,
        semantic_verdict TEXT,
        semantic_passed INTEGER,
        timed_out INTEGER,
        duration_ms INTEGER,
        head_sha TEXT,
        branch TEXT,
        parent_id INTEGER,
        semantic_prompt TEXT,
        semantic_confidence REAL,
        semantic_reason TEXT,
        semantic_evidence TEXT,
        semantic_model TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_harness_runner ON harness_events(runner);
    CREATE INDEX IF NOT EXISTS idx_harness_target ON harness_events(target);
    CREATE INDEX IF NOT EXISTS idx_harness_exit ON harness_events(exit_code);
    CREATE INDEX IF NOT EXISTS idx_harness_parent ON harness_events(parent_id);
    """,
    # v32 (ENH-2498): prompt-optimization offer/outcome telemetry.
    # `user_prompt_submit.py::handle()` writes the offer row live (mode,
    # offered, bypass_reason, raw_len) at hook-fire time — that decision can't
    # be reconstructed retroactively with historical-config confidence, so
    # (like hook_events/harness_events) this table is excluded from
    # _REBUILD_TABLES/_REBUILD_SEARCH_KINDS: a rebuild() wipe-and-replay would
    # destroy live rows with no raw_events-backed way to regenerate them.
    # Unlike those two, this table DOES get a best-effort backfill pass —
    # _backfill_prompt_opt() enriches existing offered=1 rows in place
    # (UPDATE, never INSERT/DELETE) with optimized_len/optimized_text/accepted
    # parsed from the transcript, so it's safe to run non-destructively from
    # rebuild() without registering the table in the wipe lists.
    """
    CREATE TABLE IF NOT EXISTS prompt_opt_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        mode TEXT,
        offered INTEGER,
        bypass_reason TEXT,
        raw_len INTEGER,
        optimized_len INTEGER,
        optimized_text TEXT,
        accepted INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_prompt_opt_events_session ON prompt_opt_events(session_id);
    CREATE INDEX IF NOT EXISTS idx_prompt_opt_events_mode ON prompt_opt_events(mode);
    """,
    # v33 (ENH-2504): verifier verdict outcome telemetry (ll-ready-issue,
    # ll-confidence-check, ll-go-no-go, ll-tradeoff-review-issues,
    # ll-refine-issue, ll-format-issue, ll-verify-issues, ll-prioritize-issues,
    # ll-align-issues). Live-write-only, like hook_events/harness_events —
    # the verdict is a structured dict already in hand at cmd_invoke()'s
    # Python boundary, never reconstructed from transcript text; excluded
    # from _REBUILD_TABLES/_REBUILD_SEARCH_KINDS.
    """
    CREATE TABLE IF NOT EXISTS verdict_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        verdict_kind TEXT NOT NULL,
        target_kind TEXT,
        target_id TEXT,
        verdict TEXT NOT NULL,
        severity_counts TEXT,
        findings_count INTEGER,
        confidence INTEGER,
        head_sha TEXT,
        branch TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_verdict_kind ON verdict_events(verdict_kind);
    CREATE INDEX IF NOT EXISTS idx_verdict_target ON verdict_events(target_id);
    CREATE INDEX IF NOT EXISTS idx_verdict_session ON verdict_events(session_id);
    """,
    # v34 (ENH-2507): context-window pressure measurements. context-monitor.sh
    # already computes USAGE_PERCENT/token estimate on every PostToolUse but
    # only writes it to stderr; this table gives that continuous signal a
    # queryable home. Live-write-only (the shell monitor is the sole owner of
    # the finalized measurement) — excluded from _REBUILD_TABLES/
    # _REBUILD_SEARCH_KINDS like hook_events/harness_events/prompt_opt_events.
    """
    CREATE TABLE IF NOT EXISTS context_pressure_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        used_pct REAL,
        used_tokens_est INTEGER,
        threshold_crossed INTEGER,
        crossed_level TEXT,
        head_sha TEXT,
        branch TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_pressure_session ON context_pressure_events(session_id);
    CREATE INDEX IF NOT EXISTS idx_pressure_ts ON context_pressure_events(ts);
    CREATE INDEX IF NOT EXISTS idx_pressure_crossed ON context_pressure_events(threshold_crossed);
    """,
    # v35 (ENH-2512): reviewer-side audit/review outcome telemetry
    # (review-epic, review-loop, audit-architecture, audit-claude-config,
    # audit-docs, audit-loop-run, review-sprint) — the third read-side signal
    # alongside harness_events (executor, ENH-2493) and verdict_events
    # (verifier, ENH-2504). Live-write-only, like verdict_events — excluded
    # from _REBUILD_TABLES/_REBUILD_SEARCH_KINDS.
    """
    CREATE TABLE IF NOT EXISTS review_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        reviewer_skill TEXT NOT NULL,
        target_kind TEXT,
        target_id TEXT,
        severity_counts TEXT,
        findings_count INTEGER,
        findings_json_summary TEXT,
        verdict TEXT,
        head_sha TEXT,
        branch TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_review_skill ON review_events(reviewer_skill);
    CREATE INDEX IF NOT EXISTS idx_review_target ON review_events(target_id);
    CREATE INDEX IF NOT EXISTS idx_review_session ON review_events(session_id);
    """,
    # v36 (ENH-2771): issue_num INTEGER — a stable numeric join key on
    # issue_events/issue_snapshots alongside the mutable issue_id TEXT display
    # column. An issue's type is mutable metadata (ENH -> FEAT retypes happen
    # routinely) but its number is immutable and globally unique
    # (ll-issues next-id allocates numbers with no type argument), so keying
    # history on issue_id silently splits one issue's history across two rows
    # whenever it is retyped. Backfill is a pure trailing-digit extraction
    # (`TYPE-NNN` -> NNN); no regex needed, so it runs inline as SQL rather
    # than through the _backfill_issues_and_snapshots()/_backfill_snapshots()
    # Python pass (those are updated too, in this same change, so a future
    # `backfill()` re-run also populates issue_num for newly-ingested rows).
    #
    # Ordering is load-bearing: backfill issue_num BEFORE the collision-merge
    # DELETE, and the DELETE BEFORE the new (issue_num, transition) unique
    # index, or the retype-split rows for the seven currently-known collided
    # numbers (see ENH-2771's Current Behavior table) would violate the new
    # constraint. The collision-merge rule is Option A (keep the earliest
    # `ts`) per ENH-2771's Decision Rationale: it is expressible as a single
    # pure-SQL statement with no new migration mechanism, unlike Option B
    # (prefer on-disk type), which would need a Python reconciliation pass
    # with no precedent in this file's migration history and is lossy for the
    # ~1.6%/~3% of issue_events/issue_snapshots rows with NULL issue_type.
    # ts is stored as an ISO-8601 string (session_store.py, see record_issue_event/
    # record_issue_snapshot), so lexical ORDER BY ts ASC is chronological.
    """
    ALTER TABLE issue_events ADD COLUMN issue_num INTEGER;
    ALTER TABLE issue_snapshots ADD COLUMN issue_num INTEGER;
    UPDATE issue_events
        SET issue_num = CAST(substr(issue_id, instr(issue_id, '-') + 1) AS INTEGER)
        WHERE issue_id IS NOT NULL AND instr(issue_id, '-') > 0;
    UPDATE issue_snapshots
        SET issue_num = CAST(substr(issue_id, instr(issue_id, '-') + 1) AS INTEGER)
        WHERE issue_id IS NOT NULL AND instr(issue_id, '-') > 0;
    DELETE FROM issue_events
    WHERE id NOT IN (
        SELECT id FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY issue_num, transition ORDER BY ts ASC
            ) AS rn
            FROM issue_events
            WHERE issue_num IS NOT NULL
        ) WHERE rn = 1
    ) AND issue_num IS NOT NULL;
    DELETE FROM issue_snapshots
    WHERE id NOT IN (
        SELECT id FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY issue_num, transition ORDER BY ts ASC
            ) AS rn
            FROM issue_snapshots
            WHERE issue_num IS NOT NULL
        ) WHERE rn = 1
    ) AND issue_num IS NOT NULL;
    DROP INDEX IF EXISTS idx_issue_events_dedup;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_events_dedup
        ON issue_events(issue_num, transition) WHERE issue_num IS NOT NULL;
    DROP INDEX IF EXISTS idx_issue_snapshots_dedup;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_snapshots_dedup
        ON issue_snapshots(issue_num, transition) WHERE issue_num IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_issue_events_num ON issue_events(issue_num);
    CREATE INDEX IF NOT EXISTS idx_issue_snapshots_num ON issue_snapshots(issue_num);
    DROP VIEW IF EXISTS issue_sessions;
    CREATE VIEW issue_sessions AS
    SELECT MIN(ie.issue_id) AS issue_id,
           ie.issue_num AS issue_num,
           ie.session_id,
           s.jsonl_path,
           MIN(ie.ts) AS first_message_ts,
           MAX(ie.ts) AS last_message_ts
    FROM issue_events ie
    LEFT JOIN sessions s ON s.session_id = ie.session_id
    WHERE ie.session_id IS NOT NULL
    GROUP BY ie.issue_num, ie.session_id
    UNION ALL
    SELECT l.issue_id,
           CAST(substr(l.issue_id, instr(l.issue_id, '-') + 1) AS INTEGER) AS issue_num,
           l.session_id, l.jsonl_path, l.first_message_ts, l.last_message_ts
    FROM legacy_issue_sessions_ts_overlap l
    WHERE CAST(substr(l.issue_id, instr(l.issue_id, '-') + 1) AS INTEGER) NOT IN (
        SELECT issue_num FROM issue_events
        WHERE session_id IS NOT NULL AND issue_num IS NOT NULL
    );
    """,
    # (ENH-2814): persist the FSM's explicit failure signal on loop_runs so
    # consumers read it instead of re-deriving failure-ness from the terminal
    # state's name. 1 = the run stopped on a state declared `failure: true`;
    # 0 = it did not. NULL marks a pre-ENH-2814 row whose failure-ness was
    # never recorded — those still fall back to the legacy name check (see
    # history_reader._WASTED_RUN_PREDICATE). Fix-forward only: existing rows
    # are not backfilled.
    """
    ALTER TABLE loop_runs ADD COLUMN failure_terminal INTEGER;
    CREATE INDEX IF NOT EXISTS idx_loop_runs_failure_terminal
        ON loop_runs(failure_terminal);
    """,
    # (ENH-2866): dequeue-time base-state stamp on the per-issue orchestration
    # row. base_sha is the commit SHA the work item started from, resolved and
    # persisted before anything mutates the tree or the issue file, so a
    # consumer can read it while the issue is still in flight. base_dirty is 1
    # when the tree had *tracked* modifications at stamp time (untracked files
    # are excluded — a checkout-based reconstruction is unaffected by them),
    # 0 when clean. NULL on either column means "unstamped": the orchestrator
    # predates this stamp, opted out, or its `git rev-parse` failed — readers
    # (history_reader.read_base_sha) return None and consumers fall back to
    # merge-base. Deliberately not on loop_runs: that table is one row per run
    # with no issue dimension, and autodev is covered transitively through its
    # `ll-auto --only` shell-out. Fix-forward only: existing rows are not
    # backfilled.
    """
    ALTER TABLE orchestration_runs ADD COLUMN base_sha TEXT;
    ALTER TABLE orchestration_runs ADD COLUMN base_dirty INTEGER;
    """,
    # (ENH-141): content-pinning the harness run. head_sha/branch already
    # pin the whole tree at run time (v31/ENH-2739), but two runs at the
    # same head_sha can still differ when the working tree was dirty, and a
    # cross-commit comparison cannot tell whether the skill under test
    # actually changed without diffing by hand. The new columns capture
    # three more pieces of evidence alongside head_sha/branch:
    #   * target_path — the absolute path of the resolved skill file (skill
    #     runner), DSL task YAML (dsl-task runner), or NULL for non-file
    #     runners (cmd/mcp).
    #   * target_content_hash — a 16-char SHA-256 prefix of the resolved
    #     file's bytes, or of the literal prompt text for the prompt
    #     runner. NULL when unresolvable (cmd/mcp) or the file is
    #     unreadable.
    #   * dirty — 1 when `git status --porcelain --untracked-files=no`
    #     returned non-empty at run time, 0 when clean, NULL when not in a
    #     git repo, git is unavailable, or the call timed out.
    # NULL means "not stamped": readers fall back to comparing by head_sha
    # alone (the v31 contract). The new columns are populated
    # best-effort inside the existing `contextlib.suppress(Exception)`
    # wrapper at the call site (cli/harness.py), so a failing hash or
    # unavailable git never changes the harness exit code. Fix-forward
    # only: existing rows are not backfilled.
    """
    ALTER TABLE harness_events ADD COLUMN target_content_hash TEXT;
    ALTER TABLE harness_events ADD COLUMN target_path TEXT;
    ALTER TABLE harness_events ADD COLUMN dirty INTEGER;
    """,
    # (ENH-2997): persistence surface for the pre-patch-check bundle the FSM
    # executor's guarded-window hook produces. This is the only surface
    # ENH-2998's run_dir-less `cli/harness.py` consumer can discover a
    # verdict by issue ID from -- the run-dir JSON file (MR-3) is the
    # sibling surface a delegating parent loop reads directly. One row per
    # guarded-state exit (never upserted: a run can guard multiple states,
    # and each exit's bundle is independently evidence); readers take the
    # most recent row for an issue_id. evidence_json is PrePatchEvidence.to_dict()
    # verbatim, so the reader needs no separate serializer.
    """
    CREATE TABLE IF NOT EXISTS prepatch_evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        issue_id TEXT NOT NULL,
        run_id TEXT,
        state TEXT,
        evidence_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_prepatch_evidence_issue_id
        ON prepatch_evidence(issue_id, id DESC);
    """,
]


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
