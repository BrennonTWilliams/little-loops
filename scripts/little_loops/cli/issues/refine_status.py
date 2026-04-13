"""ll-issues refine-status: Refinement depth table for active issues."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING

from little_loops.cli.output import PRIORITY_COLOR, TYPE_COLOR, colorize, print_json, terminal_width

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo

# Minimum width for the title column (before terminal-width trimming)
_MIN_TITLE_WIDTH = 20
# Fixed column widths for non-title columns
_ID_WIDTH = 8  # "BUG-525 "
_PRI_WIDTH = 4  # "P2  "
_SIZE_WIDTH = 10  # "Very Large" (longest valid value)
_SCORE_WIDTH = 5  # "ready" col
_CONF_WIDTH = 5  # "conf" col
_TOTAL_WIDTH = 5  # "total"
# Width of each command column
_CMD_WIDTH = 6
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
    "size": (_SIZE_WIDTH, "size", False),
    "title": (0, "Title", False),
    "source": (_SOURCE_WIDTH, "source", False),
    "norm": (_NORM_WIDTH, "norm", False),
    "fmt": (_FMT_WIDTH, "fmt", False),
    "ready": (_SCORE_WIDTH, "ready", True),
    "confidence": (_CONF_WIDTH, "conf", True),
    "score_complexity": (_SCORE_WIDTH, "cmplx", True),
    "score_test_coverage": (_SCORE_WIDTH, "tcov", True),
    "score_ambiguity": (_SCORE_WIDTH, "ambig", True),
    "score_change_surface": (_SCORE_WIDTH, "chsrf", True),
    "total": (_TOTAL_WIDTH, "total", True),
}

# Default column order when no config is provided
_DEFAULT_STATIC_COLUMNS: list[str] = [
    "id",
    "priority",
    "size",
    "title",
    "source",
    "norm",
    "fmt",
    "ready",
    "confidence",
    "score_complexity",
    "score_test_coverage",
    "score_ambiguity",
    "score_change_surface",
    "total",
]

# Columns that belong after the dynamic command block (all others go before)
_POST_CMD_STATIC: frozenset[str] = frozenset(
    [
        "ready",
        "confidence",
        "score_complexity",
        "score_test_coverage",
        "score_ambiguity",
        "score_change_surface",
        "total",
    ]
)

# Columns that are always pinned — never elided regardless of terminal width
_PINNED_COLUMNS: frozenset[str] = frozenset(["id", "priority", "title"])

# Default column elision order: columns dropped first when table overflows.
# Command columns not listed here are dropped rightmost-first after this list
# is exhausted.
_DEFAULT_ELIDE_ORDER: list[str] = [
    "source",
    "norm",
    "fmt",
    "size",
    "score_change_surface",
    "score_ambiguity",
    "score_test_coverage",
    "score_complexity",
    "confidence",
    "ready",
    "total",
]


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


def _apply_cell_color(col: str, padded: str, plain: str) -> str:
    """Colorize the visible content of a padded cell, preserving surrounding whitespace."""
    if col == "id":
        issue_type = plain.split("-")[0]
        code = TYPE_COLOR.get(issue_type, "")
    elif col == "priority":
        code = PRIORITY_COLOR.get(plain, "")
    elif col in ("norm", "fmt"):
        if plain == "\u2713":  # ✓
            code = "32"  # green
        elif plain == "\u2717":  # ✗
            code = "31"  # red
        else:
            code = ""
    else:
        return padded

    if not code:
        return padded

    # Preserve leading spaces (rjust cells) and trailing spaces (ljust cells)
    lstripped = padded.lstrip()
    leading = padded[: len(padded) - len(lstripped)]
    content = lstripped.rstrip()
    trailing = lstripped[len(content) :]
    return leading + colorize(content, code) + trailing


def _compute_min_total_width(
    pre_cmd: list[str], all_cmds: list[str], post_cmd: list[str], id_width: int
) -> int:
    """Compute the minimum table width with the title column at _MIN_TITLE_WIDTH."""
    n_parts = len(pre_cmd) + len(all_cmds) + len(post_cmd)
    if n_parts == 0:
        return 0
    col_sum = 0
    for c in pre_cmd:
        if c == "title":
            col_sum += _MIN_TITLE_WIDTH
        elif c == "id":
            col_sum += id_width
        elif c in _STATIC_COLUMN_SPECS:
            col_sum += _STATIC_COLUMN_SPECS[c][0]
        else:
            col_sum += _CMD_WIDTH
    col_sum += len(all_cmds) * _CMD_WIDTH
    for c in post_cmd:
        col_sum += _STATIC_COLUMN_SPECS[c][0] if c in _STATIC_COLUMN_SPECS else _CMD_WIDTH
    return col_sum + 2 * (n_parts - 1)


def _elide_columns(
    pre_cmd: list[str],
    all_cmds: list[str],
    post_cmd: list[str],
    term_cols: int,
    id_width: int,
    elide_order: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Drop columns until the table fits within term_cols.

    Columns in *elide_order* are dropped first (in listed order).  Pinned
    columns (id, priority, title) are silently skipped even if they appear in
    the list.  After the list is exhausted, remaining command columns are
    dropped rightmost-first.
    """
    pre = list(pre_cmd)
    cmds = list(all_cmds)
    post = list(post_cmd)

    def fits() -> bool:
        return _compute_min_total_width(pre, cmds, post, id_width) <= term_cols

    if fits():
        return pre, cmds, post

    for col in elide_order:
        if fits():
            break
        if col in _PINNED_COLUMNS:
            continue
        if col in pre:
            pre.remove(col)
        elif col in post:
            post.remove(col)
        elif col in cmds:
            cmds.remove(col)

    # Drop remaining command columns rightmost-first
    while not fits() and cmds:
        cmds.pop()

    return pre, cmds, post


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

    issue_id_filter = getattr(args, "issue_id", None)
    type_prefixes = {args.type} if (not issue_id_filter and getattr(args, "type", None)) else None
    issues = find_issues(config, type_prefixes=type_prefixes)

    if issue_id_filter:
        issues = [i for i in issues if i.issue_id == issue_id_filter]

    if not issues:
        if issue_id_filter:
            print(f"Error: issue '{issue_id_filter}' not found in active issues.")
            return 1
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

    # Dynamic ID column width: size to the longest issue_id present, minimum 8
    id_width = max((len(issue.issue_id) for issue in sorted_issues), default=7) + 1

    use_json_array = getattr(args, "json", False)
    fmt = getattr(args, "format", "table")

    if use_json_array:
        records = [
            {
                "id": issue.issue_id,
                "priority": issue.priority,
                "title": issue.title,
                "source": issue.discovered_by,
                "commands": issue.session_commands,
                "confidence_score": issue.confidence_score,
                "outcome_confidence": issue.outcome_confidence,
                "score_complexity": issue.score_complexity,
                "score_test_coverage": issue.score_test_coverage,
                "score_ambiguity": issue.score_ambiguity,
                "score_change_surface": issue.score_change_surface,
                "size": issue.size,
                "total": len(issue.session_commands),
                "normalized": is_normalized(issue.path.name),
                "formatted": is_formatted(issue.path),
                "refine_count": issue.session_command_counts.get("/ll:refine-issue", 0),
            }
            for issue in sorted_issues
        ]
        print_json(records[0] if issue_id_filter else records)
        return 0

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
                "score_complexity": issue.score_complexity,
                "score_test_coverage": issue.score_test_coverage,
                "score_ambiguity": issue.score_ambiguity,
                "score_change_surface": issue.score_change_surface,
                "size": issue.size,
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

    # Elide columns when the table would overflow the terminal.
    # JSON modes exit early above, so this path is table-only.
    elide_order = config.refine_status.elide_order or _DEFAULT_ELIDE_ORDER
    pre_cmd, all_cmds, post_cmd = _elide_columns(
        pre_cmd, all_cmds, post_cmd, term_cols, id_width, elide_order
    )

    # Compute title column width based on active columns and terminal size
    has_title = "title" in pre_cmd
    title_w = _MIN_TITLE_WIDTH
    if has_title:
        n_parts = len(pre_cmd) + len(all_cmds) + len(post_cmd)
        non_title_sum = (
            sum(
                (id_width if c == "id" else _STATIC_COLUMN_SPECS[c][0])
                if c in _STATIC_COLUMN_SPECS
                else _CMD_WIDTH
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
        if col == "id":
            return id_width
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
        if col == "size":
            return issue.size if issue.size else "\u2014"
        if col == "confidence":
            return (
                str(issue.outcome_confidence) if issue.outcome_confidence is not None else "\u2014"
            )
        if col == "score_complexity":
            return str(issue.score_complexity) if issue.score_complexity is not None else "\u2014"
        if col == "score_test_coverage":
            return (
                str(issue.score_test_coverage)
                if issue.score_test_coverage is not None
                else "\u2014"
            )
        if col == "score_ambiguity":
            return str(issue.score_ambiguity) if issue.score_ambiguity is not None else "\u2014"
        if col == "score_change_surface":
            return (
                str(issue.score_change_surface)
                if issue.score_change_surface is not None
                else "\u2014"
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
                plain = _cell_value(c, issue)
                parts.append(_apply_cell_color(c, _render_cell(c, plain), plain))

        for c in all_cmds:
            if issue is None:
                parts.append(_col(_cmd_label(c), _CMD_WIDTH))
            else:
                if c == "/ll:refine-issue":
                    cell = str(issue.session_command_counts.get(c, 0))
                    parts.append(_col(cell, _CMD_WIDTH))
                else:
                    hit = c in cmd_set
                    raw = "\u2713" if hit else "\u2014"
                    padded = _col(raw, _CMD_WIDTH)
                    parts.append(
                        colorize(raw, "32") + padded[len(raw) :]
                        if hit
                        else colorize(raw, "2") + padded[len(raw) :]
                    )

        for c in post_cmd:
            if issue is None:
                parts.append(_header_cell(c))
            else:
                plain = _cell_value(c, issue)
                parts.append(_apply_cell_color(c, _render_cell(c, plain), plain))

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
    print(f"  {'conf':<12} Outcome confidence score (0\u2013100)")
    print(f"  {'cmplx':<12} Outcome criterion A \u2013 Complexity (0\u201325)")
    print(f"  {'tcov':<12} Outcome criterion B \u2013 Test Coverage (0\u201325)")
    print(f"  {'ambig':<12} Outcome criterion C \u2013 Ambiguity (0\u201325)")
    print(f"  {'chsrf':<12} Outcome criterion D \u2013 Change Surface (0\u201325)")
    print(f"  {'total':<12} Number of /ll:* skills applied")
