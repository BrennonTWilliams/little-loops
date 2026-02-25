"""ll-issues impact-effort: ASCII impact vs effort matrix for active issues."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo

# Effort/impact scale: 1=low, 2=medium, 3=high
_PRIORITY_TO_EFFORT = {0: 3, 1: 3, 2: 2, 3: 2, 4: 1, 5: 1}
_PRIORITY_TO_IMPACT = {0: 3, 1: 3, 2: 2, 3: 2, 4: 1, 5: 1}

# Max issues to show per quadrant before truncating
_MAX_PER_QUADRANT = 6

# Column width for each quadrant (content area, excluding border chars)
_COL_WIDTH = 20


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


def _issue_slug(issue: IssueInfo) -> str:
    """Extract short slug from filename: description segment with hyphens→spaces, truncated."""
    name = issue.path.stem  # e.g. "P3-FEAT-505-ll-issues-cli-command"
    parts = name.split("-", 3)  # ['P3', 'FEAT', '505', 'll-issues-cli-command']
    if len(parts) >= 4:
        slug = parts[3].replace("-", " ")
    else:
        slug = issue.title
    max_len = _COL_WIDTH - len(issue.issue_id) - 2
    return slug[:max_len] if len(slug) > max_len else slug


def _render_quadrant_lines(issues: list[IssueInfo], header: str) -> list[str]:
    """Render lines for a single quadrant (no borders, fixed _COL_WIDTH)."""
    lines: list[str] = []
    lines.append(header.ljust(_COL_WIDTH))
    shown = issues[:_MAX_PER_QUADRANT]
    for issue in shown:
        slug = _issue_slug(issue)
        line = f"{issue.issue_id}  {slug}"
        lines.append(line.ljust(_COL_WIDTH))
    if len(issues) > _MAX_PER_QUADRANT:
        extra = len(issues) - _MAX_PER_QUADRANT
        lines.append(f"  \u2026 +{extra} more".ljust(_COL_WIDTH))
    if not shown:
        lines.append("(none)".ljust(_COL_WIDTH))
    return lines


def _render_grid(
    q_high_low: list[IssueInfo],  # high impact, low effort  = quick wins
    q_high_high: list[IssueInfo],  # high impact, high effort = major projects
    q_low_low: list[IssueInfo],  # low impact, low effort   = fill-ins
    q_low_high: list[IssueInfo],  # low impact, high effort  = thankless tasks
) -> str:
    """Render the 2x2 ASCII grid and return as a string."""
    lines_tl = _render_quadrant_lines(q_high_low, "\u2605 QUICK WINS")
    lines_tr = _render_quadrant_lines(q_high_high, "\u25b2 MAJOR PROJECTS")
    lines_bl = _render_quadrant_lines(q_low_low, "\u00b7 FILL-INS")
    lines_br = _render_quadrant_lines(q_low_high, "\u2717 THANKLESS")

    # Pad all quadrant line lists to the same height
    top_height = max(len(lines_tl), len(lines_tr))
    bot_height = max(len(lines_bl), len(lines_br))

    def pad(lst: list[str], height: int) -> list[str]:
        while len(lst) < height:
            lst.append(" " * _COL_WIDTH)
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

    bar = h * (_COL_WIDTH + 2)
    top_border = f"{tl}{bar}{tm}{bar}{tr}"
    mid_border = f"{ml}{bar}{mid}{bar}{mr}"
    bot_border = f"{bl}{bar}{bm}{bar}{br}"

    out: list[str] = []

    # Axis labels
    axis_width = _COL_WIDTH * 2 + 7  # total grid width
    effort_label = "\u2190 EFFORT \u2192"
    out.append(effort_label.center(axis_width + 8))
    low_high_label = "Low" + " " * (_COL_WIDTH * 2 + 1) + "High"
    out.append(" " * 8 + low_high_label)

    out.append(" " * 8 + top_border)
    for i, (tl_line, tr_line) in enumerate(zip(lines_tl, lines_tr, strict=True)):
        row_label = "High IMPACT " if i == 0 else " " * 12
        out.append(f"{row_label}{v} {tl_line} {v} {tr_line} {v}")
    out.append(" " * 8 + mid_border)
    for i, (bl_line, br_line) in enumerate(zip(lines_bl, lines_br, strict=True)):
        row_label = "Low  IMPACT " if i == 0 else " " * 12
        out.append(f"{row_label}{v} {bl_line} {v} {br_line} {v}")
    out.append(" " * 8 + bot_border)

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
    return 0
