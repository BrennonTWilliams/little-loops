"""ll-issues impact-effort: ASCII impact vs effort matrix for active issues."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from little_loops.cli.output import TYPE_COLOR, colorize, terminal_width

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo

# Effort/impact scale: 1=low, 2=medium, 3=high
_PRIORITY_TO_EFFORT = {0: 3, 1: 3, 2: 2, 3: 2, 4: 1, 5: 1}
_PRIORITY_TO_IMPACT = {0: 3, 1: 3, 2: 2, 3: 2, 4: 1, 5: 1}

# Max issues to show per quadrant before truncating
_MAX_PER_QUADRANT = 6

_QUADRANT_HEADER_COLOR = {
    "quick_wins": "32;1",  # bold green   — desirable
    "major_projects": "33",  # yellow       — important, costly
    "fill_ins": "2",  # dim          — low priority
    "thankless": "38;5;208",  # orange       — avoid
}


def _infer_effort(issue: IssueInfo) -> int:
    """Return effort level (1=low, 2=med, 3=high) from frontmatter or priority."""
    if issue.effort is not None:
        return max(1, min(3, issue.effort))
    return _PRIORITY_TO_EFFORT.get(issue.priority_int, 2)


def _infer_impact(issue: IssueInfo) -> int:
    """Return impact level (1=low, 2=med, 3=high) from frontmatter or priority."""
    if issue.impact is not None:
        return max(1, min(3, issue.impact))
    return _PRIORITY_TO_IMPACT.get(issue.priority_int, 2)


def _issue_slug(issue: IssueInfo, col_width: int) -> str:
    """Extract short slug from filename: description segment with hyphens→spaces, truncated."""
    name = issue.path.stem  # e.g. "P3-FEAT-505-ll-issues-cli-command"
    parts = name.split("-", 3)  # ['P3', 'FEAT', '505', 'll-issues-cli-command']
    if len(parts) >= 4:
        slug = parts[3].replace("-", " ")
    else:
        slug = issue.title
    max_len = col_width - len(issue.issue_id) - 2
    return slug[:max_len] if len(slug) > max_len else slug


def _render_quadrant_lines(
    issues: list[IssueInfo], header: str, header_color: str, col_width: int
) -> list[str]:
    """Render lines for a single quadrant (no borders, fixed col_width)."""
    lines: list[str] = []
    padded = colorize(header, header_color) + " " * (col_width - len(header))
    lines.append(padded)
    shown = issues[:_MAX_PER_QUADRANT]
    for issue in shown:
        slug = _issue_slug(issue, col_width)
        raw = f"{issue.issue_id}  {slug}"
        padding = " " * (col_width - len(raw))
        issue_type = issue.issue_id.split("-", 1)[0]
        colored_id = colorize(issue.issue_id, TYPE_COLOR.get(issue_type, "0"))
        lines.append(f"{colored_id}  {slug}{padding}")
    if len(issues) > _MAX_PER_QUADRANT:
        extra = len(issues) - _MAX_PER_QUADRANT
        lines.append(f"  \u2026 +{extra} more".ljust(col_width))
    if not shown:
        lines.append("(none)".ljust(col_width))
    return lines


def _render_grid(
    q_high_low: list[IssueInfo],  # high impact, low effort  = quick wins
    q_high_high: list[IssueInfo],  # high impact, high effort = major projects
    q_low_low: list[IssueInfo],  # low impact, low effort   = fill-ins
    q_low_high: list[IssueInfo],  # low impact, high effort  = thankless tasks
) -> str:
    """Render the 2x2 ASCII grid and return as a string."""
    col_width = max(18, min(38, (terminal_width() - 19) // 2))

    lines_tl = _render_quadrant_lines(
        q_high_low, "\u2605 QUICK WINS", _QUADRANT_HEADER_COLOR["quick_wins"], col_width
    )
    lines_tr = _render_quadrant_lines(
        q_high_high, "\u25b2 MAJOR PROJECTS", _QUADRANT_HEADER_COLOR["major_projects"], col_width
    )
    lines_bl = _render_quadrant_lines(
        q_low_low, "\u00b7 FILL-INS", _QUADRANT_HEADER_COLOR["fill_ins"], col_width
    )
    lines_br = _render_quadrant_lines(
        q_low_high, "\u2717 THANKLESS", _QUADRANT_HEADER_COLOR["thankless"], col_width
    )

    # Pad all quadrant line lists to the same height
    top_height = max(len(lines_tl), len(lines_tr))
    bot_height = max(len(lines_bl), len(lines_br))

    def pad(lst: list[str], height: int) -> list[str]:
        while len(lst) < height:
            lst.append(" " * col_width)
        return lst

    lines_tl = pad(lines_tl, top_height)
    lines_tr = pad(lines_tr, top_height)
    lines_bl = pad(lines_bl, bot_height)
    lines_br = pad(lines_br, bot_height)

    # Box-drawing characters
    h = "\u2500"
    v = "\u2502"
    tl = "\u250c"
    tr = "\u2510"
    bl = "\u2514"
    br = "\u2518"
    tm = "\u252c"
    bm = "\u2534"
    ml = "\u251c"
    mr = "\u2524"
    mid = "\u253c"

    bar = h * (col_width + 2)
    top_border = f"{tl}{bar}{tm}{bar}{tr}"
    mid_border = f"{ml}{bar}{mid}{bar}{mr}"
    bot_border = f"{bl}{bar}{bm}{bar}{br}"

    label_width = 12  # len("High IMPACT ") == len("Low  IMPACT ") == len(" " * 12)
    grid_width = len(top_border)  # 1 + (col_width+2) + 1 + (col_width+2) + 1
    col_section = col_width + 2  # one column's width including surrounding spaces

    out: list[str] = []

    # Axis labels: "← EFFORT →" centered over grid; "Low"/"High" over each column
    effort_plain = "\u2190 EFFORT \u2192"
    effort_pad_total = grid_width - len(effort_plain)
    effort_left = " " * (effort_pad_total // 2)
    effort_right = " " * (effort_pad_total - effort_pad_total // 2)
    out.append(" " * label_width + effort_left + colorize(effort_plain, "1") + effort_right)

    low_centered = "Low".center(col_section)
    high_plain = "High"
    high_pad_total = col_section - len(high_plain)
    high_left = " " * (high_pad_total // 2)
    high_right = " " * (high_pad_total - high_pad_total // 2)
    high_centered = high_left + colorize(high_plain, "1") + high_right
    out.append(" " * (label_width + 1) + low_centered + " " + high_centered)

    out.append(" " * label_width + top_border)
    for i, (tl_line, tr_line) in enumerate(zip(lines_tl, lines_tr, strict=True)):
        row_label = "High IMPACT " if i == 0 else " " * label_width
        out.append(f"{row_label}{v} {tl_line} {v} {tr_line} {v}")
    out.append(" " * label_width + mid_border)
    for i, (bl_line, br_line) in enumerate(zip(lines_bl, lines_br, strict=True)):
        row_label = "Low  IMPACT " if i == 0 else " " * label_width
        out.append(f"{row_label}{v} {bl_line} {v} {br_line} {v}")
    out.append(" " * label_width + bot_border)

    return "\n".join(out)


def cmd_impact_effort(config: BRConfig, args: argparse.Namespace) -> int:
    """Display impact vs effort matrix for active issues.

    Issues are grouped into four quadrants:
      - Quick Wins:      high impact, low effort
      - Major Projects:  high impact, high effort
      - Fill-ins:        low impact, low effort
      - Thankless Tasks: low impact, high effort

    Effort and impact (1=low, 2=med, 3=high) are read from issue frontmatter
    if present; otherwise inferred from priority (P0-P1=high, P2-P3=med, P4-P5=low).

    Args:
        config: Project configuration
        args: Parsed arguments (unused, reserved for future flags)

    Returns:
        Exit code (0 = success)
    """
    from little_loops.issue_parser import find_issues

    issues = find_issues(config)

    if not issues:
        print("No active issues found.")
        return 0

    q_high_low: list[IssueInfo] = []
    q_high_high: list[IssueInfo] = []
    q_low_low: list[IssueInfo] = []
    q_low_high: list[IssueInfo] = []

    for issue in issues:
        effort = _infer_effort(issue)
        impact = _infer_impact(issue)
        high_impact = impact >= 2
        high_effort = effort >= 2
        if high_impact and not high_effort:
            q_high_low.append(issue)
        elif high_impact and high_effort:
            q_high_high.append(issue)
        elif not high_impact and not high_effort:
            q_low_low.append(issue)
        else:
            q_low_high.append(issue)

    print(_render_grid(q_high_low, q_high_high, q_low_low, q_low_high))

    total = len(issues)
    print(f"\n  {total} issue{'s' if total != 1 else ''} plotted")
    return 0
