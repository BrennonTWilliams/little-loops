"""Overlap detection for parallel issue processing.

Tracks active issue scopes and detects potential file modification conflicts
before dispatch to reduce merge conflicts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import RLock
from typing import TYPE_CHECKING

from little_loops.parallel.file_hints import FileHints, extract_file_hints

if TYPE_CHECKING:
    from little_loops.issue_parser import IssueInfo

logger = logging.getLogger(__name__)


@dataclass
class OverlapResult:
    """Result of an overlap check.

    Attributes:
        has_overlap: Whether overlap was detected
        overlapping_issues: Issue IDs that overlap
        overlapping_files: Specific files/paths that overlap
    """

    has_overlap: bool = False
    overlapping_issues: list[str] = field(default_factory=list)
    overlapping_files: set[str] = field(default_factory=set)

    def __bool__(self) -> bool:
        """Allow using result directly in boolean context."""
        return self.has_overlap


class OverlapDetector:
    """Detects overlapping file modifications between parallel issues.

    Thread-safe tracking of which issues are currently being processed
    and what files they're expected to modify based on issue content analysis.

    Usage:
        detector = OverlapDetector()

        # Check before dispatch
        result = detector.check_overlap(new_issue)
        if result:
            # Handle overlap (serialize, warn, etc.)
            pass
        else:
            detector.register_issue(new_issue)

        # After completion
        detector.unregister_issue(issue_id)
    """

    def __init__(self) -> None:
        """Initialize the overlap detector."""
        self._lock = RLock()
        self._active_hints: dict[str, FileHints] = {}

    def register_issue(self, issue: IssueInfo) -> FileHints:
        """Register an issue as actively being processed.

        Args:
            issue: Issue being processed

        Returns:
            FileHints extracted from the issue
        """
        with self._lock:
            content = issue.path.read_text() if issue.path.exists() else ""
            hints = extract_file_hints(content, issue.issue_id)
            self._active_hints[issue.issue_id] = hints
            logger.debug(
                f"Registered {issue.issue_id} with hints: "
                f"files={hints.files}, dirs={hints.directories}, scopes={hints.scopes}"
            )
            return hints

    def unregister_issue(self, issue_id: str) -> None:
        """Unregister an issue when processing completes.

        Args:
            issue_id: ID of the completed issue
        """
        with self._lock:
            if issue_id in self._active_hints:
                del self._active_hints[issue_id]
                logger.debug(f"Unregistered {issue_id}")

    def check_overlap(self, issue: IssueInfo) -> OverlapResult:
        """Check if an issue overlaps with any active issues.

        Does NOT register the issue - call register_issue separately after
        deciding to proceed.

        Args:
            issue: Issue to check

        Returns:
            OverlapResult with overlap details
        """
        with self._lock:
            content = issue.path.read_text() if issue.path.exists() else ""
            new_hints = extract_file_hints(content, issue.issue_id)

            result = OverlapResult()

            for active_id, active_hints in self._active_hints.items():
                if new_hints.overlaps_with(active_hints):
                    result.has_overlap = True
                    result.overlapping_issues.append(active_id)
                    # Find specific overlapping paths
                    result.overlapping_files.update(new_hints.files & active_hints.files)
                    result.overlapping_files.update(
                        new_hints.directories & active_hints.directories
                    )

            if result.has_overlap:
                overlap_desc = (
                    result.overlapping_files if result.overlapping_files else "scope/directory overlap"
                )
                logger.info(
                    f"{issue.issue_id} overlaps with {result.overlapping_issues}: {overlap_desc}"
                )

            return result

    def get_active_issues(self) -> list[str]:
        """Get list of currently active issue IDs.

        Returns:
            List of active issue IDs
        """
        with self._lock:
            return list(self._active_hints.keys())

    def get_hints(self, issue_id: str) -> FileHints | None:
        """Get hints for a registered issue.

        Args:
            issue_id: Issue ID to look up

        Returns:
            FileHints if registered, None otherwise
        """
        with self._lock:
            return self._active_hints.get(issue_id)

    def clear(self) -> None:
        """Clear all tracked issues."""
        with self._lock:
            self._active_hints.clear()
            logger.debug("Cleared all overlap tracking")
