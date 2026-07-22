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
    SummaryNode:      dataclass for summary_nodes rows (FEAT-1712)
    GrepResult:       dataclass for ll_grep results with summary context (FEAT-1712)
    SectionProvider:  config-addressable digest section (ENH-1907)
    ProjectDigest:    aggregated project-context snapshot (ENH-1907)
    SECTION_PROVIDERS: registry of v1 section providers (ENH-1907)
    SkillEvent:       dataclass for skill event rows incl. completion columns (ENH-2460)
    CommitEvent:      dataclass for commit event rows (ENH-2458)
    RunEvent:         dataclass for test run event rows (ENH-2459)
    OrchestrationRun: dataclass for per-issue batch outcomes (ENH-2492)
    LoopRun:          dataclass for loop_runs summary rows (ENH-2463)
    find_user_corrections(topic, ...) -> list[UserCorrection]
    recent_file_events(path, ...) -> list[FileEvent]
    search(query, ...) -> list[SearchResult]
    related_issue_events(issue_id, ...) -> list[IssueEvent]
    recent_skill_events(skill_name, ...) -> list[SkillEvent]
    summarize_skills(since, ...) -> list[dict]
    cost_attribution(group_by, ...) -> list[dict]
    recent_commit_events(branch, issue_id, ...) -> list[CommitEvent]
    recent_test_runs(branch, head_sha, ...) -> list[RunEvent]
    recent_orchestration_runs(driver, issue_id, ...) -> list[OrchestrationRun]
    aggregate_orchestration_runs(group_by, ...) -> list[dict]
    recent_loop_runs(loop_name, ...) -> list[LoopRun]
    find_loop_run(run_id, ...) -> LoopRun | None
    aggregate_loop_runs(group_by, ...) -> list[dict]
    LearningTestEvent: dataclass for learning_test_events rows (ENH-2466)
    recent_learning_tests(status, ...) -> list[LearningTestEvent]
    find_learning_test(target, ...) -> LearningTestEvent | None
    LifecycleEvent: dataclass for session_lifecycle_events rows (ENH-2495)
    recent_lifecycle_events(event, since, ...) -> list[LifecycleEvent]
    handoff_frequency(since, ...) -> int
    worktree_summary(issue_id, since, ...) -> list[dict] (ENH-2509)
    SubagentRun: dataclass for subagent_runs rows (ENH-2505)
    subagent_tree(session_id, ...) -> list[SubagentRun]
    subagent_retries(agent_type, since, ...) -> list[dict]
    subagent_budget(session_id, ...) -> dict | None
    find_session_for_issue_transition(issue_id, transition, ...) -> str | None
    sessions_for_issue(issue_id, ...) -> list[SessionRef]
    issue_effort(issue_id, ...) -> dict | None
    recent_issue_velocity(limit, ...) -> list[dict]
    lookup_session_metadata(session_id, ...) -> dict
    conversation_turns(db_path, ...) -> list[list[tuple[str, str]]]
    ll_grep(pattern, ...) -> list[GrepResult]
    ll_expand(summary_id, ...) -> list[dict]
    ll_describe(node_id, ...) -> SummaryNode | None
    condensed_nodes_for_issue(issue_id, ...) -> list[SummaryNode]
    project_digest(db_path, ...) -> ProjectDigest
    render_project_context(digest, ...) -> str
    HookEvent:        dataclass for hook_events rows (ENH-2506)
    recent_hook_events(event_name, exit_code, since, ...) -> list[HookEvent]
    hook_failure_rate(event_name, since, ...) -> float | None
    hook_latency_p95(event_name, since, ...) -> float | None
    HarnessEvent:     dataclass for harness_events rows (ENH-2741)
    recent_harness_events(runner, target, since, ...) -> list[HarnessEvent]
    harness_eval_pass_rate(target, since, ...) -> float | None
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from little_loops.session_store import DEFAULT_DB_PATH, ensure_db, fts_phrase

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
    session_id: str | None = None


@dataclass
class SkillEvent:
    """A skill_events row including completion columns (ENH-2460).

    ``exit_code``/``success``/``duration_ms`` are ``None`` for rows recorded
    at dispatch time only (the user_prompt_submit hook) or written before the
    v15 migration.
    """

    ts: str
    session_id: str | None
    skill_name: str | None
    args: str | None
    exit_code: int | None = None
    success: int | None = None
    duration_ms: int | None = None


@dataclass
class CommitEvent:
    """A commit_events row (ENH-2458)."""

    ts: str
    commit_sha: str
    parent_sha: str | None
    message: str
    author: str | None
    branch: str | None
    issue_id: str | None
    files_json: str | None


@dataclass
class RunEvent:
    """A test_run_events row (ENH-2459)."""

    ts: str
    ended_at: str | None
    total: int | None
    passed: int | None
    failed: int | None
    errored: int | None
    skipped: int | None
    duration_s: float | None
    failing_names_json: str | None
    env_label: str | None
    head_sha: str | None
    branch: str | None
    command: str | None

    @property
    def pass_rate(self) -> float | None:
        """Fraction of collected tests that passed, or None when total is 0/unknown."""
        if not self.total:
            return None
        return (self.passed or 0) / self.total


@dataclass
class OrchestrationRun:
    """A per-issue orchestration outcome from ll-auto/parallel/sprint (ENH-2492)."""

    run_id: str
    driver: str
    issue_id: str
    status: str
    failure_reason: str | None
    duration_s: float | None
    wave: str | None
    pr_url: str | None
    started_at: str | None
    ended_at: str | None
    head_sha: str | None
    branch: str | None


@dataclass
class LoopRun:
    """A ``loop_runs`` row — one summary per completed FSM loop run (ENH-2463)."""

    run_id: str
    loop_name: str
    started_at: str | None
    ended_at: str | None
    final_state: str | None
    iterations: int | None
    terminated_by: str | None
    error: str | None
    evaluator_score: float | None
    diagnostics_path: str | None
    head_sha: str | None
    branch: str | None


@dataclass
class LearningTestEvent:
    """A ``learning_test_events`` row — mirror of a Learning Test Registry
    record (``.ll/learning-tests/<slug>.md``, the ``LearnTestRecord`` dataclass
    in ``little_loops.learning_tests``). Not to be confused with that
    registry-file dataclass; this is the DB-side mirror row (ENH-2466)."""

    ts: str
    record_id: str
    target: str | None
    status: str | None
    assertions_json: str | None
    date: str | None
    raw_output_path: str | None


