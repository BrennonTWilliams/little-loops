"""Type definitions for parallel issue processing.

Provides dataclasses for worker results, merge requests, orchestrator state,
and parallel configuration. Reuses IssueInfo from issue_parser.py.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.issue_parser import IssueInfo


@dataclass
class QueuedIssue:
    """Issue in priority queue with ordering support.

    Uses __lt__ for priority queue comparison. Lower priority number = higher priority.
    Within same priority level, earlier timestamp wins (FIFO).

    Attributes:
        priority: Numeric priority (0=P0, 1=P1, etc.)
        issue_info: The parsed issue information
        timestamp: When the issue was queued (for FIFO ordering)
    """

    priority: int
    issue_info: IssueInfo
    timestamp: float = field(default_factory=time.time)

    def __lt__(self, other: QueuedIssue) -> bool:
        """Compare issues for priority queue ordering."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "priority": self.priority,
            "issue_info": self.issue_info.to_dict(),
            "timestamp": self.timestamp,
        }


@dataclass
class WorkerResult:
    """Result from a worker processing an issue.

    Attributes:
        issue_id: ID of the processed issue
        success: Whether processing succeeded
        branch_name: Git branch created for this issue
        worktree_path: Path to the worker's git worktree
        changed_files: List of files modified during processing
        leaked_files: Files incorrectly written to main repo instead of worktree
        duration: Processing time in seconds
        error: Error message if processing failed
        stdout: Captured standard output
        stderr: Captured standard error
        was_corrected: Whether the issue file was auto-corrected
        corrections: List of corrections made during validation (for pattern analysis)
        should_close: Whether the issue should be closed (not implemented)
        close_reason: Reason code for closure (e.g., "already_fixed")
        close_status: Status text for closure (e.g., "Closed - Already Fixed")
        interrupted: Whether the worker was interrupted during shutdown
    """

    issue_id: str
    success: bool
    branch_name: str
    worktree_path: Path
    changed_files: list[str] = field(default_factory=list)
    leaked_files: list[str] = field(default_factory=list)
    duration: float = 0.0
    error: str | None = None
    stdout: str = ""
    stderr: str = ""
    was_corrected: bool = False
    corrections: list[str] = field(default_factory=list)
    should_close: bool = False
    close_reason: str | None = None
    close_status: str | None = None
    interrupted: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "issue_id": self.issue_id,
            "success": self.success,
            "branch_name": self.branch_name,
            "worktree_path": str(self.worktree_path),
            "changed_files": self.changed_files,
            "leaked_files": self.leaked_files,
            "duration": self.duration,
            "error": self.error,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "was_corrected": self.was_corrected,
            "corrections": self.corrections,
            "should_close": self.should_close,
            "close_reason": self.close_reason,
            "close_status": self.close_status,
            "interrupted": self.interrupted,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkerResult:
        """Create from dictionary (JSON deserialization)."""
        return cls(
            issue_id=data["issue_id"],
            success=data["success"],
            branch_name=data["branch_name"],
            worktree_path=Path(data["worktree_path"]),
            changed_files=data.get("changed_files", []),
            leaked_files=data.get("leaked_files", []),
            duration=data.get("duration", 0.0),
            error=data.get("error"),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            was_corrected=data.get("was_corrected", False),
            corrections=data.get("corrections", []),
            should_close=data.get("should_close", False),
            close_reason=data.get("close_reason"),
            close_status=data.get("close_status"),
            interrupted=data.get("interrupted", False),
        )


