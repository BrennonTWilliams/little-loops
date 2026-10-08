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
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from little_loops.history_reader._base import (
    DEFAULT_DB_PATH,
    _connect_readonly,
    _row_to_dataclass,
    logger,
)
from little_loops.history_reader.models import UsageEvent
from little_loops.token_provenance import (
    ObservationGroup,
    group_rows,
    qualify_usage,
    row_channel,
    row_host_verified,
    valid_token_value,
)

__all__ = [
    "CoverageGroup",
    "CoverageSelection",
    "agent_usage",
    "aggregate_usage",
    "cost_attribution",
    "mcp_failure_rate",
    "mcp_server_usage",
    "recent_tool_events",
    "recent_usage_events",
    "select_usage_coverage",
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
    "identity_basis",
    "turn_id",
    "request_identity_basis",
)

# UsageEvent's trailing fields (ENH-3580) -- a narrower set than
# _OPTIONAL_USAGE_COLUMNS: excludes `state` (already unconditionally selected
# below) and `provider_vendor` (out of scope; owned by the ENH-3528 chokepoint).
_USAGE_EVENT_OPTIONAL_COLUMNS = (
    "channel",
    "host",
    "host_basis",
    "provenance",
    "scope_kind",
    "observed_at",
    "observed_at_basis",
    "invocation_id",
    "run_id",
)


@dataclass(frozen=True)
class CoverageGroup:
    """One internally reconciled coverage group and its report-window rows."""

    audit_rows: tuple[Mapping[str, Any], ...]
    selected_rows: tuple[Mapping[str, Any], ...]
    coverage: str
    reason: str | None
    channel_subtotals: dict[str, dict[str, Any]]


_ACQUISITION_CHANNELS = frozenset({"live", "transcript", "rollout"})


@dataclass(frozen=True)
class CoverageSelection:
    """Canonical eligibility and raw audit evidence from one coverage policy."""

    groups: tuple[CoverageGroup, ...]
    audit_rows: tuple[Mapping[str, Any], ...]
    selected_rows: tuple[Mapping[str, Any], ...]
    coverage: str
    reason: str | None


def _verified_usage_identity(row: Mapping[str, Any]) -> bool:
    """Require both a source-verified host and a producer-observed own thread."""
    if not row.get("session_id") or not row_host_verified(row):
        return False
    channel = row_channel(row)
    if channel == "live":
        return row.get("identity_basis") == "host_observed"
    if channel == "rollout":
        return row.get("identity_basis") == "host_observed"
    # Claude transcript replay predates the identity_basis column; its
    # session ID is supplied by the verified source handle (ENH-3656).
    return channel == "transcript"


def _has_verified_retained_ingestion(
    conn: sqlite3.Connection, *, host: str, session_id: str
) -> bool:
    """Whether *session_id* has any verified source-attributed committed replay.

    Admission is identity-only: a single ``usage_events`` row whose
    :func:`_verified_usage_identity` returns ``True`` proves historical
    ingestion for this host/session, independent of whether the
    original source spelling or resolved handle path is still tracked
    in ``raw_events`` (ENH-3746). Live-only, unverified legacy and
    cursor/hold-only evidence do not admit; logical-NULL
    ``row_channel`` reads as ``transcript`` and admits when its
    session_id matches and ``row_host_verified`` holds.

    Used by ``_compute_cache_rate_from_usage`` to admit retained
    Claude transcript and Codex rollout observations after raw
    pruning (BUG-3736 retention), restoring the rate that the
    raw-only check silently drops.
    """
    if not host or not session_id:
        return False
    present = {column[1] for column in conn.execute("PRAGMA table_info(usage_events)")}
    required = {"host", "session_id"}
    if not required.issubset(present):
        return False
    cursor = conn.execute(
        "SELECT host, session_id, channel, host_basis, identity_basis FROM usage_events "
        "WHERE host = ? AND session_id = ? LIMIT 1",
        (host, session_id),
    )
    row = cursor.fetchone()
    if row is None:
        return False
    columns = [column[0] for column in cursor.description]
    return _verified_usage_identity(dict(zip(columns, row, strict=True)))


