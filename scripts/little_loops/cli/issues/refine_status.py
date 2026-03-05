"""ll-issues refine-status: Refinement depth table for active issues."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING

from little_loops.cli.output import terminal_width

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo

# Minimum width for the title column (before terminal-width trimming)
_MIN_TITLE_WIDTH = 20
# Fixed column widths for non-title columns
_ID_WIDTH = 8  # "BUG-525 "
_PRI_WIDTH = 4  # "P2  "
_SCORE_WIDTH = 7  # "ready" col
_CONF_WIDTH = 10  # "confidence" col
_TOTAL_WIDTH = 5  # "total"
# Width of each command column: longest alias is "tradeoff" = 8 chars
_CMD_WIDTH = 8
_NORM_WIDTH = 4  # "norm" / "✓" / "✗"
_FMT_WIDTH = 4  # "fmt" / "✓" / "✗"
_SOURCE_WIDTH = 7  # "source" header / "capture" value max

# Commands that are excluded from dynamic columns (shown as static columns instead)
_SOURCE_CMDS = {
    "/ll:capture-issue",
    "/ll:scan-codebase",
    "/ll:audit-architecture",
    "/ll:format-issue",
}

# Canonical workflow order for command columns
_CANONICAL_CMD_ORDER = [
    "/ll:capture-issue",
    "/ll:scan-codebase",
    "/ll:audit-architecture",
    "/ll:format-issue",
    "/ll:verify-issues",
    "/ll:refine-issue",
    "/ll:tradeoff-review-issues",
    "/ll:map-dependencies",
]

_CMD_ALIASES: dict[str, str] = {
    "/ll:capture-issue": "capture",
    "/ll:scan-codebase": "scan",
    "/ll:audit-architecture": "audit",
    "/ll:format-issue": "format",
    "/ll:verify-issues": "verify",
    "/ll:refine-issue": "refine",
    "/ll:tradeoff-review-issues": "tradeoff",
    "/ll:map-dependencies": "map",
}

# Static column metadata: name -> (fixed_width, header_text, right_justify)
# width=0 is a sentinel meaning the column width is computed dynamically (title only)
_STATIC_COLUMN_SPECS: dict[str, tuple[int, str, bool]] = {
    "id": (_ID_WIDTH, "ID", False),
    "priority": (_PRI_WIDTH, "Pri", False),
    "title": (0, "Title", False),
    "source": (_SOURCE_WIDTH, "source", False),
    "norm": (_NORM_WIDTH, "norm", False),
    "fmt": (_FMT_WIDTH, "fmt", False),
    "ready": (_SCORE_WIDTH, "ready", True),
    "confidence": (_CONF_WIDTH, "confidence", True),
    "total": (_TOTAL_WIDTH, "total", True),
}

# Default column order when no config is provided
_DEFAULT_STATIC_COLUMNS: list[str] = [
    "id",
    "priority",
    "title",
    "source",
    "norm",
    "fmt",
    "ready",
    "confidence",
    "total",
]

# Columns that belong after the dynamic command block (all others go before)
_POST_CMD_STATIC: frozenset[str] = frozenset(["ready", "confidence", "total"])


def _cmd_label(cmd: str) -> str:
    """Return display label for a command column header."""
    if cmd in _CMD_ALIASES:
        return _CMD_ALIASES[cmd]
    # Fallback: strip /ll: prefix and truncate
    short = cmd[4:] if cmd.startswith("/ll:") else cmd
    return _truncate(short, _CMD_WIDTH)


def _source_label(discovered_by: str | None) -> str:
    """Return short display label for an issue's origin source."""
    if not discovered_by:
        return "\u2014"  # em-dash
    if discovered_by in _CMD_ALIASES:
        return _CMD_ALIASES[discovered_by]
    # Non-/ll: values like "github_sync" — truncate to fit
    return _truncate(discovered_by, _SOURCE_WIDTH)


