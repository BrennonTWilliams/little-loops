"""little-loops: Development workflow toolkit for Claude Code.

This package provides automation tools for issue management, code quality checks,
and development workflows that can be configured for any software project.
"""

from little_loops.config import BRConfig
from little_loops.git_operations import check_git_status
from little_loops.issue_lifecycle import (
    FailureType,
    classify_failure,
    close_issue,
    complete_issue_lifecycle,
    create_issue_from_failure,
    verify_issue_completed,
)
from little_loops.issue_manager import AutoManager
from little_loops.sync import GitHubSyncManager, SyncResult, SyncStatus
from little_loops.work_verification import (
    EXCLUDED_DIRECTORIES,
    filter_excluded_files,
    verify_work_was_done,
)

__version__ = "1.12.2"
__all__ = [
    "BRConfig",
    # git_operations
    "check_git_status",
    # work_verification
    "EXCLUDED_DIRECTORIES",
    "filter_excluded_files",
    "verify_work_was_done",
    # issue_lifecycle
    "FailureType",
    "classify_failure",
    "close_issue",
    "complete_issue_lifecycle",
    "create_issue_from_failure",
    "verify_issue_completed",
    # issue_manager
    "AutoManager",
    # sync
    "GitHubSyncManager",
    "SyncResult",
    "SyncStatus",
]
