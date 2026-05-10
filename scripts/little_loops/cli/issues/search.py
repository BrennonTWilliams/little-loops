"""ll-issues search: Search issues with filters and sorting."""

from __future__ import annotations

import argparse
import re
from collections.abc import Callable
from datetime import date, datetime
from typing import TYPE_CHECKING

from little_loops.cli.output import PRIORITY_COLOR, TYPE_COLOR, colorize, print_json

if TYPE_CHECKING:
    from pathlib import Path

    from little_loops.config import BRConfig
    from little_loops.config.features import NextIssueConfig
    from little_loops.issue_parser import IssueInfo


def _parse_discovered_date(content: str) -> datetime | None:
    """Extract creation datetime from YAML frontmatter.

    Prefers ``captured_at`` (ISO datetime, sub-day resolution) when present,
    falling back to ``discovered_date`` (date-granular). Always returns a
    ``datetime`` — regex-only results are normalized to midnight — so sort
    comparisons never mix ``date`` and ``datetime``.
    """
    from little_loops.frontmatter import parse_frontmatter

    fm = parse_frontmatter(content)
    captured = fm.get("captured_at")
    if isinstance(captured, str) and captured:
        try:
            return datetime.fromisoformat(captured.rstrip("Z")).replace(tzinfo=None)
        except ValueError:
            pass

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None
    date_match = re.search(r"discovered_date:\s*(\S+)", match.group(1))
    if not date_match:
        return None
    date_str = date_match.group(1).strip("\"'")
    try:
        d = date.fromisoformat(date_str[:10])
    except ValueError:
        return None
    return datetime.combine(d, datetime.min.time())


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
    include_open: bool,
    include_done: bool,
    include_deferred: bool,
) -> list[tuple[IssueInfo, str]]:
    """Load issues from type directories, tagged with their frontmatter status.

    Scans only type-scoped directories (bugs/, features/, etc.) and reads
    ``IssueInfo.status`` from frontmatter instead of inferring status from the
    directory name.

    Returns:
        List of (IssueInfo, status) where status is the frontmatter value
        (e.g. 'open', 'in_progress', 'blocked', 'done', 'cancelled', 'deferred').
    """
    from little_loops.issue_parser import IssueParser

    parser = IssueParser(config)
    results: list[tuple[IssueInfo, str]] = []

    for category in config.issue_categories:
        issue_dir = config.get_issue_dir(category)
        if not issue_dir.exists():
            continue
        for f in sorted(issue_dir.glob("*.md")):
            try:
                issue = parser.parse_file(f)
                status = issue.status  # frontmatter field, default "open"
                if status in ("open", "in_progress", "blocked"):
                    if include_open:
                        results.append((issue, status))
                elif status in ("done", "cancelled"):
                    if include_done:
                        results.append((issue, status))
                elif status == "deferred":
                    if include_deferred:
                        results.append((issue, status))
                elif include_open:
                    # Unknown status: treat as open
                    results.append((issue, status))
            except Exception:
                continue

    return results


_STRATEGY_SORT_KEYS: dict[str, tuple[tuple[str, str], ...]] = {
    "confidence_first": (
        ("outcome_confidence", "desc"),
        ("confidence_score", "desc"),
        ("priority", "asc"),
    ),
    "priority_first": (
        ("priority", "asc"),
        ("outcome_confidence", "desc"),
        ("confidence_score", "desc"),
    ),
}


