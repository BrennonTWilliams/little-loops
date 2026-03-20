"""ll-issues search: Search issues with filters and sorting."""

from __future__ import annotations

import argparse
import re
from datetime import date
from typing import TYPE_CHECKING

from little_loops.cli.output import PRIORITY_COLOR, TYPE_COLOR, colorize, print_json

if TYPE_CHECKING:
    from pathlib import Path

    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo


def _parse_discovered_date(content: str) -> date | None:
    """Extract discovered_date from YAML frontmatter."""
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None
    date_match = re.search(r"discovered_date:\s*(\S+)", match.group(1))
    if not date_match:
        return None
    date_str = date_match.group(1).strip("\"'")
    try:
        # Handle ISO datetime strings like 2026-03-13T21:11:34Z
        return date.fromisoformat(date_str[:10])
    except ValueError:
        return None


def _parse_updated_date(content: str, file_path: Path) -> date | None:
    r"""Extract last-activity date from the ## Session Log section, or fall back to file mtime.

    Scans for the most recent timestamp entry in the Session Log section.
    Entry format: `- \`/ll:cmd\` - YYYY-MM-DDTHH:MM:SS - \`path\``
    Falls back to file mtime when no session log timestamps are found.
    """
    import re as _re

    _SESSION_LOG_RE = _re.compile(
        r"^## Session Log\s*\n+(.*?)(?:\n##|\n---|\Z)", _re.MULTILINE | _re.DOTALL
    )
    _TIMESTAMP_RE = _re.compile(r"- `[^`]+` - (\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}")

    match = _SESSION_LOG_RE.search(content)
    if match:
        timestamps = _TIMESTAMP_RE.findall(match.group(1))
        if timestamps:
            try:
                return date.fromisoformat(timestamps[-1])
            except ValueError:
                pass

    # Fallback to file mtime
    try:
        return date.fromtimestamp(file_path.stat().st_mtime)
    except OSError:
        return None


def _parse_labels_from_content(content: str) -> list[str]:
    """Extract labels from ## Labels section (backtick-wrapped items)."""
    match = re.search(r"## Labels\s*\n(.*?)(?:\n##|\Z)", content, re.DOTALL)
    if not match:
        return []
    return [m.lower() for m in re.findall(r"`([^`]+)`", match.group(1))]


def _parse_priority_filter(priority_values: list[str]) -> set[str]:
    """Parse priority filter values, supporting ranges like P0-P2."""
    priorities: set[str] = set()
    for val in priority_values:
        range_match = re.match(r"^(P\d)-(P\d)$", val)
        if range_match:
            start = int(range_match.group(1)[1:])
            end = int(range_match.group(2)[1:])
            for i in range(start, end + 1):
                priorities.add(f"P{i}")
        elif re.match(r"^P\d$", val):
            priorities.add(val)
    return priorities


def _load_issues_with_status(
    config: BRConfig,
    include_active: bool,
    include_completed: bool,
    include_deferred: bool,
) -> list[tuple[IssueInfo, str]]:
    """Load issues from the relevant directories, tagged with their status.

    Returns:
        List of (IssueInfo, status) where status is 'active', 'completed', or 'deferred'.
    """
    from little_loops.issue_parser import IssueParser

    parser = IssueParser(config)
    results: list[tuple[IssueInfo, str]] = []

    if include_active:
        for category in config.issue_categories:
            issue_dir = config.get_issue_dir(category)
            if issue_dir.exists():
                for f in sorted(issue_dir.glob("*.md")):
                    try:
                        results.append((parser.parse_file(f), "active"))
                    except Exception:
                        continue

    if include_completed:
        completed_dir = config.get_completed_dir()
        if completed_dir.exists():
            for f in sorted(completed_dir.glob("*.md")):
                try:
                    results.append((parser.parse_file(f), "completed"))
                except Exception:
                    continue

    if include_deferred:
        deferred_dir = config.get_deferred_dir()
        if deferred_dir.exists():
            for f in sorted(deferred_dir.glob("*.md")):
                try:
                    results.append((parser.parse_file(f), "deferred"))
                except Exception:
                    continue

    return results


