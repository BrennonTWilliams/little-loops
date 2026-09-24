"""ll-ctx-stats: Context-window analytics for the current project (FEAT-1624).

Reads per-tool byte metrics that the ``post_tool_use`` hook persists into
``.ll/history.db`` (FEAT-1623) and renders a compact summary of how much
data was processed by tools vs. how much actually entered the conversation
context. Falls back to ``.ll/ll-context-state.json`` (token estimates) when
the SQLite store is absent so first-time users still get useful output.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from little_loops.cli.logs import _aggregate_skill_stats
from little_loops.cli.output import (
    configure_output,
    format_relative_time,
    terminal_width,
    use_color_enabled,
)
from little_loops.cli_args import add_host_arg
from little_loops.config.features import LearningTestsConfig
from little_loops.issue_parser import slugify
from little_loops.learning_tests import list_records
from little_loops.learning_tests.gate import is_record_stale
from little_loops.learning_tests.import_scan import get_imported_packages
from little_loops.logger import Logger
from little_loops.session_store import (
    DEFAULT_DB_PATH,
    HistoryError,
    SessionHandle,
    cli_event_context,
    connect_readonly,
    detect_sessions,
    iter_events,
    resolve_history_db,
    translate_sqlite_errors,
)
from little_loops.subprocess_utils import normalize_codex_input
from little_loops.token_provenance import (
    COST_COLUMN,
    TOKEN_COLUMNS,
    UNKNOWN_MODEL_BUCKET,
    ObservationGroup,
    counted_entry,
    estimated_entry,
    footnotes,
    format_figure,
    json_pointer,
    same_metadata,
    suffix_for,
)
from little_loops.user_messages import _resolve_host

DEFAULT_DB_RELPATH = Path(".ll") / "history.db"
DEFAULT_STATE_RELPATH = Path(".ll") / "ll-context-state.json"


def _build_parser() -> argparse.ArgumentParser:
    """Build the ll-ctx-stats argument parser (exposed for testing)."""
    parser = argparse.ArgumentParser(
        prog="ll-ctx-stats",
        description=(
            "Show context-window savings metrics and skill-health signals for the current project. "
            "Reads per-tool byte metrics from .ll/history.db and renders how much data was processed "
            "by tools vs. how much entered conversation context. Also surfaces per-skill invocation "
            "frequency and correction rate from the same database."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                 # Print savings summary and skill-health section
  %(prog)s --db PATH       # Use a non-default session database
  %(prog)s --json          # Output as JSON (includes skill_health array)

Exit codes:
  0 - Report rendered (data present or fallback used)
  1 - No data found in either the SQLite store or the fallback file
""",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to the session database (default: .ll/history.db)",
    )
    parser.add_argument(
        "-j",
        "--json",
        dest="json_mode",
        action="store_true",
        help="Output as JSON",
    )
    add_host_arg(parser)
    return parser


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse argv into a Namespace (exposed for testing)."""
    return _build_parser().parse_args(argv)


def _format_bytes(value: int) -> str:
    """Render *value* bytes as a short ``KB``/``MB`` string."""
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"


def _time_gained(seconds: float) -> str:
    """Render *seconds* as a positive-tense ``+Xm`` string.

    ``format_relative_time`` appends ``" ago"`` (it is designed for past-tense
    durations); strip that suffix here so the line reads as savings rather
    than elapsed time. The shared helper is intentionally left unchanged
    (see Implementation Constraints #4 on FEAT-1624).
    """
    label = format_relative_time(seconds)
    if label.endswith(" ago"):
        label = label[: -len(" ago")]
    return f"+{label}"


def _progress_bar(value: int, ceiling: int, width: int) -> str:
    """Return a ``|####  |`` bar of ``width`` columns scaled to ``value/ceiling``."""
    if width < 3:
        width = 3
    inner = width - 2
    if ceiling <= 0:
        filled = 0
    else:
        filled = max(0, min(inner, round(inner * value / ceiling)))
    return "|" + "#" * filled + " " * (inner - filled) + "|"


def _aggregate_tool_events(db_path: Path) -> dict[str, Any] | None:
    """Sum per-tool byte metrics from ``tool_events``.

    Backfilled rows have ``NULL`` byte columns (see Implementation Constraints
    #1 on FEAT-1624). Per-tool aggregation filters those rows out so historic
    JSONL noise does not skew the summary; cache totals likewise.

    Returns ``None`` when the database file is missing. Returns an empty
    summary (all zeros) when the database exists but has no analytic rows.
    """
    if not db_path.exists():
        return None
    try:
        conn = connect_readonly(db_path)
    except HistoryError:
        return None
    try:
        try:
            with translate_sqlite_errors():
                rows = conn.execute(
                    "SELECT tool_name, bytes_in, bytes_out, cache_hit "
                    "FROM tool_events WHERE bytes_in IS NOT NULL OR bytes_out IS NOT NULL"
                ).fetchall()
        except HistoryError:
            return None
    finally:
        conn.close()

    per_tool: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "bytes": 0})
    total_in = 0
    total_out = 0
    cache_hits = 0
    cache_bytes = 0
    for row in rows:
        tool = (row["tool_name"] or "unknown").lower()
        bin_ = int(row["bytes_in"] or 0)
        bout = int(row["bytes_out"] or 0)
        per_tool[tool]["calls"] += 1
        per_tool[tool]["bytes"] += bout
        total_in += bin_
        total_out += bout
        if row["cache_hit"]:
            cache_hits += 1
            cache_bytes += bout

    return {
        "total_in": total_in,
        "total_out": total_out,
        "cache_hits": cache_hits,
        "cache_bytes": cache_bytes,
        "per_tool": dict(per_tool),
    }


