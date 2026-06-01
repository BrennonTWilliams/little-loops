"""EPIC progress aggregation: child-issue status rollup and oldest-open detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.issue_parser import IssueInfo

_ALL_STATUSES = frozenset({"open", "in_progress", "blocked", "done", "cancelled", "deferred"})
_OPEN_STATUSES = frozenset({"open", "in_progress", "blocked"})
_TERMINAL_STATUSES = frozenset({"done", "cancelled"})


@dataclass
class EpicProgress:
    """Aggregate progress metrics for an EPIC computed from its children."""

    epic_id: str
    epic_title: str
    children: list[IssueInfo]
    by_status: dict[str, int]
    percent_done: float
    percent_blocked: float
    oldest_open: IssueInfo | None
    oldest_open_age_days: int | None

    def to_dict(self) -> dict:
        """Serialize to a JSON-serializable dict for --format json output."""
        result: dict = {
            "epic_id": self.epic_id,
            "epic_title": self.epic_title,
            "total": len(self.children),
            "by_status": self.by_status,
            "percent_done": round(self.percent_done, 1),
            "percent_blocked": round(self.percent_blocked, 1),
        }
        if self.oldest_open is not None:
            result["oldest_open"] = {
                "id": self.oldest_open.issue_id,
                "title": self.oldest_open.title,
                "age_days": self.oldest_open_age_days,
            }
        else:
            result["oldest_open"] = None
        return result


def _issue_age_days(issue: IssueInfo) -> int | None:
    """Return age in days for an issue using captured_at → discovered_date → mtime fallback."""
    from little_loops.cli.issues.search import _parse_discovered_date

    try:
        content = issue.path.read_text(encoding="utf-8")
    except OSError:
        return None

    dt = _parse_discovered_date(content, issue.path)
    if dt is None:
        return None
    delta = datetime.now() - dt
    return max(0, delta.days)


def compute_epic_progress(
    epic_id: str,
    all_issues: list[IssueInfo],
) -> EpicProgress | None:
    """Compute progress aggregates for an EPIC from all loaded issues.

    Resolution uses union of ``relates_to:`` (forward) + ``parent:`` (backward), deduplicated.
    All statuses (including done/cancelled/deferred) are included in totals.

    Returns None when the EPIC ID is not found in all_issues.
    """
    epic_id = epic_id.upper()

    epic_matches = [i for i in all_issues if i.issue_id == epic_id]
    if not epic_matches:
        return None
    epic_info = epic_matches[0]

    forward_ids: set[str] = set(epic_info.relates_to)
    backward_ids: set[str] = {i.issue_id for i in all_issues if i.parent == epic_id}
    child_ids = forward_ids | backward_ids

    children = [i for i in all_issues if i.issue_id in child_ids]

    by_status: dict[str, int] = {}
    for child in children:
        s = child.status
        by_status[s] = by_status.get(s, 0) + 1

    total = len(children)
    done_count = sum(by_status.get(s, 0) for s in _TERMINAL_STATUSES)
    blocked_count = by_status.get("blocked", 0)

    percent_done = (done_count / total * 100) if total > 0 else 0.0
    percent_blocked = (blocked_count / total * 100) if total > 0 else 0.0

    open_children = [c for c in children if c.status in _OPEN_STATUSES]

    oldest_open: IssueInfo | None = None
    oldest_open_age_days: int | None = None

    if open_children:
        aged = [((_issue_age_days(c) or -1), c) for c in open_children]
        aged.sort(key=lambda x: -x[0])
        best_age, oldest_open = aged[0]
        oldest_open_age_days = best_age if best_age >= 0 else None

    return EpicProgress(
        epic_id=epic_id,
        epic_title=epic_info.title,
        children=children,
        by_status=by_status,
        percent_done=percent_done,
        percent_blocked=percent_blocked,
        oldest_open=oldest_open,
        oldest_open_age_days=oldest_open_age_days,
    )