def _sort_issues(
    items: list[tuple[IssueInfo, str, date | None, date | None]],
    sort_field: str,
    descending: bool,
) -> list[tuple[IssueInfo, str, date | None, date | None]]:
    """Sort issues by the requested field."""
    sentinel = date(9999, 12, 31)

    def key(item: tuple) -> tuple:
        issue, _status, disc_date, comp_date = item
        if sort_field == "priority":
            return (issue.priority_int, issue.issue_id)
        if sort_field == "id":
            m = re.search(r"-(\d+)$", issue.issue_id)
            num = int(m.group(1)) if m else 0
            return (issue.issue_id.split("-", 1)[0], num)
        if sort_field in ("date", "created"):
            return (disc_date or sentinel,)
        if sort_field == "completed":
            return (comp_date or sentinel,)
        if sort_field == "type":
            return (issue.issue_id.split("-", 1)[0], issue.priority_int, issue.issue_id)
        if sort_field == "title":
            return (issue.title.lower(),)
        if sort_field == "confidence":
            score = issue.confidence_score if issue.confidence_score is not None else 9999
            return (score,)
        if sort_field == "outcome":
            score = issue.outcome_confidence if issue.outcome_confidence is not None else 9999
            return (score,)
        if sort_field == "refinement":
            refinement_commands = {
                "/ll:verify-issues",
                "/ll:refine-issue",
                "/ll:tradeoff-review-issues",
                "/ll:map-dependencies",
                "/ll:ready-issue",
            }
            counts: dict[str, int] = getattr(issue, "session_command_counts", {}) or {}
            total = sum(counts.get(cmd, 0) for cmd in refinement_commands)
            return (total,)
        return (issue.priority_int, issue.issue_id)

    return sorted(items, key=key, reverse=descending)


