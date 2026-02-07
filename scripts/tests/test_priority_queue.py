"""Tests for little_loops.parallel.priority_queue module.

Tests cover:
- IssuePriorityQueue initialization
- add() and add_many() operations
- get() with blocking/non-blocking modes
- State transitions (mark_completed, mark_failed, requeue)
- State properties and counts
- Thread safety under concurrent access
- State persistence (load_completed, load_failed)
- scan_issues() integration with BRConfig
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.issue_parser import IssueInfo
from little_loops.parallel.priority_queue import IssuePriorityQueue

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def queue() -> IssuePriorityQueue:
    """Fresh IssuePriorityQueue instance."""
    return IssuePriorityQueue()


@pytest.fixture
def sample_issue() -> IssueInfo:
    """Create a sample IssueInfo for testing."""
    return IssueInfo(
        path=Path(".issues/bugs/P1-BUG-001-test.md"),
        issue_type="bugs",
        priority="P1",
        issue_id="BUG-001",
        title="Test Bug",
    )


@pytest.fixture
def p0_issue() -> IssueInfo:
    """P0 priority issue."""
    return IssueInfo(
        path=Path(".issues/bugs/P0-BUG-010-critical.md"),
        issue_type="bugs",
        priority="P0",
        issue_id="BUG-010",
        title="Critical Bug",
    )


@pytest.fixture
def p1_issue() -> IssueInfo:
    """P1 priority issue."""
    return IssueInfo(
        path=Path(".issues/bugs/P1-BUG-011-high.md"),
        issue_type="bugs",
        priority="P1",
        issue_id="BUG-011",
        title="High Priority Bug",
    )


@pytest.fixture
def p2_issue() -> IssueInfo:
    """P2 priority issue."""
    return IssueInfo(
        path=Path(".issues/features/P2-FEAT-001-feature.md"),
        issue_type="features",
        priority="P2",
        issue_id="FEAT-001",
        title="New Feature",
    )


@pytest.fixture
def p5_issue() -> IssueInfo:
    """P5 (lowest) priority issue."""
    return IssueInfo(
        path=Path(".issues/features/P5-FEAT-002-low.md"),
        issue_type="features",
        priority="P5",
        issue_id="FEAT-002",
        title="Low Priority Feature",
    )


@pytest.fixture
def sample_issues(p0_issue: IssueInfo, p1_issue: IssueInfo, p2_issue: IssueInfo) -> list[IssueInfo]:
    """Multiple issues with different priorities."""
    return [p1_issue, p0_issue, p2_issue]  # Intentionally unordered


# =============================================================================
# TestIssuePriorityQueueInit
# =============================================================================


class TestIssuePriorityQueueInit:
    """Tests for IssuePriorityQueue initialization."""

    def test_init_creates_empty_queue(self, queue: IssuePriorityQueue) -> None:
        """Queue starts empty with qsize() == 0."""
        assert queue.qsize() == 0

    def test_init_empty_returns_true(self, queue: IssuePriorityQueue) -> None:
        """Queue starts empty."""
        assert queue.empty() is True

    def test_init_no_in_progress(self, queue: IssuePriorityQueue) -> None:
        """No issues in progress initially."""
        assert queue.in_progress_count == 0
        assert queue.in_progress_ids == []

    def test_init_no_completed(self, queue: IssuePriorityQueue) -> None:
        """No issues completed initially."""
        assert queue.completed_count == 0
        assert queue.completed_ids == []

    def test_init_no_failed(self, queue: IssuePriorityQueue) -> None:
        """No issues failed initially."""
        assert queue.failed_count == 0
        assert queue.failed_ids == []

    def test_default_priorities_p0_to_p5(self) -> None:
        """DEFAULT_PRIORITIES contains P0 through P5."""
        expected = ["P0", "P1", "P2", "P3", "P4", "P5"]
        assert IssuePriorityQueue.DEFAULT_PRIORITIES == expected


# =============================================================================
# TestIssuePriorityQueueAdd
# =============================================================================


class TestIssuePriorityQueueAdd:
    """Tests for add() method."""

    def test_add_single_issue_returns_true(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Adding new issue returns True."""
        result = queue.add(sample_issue)
        assert result is True

    def test_add_increases_qsize(self, queue: IssuePriorityQueue, sample_issue: IssueInfo) -> None:
        """Issue is added and qsize increases."""
        assert queue.qsize() == 0
        queue.add(sample_issue)
        assert queue.qsize() == 1

    def test_add_makes_queue_non_empty(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Queue is no longer empty after add."""
        queue.add(sample_issue)
        assert queue.empty() is False

    def test_add_already_queued_returns_false(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Adding duplicate returns False."""
        queue.add(sample_issue)
        result = queue.add(sample_issue)
        assert result is False

    def test_add_duplicate_doesnt_increase_qsize(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Duplicate add does not increase queue size."""
        queue.add(sample_issue)
        queue.add(sample_issue)
        assert queue.qsize() == 1

    def test_add_in_progress_returns_false(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Cannot add issue that is currently being processed."""
        queue.add(sample_issue)
        queue.get()  # Move to in_progress
        result = queue.add(sample_issue)
        assert result is False

    def test_add_completed_returns_false(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Cannot add completed issue."""
        queue.add(sample_issue)
        queue.get()
        queue.mark_completed(sample_issue.issue_id)
        result = queue.add(sample_issue)
        assert result is False

    def test_add_failed_returns_false(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Cannot add failed issue."""
        queue.add(sample_issue)
        queue.get()
        queue.mark_failed(sample_issue.issue_id)
        result = queue.add(sample_issue)
        assert result is False


# =============================================================================
# TestIssuePriorityQueueAddMany
# =============================================================================


class TestIssuePriorityQueueAddMany:
    """Tests for add_many() method."""

    def test_add_many_returns_count(
        self, queue: IssuePriorityQueue, sample_issues: list[IssueInfo]
    ) -> None:
        """Returns number of successfully added issues."""
        count = queue.add_many(sample_issues)
        assert count == 3

    def test_add_many_increases_qsize(
        self, queue: IssuePriorityQueue, sample_issues: list[IssueInfo]
    ) -> None:
        """Queue size matches number added."""
        queue.add_many(sample_issues)
        assert queue.qsize() == 3

    def test_add_many_skips_duplicates(
        self, queue: IssuePriorityQueue, sample_issues: list[IssueInfo]
    ) -> None:
        """Duplicate issues not added, count reflects actual."""
        queue.add(sample_issues[0])  # Add first one manually
        count = queue.add_many(sample_issues)  # Try to add all
        assert count == 2  # Only 2 new ones added

    def test_add_many_empty_iterable(self, queue: IssuePriorityQueue) -> None:
        """Empty iterable returns 0."""
        count = queue.add_many([])
        assert count == 0
        assert queue.qsize() == 0


# =============================================================================
# TestIssuePriorityQueueGet
# =============================================================================


class TestIssuePriorityQueueGet:
    """Tests for get() method."""

    def test_get_returns_queued_issue(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Get returns a QueuedIssue."""
        queue.add(sample_issue)
        result = queue.get(block=False)
        assert result is not None
        assert result.issue_info == sample_issue

    def test_get_returns_highest_priority(
        self, queue: IssuePriorityQueue, sample_issues: list[IssueInfo]
    ) -> None:
        """P0 returned before P1, P1 before P2."""
        queue.add_many(sample_issues)
        first = queue.get(block=False)
        second = queue.get(block=False)
        third = queue.get(block=False)
        assert first is not None
        assert second is not None
        assert third is not None
        assert first.issue_info.priority == "P0"
        assert second.issue_info.priority == "P1"
        assert third.issue_info.priority == "P2"

    def test_get_fifo_within_same_priority(self, queue: IssuePriorityQueue) -> None:
        """Earlier additions returned first for same priority."""
        issue1 = IssueInfo(Path("a.md"), "bugs", "P1", "BUG-A", "First")
        issue2 = IssueInfo(Path("b.md"), "bugs", "P1", "BUG-B", "Second")
        queue.add(issue1)
        time.sleep(0.001)  # Ensure different timestamps
        queue.add(issue2)

        first = queue.get(block=False)
        second = queue.get(block=False)
        assert first is not None
        assert second is not None
        assert first.issue_info.issue_id == "BUG-A"
        assert second.issue_info.issue_id == "BUG-B"

    def test_get_moves_to_in_progress(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Retrieved issue moves to in_progress."""
        queue.add(sample_issue)
        queue.get(block=False)
        assert queue.in_progress_count == 1
        assert sample_issue.issue_id in queue.in_progress_ids

    def test_get_non_blocking_empty_returns_none(self, queue: IssuePriorityQueue) -> None:
        """get(block=False) returns None on empty queue."""
        result = queue.get(block=False)
        assert result is None

    def test_get_with_timeout_returns_none(self, queue: IssuePriorityQueue) -> None:
        """get(timeout=0.01) returns None on empty queue."""
        result = queue.get(block=True, timeout=0.01)
        assert result is None

    def test_get_decrements_qsize(self, queue: IssuePriorityQueue, sample_issue: IssueInfo) -> None:
        """Queue size decreases after get()."""
        queue.add(sample_issue)
        assert queue.qsize() == 1
        queue.get(block=False)
        assert queue.qsize() == 0


# =============================================================================
# TestIssuePriorityQueueStateTransitions
# =============================================================================


class TestIssuePriorityQueueStateTransitions:
    """Tests for mark_completed(), mark_failed(), and requeue()."""

    def test_mark_completed_removes_from_in_progress(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Issue removed from in_progress set."""
        queue.add(sample_issue)
        queue.get()
        assert queue.in_progress_count == 1
        queue.mark_completed(sample_issue.issue_id)
        assert queue.in_progress_count == 0

    def test_mark_completed_adds_to_completed(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Issue added to completed set."""
        queue.add(sample_issue)
        queue.get()
        queue.mark_completed(sample_issue.issue_id)
        assert sample_issue.issue_id in queue.completed_ids

    def test_mark_completed_increments_count(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """completed_count increases."""
        queue.add(sample_issue)
        queue.get()
        queue.mark_completed(sample_issue.issue_id)
        assert queue.completed_count == 1

    def test_mark_failed_removes_from_in_progress(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Issue removed from in_progress set."""
        queue.add(sample_issue)
        queue.get()
        queue.mark_failed(sample_issue.issue_id)
        assert queue.in_progress_count == 0

    def test_mark_failed_adds_to_failed(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Issue added to failed set."""
        queue.add(sample_issue)
        queue.get()
        queue.mark_failed(sample_issue.issue_id)
        assert sample_issue.issue_id in queue.failed_ids

    def test_mark_failed_increments_count(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """failed_count increases."""
        queue.add(sample_issue)
        queue.get()
        queue.mark_failed(sample_issue.issue_id)
        assert queue.failed_count == 1

    def test_requeue_removes_from_in_progress(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Requeued issue removed from in_progress."""
        queue.add(sample_issue)
        queue.get()
        queue.requeue(sample_issue)
        assert queue.in_progress_count == 0

    def test_requeue_adds_to_queue(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Requeued issue back in queue."""
        queue.add(sample_issue)
        queue.get()
        assert queue.qsize() == 0
        queue.requeue(sample_issue)
        assert queue.qsize() == 1

    def test_requeue_without_demote_keeps_priority(
        self, queue: IssuePriorityQueue, p1_issue: IssueInfo
    ) -> None:
        """Priority unchanged when demote_priority=False."""
        queue.add(p1_issue)
        queue.get()
        queue.requeue(p1_issue, demote_priority=False)
        result = queue.get(block=False)
        assert result is not None
        assert result.priority == 1  # Still P1

    def test_requeue_with_demote_lowers_priority(
        self, queue: IssuePriorityQueue, p1_issue: IssueInfo
    ) -> None:
        """P1 becomes P2 when demote_priority=True."""
        queue.add(p1_issue)
        queue.get()
        queue.requeue(p1_issue, demote_priority=True)
        result = queue.get(block=False)
        assert result is not None
        assert result.priority == 2  # Demoted to P2

    def test_requeue_demote_caps_at_p5(
        self, queue: IssuePriorityQueue, p5_issue: IssueInfo
    ) -> None:
        """P5 stays P5, doesn't go to P6."""
        queue.add(p5_issue)
        queue.get()
        queue.requeue(p5_issue, demote_priority=True)
        result = queue.get(block=False)
        assert result is not None
        assert result.priority == 5  # Still P5, not P6

    def test_requeue_removes_from_failed(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Requeued issue removed from failed set."""
        queue.add(sample_issue)
        queue.get()
        queue.mark_failed(sample_issue.issue_id)
        assert sample_issue.issue_id in queue.failed_ids
        queue.requeue(sample_issue)
        assert sample_issue.issue_id not in queue.failed_ids


# =============================================================================
# TestIssuePriorityQueueProperties
# =============================================================================


class TestIssuePriorityQueueProperties:
    """Tests for count and ID properties."""

    def test_in_progress_ids_returns_list(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """in_progress_ids returns a list."""
        queue.add(sample_issue)
        queue.get()
        ids = queue.in_progress_ids
        assert isinstance(ids, list)

    def test_completed_ids_returns_list(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """completed_ids returns a list."""
        queue.add(sample_issue)
        queue.get()
        queue.mark_completed(sample_issue.issue_id)
        ids = queue.completed_ids
        assert isinstance(ids, list)

    def test_failed_ids_returns_list(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """failed_ids returns a list."""
        queue.add(sample_issue)
        queue.get()
        queue.mark_failed(sample_issue.issue_id)
        ids = queue.failed_ids
        assert isinstance(ids, list)

    def test_counts_match_id_lists(
        self, queue: IssuePriorityQueue, sample_issues: list[IssueInfo]
    ) -> None:
        """Counts match length of ID lists."""
        queue.add_many(sample_issues)
        queue.get()  # 1 in progress
        queue.get()  # 2 in progress
        issue = queue.get()  # 3 in progress
        if issue:
            queue.mark_completed(issue.issue_info.issue_id)

        assert queue.in_progress_count == len(queue.in_progress_ids)
        assert queue.completed_count == len(queue.completed_ids)


# =============================================================================
# TestIssuePriorityQueuePersistence
# =============================================================================


class TestIssuePriorityQueuePersistence:
    """Tests for load_completed() and load_failed()."""

    def test_load_completed_adds_ids(self, queue: IssuePriorityQueue) -> None:
        """load_completed adds IDs to completed set."""
        queue.load_completed(["BUG-001", "BUG-002"])
        assert queue.completed_count == 2
        assert "BUG-001" in queue.completed_ids
        assert "BUG-002" in queue.completed_ids

    def test_load_completed_prevents_add(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Loaded completed IDs rejected by add()."""
        queue.load_completed([sample_issue.issue_id])
        result = queue.add(sample_issue)
        assert result is False

    def test_load_failed_adds_ids(self, queue: IssuePriorityQueue) -> None:
        """load_failed adds IDs to failed set."""
        queue.load_failed(["BUG-003", "BUG-004"])
        assert queue.failed_count == 2
        assert "BUG-003" in queue.failed_ids
        assert "BUG-004" in queue.failed_ids

    def test_load_failed_prevents_add(
        self, queue: IssuePriorityQueue, sample_issue: IssueInfo
    ) -> None:
        """Loaded failed IDs rejected by add()."""
        queue.load_failed([sample_issue.issue_id])
        result = queue.add(sample_issue)
        assert result is False

    def test_load_empty_iterables(self, queue: IssuePriorityQueue) -> None:
        """Loading empty iterables is safe."""
        queue.load_completed([])
        queue.load_failed([])
        assert queue.completed_count == 0
        assert queue.failed_count == 0


# =============================================================================
# TestIssuePriorityQueueThreadSafety
# =============================================================================


class TestIssuePriorityQueueThreadSafety:
    """Tests for thread safety under concurrent access."""

    def test_concurrent_add_operations(self, queue: IssuePriorityQueue) -> None:
        """Multiple threads adding simultaneously."""
        issues = [
            IssueInfo(Path(f"{i}.md"), "bugs", "P1", f"BUG-{i:03d}", f"Bug {i}") for i in range(100)
        ]
        added_count = []

        def add_issues(issue_list: list[IssueInfo]) -> None:
            count = 0
            for issue in issue_list:
                if queue.add(issue):
                    count += 1
            added_count.append(count)

        # Split issues across 4 threads
        threads = []
        for i in range(4):
            subset = issues[i * 25 : (i + 1) * 25]
            t = threading.Thread(target=add_issues, args=(subset,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert queue.qsize() == 100
        assert sum(added_count) == 100

    def test_concurrent_get_operations(
        self, queue: IssuePriorityQueue, sample_issues: list[IssueInfo]
    ) -> None:
        """Multiple threads getting simultaneously."""
        queue.add_many(sample_issues)
        results: list[str] = []
        lock = threading.Lock()

        def get_issue() -> None:
            result = queue.get(block=False)
            if result:
                with lock:
                    results.append(result.issue_info.issue_id)

        threads = [threading.Thread(target=get_issue) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have gotten exactly 3 issues (no duplicates)
        assert len(results) == 3
        assert len(set(results)) == 3  # All unique

    def test_concurrent_state_transitions(self, queue: IssuePriorityQueue) -> None:
        """Mixed operations under contention."""
        issues = [
            IssueInfo(Path(f"{i}.md"), "bugs", "P1", f"BUG-{i:03d}", f"Bug {i}") for i in range(20)
        ]
        queue.add_many(issues)

        def process_issues() -> None:
            while True:
                item = queue.get(block=False)
                if not item:
                    break
                # Randomly complete or fail
                if int(item.issue_info.issue_id.split("-")[1]) % 2 == 0:
                    queue.mark_completed(item.issue_info.issue_id)
                else:
                    queue.mark_failed(item.issue_info.issue_id)

        threads = [threading.Thread(target=process_issues) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All issues should be processed
        assert queue.qsize() == 0
        assert queue.in_progress_count == 0
        assert queue.completed_count + queue.failed_count == 20


# =============================================================================
# TestIssuePriorityQueueScanIssues
# =============================================================================


class TestIssuePriorityQueueScanIssues:
    """Tests for scan_issues() static method."""

    def test_scan_issues_calls_find_issues(self) -> None:
        """scan_issues uses find_issues from issue_parser."""
        mock_config = MagicMock()
        mock_issues = [
            IssueInfo(Path("a.md"), "bugs", "P1", "BUG-001", "Bug 1"),
            IssueInfo(Path("b.md"), "bugs", "P2", "BUG-002", "Bug 2"),
        ]

        with patch(
            "little_loops.parallel.priority_queue.find_issues", return_value=mock_issues
        ) as mock_find:
            result = IssuePriorityQueue.scan_issues(mock_config)

            mock_find.assert_called_once_with(
                mock_config, category=None, skip_ids=set(), only_ids=None
            )
            assert len(result) == 2

    def test_scan_issues_applies_priority_filter(self) -> None:
        """Only specified priorities returned."""
        mock_config = MagicMock()
        mock_issues = [
            IssueInfo(Path("a.md"), "bugs", "P0", "BUG-001", "P0 Bug"),
            IssueInfo(Path("b.md"), "bugs", "P1", "BUG-002", "P1 Bug"),
            IssueInfo(Path("c.md"), "bugs", "P2", "BUG-003", "P2 Bug"),
        ]

        with patch("little_loops.parallel.priority_queue.find_issues", return_value=mock_issues):
            result = IssuePriorityQueue.scan_issues(mock_config, priority_filter=["P0", "P1"])

            assert len(result) == 2
            assert all(i.priority in ["P0", "P1"] for i in result)

    def test_scan_issues_passes_skip_ids(self) -> None:
        """Skip IDs passed to find_issues."""
        mock_config = MagicMock()
        skip = {"BUG-001", "BUG-002"}

        with patch(
            "little_loops.parallel.priority_queue.find_issues", return_value=[]
        ) as mock_find:
            IssuePriorityQueue.scan_issues(mock_config, skip_ids=skip)

            mock_find.assert_called_once()
            call_args = mock_find.call_args
            assert call_args.kwargs["skip_ids"] == skip

    def test_scan_issues_passes_only_ids(self) -> None:
        """Only IDs passed to find_issues."""
        mock_config = MagicMock()
        only = {"BUG-005"}

        with patch(
            "little_loops.parallel.priority_queue.find_issues", return_value=[]
        ) as mock_find:
            IssuePriorityQueue.scan_issues(mock_config, only_ids=only)

            mock_find.assert_called_once()
            call_args = mock_find.call_args
            assert call_args.kwargs["only_ids"] == only

    def test_scan_issues_passes_category(self) -> None:
        """Category passed to find_issues."""
        mock_config = MagicMock()

        with patch(
            "little_loops.parallel.priority_queue.find_issues", return_value=[]
        ) as mock_find:
            IssuePriorityQueue.scan_issues(mock_config, category="bugs")

            mock_find.assert_called_once()
            call_args = mock_find.call_args
            assert call_args.kwargs["category"] == "bugs"

    def test_scan_issues_uses_default_priorities(self) -> None:
        """Without filter, accepts P0-P5."""
        mock_config = MagicMock()
        mock_issues = [
            IssueInfo(Path("a.md"), "bugs", "P3", "BUG-001", "P3 Bug"),
            IssueInfo(Path("b.md"), "bugs", "P5", "BUG-002", "P5 Bug"),
        ]

        with patch("little_loops.parallel.priority_queue.find_issues", return_value=mock_issues):
            result = IssuePriorityQueue.scan_issues(mock_config)

            assert len(result) == 2  # Both P3 and P5 included


# =============================================================================
# Edge Cases
# =============================================================================


class TestIssuePriorityQueueEdgeCases:
    """Edge case tests."""

    def test_mark_completed_nonexistent_id(self, queue: IssuePriorityQueue) -> None:
        """mark_completed on non-existent ID is safe (no-op)."""
        queue.mark_completed("NONEXISTENT-001")  # Should not raise
        assert queue.completed_count == 1  # ID still added to completed

    def test_mark_failed_nonexistent_id(self, queue: IssuePriorityQueue) -> None:
        """mark_failed on non-existent ID is safe (no-op)."""
        queue.mark_failed("NONEXISTENT-002")  # Should not raise
        assert queue.failed_count == 1  # ID still added to failed

    def test_unknown_priority_uses_fallback(self) -> None:
        """Issue with unknown priority gets priority_int 99."""
        issue = IssueInfo(Path("x.md"), "bugs", "PX", "BUG-X", "Unknown Priority")
        assert issue.priority_int == 99

    def test_get_exception_handling(self, queue: IssuePriorityQueue) -> None:
        """get() returns None on queue.Empty exception."""
        # Empty queue with block=False should return None, not raise
        result = queue.get(block=False)
        assert result is None

    def test_get_propagates_non_empty_exceptions(
        self, queue: IssuePriorityQueue
    ) -> None:
        """get() propagates exceptions that aren't queue.Empty."""
        # Mock _queue.get to return an object without issue_info
        bad_item = MagicMock(spec=[])  # no issue_info attribute
        with patch.object(queue._queue, "get", return_value=bad_item):
            with pytest.raises(AttributeError):
                queue.get(block=False)
