"""ll-issues show: Display summary card for a single issue."""

from __future__ import annotations

import argparse
import re
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.cli.output import PRIORITY_COLOR, TYPE_COLOR, colorize, print_json, terminal_width

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


def _parse_card_fields(path: Path, config: BRConfig) -> dict[str, str | None]:
    """Parse issue file to extract summary card fields.

    Args:
        path: Path to the issue file
        config: Project configuration (used for relative path computation)

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

    # --- New fields ---

    # Summary: full first paragraph from ## Summary section
    summary: str | None = None
    summary_match = re.search(
        r"^## Summary\s*\n+(.*?)(?:\n\n|\n##|\Z)", content, re.MULTILINE | re.DOTALL
    )
    if summary_match:
        text = summary_match.group(1).strip()
        if text:
            summary = text

    # Integration file count: count items under ### Files to Modify
    integration_files: int | None = None
    ftm_match = re.search(r"^### Files to Modify\s*$", content, re.MULTILINE)
    if ftm_match:
        start = ftm_match.end()
        next_header = re.search(r"^#{2,3}\s+", content[start:], re.MULTILINE)
        section = content[start : start + next_header.start()] if next_header else content[start:]
        count = len(re.findall(r"^- .+", section, re.MULTILINE))
        if count > 0:
            integration_files = count

    # Risk: extract from ## Impact section
    risk: str | None = None
    risk_match = re.search(r"\*\*Risk\*\*:\s*(Low|Medium|High)", content, re.IGNORECASE)
    if risk_match:
        risk = risk_match.group(1).capitalize()

    # Labels: extract backtick-delimited labels from ## Labels section
    labels: str | None = None
    labels_match = re.search(
        r"^## Labels\s*\n+(.*?)(?:\n\n|\n##|\Z)", content, re.MULTILINE | re.DOTALL
    )
    if labels_match:
        found = re.findall(r"`([^`]+)`", labels_match.group(1))
        if found:
            labels = ", ".join(found)

    # Session log: parse ## Session Log for unique /ll:* commands with counts
    history: str | None = None
    from little_loops.session_log import count_session_commands, parse_session_log

    distinct = parse_session_log(content)
    if distinct:
        counts = count_session_commands(content)
        parts = [f"{cmd} ({counts[cmd]})" if counts.get(cmd, 1) > 1 else cmd for cmd in distinct]
        history = ", ".join(parts)

    # Relative path
    try:
        rel_path = str(path.relative_to(config.project_root))
    except ValueError:
        rel_path = str(path)

    return {
        "issue_id": issue_id,
        "title": title,
        "priority": priority,
        "status": status,
        "effort": str(effort) if effort is not None else None,
        "confidence": str(confidence) if confidence is not None else None,
        "outcome": str(outcome) if outcome is not None else None,
        "summary": summary,
        "integration_files": str(integration_files) if integration_files is not None else None,
        "risk": risk,
        "labels": labels,
        "history": history,
        "path": rel_path,
    }


_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _ljust(text: str, width: int) -> str:
    """Left-justify text accounting for invisible ANSI escape codes."""
    pad = max(0, width - len(_strip_ansi(text)))
    return text + " " * pad


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

    # Build metadata line (plain, for width calculation)
    priority = fields.get("priority")
    status = fields.get("status")
    effort = fields.get("effort")
    risk = fields.get("risk")

    meta_parts: list[str] = []
    if priority:
        meta_parts.append(f"Priority: {priority}")
    if status:
        meta_parts.append(f"Status: {status}")
    if effort:
        meta_parts.append(f"Effort: {effort}")
    if risk:
        meta_parts.append(f"Risk: {risk}")
    meta_line = "  \u2502  ".join(meta_parts)

    # Build scores line (only if at least one score present)
    score_parts: list[str] = []
    if fields.get("confidence"):
        score_parts.append(f"Confidence: {fields['confidence']}")
    if fields.get("outcome"):
        score_parts.append(f"Outcome: {fields['outcome']}")
    scores_line = "  \u2502  ".join(score_parts) if score_parts else None

    # Build detail lines (integration+labels, history)
    detail_lines: list[str] = []
    detail_mid_parts: list[str] = []
    if fields.get("integration_files"):
        detail_mid_parts.append(f"Integration: {fields['integration_files']} files")
    if fields.get("labels"):
        detail_mid_parts.append(f"Labels: {fields['labels']}")
    if detail_mid_parts:
        detail_lines.append("  \u2502  ".join(detail_mid_parts))
    if fields.get("history"):
        detail_lines.append(f"History: {fields['history']}")

    # Build path line
    path_line = f"Path: {fields.get('path', '???')}"

    # Calculate structural width from non-summary content
    structural_lines = [header, meta_line, path_line]
    if scores_line:
        structural_lines.append(scores_line)
    structural_lines.extend(detail_lines)
    wrap_width = max((len(line) for line in structural_lines), default=60)
    wrap_width = max(wrap_width, 60)  # minimum content width

    # Build summary lines — wrap to fit structural width
    summary_lines: list[str] = []
    summary_text = fields.get("summary")
    if summary_text:
        for line in summary_text.splitlines():
            if line.strip():
                summary_lines.extend(textwrap.wrap(line, width=wrap_width, break_long_words=False))
            else:
                summary_lines.append("")

    # Final width includes wrapped summary (may exceed wrap_width for unbreakable tokens)
    all_lines = structural_lines + summary_lines
    width = max(len(line) for line in all_lines) + 2  # +2 for padding

    # Cap width to terminal to prevent overflow
    width = min(width, terminal_width() - 4)

    # Build colorized header
    if issue_id and "-" in issue_id:
        itype = issue_id.split("-")[0]
        colored_id = colorize(issue_id, TYPE_COLOR.get(itype, "0"))
    else:
        colored_id = issue_id
    colored_header = f"{colored_id}: {title}"

    # Build colorized meta line
    colored_meta_parts: list[str] = []
    if priority:
        colored_meta_parts.append(
            f"Priority: {colorize(priority, PRIORITY_COLOR.get(priority, '0'))}"
        )
    if status:
        colored_status = colorize("Completed", "32") if status == "Completed" else status
        colored_meta_parts.append(f"Status: {colored_status}")
    if effort:
        colored_meta_parts.append(f"Effort: {effort}")
    if risk:
        risk_code = {"High": "38;5;208", "Medium": "33", "Low": "2"}.get(risk, "0")
        colored_meta_parts.append(f"Risk: {colorize(risk, risk_code)}")
    colored_meta_line = "  \u2502  ".join(colored_meta_parts)

    # Build card
    lines: list[str] = []
    top_border = f"{tl}{h * width}{tr}"
    mid_border = f"{ml}{h * width}{mr}"
    bot_border = f"{bl}{h * width}{br}"

    lines.append(top_border)
    lines.append(f"{v} {_ljust(colored_header, width - 1)}{v}")
    lines.append(mid_border)
    lines.append(f"{v} {_ljust(colored_meta_line, width - 1)}{v}")
    if scores_line:
        lines.append(f"{v} {scores_line:<{width - 1}}{v}")
    if summary_lines:
        lines.append(mid_border)
        for sl in summary_lines:
            lines.append(f"{v} {sl:<{width - 1}}{v}")
    if detail_lines:
        lines.append(mid_border)
        for dl in detail_lines:
            lines.append(f"{v} {dl:<{width - 1}}{v}")
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

    fields = _parse_card_fields(path, config)

    if getattr(args, "json", False):
        print_json(fields)
        return 0

    card = _render_card(fields)
    print(card)
    return 0
