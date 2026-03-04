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
_SCORE_WIDTH = 7  # " Ready  " / "OutConf "
_TOTAL_WIDTH = 6  # "Total "
# Width of each command column: strip "/ll:" prefix and display short name
_CMD_WIDTH = 9  # enough for most command short names
_NORM_WIDTH = 4  # "Norm" / "✓" / "✗"


def _short_name(cmd: str) -> str:
    """Strip /ll: prefix from a command name for compact column header."""
    if cmd.startswith("/ll:"):
        return cmd[4:]
    return cmd


def _truncate(text: str, width: int) -> str:
    """Truncate text to width, replacing last char with ellipsis if needed."""
    if len(text) <= width:
        return text
    return text[: width - 1] + "\u2026"


def _col(text: str, width: int) -> str:
    """Left-justify text in a fixed-width column."""
    return text.ljust(width)[:width]


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
    from little_loops.issue_parser import find_issues, is_normalized

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
    all_cmds: list[str] = list(seen.keys())

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
                "commands": issue.session_commands,
                "confidence_score": issue.confidence_score,
                "outcome_confidence": issue.outcome_confidence,
                "total": len(issue.session_commands),
                "normalized": is_normalized(issue.path.name),
            }
            print(json.dumps(record))
        return 0

    # --- Table rendering ---
    term_cols = shutil.get_terminal_size().columns

    # Compute how much space is consumed by fixed columns + command columns
    # Layout: ID | Pri | Title | [cmd cols...] | Norm | Ready | OutConf | Total
    fixed_width = (
        _ID_WIDTH + 1
        + _PRI_WIDTH + 1
        + _NORM_WIDTH + 1  # Norm
        + _SCORE_WIDTH + 1  # Ready
        + _SCORE_WIDTH + 1  # OutConf
        + _TOTAL_WIDTH
    )
    cmd_cols_width = len(all_cmds) * (_CMD_WIDTH + 1)
    title_width = max(_MIN_TITLE_WIDTH, term_cols - fixed_width - cmd_cols_width - 2)

    def _row(
        issue_id: str,
        pri: str,
        title: str,
        cmd_cells: list[str],
        norm: str,
        ready: str,
        out_conf: str,
        total: str,
    ) -> str:
        parts = [
            _col(issue_id, _ID_WIDTH),
            _col(pri, _PRI_WIDTH),
            _col(title, title_width),
        ]
        for cell in cmd_cells:
            parts.append(_col(cell, _CMD_WIDTH))
        parts.append(_col(norm, _NORM_WIDTH))
        parts.append(_col(ready, _SCORE_WIDTH))
        parts.append(_col(out_conf, _SCORE_WIDTH))
        parts.append(_col(total, _TOTAL_WIDTH))
        return "  ".join(parts)

    # Header row
    cmd_headers = [_col(_truncate(_short_name(c), _CMD_WIDTH), _CMD_WIDTH) for c in all_cmds]
    header = _row("ID", "Pri", "Title", cmd_headers, "Norm", "Ready", "OutConf", "Total")
    separator = "-" * len(header)

    rows: list[str] = [header, separator]

    for issue in sorted_issues:
        cmd_set = set(issue.session_commands)
        cmd_cells = ["\u2713" if c in cmd_set else "\u2014" for c in all_cmds]
        norm_cell = "\u2713" if is_normalized(issue.path.name) else "\u2717"
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
                cmd_cells,
                norm_cell,
                ready,
                out_conf,
                total,
            )
        )

    print("\n".join(rows))

    if not getattr(args, "no_key", False):
        _print_key(all_cmds)

    return 0


def _print_key(all_cmds: list[str]) -> None:
    """Print a legend mapping truncated column headers to full names."""
    print("\nKey:")
    for cmd in all_cmds:
        short = _truncate(_short_name(cmd), _CMD_WIDTH)
        print(f"  {short:<12} {cmd}")
    print(f"  {'Norm':<12} Filename matches naming convention (P[0-5]-TYPE-NNN-desc.md)")
    print(f"  {'Ready':<12} Readiness score (0\u2013100)")
    print(f"  {'OutConf':<12} Outcome confidence score (0\u2013100)")
    print(f"  {'Total':<12} Count of command columns with \u2713")