def _truncate(text: str, width: int) -> str:
    """Truncate text to width, replacing last char with ellipsis if needed."""
    if len(text) <= width:
        return text
    return text[: width - 1].rstrip() + "\u2026"


def _col(text: str, width: int) -> str:
    """Left-justify text in a fixed-width column."""
    return text.ljust(width)[:width]


def _rcol(text: str, width: int) -> str:
    """Right-justify text in a fixed-width column."""
    return text.rjust(width)[:width]


def cmd_refine_status(config: BRConfig, args: argparse.Namespace) -> int:
    """Render a refinement depth table for all active issues.

    Each column represents a distinct /ll:* command found across Session Log
    sections. Issues are sorted descending by refinement depth (Total), then
    ascending by priority as a tiebreaker.

    Args:
        config: Project configuration.
        args: Parsed arguments with optional .type and .format attributes.

    Returns:
        Exit code (0 = success).
    """
    from little_loops.issue_parser import find_issues, is_formatted, is_normalized

    type_prefixes = {args.type} if getattr(args, "type", None) else None
    issues = find_issues(config, type_prefixes=type_prefixes)

    if not issues:
        print("No active issues found.")
        return 0

    # Derive dynamic column set: all distinct commands across all issues
    seen: dict[str, None] = {}
    for issue in issues:
        for cmd in issue.session_commands:
            seen[cmd] = None

    def _canonical_sort_key(cmd: str) -> tuple[int, str]:
        try:
            return (_CANONICAL_CMD_ORDER.index(cmd), cmd)
        except ValueError:
            return (len(_CANONICAL_CMD_ORDER), cmd)

    all_cmds: list[str] = [
        cmd for cmd in sorted(seen.keys(), key=_canonical_sort_key) if cmd not in _SOURCE_CMDS
    ]

    # Sort issues: descending by total commands touched, then ascending priority
    def _sort_key(issue: IssueInfo) -> tuple[int, int]:
        return (-len(issue.session_commands), issue.priority_int)

    sorted_issues = sorted(issues, key=_sort_key)

    fmt = getattr(args, "format", "table")

    if fmt == "json":
        for issue in sorted_issues:
            record = {
                "id": issue.issue_id,
                "priority": issue.priority,
                "title": issue.title,
                "source": issue.discovered_by,
                "commands": issue.session_commands,
                "confidence_score": issue.confidence_score,
                "outcome_confidence": issue.outcome_confidence,
                "total": len(issue.session_commands),
                "normalized": is_normalized(issue.path.name),
                "formatted": is_formatted(issue.path),
                "refine_count": issue.session_command_counts.get("/ll:refine-issue", 0),
            }
            print(json.dumps(record))
        return 0

    # --- Table rendering ---
    term_cols = terminal_width()

    # Determine active static columns from config (empty list = use defaults)
    config_cols = config.refine_status.columns
    active_static = list(config_cols) if config_cols else list(_DEFAULT_STATIC_COLUMNS)

    # Split active columns: pre-cmd (before dynamic command block) and post-cmd (after)
    pre_cmd = [c for c in active_static if c not in _POST_CMD_STATIC]
    post_cmd = [c for c in active_static if c in _POST_CMD_STATIC]

    # Compute title column width based on active columns and terminal size
    has_title = "title" in pre_cmd
    title_w = _MIN_TITLE_WIDTH
    if has_title:
        n_parts = len(pre_cmd) + len(all_cmds) + len(post_cmd)
        non_title_sum = (
            sum(
                _STATIC_COLUMN_SPECS[c][0] if c in _STATIC_COLUMN_SPECS else _CMD_WIDTH
                for c in pre_cmd
                if c != "title"
            )
            + len(all_cmds) * _CMD_WIDTH
            + sum(
                _STATIC_COLUMN_SPECS[c][0] if c in _STATIC_COLUMN_SPECS else _CMD_WIDTH
                for c in post_cmd
            )
        )
        title_w = max(_MIN_TITLE_WIDTH, term_cols - non_title_sum - 2 * (n_parts - 1))

    def _get_col_display_width(col: str) -> int:
        if col == "title":
            return title_w
        if col in _STATIC_COLUMN_SPECS:
            return _STATIC_COLUMN_SPECS[col][0]
        return _CMD_WIDTH

    def _render_cell(col: str, value: str) -> str:
        w = _get_col_display_width(col)
        if col in _STATIC_COLUMN_SPECS:
            rjust = _STATIC_COLUMN_SPECS[col][2]
            return _rcol(value, w) if rjust else _col(value, w)
        return _col(value, w)

    def _header_cell(col: str) -> str:
        if col in _STATIC_COLUMN_SPECS:
            hdr = _STATIC_COLUMN_SPECS[col][1]
        else:
            hdr = _truncate(col, _get_col_display_width(col))
        return _render_cell(col, hdr)

    def _cell_value(col: str, issue: IssueInfo) -> str:
        if col == "id":
            return issue.issue_id
        if col == "priority":
            return issue.priority
        if col == "title":
            return _truncate(issue.title, title_w)
        if col == "source":
            return _source_label(issue.discovered_by)
        if col == "norm":
            return "\u2713" if is_normalized(issue.path.name) else "\u2717"
        if col == "fmt":
            return "\u2713" if is_formatted(issue.path) else "\u2717"
        if col == "ready":
            return str(issue.confidence_score) if issue.confidence_score is not None else "\u2014"
        if col == "confidence":
            return (
                str(issue.outcome_confidence) if issue.outcome_confidence is not None else "\u2014"
            )
        if col == "total":
            return str(len(issue.session_commands))
        return "\u2014"  # unknown column: em-dash

    def _build_row(issue: IssueInfo | None) -> str:
        parts: list[str] = []
        cmd_set = set(issue.session_commands) if issue is not None else set()

        for c in pre_cmd:
            if issue is None:
                parts.append(_header_cell(c))
            else:
                parts.append(_render_cell(c, _cell_value(c, issue)))

        for c in all_cmds:
            if issue is None:
                parts.append(_col(_cmd_label(c), _CMD_WIDTH))
            else:
                if c == "/ll:refine-issue":
                    cell = str(issue.session_command_counts.get(c, 0))
                else:
                    cell = "\u2713" if c in cmd_set else "\u2014"
                parts.append(_col(cell, _CMD_WIDTH))

        for c in post_cmd:
            if issue is None:
                parts.append(_header_cell(c))
            else:
                parts.append(_render_cell(c, _cell_value(c, issue)))

        return "  ".join(parts)

    header = _build_row(None)
    separator = "-" * len(header)

    rows: list[str] = [header, separator]

    for issue in sorted_issues:
        rows.append(_build_row(issue))

    print("\n".join(rows))

    issue_word = "issue" if len(sorted_issues) == 1 else "issues"
    scored = sum(1 for i in sorted_issues if i.confidence_score is not None)
    print(f"\n{len(sorted_issues)} {issue_word}  ({scored} scored)")

    if not getattr(args, "no_key", False):
        _print_key(all_cmds)

    return 0


def _print_key(all_cmds: list[str]) -> None:
    """Print a legend mapping column headers to their full command names."""
    print("\nKey:")
    print(f"  {'source':<12} Origin command/workflow that created the issue")
    print(f"  {'norm':<12} Filename follows naming convention (P[0-5]-TYPE-NNN-desc.md)")
    print(f"  {'fmt':<12} Issue has all required sections per type template (structural check)")
    for cmd in all_cmds:
        label = _cmd_label(cmd)
        if cmd == "/ll:refine-issue":
            print(f"  {label:<12} Times /ll:refine-issue was run")
        else:
            print(f"  {label:<12} {cmd}")
    print(f"  {'ready':<12} Readiness score (0\u2013100)")
    print(f"  {'confidence':<12} Outcome confidence score (0\u2013100)")
    print(f"  {'total':<12} Number of /ll:* skills applied")
