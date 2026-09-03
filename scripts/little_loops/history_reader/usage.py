"""Tool-event and usage-event queries (ENH-2775 split from the former flat
``history_reader.py``).

Two adjacent, table-backed clusters grouped into one submodule: the
``tool_events`` cluster (``agent_usage``, ``recent_tool_events``,
``mcp_server_usage``, ``mcp_failure_rate``) and the ``usage_events`` cluster
(``cost_attribution``, ``waste_attribution``, ``recent_usage_events``,
``aggregate_usage``) — the former flat module had no comment boundary between
them despite each backing a different table.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Literal

from little_loops.history_reader._base import (
    DEFAULT_DB_PATH,
    _connect_readonly,
    _row_to_dataclass,
    logger,
)
from little_loops.history_reader.models import UsageEvent

__all__ = [
    "agent_usage",
    "aggregate_usage",
    "cost_attribution",
    "mcp_failure_rate",
    "mcp_server_usage",
    "recent_tool_events",
    "recent_usage_events",
    "waste_attribution",
]


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


_WASTED_RUN_PREDICATE = (
    "(lr.terminated_by IN ('error', 'max_steps', 'max_iterations_reached', "
    "'timeout', 'system_signal', 'interrupted') "
    "OR lr.failure_terminal = 1 "
    "OR (lr.failure_terminal IS NULL AND lr.terminated_by = 'terminal' "
    "AND lr.final_state != 'done'))"
)


def waste_attribution(
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Per-loop token spend vs. spend wasted on no-artifact runs (ENH-2722).

    Joins ``usage_events.run_id = loop_runs.run_id`` (an equi-join, exact
    since ENH-2723/2724 — no time-range join). ``usage_events`` rows with no
    matching ``loop_runs`` row (unbackfilled historical rows, or rows whose
    backfill timestamp matched zero/multiple overlapping run windows) are
    excluded by the inner join rather than misattributed. See
    ``_WASTED_RUN_PREDICATE`` for the "wasted" definition.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT lr.loop_name AS loop_name, "
            "SUM(COALESCE(ue.input_tokens, 0) + COALESCE(ue.output_tokens, 0)) AS tokens_total, "
            f"SUM(CASE WHEN {_WASTED_RUN_PREDICATE} THEN "
            "COALESCE(ue.input_tokens, 0) + COALESCE(ue.output_tokens, 0) ELSE 0 END) "
            "AS tokens_wasted, "
            "COUNT(DISTINCT lr.run_id) AS runs_total, "
            f"COUNT(DISTINCT CASE WHEN {_WASTED_RUN_PREDICATE} THEN lr.run_id END) AS runs_wasted "
            "FROM usage_events ue JOIN loop_runs lr ON ue.run_id = lr.run_id "
        )
        params: list[Any] = []
        if since is not None:
            sql += "WHERE ue.ts >= ? "
            params.append(since)
        sql += "GROUP BY lr.loop_name ORDER BY tokens_wasted DESC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: waste_attribution query failed", exc_info=True)
        return []
    finally:
        conn.close()
    result: list[dict] = []
    for row in rows:
        tokens_total = row["tokens_total"] or 0
        tokens_wasted = row["tokens_wasted"] or 0
        result.append(
            {
                "loop_name": row["loop_name"],
                "tokens_total": tokens_total,
                "tokens_wasted": tokens_wasted,
                "waste_pct": (tokens_wasted / tokens_total) if tokens_total else None,
                "runs_total": row["runs_total"] or 0,
                "runs_wasted": row["runs_wasted"] or 0,
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
