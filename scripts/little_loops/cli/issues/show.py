"""ll-issues show: Display summary card for a single issue."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def _resolve_issue_id(config: BRConfig, user_input: str) -> Path | None:
    """Resolve user input to an issue file path.

    Accepts three input formats:
    - Numeric ID only: "518"
    - Type + ID: "FEAT-518"
    - Priority + Type + ID: "P3-FEAT-518"

    Searches all active category directories and the completed directory.

    Args:
        config: Project configuration
        user_input: Issue ID string in any supported format

    Returns:
        Path to the matched issue file, or None if not found
    """
    user_input = user_input.strip()

    # Parse input to extract components
    numeric_id: str | None = None
    type_prefix: str | None = None
    priority: str | None = None

    # Try P-TYPE-NNN format (e.g., P3-FEAT-518)
    m = re.match(r"^(P\d)-(BUG|FEAT|ENH)-(\d+)$", user_input, re.IGNORECASE)
    if m:
        priority = m.group(1).upper()
        type_prefix = m.group(2).upper()
        numeric_id = m.group(3)
    else:
        # Try TYPE-NNN format (e.g., FEAT-518)
        m = re.match(r"^(BUG|FEAT|ENH)-(\d+)$", user_input, re.IGNORECASE)
        if m:
            type_prefix = m.group(1).upper()
            numeric_id = m.group(2)
        else:
            # Try numeric only (e.g., 518)
            m = re.match(r"^(\d+)$", user_input)
            if m:
                numeric_id = m.group(1)

    if numeric_id is None:
        return None

    # Build search directories: all active categories + completed
    search_dirs: list[Path] = []
    for category in config.issue_categories:
        search_dirs.append(config.get_issue_dir(category))
    search_dirs.append(config.get_completed_dir())

    # Search for matching files
    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for path in search_dir.glob(f"*-{numeric_id}-*.md"):
            filename = path.name
            # Verify type prefix if provided
            if type_prefix and f"-{type_prefix}-" not in filename.upper():
                continue
            # Verify priority if provided
            if priority and not filename.upper().startswith(f"{priority}-"):
                continue
            return path

    return None


def _parse_card_fields(path: Path) -> dict[str, str | None]:
    """Parse issue file to extract summary card fields.

    Args:
        path: Path to the issue file

    Returns:
        Dictionary of card fields
    """
    from little_loops.frontmatter import parse_frontmatter

    content = path.read_text()
    frontmatter = parse_frontmatter(content, coerce_types=True)
    filename = path.name

    # Extract priority from filename (e.g., P3-FEAT-518-...)
    priority_match = re.match(r"^(P\d)-", filename)
    priority = priority_match.group(1) if priority_match else None

    # Extract type and ID from filename (e.g., FEAT-518)
    type_id_match = re.search(r"(BUG|FEAT|ENH)-(\d+)", filename)
    issue_id = f"{type_id_match.group(1)}-{type_id_match.group(2)}" if type_id_match else None

    # Extract title from content
    title: str | None = None
    title_match = re.search(r"^#\s+[\w-]+:\s*(.+)$", content, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    else:
        header_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if header_match:
            title = header_match.group(1).strip()
        else:
            title = path.stem

    # Determine status
    is_completed = path.parent.name == "completed"
    status = "Completed" if is_completed else "Open"

    # Extract optional frontmatter fields
    confidence = frontmatter.get("confidence_score")
    outcome = frontmatter.get("outcome_confidence")
    effort = frontmatter.get("effort")

    return {
        "issue_id": issue_id,
        "title": title,
        "priority": priority,
        "status": status,
        "effort": str(effort) if effort is not None else None,
        "confidence": str(confidence) if confidence is not None else None,
        "outcome": str(outcome) if outcome is not None else None,
        "path": str(path),
    }


def _render_card(fields: dict[str, str | None]) -> str:
    """Render a summary card using box-drawing characters.

    Args:
        fields: Dictionary of card fields from _parse_card_fields

    Returns:
        Formatted card string
    """
    # Box-drawing characters
    h = "\u2500"  # ─
    v = "\u2502"  # │
    tl = "\u250c"  # ┌
    tr = "\u2510"  # ┐
    bl = "\u2514"  # └
    br = "\u2518"  # ┘
    ml = "\u251c"  # ├
    mr = "\u2524"  # ┤

    issue_id = fields.get("issue_id") or "???"
    title = fields.get("title") or "Untitled"
    header = f"{issue_id}: {title}"

    # Build metadata line
    meta_parts: list[str] = []
    if fields.get("priority"):
        meta_parts.append(f"Priority: {fields['priority']}")
    if fields.get("status"):
        meta_parts.append(f"Status: {fields['status']}")
    if fields.get("effort"):
        meta_parts.append(f"Effort: {fields['effort']}")
    meta_line = "  \u2502  ".join(meta_parts)

    # Build scores line (only if at least one score present)
    score_parts: list[str] = []
    if fields.get("confidence"):
        score_parts.append(f"Confidence: {fields['confidence']}")
    if fields.get("outcome"):
        score_parts.append(f"Outcome: {fields['outcome']}")
    scores_line = "  \u2502  ".join(score_parts) if score_parts else None

    # Build path line
    path_line = f"Path: {fields.get('path', '???')}"

    # Calculate width (minimum of inner content + padding)
    content_lines = [header, meta_line, path_line]
    if scores_line:
        content_lines.append(scores_line)
    width = max(len(line) for line in content_lines) + 2  # +2 for padding

    # Build card
    lines: list[str] = []
    top_border = f"{tl}{h * width}{tr}"
    mid_border = f"{ml}{h * width}{mr}"
    bot_border = f"{bl}{h * width}{br}"

    lines.append(top_border)
    lines.append(f"{v} {header:<{width - 1}}{v}")
    lines.append(mid_border)
    lines.append(f"{v} {meta_line:<{width - 1}}{v}")
    if scores_line:
        lines.append(f"{v} {scores_line:<{width - 1}}{v}")
    lines.append(mid_border)
    lines.append(f"{v} {path_line:<{width - 1}}{v}")
    lines.append(bot_border)

    return "\n".join(lines)


def cmd_show(config: BRConfig, args: argparse.Namespace) -> int:
    """Display summary card for a single issue.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id attribute

    Returns:
        Exit code (0 = success, 1 = not found)
    """
    issue_id = args.issue_id
    path = _resolve_issue_id(config, issue_id)

    if path is None:
        print(f"Error: Issue '{issue_id}' not found.")
        return 1

    fields = _parse_card_fields(path)
    card = _render_card(fields)
    print(card)
    return 0
