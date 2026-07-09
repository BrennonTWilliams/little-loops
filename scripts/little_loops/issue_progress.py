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


def build_parent_map(all_issues: list[IssueInfo]) -> dict[str, str | None]:
    """Build ``{issue_id: parent_id}`` from an in-memory issue list.

    The in-memory analog of ``WorkerPool._build_parent_map`` (which scans
    ``.issues/`` from disk). Retains ``None``-valued parents so the shape matches
    the disk-scan builder; ``find_nearest_epic_ancestor`` / ``_issue_descends_to``
    treat a ``None`` value identically to a missing key (``.get()`` returns
    ``None`` and the ``while current`` guard halts), so retaining them is
    behavior-preserving.
    """
    return {i.issue_id: i.parent for i in all_issues}


def find_nearest_epic_ancestor(
    issue: IssueInfo,
    parent_map: dict[str, str | None],
) -> str | None:
    """Walk ``issue.parent`` chain upward; return nearest ``EPIC-*`` ID or None.

    Cycle-guarded via a ``seen`` set (mirrors the shape of
    ``cli/issues/list_cmd.py::_find_epic_ancestor``). Stops at the first ancestor
    whose ID starts with the ``EPIC`` prefix. The caller supplies ``parent_map``
    (via ``build_parent_map`` for in-memory lists, or a disk-scan builder) — this
    function performs no filesystem access.
    """
    if not issue.parent:
        return None
    seen: set[str] = set()
    current: str | None = issue.parent
    while current and current not in seen:
        seen.add(current)
        if current.split("-", 1)[0] == "EPIC":
            return current
        current = parent_map.get(current)
    return None


def _issue_descends_to(issue_id: str, epic_id: str, parent_map: dict[str, str | None]) -> bool:
    """Walk parent chain upward; True iff `issue_id` (transitively) parents to `epic_id`.

    Cycle-safe via a `seen` guard matching the pattern in
    `cli/issues/list_cmd.py::_find_epic_ancestor`.
    """
    seen: set[str] = set()
    current = parent_map.get(issue_id)
    while current and current not in seen:
        if current == epic_id:
            return True
        seen.add(current)
        current = parent_map.get(current)
    return False


def compute_epic_progress(
    epic_id: str,
    all_issues: list[IssueInfo],
) -> EpicProgress | None:
    """Compute progress aggregates for an EPIC from all loaded issues.

    Child resolution walks the ``parent:`` chain transitively (cycle-guarded),
    mirroring ``cli/issues/list_cmd.py::_find_epic_ancestor`` so an issue
    nests under an EPIC even if its immediate parent is a (done) intermediate
    FEAT. ``relates_to:`` is a cross-reference field (siblings, dependencies)
    and is intentionally excluded to avoid inflating counts with non-child
    references. All statuses (including done/cancelled/deferred) are included
    in totals.

    Returns None when the EPIC ID is not found in all_issues.
    """
    epic_id = epic_id.upper()

    epic_matches = [i for i in all_issues if i.issue_id == epic_id]
    if not epic_matches:
        return None
    epic_info = epic_matches[0]

    parent_map = build_parent_map(all_issues)
    child_ids: set[str] = {
        i.issue_id
        for i in all_issues
        if i.issue_id != epic_id and _issue_descends_to(i.issue_id, epic_id, parent_map)
    }

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
