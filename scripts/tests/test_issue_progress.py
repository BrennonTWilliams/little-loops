"""Unit tests for issue_progress.compute_epic_progress()."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from little_loops.issue_progress import compute_epic_progress


def _make_issue(
    tmp_path: Path,
    issue_id: str,
    status: str = "open",
    parent: str | None = None,
    relates_to: list[str] | None = None,
    blocked_by: list[str] | None = None,
    captured_at: str | None = None,
    title: str | None = None,
) -> Any:
    """Create a minimal IssueInfo-like object backed by a real temp file."""
    from little_loops.issue_parser import IssueInfo

    parts = issue_id.split("-")
    issue_type = parts[0]
    priority = "P2"

    title = title or f"{issue_id} title"
    frontmatter_lines = [f"status: {status}"]
    if parent:
        frontmatter_lines.append(f"parent: {parent}")
    if relates_to:
        frontmatter_lines.append("relates_to:")
        for r in relates_to:
            frontmatter_lines.append(f"  - {r}")
    if blocked_by:
        frontmatter_lines.append("blocked_by:")
        for b in blocked_by:
            frontmatter_lines.append(f"  - {b}")
    if captured_at:
        frontmatter_lines.append(f"captured_at: '{captured_at}'")

    content = "---\n" + "\n".join(frontmatter_lines) + "\n---\n" + f"# {issue_id}: {title}\n"

    subdir = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements", "EPIC": "epics"}.get(
        issue_type, "bugs"
    )
    issues_dir = tmp_path / ".issues" / subdir
    issues_dir.mkdir(parents=True, exist_ok=True)
    file_path = issues_dir / f"{priority}-{issue_id}-{title.lower().replace(' ', '-')}.md"
    file_path.write_text(content)

    return IssueInfo(
        path=file_path,
        issue_type=issue_type,
        priority=priority,
        issue_id=issue_id,
        title=title,
        status=status,
        parent=parent,
        relates_to=relates_to or [],
        blocked_by=blocked_by or [],
    )


class TestComputeEpicProgress:
    def test_epic_not_found_returns_none(self, tmp_path: Path) -> None:
        issues = [_make_issue(tmp_path, "BUG-001")]
        result = compute_epic_progress("EPIC-999", issues)
        assert result is None

    def test_epic_no_children_returns_empty_progress(self, tmp_path: Path) -> None:
        epic = _make_issue(tmp_path, "EPIC-001", title="my epic")
        result = compute_epic_progress("EPIC-001", [epic])
        assert result is not None
        assert result.epic_id == "EPIC-001"
        assert result.epic_title == "my epic"
        assert result.children == []
        assert result.by_status == {}
        assert result.percent_done == 0.0
        assert result.percent_blocked == 0.0
        assert result.oldest_open is None
        assert result.oldest_open_age_days is None

    def test_backward_resolution_via_parent(self, tmp_path: Path) -> None:
        epic = _make_issue(tmp_path, "EPIC-001")
        child1 = _make_issue(tmp_path, "BUG-010", parent="EPIC-001")
        child2 = _make_issue(tmp_path, "ENH-011", parent="EPIC-001")
        unrelated = _make_issue(tmp_path, "FEAT-020")

        result = compute_epic_progress("EPIC-001", [epic, child1, child2, unrelated])
        assert result is not None
        child_ids = {c.issue_id for c in result.children}
        assert child_ids == {"BUG-010", "ENH-011"}

    def test_forward_resolution_via_relates_to(self, tmp_path: Path) -> None:
        # relates_to is a cross-reference field, not a child edge — should not contribute to children
        epic = _make_issue(tmp_path, "EPIC-002", relates_to=["FEAT-030", "ENH-040"])
        feat = _make_issue(tmp_path, "FEAT-030")
        enh = _make_issue(tmp_path, "ENH-040")

        result = compute_epic_progress("EPIC-002", [epic, feat, enh])
        assert result is not None
        assert result.children == []

    def test_union_deduplication(self, tmp_path: Path) -> None:
        # Only parent: back-reference counts; relates_to on the EPIC is ignored
        epic = _make_issue(tmp_path, "EPIC-003", relates_to=["BUG-001"])
        bug = _make_issue(tmp_path, "BUG-001", parent="EPIC-003")

        result = compute_epic_progress("EPIC-003", [epic, bug])
        assert result is not None
        assert len(result.children) == 1

    def test_all_done_100_percent(self, tmp_path: Path) -> None:
        epic = _make_issue(tmp_path, "EPIC-004")
        b1 = _make_issue(tmp_path, "BUG-002", status="done", parent="EPIC-004")
        b2 = _make_issue(tmp_path, "BUG-003", status="cancelled", parent="EPIC-004")

        result = compute_epic_progress("EPIC-004", [epic, b1, b2])
        assert result is not None
        assert result.percent_done == 100.0
        assert result.by_status.get("done", 0) == 1
        assert result.by_status.get("cancelled", 0) == 1

    def test_mixed_statuses(self, tmp_path: Path) -> None:
        epic = _make_issue(tmp_path, "EPIC-005")
        b1 = _make_issue(tmp_path, "BUG-010", status="done", parent="EPIC-005")
        b2 = _make_issue(tmp_path, "BUG-011", status="open", parent="EPIC-005")
        b3 = _make_issue(tmp_path, "BUG-012", status="blocked", parent="EPIC-005")

        result = compute_epic_progress("EPIC-005", [epic, b1, b2, b3])
        assert result is not None
        assert result.by_status["done"] == 1
        assert result.by_status["open"] == 1
        assert result.by_status["blocked"] == 1
        assert abs(result.percent_done - 33.3) < 1.0
        assert abs(result.percent_blocked - 33.3) < 1.0

    def test_blocked_only_no_open(self, tmp_path: Path) -> None:
        epic = _make_issue(tmp_path, "EPIC-006")
        blocked = _make_issue(
            tmp_path, "BUG-020", status="blocked", parent="EPIC-006", blocked_by=["BUG-099"]
        )

        result = compute_epic_progress("EPIC-006", [epic, blocked])
        assert result is not None
        assert result.percent_blocked == 100.0
        assert result.oldest_open is not None
        assert result.oldest_open.issue_id == "BUG-020"

    def test_done_children_included_in_totals(self, tmp_path: Path) -> None:
        epic = _make_issue(tmp_path, "EPIC-007")
        b1 = _make_issue(tmp_path, "BUG-030", status="done", parent="EPIC-007")
        b2 = _make_issue(tmp_path, "BUG-031", status="done", parent="EPIC-007")
        b3 = _make_issue(tmp_path, "BUG-032", status="open", parent="EPIC-007")

        result = compute_epic_progress("EPIC-007", [epic, b1, b2, b3])
        assert result is not None
        assert len(result.children) == 3
        assert abs(result.percent_done - 66.7) < 1.0

    def test_oldest_open_prefers_captured_at(self, tmp_path: Path) -> None:
        epic = _make_issue(tmp_path, "EPIC-008")
        newer = _make_issue(
            tmp_path, "BUG-040", status="open", parent="EPIC-008", captured_at="2026-05-01T00:00:00Z"
        )
        older = _make_issue(
            tmp_path, "BUG-041", status="open", parent="EPIC-008", captured_at="2026-01-01T00:00:00Z"
        )

        result = compute_epic_progress("EPIC-008", [epic, newer, older])
        assert result is not None
        assert result.oldest_open is not None
        assert result.oldest_open.issue_id == "BUG-041"

    def test_oldest_open_age_days_is_non_negative(self, tmp_path: Path) -> None:
        epic = _make_issue(tmp_path, "EPIC-009")
        child = _make_issue(
            tmp_path, "BUG-050", status="open", parent="EPIC-009", captured_at="2020-01-01T00:00:00Z"
        )

        result = compute_epic_progress("EPIC-009", [epic, child])
        assert result is not None
        assert result.oldest_open_age_days is not None
        assert result.oldest_open_age_days > 0

    def test_oldest_open_none_when_all_terminal(self, tmp_path: Path) -> None:
        epic = _make_issue(tmp_path, "EPIC-010")
        child = _make_issue(tmp_path, "BUG-060", status="done", parent="EPIC-010")

        result = compute_epic_progress("EPIC-010", [epic, child])
        assert result is not None
        assert result.oldest_open is None
        assert result.oldest_open_age_days is None

    def test_to_dict_structure(self, tmp_path: Path) -> None:
        epic = _make_issue(tmp_path, "EPIC-011")
        child = _make_issue(tmp_path, "BUG-070", status="open", parent="EPIC-011")

        result = compute_epic_progress("EPIC-011", [epic, child])
        assert result is not None
        d = result.to_dict()
        assert d["epic_id"] == "EPIC-011"
        assert d["total"] == 1
        assert "by_status" in d
        assert "percent_done" in d
        assert "percent_blocked" in d
        assert "oldest_open" in d
        # Verify it's JSON-serializable
        json.dumps(d)

    def test_deferred_children_included_unlike_sprint(self, tmp_path: Path) -> None:
        epic = _make_issue(tmp_path, "EPIC-012")
        deferred = _make_issue(tmp_path, "BUG-080", status="deferred", parent="EPIC-012")
        active = _make_issue(tmp_path, "BUG-081", status="open", parent="EPIC-012")

        result = compute_epic_progress("EPIC-012", [epic, deferred, active])
        assert result is not None
        assert len(result.children) == 2
        assert result.by_status.get("deferred", 0) == 1

    def test_epic_id_case_insensitive(self, tmp_path: Path) -> None:
        epic = _make_issue(tmp_path, "EPIC-013")
        result_upper = compute_epic_progress("EPIC-013", [epic])
        result_lower = compute_epic_progress("epic-013", [epic])
        assert result_upper is not None
        assert result_lower is not None
        assert result_upper.epic_id == result_lower.epic_id