@dataclass
class LifecycleEvent:
    """A ``session_lifecycle_events`` row — a session-lifecycle / handoff
    transition (``handoff_needed``, ``compaction``, ``stale_ref_sweep``, plus
    ENH-2509's ``worktree_*`` discriminators sharing this table) (ENH-2495)."""

    id: int
    ts: str
    session_id: str | None
    event: str
    detail: dict | None
    head_sha: str | None
    branch: str | None


@dataclass
class SubagentRun:
    """A ``subagent_runs`` row — one Task/Agent spawn (ENH-2505).

    ``agent_id`` is spawn-local (scoped to ``parent_session_id``, not a
    ``sessions.session_id``); a subagent's transcript is a nested file
    (``<parent-transcript-dir>/subagents/agent-<id>.jsonl``), not a top-level
    session row.
    """

    ts: str
    parent_session_id: str | None
    agent_id: str | None
    agent_type: str | None
    agent_transcript_path: str | None
    started_at: str | None
    ended_at: str | None
    status: str | None


@dataclass
class UsageEvent:
    """A ``usage_events`` row — real LLM token counts per assistant turn (ENH-2461).

    Column names mirror the Anthropic API usage fields. ``state`` is always
    ``None`` on parser-written rows (the transcript stream carries no FSM-state
    boundary); ``cost_usd`` is ``None`` when the model is not in the pricing
    table.
    """

    ts: str
    session_id: str | None
    model: str | None
    state: str | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_input_tokens: int | None
    cache_creation_input_tokens: int | None
    cost_usd: float | None


@dataclass
class SessionRef:
    """A session that co-occurred with an issue's active period (ENH-1711)."""

    issue_id: str | None
    session_id: str | None
    jsonl_path: str | None
    first_message_ts: str | None
    last_message_ts: str | None


@dataclass
class SummaryNode:
    """A summary_nodes row from the LCM-style compaction DAG (FEAT-1712)."""

    id: int
    kind: str
    content: str
    tokens: int | None
    parent_id: int | None
    session_id: str | None
    ts_start: str | None
    ts_end: str | None
    created_at: str
    level: int | None


@dataclass
class GrepResult:
    """A message_event regex match with its covering summary node context (FEAT-1712)."""

    message_event_id: int
    session_id: str | None
    ts: str
    content: str
    summary_id: int | None
    summary_kind: str | None


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


def related_issue_events(
    issue_id: str,
    *,
    session_id: str | None = None,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[IssueEvent]:
    """Return issue events for *issue_id*, ordered by most recent first.

    When *session_id* is given, only events recorded with that exact
    authoritative session ID are returned (ENH-2462); the default returns all
    rows regardless of session.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, issue_id, transition, discovered_by, issue_type, priority, session_id "
            "FROM issue_events WHERE issue_id = ? "
        )
        params: list[Any] = [issue_id]
        if session_id is not None:
            sql += "AND session_id = ? "
            params.append(session_id)
        sql += "ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: related_issue_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, IssueEvent) for row in rows]


def find_session_for_issue_transition(
    issue_id: str,
    transition: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> str | None:
    """Return the session_id recorded for an exact issue transition (ENH-2462).

    Reads the authoritative ``issue_events.session_id`` column; returns
    ``None`` for legacy rows written before the v16 migration, when the
    transition was emitted outside a session-known context, or when no such
    transition exists.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT session_id FROM issue_events "
            "WHERE issue_id = ? AND transition = ? AND session_id IS NOT NULL "
            "ORDER BY ts DESC LIMIT 1",
            (issue_id, transition),
        ).fetchone()
    except sqlite3.Error:
        logger.warning(
            "history_reader: find_session_for_issue_transition query failed", exc_info=True
        )
        return None
    finally:
        conn.close()
    return row["session_id"] if row else None