def build_sort_key(config: NextIssueConfig) -> Callable[[IssueInfo], tuple]:
    """Return a sort-key callable for an IssueInfo list based on NextIssueConfig.

    Resolution order:
    - If ``config.sort_keys`` is set, it takes precedence over ``config.strategy``.
    - Otherwise, the named strategy preset is used.

    The returned callable produces a multi-field tuple where each component is
    transformed per-field so that a plain ``sorted(..., reverse=False)`` call
    yields the desired order. Do NOT pass ``reverse=True`` — mixed directions
    are baked into each tuple component.

    None-handling (per-field sentinel):
    - ``direction="desc"`` (higher = better): component = ``-value`` when set, ``1`` when None.
      This mirrors ``-(value or -1)`` — values > 0 sort first, None sorts after 0.
    - ``direction="asc"``  (lower = better):  component = ``value``  when set, ``9999`` when None.

    The schema key ``"priority"`` maps to ``IssueInfo.priority_int``; all other
    keys are read directly off the dataclass.

    Raises:
        ValueError: If ``config.strategy`` is unknown (``from_dict`` normally
            guards this, but direct instantiation can bypass validation).
    """
    if config.sort_keys is not None:
        entries: tuple[tuple[str, str], ...] = tuple(
            (sk.key, sk.direction) for sk in config.sort_keys
        )
    else:
        preset = _STRATEGY_SORT_KEYS.get(config.strategy)
        if preset is None:
            raise ValueError(f"Unknown strategy: {config.strategy!r}")
        entries = preset

    def key(issue: IssueInfo) -> tuple:
        parts: list[int] = []
        for field_name, direction in entries:
            attr = "priority_int" if field_name == "priority" else field_name
            value = getattr(issue, attr)
            if direction == "desc":
                parts.append(-value if value is not None else 1)
            else:
                parts.append(value if value is not None else 9999)
        return tuple(parts)

    return key


def _sort_issues(
    items: list[tuple],
    sort_field: str,
    descending: bool,
) -> list[tuple]:
    """Sort issues by the requested field."""

    def key(item: tuple) -> tuple:
        issue, _status, disc_date, comp_date, *_rest = item
        if sort_field == "priority":
            return (issue.priority_int, issue.issue_id)
        if sort_field == "id":
            m = re.search(r"-(\d+)$", issue.issue_id)
            num = int(m.group(1)) if m else 0
            return (issue.issue_id.split("-", 1)[0], num)
        if sort_field in ("date", "created"):
            return (disc_date or datetime.max,)
        if sort_field == "completed":
            return (comp_date or date.max,)
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
    status = getattr(args, "status", "open")
    if getattr(args, "include_completed", False):
        status = "all"

    include_open = status in ("open", "in_progress", "blocked", "all")
    include_done = status in ("done", "cancelled", "all")
    include_deferred = status in ("deferred", "all")

    # Load issues
    raw = _load_issues_with_status(config, include_open, include_done, include_deferred)

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

    # Build enriched list: (IssueInfo, status, discovered_date, completed_date, labels)
    enriched: list[tuple[IssueInfo, str, datetime | None, date | None, list[str]]] = []
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
        ref_date: date | None
        if date_field == "discovered":
            # disc_date is datetime for sort precision; normalize to date for day-granular filters
            ref_date = disc_date.date() if disc_date is not None else None
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
        enriched.append((issue, stat, disc_date, comp_date, labels))

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
    labels_out = [item[4] for item in enriched]

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
                    "discovered_date": d.date().isoformat() if d else None,
                    "labels": lbls,
                }
                for issue, stat, d, lbls in zip(
                    issues_out, statuses_out, dates_out, labels_out, strict=True
                )
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
    buckets: dict[str, list[tuple[IssueInfo, str]]] = {"BUG": [], "FEAT": [], "ENH": [], "EPIC": []}
    for issue, stat in zip(issues_out, statuses_out, strict=True):
        prefix = issue.issue_id.split("-", 1)[0]
        if prefix in buckets:
            buckets[prefix].append((issue, stat))

    type_labels = {"BUG": "Bugs", "FEAT": "Features", "ENH": "Enhancements", "EPIC": "Epics"}
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
            status_tag = f" [{stat}]" if stat not in ("open", "in_progress") else ""
            lines.append(f"  {colored_priority}  {colored_id}  {issue.title}{status_tag}")
        lines.append("")
    lines.append(f"Total: {len(issues_out)} issue(s) found")
    print("\n".join(lines))
    return 0