def _aggregate_mcp_health(db_path: Path) -> list[dict[str, Any]] | None:
    """Per-MCP-server call count / success rate / avg latency (ENH-2511).

    Returns ``None`` when the database file is missing (mirrors
    ``_aggregate_tool_events``'s absent-DB contract); an empty list when the
    DB exists but has no MCP rows yet.
    """
    if not db_path.exists():
        return None
    from little_loops.history_reader import mcp_server_usage

    return mcp_server_usage(db=db_path)


def _aggregate_waste(db_path: Path) -> list[dict[str, Any]] | None:
    """Per-loop tokens-wasted rollup (ENH-2722).

    Returns ``None`` when the database file is missing (mirrors
    ``_aggregate_mcp_health``'s absent-DB contract); an empty list when the
    DB exists but has no joinable ``usage_events``/``loop_runs`` rows yet.
    """
    if not db_path.exists():
        return None
    from little_loops.history_reader import waste_attribution

    return waste_attribution(db=db_path)


def _aggregate_usage_events(db_path: Path) -> dict[str, Any] | None:
    """Aggregate real LLM token usage from ``usage_events``, by model (ENH-2461).

    Reads the per-call ``usage_events`` rows through
    :func:`~little_loops.history_reader.usage.select_usage_observations` (the
    single token/cost selection point, ENH-3528) — populated by
    ``session_store._backfill_usage_events`` (historical, transcript-derived)
    and by the live per-invocation writer — and rolls them up into overall
    totals plus a per-model breakdown. Returns a dict shaped like::

        {
            "totals": {"input_tokens": ..., "output_tokens": ...,
                       "cache_read_input_tokens": ...,
                       "cache_creation_input_tokens": ..., "cost_usd": ...},
            "per_model": {"model_name": {"events": ..., <same token/cost keys>}},
            "provenance": {"<RFC 6901 pointer>": {<token_provenance entry>}},
        }

    A component is the sum of its *known* contributors and is ``None`` when no
    observation supplied it (missing is unavailable, never a measured zero);
    ``provenance`` entries carry the known/missing counts, so a partial
    subtotal is labeled ``availability='partial'``. Rows with a NULL model
    share the reserved ``"(unknown model)"`` bucket, distinct from a model
    literally named ``"unknown"``. ``provenance`` is keyed by pointers relative
    to the ``--json`` document root (``/usage_by_model/...``).

    Returns ``None`` when the DB file is missing or the ``usage_events`` table
    is absent (legacy DB predating the v20 migration).
    """
    if not db_path.exists():
        return None
    from little_loops.history_reader.usage import select_usage_observations

    try:
        conn = connect_readonly(db_path)
    except HistoryError:
        return None
    try:
        try:
            with translate_sqlite_errors():
                total = ObservationGroup()
                by_model: dict[str, ObservationGroup] = {}
                for row in select_usage_observations(conn):
                    total.add(row)
                    model = str(row["model"]) if row["model"] is not None else UNKNOWN_MODEL_BUCKET
                    by_model.setdefault(model, ObservationGroup()).add(row)
        except HistoryError:
            return None
    finally:
        conn.close()

    columns = (*TOKEN_COLUMNS, COST_COLUMN)
    provenance: dict[str, dict[str, Any]] = {}
    totals = {col: total.subtotal(col) for col in columns}
    for col in columns:
        provenance[json_pointer("usage_by_model", "totals", col)] = total.entry(col)
    per_model: dict[str, dict[str, Any]] = {}
    for model, group in by_model.items():
        per_model[model] = {"events": group.rows, **{c: group.subtotal(c) for c in columns}}
        for col in columns:
            provenance[json_pointer("usage_by_model", "per_model", model, col)] = group.entry(col)
    return {"totals": totals, "per_model": per_model, "provenance": provenance}