def recent_skill_events(
    skill_name: str | None = None,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SkillEvent]:
    """Return recent skill events, newest first, incl. completion columns (ENH-2460)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, session_id, skill_name, args, exit_code, success, duration_ms "
            "FROM skill_events "
        )
        params: list[Any] = []
        if skill_name is not None:
            sql += "WHERE skill_name = ? "
            params.append(skill_name)
        sql += "ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_skill_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, SkillEvent) for row in rows]


def summarize_skills(
    since: str | None = None,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Per-skill rollup of invocations / completions / success rate (ENH-2460).

    ``success_rate`` and ``avg_duration_ms`` are computed over rows that carry
    a completion signal only (dispatch-only rows have ``success IS NULL`` and
    count toward ``invocations`` but not the rate). *since* is an ISO 8601
    lower bound on ``ts``. Sorted by invocation count, descending.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT skill_name, COUNT(*) AS invocations, "
            "COUNT(success) AS completions, "
            "SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successes, "
            "AVG(duration_ms) AS avg_duration_ms "
            "FROM skill_events "
        )
        params: list[Any] = []
        if since is not None:
            sql += "WHERE ts >= ? "
            params.append(since)
        sql += "GROUP BY skill_name ORDER BY invocations DESC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: summarize_skills query failed", exc_info=True)
        return []
    finally:
        conn.close()
    result: list[dict] = []
    for row in rows:
        completions = row["completions"] or 0
        successes = row["successes"] or 0
        result.append(
            {
                "skill_name": row["skill_name"],
                "invocations": row["invocations"],
                "completions": completions,
                "successes": successes,
                "success_rate": (successes / completions) if completions else None,
                "avg_duration_ms": row["avg_duration_ms"],
            }
        )
    return result


def agent_usage(
    since: str | None = None,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Per-agent rollup of Task-tool subagent spawn counts (ENH-2497).

    Only rows with ``tool_name = 'Task'`` and a non-NULL ``agent_type`` count;
    other tools are excluded. *since* is an ISO 8601 lower bound on ``ts``.
    Sorted by invocation count, descending.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT agent_type, COUNT(*) AS invocations FROM tool_events "
            "WHERE tool_name = 'Task' AND agent_type IS NOT NULL "
        )
        params: list[Any] = []
        if since is not None:
            sql += "AND ts >= ? "
            params.append(since)
        sql += "GROUP BY agent_type ORDER BY invocations DESC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: agent_usage query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [{"agent_type": row["agent_type"], "invocations": row["invocations"]} for row in rows]


def recent_tool_events(
    agent_type: str | None = None,
    mcp_server: str | None = None,
    mcp_tool: str | None = None,
    mcp_outcome: str | None = None,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Return recent ``tool_events`` rows, newest first, optionally filtered by
    ``agent_type`` (ENH-2497) and/or ``mcp_server``/``mcp_tool``/``mcp_outcome`` (ENH-2511).
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, session_id, tool_name, args_hash, result_size, bytes_in, "
            "bytes_out, cache_hit, agent_type, mcp_server, mcp_tool, mcp_outcome, "
            "latency_ms FROM tool_events "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if agent_type is not None:
            clauses.append("agent_type = ?")
            params.append(agent_type)
        if mcp_server is not None:
            clauses.append("mcp_server = ?")
            params.append(mcp_server)
        if mcp_tool is not None:
            clauses.append("mcp_tool = ?")
            params.append(mcp_tool)
        if mcp_outcome is not None:
            clauses.append("mcp_outcome = ?")
            params.append(mcp_outcome)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_tool_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [dict(row) for row in rows]


def mcp_server_usage(
    server: str | None = None,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Per-MCP-server rollup of invocations / completions / success rate / avg latency (ENH-2511)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT mcp_server, COUNT(*) AS invocations, "
            "COUNT(mcp_outcome) AS completions, "
            "SUM(CASE WHEN mcp_outcome = 'success' THEN 1 ELSE 0 END) AS successes, "
            "AVG(latency_ms) AS avg_latency_ms "
            "FROM tool_events WHERE mcp_server IS NOT NULL "
        )
        params: list[Any] = []
        if server is not None:
            sql += "AND mcp_server = ? "
            params.append(server)
        if since is not None:
            sql += "AND ts >= ? "
            params.append(since)
        sql += "GROUP BY mcp_server ORDER BY invocations DESC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: mcp_server_usage query failed", exc_info=True)
        return []
    finally:
        conn.close()
    result: list[dict] = []
    for row in rows:
        completions = row["completions"] or 0
        successes = row["successes"] or 0
        result.append(
            {
                "mcp_server": row["mcp_server"],
                "invocations": row["invocations"],
                "completions": completions,
                "successes": successes,
                "success_rate": (successes / completions) if completions else None,
                "avg_latency_ms": row["avg_latency_ms"],
            }
        )
    return result


def mcp_failure_rate(
    server: str | None = None,
    tool: str | None = None,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Per-server/tool MCP failure rate rollup (ENH-2511)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT mcp_server, mcp_tool, COUNT(*) AS invocations, "
            "SUM(CASE WHEN mcp_outcome = 'error' THEN 1 ELSE 0 END) AS error_count "
            "FROM tool_events WHERE mcp_server IS NOT NULL "
        )
        params: list[Any] = []
        if server is not None:
            sql += "AND mcp_server = ? "
            params.append(server)
        if tool is not None:
            sql += "AND mcp_tool = ? "
            params.append(tool)
        if since is not None:
            sql += "AND ts >= ? "
            params.append(since)
        sql += "GROUP BY mcp_server, mcp_tool ORDER BY invocations DESC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: mcp_failure_rate query failed", exc_info=True)
        return []
    finally:
        conn.close()
    result: list[dict] = []
    for row in rows:
        invocations = row["invocations"] or 0
        error_count = row["error_count"] or 0
        result.append(
            {
                "mcp_server": row["mcp_server"],
                "mcp_tool": row["mcp_tool"],
                "invocations": invocations,
                "error_count": error_count,
                "failure_rate": (error_count / invocations) if invocations else None,
            }
        )
    return result


# FEAT-2478 — accepted GROUP BY dimensions for cost_attribution(). Maps the
# caller-facing OTel attribute name (and raw column aliases) to the physical
# usage_events column. Whitelisted to keep the GROUP BY clause injection-safe.
_COST_ATTR_GROUP_COLUMNS: dict[str, str] = {
    "gen_ai.invocation.id": "invocation_id",
    "gen_ai.provider.vendor": "provider_vendor",
    "invocation_id": "invocation_id",
    "provider_vendor": "provider_vendor",
    "session_id": "session_id",
    "model": "model",
    "state": "state",
    "run_id": "run_id",
}


def cost_attribution(
    group_by: str = "gen_ai.invocation.id",
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Per-``group_by`` token/cost rollup over ``usage_events`` (FEAT-2478).

    *group_by* is an OTel attribute name (``gen_ai.invocation.id`` /
    ``gen_ai.provider.vendor``) or a raw ``usage_events`` column
    (``session_id`` / ``model`` / ``state`` / ``invocation_id`` /
    ``provider_vendor``); any other value raises ``ValueError`` (the clause is
    whitelisted, never interpolated raw). *since* is an ISO 8601 lower bound on
    ``ts``. Sorted by ``input_tokens`` sum descending.

    Each returned dict carries the group key under both the requested
    *group_by* name and — for the default invocation grouping — the summed token
    counts under the canonical dotted OTel names, so a
    ``GROUP BY gen_ai.invocation.id`` rollup matches raw ``result``-event
    ``usage`` totals row-for-row (see FEAT-2478 § Acceptance Criteria).
    """
    from little_loops.observability.tracing import (
        GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
        GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
        GEN_AI_USAGE_INPUT_TOKENS,
        GEN_AI_USAGE_OUTPUT_TOKENS,
    )

    column = _COST_ATTR_GROUP_COLUMNS.get(group_by)
    if column is None:
        raise ValueError(
            f"cost_attribution: unsupported group_by {group_by!r}; "
            f"expected one of {sorted(_COST_ATTR_GROUP_COLUMNS)}"
        )
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            f"SELECT {column} AS grp, "
            "SUM(input_tokens) AS input_tokens, "
            "SUM(output_tokens) AS output_tokens, "
            "SUM(cache_read_input_tokens) AS cache_read_input_tokens, "
            "SUM(cache_creation_input_tokens) AS cache_creation_input_tokens, "
            "SUM(cost_usd) AS cost_usd, "
            "COUNT(*) AS invocations "
            "FROM usage_events "
        )
        params: list[Any] = []
        if since is not None:
            sql += "WHERE ts >= ? "
            params.append(since)
        sql += "GROUP BY grp ORDER BY input_tokens DESC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: cost_attribution query failed", exc_info=True)
        return []
    finally:
        conn.close()
    result: list[dict] = []
    for row in rows:
        result.append(
            {
                group_by: row["grp"],
                GEN_AI_USAGE_INPUT_TOKENS: row["input_tokens"] or 0,
                GEN_AI_USAGE_OUTPUT_TOKENS: row["output_tokens"] or 0,
                GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS: row["cache_read_input_tokens"] or 0,
                GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS: (row["cache_creation_input_tokens"] or 0),
                "cost_usd": row["cost_usd"] or 0.0,
                "invocations": row["invocations"],
            }
        )
    return result


