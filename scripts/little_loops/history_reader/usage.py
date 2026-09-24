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
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

from little_loops.history_reader._base import (
    DEFAULT_DB_PATH,
    _connect_readonly,
    _row_to_dataclass,
    logger,
)
from little_loops.history_reader.models import UsageEvent
from little_loops.token_provenance import ObservationGroup, group_rows

__all__ = [
    "agent_usage",
    "aggregate_usage",
    "cost_attribution",
    "mcp_failure_rate",
    "mcp_server_usage",
    "recent_tool_events",
    "recent_usage_events",
    "select_usage_observations",
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


_USAGE_TOKEN_COLUMNS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)

# Optional ``usage_events`` columns: pre-v54/v55 (and pre-channel) databases lack
# some of them, so the chokepoint selects ``NULL`` for any that are absent.
_OPTIONAL_USAGE_COLUMNS = (
    "state",
    "run_id",
    "invocation_id",
    "provider_vendor",
    "channel",
    "host",
    "host_basis",
    "provenance",
    "scope_kind",
    "observed_at",
    "observed_at_basis",
)


def select_usage_observations(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    require_run_id: bool = False,
) -> Iterator[sqlite3.Row]:
    """Stream every ``usage_events`` row -- the single token/cost selection point (ENH-3528).

    All token/cost aggregation reads go through here so a coverage selector
    (ENH-3543) can replace the selection policy in one place. For now every row
    is yielded (the unreconciled observation sum). Columns missing from older
    schemas are selected as ``NULL``. *since* is an ISO 8601 lower bound on
    ``ts``; *require_run_id* keeps only rows with a non-NULL ``run_id`` (no
    ``IN (...)`` list, which would hit SQLite's bound-parameter limit). Raises
    ``sqlite3.OperationalError`` when the table is absent. Rows must be
    consumed while *conn* is open.
    """
    present = {row[1] for row in conn.execute("PRAGMA table_info(usage_events)")}
    if not present:
        raise sqlite3.OperationalError("no such table: usage_events")
    optional = ", ".join(
        col if col in present else f"NULL AS {col}" for col in _OPTIONAL_USAGE_COLUMNS
    )
    sql = (
        "SELECT id, ts, session_id, model, input_tokens, output_tokens, "
        "cache_read_input_tokens, cache_creation_input_tokens, cost_usd, "
        f"{optional} FROM usage_events "  # noqa: S608 - column names are module constants
    )
    clauses: list[str] = []
    params: list[Any] = []
    if since is not None:
        clauses.append("ts >= ?")
        params.append(since)
    if require_run_id and "run_id" in present:
        clauses.append("run_id IS NOT NULL")
    elif require_run_id:
        return
    if clauses:
        sql += "WHERE " + " AND ".join(clauses) + " "
    sql += "ORDER BY id"
    cursor = conn.execute(sql, params)
    yield from cursor


def _provenance_fields(group: ObservationGroup) -> dict[str, Any]:
    """Coverage/provenance qualification shared by every rollup (ENH-3528)."""
    coverage = group.coverage()
    fields: dict[str, Any] = {
        "provenance": group.aggregate_provenance("input_tokens"),
        "coverage": coverage,
        "channel_subtotals": group.channel_subtotals(),
    }
    if coverage == "overlap_unresolved":
        fields["coverage_reason"] = (
            "live and transcript observations may cover the same work; unreconciled observation sum"
        )
    return fields


def _sort_desc(value: Any) -> tuple[bool, float]:
    """Sort key placing ``None`` last in a descending sort (SQLite NULL order)."""
    return (value is not None, value if value is not None else 0.0)


def _read_groups(
    db: Path | str, key: Any, *, since: str | None, name: str, require_run_id: bool = False
) -> dict[Any, ObservationGroup] | None:
    """Group chokepoint rows by ``key(row)``; ``None`` when the store is unreadable."""
    conn = _connect_readonly(Path(db))
    if conn is None:
        return None
    try:
        return group_rows(
            select_usage_observations(conn, since=since, require_run_id=require_run_id), key
        )
    except sqlite3.Error:
        logger.warning("history_reader: %s query failed", name, exc_info=True)
        return None
    finally:
        conn.close()


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

    ENH-3538: a token component (or ``cost_usd``) with any NULL contributor is
    unavailable — the flat field is ``None`` and the ``gen_ai.usage.*``
    attribute is omitted rather than exported as a partial subtotal. Each row
    also carries ``<column>_missing`` counts for the four token columns and
    ``cost_usd``.

    ENH-3528: rows are read through :func:`select_usage_observations` and
    grouped in Python; each dict also carries ``provenance``, ``coverage`` and
    per-channel subtotals (a combined live/transcript rollup is an unreconciled
    observation sum with ``coverage='overlap_unresolved'``).
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
    groups = _read_groups(db, lambda row: row[column], since=since, name="cost_attribution")
    if groups is None:
        return []
    otel_names = {
        "input_tokens": GEN_AI_USAGE_INPUT_TOKENS,
        "output_tokens": GEN_AI_USAGE_OUTPUT_TOKENS,
        "cache_read_input_tokens": GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
        "cache_creation_input_tokens": GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
    }
    ordered = sorted(
        groups.items(), key=lambda kv: _sort_desc(kv[1].subtotal("input_tokens")), reverse=True
    )
    result: list[dict] = []
    for key, group in ordered:
        entry: dict[str, Any] = {group_by: key}
        for token_col in _USAGE_TOKEN_COLUMNS:
            total = group.total(token_col)
            if total is not None:
                entry[otel_names[token_col]] = total
        entry["cost_usd"] = group.total("cost_usd")
        entry["invocations"] = group.rows
        for col in (*_USAGE_TOKEN_COLUMNS, "cost_usd"):
            entry[f"{col}_missing"] = group.missing(col)
        entry.update(_provenance_fields(group))
        result.append(entry)
    return result


