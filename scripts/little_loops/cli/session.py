"""ll-session: query the unified session store (SQLite + FTS5).

Wraps :mod:`little_loops.session_store` with a CLI surface so operators can
search and inspect the per-project ``.ll/history.db`` without re-parsing the
scattered JSON/markdown sources the analyze-* skills read.

Subcommands:
    search   FTS5 full-text query with BM25-ranked results and optional --kind filter
    recent   most recent rows for an event kind (tool, file, issue, loop, correction,
             message, skill, cli, snapshot, commit, test_run, usage, orchestration_run,
             hook_event, harness, prompt_opt, verdict, context_pressure)
    skill-stats per-skill invocation/success-rate rollup (ENH-2460)
    backfill ingest on-disk sources into raw_events + issue/loop/commit tables (ENH-2581)
    refresh  replace verified normalized raw rows from original session sources (ENH-3534)
    rebuild  wipe+re-derive the JSONL-derived cache tables from raw_events (ENH-2581)
    compact  sweep old raw_events into per-session retention summaries (ENH-2581)
    related  issue events for a given issue ID
    subagents subagent spawn tree (or --budget rollup) for a session (ENH-3211)
    subagent-retries repeat-spawn rollup for an agent type (ENH-3211)
    path     resolve JSONL file path for a session ID
    grep     regex search over message_events with covering summary node context
    expand   return message_events covered by a summary node
    describe metadata for a summary node
    migrate  apply pending schema migrations; the only command that migrates a remote store
    prune    delete compacted raw_events rows older than configured max-age and VACUUM (ENH-1906)
    recompress rewrite legacy uncompressed raw_events payloads as zlib BLOBs and VACUUM
    redact   scrub stored raw_events payloads under the current redaction policy (ENH-3752)
    export   dump selected tables as JSONL for visualization or external tooling
    record-hook-event  record one hook fire into hook_events; invoked by the bash shim (ENH-2506)
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.cli_args import add_host_arg, add_json_arg
from little_loops.history_reader import (
    ll_describe,
    ll_expand,
    ll_grep,
    related_issue_events,
    sessions_for_issue,
    subagent_budget,
    subagent_retries,
    subagent_tree,
)
from little_loops.history_reader import search as history_search
from little_loops.logger import Logger
from little_loops.session_store import (
    DEFAULT_DB_PATH,
    VALID_KINDS,
    HistoryError,
    SessionHandle,
    backfill,
    backfill_incremental,
    backfill_snapshots,
    cli_event_context,
    compact,
    connect,
    detect_sessions,
    explain_no_sessions,
    export_history,
    export_tables_help,
    host_layout_for,
    prune,
    rebuild,
    recent,
    recompress_raw_events,
    record_hook_event,
    redact_raw_events,
    resolve_history_db,
    search,
)
from little_loops.session_store.backend import refuse_on_remote
from little_loops.session_store.raw_redaction import RawRedactionError, RawRedactionReport
from little_loops.session_store.usage_refresh import refresh_raw_events
from little_loops.user_messages import get_project_folder


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for ll-session."""
    parser = argparse.ArgumentParser(
        prog="ll-session",
        description="Query the unified session store (SQLite + FTS5)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s search --fts "rate limit"              # Full-text search, BM25-ranked
  %(prog)s search --fts "error" --kind loop       # FTS5 search filtered by kind
  %(prog)s recent --kind loop                     # Recent loop events
  %(prog)s recent --kind verdict                  # Recent verifier verdicts
  %(prog)s recent --kind context_pressure         # Recent context-pressure samples
  %(prog)s related BUG-1759                       # Events for a specific issue
  %(prog)s subagents SESSION_ID                    # Subagent spawn tree for a session
  %(prog)s subagents SESSION_ID --budget           # Spawn count + total duration
  %(prog)s subagent-retries Explore                # Sessions that re-spawned Explore
  %(prog)s backfill                               # Ingest on-disk sources (raw_events + issues/loops/commits)
  %(prog)s backfill --rebuild                     # Ingest, then materialize cache tables in one call
  %(prog)s refresh --host claude-code --session-id ID --rebuild  # Restore from original
  %(prog)s rebuild                                # Re-derive cache tables from raw_events
  %(prog)s compact --and-prune                    # Sweep+summarize old raw_events, then delete
  %(prog)s grep "auth middleware"                 # Regex search over message_events
  %(prog)s expand 42                              # Messages covered by summary node 42
  %(prog)s describe 42                            # Metadata for summary node 42
  %(prog)s prune --dry-run                        # Show what would be pruned
  %(prog)s prune                                  # Delete old raw events and VACUUM
  %(prog)s recompress                             # Compress legacy raw_events payloads and VACUUM
  %(prog)s redact --dry-run                       # Preview scrubbing stored raw_events payloads
  %(prog)s redact                                 # Scrub stored raw_events payloads in place
""",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        metavar="PATH",
        help="Path to the session database (default: .ll/history.db)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    path_parser = subparsers.add_parser("path", help="Resolve JSONL file path for a session ID")
    path_parser.add_argument("session_id", metavar="SESSION_ID", help="Session ID to look up")

    search_parser = subparsers.add_parser("search", help="FTS5 full-text search")
    search_parser.add_argument("--fts", required=True, metavar="QUERY", help="FTS5 match query")
    search_parser.add_argument(
        "--kind",
        choices=list(VALID_KINDS),
        default=None,
        help="Filter results by event kind",
    )
    search_parser.add_argument(
        "--limit", type=int, default=20, metavar="N", help="Maximum results (default: 20)"
    )
    add_json_arg(search_parser)

    recent_parser = subparsers.add_parser("recent", help="Recent events by kind")
    recent_parser.add_argument(
        "--kind",
        choices=list(VALID_KINDS),
        default=None,
        help="Event kind to list (required unless --issue is given)",
    )
    recent_parser.add_argument(
        "--issue",
        default=None,
        metavar="ID",
        help="Filter to sessions that touched this issue ID (e.g. ENH-1710)",
    )
    recent_parser.add_argument(
        "--limit", type=int, default=20, metavar="N", help="Maximum rows (default: 20)"
    )
    recent_parser.add_argument(
        "--mcp-server",
        default=None,
        metavar="NAME",
        help="Filter --kind tool rows to this MCP server (ENH-2511)",
    )
    recent_parser.add_argument(
        "--mcp-tool",
        default=None,
        metavar="NAME",
        help="Filter --kind tool rows to this MCP tool (ENH-2511)",
    )
    recent_parser.add_argument(
        "--mcp-outcome",
        choices=["success", "error", "timeout"],
        default=None,
        help="Filter --kind tool rows to this MCP outcome (ENH-2511)",
    )
    recent_parser.add_argument(
        "--json", action="store_true", dest="json", help="Output as JSON array"
    )

    related_parser = subparsers.add_parser("related", help="Issue events for an issue ID")
    related_parser.add_argument("issue_id", metavar="ISSUE_ID", help="Issue ID (e.g., BUG-1759)")
    related_parser.add_argument(
        "--limit", type=int, default=20, metavar="N", help="Maximum results (default: 20)"
    )
    add_json_arg(related_parser)

    subagents_parser = subparsers.add_parser(
        "subagents", help="Subagent spawn tree for a session (ENH-2505)"
    )
    subagents_parser.add_argument(
        "session_id", metavar="SESSION_ID", help="Parent session ID to look up"
    )
    subagents_parser.add_argument(
        "--budget",
        action="store_true",
        default=False,
        help="Show spawn count + total duration instead of the per-row tree",
    )
    add_json_arg(subagents_parser)

    subagent_retries_parser = subparsers.add_parser(
        "subagent-retries", help="Repeat-spawn rollup for an agent type (ENH-2505)"
    )
    subagent_retries_parser.add_argument(
        "agent_type", metavar="AGENT_TYPE", help="Agent type to check for repeat spawns"
    )
    subagent_retries_parser.add_argument(
        "--since",
        default=None,
        metavar="DATE",
        help="Only count spawns at or after this ISO 8601 date/datetime",
    )
    add_json_arg(subagent_retries_parser)

    backfill_parser = subparsers.add_parser(
        "backfill", help="Seed the database from existing on-disk sources"
    )
    backfill_parser.add_argument(
        "--since",
        metavar="DATE",
        default=None,
        help="Only process JSONL files modified after DATE (ISO 8601 or YYYY-MM-DD); uses incremental mode",
    )

    refresh_parser = subparsers.add_parser(
        "refresh", help="Re-ingest verified stored session sources from their originals"
    )
    add_host_arg(refresh_parser, help_text="Verified stored source host to refresh")
    refresh_parser.add_argument("--session-id", metavar="ID", help="Refresh one stored session ID")
    refresh_parser.add_argument(
        "--all", action="store_true", help="Refresh every verified stored source for --host"
    )
    refresh_parser.add_argument(
        "--rebuild", action="store_true", help="Re-derive cache tables after raw replacement"
    )
    add_json_arg(refresh_parser)
    add_host_arg(
        backfill_parser,
        help_text="Host to discover session logs for (default: auto-detect from LL_HOOK_HOST env)",
    )
    backfill_parser.add_argument(
        "--extract-decisions",
        action="store_true",
        default=False,
        dest="extract_decisions",
        help="After backfill, run extract-from-completed to mine completed issues for rules (ENH-2152)",
    )
    backfill_parser.add_argument(
        "--snapshots",
        action="store_true",
        default=False,
        help="Hydrate issue_snapshots table from existing .issues/ files (ENH-2151)",
    )
    backfill_parser.add_argument(
        "--max-sessions",
        type=int,
        default=None,
        metavar="N",
        dest="max_sessions",
        help="Cap the number of sessions compacted in this run (newest first); useful for large DBs",
    )
    backfill_parser.add_argument(
        "--rebuild",
        action="store_true",
        default=False,
        help=(
            "Also materialize the JSONL-derived cache tables from raw_events "
            "in this call (ingest + rebuild in one step; ENH-2581)"
        ),
    )

    rebuild_parser = subparsers.add_parser(
        "rebuild",
        help="Wipe+re-derive the JSONL-derived cache tables from raw_events (ENH-2581)",
    )
    rebuild_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to ll-config.json (default: auto-resolve from cwd)",
    )
    add_json_arg(rebuild_parser)

    compact_parser = subparsers.add_parser(
        "compact",
        help="Sweep old raw_events into per-session retention summaries (ENH-2581)",
    )
    compact_parser.add_argument(
        "--and-prune",
        action="store_true",
        default=False,
        dest="and_prune",
        help="Also delete the newly-compacted raw_events rows and VACUUM afterward",
    )
    compact_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to ll-config.json (default: auto-resolve from cwd)",
    )
    add_json_arg(compact_parser)

    export_parser = subparsers.add_parser(
        "export",
        help="Dump selected tables as JSONL for visualization or external tooling",
    )
    export_parser.add_argument(
        "--tables",
        nargs="+",
        metavar="TYPE",
        default=None,
        help=export_tables_help(),
    )
    export_parser.add_argument(
        "--since",
        metavar="DATE",
        default=None,
        help="Only rows at or after this ISO 8601 date/datetime",
    )
    export_parser.add_argument(
        "--include-messages",
        action="store_true",
        default=False,
        dest="include_messages",
        help="Also include message_events (~46 K rows); ignored when --tables is given",
    )
    export_parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        default=None,
        help="Write output to FILE instead of stdout",
    )

    grep_parser = subparsers.add_parser(
        "grep", help="Regex search over message_events with summary node context"
    )
    grep_parser.add_argument("pattern", metavar="PATTERN", help="Regex pattern (case-insensitive)")
    grep_parser.add_argument(
        "--summary-id",
        type=int,
        default=None,
        metavar="ID",
        help="Restrict search to messages covered by this summary node ID",
    )
    grep_parser.add_argument(
        "--limit", type=int, default=50, metavar="N", help="Maximum results (default: 50)"
    )
    add_json_arg(grep_parser)

    expand_parser = subparsers.add_parser(
        "expand", help="Return message_events covered by a summary node"
    )
    expand_parser.add_argument(
        "summary_id", type=int, metavar="SUMMARY_ID", help="Summary node ID to expand"
    )
    add_json_arg(expand_parser)

    describe_parser = subparsers.add_parser("describe", help="Show metadata for a summary node")
    describe_parser.add_argument(
        "node_id", type=int, metavar="NODE_ID", help="Summary node ID to describe"
    )
    add_json_arg(describe_parser)

    skill_stats_parser = subparsers.add_parser(
        "skill-stats",
        help="Per-skill invocation/success-rate rollup from skill_events (ENH-2460)",
    )
    skill_stats_parser.add_argument(
        "--since",
        metavar="DATE",
        default=None,
        help="Only count rows at or after this ISO 8601 date/datetime",
    )
    add_json_arg(skill_stats_parser)

    prune_parser = subparsers.add_parser(
        "prune",
        help="Prune raw event rows older than configured max-age and VACUUM the database",
    )
    prune_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report which rows would be deleted without actually deleting them",
    )
    add_json_arg(prune_parser)

    recompress_parser = subparsers.add_parser(
        "recompress",
        help="Rewrite legacy uncompressed raw_events payloads as zlib BLOBs and VACUUM",
    )
    recompress_parser.add_argument(
        "--batch",
        type=int,
        default=2000,
        metavar="N",
        help="Rows to rewrite per transaction (default: 2000)",
    )
    add_json_arg(recompress_parser)

    redact_parser = subparsers.add_parser(
        "redact",
        help="Scrub stored raw_events payloads under the current redaction policy "
        "(local or remote; never migrates)",
    )
    redact_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate and report what would change without writing anything",
    )
    redact_parser.add_argument(
        "--batch",
        type=_positive_int,
        default=2000,
        metavar="N",
        help="Maximum rows per scan page (default: 2000; internal byte bounds still apply)",
    )
    add_json_arg(redact_parser)

    subparsers.add_parser(
        "migrate",
        help="Bring the history store's schema to this install's version "
        "(the only path that migrates a remote store)",
    )

    record_hook_event_parser = subparsers.add_parser(
        "record-hook-event",
        help="Record one hook fire into hook_events (ENH-2506); invoked by the bash shim",
    )
    record_hook_event_parser.add_argument("--session-id", default=None, metavar="ID")
    record_hook_event_parser.add_argument("--event-name", required=True, metavar="NAME")
    record_hook_event_parser.add_argument("--matcher", default=None, metavar="PATTERN")
    record_hook_event_parser.add_argument("--script", default=None, metavar="PATH")
    record_hook_event_parser.add_argument("--exit-code", type=int, required=True, metavar="N")
    record_hook_event_parser.add_argument("--duration-ms", type=int, default=None, metavar="N")
    record_hook_event_parser.add_argument("--stderr-preview", default=None, metavar="TEXT")

    return parser


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments. Exposed for testing."""
    return _build_parser().parse_args()


def _run_extract_decisions(since: str | None = None) -> None:
    """Invoke ll-issues decisions extract-from-completed after a backfill."""
    import subprocess
    import sys

    cmd = ["ll-issues", "decisions", "extract-from-completed"]
    if since:
        cmd += ["--since", since]
    try:
        result = subprocess.run(cmd, capture_output=False)
        if result.returncode != 0:
            print(
                "extract-from-completed exited non-zero; decisions.yaml unchanged", file=sys.stderr
            )
    except FileNotFoundError:
        print("ll-issues not found; skipping extract-from-completed", file=sys.stderr)


def _load_capture_config(cwd: Path) -> dict | None:
    """Load the project's ll-config.json as a raw dict for analytics gating (ENH-3449).

    Guarded loader (``resolve_config_path`` + except-guarded ``json.loads``,
    matching ``cli/history.py``): a missing or malformed config returns
    ``None`` — permissive — so a broken ll-config.json can never fail
    ll-session's never-fail enter contract.
    """
    import json

    from little_loops.config.core import resolve_config_path

    config_path = resolve_config_path(cwd)
    if config_path is None:
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _is_foreign_path(path_text: str | None) -> bool:
    """True when *path_text* is a transcript path that does not exist on this machine and the
    history store is a shared remote one (so the row was most likely recorded elsewhere)."""
    if not path_text or Path(path_text).exists():
        return False
    from little_loops.session_store.db import resolve_history_target
    from little_loops.session_store.targets import RemoteTarget

    return isinstance(resolve_history_target(DEFAULT_DB_PATH), RemoteTarget)


def _positive_int(raw: str) -> int:
    """argparse ``type=`` callable: an integer >= 1."""
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {value}")
    return value


# Fixed stderr text per stop reason: backend messages, endpoints and credentials never appear.
_REDACT_GUIDANCE = {
    (
        "target_unavailable",
        None,
    ): "the history store is missing or unreachable; nothing was created",
    ("schema_mismatch", "migrate"): (
        "the history store schema is behind this install; run `ll-session migrate`, then retry"
    ),
    ("schema_mismatch", "upgrade"): (
        "the history store schema is ahead of this install; upgrade little-loops, then retry"
    ),
    ("schema_mismatch", None): "the history store is not a current-schema store for this project",
    ("backend_failure", None): "the history store reported a failure before any row was scanned",
    ("interrupted", None): "interrupted before the scan started",
}

_REDACT_SCOPE = (
    "Scope: raw_events payload columns only. Derived/FTS/summary rows, original transcripts, "
    "backups, WAL/free pages and provider history are not covered; no rebuild was run."
)


def _redact_error(args: argparse.Namespace, exc: RawRedactionError | None) -> int:
    reason = "backend_failure" if exc is None else exc.reason
    guidance = None if exc is None else exc.guidance
    if args.json:
        print_json({"complete": False, "error": reason})
    text = _REDACT_GUIDANCE.get((reason, guidance)) or _REDACT_GUIDANCE.get((reason, None))
    print(f"ll-session redact: {text or reason}", file=sys.stderr)
    return 130 if reason == "interrupted" else 1


_SIZE_DETAIL = {
    "stored": "stored value ({stored}) exceeds the {limit}-byte read limit; not validated",
    "decoded": "decoded value exceeds the {limit}-byte limit (stored {stored}); not validated",
    "replacement_stored": (
        "redactable content found, but the scrubbed value exceeds the {limit}-byte stored limit "
        "(original {stored}); NOT written"
    ),
    "replacement_decoded": (
        "redactable content found, but the scrubbed value exceeds the {limit}-byte decoded limit "
        "(original {stored}); NOT written"
    ),
    "request": (
        "redactable content found, but the guarded write request exceeds the {limit}-byte "
        "remote limit; NOT written"
    ),
}


def _print_size_refusals(report: RawRedactionReport) -> None:
    """Itemize retained size refusals and state honestly what a rerun cannot change."""
    print(
        f"Size-refused: {report.oversize_refused:,} row(s) exceeded a fixed size budget; each "
        "whole row was left unchanged."
    )
    itemized: set[int | None] = set()
    for p in report.problems:
        if p.limit_kind is None or p.limit_kind not in _SIZE_DETAIL:
            continue
        itemized.add(p.row_id)
        stored = "unknown size" if p.stored_bytes is None else f"{p.stored_bytes:,} bytes"
        detail = _SIZE_DETAIL[p.limit_kind].format(stored=stored, limit=f"{p.limit_bytes or 0:,}")
        print(f"  row {p.row_id} {p.column or '(request)'}: {detail}")
    omitted = report.oversize_refused - len(itemized)
    if omitted > 0:
        print(
            f"  {omitted:,} more size-refused row(s) are not itemized (details omitted); they "
            "may include known-dirty payloads left unredacted."
        )
    print(
        "  An unchanged row may still contain unredacted matches, including in a sibling column "
        "that validated cleanly."
    )
    print(
        "  Rerunning unchanged cannot resolve this: review the reported row ids and reduce or "
        "remove the affected payloads through backend administration before rerunning. This "
        "command never modifies or deletes them."
    )


def _print_redact_report(report: RawRedactionReport) -> None:
    verb = "Would change" if report.dry_run else "Changed"
    through = "" if report.last_scanned_id is None else f" through id {report.last_scanned_id}"
    if report.dry_run:
        print("DRY RUN — nothing was written\n")
    print(f"Scanned {report.scanned:,} row(s){through}.")
    if report.dry_run:
        print(f"{verb} {report.would_change:,} row(s).")
    else:
        print(f"{verb}: {report.updates_applied:,} update(s) applied.")
        if report.unattributed_updates_applied:
            print(f"  {report.unattributed_updates_applied:,} without a per-rule breakdown.")
        if report.reconciled:
            print(f"  {report.reconciled:,} row(s) already scrubbed when re-read.")
    for column, rules in report.counts_by_column.items():
        detail = ", ".join(f"{rule}={n:,}" for rule, n in sorted(rules.items()))
        print(f"  {column}: {detail}")
    if not report.counts_complete:
        print("Counts are a lower bound: some write outcomes could not be attributed.")
    for label, value in (
        ("Failed", report.failed),
        ("Conflicts", report.conflicts),
        ("Unconfirmed", report.unconfirmed),
    ):
        if value:
            print(f"{label}: {value:,} row(s) left as found (see --json for codes).")
    if report.oversize_refused:
        _print_size_refusals(report)
    if report.stop_reason:
        print(f"Stopped early: {report.stop_reason}")
    if not report.complete:
        if not report.oversize_refused:
            print("Incomplete: rerun after resolving the above.")
        elif (
            report.oversize_refused == report.failed
            and not report.conflicts
            and not report.unconfirmed
            and not report.stop_reason
        ):
            print("Incomplete: size-refused rows will not change on a rerun.")
        else:
            print("Incomplete: rerun after resolving the above; size-refused rows will not change.")
    print(_REDACT_SCOPE)


def _main_redact(args: argparse.Namespace) -> int:
    """``ll-session redact``: runs outside ``cli_event_context`` so a preview writes no telemetry
    and the explicit ``--db`` target is the only store touched."""
    from dataclasses import asdict

    from little_loops.session_store.backend import HistoryError

    configure_output()
    try:
        report = redact_raw_events(args.db, batch_size=args.batch, dry_run=args.dry_run)
    except RawRedactionError as exc:
        return _redact_error(args, exc)
    except HistoryError:
        return _redact_error(args, None)
    if args.json:
        print_json(asdict(report))
    else:
        _print_redact_report(report)
    if report.complete:
        return 0
    return 130 if report.stop_reason == "interrupted" else 1


def _main_migrate() -> int:
    """``ll-session migrate``: run before ``cli_event_context`` so no telemetry row is written
    into a store that may be mid-migration (or, for a remote store, not yet migratable)."""
    from little_loops.session_store import remote_schema
    from little_loops.session_store.backend import HistoryError, RemoteTarget
    from little_loops.session_store.db import resolve_history_target
    from little_loops.session_store.schema import (
        SCHEMA_VERSION,
        _current_version,
        ensure_db,
    )

    _build_parser().parse_args()
    configure_output()
    logger = Logger(use_color=use_color_enabled())
    try:
        target = resolve_history_target(DEFAULT_DB_PATH)
        if isinstance(target, RemoteTarget):
            from little_loops.session_store.hrana import HranaClient

            cfg = target.config
            report = remote_schema.migrate_remote(
                HranaClient(cfg.endpoint(), cfg.auth_token()), cfg.project_id
            )
            before, after, where = report.before, report.after, f"remote ({cfg.provider})"
        else:
            from little_loops.session_store.backend import HistoryUnavailable, connect_readonly

            path = target.path
            before = 0
            try:  # strict read-only probe: never creates or migrates the file
                with contextlib.closing(connect_readonly(path)) as probe:
                    before = _current_version(probe)
            except HistoryUnavailable:
                pass
            ensure_db(path)
            after, where = SCHEMA_VERSION, str(path)
    except HistoryError as exc:
        logger.error(f"migrate failed: {exc}")
        return 1
    if before == after:
        logger.info(f"Schema already current at v{after} ({where})")
    else:
        logger.success(f"Migrated schema v{before} -> {after} ({where}): {before} -> {after}")
    return 0


def main_session() -> int:
    """Entry point for ``ll-session``; reports history-policy refusals by reason code only."""
    from little_loops.pii import HistorySanitizationError

    try:
        return _main_session()
    except HistorySanitizationError as exc:
        # ENH-3751: a backfill source the sanitizer rejects (e.g. invalid_payload). The
        # error carries only its fixed reason code, never payload text.
        print(f"ll-session: history sanitization rejected a source: {exc.reason}", file=sys.stderr)
        return 1


def _main_session() -> int:
    """Entry point for ll-session command.

    Returns:
        0 on success, 1 when no subcommand is given or on error.
    """
    if sys.argv[1:2] == ["migrate"]:
        return _main_migrate()
    # Parsed once, before the telemetry context (ENH-3752): `redact` must run outside it, so
    # help and argparse usage errors no longer emit telemetry for any subcommand.
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "redact":
        return _main_redact(args)
    # Loaded before the with-block: the context manager opens before argparse
    # runs, so parsed args cannot participate (see cli/history.py, ENH-3449).
    capture_config = _load_capture_config(Path.cwd())
    with cli_event_context(DEFAULT_DB_PATH, "ll-session", sys.argv[1:], config=capture_config):
        configure_output()
        logger = Logger(use_color=use_color_enabled())

        if not args.command:
            parser.print_help()
            return 1

        if args.command == "path":
            conn = connect(args.db)
            try:
                row = conn.execute(
                    "SELECT jsonl_path FROM sessions WHERE session_id = ?", (args.session_id,)
                ).fetchone()
            finally:
                conn.close()
            if row is None:
                print(f"Session {args.session_id} not found.")
                return 1
            path_text = row["jsonl_path"]
            if _is_foreign_path(path_text):
                # A shared remote store holds rows recorded on other machines; their
                # transcript paths do not exist here and are not an error (FEAT-3535).
                print(f"{path_text}  (recorded on another machine)")
            else:
                print(path_text)
            return 0

        if args.command == "search":
            results: list[Any]
            if args.kind:
                results = history_search(args.fts, kind=args.kind, limit=args.limit, db=args.db)
            else:
                try:
                    results = search(args.db, query=args.fts, limit=args.limit)
                except ValueError as exc:
                    logger.error(str(exc))
                    return 1
            if args.json:
                if (
                    isinstance(results, list)
                    and results
                    and hasattr(results[0], "__dataclass_fields__")
                ):
                    from dataclasses import asdict

                    results = [asdict(r) for r in results]
                print_json(list(results))
                return 0
            if not results:
                print("No matches.")
                return 0
            for row in results:
                if hasattr(row, "__dataclass_fields__"):
                    anchor = f"  ({row.anchor})" if row.anchor else ""
                    print(f"[{row.kind}] {row.content}{anchor}")
                else:
                    anchor = f"  ({row['anchor']})" if row.get("anchor") else ""
                    print(f"[{row['kind']}] {row['content']}{anchor}")
            return 0

        if args.command == "related":
            events = related_issue_events(args.issue_id, limit=args.limit, db=args.db)
            if args.json:
                from dataclasses import asdict

                print_json([asdict(e) for e in events])
                return 0
            if not events:
                print(f"No events for {args.issue_id}.")
                return 0
            for e in events:
                fields = ", ".join(
                    f"{k}={getattr(e, k)}"
                    for k in ("ts", "transition", "issue_type", "priority")
                    if getattr(e, k)
                )
                print(fields)
            return 0

        if args.command == "subagents":
            if args.budget:
                budget = subagent_budget(args.session_id, db=args.db)
                if budget is None:
                    if args.json:
                        print_json(None)
                        return 0
                    print(f"No subagent runs found for {args.session_id}.")
                    return 0
                tree = subagent_tree(args.session_id, db=args.db)
                excluded = [run for run in tree if run.ended_at is None]
                excluded_running = sum(1 for run in excluded if run.status == "running")
                excluded_orphaned = sum(1 for run in excluded if run.status == "orphaned")
                if args.json:
                    print_json(
                        {
                            **budget,
                            "excluded_count": len(excluded),
                            "excluded_running": excluded_running,
                            "excluded_orphaned": excluded_orphaned,
                        }
                    )
                    return 0
                excluded_note = ""
                if excluded:
                    excluded_note = (
                        f"  ({len(excluded)} rows excluded: no ended_at"
                        f" — {excluded_running} running, {excluded_orphaned} orphaned)"
                    )
                print(
                    f"spawn_count={budget['spawn_count']}  "
                    f"total_duration_s={budget['total_duration_s']:.1f}{excluded_note}"
                )
                return 0

            tree = subagent_tree(args.session_id, db=args.db)
            if args.json:
                from dataclasses import asdict

                print_json([asdict(run) for run in tree])
                return 0
            if not tree:
                print(f"No subagent runs found for {args.session_id}.")
                return 0
            for run in tree:
                duration = "n/a"
                if run.started_at and run.ended_at:
                    try:
                        start = datetime.fromisoformat(run.started_at.replace("Z", "+00:00"))
                        end = datetime.fromisoformat(run.ended_at.replace("Z", "+00:00"))
                        duration = f"{(end - start).total_seconds():.1f}s"
                    except ValueError:
                        duration = "n/a"
                print(
                    f"agent_id={run.agent_id}  agent_type={run.agent_type}  "
                    f"status={run.status}  duration={duration}"
                )
            return 0

        if args.command == "subagent-retries":
            rows = subagent_retries(args.agent_type, since=args.since, db=args.db)
            if args.json:
                print_json(rows)
                return 0
            if not rows:
                print(f"No subagent runs found for {args.agent_type}.")
                return 0
            for row in rows:
                print(
                    f"parent_session_id={row['parent_session_id']}  spawn_count={row['spawn_count']}"
                )
            return 0

        if args.command == "recent":
            issue_filter = getattr(args, "issue", None)

            # --issue only: show sessions that co-occurred with the issue
            if issue_filter and not args.kind:
                refs = sessions_for_issue(issue_filter, limit=args.limit, db=args.db)
                if args.json:
                    from dataclasses import asdict

                    print_json([asdict(r) for r in refs])
                    return 0
                if not refs:
                    print(f"No sessions found for {issue_filter}.")
                    return 0
                for r in refs:
                    path = r.jsonl_path or "(no path)"
                    print(f"{r.session_id}  {path}")
                return 0

            if not args.kind:
                logger.error("recent: --kind is required unless --issue is given")
                return 1

            mcp_server = getattr(args, "mcp_server", None)
            mcp_tool = getattr(args, "mcp_tool", None)
            mcp_outcome = getattr(args, "mcp_outcome", None)
            if args.kind == "tool" and (mcp_server or mcp_tool or mcp_outcome):
                from little_loops.history_reader import recent_tool_events

                rows = recent_tool_events(
                    mcp_server=mcp_server,
                    mcp_tool=mcp_tool,
                    mcp_outcome=mcp_outcome,
                    limit=args.limit,
                    db=args.db,
                )
            else:
                rows = recent(args.db, kind=args.kind, limit=args.limit)
            if issue_filter:
                session_ids = {r.session_id for r in sessions_for_issue(issue_filter, db=args.db)}
                rows = [r for r in rows if r.get("session_id") in session_ids]
            if args.json:
                print_json(list(rows))
                return 0
            if not rows:
                print(f"No {args.kind} events.")
                return 0
            for row in rows:
                fields = ", ".join(
                    f"{k}={v}" for k, v in row.items() if k != "id" and v is not None
                )
                print(fields)
            return 0

        if args.command == "refresh":
            if not args.host:
                print("refresh requires --host", file=sys.stderr)
                return 1
            if bool(args.session_id) == bool(args.all):
                print("refresh requires exactly one of --session-id ID or --all", file=sys.stderr)
                return 1
            try:
                refuse_on_remote(args.db, "refresh_raw_events")
                db_path = resolve_history_db(args.db)
            except HistoryError as exc:
                print(f"Cannot refresh source rows: {exc}", file=sys.stderr)
                return 1
            if not db_path.exists():
                print(f"No history store at {db_path}", file=sys.stderr)
                return 1

            conn = connect(args.db)
            try:
                sql = (
                    "SELECT source_path, MIN(session_id), "
                    "COUNT(DISTINCT COALESCE(session_id, '')) "
                    "FROM raw_events WHERE source_path IN ("
                    "SELECT source_path FROM raw_events "
                    "WHERE host = ? AND host_basis = 'handle'"
                )
                params: list[str] = [args.host]
                if args.session_id:
                    sql += " AND session_id = ?"
                    params.append(args.session_id)
                sql += ") GROUP BY source_path ORDER BY source_path"
                sources = conn.execute(sql, params).fetchall()
            finally:
                conn.close()
            if not sources:
                label = f" session {args.session_id}" if args.session_id else ""
                print(f"No verified stored sources for {args.host}{label}", file=sys.stderr)
                return 1

            handles: list[SessionHandle] = []
            skipped: list[dict[str, Any]] = []
            for source_path, session_id, identity_count in sources:
                source_file = Path(source_path)
                if identity_count != 1 or not session_id:
                    skipped.append(
                        {
                            "path": source_path,
                            "status": "skipped",
                            "reason": "ambiguous_session_attribution",
                            "rows": 0,
                        }
                    )
                    continue
                try:
                    updated_at = source_file.stat().st_mtime
                except OSError:
                    updated_at = 0.0
                handles.append(
                    SessionHandle(args.host, session_id, source_file, Path.cwd(), updated_at)
                )
            refreshed = refresh_raw_events(args.db, handles=handles)
            source_results = [
                {
                    "path": str(source.path),
                    "status": source.status,
                    "reason": source.reason,
                    "rows": source.rows,
                }
                for source in refreshed.sources
            ] + skipped
            for source in source_results:
                if source["status"] == "skipped":
                    print(f"Skipped {source['path']}: {source['reason']}", file=sys.stderr)
            rebuild_counts = rebuild(args.db) if args.rebuild and handles else None
            needs_rebuild = refreshed.needs_rebuild and rebuild_counts is None
            if args.json:
                print_json(
                    {
                        "host": args.host,
                        "sources": source_results,
                        "rows_replaced": sum(
                            source["rows"]
                            for source in source_results
                            if source["status"] == "refreshed"
                        ),
                        "needs_rebuild": needs_rebuild,
                        "rebuild_counts": rebuild_counts,
                    }
                )
            else:
                changed = sum(source["status"] == "refreshed" for source in source_results)
                unchanged = sum(source["status"] == "unchanged" for source in source_results)
                print(f"Refreshed {changed} source(s); {unchanged} unchanged.")
                if needs_rebuild:
                    print("Run ll-session rebuild to re-derive usage and cache tables.")
                elif rebuild_counts is not None:
                    print("Rebuilt usage and cache tables from refreshed raw events.")
            return 1 if any(source["status"] == "skipped" for source in source_results) else 0

        if args.command == "backfill":
            if getattr(args, "snapshots", False):
                count = backfill_snapshots(args.db)
                logger.success(f"Backfilled {count} issue snapshots.")
                return 0

            # Effective host for layout lookups: --host wins, else the same
            # LL_HOOK_HOST auto-detect that get_project_folder uses (ENH-3165).
            from little_loops.user_messages import _resolve_host

            _backfill_host: str = _resolve_host(args.host, default="claude-code")

            # Read project config so compaction settings are respected (same
            # pattern as the prune handler).
            import json as _json

            from little_loops.config.core import resolve_config_path

            _config: dict | None = None
            _config_path = resolve_config_path(Path.cwd())
            if _config_path is not None:
                try:
                    _config = _json.loads(_config_path.read_text(encoding="utf-8"))
                except (OSError, _json.JSONDecodeError):
                    _config = None

            max_sessions = getattr(args, "max_sessions", None)
            since_flag = getattr(args, "since", None)
            if since_flag is not None:
                try:
                    try:
                        dt = datetime.fromisoformat(since_flag.replace("Z", "+00:00"))
                    except ValueError:
                        dt = datetime.strptime(since_flag, "%Y-%m-%d")
                    since_ts = dt.timestamp()
                except ValueError:
                    logger.error(f"Invalid date: {since_flag!r}. Use YYYY-MM-DD or ISO 8601.")
                    return 1
                also_rebuild = getattr(args, "rebuild", False)
                if _backfill_host == "codex":
                    # get_project_folder(host="codex") is always None by design
                    # (ENH-3420/ENH-3422 D4) — Codex keys sessions by cwd, not a
                    # projects/ tree, so discovery goes through detect_sessions.
                    codex_handles = detect_sessions(Path.cwd(), "codex")
                    if not codex_handles:
                        _cause, reason = explain_no_sessions(Path.cwd(), "codex")
                        print(f"No sessions found for: {Path.cwd()}", file=sys.stderr)
                        print(reason, file=sys.stderr)
                        return 1
                    inc_counts = backfill_incremental(
                        args.db,
                        handles=codex_handles,
                        since_ts=since_ts,
                        config=_config,
                        also_rebuild=also_rebuild,
                        host=_backfill_host,
                    )
                else:
                    project_folder = get_project_folder(host=args.host)
                    if project_folder is None:
                        _cause, reason = explain_no_sessions(Path.cwd(), host=_backfill_host)
                        print(f"No sessions found for: {Path.cwd()}", file=sys.stderr)
                        print(reason, file=sys.stderr)
                        return 1
                    # session_glob already encodes any subdir (e.g. qwen's
                    # "chats/*.jsonl", kimi-code's "session_*/agents/main/wire.jsonl"
                    # since ENH-3422); matches cli/backfill_worker.py (D5).
                    jsonl_files = list(
                        project_folder.glob(host_layout_for(_backfill_host).session_glob)
                    )
                    inc_counts = backfill_incremental(
                        args.db,
                        jsonl_files=jsonl_files,
                        since_ts=since_ts,
                        config=_config,
                        also_rebuild=also_rebuild,
                        host=_backfill_host,
                    )
                inc_total = sum(inc_counts.values())
                logger.success(
                    f"Backfilled {inc_total} rows (incremental, since {since_flag}; "
                    f"raw_events={inc_counts['raw_events']}"
                    + (
                        f", messages={inc_counts.get('messages', 0)}, "
                        f"sessions={inc_counts.get('sessions', 0)}, "
                        f"corrections={inc_counts.get('corrections', 0)})"
                        if also_rebuild
                        else ")"
                    )
                )
                if getattr(args, "extract_decisions", False):
                    _run_extract_decisions(since=since_flag)
                return 0
            # Full backfill (no --since): discover session sources so
            # non-Claude-Code hosts also get message/tool/session backfill
            # (ENH-1945). Codex has no project folder to glob (get_project_folder
            # always returns None for it by design) so it discovers via
            # detect_sessions and is cwd-scoped, ingest-only — no
            # sessions_root, since it has no subagent-transcript mapping
            # (ENH-3422 D4).
            if _backfill_host == "codex":
                codex_handles = detect_sessions(Path.cwd(), "codex")
                if not codex_handles:
                    _cause, reason = explain_no_sessions(Path.cwd(), "codex")
                    print(f"No sessions found for: {Path.cwd()}", file=sys.stderr)
                    print(reason, file=sys.stderr)
                counts = backfill(
                    args.db,
                    handles=codex_handles,
                    config=_config,
                    max_sessions=max_sessions,
                    repo_root=Path.cwd(),
                    sessions_root=None,
                    host=_backfill_host,
                    also_rebuild=getattr(args, "rebuild", False),
                )
            else:
                project_folder = get_project_folder(host=args.host)
                if project_folder is None:
                    _cause, reason = explain_no_sessions(Path.cwd(), host=_backfill_host)
                    print(f"No sessions found for: {Path.cwd()}", file=sys.stderr)
                    print(reason, file=sys.stderr)
                # session_glob already encodes any subdir (D5); matches
                # cli/backfill_worker.py.
                full_jsonl_files: list[Path] | None = (
                    list(project_folder.glob(host_layout_for(_backfill_host).session_glob))
                    if project_folder
                    else None
                )
                counts = backfill(
                    args.db,
                    jsonl_files=full_jsonl_files,
                    config=_config,
                    max_sessions=max_sessions,
                    repo_root=Path.cwd(),
                    sessions_root=project_folder,
                    host=_backfill_host,
                    also_rebuild=getattr(args, "rebuild", False),
                )
            total = sum(counts.values())
            logger.success(
                f"Backfilled {total} rows "
                f"(issues={counts['issues']}, loops={counts['loops']}, "
                f"raw_events={counts.get('raw_events', 0)}, "
                f"snapshots={counts.get('snapshots', 0)}, commits={counts.get('commits', 0)}, "
                f"learning_tests={counts.get('learning_tests', 0)}"
                + (
                    f", tools={counts.get('tools', 0)}, messages={counts.get('messages', 0)}, "
                    f"sessions={counts.get('sessions', 0)}, corrections={counts.get('corrections', 0)}, "
                    f"summaries={counts.get('summaries', 0)})"
                    if getattr(args, "rebuild", False)
                    else ")"
                )
            )
            if getattr(args, "extract_decisions", False):
                _run_extract_decisions(since=None)
            return 0

        if args.command == "rebuild":
            import json as _json

            from little_loops.config.core import resolve_config_path

            config_path = getattr(args, "config", None) or resolve_config_path(Path.cwd())
            config = None
            if config_path is not None:
                try:
                    config = _json.loads(config_path.read_text(encoding="utf-8"))
                except (OSError, _json.JSONDecodeError):
                    config = None

            counts = rebuild(args.db, config=config)
            if args.json:
                print_json(counts)
                return 0
            total = sum(counts.values())
            logger.success(
                f"Rebuilt {total} rows from raw_events "
                f"(tools={counts.get('tools', 0)}, messages={counts.get('messages', 0)}, "
                f"assistant_messages={counts.get('assistant_messages', 0)}, "
                f"skill_events={counts.get('skill_events', 0)}, sessions={counts.get('sessions', 0)}, "
                f"corrections={counts.get('corrections', 0)}, summaries={counts.get('summaries', 0)})"
            )
            return 0

        if args.command == "compact":
            import json as _json

            from little_loops.config.core import resolve_config_path

            config_path = getattr(args, "config", None) or resolve_config_path(Path.cwd())
            config = None
            if config_path is not None:
                try:
                    config = _json.loads(config_path.read_text(encoding="utf-8"))
                except (OSError, _json.JSONDecodeError):
                    config = None

            compact_result = compact(args.db, config=config, and_prune=args.and_prune)
            if args.json:
                print_json(compact_result)
                return 0
            logger.success(
                f"Compacted {compact_result['compacted_rows']} raw event(s) into "
                f"{compact_result['summary_nodes']} retention summary node(s)"
                + (f"; pruned {compact_result['pruned_rows']} row(s)" if args.and_prune else "")
                + (
                    f"; retained {compact_result['retained_rows']} row(s) "
                    f"({', '.join(compact_result.get('retention_reasons', []))})"
                    if args.and_prune and compact_result.get("retained_rows")
                    else ""
                )
            )
            return 0

        if args.command == "skill-stats":
            from little_loops.history_reader import summarize_skills

            stats = summarize_skills(getattr(args, "since", None), db=args.db)
            if args.json:
                print_json(stats)
                return 0
            if not stats:
                print("No skill events.")
                return 0
            for s in stats:
                rate = f"{s['success_rate']:.0%}" if s["success_rate"] is not None else "n/a"
                avg = f"{s['avg_duration_ms']:.0f}ms" if s["avg_duration_ms"] is not None else "n/a"
                print(
                    f"{s['skill_name']}: invocations={s['invocations']} "
                    f"completions={s['completions']} success_rate={rate} avg_duration={avg}"
                )
            return 0

        if args.command == "grep":
            grep_results = ll_grep(
                args.pattern,
                summary_id=args.summary_id,
                limit=args.limit,
                db=args.db,
            )
            if args.json:
                from dataclasses import asdict

                print_json([asdict(r) for r in grep_results])
                return 0
            if not grep_results:
                print("No matches.")
                return 0
            for gr in grep_results:
                node_info = f"  [node {gr.summary_id}/{gr.summary_kind}]" if gr.summary_id else ""
                snippet = gr.content[:120].replace("\n", " ")
                print(f"{gr.ts}  {snippet}{node_info}")
            return 0

        if args.command == "expand":
            messages = ll_expand(args.summary_id, db=args.db)
            if args.json:
                print_json(messages)
                return 0
            if not messages:
                print(f"No messages found for summary node {args.summary_id}.")
                return 0
            for m in messages:
                snippet = (m.get("content") or "")[:120].replace("\n", " ")
                print(f"{m.get('ts', '')}  {snippet}")
            return 0

        if args.command == "describe":
            node = ll_describe(args.node_id, db=args.db)
            if node is None:
                print(f"Summary node {args.node_id} not found.")
                return 1
            if args.json:
                from dataclasses import asdict

                print_json(asdict(node))
                return 0
            print(f"id={node.id}  kind={node.kind}  level={node.level}  session={node.session_id}")
            print(f"ts_start={node.ts_start}  ts_end={node.ts_end}")
            print(f"tokens={node.tokens}  created_at={node.created_at}")
            print(f"content: {node.content[:200]}")
            return 0

        if args.command == "prune":
            import json as _json

            from little_loops.config.core import resolve_config_path

            config = None
            config_path = resolve_config_path(Path.cwd())
            if config_path is not None:
                try:
                    config = _json.loads(config_path.read_text(encoding="utf-8"))
                except (OSError, _json.JSONDecodeError):
                    config = None

            result = prune(args.db, config=config, dry_run=args.dry_run)

            if args.json:
                print_json(result)
                return 0

            if args.dry_run:
                print("DRY RUN — no rows deleted\n")

            if result["gate_unmet"]:
                print("Gates unmet — pruning skipped:")
                for reason in result["gate_unmet"]:
                    print(f"  {reason}")
                print(
                    f"\nDB: {result['db_size_mb']:.1f} MB  |  "
                    f"project age: {result['project_age_days']}d"
                )
                return 0

            if not result["pruned"]:
                print("No pruning configured (raw_event_max_age_days is null).")
                return 0

            deleted = result.get("deleted", {})
            total = sum(deleted.values())
            retained = sum(result.get("retained", {}).values())
            if total == 0 and retained == 0:
                print("Gates met — no eligible rows found.")
            elif total == 0:
                print("Gates met — no rows deleted.")
            else:
                label = "Would delete" if args.dry_run else "Deleted"
                for table, count in deleted.items():
                    print(f"  {table}: {count:,} rows")
                print(f"\n{label} {total:,} rows total.")
            if retained:
                print(
                    f"Retained {retained:,} aged compacted rows to keep usage replayable "
                    f"({', '.join(result.get('retention_reasons', []))})."
                )

            if not args.dry_run and result.get("vacuumed"):
                print("Database VACUUMed.")

            return 0

        if args.command == "recompress":
            result = recompress_raw_events(args.db, batch_size=args.batch)
            if args.json:
                print_json(result)
                return 0
            saved = result["size_before_mb"] - result["size_after_mb"]
            print(
                f"Recompressed {result['recompressed']:,} raw_events row(s).\n"
                f"DB: {result['size_before_mb']:.1f} MB -> "
                f"{result['size_after_mb']:.1f} MB (saved {saved:.1f} MB)"
            )
            return 0

        if args.command == "export":
            import json as _json

            out_path = getattr(args, "output", None)
            out = open(out_path, "w", encoding="utf-8") if out_path else sys.stdout
            count = 0
            try:
                for record in export_history(
                    args.db,
                    tables=getattr(args, "tables", None),
                    since=getattr(args, "since", None),
                    include_messages=getattr(args, "include_messages", False),
                ):
                    out.write(_json.dumps(record, default=str) + "\n")
                    count += 1
            finally:
                if out_path:
                    out.close()
            if out_path:
                logger.success(f"Exported {count:,} records to {out_path}")
            return 0

        if args.command == "record-hook-event":
            # Best-effort by design (ENH-2506): the bash shim must not fail the
            # preceding hook's exit code just because telemetry couldn't be
            # written. record_hook_event() already swallows DB errors; this
            # branch additionally swallows any argument-shape surprise.
            try:
                record_hook_event(
                    args.db,
                    session_id=args.session_id,
                    event_name=args.event_name,
                    matcher=args.matcher,
                    script=args.script,
                    exit_code=args.exit_code,
                    duration_ms=args.duration_ms,
                    stderr_preview=args.stderr_preview,
                )
            except Exception:
                logger.warning("record-hook-event: failed to write hook_events row")
            return 0

        return 1