def recent_usage_events(
    session_id: str | None = None,
    model: str | None = None,
    *,
    since: str | None = None,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[UsageEvent]:
    """Return recent usage events, newest first, optionally filtered (ENH-2461).

    *session_id* / *model* narrow the result; *since* is an ISO 8601 lower bound
    on ``ts``. Returns ``[]`` on any read failure (graceful degradation).
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, session_id, model, state, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens, cost_usd "
            "FROM usage_events "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if model is not None:
            clauses.append("model = ?")
            params.append(model)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_usage_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, UsageEvent) for row in rows]


def aggregate_usage(
    group_by: Literal["model", "session"] = "model",
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Roll up token totals and cost, grouped by ``model`` or ``session`` (ENH-2461).

    Each result dict carries the group key, ``events`` (row count), summed
    ``input_tokens`` / ``output_tokens`` / ``cache_read_input_tokens`` /
    ``cache_creation_input_tokens``, and ``cost_usd`` (rows with an unpriced
    model contribute ``NULL`` cost, summed as 0 by SQLite). *since* is an ISO
    8601 lower bound on ``ts``. Sorted by ``cost_usd`` descending. Grain is
    per-call — usage_events carries no FSM ``state``, so per-state rollups are
    not offered here (ENH-2461 Addendum 2).
    """
    key_col = "model" if group_by == "model" else "session_id"
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            f"SELECT {key_col} AS group_key, COUNT(*) AS events, "  # noqa: S608 - key_col fixed
            "SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens, "
            "SUM(cache_read_input_tokens) AS cache_read_input_tokens, "
            "SUM(cache_creation_input_tokens) AS cache_creation_input_tokens, "
            "SUM(cost_usd) AS cost_usd "
            "FROM usage_events "
        )
        params: list[Any] = []
        if since is not None:
            sql += "WHERE ts >= ? "
            params.append(since)
        sql += f"GROUP BY {key_col} ORDER BY cost_usd DESC"  # noqa: S608 - key_col fixed
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: aggregate_usage query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [
        {
            group_by: row["group_key"],
            "events": row["events"],
            "input_tokens": row["input_tokens"] or 0,
            "output_tokens": row["output_tokens"] or 0,
            "cache_read_input_tokens": row["cache_read_input_tokens"] or 0,
            "cache_creation_input_tokens": row["cache_creation_input_tokens"] or 0,
            "cost_usd": row["cost_usd"],
        }
        for row in rows
    ]


def recent_commit_events(
    *,
    branch: str | None = None,
    issue_id: str | None = None,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[CommitEvent]:
    """Return recent commit events, newest first, optionally filtered (ENH-2458)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, commit_sha, parent_sha, message, author, branch, issue_id, files_json "
            "FROM commit_events "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if branch is not None:
            clauses.append("branch = ?")
            params.append(branch)
        if issue_id is not None:
            clauses.append("issue_id = ?")
            params.append(issue_id)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_commit_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, CommitEvent) for row in rows]


def recent_learning_tests(
    *,
    status: str | None = None,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[LearningTestEvent]:
    """Return recent Learning Test Registry mirror rows, newest first (ENH-2466)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, record_id, target, status, assertions_json, date, raw_output_path "
            "FROM learning_test_events "
        )
        params: list[Any] = []
        if status is not None:
            sql += "WHERE status = ? "
            params.append(status)
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_learning_tests query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, LearningTestEvent) for row in rows]