class MergeStatus(Enum):
    """Status of a merge operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    CONFLICT = "conflict"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class MergeRequest:
    """Request to merge a completed worker's changes.

    Attributes:
        worker_result: The result from the worker
        status: Current merge status
        retry_count: Number of merge/rebase attempts
        error: Error message if merge failed
        queued_at: When the merge was requested
    """

    worker_result: WorkerResult
    status: MergeStatus = MergeStatus.PENDING
    retry_count: int = 0
    error: str | None = None
    queued_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "worker_result": self.worker_result.to_dict(),
            "status": self.status.value,
            "retry_count": self.retry_count,
            "error": self.error,
            "queued_at": self.queued_at,
        }


@dataclass
class OrchestratorState:
    """Persistent state for the parallel orchestrator.

    Enables resume capability after interruption.

    Attributes:
        in_progress_issues: Issues currently being processed by workers
        completed_issues: Successfully completed issue IDs
        failed_issues: Mapping of issue ID to failure reason
        pending_merges: Issues awaiting merge
        timing: Per-issue timing breakdown
        corrections: Mapping of issue ID to list of corrections made (for pattern analysis)
        started_at: When orchestration started
        last_checkpoint: Last state save timestamp
    """

    in_progress_issues: list[str] = field(default_factory=list)
    completed_issues: list[str] = field(default_factory=list)
    failed_issues: dict[str, str] = field(default_factory=dict)
    pending_merges: list[str] = field(default_factory=list)
    timing: dict[str, dict[str, float]] = field(default_factory=dict)
    corrections: dict[str, list[str]] = field(default_factory=dict)
    started_at: str = ""
    last_checkpoint: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary for JSON serialization."""
        return {
            "in_progress_issues": self.in_progress_issues,
            "completed_issues": self.completed_issues,
            "failed_issues": self.failed_issues,
            "pending_merges": self.pending_merges,
            "timing": self.timing,
            "corrections": self.corrections,
            "started_at": self.started_at,
            "last_checkpoint": self.last_checkpoint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrchestratorState:
        """Create state from dictionary (JSON deserialization)."""
        return cls(
            in_progress_issues=data.get("in_progress_issues", []),
            completed_issues=data.get("completed_issues", []),
            failed_issues=data.get("failed_issues", {}),
            pending_merges=data.get("pending_merges", []),
            timing=data.get("timing", {}),
            corrections=data.get("corrections", {}),
            started_at=data.get("started_at", ""),
            last_checkpoint=data.get("last_checkpoint", ""),
        )


@dataclass
class PendingWorktreeInfo:
    """Information about a pending worktree from a previous run.

    Attributes:
        worktree_path: Path to the worktree directory
        branch_name: Git branch name (parallel/<issue-id>-<timestamp>)
        issue_id: Extracted issue ID (e.g., BUG-045)
        commits_ahead: Number of commits ahead of main
        has_uncommitted_changes: Whether there are uncommitted changes
        changed_files: List of files with uncommitted changes
    """

    worktree_path: Path
    branch_name: str
    issue_id: str
    commits_ahead: int
    has_uncommitted_changes: bool
    changed_files: list[str] = field(default_factory=list)

    @property
    def has_pending_work(self) -> bool:
        """Return True if this worktree has work that could be merged."""
        return self.commits_ahead > 0 or self.has_uncommitted_changes


@dataclass
class ParallelConfig:
    """Configuration for the parallel issue manager.

    Supports configurable command templates for different project setups.
    Commands use placeholders: {{issue_id}}, {{issue_type}}, {{action}}

    Attributes:
        max_workers: Number of parallel workers (default: 2)
        p0_sequential: Process P0 issues sequentially (default: True)
        merge_interval: Seconds between merge attempts (default: 30.0)
        worktree_base: Base directory for git worktrees
        state_file: Path to state persistence file
        max_merge_retries: Maximum rebase attempts before giving up (default: 2)
        priority_filter: Which priority levels to process
        max_issues: Maximum issues to process (0 = unlimited)
        dry_run: Preview mode without actual processing
        timeout_per_issue: Timeout in seconds for each issue (default: 3600)
        orchestrator_timeout: Timeout for waiting on workers (default: 0 = auto)
        stream_subprocess_output: Whether to stream subprocess output
        show_model: Make API call to verify and display model on worktree setup
        command_prefix: Prefix for slash commands (default: "/ll:")
        ready_command: Template for ready_issue command
        manage_command: Template for manage_issue command
        only_ids: If provided, only process these issue IDs
        skip_ids: Issue IDs to skip (in addition to completed/failed)
        merge_pending: Attempt to merge pending worktrees from previous runs
        clean_start: Remove all worktrees without checking for pending work
        ignore_pending: Report pending work but continue without merging
    """

    max_workers: int = 2
    p0_sequential: bool = True
    merge_interval: float = 30.0
    worktree_base: Path = field(default_factory=lambda: Path(".worktrees"))
    state_file: Path = field(default_factory=lambda: Path(".parallel-manage-state.json"))
    max_merge_retries: int = 2
    priority_filter: list[str] = field(default_factory=lambda: ["P0", "P1", "P2", "P3", "P4", "P5"])
    max_issues: int = 0
    dry_run: bool = False
    timeout_per_issue: int = 3600
    orchestrator_timeout: int = 0  # 0 = use timeout_per_issue * max_workers
    stream_subprocess_output: bool = False
    show_model: bool = False  # Make API call to verify model on worktree setup
    # Configurable command templates
    command_prefix: str = "/ll:"
    ready_command: str = "ready_issue {{issue_id}}"
    manage_command: str = "manage_issue {{issue_type}} {{action}} {{issue_id}}"
    # Issue ID filters
    only_ids: set[str] | None = None
    skip_ids: set[str] | None = None
    # Validation settings
    require_code_changes: bool = True  # If False, allow changes to only excluded dirs
    # Additional files to copy from main repo to worktrees
    # Note: .claude/ directory is always copied automatically (see worker_pool.py)
    worktree_copy_files: list[str] = field(default_factory=lambda: [".env"])
    # Pending worktree handling flags
    merge_pending: bool = False  # Attempt to merge pending worktrees
    clean_start: bool = False  # Remove all worktrees without checking
    ignore_pending: bool = False  # Report pending work but continue

    def get_ready_command(self, issue_id: str) -> str:
        """Build the ready_issue command string.

        Args:
            issue_id: Issue identifier

        Returns:
            Complete command string
        """
        cmd = self.ready_command.replace("{{issue_id}}", issue_id)
        return f"{self.command_prefix}{cmd}"

    def get_manage_command(self, issue_type: str, action: str, issue_id: str) -> str:
        """Build the manage_issue command string.

        Args:
            issue_type: Type of issue (bug, feature, enhancement)
            action: Action to perform (fix, implement, improve)
            issue_id: Issue identifier

        Returns:
            Complete command string
        """
        cmd = (
            self.manage_command.replace("{{issue_type}}", issue_type)
            .replace("{{action}}", action)
            .replace("{{issue_id}}", issue_id)
        )
        return f"{self.command_prefix}{cmd}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "max_workers": self.max_workers,
            "p0_sequential": self.p0_sequential,
            "merge_interval": self.merge_interval,
            "worktree_base": str(self.worktree_base),
            "state_file": str(self.state_file),
            "max_merge_retries": self.max_merge_retries,
            "priority_filter": self.priority_filter,
            "max_issues": self.max_issues,
            "dry_run": self.dry_run,
            "timeout_per_issue": self.timeout_per_issue,
            "orchestrator_timeout": self.orchestrator_timeout,
            "stream_subprocess_output": self.stream_subprocess_output,
            "show_model": self.show_model,
            "command_prefix": self.command_prefix,
            "ready_command": self.ready_command,
            "manage_command": self.manage_command,
            "only_ids": list(self.only_ids) if self.only_ids else None,
            "skip_ids": list(self.skip_ids) if self.skip_ids else None,
            "require_code_changes": self.require_code_changes,
            "merge_pending": self.merge_pending,
            "clean_start": self.clean_start,
            "ignore_pending": self.ignore_pending,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParallelConfig:
        """Create from dictionary (JSON deserialization)."""
        only_ids_data = data.get("only_ids")
        skip_ids_data = data.get("skip_ids")
        return cls(
            max_workers=data.get("max_workers", 2),
            p0_sequential=data.get("p0_sequential", True),
            merge_interval=data.get("merge_interval", 30.0),
            worktree_base=Path(data.get("worktree_base", ".worktrees")),
            state_file=Path(data.get("state_file", ".parallel-manage-state.json")),
            max_merge_retries=data.get("max_merge_retries", 2),
            priority_filter=data.get("priority_filter", ["P0", "P1", "P2", "P3", "P4", "P5"]),
            max_issues=data.get("max_issues", 0),
            dry_run=data.get("dry_run", False),
            timeout_per_issue=data.get("timeout_per_issue", 3600),
            orchestrator_timeout=data.get("orchestrator_timeout", 0),
            stream_subprocess_output=data.get("stream_subprocess_output", False),
            show_model=data.get("show_model", False),
            command_prefix=data.get("command_prefix", "/ll:"),
            ready_command=data.get("ready_command", "ready_issue {{issue_id}}"),
            manage_command=data.get(
                "manage_command", "manage_issue {{issue_type}} {{action}} {{issue_id}}"
            ),
            only_ids=set(only_ids_data) if only_ids_data else None,
            skip_ids=set(skip_ids_data) if skip_ids_data else None,
            require_code_changes=data.get("require_code_changes", True),
            merge_pending=data.get("merge_pending", False),
            clean_start=data.get("clean_start", False),
            ignore_pending=data.get("ignore_pending", False),
        )