_WASTED_RUN_PREDICATE = (
    "(lr.terminated_by IN ('error', 'no_route', 'max_steps', 'max_iterations_reached', "
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
    excluded rather than misattributed. See ``_WASTED_RUN_PREDICATE`` for the
    "wasted" definition.

    ENH-3528: the join happens in Python over
    :func:`select_usage_observations`. A row missing ``input_tokens`` or
    ``output_tokens`` has an unavailable token count, so ``tokens_total`` /
    ``tokens_wasted`` are ``None`` when any contributor is missing (with the
    shortfall in ``tokens_total_missing`` / ``tokens_wasted_missing``) and
    ``waste_pct`` is ``None`` when either operand is ``None`` or the
    denominator is zero. Each dict also carries ``provenance`` / ``coverage`` /
    ``channel_subtotals`` (see :func:`cost_attribution`).
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        runs = {
            row["run_id"]: (row["loop_name"], bool(row["wasted"]))
            for row in conn.execute(
                "SELECT lr.run_id AS run_id, lr.loop_name AS loop_name, "
                f"CASE WHEN {_WASTED_RUN_PREDICATE} THEN 1 ELSE 0 END AS wasted "
                "FROM loop_runs lr"
            )
        }
        per_loop: dict[Any, dict[str, Any]] = {}
        for row in select_usage_observations(conn, since=since, require_run_id=True):
            match = runs.get(row["run_id"])
            if match is None:
                continue
            loop_name, wasted = match
            slot = per_loop.setdefault(
                loop_name,
                {
                    "group": ObservationGroup(),
                    "runs": set(),
                    "wasted_runs": set(),
                    "total": 0,
                    "total_missing": 0,
                    "wasted": 0,
                    "wasted_missing": 0,
                },
            )
            slot["group"].add(row)
            slot["runs"].add(row["run_id"])
            known = row["input_tokens"] is not None and row["output_tokens"] is not None
            tokens = row["input_tokens"] + row["output_tokens"] if known else 0
            slot["total"] += tokens
            slot["total_missing"] += 0 if known else 1
            if wasted:
                slot["wasted_runs"].add(row["run_id"])
                slot["wasted"] += tokens
                slot["wasted_missing"] += 0 if known else 1
    except sqlite3.Error:
        logger.warning("history_reader: waste_attribution query failed", exc_info=True)
        return []
    finally:
        conn.close()
    result: list[dict] = []
    for loop_name, slot in per_loop.items():
        tokens_total = None if slot["total_missing"] else slot["total"]
        tokens_wasted = None if slot["wasted_missing"] else slot["wasted"]
        result.append(
            {
                "loop_name": loop_name,
                "tokens_total": tokens_total,
                "tokens_wasted": tokens_wasted,
                "tokens_total_missing": slot["total_missing"],
                "tokens_wasted_missing": slot["wasted_missing"],
                "waste_pct": (
                    tokens_wasted / tokens_total
                    if tokens_total and tokens_wasted is not None
                    else None
                ),
                "runs_total": len(slot["runs"]),
                "runs_wasted": len(slot["wasted_runs"]),
                **_provenance_fields(slot["group"]),
            }
        )
    result.sort(key=lambda r: _sort_desc(r["tokens_wasted"]), reverse=True)
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
    ``cache_creation_input_tokens``, and ``cost_usd``. A total with any NULL
    contributor (a missing token component, or an unpriced/incomplete row's
    ``NULL`` cost) is ``None`` — never a partial subtotal (ENH-3538) — with the
    contributor shortfall in ``<column>_missing``. *since* is an ISO
    8601 lower bound on ``ts``. Sorted by ``cost_usd`` descending. Rows are read
    through :func:`select_usage_observations` (ENH-3528) and each dict also
    carries ``provenance`` / ``coverage`` / ``channel_subtotals``. Grain is
    per-call — usage_events carries no FSM ``state``, so per-state rollups are
    not offered here (ENH-2461 Addendum 2).
    """
    key_col = "model" if group_by == "model" else "session_id"
    groups = _read_groups(db, lambda row: row[key_col], since=since, name="aggregate_usage")
    if groups is None:
        return []
    ordered = sorted(
        groups.items(), key=lambda kv: _sort_desc(kv[1].subtotal("cost_usd")), reverse=True
    )
    return [
        {
            group_by: key,
            "events": group.rows,
            **{col: group.total(col) for col in _USAGE_TOKEN_COLUMNS},
            "cost_usd": group.total("cost_usd"),
            **{f"{col}_missing": group.missing(col) for col in (*_USAGE_TOKEN_COLUMNS, "cost_usd")},
            **_provenance_fields(group),
        }
        for key, group in ordered
    ]