def _has_ingested_raw(
    conn: sqlite3.Connection,
    source_path: str,
    resolved_source_path: str,
    host: str,
    session_id: str,
) -> bool:
    """Whether a current verified handle-path raw row exists for *session_id*.

    Returns True when ``raw_events`` carries a row whose ``host_basis`` is
    'handle' for either the bare or resolved source path. This is the
    legacy raw-only admission path retained alongside ENH-3746's
    verified-replay admission: a session with a fresh ``refresh_usage_source``
    ingest (raw path) but no qualified observations still admits here, then
    falls through to ``ingested_without_usage``. A session with only
    retained replay observations (raw pruned) admits via
    :func:`_has_verified_retained_ingestion` instead.
    """
    if not host or not session_id:
        return False
    present = {column[1] for column in conn.execute("PRAGMA table_info(raw_events)")}
    required = {"host", "session_id", "host_basis"}
    if not required.issubset(present):
        return False
    return (
        conn.execute(
            "SELECT 1 FROM raw_events WHERE source_path IN (?, ?) AND host = ? "
            "AND session_id = ? AND host_basis = 'handle' LIMIT 1",
            (source_path, resolved_source_path, host, session_id),
        ).fetchone()
        is not None
    )


def _coverage_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Keep verified host/thread pairs separate without exporting the key."""
    if _verified_usage_identity(row):
        return ("verified", row["host"], row["session_id"])
    if row.get("session_id"):
        return ("unverified", row["session_id"])
    return ("unidentified", row["id"])


def _classify_coverage(
    rows: Sequence[Mapping[str, Any]], *, ambiguous_cross_channel: bool
) -> tuple[str, str | None]:
    """Never infer a live-to-rollout join from counts, order, or timestamps."""
    channels = {row_channel(row) for row in rows}
    live = "live" in channels
    replay = any(channel != "live" for channel in channels)
    if ambiguous_cross_channel:
        return "overlap_unresolved", "unverified_cross_channel_identity"
    if live and replay:
        return "overlap_unresolved", "live_replay_join_unproven"
    if len(channels) > 1:
        return "overlap_unresolved", "cross_channel_join_unproven"
    if any(
        row_channel(row) == "live"
        and row.get("host") == "codex"
        and row.get("scope_kind") != "invocation"
        for row in rows
    ):
        return "unknown", "codex_live_scope_unknown"
    if any(
        row_channel(row) == "live"
        and row.get("host") == "codex"
        and not _verified_usage_identity(row)
        for row in rows
    ):
        return "unknown", "codex_live_identity_unverified"
    if any(
        row_channel(row) == "rollout"
        and row.get("host") == "codex"
        and (
            row.get("request_identity_basis") != "native_response"
            or not _verified_usage_identity(row)
            or not row.get("turn_id")
            or row.get("provenance") != "measured"
        )
        for row in rows
    ):
        return "unknown", "rollout_request_identity_unverified"
    return "non_overlapping", None


def select_usage_coverage(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    require_run_id: bool = False,
    host: str | None = None,
    session_id: str | None = None,
    channel: str | None = None,
) -> CoverageSelection:
    """Reconcile producer coverage before applying host/session or report-window filters.

    `audit_rows` retains every observation; `selected_rows` contains only
    canonical-eligible rows. No live/rollout counterpart is suppressed because
    Codex 0.158.0 exposes no native live-to-rollout request key (ENH-3655).
    Unresolved groups therefore have empty `selected_rows`, their full audit
    rows, channel subtotals, and a stable reason code. Report filters cannot
    turn a partial group into complete coverage. ``host``/``session_id`` narrow
    the returned rows only; unverified possible counterparts outside the scope
    still make the scoped coverage unresolved (BUG-3735).

    ``channel`` (``live``/``transcript``/``rollout``) is an *acquisition* scope,
    unlike host/session: rows whose logical channel (``row_channel``) differs are
    dropped before grouping and before ``ambiguous_cross_channel`` is computed, so
    excluded counterparts cannot change values, coverage or qualification
    (ENH-3748). ``None`` keeps the full population.
    """
    if channel is not None and channel not in _ACQUISITION_CHANNELS:
        raise ValueError(
            f"select_usage_coverage: channel must be one of {sorted(_ACQUISITION_CHANNELS)}, "
            f"got {channel!r}"
        )
    if session_id is not None and host is None:
        raise ValueError("select_usage_coverage: session_id requires host")
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
    if session_id is not None:
        if not {"host", "host_basis", "session_id", "channel", "identity_basis"}.issubset(present):
            return CoverageSelection((), (), (), "unknown", "no_verified_identity_columns")
    elif host is not None and "host" not in present:
        return CoverageSelection((), (), (), "unknown", "no_host_column")
    # Host/session select *output*, never the acquisition population: a possible
    # counterpart lacking a verified host/session must still taint coverage (BUG-3735).
    cursor = conn.execute(sql + "ORDER BY id")
    columns = [column[0] for column in cursor.description]
    rows = [dict(zip(columns, row, strict=True)) for row in cursor]
    if channel is not None:
        # row_channel has no SQL equivalent for legacy NULL rows, so scope in Python.
        rows = [row for row in rows if row_channel(row) == channel]
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_coverage_key(row), []).append(row)
    channels = {row_channel(row) for row in rows}
    ambiguous_cross_channel = (
        "live" in channels
        and any(channel != "live" for channel in channels)
        and any(not _verified_usage_identity(row) for row in rows)
    )

    def in_scope(row: Mapping[str, Any]) -> bool:
        if session_id is not None:
            return (
                row.get("host") == host
                and row.get("session_id") == session_id
                and _verified_usage_identity(row)
            )
        return host is None or row.get("host") == host

    groups: list[CoverageGroup] = []
    audit_rows: list[Mapping[str, Any]] = []
    selected_rows: list[Mapping[str, Any]] = []
    for members in grouped.values():
        coverage, reason = _classify_coverage(
            members, ambiguous_cross_channel=ambiguous_cross_channel
        )
        visible = [
            {**row, "_coverage": coverage, "_coverage_reason": reason}
            for row in members
            if in_scope(row)
            and (since is None or row["ts"] >= since)
            and (not require_run_id or row.get("run_id") is not None)
        ]
        if not visible:
            continue
        audit = tuple(visible)
        selected = audit if coverage == "non_overlapping" else ()
        audit_group = ObservationGroup()
        for row in audit:
            audit_group.add(row)
        groups.append(
            CoverageGroup(audit, selected, coverage, reason, audit_group.channel_subtotals())
        )
        audit_rows.extend(audit)
        selected_rows.extend(selected)
    audit_rows.sort(key=lambda row: row["id"])
    selected_rows.sort(key=lambda row: row["id"])
    statuses = {group.coverage for group in groups}
    coverage = (
        "overlap_unresolved"
        if "overlap_unresolved" in statuses
        else "unknown"
        if "unknown" in statuses or not statuses
        else "non_overlapping"
    )
    reasons = sorted(
        {group.reason for group in groups if group.coverage == coverage and group.reason}
    )
    reason = reasons[0] if reasons else None
    return CoverageSelection(
        tuple(groups), tuple(audit_rows), tuple(selected_rows), coverage, reason
    )


def select_usage_observations(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    require_run_id: bool = False,
    host: str | None = None,
    session_id: str | None = None,
    channel: str | None = None,
) -> Iterator[Mapping[str, Any]]:
    """Yield audit observations annotated by the shared coverage selector."""
    yield from select_usage_coverage(
        conn,
        since=since,
        require_run_id=require_run_id,
        host=host,
        session_id=session_id,
        channel=channel,
    ).audit_rows


def _provenance_fields(group: ObservationGroup) -> dict[str, Any]:
    """Coverage/provenance qualification shared by every rollup (ENH-3528)."""
    coverage = group.coverage()
    fields: dict[str, Any] = {
        "provenance": group.aggregate_provenance("input_tokens"),
        "coverage": coverage,
        "channel_subtotals": group.channel_subtotals(),
    }
    if coverage != "non_overlapping":
        fields["coverage_reason"] = group.coverage_reason() or "coverage_unverified"
    return fields


def _sort_desc(value: Any) -> tuple[bool, float]:
    """Sort key placing ``None`` last in a descending sort (SQLite NULL order)."""
    return (value is not None, value if value is not None else 0.0)


def _qualification_fields(group: ObservationGroup) -> dict[str, Any]:
    """Independent token/cost qualification reasons and invalid counts (ENH-3731).

    Tokens qualify with ``require_cost=False`` and cost separately with
    ``require_cost=True``, so a missing cost never blanks qualified tokens.
    """
    token = qualify_usage(group)
    cost = qualify_usage(group, require_cost=True)
    fields: dict[str, Any] = {
        "qualification_reason": token.reason,
        "cost_qualification_reason": cost.reason,
    }
    for counts in cost.component_counts:
        fields[f"{counts.column}_invalid"] = counts.invalid_count
    return fields


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

    ENH-3538/ENH-3731: the four token components qualify together — a group
    publishes them only when every contributing row is admitted (all four token
    columns valid) and has measured or estimated provenance; otherwise every flat
    field is ``None`` and every ``gen_ai.usage.*`` attribute is omitted. ``cost_usd``
    qualifies independently (every contributor needs a valid stored cost), so a
    missing cost never blanks qualified tokens. Each row carries
    ``<column>_missing`` / ``<column>_invalid`` counts, token
    ``qualification_reason`` and ``cost_qualification_reason``.

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
        groups.items(),
        key=lambda kv: _sort_desc(kv[1].audit_subtotal("input_tokens")),
        reverse=True,
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
        entry.update(_qualification_fields(group))
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

    ENH-3528/ENH-3731: the join happens in Python over
    :func:`select_usage_observations`. One per-loop qualification over the full
    joined population (all four token columns valid, measured or estimated
    provenance, resolved coverage) governs both ``tokens_total`` and
    ``tokens_wasted``; either is ``None`` when it fails, with the
    ``input_tokens``/``output_tokens`` pair shortfall in ``tokens_total_missing`` /
    ``tokens_wasted_missing`` (and ``*_invalid``) and the bounded
    ``qualification_reason``. ``waste_pct`` is ``None`` when the base figures are
    unavailable or the denominator is zero (``waste_pct_qualification_reason``). Each dict also carries
    ``provenance`` / ``coverage`` /
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
                    "total_invalid": 0,
                    "wasted": 0,
                    "wasted_missing": 0,
                    "wasted_invalid": 0,
                },
            )
            slot["group"].add(row)
            slot["runs"].add(row["run_id"])
            operands = (row["input_tokens"], row["output_tokens"])
            if any(value is None for value in operands):
                state = "missing"
            elif not all(valid_token_value(value) for value in operands):
                state = "invalid"
            else:
                state = "known"
            tokens = sum(operands) if state == "known" else 0
            slot["total"] += tokens
            if state != "known":
                slot[f"total_{state}"] += 1
            if wasted:
                slot["wasted_runs"].add(row["run_id"])
                slot["wasted"] += tokens
                if state != "known":
                    slot[f"wasted_{state}"] += 1
    except sqlite3.Error:
        logger.warning("history_reader: waste_attribution query failed", exc_info=True)
        return []
    finally:
        conn.close()
    result: list[dict] = []
    for loop_name, slot in per_loop.items():
        qualification = qualify_usage(slot["group"])
        tokens_total = slot["total"] if qualification.eligible else None
        tokens_wasted = slot["wasted"] if qualification.eligible else None
        ratio_reason = qualification.reason or ("zero_denominator" if not slot["total"] else None)
        result.append(
            {
                "loop_name": loop_name,
                "tokens_total": tokens_total,
                "tokens_wasted": tokens_wasted,
                "tokens_total_missing": slot["total_missing"],
                "tokens_wasted_missing": slot["wasted_missing"],
                "tokens_total_invalid": slot["total_invalid"],
                "tokens_wasted_invalid": slot["wasted_invalid"],
                "waste_pct": (tokens_wasted / tokens_total if ratio_reason is None else None),
                "runs_total": len(slot["runs"]),
                "runs_wasted": len(slot["wasted_runs"]),
                "qualification_reason": qualification.reason,
                "waste_pct_qualification_reason": ratio_reason,
                "rejected_contributors": qualification.rejected_contributors,
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

    ENH-3580: also populates ``UsageEvent``'s v54/v55 provenance fields.
    Columns missing from pre-v54/v55 schemas are selected as ``NULL``; a NULL
    stored ``provenance`` surfaces as ``"unknown"``, other missing fields
    surface as ``None``.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        present = {row[1] for row in conn.execute("PRAGMA table_info(usage_events)")}
        optional = ", ".join(
            (f"COALESCE({col}, 'unknown') AS {col}" if col == "provenance" else col)
            if col in present
            else (f"'unknown' AS {col}" if col == "provenance" else f"NULL AS {col}")
            for col in _USAGE_EVENT_OPTIONAL_COLUMNS
        )
        sql = (
            "SELECT ts, session_id, model, state, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens, cost_usd, "
            f"{optional} FROM usage_events "  # noqa: S608 - column names are module constants
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
        groups.items(),
        key=lambda kv: _sort_desc(kv[1].audit_subtotal("cost_usd")),
        reverse=True,
    )
    return [
        {
            group_by: key,
            "events": group.rows,
            **{col: group.total(col) for col in _USAGE_TOKEN_COLUMNS},
            "cost_usd": group.total("cost_usd"),
            **{f"{col}_missing": group.missing(col) for col in (*_USAGE_TOKEN_COLUMNS, "cost_usd")},
            **_qualification_fields(group),
            **_provenance_fields(group),
        }
        for key, group in ordered
    ]
