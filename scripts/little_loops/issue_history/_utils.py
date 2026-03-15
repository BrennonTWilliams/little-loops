"""Shared utilities for issue_history sub-modules."""

from __future__ import annotations

from pathlib import Path

from little_loops.issue_history.models import CompletedIssue


def get_issue_content(issue: CompletedIssue, contents: dict[Path, str] | None) -> str | None:
    """Retrieve issue content from cache or filesystem.

    Args:
        issue: The completed issue to retrieve content for
        contents: Optional pre-loaded content cache (path -> content)

    Returns:
        Issue file content string, or None if unavailable
    """
    if contents is not None and issue.path in contents:
        return contents[issue.path]
    try:
        return issue.path.read_text(encoding="utf-8")
    except Exception:
        return None
