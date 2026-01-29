"""Tests for parallel types module.

Tests for dataclasses in little_loops/parallel/types.py including:
- QueuedIssue
- WorkerResult
- MergeStatus/MergeRequest
- OrchestratorState
- PendingWorktreeInfo
- ParallelConfig
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from little_loops.issue_parser import IssueInfo
from little_loops.parallel.types import (
    MergeRequest,
    MergeStatus,
    OrchestratorState,
    ParallelConfig,
    PendingWorktreeInfo,
    QueuedIssue,
    WorkerResult,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_issue_info() -> IssueInfo:
    """Create a sample IssueInfo for testing."""
    return IssueInfo(
        path=Path(".issues/bugs/P1-BUG-001-test.md"),
        issue_type="bugs",
        priority="P1",
        issue_id="BUG-001",
        title="Test Bug",
    )


@pytest.fixture
def p0_issue_info() -> IssueInfo:
    """P0 priority issue info."""
    return IssueInfo(
        path=Path(".issues/bugs/P0-BUG-010-critical.md"),
        issue_type="bugs",
        priority="P0",
        issue_id="BUG-010",
        title="Critical Bug",
    )


@pytest.fixture
def sample_worker_result() -> WorkerResult:
    """Create a sample WorkerResult for testing."""
    return WorkerResult(
        issue_id="BUG-001",
        success=True,
        branch_name="parallel/bug-001-12345",
        worktree_path=Path("/tmp/worktrees/bug-001"),
    )


# =============================================================================
# QueuedIssue Tests
# =============================================================================


class TestQueuedIssue:
    """Tests for QueuedIssue dataclass."""

    def test_creation_with_all_fields(self, sample_issue_info: IssueInfo) -> None:
        """QueuedIssue can be created with all fields."""
        timestamp = 1000.0
        queued = QueuedIssue(
            priority=1,
            issue_info=sample_issue_info,
            timestamp=timestamp,
        )

        assert queued.priority == 1
        assert queued.issue_info == sample_issue_info
        assert queued.timestamp == timestamp

    def test_timestamp_defaults_to_current_time(
        self, sample_issue_info: IssueInfo
    ) -> None:
        """QueuedIssue timestamp defaults to current time."""
        before = time.time()
        queued = QueuedIssue(priority=1, issue_info=sample_issue_info)
        after = time.time()

        assert before <= queued.timestamp <= after

    def test_lt_different_priorities(
        self, sample_issue_info: IssueInfo, p0_issue_info: IssueInfo
    ) -> None:
        """Lower priority number compares as less than (higher priority)."""
        p0_queued = QueuedIssue(priority=0, issue_info=p0_issue_info, timestamp=100.0)
        p1_queued = QueuedIssue(priority=1, issue_info=sample_issue_info, timestamp=50.0)

        # P0 should come before P1 even though P1 has earlier timestamp
        assert p0_queued < p1_queued
        assert not p1_queued < p0_queued

    def test_lt_same_priority_uses_timestamp(
        self, sample_issue_info: IssueInfo
    ) -> None:
        """Same priority uses timestamp for ordering (FIFO)."""
        earlier = QueuedIssue(priority=1, issue_info=sample_issue_info, timestamp=100.0)
        later = QueuedIssue(priority=1, issue_info=sample_issue_info, timestamp=200.0)

        assert earlier < later
        assert not later < earlier

    def test_lt_same_priority_same_timestamp(
        self, sample_issue_info: IssueInfo
    ) -> None:
        """Same priority and timestamp compares as not less than."""
        q1 = QueuedIssue(priority=1, issue_info=sample_issue_info, timestamp=100.0)
        q2 = QueuedIssue(priority=1, issue_info=sample_issue_info, timestamp=100.0)

        assert not q1 < q2
        assert not q2 < q1

    def test_to_dict(self, sample_issue_info: IssueInfo) -> None:
        """to_dict serializes all fields."""
        queued = QueuedIssue(
            priority=2,
            issue_info=sample_issue_info,
            timestamp=12345.67,
        )

        result = queued.to_dict()

        assert result["priority"] == 2
        assert result["timestamp"] == 12345.67
        assert result["issue_info"]["issue_id"] == "BUG-001"
        assert result["issue_info"]["priority"] == "P1"

    def test_to_dict_nested_issue_info(self, sample_issue_info: IssueInfo) -> None:
        """to_dict properly nests issue_info serialization."""
        queued = QueuedIssue(priority=0, issue_info=sample_issue_info, timestamp=0)

        result = queued.to_dict()

        # Verify nested structure
        assert "issue_info" in result
        assert result["issue_info"]["path"] == str(sample_issue_info.path)
        assert result["issue_info"]["issue_type"] == "bugs"
        assert result["issue_info"]["title"] == "Test Bug"


# =============================================================================
# WorkerResult Tests
# =============================================================================


class TestWorkerResult:
    """Tests for WorkerResult dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """WorkerResult can be created with only required fields."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
        )

        assert result.issue_id == "BUG-001"
        assert result.success is True
        assert result.branch_name == "parallel/bug-001"
        assert result.worktree_path == Path("/tmp/worktree")

    def test_default_values(self) -> None:
        """WorkerResult has correct default values for optional fields."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="branch",
            worktree_path=Path("/tmp"),
        )

        assert result.changed_files == []
        assert result.leaked_files == []
        assert result.duration == 0.0
        assert result.error is None
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.was_corrected is False
        assert result.corrections == []
        assert result.should_close is False
        assert result.close_reason is None
        assert result.close_status is None
        assert result.interrupted is False

    def test_creation_with_all_fields(self) -> None:
        """WorkerResult can be created with all fields."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=False,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            changed_files=["file1.py", "file2.py"],
            leaked_files=["leaked.py"],
            duration=123.45,
            error="Something went wrong",
            stdout="output",
            stderr="error output",
            was_corrected=True,
            corrections=["fixed typo"],
            should_close=True,
            close_reason="already_fixed",
            close_status="Closed - Already Fixed",
            interrupted=True,
        )

        assert result.changed_files == ["file1.py", "file2.py"]
        assert result.leaked_files == ["leaked.py"]
        assert result.duration == 123.45
        assert result.error == "Something went wrong"
        assert result.stdout == "output"
        assert result.stderr == "error output"
        assert result.was_corrected is True
        assert result.corrections == ["fixed typo"]
        assert result.should_close is True
        assert result.close_reason == "already_fixed"
        assert result.close_status == "Closed - Already Fixed"
        assert result.interrupted is True

    def test_to_dict(self, sample_worker_result: WorkerResult) -> None:
        """to_dict serializes all fields."""
        result = sample_worker_result.to_dict()

        assert result["issue_id"] == "BUG-001"
        assert result["success"] is True
        assert result["branch_name"] == "parallel/bug-001-12345"
        assert result["worktree_path"] == "/tmp/worktrees/bug-001"
        assert result["changed_files"] == []
        assert result["interrupted"] is False

    def test_to_dict_path_converted_to_string(self) -> None:
        """to_dict converts Path to string."""
        result = WorkerResult(
            issue_id="X",
            success=True,
            branch_name="b",
            worktree_path=Path("/some/path"),
        )

        data = result.to_dict()

        assert isinstance(data["worktree_path"], str)
        assert data["worktree_path"] == "/some/path"

    def test_from_dict(self) -> None:
        """from_dict deserializes correctly."""
        data = {
            "issue_id": "BUG-002",
            "success": False,
            "branch_name": "parallel/bug-002",
            "worktree_path": "/path/to/worktree",
            "changed_files": ["a.py"],
            "duration": 10.5,
            "error": "failed",
            "interrupted": True,
        }

        result = WorkerResult.from_dict(data)

        assert result.issue_id == "BUG-002"
        assert result.success is False
        assert result.branch_name == "parallel/bug-002"
        assert result.worktree_path == Path("/path/to/worktree")
        assert result.changed_files == ["a.py"]
        assert result.duration == 10.5
        assert result.error == "failed"
        assert result.interrupted is True

    def test_from_dict_string_to_path_conversion(self) -> None:
        """from_dict converts worktree_path string to Path."""
        data = {
            "issue_id": "X",
            "success": True,
            "branch_name": "b",
            "worktree_path": "/converted/path",
        }

        result = WorkerResult.from_dict(data)

        assert isinstance(result.worktree_path, Path)
        assert result.worktree_path == Path("/converted/path")

    def test_from_dict_defaults_for_missing_optional_fields(self) -> None:
        """from_dict provides defaults for missing optional fields."""
        data = {
            "issue_id": "BUG-003",
            "success": True,
            "branch_name": "branch",
            "worktree_path": "/tmp",
        }

        result = WorkerResult.from_dict(data)

        assert result.changed_files == []
        assert result.leaked_files == []
        assert result.duration == 0.0
        assert result.error is None
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.was_corrected is False
        assert result.corrections == []
        assert result.should_close is False
        assert result.close_reason is None
        assert result.close_status is None
        assert result.interrupted is False

    def test_roundtrip_serialization(self) -> None:
        """Roundtrip through to_dict/from_dict preserves all fields."""
        original = WorkerResult(
            issue_id="BUG-100",
            success=False,
            branch_name="parallel/bug-100",
            worktree_path=Path("/work/tree"),
            changed_files=["x.py", "y.py"],
            leaked_files=["z.py"],
            duration=99.9,
            error="error msg",
            stdout="out",
            stderr="err",
            was_corrected=True,
            corrections=["c1", "c2"],
            should_close=True,
            close_reason="reason",
            close_status="status",
            interrupted=True,
        )

        restored = WorkerResult.from_dict(original.to_dict())

        assert restored.issue_id == original.issue_id
        assert restored.success == original.success
        assert restored.branch_name == original.branch_name
        assert restored.worktree_path == original.worktree_path
        assert restored.changed_files == original.changed_files
        assert restored.leaked_files == original.leaked_files
        assert restored.duration == original.duration
        assert restored.error == original.error
        assert restored.stdout == original.stdout
        assert restored.stderr == original.stderr
        assert restored.was_corrected == original.was_corrected
        assert restored.corrections == original.corrections
        assert restored.should_close == original.should_close
        assert restored.close_reason == original.close_reason
        assert restored.close_status == original.close_status
        assert restored.interrupted == original.interrupted


# =============================================================================
# MergeStatus Tests
# =============================================================================


class TestMergeStatus:
    """Tests for MergeStatus enum."""

    def test_all_status_values_exist(self) -> None:
        """All expected status values exist."""
        assert MergeStatus.PENDING.value == "pending"
        assert MergeStatus.IN_PROGRESS.value == "in_progress"
        assert MergeStatus.SUCCESS.value == "success"
        assert MergeStatus.CONFLICT.value == "conflict"
        assert MergeStatus.FAILED.value == "failed"
        assert MergeStatus.RETRYING.value == "retrying"

    def test_enum_member_count(self) -> None:
        """MergeStatus has exactly 6 members."""
        assert len(MergeStatus) == 6


# =============================================================================
# MergeRequest Tests
# =============================================================================


class TestMergeRequest:
    """Tests for MergeRequest dataclass."""

    def test_creation_with_required_fields(
        self, sample_worker_result: WorkerResult
    ) -> None:
        """MergeRequest can be created with only worker_result."""
        before = time.time()
        request = MergeRequest(worker_result=sample_worker_result)
        after = time.time()

        assert request.worker_result == sample_worker_result
        assert request.status == MergeStatus.PENDING
        assert request.retry_count == 0
        assert request.error is None
        assert before <= request.queued_at <= after

    def test_creation_with_all_fields(
        self, sample_worker_result: WorkerResult
    ) -> None:
        """MergeRequest can be created with all fields."""
        request = MergeRequest(
            worker_result=sample_worker_result,
            status=MergeStatus.CONFLICT,
            retry_count=2,
            error="merge conflict",
            queued_at=1000.0,
        )

        assert request.status == MergeStatus.CONFLICT
        assert request.retry_count == 2
        assert request.error == "merge conflict"
        assert request.queued_at == 1000.0

    def test_to_dict(self, sample_worker_result: WorkerResult) -> None:
        """to_dict serializes all fields correctly."""
        request = MergeRequest(
            worker_result=sample_worker_result,
            status=MergeStatus.IN_PROGRESS,
            retry_count=1,
            error="retry",
            queued_at=500.0,
        )

        result = request.to_dict()

        assert result["status"] == "in_progress"
        assert result["retry_count"] == 1
        assert result["error"] == "retry"
        assert result["queued_at"] == 500.0
        assert result["worker_result"]["issue_id"] == "BUG-001"

    def test_to_dict_status_serialized_as_value(
        self, sample_worker_result: WorkerResult
    ) -> None:
        """Status enum is serialized as its string value."""
        request = MergeRequest(
            worker_result=sample_worker_result,
            status=MergeStatus.SUCCESS,
        )

        result = request.to_dict()

        assert result["status"] == "success"
        assert isinstance(result["status"], str)


# =============================================================================
# OrchestratorState Tests
# =============================================================================


class TestOrchestratorState:
    """Tests for OrchestratorState dataclass."""

    def test_default_values(self) -> None:
        """OrchestratorState has correct default values."""
        state = OrchestratorState()

        assert state.in_progress_issues == []
        assert state.completed_issues == []
        assert state.failed_issues == {}
        assert state.pending_merges == []
        assert state.timing == {}
        assert state.corrections == {}
        assert state.started_at == ""
        assert state.last_checkpoint == ""

    def test_creation_with_all_fields(self) -> None:
        """OrchestratorState can be created with all fields."""
        state = OrchestratorState(
            in_progress_issues=["BUG-001"],
            completed_issues=["BUG-002", "BUG-003"],
            failed_issues={"BUG-004": "timeout"},
            pending_merges=["BUG-005"],
            timing={"BUG-001": {"start": 100.0, "end": 200.0}},
            corrections={"BUG-002": ["fixed typo"]},
            started_at="2026-01-23T10:00:00",
            last_checkpoint="2026-01-23T10:30:00",
        )

        assert state.in_progress_issues == ["BUG-001"]
        assert state.completed_issues == ["BUG-002", "BUG-003"]
        assert state.failed_issues == {"BUG-004": "timeout"}
        assert state.pending_merges == ["BUG-005"]
        assert state.timing == {"BUG-001": {"start": 100.0, "end": 200.0}}
        assert state.corrections == {"BUG-002": ["fixed typo"]}
        assert state.started_at == "2026-01-23T10:00:00"
        assert state.last_checkpoint == "2026-01-23T10:30:00"

    def test_to_dict(self) -> None:
        """to_dict serializes all fields."""
        state = OrchestratorState(
            in_progress_issues=["A"],
            completed_issues=["B"],
            failed_issues={"C": "error"},
            pending_merges=["D"],
            timing={"A": {"x": 1.0}},
            corrections={"B": ["c1"]},
            started_at="start",
            last_checkpoint="check",
        )

        result = state.to_dict()

        assert result["in_progress_issues"] == ["A"]
        assert result["completed_issues"] == ["B"]
        assert result["failed_issues"] == {"C": "error"}
        assert result["pending_merges"] == ["D"]
        assert result["timing"] == {"A": {"x": 1.0}}
        assert result["corrections"] == {"B": ["c1"]}
        assert result["started_at"] == "start"
        assert result["last_checkpoint"] == "check"

    def test_from_dict(self) -> None:
        """from_dict deserializes correctly."""
        data = {
            "in_progress_issues": ["X"],
            "completed_issues": ["Y"],
            "failed_issues": {"Z": "fail"},
            "pending_merges": ["W"],
            "timing": {"X": {"t": 2.0}},
            "corrections": {"Y": ["fix"]},
            "started_at": "s",
            "last_checkpoint": "c",
        }

        state = OrchestratorState.from_dict(data)

        assert state.in_progress_issues == ["X"]
        assert state.completed_issues == ["Y"]
        assert state.failed_issues == {"Z": "fail"}
        assert state.pending_merges == ["W"]
        assert state.timing == {"X": {"t": 2.0}}
        assert state.corrections == {"Y": ["fix"]}
        assert state.started_at == "s"
        assert state.last_checkpoint == "c"

    def test_from_dict_defaults_for_missing_fields(self) -> None:
        """from_dict provides defaults for missing fields."""
        data: dict = {}

        state = OrchestratorState.from_dict(data)

        assert state.in_progress_issues == []
        assert state.completed_issues == []
        assert state.failed_issues == {}
        assert state.pending_merges == []
        assert state.timing == {}
        assert state.corrections == {}
        assert state.started_at == ""
        assert state.last_checkpoint == ""

    def test_from_dict_partial_data(self) -> None:
        """from_dict handles partial data correctly."""
        data = {
            "completed_issues": ["DONE-1"],
            "failed_issues": {"FAIL-1": "reason"},
        }

        state = OrchestratorState.from_dict(data)

        assert state.in_progress_issues == []
        assert state.completed_issues == ["DONE-1"]
        assert state.failed_issues == {"FAIL-1": "reason"}
        assert state.pending_merges == []

    def test_roundtrip_serialization(self) -> None:
        """Roundtrip through to_dict/from_dict preserves all fields."""
        original = OrchestratorState(
            in_progress_issues=["A", "B"],
            completed_issues=["C"],
            failed_issues={"D": "err"},
            pending_merges=["E"],
            timing={"A": {"start": 1.0}},
            corrections={"C": ["c1", "c2"]},
            started_at="2026-01-01",
            last_checkpoint="2026-01-02",
        )

        restored = OrchestratorState.from_dict(original.to_dict())

        assert restored.in_progress_issues == original.in_progress_issues
        assert restored.completed_issues == original.completed_issues
        assert restored.failed_issues == original.failed_issues
        assert restored.pending_merges == original.pending_merges
        assert restored.timing == original.timing
        assert restored.corrections == original.corrections
        assert restored.started_at == original.started_at
        assert restored.last_checkpoint == original.last_checkpoint


# =============================================================================
# PendingWorktreeInfo Tests
# =============================================================================


class TestPendingWorktreeInfo:
    """Tests for PendingWorktreeInfo dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """PendingWorktreeInfo can be created with required fields."""
        info = PendingWorktreeInfo(
            worktree_path=Path("/work/trees/bug-001"),
            branch_name="parallel/bug-001-12345",
            issue_id="BUG-001",
            commits_ahead=2,
            has_uncommitted_changes=False,
        )

        assert info.worktree_path == Path("/work/trees/bug-001")
        assert info.branch_name == "parallel/bug-001-12345"
        assert info.issue_id == "BUG-001"
        assert info.commits_ahead == 2
        assert info.has_uncommitted_changes is False

    def test_default_changed_files(self) -> None:
        """changed_files defaults to empty list."""
        info = PendingWorktreeInfo(
            worktree_path=Path("/tmp"),
            branch_name="branch",
            issue_id="X",
            commits_ahead=0,
            has_uncommitted_changes=False,
        )

        assert info.changed_files == []

    def test_creation_with_all_fields(self) -> None:
        """PendingWorktreeInfo can be created with all fields."""
        info = PendingWorktreeInfo(
            worktree_path=Path("/tmp"),
            branch_name="branch",
            issue_id="X",
            commits_ahead=1,
            has_uncommitted_changes=True,
            changed_files=["a.py", "b.py"],
        )

        assert info.changed_files == ["a.py", "b.py"]

    def test_has_pending_work_commits_ahead(self) -> None:
        """has_pending_work returns True when commits_ahead > 0."""
        info = PendingWorktreeInfo(
            worktree_path=Path("/tmp"),
            branch_name="branch",
            issue_id="X",
            commits_ahead=1,
            has_uncommitted_changes=False,
        )

        assert info.has_pending_work is True

    def test_has_pending_work_uncommitted_changes(self) -> None:
        """has_pending_work returns True when has_uncommitted_changes is True."""
        info = PendingWorktreeInfo(
            worktree_path=Path("/tmp"),
            branch_name="branch",
            issue_id="X",
            commits_ahead=0,
            has_uncommitted_changes=True,
        )

        assert info.has_pending_work is True

    def test_has_pending_work_both_conditions(self) -> None:
        """has_pending_work returns True when both conditions are met."""
        info = PendingWorktreeInfo(
            worktree_path=Path("/tmp"),
            branch_name="branch",
            issue_id="X",
            commits_ahead=5,
            has_uncommitted_changes=True,
        )

        assert info.has_pending_work is True

    def test_has_pending_work_no_pending(self) -> None:
        """has_pending_work returns False when no pending work."""
        info = PendingWorktreeInfo(
            worktree_path=Path("/tmp"),
            branch_name="branch",
            issue_id="X",
            commits_ahead=0,
            has_uncommitted_changes=False,
        )

        assert info.has_pending_work is False


