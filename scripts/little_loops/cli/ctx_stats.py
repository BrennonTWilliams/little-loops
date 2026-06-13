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
import sqlite3
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
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

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
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT tool_name, bytes_in, bytes_out, cache_hit "
                "FROM tool_events WHERE bytes_in IS NOT NULL OR bytes_out IS NOT NULL"
            ).fetchall()
        except sqlite3.OperationalError:
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


def _load_fallback_state(path: Path) -> dict[str, Any] | None:
    """Return ``.ll/ll-context-state.json`` parsed, or ``None`` if absent/invalid."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _render(
    summary: dict[str, Any],
    logger: Logger,
    skill_stats: dict[str, dict[str, int]] | None = None,
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

    if skill_stats:
        print()
        print("Skill health:")
        ranked_skills = sorted(skill_stats.items(), key=lambda kv: kv[1]["invocations"], reverse=True)
        for skill, counts in ranked_skills:
            inv = counts["invocations"]
            corr = counts["corrections"]
            rate = round(100 * corr / inv) if inv > 0 else 0
            print(f"  {skill:<22} {inv:>3} invocations   {corr:>2} corrections ({rate}%)")
    elif skill_stats is not None:
        logger.info("No skill events recorded yet.")


def _render_fallback(state: dict[str, Any], logger: Logger) -> None:
    """Render the ``.ll/ll-context-state.json`` fallback (token estimates)."""
    estimated = int(state.get("estimated_tokens") or 0)
    tool_calls = int(state.get("tool_calls") or 0)
    breakdown = state.get("breakdown") or {}

    logger.info(
        "SQLite session store not found — falling back to .ll/ll-context-state.json "
        "(enable analytics (analytics.enabled: true) and ensure analytics.capture.file_events is not disabled)."
    )
    print()
    print(f"Estimated tokens in context: {estimated:,}")
    print(f"Tool calls this session:     {tool_calls}")
    if isinstance(breakdown, dict) and breakdown:
        print()
        print("Per-tool token estimates:")
        for tool, tokens in sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True):
            print(f"  {str(tool):<20} {int(tokens):>8} tokens")


def _print_json(
    summary: dict[str, Any] | None,
    state: dict[str, Any] | None,
    skill_stats: dict[str, dict[str, int]] | None = None,
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
            "per_tool": summary["per_tool"],
            "skill_health": skill_health,
        }
    elif state is not None:
        payload = {
            "source": "fallback",
            "estimated_tokens": int(state.get("estimated_tokens") or 0),
            "tool_calls": int(state.get("tool_calls") or 0),
            "breakdown": state.get("breakdown") or {},
        }
    else:
        payload = {"source": "none"}
    print(json.dumps(payload, indent=2))


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
        db_path = args.db if args.db is not None else cwd / DEFAULT_DB_RELPATH
        state_path = cwd / DEFAULT_STATE_RELPATH

        summary = _aggregate_tool_events(db_path)
        skill_stats = _aggregate_skill_stats(db_path)
        fallback = _load_fallback_state(state_path) if summary is None else None

        if args.json_mode:
            _print_json(summary, fallback, skill_stats)
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
                _render(summary, logger, skill_stats)
                return 0

        if fallback is not None:
            _render_fallback(fallback, logger)
            return 0

        logger.error(
            "No context analytics found: neither .ll/history.db nor "
            ".ll/ll-context-state.json contained data for this project."
        )
        return 1