def find_learning_test(
    target: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> LearningTestEvent | None:
    """Return the mirror row for *target* (slugified to ``record_id``), or None (ENH-2466)."""
    from little_loops.issue_parser import slugify

    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT ts, record_id, target, status, assertions_json, date, raw_output_path "
            "FROM learning_test_events WHERE record_id = ?",
            (slugify(target),),
        ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: find_learning_test query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None:
        return None
    return _row_to_dataclass(row, LearningTestEvent)


def recent_lifecycle_events(
    *,
    event: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[LifecycleEvent]:
    """Return recent session-lifecycle events, newest first, optionally filtered (ENH-2495)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT id, ts, session_id, event, detail, head_sha, branch "
            "FROM session_lifecycle_events "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if event is not None:
            clauses.append("event = ?")
            params.append(event)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_lifecycle_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    results = []
    for row in rows:
        kwargs = dict(row)
        detail_raw = kwargs.get("detail")
        kwargs["detail"] = json.loads(detail_raw) if detail_raw else None
        results.append(LifecycleEvent(**kwargs))
    return results


def handoff_frequency(
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> int:
    """Count of ``handoff_needed`` lifecycle events, optionally since a timestamp (ENH-2495)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return 0
    try:
        sql = "SELECT COUNT(*) FROM session_lifecycle_events WHERE event = 'handoff_needed'"
        params: list[Any] = []
        if since is not None:
            sql += " AND ts >= ?"
            params.append(since)
        row = conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: handoff_frequency query failed", exc_info=True)
        return 0
    finally:
        conn.close()
    return int(row[0]) if row else 0


def worktree_summary(
    *,
    issue_id: str | None = None,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Per-issue worktree op counts from ``worktree_*`` lifecycle events (ENH-2509).

    Returns one dict per issue_id with ``created``/``merged``/``deleted`` counts,
    derived from ``json_extract(detail, '$.issue_id')``. Rows with no ``issue_id``
    in ``detail`` (e.g. orphan-sweep cleanups) group under ``issue_id=None``.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT json_extract(detail, '$.issue_id') AS issue_id, "
            "COUNT(*) FILTER (WHERE event = 'worktree_create') AS created, "
            "COUNT(*) FILTER (WHERE event = 'worktree_merge') AS merged, "
            "COUNT(*) FILTER (WHERE event = 'worktree_delete') AS deleted "
            "FROM session_lifecycle_events WHERE event LIKE 'worktree_%' "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if issue_id is not None:
            clauses.append("json_extract(detail, '$.issue_id') = ?")
            params.append(issue_id)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if clauses:
            sql += "AND " + " AND ".join(clauses) + " "
        sql += "GROUP BY 1 ORDER BY 1"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: worktree_summary query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [dict(row) for row in rows]


def subagent_tree(
    session_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SubagentRun]:
    """Direct ``agent_id`` spawns for a parent session (ENH-2505).

    Recursion into grandchildren is not performed here — a subagent's own
    spawns live in its nested transcript
    (``agent_transcript_path``), not a joinable ``sessions`` row, so walking
    the full tree requires re-parsing that transcript rather than a SQL join.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT ts, parent_session_id, agent_id, agent_type, agent_transcript_path, "
            "started_at, ended_at, status FROM subagent_runs "
            "WHERE parent_session_id = ? ORDER BY started_at",
            (session_id,),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: subagent_tree query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, SubagentRun) for row in rows]


def subagent_retries(
    agent_type: str,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Per-parent re-spawn counts for *agent_type* — the "oscillation" signal (ENH-2505).

    Returns one dict per ``parent_session_id`` with a ``spawn_count`` for that
    agent type, restricted to parents that spawned it more than once.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT parent_session_id, COUNT(*) AS spawn_count FROM subagent_runs "
            "WHERE agent_type = ? "
        )
        params: list[Any] = [agent_type]
        if since is not None:
            sql += "AND started_at >= ? "
            params.append(since)
        sql += "GROUP BY parent_session_id HAVING COUNT(*) > 1 ORDER BY spawn_count DESC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: subagent_retries query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [dict(row) for row in rows]


def subagent_budget(
    session_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> dict | None:
    """Total subagent-run duration rollup for a parent session — the "burn budget" signal (ENH-2505).

    Returns ``None`` when the DB is absent or no subagent rows exist for
    *session_id*. ``total_duration_s`` only accounts for rows with both
    ``started_at`` and ``ended_at`` set; still-running or malformed rows are
    excluded from the sum but counted in ``spawn_count``.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS spawn_count, "
            "SUM(CASE WHEN started_at IS NOT NULL AND ended_at IS NOT NULL "
            "THEN (julianday(ended_at) - julianday(started_at)) * 86400 ELSE 0 END) "
            "AS total_duration_s "
            "FROM subagent_runs WHERE parent_session_id = ?",
            (session_id,),
        ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: subagent_budget query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None or not row["spawn_count"]:
        return None
    return {
        "spawn_count": row["spawn_count"],
        "total_duration_s": row["total_duration_s"] or 0.0,
    }


def recent_test_runs(
    *,
    branch: str | None = None,
    head_sha: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[RunEvent]:
    """Return recent test-run events, newest first, optionally filtered (ENH-2459)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, ended_at, total, passed, failed, errored, skipped, duration_s, "
            "failing_names_json, env_label, head_sha, branch, command "
            "FROM test_run_events "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if branch is not None:
            clauses.append("branch = ?")
            params.append(branch)
        if head_sha is not None:
            clauses.append("head_sha = ?")
            params.append(head_sha)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_test_runs query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, RunEvent) for row in rows]


_ORCHESTRATION_GROUP_COLUMNS: dict[str, str] = {
    "driver": "driver",
    "issue_id": "issue_id",
    "status": "status",
}


def recent_orchestration_runs(
    driver: str | None = None,
    issue_id: str | None = None,
    *,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[OrchestrationRun]:
    """Return recent per-issue orchestration outcomes, newest first (ENH-2492)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT run_id, driver, issue_id, status, failure_reason, duration_s, "
            "wave, pr_url, started_at, ended_at, head_sha, branch "
            "FROM orchestration_runs "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if driver is not None:
            clauses.append("driver = ?")
            params.append(driver)
        if issue_id is not None:
            clauses.append("issue_id = ?")
            params.append(issue_id)
        if since is not None:
            clauses.append("COALESCE(ended_at, started_at) >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY COALESCE(ended_at, started_at) DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_orchestration_runs query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, OrchestrationRun) for row in rows]


def aggregate_orchestration_runs(
    group_by: Literal["driver", "issue_id", "status"] = "driver",
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Roll up run count, completion rate, and mean duration by a fixed dimension."""
    column = _ORCHESTRATION_GROUP_COLUMNS.get(group_by)
    if column is None:
        raise ValueError(
            f"aggregate_orchestration_runs: unsupported group_by {group_by!r}; "
            f"expected one of {sorted(_ORCHESTRATION_GROUP_COLUMNS)}"
        )
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            f"SELECT {column} AS group_key, COUNT(*) AS runs, "  # noqa: S608 - fixed map
            "SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed, "
            "AVG(duration_s) AS avg_duration_s FROM orchestration_runs "
        )
        params: list[Any] = []
        if since is not None:
            sql += "WHERE COALESCE(ended_at, started_at) >= ? "
            params.append(since)
        sql += f"GROUP BY {column} ORDER BY runs DESC, group_key"  # noqa: S608 - fixed map
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: aggregate_orchestration_runs query failed", exc_info=True)
        return []
    finally:
        conn.close()

    result: list[dict] = []
    for row in rows:
        runs = row["runs"] or 0
        completed = row["completed"] or 0
        result.append(
            {
                group_by: row["group_key"],
                "runs": runs,
                "completed": completed,
                "success_rate": completed / runs if runs else None,
                "avg_duration_s": row["avg_duration_s"],
            }
        )
    return result


_LOOP_RUN_COLUMNS = (
    "run_id, loop_name, started_at, ended_at, final_state, iterations, "
    "terminated_by, error, evaluator_score, diagnostics_path, head_sha, branch"
)


def recent_loop_runs(
    *,
    loop_name: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[LoopRun]:
    """Return recent loop-run summaries, newest first, optionally filtered (ENH-2463)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = f"SELECT {_LOOP_RUN_COLUMNS} FROM loop_runs "
        clauses: list[str] = []
        params: list[Any] = []
        if loop_name is not None:
            clauses.append("loop_name = ?")
            params.append(loop_name)
        if since is not None:
            clauses.append("COALESCE(ended_at, started_at) >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY COALESCE(ended_at, started_at) DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_loop_runs query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, LoopRun) for row in rows]


def find_loop_run(run_id: str, *, db: Path | str = DEFAULT_DB_PATH) -> LoopRun | None:
    """Return the single ``loop_runs`` row for *run_id*, or None if missing (ENH-2463)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            f"SELECT {_LOOP_RUN_COLUMNS} FROM loop_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: find_loop_run query failed", exc_info=True)
        return None
    finally:
        conn.close()
    return _row_to_dataclass(row, LoopRun) if row is not None else None


_LOOP_RUN_GROUP_COLUMNS: dict[str, str] = {
    "loop_name": "loop_name",
    "terminated_by": "terminated_by",
}


def aggregate_loop_runs(
    group_by: Literal["loop_name", "terminated_by"] = "loop_name",
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Roll up run count and mean iteration count by loop_name or terminated_by (ENH-2463)."""
    column = _LOOP_RUN_GROUP_COLUMNS.get(group_by)
    if column is None:
        raise ValueError(
            f"aggregate_loop_runs: unsupported group_by {group_by!r}; "
            f"expected one of {sorted(_LOOP_RUN_GROUP_COLUMNS)}"
        )
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            f"SELECT {column} AS group_key, COUNT(*) AS runs, "  # noqa: S608 - fixed map
            "AVG(iterations) AS avg_iterations FROM loop_runs "
        )
        params: list[Any] = []
        if since is not None:
            sql += "WHERE COALESCE(ended_at, started_at) >= ? "
            params.append(since)
        sql += f"GROUP BY {column} ORDER BY runs DESC, group_key"  # noqa: S608 - fixed map
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: aggregate_loop_runs query failed", exc_info=True)
        return []
    finally:
        conn.close()

    return [
        {
            group_by: row["group_key"],
            "runs": row["runs"] or 0,
            "avg_iterations": row["avg_iterations"],
        }
        for row in rows
    ]


def sessions_for_issue(
    issue_id: str,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SessionRef]:
    """Return sessions that co-occurred with *issue_id*'s active period.

    Queries the ``issue_sessions`` VIEW. As of the v16 migration (ENH-2462)
    the view prefers exact joins on the authoritative
    ``issue_events.session_id`` column and falls back to the deprecated
    timestamp-overlap inference (``legacy_issue_sessions_ts_overlap``) only
    for issues with no authoritative rows. Live-emitted rows (from
    ``issue_lifecycle.py``'s 6 emit sites) populate ``captured_at`` and
    ``session_id`` directly; no prior ``backfill`` pass is needed for issues
    processed after ENH-1839.

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


def lookup_session_metadata(
    session_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> dict:
    """Return session-quality metadata dict for a session ID (ENH-1943).

    Returns:
        dict with keys: ``has_corrections`` (bool), ``issue_outcome`` (str|None),
        ``tool_count`` (int), ``files_modified`` (int), ``loop_outcome`` (str|None).

        ``loop_outcome`` is always ``None`` until ``loop_events`` gains a
        ``session_id`` column (schema change out of scope).

    Returns empty dict ``{}`` when DB is missing, empty, or lacks relevant tables.
    """
    db_path = Path(db)
    if not db_path.exists():
        return {}
    conn = _connect_readonly(db_path)
    if conn is None:
        return {}
    try:
        # has_corrections: direct query on user_corrections
        row = conn.execute(
            "SELECT COUNT(*) > 0 AS has_corrections FROM user_corrections WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        has_corrections = bool(row["has_corrections"]) if row else False

        # issue_outcome: JOIN through issue_sessions VIEW (issue_events has no
        # session_id column; migration v5 bridges via the VIEW)
        row = conn.execute(
            "SELECT ie.transition "
            "FROM issue_sessions is2 "
            "JOIN issue_events ie ON is2.issue_id = ie.issue_id "
            "WHERE is2.session_id = ? AND ie.transition = 'done' "
            "ORDER BY ie.ts DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        issue_outcome: str | None = row["transition"] if row else None

        # tool_count: direct query on tool_events
        row = conn.execute(
            "SELECT COUNT(*) AS tool_count FROM tool_events WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        tool_count: int = row["tool_count"] if row else 0

        # files_modified: direct query on file_events; op values include both
        # hook-written tool names ('Write') and lowercase variants ('write', 'create')
        row = conn.execute(
            "SELECT COUNT(*) AS files_modified FROM file_events "
            "WHERE session_id = ? AND op IN ('write', 'create', 'Write')",
            (session_id,),
        ).fetchone()
        files_modified: int = row["files_modified"] if row else 0

        # loop_outcome: loop_events has no session_id column; always None
        loop_outcome: None = None

    except sqlite3.Error:
        logger.warning("history_reader: lookup_session_metadata query failed", exc_info=True)
        return {}
    finally:
        conn.close()

    return {
        "has_corrections": has_corrections,
        "issue_outcome": issue_outcome,
        "tool_count": tool_count,
        "files_modified": files_modified,
        "loop_outcome": loop_outcome,
    }


def conversation_turns(
    db_path: Path | str,
    since: datetime | None = None,
    context_window: int = 3,
) -> list[list[tuple[str, str]]]:
    """Return conversation turn-pair windows from ``history.db`` (ENH-1942).

    Queries ``message_events`` and ``assistant_messages``, pairs user messages
    with their assistant responses via temporal adjacency (same algorithm as
    ``_extract_turn_pairs()`` in ``user_messages.py``), and groups them into
    sliding windows of *context_window* turn-pairs each.

    Returns ``[]`` when the database is missing, empty, predates schema v11
    (no ``assistant_messages`` table), or when no turn-pairs match the *since*
    filter. Callers should fall back to JSONL parsing in that case.

    Args:
        db_path: Path to ``history.db``.
        since: Only include turns where the user message timestamp is >= this value.
        context_window: Number of (user, assistant) turn-pairs per output window.

    Returns:
        List of conversation windows; each window is a ``list[tuple[str, str]]``
        alternating between ``("user", text)`` and ``("assistant", text)``.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        # Check that assistant_messages table exists (schema >= v11)
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM sqlite_master "
            "WHERE type = 'table' AND name = 'assistant_messages'"
        ).fetchone()
        if not row or row["n"] == 0:
            return []

        # Pair each user message with assistant messages between it and the
        # NEXT user message (temporal-adjacency, matching _extract_turn_pairs).
        # The subquery finds the next user message timestamp per session;
        # COALESCE defaults to a far-future sentinel for the last message.
        base_sql = (
            "SELECT u.session_id, u.ts AS user_ts, u.content AS user_text, "
            "a.content AS assistant_text "
            "FROM message_events u "
            "JOIN assistant_messages a ON a.session_id = u.session_id "
            "AND a.ts > u.ts "
            "AND a.ts < COALESCE("
            "  (SELECT MIN(u2.ts) FROM message_events u2 "
            "   WHERE u2.session_id = u.session_id AND u2.ts > u.ts), "
            "  '9999-12-31'"
            ") "
        )
        params: list[Any] = []
        if since is not None:
            base_sql += "WHERE u.ts >= ? "
            params.append(since.strftime("%Y-%m-%dT%H:%M:%SZ"))
        base_sql += "ORDER BY u.session_id, u.ts, a.ts"

        rows = conn.execute(base_sql, params or ()).fetchall()

        if not rows:
            return []

        # Group assistant texts by user message.
        # The SQL already only includes assistant messages between consecutive
        # user messages, so simple grouping by (session_id, user_ts) suffices.
        turn_pairs: list[tuple[str, str]] = []
        current_key: tuple[str, str] | None = None
        current_user: str = ""
        assistant_texts: list[str] = []

        for row_ in rows:
            key = (row_["session_id"], row_["user_ts"])
            if key != current_key:
                if current_key is not None and assistant_texts:
                    turn_pairs.append((current_user, "\n\n".join(assistant_texts)))
                current_key = key
                current_user = row_["user_text"]
                assistant_texts = []
            assistant_texts.append(row_["assistant_text"])

        # Flush the final turn
        if current_key is not None and assistant_texts:
            turn_pairs.append((current_user, "\n\n".join(assistant_texts)))

        # Emit sliding windows of context_window turn-pairs
        windows: list[list[tuple[str, str]]] = []
        n = len(turn_pairs)
        if n == 0:
            return []
        for i in range(max(1, n - context_window + 1)):
            window_pairs = turn_pairs[i : i + context_window]
            window: list[tuple[str, str]] = []
            for user_text, assistant_text in window_pairs:
                window.append(("user", user_text))
                window.append(("assistant", assistant_text))
            windows.append(window)

        return windows

    except sqlite3.Error:
        logger.warning("history_reader: conversation_turns query failed", exc_info=True)
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Summary DAG retrieval (FEAT-1712)
# ---------------------------------------------------------------------------


def ll_grep(
    pattern: str,
    *,
    summary_id: int | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[GrepResult]:
    """Regex search over message_events, with covering summary node context.

    Each result includes the summary_id and summary_kind of the leaf node covering the
    matched message (or None/None for messages not yet compacted). If *summary_id* is
    provided, restrict the search to messages covered by that specific node.

    When *summary_id* is a condensed node (kind='condensed'), uses a recursive CTE to
    walk the N-level DAG (condensed → … → leaves via parent_id → message_events via
    summary_spans) so that messages under all descendant leaves are searched regardless
    of condensation depth.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []

    def _regexp(pat: str, val: str | None) -> bool:
        try:
            return bool(re.search(pat, val or "", re.IGNORECASE))
        except re.error:
            return False

    try:
        conn.create_function("regexp_match", 2, _regexp)
        if summary_id is not None:
            # Recursive CTE walks the full N-level DAG from the starting node
            # through all descendants, terminating at leaf nodes that have
            # summary_spans entries.  Works uniformly for both kind='leaf'
            # (CTE = 1 row) and kind='condensed' at any depth.
            rows = conn.execute(
                "WITH RECURSIVE descendants AS ("
                "  SELECT id, kind FROM summary_nodes WHERE id = ?1"
                "  UNION ALL"
                "  SELECT sn.id, sn.kind"
                "  FROM summary_nodes sn"
                "  JOIN descendants d ON sn.parent_id = d.id"
                ")"
                "SELECT me.id, me.session_id, me.ts, me.content,"
                " sn.id AS summary_id, sn.kind AS summary_kind"
                " FROM message_events me"
                " JOIN summary_spans ss ON ss.message_event_id = me.id"
                " JOIN descendants leaf ON leaf.id = ss.summary_id"
                " JOIN summary_nodes sn ON sn.id = leaf.id"
                " WHERE regexp_match(?2, me.content)"
                " ORDER BY me.ts, me.id LIMIT ?3",
                (summary_id, pattern, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT me.id, me.session_id, me.ts, me.content,"
                " sn.id AS summary_id, sn.kind AS summary_kind"
                " FROM message_events me"
                " LEFT JOIN summary_spans ss ON ss.message_event_id = me.id"
                " LEFT JOIN summary_nodes sn ON sn.id = ss.summary_id"
                " WHERE regexp_match(?, me.content)"
                " ORDER BY me.ts, me.id LIMIT ?",
                (pattern, limit),
            ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: ll_grep query failed", exc_info=True)
        return []
    finally:
        conn.close()

    return [
        GrepResult(
            message_event_id=row["id"],
            session_id=row["session_id"],
            ts=row["ts"],
            content=row["content"] or "",
            summary_id=row["summary_id"],
            summary_kind=row["summary_kind"],
        )
        for row in rows
    ]


def ll_expand(
    summary_id: int,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Return the message_events covered by *summary_id*.

    Uses a recursive CTE to walk the N-level summary DAG from the starting
    node through all descendants, terminating at leaf nodes that have
    ``summary_spans`` entries.  Works uniformly for both ``kind='leaf'``
    (CTE = 1 row, direct span join) and ``kind='condensed'`` at any
    condensation depth (CTE descends through intermediate condensed nodes
    to reach the leaves).

    Returns dicts with keys ``id``, ``session_id``, ``ts``, ``content``.
    Empty list when the summary node does not exist or has no spans.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        # Recursive CTE handles leaf and condensed nodes uniformly at any depth.
        # For a leaf node, descendants = {itself} and the summary_spans join is direct.
        # For a condensed node, descendants = {condensed, children, grandchildren, …}
        # and the summary_spans join only matches the leaf-descendant rows.
        rows = conn.execute(
            "WITH RECURSIVE descendants AS ("
            "  SELECT id, kind FROM summary_nodes WHERE id = ?1"
            "  UNION ALL"
            "  SELECT sn.id, sn.kind"
            "  FROM summary_nodes sn"
            "  JOIN descendants d ON sn.parent_id = d.id"
            ")"
            "SELECT me.id, me.session_id, me.ts, me.content"
            " FROM message_events me"
            " JOIN summary_spans ss ON ss.message_event_id = me.id"
            " JOIN descendants leaf ON leaf.id = ss.summary_id"
            " ORDER BY me.ts, me.id",
            (summary_id,),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: ll_expand query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [dict(row) for row in rows]


def ll_describe(
    node_id: int,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> SummaryNode | None:
    """Return metadata for a summary_nodes row.

    Returns ``None`` when the node does not exist or the database is unavailable.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT id, kind, content, tokens, parent_id, session_id,"
            " ts_start, ts_end, created_at, level"
            " FROM summary_nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: ll_describe query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None:
        return None
    return SummaryNode(
        id=row["id"],
        kind=row["kind"],
        content=row["content"],
        tokens=row["tokens"],
        parent_id=row["parent_id"],
        session_id=row["session_id"],
        ts_start=row["ts_start"],
        ts_end=row["ts_end"],
        created_at=row["created_at"],
        level=row["level"],
    )


def condensed_nodes_for_issue(
    issue_id: str,
    *,
    limit: int = 3,
    node_char_cap: int = 500,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SummaryNode]:
    """Return level-0 condensed summary_nodes for an issue's sessions (ENH-2231).

    Joins the ``issue_sessions`` VIEW to ``summary_nodes`` filtering for
    ``kind='condensed'`` and ``level=0`` (per-session condensed nodes, one per
    session).  Returns nodes newest-first, limited to *limit*.  Each node's
    ``content`` is truncated to *node_char_cap* characters.

    Returns an empty list when the DB is absent, the issue has no recorded
    sessions, no condensed nodes have been generated, or any query error occurs.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT sn.id, sn.kind, sn.content, sn.tokens, sn.parent_id, sn.session_id,"
            " sn.ts_start, sn.ts_end, sn.created_at, sn.level"
            " FROM summary_nodes sn"
            " JOIN issue_sessions isl ON isl.session_id = sn.session_id"
            " WHERE isl.issue_id = ?"
            " AND sn.kind = 'condensed'"
            " AND sn.level = 0"
            " ORDER BY sn.ts_end DESC, sn.id DESC"
            " LIMIT ?",
            (issue_id, limit),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: condensed_nodes_for_issue query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [
        SummaryNode(
            id=row["id"],
            kind=row["kind"],
            content=(row["content"] or "")[:node_char_cap],
            tokens=row["tokens"],
            parent_id=row["parent_id"],
            session_id=row["session_id"],
            ts_start=row["ts_start"],
            ts_end=row["ts_end"],
            created_at=row["created_at"],
            level=row["level"],
        )
        for row in rows
    ]


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


# ---------------------------------------------------------------------------
# Hook execution telemetry (ENH-2506)
# ---------------------------------------------------------------------------


@dataclass
class HookEvent:
    """A ``hook_events`` row — one per hook fire (ENH-2506)."""

    ts: str
    session_id: str | None
    event_name: str
    matcher: str | None
    script: str | None
    exit_code: int | None
    duration_ms: int | None
    stderr_preview: str | None
    head_sha: str | None
    branch: str | None


_HOOK_EVENT_COLUMNS = (
    "ts, session_id, event_name, matcher, script, exit_code, duration_ms, "
    "stderr_preview, head_sha, branch"
)


def recent_hook_events(
    event_name: str | None = None,
    *,
    exit_code: int | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[HookEvent]:
    """Return recent hook fires, newest first, optionally filtered (ENH-2506)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = f"SELECT {_HOOK_EVENT_COLUMNS} FROM hook_events "
        clauses: list[str] = []
        params: list[Any] = []
        if event_name is not None:
            clauses.append("event_name = ?")
            params.append(event_name)
        if exit_code is not None:
            clauses.append("exit_code = ?")
            params.append(exit_code)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_hook_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, HookEvent) for row in rows]


def hook_failure_rate(
    event_name: str,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> float | None:
    """Return the fraction of *event_name* fires with a non-zero exit code, or None if no fires."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        sql = (
            "SELECT AVG(CASE WHEN exit_code != 0 THEN 1.0 ELSE 0.0 END) AS failure_rate, "
            "COUNT(*) AS n FROM hook_events WHERE event_name = ? AND exit_code IS NOT NULL"
        )
        params: list[Any] = [event_name]
        if since is not None:
            sql += " AND ts >= ?"
            params.append(since)
        row = conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: hook_failure_rate query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None or not row["n"]:
        return None
    return row["failure_rate"]


def hook_latency_p95(
    event_name: str,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> float | None:
    """Return the p95 ``duration_ms`` for *event_name* fires, or None if no fires (ENH-2506).

    SQLite has no built-in percentile aggregate, so durations are fetched and
    ranked in Python (nearest-rank method) — fine at the scale hook telemetry
    accumulates (thousands, not millions, of rows per project).
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        sql = "SELECT duration_ms FROM hook_events WHERE event_name = ? AND duration_ms IS NOT NULL"
        params: list[Any] = [event_name]
        if since is not None:
            sql += " AND ts >= ?"
            params.append(since)
        sql += " ORDER BY duration_ms ASC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: hook_latency_p95 query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if not rows:
        return None
    durations = [row["duration_ms"] for row in rows]
    idx = max(0, int(len(durations) * 0.95) - 1)
    return float(durations[min(idx, len(durations) - 1)])


# ---------------------------------------------------------------------------
# ll-harness / eval outcome telemetry (ENH-2741)
# ---------------------------------------------------------------------------


@dataclass
class HarnessEvent:
    """A ``harness_events`` row — one ll-harness / eval run outcome (ENH-2741)."""

    ts: str
    runner: str | None
    target: str | None
    exit_code: int | None
    semantic_verdict: str | None
    semantic_passed: int | None
    timed_out: int | None
    duration_ms: int | None
    head_sha: str | None
    branch: str | None
    parent_id: int | None
    semantic_prompt: str | None
    semantic_confidence: float | None
    semantic_reason: str | None
    semantic_evidence: str | None
    semantic_model: str | None


_HARNESS_EVENT_COLUMNS = (
    "ts, runner, target, exit_code, semantic_verdict, semantic_passed, timed_out, "
    "duration_ms, head_sha, branch, parent_id, semantic_prompt, semantic_confidence, "
    "semantic_reason, semantic_evidence, semantic_model"
)


def recent_harness_events(
    *,
    runner: str | None = None,
    target: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[HarnessEvent]:
    """Return recent ll-harness / eval outcomes, newest first, optionally filtered (ENH-2741)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = f"SELECT {_HARNESS_EVENT_COLUMNS} FROM harness_events "
        clauses: list[str] = []
        params: list[Any] = []
        if runner is not None:
            clauses.append("runner = ?")
            params.append(runner)
        if target is not None:
            clauses.append("target = ?")
            params.append(target)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_harness_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, HarnessEvent) for row in rows]


def harness_eval_pass_rate(
    target: str,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> float | None:
    """Return the semantic-verdict pass fraction for *target*, or None if no scored rows (ENH-2741).

    Only rows with a non-NULL ``semantic_passed`` (the ``check_semantic`` verdict path,
    not the plain ``exit_code``) count toward the rollup.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        sql = (
            "SELECT SUM(CASE WHEN semantic_passed = 1 THEN 1 ELSE 0 END) AS successes, "
            "COUNT(semantic_passed) AS scored "
            "FROM harness_events WHERE target = ?"
        )
        params: list[Any] = [target]
        if since is not None:
            sql += " AND ts >= ?"
            params.append(since)
        row = conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: harness_eval_pass_rate query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None or not row["scored"]:
        return None
    return row["successes"] / row["scored"]