def _aggregate_context_pressure(db_path: Path) -> dict[str, Any] | None:
    """Aggregate context-pressure samples across all sessions (ENH-2507).

    Returns ``None`` when the database file is missing or the
    ``context_pressure_events`` table is absent (legacy DB predating the v34
    migration). Returns a zeroed summary when the table exists but has no rows.
    """
    if not db_path.exists():
        return None
    try:
        conn = connect_readonly(db_path)
    except HistoryError:
        return None
    try:
        try:
            with translate_sqlite_errors():
                rows = conn.execute(
                    "SELECT used_pct, threshold_crossed, crossed_level FROM context_pressure_events"
                ).fetchall()
        except HistoryError:
            return None
    finally:
        conn.close()

    if not rows:
        return {"samples": 0, "peak_pct": None, "avg_pct": None, "crossings": {}}

    pct_values = [row["used_pct"] for row in rows if row["used_pct"] is not None]
    crossings: dict[str, int] = defaultdict(int)
    for row in rows:
        if row["threshold_crossed"] and row["crossed_level"]:
            crossings[str(row["crossed_level"])] += 1

    return {
        "samples": len(rows),
        "peak_pct": max(pct_values) if pct_values else None,
        "avg_pct": round(sum(pct_values) / len(pct_values), 1) if pct_values else None,
        "crossings": dict(crossings),
    }


def _load_fallback_state(path: Path) -> dict[str, Any] | None:
    """Return ``.ll/ll-context-state.json`` parsed, or ``None`` if absent/invalid."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _codex_cache_usage(handle: SessionHandle) -> dict[str, Any] | None:
    """Compute cache hit rate from a Codex rollout's ``token_count`` events.

    ``last_token_usage`` (not the cumulative ``total_token_usage``, which
    resets across a mid-session compaction) is normalized per observation via
    :func:`~little_loops.subprocess_utils.normalize_codex_input` (Codex input is
    inclusive of cached/cache-write tokens) and only consistent splits are
    summed. Incomplete, malformed, or over-cached observations are excluded from
    the rate and counted in ``inconsistent_events`` rather than clamped; a
    mapping ``info`` without ``last_token_usage`` and ``info: null`` records
    are not observations. With no consistent observation the rate and token
    totals are ``None``. Always returns a dict for a Codex session (BUG-3531).
    """
    cache_read = cache_write = uncached = 0
    consistent = inconsistent = 0

    for event in iter_events(handle):
        if event.type != "event_msg" or event.payload.get("type") != "token_count":
            continue
        info = event.payload.get("info")
        if info is None:
            continue
        if not isinstance(info, dict):
            inconsistent += 1
            continue
        if "last_token_usage" not in info:
            continue
        split = normalize_codex_input(info["last_token_usage"])
        if (
            not split.consistent
            or split.uncached_input is None
            or split.cache_read is None
            or split.cache_write is None
        ):
            inconsistent += 1
            continue
        consistent += 1
        cache_read += split.cache_read
        cache_write += split.cache_write
        uncached += split.uncached_input

    counts = {
        name: {"known": consistent, "missing": inconsistent}
        for name in ("cache_read", "cache_write", "uncached", "hit_rate_pct")
    }
    result: dict[str, Any] = {
        "cache_read": None,
        "cache_write": None,
        "uncached": None,
        "hit_rate_pct": None,
        "host": handle.host,
        "session_id": handle.session_id,
        "provenance": "measured",
        "counts": counts,
        "consistent_events": consistent,
        "inconsistent_events": inconsistent,
    }
    if consistent:
        total = cache_read + cache_write + uncached
        result.update(cache_read=cache_read, cache_write=cache_write, uncached=uncached)
        result["hit_rate_pct"] = round(cache_read / total * 100) if total else None
    return result


def _compute_cache_rate_from_jsonl(cwd: Path, host: str | None) -> dict[str, Any] | None:
    """Compute session-aggregate cache hit rate from the most recent session.

    Picks the newest non-agent session for *host* (or, when ``host`` is
    ``None``, the newest across every registered host) via
    :func:`detect_sessions`. Codex sessions are read through
    :func:`_codex_cache_usage` (``token_count`` events via ``iter_events``);
    every other host keeps the raw per-line reader over the transcript,
    summing ``cache_read_input_tokens``, ``cache_creation_input_tokens``, and
    ``input_tokens`` across all unique assistant entries (deduplicated by
    UUID to avoid double-counting). qwen/gemini/omp real cache rates stay
    unreachable this way — their normalizers strip ``message.usage`` — a
    native usage reader for them is a follow-up, not this function's job.

    Formula: hit_rate = cache_read / (cache_read + cache_write + uncached) * 100

    ENH-3528: this is a single-session transcript read (not ``usage_events``).
    An absent or ``null`` usage component is *missing*, never a measured zero:
    each component sums its known values and is ``None`` when none supplied it,
    while the hit rate uses only records that carry all three components (the
    common eligible set; excluded records are counted in
    ``counts['hit_rate_pct']['missing']``). A usage mapping with none of the
    three keys is not an observation. The result carries ``provenance``
    (``measured`` for Codex, ``unknown`` for other hosts until ENH-3546),
    ``session_id`` and per-component ``counts``.
    """
    handles = detect_sessions(cwd, host, include_agents=False, limit=1)
    if not handles:
        return None
    latest = handles[0]

    if latest.host == "codex":
        return _codex_cache_usage(latest)

    fields = (
        ("cache_read", "cache_read_input_tokens"),
        ("cache_write", "cache_creation_input_tokens"),
        ("uncached", "input_tokens"),
    )
    sums = {name: 0 for name, _ in fields}
    known = {name: 0 for name, _ in fields}
    missing = {name: 0 for name, _ in fields}
    eligible = {name: 0 for name, _ in fields}
    eligible_events = excluded_events = 0
    seen_uuids: set[str] = set()

    try:
        with open(latest.path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict) or record.get("type") != "assistant":
                    continue
                uuid = record.get("uuid")
                if uuid:
                    if uuid in seen_uuids:
                        continue
                    seen_uuids.add(uuid)
                message = record.get("message")
                usage = message.get("usage") if isinstance(message, dict) else None
                # A usage mapping with none of the three keys is not an observation.
                if not isinstance(usage, dict) or not any(key in usage for _, key in fields):
                    continue
                values: dict[str, int | None] = {}
                for name, key in fields:
                    values[name] = _known_int(usage.get(key))
                for name, value in values.items():
                    if value is None:
                        missing[name] += 1
                    else:
                        known[name] += 1
                        sums[name] += value
                if all(v is not None for v in values.values()):
                    eligible_events += 1
                    for name, value in values.items():
                        eligible[name] += value or 0
                else:
                    excluded_events += 1
    except OSError:
        return None

    if not eligible_events and not excluded_events:
        return None
    total = sum(eligible.values())
    if not any(sums.values()) and not any(missing.values()):
        return None

    counts = {name: {"known": known[name], "missing": missing[name]} for name in sums}
    counts["hit_rate_pct"] = {"known": eligible_events, "missing": excluded_events}
    return {
        **{name: (sums[name] if known[name] else None) for name in sums},
        "hit_rate_pct": round(eligible["cache_read"] / total * 100) if total else None,
        "host": latest.host,
        "session_id": latest.session_id,
        "provenance": "unknown",
        "counts": counts,
    }


def _known_int(value: Any) -> int | None:
    """Coerce a transcript usage component to ``int``; absent/null/malformed → ``None``."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_CACHE_SCOPE_REASON = "single-session transcript read (newest session only, not the whole history)"


