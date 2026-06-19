"""ll-history-context: render a Historical Context block for an issue.

Queries .ll/history.db for user corrections and FTS5 matches relevant to an
issue ID and prints a ready-to-inject ``## Historical Context`` markdown block.
Returns empty output when the DB is missing, has no matches, or all rows are
stale.

Pass ``--project`` instead of an issue ID to print the project-wide context
digest that the session-start hook would inject (inspection / config-tuning
dry-run, ENH-1907).

Usage:
    ll-history-context <issue_id> [--file <path>] [--db <path>]
    ll-history-context --project [--db <path>]
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.config.core import resolve_config_path
from little_loops.history_reader import (
    STALE_DAYS_DEFAULT,
    SearchResult,
    UserCorrection,
    find_user_corrections,
    issue_effort,
    project_digest,
    recent_file_events,
    render_project_context,
    search,
)
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context, connect

logger = logging.getLogger(__name__)

_MAX_ROWS = 5


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _render_learning_test_section(
    targets: list[str],
    *,
    stale_after_days: int = 30,
    base_dir: Path | None = None,
) -> str | None:
    """Build a ## Learning Test Evidence markdown table, or None if no records exist."""
    from little_loops.learning_tests import check_learning_test
    from little_loops.learning_tests.gate import is_record_stale

    rows: list[str] = []
    for target in targets:
        record = check_learning_test(target, base_dir=base_dir)
        if record is None:
            continue
        effective_status = "stale" if is_record_stale(record, stale_after_days) else record.status
        passes = sum(1 for a in record.assertions if a.result == "pass")
        fails = sum(1 for a in record.assertions if a.result == "fail")
        untested = sum(1 for a in record.assertions if a.result == "untested")
        rows.append(
            f"| {target} | {effective_status} | {record.date} | {passes}/{fails}/{untested} |"
        )

    if not rows:
        return None

    lines = [
        "## Learning Test Evidence",
        "",
        "| Target | Status | Date | Pass/Fail/Untested |",
        "|--------|--------|------|--------------------|",
        *rows,
    ]
    return "\n".join(lines)


def _get_issue_lt_targets(issue_id: str, cfg: object) -> list[str]:
    """Read learning_tests_required from the issue file frontmatter."""
    from little_loops.cli.issues.show import _resolve_issue_id

    issue_path = _resolve_issue_id(cfg, issue_id)  # type: ignore[arg-type]
    if issue_path is None:
        return []
    try:
        content = issue_path.read_text(encoding="utf-8")
    except OSError:
        return []
    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return []
    try:
        fm = yaml.safe_load(fm_match.group(1)) or {}
    except yaml.YAMLError:
        return []
    raw = fm.get("learning_tests_required")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw]
    if isinstance(raw, str):
        return [raw]
    return []


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ll-history-context",
        description="Render a ## Historical Context block for an issue from .ll/history.db",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ENH-1708                        # Corrections matching the issue ID
  %(prog)s ENH-1708 --file src/foo.py      # Also include recent file events
  %(prog)s ENH-1708 --db custom/history.db # Use a non-default database
  %(prog)s --project                        # Print project-wide context digest
