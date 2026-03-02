"""Documentation synthesis from completed issue history.

Synthesizes architecture documentation from completed issues by scoring
relevance to a given topic, ordering chronologically by completion date,
and constructing a structured markdown document.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from little_loops.issue_history.models import CompletedIssue
from little_loops.text_utils import calculate_word_overlap, extract_words


def score_relevance(topic: str, issue: CompletedIssue, content: str) -> float:
    """Score how relevant a completed issue is to a topic.

    Uses Jaccard word overlap between the topic and the issue's
    title + summary content.

    Args:
        topic: Search topic string
        issue: Completed issue to score
        content: Raw file content of the issue

    Returns:
        Relevance score from 0.0 to 1.0
    """
    topic_words = extract_words(topic)
    if not topic_words:
        return 0.0

    # Combine issue ID, filename stem, and content for matching
    issue_text = f"{issue.issue_id} {issue.path.stem.replace('-', ' ')} {content}"
    issue_words = extract_words(issue_text)

    return calculate_word_overlap(topic_words, issue_words)


def _extract_section(content: str, heading: str) -> str:
    """Extract content under a markdown heading.

    Args:
        content: Full markdown content
        heading: Heading text to find (without ##)

    Returns:
        Section content (empty string if not found)
    """
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        return ""

    start = match.end()
    # Find next heading of same or higher level
    next_heading = re.search(r"^##\s", content[start:], re.MULTILINE)
    if next_heading:
        end = start + next_heading.start()
    else:
        end = len(content)

    return content[start:end].strip()


def _extract_title(content: str) -> str:
    """Extract the H1 title from issue content.

    Args:
        content: Issue file content

    Returns:
        Title text, or empty string if not found
    """
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def synthesize_docs(
    topic: str,
    issues: list[CompletedIssue],
    contents: dict[Path, str],
    format: str = "narrative",
    min_relevance: float = 0.3,
    since: date | None = None,
    issue_type: str | None = None,
) -> str:
    """Synthesize documentation from completed issues matching a topic.

    Filters issues by relevance, orders chronologically by completion date,
    and builds a markdown document.

    Args:
        topic: Topic to search for
        issues: List of completed issues
        contents: Pre-loaded issue file contents (path -> content)
        format: Output format - "narrative" or "structured"
        min_relevance: Minimum relevance score threshold
        since: Only include issues completed after this date
        issue_type: Filter by issue type (BUG, FEAT, ENH)

    Returns:
        Synthesized markdown document
    """
    # Score and filter issues
    scored: list[tuple[CompletedIssue, float, str]] = []
    for issue in issues:
        content = contents.get(issue.path, "")
        if not content:
            continue

        # Apply type filter
        if issue_type and issue.issue_type != issue_type:
            continue

        # Apply date filter
        if since and issue.completed_date and issue.completed_date < since:
            continue

        score = score_relevance(topic, issue, content)
        if score >= min_relevance:
            scored.append((issue, score, content))

    # Sort by completion date ascending (oldest first), then by score
    scored.sort(
        key=lambda x: (
            x[0].completed_date or date.min,
            -x[1],
        )
    )

    if not scored:
        return f"No completed issues found matching topic: {topic}"

    if format == "structured":
        return build_structured_doc(topic, scored)
    return build_narrative_doc(topic, scored)


def build_narrative_doc(
    topic: str,
    scored_issues: list[tuple[CompletedIssue, float, str]],
) -> str:
    """Build a narrative-style documentation document.

    Each issue becomes a section describing what was built and why,
    ordered chronologically to read as a development narrative.

    Args:
        topic: The topic being documented
        scored_issues: List of (issue, score, content) tuples, pre-sorted

    Returns:
        Markdown document string
    """
    lines: list[str] = []

    lines.append(f"# {topic}")
    lines.append("")
    lines.append(
        f"*Synthesized from {len(scored_issues)} completed issue(s). "
        f"Generated from issue history.*"
    )
    lines.append("")

    for issue, _score, content in scored_issues:
        title = _extract_title(content)
        display_title = title or issue.issue_id

        # Section heading with date
        date_str = (
            issue.completed_date.isoformat() if issue.completed_date else "unknown"
        )
        lines.append(f"## {display_title}")
        lines.append("")
        lines.append(
            f"*{issue.issue_id} | Completed: {date_str} | "
            f"Type: {issue.issue_type} | Priority: {issue.priority}*"
        )
        lines.append("")

        # Summary section
        summary = _extract_section(content, "Summary")
        if summary:
            lines.append(summary)
            lines.append("")

        # Motivation section
        motivation = _extract_section(content, "Motivation")
        if motivation:
            lines.append(f"**Motivation:** {motivation}")
            lines.append("")

        # Implementation notes
        impl_notes = _extract_section(content, "Implementation Notes")
        if not impl_notes:
            impl_notes = _extract_section(content, "Resolution")
        if impl_notes:
            lines.append(f"**Implementation:** {impl_notes}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def build_structured_doc(
    topic: str,
    scored_issues: list[tuple[CompletedIssue, float, str]],
) -> str:
    """Build a structured documentation document.

    Organized with a summary table followed by detailed sections,
    focusing on technical content rather than narrative flow.

    Args:
        topic: The topic being documented
        scored_issues: List of (issue, score, content) tuples, pre-sorted

    Returns:
        Markdown document string
    """
    lines: list[str] = []

    lines.append(f"# {topic}")
    lines.append("")
    lines.append(
        f"*Synthesized from {len(scored_issues)} completed issue(s). "
        f"Generated from issue history.*"
    )
    lines.append("")

    # Summary table
    lines.append("## Overview")
    lines.append("")
    lines.append("| Issue | Type | Priority | Completed | Relevance |")
    lines.append("|-------|------|----------|-----------|-----------|")
    for issue, score, content in scored_issues:
        title = _extract_title(content) or issue.issue_id
        # Truncate long titles for the table
        if len(title) > 60:
            title = title[:57] + "..."
        date_str = (
            issue.completed_date.isoformat() if issue.completed_date else "N/A"
        )
        lines.append(
            f"| {title} | {issue.issue_type} | {issue.priority} | "
            f"{date_str} | {score:.0%} |"
        )
    lines.append("")

    # Detailed sections
    lines.append("## Details")
    lines.append("")

    for issue, _score, content in scored_issues:
        title = _extract_title(content) or issue.issue_id
        date_str = (
            issue.completed_date.isoformat() if issue.completed_date else "unknown"
        )

        lines.append(f"### {title}")
        lines.append("")
        lines.append(f"**ID:** {issue.issue_id} | **Completed:** {date_str}")
        lines.append("")

        summary = _extract_section(content, "Summary")
        if summary:
            lines.append(summary)
            lines.append("")

        # Expected behavior or proposed solution
        expected = _extract_section(content, "Expected Behavior")
        if not expected:
            expected = _extract_section(content, "Proposed Solution")
        if expected:
            lines.append(f"**Solution:** {expected}")
            lines.append("")

        impl_notes = _extract_section(content, "Implementation Notes")
        if not impl_notes:
            impl_notes = _extract_section(content, "Resolution")
        if impl_notes:
            lines.append(f"**Implementation:** {impl_notes}")
            lines.append("")

    return "\n".join(lines)