def cmd_search(config: BRConfig, args: argparse.Namespace) -> int:
    """Search issues with optional text query, filters, and sorting.

    Args:
        config: Project configuration
        args: Parsed arguments

    Returns:
        Exit code (0 = success)
    """
    # Resolve status flags
    status = getattr(args, "status", "active")
    if getattr(args, "include_completed", False):
        status = "all"

    include_active = status in ("active", "all")
    include_completed = status in ("completed", "all")
    include_deferred = status in ("deferred", "all")

    # Load issues
    raw = _load_issues_with_status(config, include_active, include_completed, include_deferred)

    # Parse additional metadata (dates, labels) only when needed
    query: str | None = getattr(args, "query", None)
    since_date: date | None = None
    until_date: date | None = None
    raw_since = getattr(args, "since", None)
    raw_until = getattr(args, "until", None)
    if raw_since:
        try:
            since_date = date.fromisoformat(raw_since)
        except ValueError:
            print(f"Invalid --since date: {raw_since!r}. Use YYYY-MM-DD.")
            return 1
    if raw_until:
        try:
            until_date = date.fromisoformat(raw_until)
        except ValueError:
            print(f"Invalid --until date: {raw_until!r}. Use YYYY-MM-DD.")
            return 1

    sort_field = getattr(args, "sort", "priority") or "priority"
    need_content = bool(
        query
        or since_date
        or until_date
        or getattr(args, "label", None)
        or sort_field in {"date", "created", "completed"}
        or getattr(args, "date_field", "discovered") == "updated"
    )

    # Build enriched list: (IssueInfo, status, discovered_date, completed_date)
    enriched: list[tuple[IssueInfo, str, date | None, date | None]] = []
    for issue, stat in raw:
        if need_content:
            try:
                content = issue.path.read_text(encoding="utf-8")
            except Exception:
                content = ""
            disc_date = _parse_discovered_date(content)
            labels = _parse_labels_from_content(content)
        else:
            content = ""
            disc_date = None
            labels = []

        # --- Filter: text query ---
        if query:
            haystack = (issue.title + "\n" + content).lower()
            if query.lower() not in haystack:
                continue

        # --- Filter: type ---
        type_filters: list[str] = getattr(args, "type", None) or []
        if type_filters:
            issue_type = issue.issue_id.split("-", 1)[0]
            if issue_type not in type_filters:
                continue

        # --- Filter: priority ---
        priority_filters: list[str] = getattr(args, "priority", None) or []
        if priority_filters:
            allowed = _parse_priority_filter(priority_filters)
            if issue.priority not in allowed:
                continue

        # --- Filter: label ---
        label_filters: list[str] = getattr(args, "label", None) or []
        if label_filters:
            if not any(lf.lower() in labels for lf in label_filters):
                continue

        # --- Filter: date range ---
        date_field = getattr(args, "date_field", "discovered")
        if date_field == "discovered":
            ref_date = disc_date
        else:
            ref_date = _parse_updated_date(content, issue.path)

        if since_date and (ref_date is None or ref_date < since_date):
            continue
        if until_date and (ref_date is None or ref_date > until_date):
            continue

        comp_date: date | None = None
        if sort_field == "completed" and need_content:
            from little_loops.issue_history.parsing import _parse_completion_date

            comp_date = _parse_completion_date(content, issue.path)
        enriched.append((issue, stat, disc_date, comp_date))

    # --- Sort ---
    # Default direction: desc for date/created/completed (newest first), asc for everything else
    if getattr(args, "desc", False):
        descending = True
    elif getattr(args, "asc", False):
        descending = False
    else:
        descending = sort_field in {"date", "created", "completed"}

    enriched = _sort_issues(enriched, sort_field, descending)

    # --- Limit ---
    limit = getattr(args, "limit", None)
    if limit and limit > 0:
        enriched = enriched[:limit]

    if not enriched:
        print("No issues found.")
        return 0

    # --- Output ---
    issues_out = [item[0] for item in enriched]
    statuses_out = [item[1] for item in enriched]
    dates_out = [item[2] for item in enriched]

    if getattr(args, "json", False):
        print_json(
            [
                {
                    "id": issue.issue_id,
                    "priority": issue.priority,
                    "type": issue.issue_id.split("-", 1)[0],
                    "title": issue.title,
                    "path": str(issue.path),
                    "status": stat,
                    "discovered_date": str(d) if d else None,
                }
                for issue, stat, d in zip(issues_out, statuses_out, dates_out, strict=True)
            ]
        )
        return 0

    fmt = getattr(args, "format", "table") or "table"

    if fmt == "ids":
        for issue in issues_out:
            print(issue.issue_id)
        return 0

    if fmt == "list":
        for issue in issues_out:
            print(f"{issue.path.name}  {issue.title}")
        return 0

    # Default: table (grouped by type, similar to ll-issues list)
    buckets: dict[str, list[tuple[IssueInfo, str]]] = {"BUG": [], "FEAT": [], "ENH": []}
    for issue, stat in zip(issues_out, statuses_out, strict=True):
        prefix = issue.issue_id.split("-", 1)[0]
        if prefix in buckets:
            buckets[prefix].append((issue, stat))

    type_labels = {"BUG": "Bugs", "FEAT": "Features", "ENH": "Enhancements"}
    lines: list[str] = []
    for prefix, label in type_labels.items():
        group = buckets[prefix]
        if not group:
            continue
        header = colorize(f"{label} ({len(group)})", f"{TYPE_COLOR.get(prefix, '0')};1")
        lines.append(header)
        for issue, stat in group:
            issue_type = issue.issue_id.split("-", 1)[0]
            colored_id = colorize(issue.issue_id, TYPE_COLOR.get(issue_type, "0"))
            colored_priority = colorize(issue.priority, PRIORITY_COLOR.get(issue.priority, "0"))
            status_tag = f" [{stat}]" if stat != "active" else ""
            lines.append(f"  {colored_priority}  {colored_id}  {issue.title}{status_tag}")
        lines.append("")
    lines.append(f"Total: {len(issues_out)} issue(s) found")
    print("\n".join(lines))
    return 0