""",
    )
    parser.add_argument(
        "issue_id",
        metavar="ISSUE_ID",
        nargs="?",
        default=None,
        help="Issue ID to query (e.g. ENH-1708). Mutually exclusive with --project.",
    )
    parser.add_argument(
        "--project",
        action="store_true",
        default=False,
        help="Print the project-wide context digest (dry-run of session-start injection).",
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        default=None,
        help="Also include recent file events for this path",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        metavar="PATH",
        help="Path to the session database (default: .ll/history.db)",
    )
    parser.add_argument(
        "--effort",
        action="store_true",
        default=False,
        help="Include effort/velocity context (session count and cycle time)",
    )
    parser.add_argument(
        "--for-skill",
        type=str,
        default=None,
        metavar="NAME",
        help="Exit 0 with no output if NAME is not in history.planning_skills.",
    )
    return parser


def main_history_context() -> int:
    """Entry point for ll-history-context command.

    Returns:
        0 on success (including empty output when no matches or DB absent), 1 on argument error.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-history-context", sys.argv[1:]):
        configure_output()
        logger = Logger(use_color=use_color_enabled())  # noqa: F841

        parser = _build_parser()
        args = parser.parse_args()

        # Mutual-exclusion guard: require exactly one of issue_id or --project.
        if args.project and args.issue_id:
            parser.error("--project and ISSUE_ID are mutually exclusive")
        if not args.project and not args.issue_id:
            parser.error("one of ISSUE_ID or --project is required")

        # --project: print the project-wide digest dry-run and exit.
        if args.project:
            from little_loops.config.features import HistoryConfig

            cwd = Path.cwd()
            config_path = resolve_config_path(cwd)
            if config_path is not None:
                import json

                try:
                    merged = json.loads(config_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    merged = {}
            else:
                merged = {}

            _hist = HistoryConfig.from_dict(merged.get("history", {}))
            _sd = _hist.session_digest
            _sections = _sd.sections if _sd.sections else None
            digest = project_digest(args.db, days=_sd.days, sections=_sections)
            block = render_project_context(digest, char_cap=_sd.char_cap, days=_sd.days)
            if block:
                print(block)
            return 0

        # --for-skill guard: exit 0 with no output if skill is not in history.planning_skills.
        if args.for_skill is not None:
            from little_loops.config import BRConfig

            cfg = BRConfig(Path.cwd())
            if args.for_skill not in cfg.history.planning_skills:
                return 0

        # --effort: print effort/velocity context and exit.
        if args.effort:
            from little_loops.config import BRConfig

            cfg = BRConfig(Path.cwd())
            fields = cfg.history.effort_fields
            effort = issue_effort(args.issue_id, db=args.db)
            if effort is None:
                return 0
            valid_fields = {"session_count", "cycle_time_days"}
            print("## Effort Context")
            print()
            for f in fields:
                if f not in valid_fields:
                    logger.warning(f"history_context: unknown effort field {f!r} — skipping")
                    continue
                val = effort.get(f)
                if val is None:
                    print(f"- {f}: n/a")
                else:
                    print(f"- {f}: {val}")
            return 0

        cutoff = (datetime.now(UTC) - timedelta(days=STALE_DAYS_DEFAULT)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        corrections: list[UserCorrection] = find_user_corrections(
            topic=args.issue_id, limit=20, db=args.db
        )

        search_results: list[SearchResult] = search(
            query=args.issue_id, kind="correction", limit=20, db=args.db
        )
        fresh_search = [r for r in search_results if r.ts >= cutoff]

        file_contents: list[str] = []
        if args.file:
            for fe in recent_file_events(path=args.file, limit=5, db=args.db):
                file_contents.append(f"file:{fe.path}:{fe.op}")

        seen: set[str] = set()
        rows: list[str] = []

        for uc in corrections:
            h = _content_hash(uc.content)
            if h not in seen:
                seen.add(h)
                rows.append(uc.content)

        for sr in fresh_search:
            h = _content_hash(sr.content)
            if h not in seen:
                seen.add(h)
                rows.append(sr.content)

        for fc in file_contents:
            h = _content_hash(fc)
            if h not in seen:
                seen.add(h)
                rows.append(fc)

        rows = rows[:_MAX_ROWS]

        if not rows:
            # Fallback: query issue_snapshots when no corrections/search rows found.
            try:
                conn = connect(args.db)
                try:
                    snap = conn.execute(
                        "SELECT title, body FROM issue_snapshots"
                        " WHERE issue_id = ? ORDER BY ts DESC LIMIT 1",
                        (args.issue_id,),
                    ).fetchone()
                finally:
                    conn.close()
                if snap is not None:
                    body_text = (snap["body"] or "").strip()
                    if body_text:
                        rows.append(body_text[:512])
            except Exception:
                pass

        # Build Learning Test Evidence section if feature is enabled.
        lt_section: str | None = None
        try:
            from little_loops.config import BRConfig

            cfg = BRConfig(Path.cwd())
            if cfg.learning_tests.enabled:
                targets = _get_issue_lt_targets(args.issue_id, cfg)
                if targets:
                    lt_dir = Path.cwd() / ".ll" / "learning-tests"
                    lt_section = _render_learning_test_section(
                        targets,
                        stale_after_days=cfg.learning_tests.stale_after_days,
                        base_dir=lt_dir,
                    )
        except Exception:
            pass

        # Build Prior Work (condensed) section if compaction is enabled (ENH-2231).
        prior_work_section: str | None = None
        _PRIOR_WORK_SECTION_BUDGET = 1000
        _PRIOR_WORK_NODE_CHAR_CAP = 400
        try:
            from little_loops.config import BRConfig
            from little_loops.history_reader import condensed_nodes_for_issue

            _cfg = BRConfig(Path.cwd())
            if _cfg.history.compaction.enabled:
                _nodes = condensed_nodes_for_issue(
                    args.issue_id,
                    node_char_cap=_PRIOR_WORK_NODE_CHAR_CAP,
                    db=args.db,
                )
                if _nodes:
                    section_lines: list[str] = ["## Prior Work (condensed)", ""]
                    budget = _PRIOR_WORK_SECTION_BUDGET
                    for node in _nodes:
                        text = (node.content or "").strip()
                        provenance = (
                            f"*(session: {node.session_id or 'unknown'},"
                            f" ts_end: {node.ts_end or 'unknown'})*"
                        )
                        entry = f"{text}\n\n{provenance}"
                        if budget <= 0:
                            break
                        section_lines.append(entry)
                        section_lines.append("")
                        budget -= len(entry)
                    if len(section_lines) > 2:
                        prior_work_section = "\n".join(section_lines).rstrip()
        except Exception:
            pass

        if not rows and lt_section is None and prior_work_section is None:
            return 0

        if rows:
            print("## Historical Context")
            print()
            for row in rows:
                print(f"- {row}")

        if lt_section is not None:
            if rows:
                print()
            print(lt_section)

        if prior_work_section is not None:
            if rows or lt_section is not None:
                print()
            print(prior_work_section)

        return 0
