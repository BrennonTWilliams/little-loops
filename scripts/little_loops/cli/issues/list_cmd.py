"""ll-issues list: List active issues with optional type/priority/status filters."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from little_loops.cli.output import PRIORITY_COLOR, TYPE_COLOR, colorize, print_json

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_list(config: BRConfig, args: argparse.Namespace) -> int:
    """List issues with optional filters.

    Args:
        config: Project configuration
        args: Parsed arguments with optional .type, .priority, .status, .flat, and .json attributes

    Returns:
        Exit code (0 = success)
    """
    from datetime import date, datetime

    from little_loops.cli.issues.search import (
        _load_issues_with_status,
        _parse_discovered_date,
        _parse_labels_from_content,
        _sort_issues,
    )

    status = getattr(args, "status", "open") or "open"
    include_open = status in ("open", "in_progress", "blocked", "all")
    include_done = status in ("done", "cancelled", "all")
    include_deferred = status in ("deferred", "all")

    raw = _load_issues_with_status(config, include_open, include_done, include_deferred)

    from little_loops.cli_args import parse_priorities

    type_filter = getattr(args, "type", None)
    priority_filter: set[str] | None = parse_priorities(getattr(args, "priority", None))
    label_filters: list[str] = getattr(args, "label", None) or []
    milestone_filter: str | None = getattr(args, "milestone", None) or None

    filtered = [
        (issue, stat)
        for issue, stat in raw
        if (not type_filter or issue.issue_id.split("-", 1)[0] == type_filter)
        and (not priority_filter or issue.priority in priority_filter)
        and (
            not label_filters
            or any(lf.lower() in [lb.lower() for lb in issue.labels] for lf in label_filters)
        )
        and (not milestone_filter or issue.milestone == milestone_filter)
    ]

    # Sort
    sort_field = getattr(args, "sort", "priority") or "priority"
    need_content = sort_field in {"created", "completed"}
    want_json = getattr(args, "json", False)
    enriched: list[tuple] = []
    for issue, stat in filtered:
        disc_date: datetime | None = None
        comp_date: date | None = None
        labels: list[str] = []
        content = ""
        if need_content or want_json:
            try:
                content = issue.path.read_text(encoding="utf-8")
            except Exception:
                content = ""
        if need_content:
            if sort_field == "created":
                disc_date = _parse_discovered_date(content, issue.path)
            elif sort_field == "completed":
                from little_loops.issue_history.parsing import _parse_completion_date

                comp_date = _parse_completion_date(content, issue.path)
        if want_json:
            labels = _parse_labels_from_content(content)
        enriched.append((issue, stat, disc_date, comp_date, labels))

    if getattr(args, "desc", False):
        descending = True
    elif getattr(args, "asc", False):
        descending = False
    else:
        descending = sort_field in {"created", "completed"}

    enriched = _sort_issues(enriched, sort_field, descending)

    limit = getattr(args, "limit", None)
    if limit is not None and limit < 1:
        import sys

        print(f"Error: --limit must be a positive integer, got {limit}", file=sys.stderr)
        return 1

    if limit is not None:
        enriched = enriched[:limit]

    issues_with_status = [(item[0], item[1]) for item in enriched]

    if not issues_with_status:
        print("No active issues")
        return 0

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
                    "discovered_date": disc_date.date().isoformat() if disc_date else None,
                    "parent": issue.parent,
                    "labels": lbls,
                    "milestone": issue.milestone,
                }
                for issue, stat, disc_date, _comp_date, lbls in enriched
            ]
        )
        return 0

    if getattr(args, "flat", False):
        for issue, _stat in issues_with_status:
            print(f"{issue.path.name}  {issue.title}")
        return 0

    group_by = getattr(args, "group_by", "type")
    if group_by == "epic":
        # Build parent title lookup from raw (before type filter) so headers
        # resolve correctly when --type BUG is combined with --group-by epic
        parent_titles: dict[str, str] = {i.issue_id: i.title for i, _ in raw if i.title}

        parent_buckets: dict[str | None, list] = {}
        for issue, stat in issues_with_status:
            if issue.issue_id.split("-", 1)[0] == "EPIC":
                continue
            key = (
                issue.parent if (issue.parent and issue.parent.split("-", 1)[0] == "EPIC") else None
            )
            if key not in parent_buckets:
                parent_buckets[key] = []
            parent_buckets[key].append((issue, stat))

        named_keys = sorted(k for k in parent_buckets if k is not None)
        ordered_keys = named_keys + ([None] if None in parent_buckets else [])

        # Pre-compute progress badges for named EPIC buckets
        epic_progress_cache: dict[str, tuple[int, int, int]] = {}
        if named_keys:
            from little_loops.issue_parser import find_issues as _find_issues_all
            from little_loops.issue_progress import compute_epic_progress

            _all_statuses: set[str] = {
                "open", "in_progress", "blocked", "done", "cancelled", "deferred"
            }
            all_issues_for_progress = _find_issues_all(config, status_filter=_all_statuses)
            for epic_key in named_keys:
                prog = compute_epic_progress(epic_key, all_issues_for_progress)
                if prog is not None:
                    done = prog.by_status.get("done", 0) + prog.by_status.get("cancelled", 0)
                    blocked = prog.by_status.get("blocked", 0)
                    epic_progress_cache[epic_key] = (done, len(prog.children), blocked)

        lines: list[str] = []
        for key in ordered_keys:
            group = parent_buckets[key]
            if key is None:
                header = colorize(f"Unparented ({len(group)})", "1")
            else:
                title = parent_titles.get(key, "")
                badge = ""
                if key in epic_progress_cache:
                    done, total, blocked = epic_progress_cache[key]
                    badge = f" ({done}/{total} done"
                    if blocked > 0:
                        badge += f" · {blocked} blocked"
                    badge += ")"
                base_label = f"{key}: {title}" if title else key
                label = f"{base_label} ({len(group)}){badge}"
                parent_prefix = key.split("-", 1)[0]
                header = colorize(label, f"{TYPE_COLOR.get(parent_prefix, '0')};1")
            lines.append(header)
            for issue, stat in group:
                issue_type = issue.issue_id.split("-", 1)[0]
                colored_id = colorize(issue.issue_id, TYPE_COLOR.get(issue_type, "0"))
                colored_priority = colorize(issue.priority, PRIORITY_COLOR.get(issue.priority, "0"))
                status_tag = f" [{stat}]" if stat not in ("open", "in_progress") else ""
                lines.append(f"  {colored_priority}  {colored_id}  {issue.title}{status_tag}")
            lines.append("")
        displayed = sum(len(g) for g in parent_buckets.values())
        lines.append(f"Total: {displayed} active issues (excluding EPICs)")
        print("\n".join(lines))
        return 0

    # Group by type prefix
    buckets: dict[str, list] = {"BUG": [], "FEAT": [], "ENH": [], "EPIC": []}
    for issue, stat in issues_with_status:
        prefix = issue.issue_id.split("-", 1)[0]
        if prefix in buckets:
            buckets[prefix].append((issue, stat))

    type_labels = {"BUG": "Bugs", "FEAT": "Features", "ENH": "Enhancements", "EPIC": "Epics"}
    lines = []
    for prefix, label in type_labels.items():
        group = buckets[prefix]
        header = colorize(f"{label} ({len(group)})", f"{TYPE_COLOR.get(prefix, '0')};1")
        lines.append(header)
        for issue, stat in group:
            issue_type = issue.issue_id.split("-", 1)[0]
            colored_id = colorize(issue.issue_id, TYPE_COLOR.get(issue_type, "0"))
            colored_priority = colorize(issue.priority, PRIORITY_COLOR.get(issue.priority, "0"))
            status_tag = f" [{stat}]" if stat not in ("open", "in_progress") else ""
            lines.append(f"  {colored_priority}  {colored_id}  {issue.title}{status_tag}")
        lines.append("")
    lines.append(f"Total: {len(issues_with_status)} active issues")
    print("\n".join(lines))
    return 0
