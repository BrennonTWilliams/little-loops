"""Thread-safe priority queue for issue processing.

Provides a priority queue implementation that orders issues by priority level
(P0 > P1 > P2 > P3 > P4 > P5) with FIFO ordering within the same priority level.
"""

from __future__ import annotations

import threading
from queue import Empty, PriorityQueue
from typing import TYPE_CHECKING

from little_loops.issue_parser import IssueInfo, find_issues
from little_loops.parallel.types import QueuedIssue

if TYPE_CHECKING:
    from collections.abc import Iterable

    from little_loops.config import BRConfig


class IssuePriorityQueue:
    """Thread-safe priority queue for issues.

    Orders issues by priority (P0=highest) with FIFO within same priority.
    Tracks in-progress and completed issues to prevent duplicate processing.

    Example:
        >>> config = BRConfig(Path.cwd())
        >>> queue = IssuePriorityQueue()
        >>> issues = queue.scan_issues(config)
        >>> queue.add_many(issues)
        >>> issue = queue.get()  # Returns highest priority issue
        >>> queue.mark_completed(issue.issue_info.issue_id)
    """

    # Default priority ordering (P0 highest)
    DEFAULT_PRIORITIES = ["P0", "P1", "P2", "P3", "P4", "P5"]

    def __init__(self) -> None:
        """Initialize the priority queue."""
        self._queue: PriorityQueue[QueuedIssue] = PriorityQueue()
        self._lock = threading.Lock()
        self._queued: set[str] = set()  # Issues currently in queue
        self._in_progress: set[str] = set()
        self._completed: set[str] = set()
        self._failed: set[str] = set()

    def add(self, issue: IssueInfo) -> bool:
        """Add an issue to the queue if not already processed.

        Args:
            issue: Issue information to queue

        Returns:
            True if issue was added, False if already queued/in_progress/completed
        """
        with self._lock:
            if issue.issue_id in self._queued:
                return False
            if issue.issue_id in self._in_progress:
                return False
            if issue.issue_id in self._completed:
                return False
            if issue.issue_id in self._failed:
                return False

            queued = QueuedIssue(
                priority=issue.priority_int,
                issue_info=issue,
            )
            self._queue.put(queued)
            self._queued.add(issue.issue_id)
            return True

    def add_many(self, issues: Iterable[IssueInfo]) -> int:
        """Add multiple issues to the queue.

        Args:
            issues: Iterable of issue information

        Returns:
            Number of issues successfully added
        """
        added = 0
        for issue in issues:
            if self.add(issue):
                added += 1
        return added

    def get(self, block: bool = True, timeout: float | None = None) -> QueuedIssue | None:
        """Get the highest priority issue from the queue.

        Args:
            block: Whether to block waiting for an issue
            timeout: Maximum time to wait (None = forever)

        Returns:
            The highest priority queued issue, or None if queue is empty
        """
        try:
            queued = self._queue.get(block=block, timeout=timeout)
            with self._lock:
                self._queued.discard(queued.issue_info.issue_id)
                self._in_progress.add(queued.issue_info.issue_id)
            return queued
        except Empty:
            return None

    def mark_completed(self, issue_id: str) -> None:
        """Mark an issue as successfully completed.

        Args:
            issue_id: ID of the completed issue
        """
        with self._lock:
            self._in_progress.discard(issue_id)
            self._completed.add(issue_id)

    def mark_failed(self, issue_id: str) -> None:
        """Mark an issue as failed.

        Args:
            issue_id: ID of the failed issue
        """
        with self._lock:
            self._in_progress.discard(issue_id)
            self._failed.add(issue_id)

    def requeue(self, issue: IssueInfo, demote_priority: bool = False) -> None:
        """Requeue an issue (e.g., after merge conflict).

        Args:
            issue: Issue to requeue
            demote_priority: Whether to lower the priority by one level
        """
        with self._lock:
            self._in_progress.discard(issue.issue_id)
            self._failed.discard(issue.issue_id)

            priority = issue.priority_int
            if demote_priority and priority < 5:
                priority += 1

            queued = QueuedIssue(
                priority=priority,
                issue_info=issue,
            )
            self._queue.put(queued)
            self._queued.add(issue.issue_id)

    def empty(self) -> bool:
        """Check if the queue is empty."""
        return self._queue.empty()

    def qsize(self) -> int:
        """Get approximate queue size."""
        return self._queue.qsize()

    @property
    def in_progress_count(self) -> int:
        """Number of issues currently being processed."""
        with self._lock:
            return len(self._in_progress)

    @property
    def completed_count(self) -> int:
        """Number of completed issues."""
        with self._lock:
            return len(self._completed)

    @property
    def failed_count(self) -> int:
        """Number of failed issues."""
        with self._lock:
            return len(self._failed)

    @property
    def in_progress_ids(self) -> list[str]:
        """List of issue IDs currently being processed."""
        with self._lock:
            return list(self._in_progress)

    @property
    def completed_ids(self) -> list[str]:
        """List of completed issue IDs."""
        with self._lock:
            return list(self._completed)

    @property
    def failed_ids(self) -> list[str]:
        """List of failed issue IDs."""
        with self._lock:
            return list(self._failed)

    def load_completed(self, completed: Iterable[str]) -> None:
        """Load previously completed issues (for resume).

        Args:
            completed: Issue IDs that were already completed
        """
        with self._lock:
            self._completed.update(completed)

    def load_failed(self, failed: Iterable[str]) -> None:
        """Load previously failed issues (for resume).

        Args:
            failed: Issue IDs that previously failed
        """
        with self._lock:
            self._failed.update(failed)

    @staticmethod
    def scan_issues(
        config: BRConfig,
        priority_filter: list[str] | None = None,
        skip_ids: set[str] | None = None,
        only_ids: set[str] | None = None,
        category: str | None = None,
    ) -> list[IssueInfo]:
        """Scan issue directories and return sorted issues.

        Uses BRConfig to locate issue directories and determine categories.

        Args:
            config: Project configuration
            priority_filter: Only include these priority levels (default: all)
            skip_ids: Issue IDs to skip
            only_ids: If provided, only include these issue IDs
            category: Optional category filter (e.g., "bugs")

        Returns:
            List of IssueInfo sorted by priority then alphabetically
        """
        skip_ids = skip_ids or set()
        priority_filter = priority_filter or IssuePriorityQueue.DEFAULT_PRIORITIES

        # Use the existing find_issues function from issue_parser
        all_issues = find_issues(config, category=category, skip_ids=skip_ids, only_ids=only_ids)

        # Apply priority filter
        filtered = [i for i in all_issues if i.priority in priority_filter]

        return filtered