# =============================================================================
# ParallelConfig Tests
# =============================================================================


class TestParallelConfig:
    """Tests for ParallelConfig dataclass."""

    def test_default_values(self) -> None:
        """ParallelConfig has correct default values."""
        config = ParallelConfig()

        assert config.max_workers == 2
        assert config.p0_sequential is True
        assert config.merge_interval == 30.0
        assert config.worktree_base == Path(".worktrees")
        assert config.state_file == Path(".parallel-manage-state.json")
        assert config.max_merge_retries == 2
        assert config.priority_filter == ["P0", "P1", "P2", "P3", "P4", "P5"]
        assert config.max_issues == 0
        assert config.dry_run is False
        assert config.timeout_per_issue == 3600
        assert config.orchestrator_timeout == 0
        assert config.stream_subprocess_output is False
        assert config.show_model is False
        assert config.command_prefix == "/ll:"
        assert config.ready_command == "ready_issue {{issue_id}}"
        assert config.manage_command == "manage_issue {{issue_type}} {{action}} {{issue_id}}"
        assert config.only_ids is None
        assert config.skip_ids is None
        assert config.require_code_changes is True
        assert config.worktree_copy_files == [".env"]
        assert config.merge_pending is False
        assert config.clean_start is False
        assert config.ignore_pending is False

    def test_creation_with_custom_values(self) -> None:
        """ParallelConfig can be created with custom values."""
        config = ParallelConfig(
            max_workers=4,
            p0_sequential=False,
            merge_interval=60.0,
            worktree_base=Path("/custom/worktrees"),
            max_issues=10,
            dry_run=True,
            only_ids={"BUG-001", "BUG-002"},
            skip_ids={"BUG-003"},
        )

        assert config.max_workers == 4
        assert config.p0_sequential is False
        assert config.merge_interval == 60.0
        assert config.worktree_base == Path("/custom/worktrees")
        assert config.max_issues == 10
        assert config.dry_run is True
        assert config.only_ids == {"BUG-001", "BUG-002"}
        assert config.skip_ids == {"BUG-003"}

    def test_get_ready_command(self) -> None:
        """get_ready_command builds correct command string."""
        config = ParallelConfig()

        cmd = config.get_ready_command("BUG-123")

        assert cmd == "/ll:ready_issue BUG-123"

    def test_get_ready_command_custom_prefix(self) -> None:
        """get_ready_command respects custom command_prefix."""
        config = ParallelConfig(command_prefix="/custom:")

        cmd = config.get_ready_command("FEAT-001")

        assert cmd == "/custom:ready_issue FEAT-001"

    def test_get_ready_command_custom_template(self) -> None:
        """get_ready_command respects custom ready_command template."""
        config = ParallelConfig(
            ready_command="validate {{issue_id}} --strict",
        )

        cmd = config.get_ready_command("ENH-050")

        assert cmd == "/ll:validate ENH-050 --strict"

    def test_get_manage_command(self) -> None:
        """get_manage_command builds correct command string."""
        config = ParallelConfig()

        cmd = config.get_manage_command("bug", "fix", "BUG-123")

        assert cmd == "/ll:manage_issue bug fix BUG-123"

    def test_get_manage_command_all_substitutions(self) -> None:
        """get_manage_command substitutes all placeholders."""
        config = ParallelConfig()

        cmd = config.get_manage_command("feature", "implement", "FEAT-999")

        assert cmd == "/ll:manage_issue feature implement FEAT-999"

    def test_get_manage_command_custom_template(self) -> None:
        """get_manage_command respects custom manage_command template."""
        config = ParallelConfig(
            manage_command="process --type={{issue_type}} --action={{action}} {{issue_id}}",
        )

        cmd = config.get_manage_command("enhancement", "improve", "ENH-001")

        assert cmd == "/ll:process --type=enhancement --action=improve ENH-001"

    def test_to_dict(self) -> None:
        """to_dict serializes all fields correctly."""
        config = ParallelConfig(
            max_workers=3,
            worktree_base=Path("/path/to/trees"),
            only_ids={"A", "B"},
            skip_ids={"C"},
        )

        result = config.to_dict()

        assert result["max_workers"] == 3
        assert result["worktree_base"] == "/path/to/trees"
        assert set(result["only_ids"]) == {"A", "B"}
        assert set(result["skip_ids"]) == {"C"}

    def test_to_dict_paths_to_strings(self) -> None:
        """to_dict converts Path objects to strings."""
        config = ParallelConfig(
            worktree_base=Path("/trees"),
            state_file=Path("/state.json"),
        )

        result = config.to_dict()

        assert isinstance(result["worktree_base"], str)
        assert isinstance(result["state_file"], str)
        assert result["worktree_base"] == "/trees"
        assert result["state_file"] == "/state.json"

    def test_to_dict_sets_to_lists(self) -> None:
        """to_dict converts sets to lists."""
        config = ParallelConfig(
            only_ids={"X", "Y"},
            skip_ids={"Z"},
        )

        result = config.to_dict()

        assert isinstance(result["only_ids"], list)
        assert isinstance(result["skip_ids"], list)

    def test_to_dict_none_sets_preserved(self) -> None:
        """to_dict preserves None for unset ID filters."""
        config = ParallelConfig()

        result = config.to_dict()

        assert result["only_ids"] is None
        assert result["skip_ids"] is None

    def test_from_dict(self) -> None:
        """from_dict deserializes correctly."""
        data = {
            "max_workers": 5,
            "p0_sequential": False,
            "merge_interval": 45.0,
            "worktree_base": "/custom/trees",
            "state_file": "/custom/state.json",
            "max_merge_retries": 5,
            "priority_filter": ["P0", "P1"],
            "max_issues": 20,
            "dry_run": True,
            "timeout_per_issue": 3600,
            "only_ids": ["A", "B"],
            "skip_ids": ["C"],
        }

        config = ParallelConfig.from_dict(data)

        assert config.max_workers == 5
        assert config.p0_sequential is False
        assert config.merge_interval == 45.0
        assert config.worktree_base == Path("/custom/trees")
        assert config.state_file == Path("/custom/state.json")
        assert config.max_merge_retries == 5
        assert config.priority_filter == ["P0", "P1"]
        assert config.max_issues == 20
        assert config.dry_run is True
        assert config.timeout_per_issue == 3600
        assert config.only_ids == {"A", "B"}
        assert config.skip_ids == {"C"}

    def test_from_dict_strings_to_paths(self) -> None:
        """from_dict converts strings to Path objects."""
        data = {
            "worktree_base": "/path/one",
            "state_file": "/path/two",
        }

        config = ParallelConfig.from_dict(data)

        assert isinstance(config.worktree_base, Path)
        assert isinstance(config.state_file, Path)
        assert config.worktree_base == Path("/path/one")
        assert config.state_file == Path("/path/two")

    def test_from_dict_lists_to_sets(self) -> None:
        """from_dict converts lists to sets for ID filters."""
        data = {
            "only_ids": ["X", "Y", "Z"],
            "skip_ids": ["A"],
        }

        config = ParallelConfig.from_dict(data)

        assert isinstance(config.only_ids, set)
        assert isinstance(config.skip_ids, set)
        assert config.only_ids == {"X", "Y", "Z"}
        assert config.skip_ids == {"A"}

    def test_from_dict_none_ids_preserved(self) -> None:
        """from_dict preserves None for unset ID filters."""
        data: dict = {}

        config = ParallelConfig.from_dict(data)

        assert config.only_ids is None
        assert config.skip_ids is None

    def test_from_dict_defaults_for_missing_fields(self) -> None:
        """from_dict provides defaults for missing fields."""
        data: dict = {}

        config = ParallelConfig.from_dict(data)

        assert config.max_workers == 2
        assert config.p0_sequential is True
        assert config.merge_interval == 30.0
        assert config.worktree_base == Path(".worktrees")
        assert config.max_merge_retries == 2
        assert config.priority_filter == ["P0", "P1", "P2", "P3", "P4", "P5"]
        assert config.command_prefix == "/ll:"

    def test_roundtrip_serialization(self) -> None:
        """Roundtrip through to_dict/from_dict preserves all fields."""
        original = ParallelConfig(
            max_workers=4,
            p0_sequential=False,
            merge_interval=60.0,
            worktree_base=Path("/trees"),
            state_file=Path("/state.json"),
            max_merge_retries=3,
            priority_filter=["P0", "P1"],
            max_issues=50,
            dry_run=True,
            timeout_per_issue=1800,
            orchestrator_timeout=7200,
            stream_subprocess_output=True,
            show_model=True,
            command_prefix="/test:",
            ready_command="ready {{issue_id}}",
            manage_command="manage {{issue_type}} {{action}} {{issue_id}}",
            only_ids={"A", "B"},
            skip_ids={"C"},
            require_code_changes=False,
            merge_pending=True,
            clean_start=True,
            ignore_pending=True,
        )

        restored = ParallelConfig.from_dict(original.to_dict())

        assert restored.max_workers == original.max_workers
        assert restored.p0_sequential == original.p0_sequential
        assert restored.merge_interval == original.merge_interval
        assert restored.worktree_base == original.worktree_base
        assert restored.state_file == original.state_file
        assert restored.max_merge_retries == original.max_merge_retries
        assert restored.priority_filter == original.priority_filter
        assert restored.max_issues == original.max_issues
        assert restored.dry_run == original.dry_run
        assert restored.timeout_per_issue == original.timeout_per_issue
        assert restored.orchestrator_timeout == original.orchestrator_timeout
        assert restored.stream_subprocess_output == original.stream_subprocess_output
        assert restored.show_model == original.show_model
        assert restored.command_prefix == original.command_prefix
        assert restored.ready_command == original.ready_command
        assert restored.manage_command == original.manage_command
        assert restored.only_ids == original.only_ids
        assert restored.skip_ids == original.skip_ids
        assert restored.require_code_changes == original.require_code_changes
        assert restored.merge_pending == original.merge_pending
        assert restored.clean_start == original.clean_start
        assert restored.ignore_pending == original.ignore_pending
