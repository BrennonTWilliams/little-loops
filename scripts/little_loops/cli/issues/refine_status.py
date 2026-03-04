"""ll-issues refine-status: Refinement depth table for active issues."""

from __future__ import annotations

import argparse
import json
import shutil
from typing import TYPE_CHECKING

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
    term_cols = shutil.get_terminal_size().columns

    # Compute how much space is consumed by fixed columns + command columns.
    # Layout: ID | Pri | Title | source | norm | fmt | [cmd cols...] | ready | confidence | total
    # _row uses "  ".join(parts) — 2-char separator between each part.
    # Each "+2" below accounts for the 2-char separator that follows that column.
    # The final "- 2" accounts for the separator between Title and the next column (source).
    fixed_width = (
        _ID_WIDTH
        + 2
        + _PRI_WIDTH
        + 2
        + _SOURCE_WIDTH
        + 2  # source (before norm)
        + _NORM_WIDTH
        + 2  # norm
        + _FMT_WIDTH
        + 2  # fmt
        + _SCORE_WIDTH
        + 2  # ready
        + _CONF_WIDTH
        + 2  # confidence
        + _TOTAL_WIDTH
    )
    cmd_cols_width = len(all_cmds) * (_CMD_WIDTH + 2)
    title_width = max(_MIN_TITLE_WIDTH, term_cols - fixed_width - cmd_cols_width - 2)

    def _row(
        issue_id: str,
        pri: str,
        title: str,
        source: str,
        norm: str,
        fmt: str,
        cmd_cells: list[str],
        ready: str,
        conf: str,
        total: str,
    ) -> str:
        parts = [
            _col(issue_id, _ID_WIDTH),
            _col(pri, _PRI_WIDTH),
            _col(title, title_width),
            _col(source, _SOURCE_WIDTH),
            _col(norm, _NORM_WIDTH),
            _col(fmt, _FMT_WIDTH),
        ]
        for cell in cmd_cells:
            parts.append(_col(cell, _CMD_WIDTH))
        parts.append(_rcol(ready, _SCORE_WIDTH))
        parts.append(_rcol(conf, _CONF_WIDTH))
        parts.append(_rcol(total, _TOTAL_WIDTH))
        return "  ".join(parts)

    # Header row
    cmd_headers = [_col(_cmd_label(c), _CMD_WIDTH) for c in all_cmds]
    header = _row(
        "ID", "Pri", "Title", "source", "norm", "fmt", cmd_headers, "ready", "confidence", "total"
    )
    separator = "-" * len(header)

    rows: list[str] = [header, separator]

    for issue in sorted_issues:
        cmd_set = set(issue.session_commands)
        cmd_cells = []
        for c in all_cmds:
            if c == "/ll:refine-issue":
                cmd_cells.append(str(issue.session_command_counts.get(c, 0)))
            else:
                cmd_cells.append("\u2713" if c in cmd_set else "\u2014")
        source_cell = _source_label(issue.discovered_by)
        norm_cell = "\u2713" if is_normalized(issue.path.name) else "\u2717"
        fmt_cell = "\u2713" if is_formatted(issue.path) else "\u2717"
        ready = str(issue.confidence_score) if issue.confidence_score is not None else "\u2014"
        out_conf = (
            str(issue.outcome_confidence) if issue.outcome_confidence is not None else "\u2014"
        )
        total = str(len(issue.session_commands))
        rows.append(
            _row(
                issue.issue_id,
                issue.priority,
                _truncate(issue.title, title_width),
                source_cell,
                norm_cell,
                fmt_cell,
                cmd_cells,
                ready,
                out_conf,
                total,
            )
        )

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