def _cache_rate_provenance(cache_rate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Pointer → entry for the single-session transcript cache figures (ENH-3528)."""
    counts = cache_rate.get("counts") or {}
    provenance = cache_rate.get("provenance") or "unknown"
    host = cache_rate.get("host")
    fields = (
        ("cache_read_tokens", "cache_read", "cache_read_input_tokens"),
        ("cache_write_tokens", "cache_write", "cache_creation_input_tokens"),
        ("uncached_tokens", "uncached", "input_tokens"),
        ("cache_hit_rate_pct", "hit_rate_pct", "cache_hit_rate_pct"),
    )
    entries: dict[str, dict[str, Any]] = {}
    for json_key, src_key, metric in fields:
        default_known = 1 if cache_rate.get(src_key) is not None else 0
        count = counts.get(src_key) or {"known": default_known, "missing": 0}
        entries[json_pointer(json_key)] = counted_entry(
            metric,
            provenance=provenance,
            known=int(count["known"]),
            missing=int(count["missing"]),
            scope_kind="session",
            hosts=[host] if host else None,
            channels=["transcript_file"],
            session_id=cache_rate.get("session_id"),
            reason=_CACHE_SCOPE_REASON,
        )
    return entries


def _waste_provenance(waste: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Pointer → entry for each loop's token totals and waste ratio."""
    entries: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(waste):
        subtotals = row.get("channel_subtotals") or {}
        events = sum(int(sub.get("events", 0)) for sub in subtotals.values())
        reason = row.get("coverage_reason")
        base: dict[str, Any] = {
            "provenance": row.get("provenance") or "unknown",
            "coverage": row.get("coverage") or "unknown",
            "channels": sorted(subtotals) or None,
            "reason": reason,
        }
        for key, missing_key in (
            ("tokens_total", "tokens_total_missing"),
            ("tokens_wasted", "tokens_wasted_missing"),
        ):
            missing = int(row.get(missing_key) or 0)
            entries[json_pointer("waste", str(index), key)] = counted_entry(
                key, known=max(events - missing, 0), missing=missing, **base
            )
        known = events if row.get("waste_pct") is not None else 0
        entries[json_pointer("waste", str(index), "waste_pct")] = counted_entry(
            "waste_pct", known=known, missing=events - known, **base
        )
    return entries


def _pressure_provenance(pressure: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Pointer → entry for context-pressure percentages (always ``estimated``)."""
    return {
        json_pointer("context_pressure", key): estimated_entry(
            "context_pressure_used_pct",
            scope_kind="context",
            available=pressure.get(key) is not None,
        )
        for key in ("peak_pct", "avg_pct")
    }


def _fallback_provenance(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Pointer → entry for the context-state fallback estimates."""
    entries = {
        json_pointer("estimated_tokens"): estimated_entry(
            "estimated_tokens",
            scope_kind="context",
            available=state.get("estimated_tokens") is not None,
        )
    }
    breakdown = state.get("breakdown")
    if isinstance(breakdown, dict):
        for tool in breakdown:
            entries[json_pointer("breakdown", str(tool))] = estimated_entry(
                "estimated_tokens", scope_kind="context"
            )
    return entries


def _render_provenance_group(
    header: str, figures: list[tuple[str, Any, dict[str, Any]]]
) -> tuple[str, list[str]]:
    """Apply the group-header rule to *figures* of ``(label, value, entry)``.

    Returns ``(header_line, figure_texts)``: one suffix on the header when every
    figure's metadata matches, otherwise per-figure suffixes and a bare header.
    """
    uniform = same_metadata(entry for _, _, entry in figures)
    if uniform and figures:
        # Unavailable values still render "—" but the shared suffix stays the group's.
        header_line = f"{header} {suffix_for(figures[0][2])}"
        return header_line, [format_figure(v, e, suffix=False) for _, v, e in figures]
    return header, [format_figure(v, e) for _, v, e in figures]


def _render(
    summary: dict[str, Any],
    logger: Logger,
    skill_stats: dict[str, dict[str, int]] | None = None,
    cache_rate: dict[str, Any] | None = None,
    lt_stats: dict[str, Any] | None = None,
    mcp_health: list[dict[str, Any]] | None = None,
    waste: list[dict[str, Any]] | None = None,
    pressure: dict[str, Any] | None = None,
) -> None:
    """Print the savings report for an aggregated SQLite ``summary`` dict."""
    total_processed = int(summary["total_in"]) + int(summary["total_out"])
    in_context = max(0, int(summary["total_out"]) - int(summary["cache_bytes"]))
    saved = max(0, total_processed - in_context)
    reduction = round(100 * saved / total_processed) if total_processed > 0 else 0

    width = terminal_width()
    bar_width = max(20, min(50, width - 30))
    print(
        f"Without savings:  {_progress_bar(total_processed, total_processed, bar_width)} "
        f"{_format_bytes(total_processed)} in conversation"
    )
    print(
        f"With savings:     {_progress_bar(in_context, total_processed, bar_width)} "
        f"{_format_bytes(in_context)} in conversation"
    )
    print()
    print(
        f"{_format_bytes(saved)} processed by tools, never entered conversation. "
        f"({reduction}% reduction)"
    )
    # Heuristic: ~100 bytes/sec of saved context ≈ time the user would have spent
    # waiting for compaction or re-reading. The estimate is rough by design;
    # FEAT-1625 may revisit once real telemetry is collected.
    time_seconds = saved / 100.0 if saved > 0 else 0.0
    print(f"{_time_gained(time_seconds)} session time gained.")
    print()

    per_tool: dict[str, dict[str, int]] = summary["per_tool"]
    if per_tool:
        ranked = sorted(per_tool.items(), key=lambda kv: kv[1]["bytes"], reverse=True)
        for tool, stats in ranked:
            print(
                f"  {tool:<13} {stats['calls']:>3} calls   {_format_bytes(stats['bytes']):>10} used"
            )
        print()

    cache_hits = int(summary["cache_hits"])
    cache_bytes = int(summary["cache_bytes"])
    if cache_hits:
        print(f"Cache: {cache_hits} hits | {_format_bytes(cache_bytes)} saved")
    else:
        logger.info("Cache: no hits recorded in this session")

    if cache_rate is not None:
        rate_host = cache_rate.get("host")
        entries = _cache_rate_provenance(cache_rate)
        rate_entry = entries[json_pointer("cache_hit_rate_pct")]
        good = cache_rate.get("consistent_events")
        bad = cache_rate.get("inconsistent_events")
        counts = cache_rate.get("counts") or {}
        excluded = int((counts.get("hit_rate_pct") or {}).get("missing") or 0)
        if cache_rate["cache_read"] is None:
            if good == 0 and not bad:
                print(f"Cache hit rate: no usage observed {suffix_for(rate_entry)}")
            else:
                print(
                    f"Cache hit rate: unavailable ({bad or excluded} observation(s) excluded as "
                    f"inconsistent) {suffix_for(rate_entry)}"
                )
        else:
            cr = cache_rate["cache_read"]
            cw = cache_rate["cache_write"]
            u = cache_rate["uncached"]
            pct = cache_rate["hit_rate_pct"]
            shown = f"{pct}%" if pct is not None else "n/a (zero usage)"
            figures = [
                ("rate", shown, rate_entry),
                ("cache_read", cr, entries[json_pointer("cache_read_tokens")]),
                ("cache_write", cw, entries[json_pointer("cache_write_tokens")]),
                ("uncached", u, entries[json_pointer("uncached_tokens")]),
            ]
            if same_metadata(entry for _, _, entry in figures):
                print(
                    f"Cache hit rate: {shown}  "
                    f"(cache_read={_fmt_count(cr)} | cache_write={_fmt_count(cw)} | "
                    f"uncached={_fmt_count(u)}) {suffix_for(rate_entry)}"
                )
            else:
                parts = [
                    f"{label}={format_figure(value, entry)}" for label, value, entry in figures[1:]
                ]
                print(f"Cache hit rate: {shown} {suffix_for(rate_entry)}  ({' | '.join(parts)})")
            if bad:
                print(f"  based on {good} accepted observation(s); {bad} excluded as inconsistent")
            elif excluded:
                print(
                    f"  based on {(counts['hit_rate_pct'] or {}).get('known')} eligible "
                    f"record(s); {excluded} excluded (missing usage component)"
                )
        host_note = f"; host: {rate_host}" if rate_host else ""
        print(f"* {_CACHE_SCOPE_REASON}{host_note}")

    if skill_stats:
        print()
        print("Skill health:")
        ranked_skills = sorted(
            skill_stats.items(), key=lambda kv: kv[1]["invocations"], reverse=True
        )
        for skill, counts in ranked_skills:
            inv = counts["invocations"]
            corr = counts["corrections"]
            rate = round(100 * corr / inv) if inv > 0 else 0
            print(f"  {skill:<22} {inv:>3} invocations   {corr:>2} corrections ({rate}%)")
    elif skill_stats is not None:
        logger.info("No skill events recorded yet.")

    if mcp_health:
        print()
        print("MCP server health:")
        for row in mcp_health:
            success_rate = (
                f"{row['success_rate']:.0%}" if row["success_rate"] is not None else "n/a"
            )
            avg_latency = (
                f"{row['avg_latency_ms']:.0f}ms" if row["avg_latency_ms"] is not None else "n/a"
            )
            print(
                f"  {row['mcp_server']:<22} {row['invocations']:>3} calls   "
                f"success_rate={success_rate} avg_latency={avg_latency}"
            )

    if waste:
        print()
        entries = _waste_provenance(waste)
        all_entries = list(entries.values())
        uniform = same_metadata(all_entries)
        header = "Waste (runs ending without an accepted artifact):"
        print(f"{header} {suffix_for(all_entries[0])}" if uniform else header)
        for index, row in enumerate(waste):
            pct = f"{row['waste_pct']:.0%}" if row["waste_pct"] is not None else "n/a"
            wasted = format_figure(
                row["tokens_wasted"],
                entries[json_pointer("waste", str(index), "tokens_wasted")],
                suffix=not uniform,
            )
            total = format_figure(
                row["tokens_total"],
                entries[json_pointer("waste", str(index), "tokens_total")],
                suffix=not uniform,
            )
            print(
                f"  {row['loop_name']:<22} {row['runs_wasted']:>3}/{row['runs_total']:<3} runs wasted   "
                f"waste={pct} ({wasted}/{total} tokens)"
            )
        for note in footnotes(all_entries):
            print(note)

    if pressure and pressure["samples"]:
        print()
        print(
            "Context pressure curve: "
            f"{suffix_for(estimated_entry('context_pressure_used_pct', scope_kind='context'))}"
        )
        print(
            f"  {pressure['samples']} samples   "
            f"peak={pressure['peak_pct']:.0f}%   avg={pressure['avg_pct']:.0f}%"
        )
        if pressure["crossings"]:
            crossing_str = ", ".join(
                f"{level}%×{count}"
                for level, count in sorted(pressure["crossings"].items(), key=lambda kv: int(kv[0]))
            )
            print(f"  Crossings: {crossing_str}")

    if lt_stats is not None:
        _render_learning_tests_section(lt_stats)


def _fmt_count(value: Any) -> str:
    """Thousands-grouped count; unavailable renders ``—``, never ``0``."""
    return "—" if value is None else f"{int(value):,}"


def _render_fallback(state: dict[str, Any], logger: Logger) -> None:
    """Render the ``.ll/ll-context-state.json`` fallback (token estimates).

    Every figure is a context-state estimate, so the group is labeled
    ``[estimated]`` (ENH-3528); an absent estimate renders ``—``, not ``0``.
    """
    raw_estimate = state.get("estimated_tokens")
    tool_calls = int(state.get("tool_calls") or 0)
    breakdown = state.get("breakdown") or {}
    entries = _fallback_provenance(state)

    logger.info(
        "SQLite session store not found — falling back to .ll/ll-context-state.json "
        "(enable analytics (analytics.enabled: true) and ensure analytics.capture.file_events is not disabled)."
    )
    print()
    print(
        "Estimated tokens in context: "
        f"{format_figure(raw_estimate, entries[json_pointer('estimated_tokens')])}"
    )
    print(f"Tool calls this session:     {tool_calls}")
    if isinstance(breakdown, dict) and breakdown:
        print()
        tool_entries = [entries[json_pointer("breakdown", str(t))] for t in breakdown]
        header = "Per-tool token estimates:"
        uniform = same_metadata(tool_entries)
        print(f"{header} {suffix_for(tool_entries[0])}" if uniform else header)
        for tool, tokens in sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True):
            entry = entries[json_pointer("breakdown", str(tool))]
            print(
                f"  {str(tool):<20} "
                f"{format_figure(int(tokens), entry, suffix=not uniform):>8} tokens"
            )


def _token_provenance(
    summary: dict[str, Any] | None,
    state: dict[str, Any] | None,
    cache_rate: dict[str, Any] | None,
    usage_events: dict[str, Any] | None,
    waste: list[dict[str, Any]] | None,
    pressure: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Assemble the top-level ``token_provenance`` map (RFC 6901 pointer keys)."""
    entries: dict[str, dict[str, Any]] = {}
    if summary is not None:
        if cache_rate:
            entries.update(_cache_rate_provenance(cache_rate))
        if usage_events:
            entries.update(usage_events.get("provenance") or {})
        if waste:
            entries.update(_waste_provenance(waste))
    elif state is not None:
        entries.update(_fallback_provenance(state))
    if pressure and pressure.get("samples"):
        entries.update(_pressure_provenance(pressure))
    return entries


def _print_json(
    summary: dict[str, Any] | None,
    state: dict[str, Any] | None,
    skill_stats: dict[str, dict[str, int]] | None = None,
    cache_rate: dict[str, Any] | None = None,
    lt_stats: dict[str, Any] | None = None,
    usage_events: dict[str, Any] | None = None,
    mcp_health: list[dict[str, Any]] | None = None,
    waste: list[dict[str, Any]] | None = None,
    pressure: dict[str, Any] | None = None,
) -> None:
    """Emit a JSON document combining SQLite + fallback data."""
    if summary is not None:
        total_processed = int(summary["total_in"]) + int(summary["total_out"])
        in_context = max(0, int(summary["total_out"]) - int(summary["cache_bytes"]))
        saved = max(0, total_processed - in_context)
        skill_health = None
        if skill_stats:
            skill_health = [
                {
                    "skill": skill,
                    "invocations": counts["invocations"],
                    "corrections": counts["corrections"],
                    "correction_rate": (
                        round(counts["corrections"] / counts["invocations"], 4)
                        if counts["invocations"] > 0
                        else 0.0
                    ),
                }
                for skill, counts in sorted(
                    skill_stats.items(), key=lambda kv: kv[1]["invocations"], reverse=True
                )
            ]
        payload: dict[str, Any] = {
            "source": "sqlite",
            "bytes_processed": total_processed,
            "bytes_in_context": in_context,
            "bytes_saved": saved,
            "reduction_pct": round(100 * saved / total_processed) if total_processed else 0,
            "cache_hits": int(summary["cache_hits"]),
            "cache_bytes_saved": int(summary["cache_bytes"]),
            "cache_hit_rate_pct": cache_rate["hit_rate_pct"] if cache_rate else None,
            "cache_read_tokens": cache_rate["cache_read"] if cache_rate else None,
            "cache_write_tokens": cache_rate["cache_write"] if cache_rate else None,
            "uncached_tokens": cache_rate["uncached"] if cache_rate else None,
            "cache_rate_host": cache_rate.get("host") if cache_rate else None,
            "cache_rate_consistent_events": (
                cache_rate.get("consistent_events") if cache_rate else None
            ),
            "cache_rate_inconsistent_events": (
                cache_rate.get("inconsistent_events") if cache_rate else None
            ),
            "per_tool": summary["per_tool"],
            "skill_health": skill_health,
            "learning_tests": lt_stats,
            "usage_by_model": (
                {k: v for k, v in usage_events.items() if k != "provenance"}
                if usage_events is not None
                else None
            ),
            "mcp_health": mcp_health,
            "waste": waste,
            "context_pressure": pressure,
        }
    elif state is not None:
        raw_estimate = state.get("estimated_tokens")
        payload = {
            "source": "fallback",
            "estimated_tokens": int(raw_estimate) if raw_estimate is not None else None,
            "tool_calls": int(state.get("tool_calls") or 0),
            "breakdown": state.get("breakdown") or {},
            "learning_tests": lt_stats,
            "context_pressure": pressure,
        }
    else:
        payload = {"source": "none"}
    if payload["source"] != "none":
        payload["token_provenance"] = _token_provenance(
            summary, state, cache_rate, usage_events, waste, pressure
        )
    print(json.dumps(payload, indent=2))


def _load_lt_config(cwd: Path) -> LearningTestsConfig:
    """Load LearningTestsConfig from .ll/ll-config.json, defaulting to disabled."""
    config_path = cwd / ".ll" / "ll-config.json"
    if not config_path.exists():
        return LearningTestsConfig()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return LearningTestsConfig.from_dict(data.get("learning_tests", {}))
    except (OSError, json.JSONDecodeError):
        return LearningTestsConfig()


def _first_party_top_level_names(scan_dirs: list[Path]) -> set[str]:
    """Top-level directory names under scan_dirs (e.g. ``little_loops``, ``tests``).

    Used to exclude first-party modules from the "coverage gaps" list (AC 11) —
    a widened import scan otherwise surfaces hundreds of ``little_loops.*``
    submodules as spurious gaps.
    """
    names: set[str] = set()
    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for entry in scan_dir.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                names.add(entry.name.lower())
    return names


def _compute_learning_tests_stats(
    cwd: Path,
    lt_config: LearningTestsConfig,
) -> dict[str, Any] | None:
    """Compute learning test registry stats.

    Applies date-aware staleness reclassification: a record with status=proven
    that exceeds stale_after_days is counted as stale, not proven (ENH-2208).
    Returns None when learning_tests.enabled is False.
    """
    if not lt_config.enabled:
        return None

    records = list_records()

    proven = 0
    stale = 0
    refuted = 0
    last_date: str | None = None
    known_slugs: set[str] = set()

    for record in records:
        if last_date is None or record.date > last_date:
            last_date = record.date
        known_slugs.add(slugify(record.target))

        if record.status == "refuted":
            refuted += 1
        elif record.status == "stale" or (
            record.status == "proven"
            and is_record_stale(
                record,
                lt_config.stale_after_days,
                version_aware=lt_config.version_aware_staleness,
                backstop_multiplier=lt_config.version_match_backstop_multiplier,
            )
        ):
            stale += 1
        else:
            proven += 1

    scan_dirs = [cwd / d for d in lt_config.scan_dirs]
    imported = get_imported_packages(scan_dirs)
    stdlib_names = set(sys.stdlib_module_names)
    first_party_names = _first_party_top_level_names(scan_dirs)
    gaps = sorted(
        pkg
        for pkg in imported
        if slugify(pkg) not in known_slugs
        and pkg.split(".")[0] not in stdlib_names
        and pkg.split(".")[0] not in first_party_names
    )

    return {
        "total": len(records),
        "proven": proven,
        "stale": stale,
        "refuted": refuted,
        "last_record": last_date,
        "gaps": gaps,
    }


def _render_learning_tests_section(lt_stats: dict[str, Any]) -> None:
    """Print the Learning Tests dashboard section."""
    total = lt_stats["total"]
    proven = lt_stats["proven"]
    stale = lt_stats["stale"]
    refuted = lt_stats["refuted"]
    last_record = lt_stats["last_record"]
    gaps: list[str] = lt_stats["gaps"]

    print()
    print("Learning tests:")
    print(f"  {total} total ({proven} proven, {stale} stale, {refuted} refuted)")
    if last_record:
        print(f"  Last record: {last_record}")
    if gaps:
        print(f"  Coverage gaps: {', '.join(gaps)}")


def main_ctx_stats(argv: list[str] | None = None) -> int:
    """Entry point for ll-ctx-stats command.

    Read per-tool byte metrics from ``.ll/history.db`` (FEAT-1623) and print
    a context-window savings summary. Falls back to
    ``.ll/ll-context-state.json`` when the SQLite store is absent.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-ctx-stats", sys.argv[1:]):
        args = _parse_args(argv)
        configure_output()
        logger = Logger(use_color=use_color_enabled())

        cwd = Path.cwd()
        db_path = args.db if args.db is not None else resolve_history_db(cwd / DEFAULT_DB_RELPATH)
        state_path = cwd / DEFAULT_STATE_RELPATH

        summary = _aggregate_tool_events(db_path)
        skill_stats = _aggregate_skill_stats(db_path)
        fallback = _load_fallback_state(state_path) if summary is None else None
        host = _resolve_host(args.host, default=None)
        cache_rate = _compute_cache_rate_from_jsonl(cwd, host)
        lt_config = _load_lt_config(cwd)
        lt_stats = _compute_learning_tests_stats(cwd, lt_config)
        usage_events = _aggregate_usage_events(db_path)
        mcp_health = _aggregate_mcp_health(db_path)
        waste = _aggregate_waste(db_path)
        pressure = _aggregate_context_pressure(db_path)

        if args.json_mode:
            _print_json(
                summary,
                fallback,
                skill_stats,
                cache_rate,
                lt_stats,
                usage_events,
                mcp_health,
                waste,
                pressure,
            )
            return 0 if (summary is not None or fallback is not None) else 1

        if summary is not None:
            total_rows = int(summary["total_in"]) + int(summary["total_out"])
            if total_rows == 0:
                logger.warning(
                    "No analytic rows in .ll/history.db — enable analytics (analytics.enabled: true) "
                    "and ensure analytics.capture.file_events is not disabled, then run a few tool calls."
                )
                if fallback is None:
                    fallback = _load_fallback_state(state_path)
            else:
                _render(
                    summary, logger, skill_stats, cache_rate, lt_stats, mcp_health, waste, pressure
                )
                return 0

        if fallback is not None:
            _render_fallback(fallback, logger)
            return 0

        logger.error(
            "No context analytics found: neither .ll/history.db nor "
            ".ll/ll-context-state.json contained data for this project."
        )
        return 1
