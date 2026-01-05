"""Tests for little_loops.issue_lifecycle module.

Provides comprehensive test coverage for issue lifecycle management including:
- Resolution building functions
- Content manipulation
- Git operations (move, commit, cleanup)
- Issue verification
- Issue creation from failure
- Close and complete flows
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.config import BRConfig
from little_loops.issue_lifecycle import (
    _build_closure_resolution,
    _build_completion_resolution,
    _cleanup_stale_source,
    _commit_issue_completion,
    _move_issue_to_completed,
    _prepare_issue_content,
    close_issue,
    complete_issue_lifecycle,
    create_issue_from_failure,
    verify_issue_completed,
)
from little_loops.issue_parser import IssueInfo
from little_loops.logger import Logger

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_logger() -> MagicMock:
    """Create a mock logger."""
    return MagicMock(spec=Logger)


@pytest.fixture
def sample_issue_info(tmp_path: Path) -> IssueInfo:
    """Create a sample IssueInfo for testing."""
    issue_path = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
    issue_path.parent.mkdir(parents=True, exist_ok=True)
    issue_path.write_text("# BUG-001: Test Bug\n\n## Summary\nTest content.")
    return IssueInfo(
        path=issue_path,
        issue_type="bugs",
        priority="P1",
        issue_id="BUG-001",
        title="Test Bug",
    )


@pytest.fixture
def sample_config(tmp_path: Path) -> BRConfig:
    """Create a sample BRConfig for testing."""
    config_data = {
        "project": {
            "name": "test-project",
            "src_dir": "src/",
            "test_cmd": "pytest tests/",
            "lint_cmd": "ruff check .",
        },
        "issues": {
            "base_dir": ".issues",
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
            },
            "completed_dir": "completed",
            "priorities": ["P0", "P1", "P2", "P3"],
        },
    }
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    config_path = claude_dir / "ll-config.json"
    config_path.write_text(json.dumps(config_data, indent=2))

    # Create issue directories
    issues_dir = tmp_path / ".issues"
    (issues_dir / "bugs").mkdir(parents=True, exist_ok=True)
    (issues_dir / "features").mkdir(parents=True, exist_ok=True)
    (issues_dir / "enhancements").mkdir(parents=True, exist_ok=True)
    (issues_dir / "completed").mkdir(parents=True, exist_ok=True)

    return BRConfig(tmp_path)


# =============================================================================
# Tests: Resolution Building Functions
# =============================================================================


class TestBuildClosureResolution:
    """Tests for _build_closure_resolution function."""

    def test_basic_output_format(self) -> None:
        """Test that output contains expected sections."""
        result = _build_closure_resolution("Closed - Already Fixed", "already_fixed")

        assert "## Resolution" in result
        assert "**Status**: Closed - Already Fixed" in result
        assert "**Reason**: already_fixed" in result
        assert "**Closure**: Automated (ready_issue validation)" in result
        assert "### Closure Notes" in result

    def test_contains_date(self) -> None:
        """Test that output contains current date."""
        result = _build_closure_resolution("Closed", "test")
        today = datetime.now().strftime("%Y-%m-%d")
        assert f"**Closed**: {today}" in result

    def test_different_status_values(self) -> None:
        """Test with various status values."""
        statuses = [
            ("Closed - Invalid", "invalid_ref"),
            ("Closed - Duplicate", "duplicate"),
            ("Closed - Won't Fix", "wontfix"),
        ]
        for status, reason in statuses:
            result = _build_closure_resolution(status, reason)
            assert f"**Status**: {status}" in result
            assert f"**Reason**: {reason}" in result

    def test_starts_with_separator(self) -> None:
        """Test that output starts with markdown separator."""
        result = _build_closure_resolution("Closed", "test")
        assert result.strip().startswith("---")


class TestBuildCompletionResolution:
    """Tests for _build_completion_resolution function."""

    def test_basic_output_format(self) -> None:
        """Test that output contains expected sections."""
        result = _build_completion_resolution("fix")

        assert "## Resolution" in result
        assert "**Action**: fix" in result
        assert "**Status**: Completed (automated fallback)" in result
        assert "### Changes Made" in result
        assert "### Verification Results" in result
        assert "### Commits" in result

    def test_contains_date(self) -> None:
        """Test that output contains current date."""
        result = _build_completion_resolution("implement")
        today = datetime.now().strftime("%Y-%m-%d")
        assert f"**Completed**: {today}" in result

    def test_different_actions(self) -> None:
        """Test with various action values."""
        actions = ["fix", "implement", "improve", "refactor"]
        for action in actions:
            result = _build_completion_resolution(action)
            assert f"**Action**: {action}" in result

    def test_starts_with_separator(self) -> None:
        """Test that output starts with markdown separator."""
        result = _build_completion_resolution("fix")
        assert result.strip().startswith("---")


# =============================================================================
# Tests: Content Manipulation
# =============================================================================


class TestPrepareIssueContent:
    """Tests for _prepare_issue_content function."""

    def test_appends_resolution(self, tmp_path: Path) -> None:
        """Test that resolution is appended to content."""
        issue_file = tmp_path / "test-issue.md"
        issue_file.write_text("# Test Issue\n\n## Summary\nSome content.")

        resolution = "\n\n---\n\n## Resolution\n- **Status**: Completed"
        result = _prepare_issue_content(issue_file, resolution)

        assert "# Test Issue" in result
        assert "## Summary" in result
        assert "## Resolution" in result
        assert "**Status**: Completed" in result

    def test_idempotency_existing_resolution(self, tmp_path: Path) -> None:
        """Test that resolution is not duplicated if already present."""
        issue_file = tmp_path / "test-issue.md"
        original_content = "# Test Issue\n\n## Summary\nContent.\n\n## Resolution\nExisting."
        issue_file.write_text(original_content)

        new_resolution = "\n\n---\n\n## Resolution\n- **Status**: New"
        result = _prepare_issue_content(issue_file, new_resolution)

        # Should not append new resolution since one already exists
        assert result == original_content
        assert result.count("## Resolution") == 1

    def test_preserves_original_content(self, tmp_path: Path) -> None:
        """Test that original content is preserved."""
        issue_file = tmp_path / "test-issue.md"
        original = "# Issue\n\n## Description\nDetail here.\n\n## Impact\nHigh"
        issue_file.write_text(original)

        resolution = "\n\n---\n\n## Resolution\nDone."
        result = _prepare_issue_content(issue_file, resolution)

        assert "# Issue" in result
        assert "## Description" in result
        assert "Detail here." in result
        assert "## Impact" in result


# =============================================================================
# Tests: Git Operations
# =============================================================================


class TestCleanupStaleSource:
    """Tests for _cleanup_stale_source function."""

    def test_removes_file_and_commits(self, tmp_path: Path, mock_logger: MagicMock) -> None:
        """Test that file is removed and git commands are called."""
        # Create a file to remove
        issue_file = tmp_path / "stale-issue.md"
        issue_file.write_text("Stale content")

        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured_commands.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            _cleanup_stale_source(issue_file, "BUG-001", mock_logger)

        # File should be removed
        assert not issue_file.exists()

        # Git add -A should be called
        add_cmds = [c for c in captured_commands if c == ["git", "add", "-A"]]
        assert len(add_cmds) == 1

        # Git commit should be called with cleanup message
        commit_cmds = [c for c in captured_commands if "commit" in c]
        assert len(commit_cmds) == 1
        assert "cleanup" in commit_cmds[0][3].lower()
        assert "BUG-001" in commit_cmds[0][3]


class TestMoveIssueToCompleted:
    """Tests for _move_issue_to_completed function."""

    def test_git_mv_success(self, tmp_path: Path, mock_logger: MagicMock) -> None:
        """Test successful git mv path."""
        original = tmp_path / "bugs" / "issue.md"
        completed = tmp_path / "completed" / "issue.md"
        original.parent.mkdir(parents=True, exist_ok=True)
        completed.parent.mkdir(parents=True, exist_ok=True)
        original.write_text("Original content")

        content = "Updated content with resolution"

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if "git" in cmd and "mv" in cmd:
                # Simulate git mv by actually moving
                original.rename(completed)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = _move_issue_to_completed(original, completed, content, mock_logger)

        assert result is True
        assert completed.exists()
        assert completed.read_text() == content
        mock_logger.success.assert_called()

    def test_git_mv_fallback(self, tmp_path: Path, mock_logger: MagicMock) -> None:
        """Test fallback to manual copy+delete when git mv fails."""
        original = tmp_path / "bugs" / "issue.md"
        completed = tmp_path / "completed" / "issue.md"
        original.parent.mkdir(parents=True, exist_ok=True)
        completed.parent.mkdir(parents=True, exist_ok=True)
        original.write_text("Original content")

        content = "Updated content with resolution"

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if "git" in cmd and "mv" in cmd:
                # Simulate git mv failure
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="fatal: error")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = _move_issue_to_completed(original, completed, content, mock_logger)

        assert result is True
        assert completed.exists()
        assert completed.read_text() == content
        assert not original.exists()
        mock_logger.warning.assert_called()


class TestCommitIssueCompletion:
    """Tests for _commit_issue_completion function."""

    def test_successful_commit(self, sample_issue_info: IssueInfo, mock_logger: MagicMock) -> None:
        """Test successful commit with hash extraction."""
        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured_commands.append(cmd)
            if "commit" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="[main abc1234] commit message", stderr=""
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = _commit_issue_completion(
                sample_issue_info, "fix", "BUG-001 fixed", mock_logger
            )

        assert result is True
        mock_logger.success.assert_called()

        # Verify git add -A was called
        add_cmds = [c for c in captured_commands if c == ["git", "add", "-A"]]
        assert len(add_cmds) == 1

        # Verify commit message format
        commit_cmds = [c for c in captured_commands if "commit" in c]
        assert len(commit_cmds) == 1
        assert "fix(bugs)" in commit_cmds[0][3]

    def test_nothing_to_commit(self, sample_issue_info: IssueInfo, mock_logger: MagicMock) -> None:
        """Test handling when there's nothing to commit."""

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if "commit" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 1, stdout="nothing to commit, working tree clean", stderr=""
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = _commit_issue_completion(sample_issue_info, "fix", "test", mock_logger)

        assert result is True
        mock_logger.info.assert_called()

    def test_commit_failure(self, sample_issue_info: IssueInfo, mock_logger: MagicMock) -> None:
        """Test handling commit failure."""

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if "commit" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 1, stdout="", stderr="fatal: error occurred"
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = _commit_issue_completion(sample_issue_info, "fix", "test", mock_logger)

        assert result is True  # Still returns True to continue flow
        mock_logger.warning.assert_called()


# =============================================================================
# Tests: Issue Verification
# =============================================================================


class TestVerifyIssueCompleted:
    """Tests for verify_issue_completed function."""

    def test_properly_moved(
        self, tmp_path: Path, sample_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """Test verification when issue properly moved to completed."""
        # Create issue in completed, not in original location
        completed_dir = tmp_path / ".issues" / "completed"
        completed_file = completed_dir / "P1-BUG-001-test.md"
        completed_file.write_text("Completed issue")

        info = IssueInfo(
            path=tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md",
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        result = verify_issue_completed(info, sample_config, mock_logger)

        assert result is True
        mock_logger.success.assert_called()

    def test_exists_in_both_locations(
        self, tmp_path: Path, sample_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """Test warning when issue exists in both locations."""
        # Create in both locations
        original = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        completed = tmp_path / ".issues" / "completed" / "P1-BUG-001-test.md"
        original.write_text("Original")
        completed.write_text("Completed")

        info = IssueInfo(
            path=original,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        result = verify_issue_completed(info, sample_config, mock_logger)

        # Returns False because original still exists
        assert result is False
        mock_logger.warning.assert_called()

    def test_deleted_but_not_moved(
        self, tmp_path: Path, sample_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """Test warning when issue deleted but not moved to completed."""
        # Neither file exists
        info = IssueInfo(
            path=tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md",
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        result = verify_issue_completed(info, sample_config, mock_logger)

        # Returns True (issue is gone) but with warning
        assert result is True
        mock_logger.warning.assert_called()

    def test_not_moved(
        self, tmp_path: Path, sample_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """Test warning when issue still in original location."""
        # Only original exists
        original = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        original.write_text("Still here")

        info = IssueInfo(
            path=original,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        result = verify_issue_completed(info, sample_config, mock_logger)

        assert result is False
        mock_logger.warning.assert_called()


# =============================================================================
# Tests: Issue Creation from Failure
# =============================================================================


class TestCreateIssueFromFailure:
    """Tests for create_issue_from_failure function."""

    def test_creates_valid_markdown(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Test that valid markdown issue is created."""
        error_output = (
            "Traceback (most recent call last):\n  File 'test.py'\nValueError: test error"
        )

        result = create_issue_from_failure(
            error_output, sample_issue_info, sample_config, mock_logger
        )

        assert result is not None
        assert result.exists()

        content = result.read_text()
        assert "# BUG-" in content
        assert "## Summary" in content
        assert "## Current Behavior" in content
        assert error_output.split("\n")[0] in content
        mock_logger.success.assert_called()

    def test_extracts_error_message(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Test that error message is extracted for title."""
        error_output = "Some output\nValueError: Invalid input provided\nMore output"

        result = create_issue_from_failure(
            error_output, sample_issue_info, sample_config, mock_logger
        )

        assert result is not None
        content = result.read_text()
        # Error type should be in the content
        assert "ValueError" in content or "Invalid input" in content

    def test_creates_directory_if_needed(
        self,
        tmp_path: Path,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Test that bugs directory is created if missing."""
        # Create minimal config without bugs directory
        config_data = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                "completed_dir": "completed",
                "priorities": ["P0", "P1"],
            },
        }
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "ll-config.json").write_text(json.dumps(config_data))
        config = BRConfig(tmp_path)

        result = create_issue_from_failure("Error occurred", sample_issue_info, config, mock_logger)

        assert result is not None
        assert (tmp_path / ".issues" / "bugs").exists()

    def test_returns_none_on_failure(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Test that None is returned on write failure."""
        with patch.object(Path, "write_text", side_effect=PermissionError("denied")):
            result = create_issue_from_failure(
                "Error", sample_issue_info, sample_config, mock_logger
            )

        assert result is None
        mock_logger.error.assert_called()

    def test_priority_is_p1(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Test that created issue has P1 priority."""
        result = create_issue_from_failure("Error", sample_issue_info, sample_config, mock_logger)

        assert result is not None
        assert "P1-BUG-" in result.name


# =============================================================================
# Tests: Close Issue Flow
# =============================================================================


class TestCloseIssue:
    """Tests for close_issue function."""

    def test_full_close_flow(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Test complete close flow with git operations."""
        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured_commands.append(cmd)
            if "mv" in cmd:
                # Simulate git mv
                src = Path(cmd[2])
                dst = Path(cmd[3])
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    src.rename(dst)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if "commit" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="[main abc123] commit", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = close_issue(
                sample_issue_info,
                sample_config,
                mock_logger,
                close_reason="already_fixed",
                close_status="Closed - Already Fixed",
            )

        assert result is True
        mock_logger.success.assert_called()

        # Verify completed file exists
        completed = sample_config.get_completed_dir() / sample_issue_info.path.name
        assert completed.exists()

        # Verify resolution section added
        content = completed.read_text()
        assert "## Resolution" in content
        assert "Already Fixed" in content

    def test_close_when_already_completed(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        mock_logger: MagicMock,
    ) -> None:
        """Test closing when issue already in completed directory."""
        # Create issue in completed
        completed_dir = sample_config.get_completed_dir()
        completed_file = completed_dir / "P1-BUG-001-test.md"
        completed_file.write_text("Already completed")

        # Create original also (stale state)
        original = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_text("Original")

        info = IssueInfo(
            path=original,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = close_issue(info, sample_config, mock_logger, None, None)

        assert result is True
        # Original should be cleaned up
        assert not original.exists()

    def test_close_with_defaults(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Test close with default reason and status."""

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if "mv" in cmd:
                src = Path(cmd[2])
                dst = Path(cmd[3])
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    src.rename(dst)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = close_issue(sample_issue_info, sample_config, mock_logger, None, None)

        assert result is True
        completed = sample_config.get_completed_dir() / sample_issue_info.path.name
        content = completed.read_text()
        assert "Closed - Invalid" in content
        assert "unknown" in content

    def test_close_source_already_removed(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        mock_logger: MagicMock,
    ) -> None:
        """Test close when source file already removed."""
        info = IssueInfo(
            path=tmp_path / ".issues" / "bugs" / "nonexistent.md",
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        result = close_issue(info, sample_config, mock_logger, None, None)

        assert result is True
        mock_logger.info.assert_called()


# =============================================================================
# Tests: Complete Issue Lifecycle Flow
# =============================================================================


class TestCompleteIssueLifecycle:
    """Tests for complete_issue_lifecycle function."""

    def test_full_complete_flow(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Test complete lifecycle completion flow."""
        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured_commands.append(cmd)
            if "mv" in cmd:
                src = Path(cmd[2])
                dst = Path(cmd[3])
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    src.rename(dst)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if "commit" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="[main def456] commit", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = complete_issue_lifecycle(sample_issue_info, sample_config, mock_logger)

        assert result is True
        mock_logger.success.assert_called()

        # Verify completed file
        completed = sample_config.get_completed_dir() / sample_issue_info.path.name
        assert completed.exists()

        # Verify resolution with action
        content = completed.read_text()
        assert "## Resolution" in content
        assert "**Action**: fix" in content  # bugs category action

    def test_complete_when_already_in_completed(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        mock_logger: MagicMock,
    ) -> None:
        """Test completion when already in completed directory."""
        # Create in completed
        completed_dir = sample_config.get_completed_dir()
        completed_file = completed_dir / "P1-BUG-001-test.md"
        completed_file.write_text("Already done")

        # Create stale original
        original = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_text("Original")

        info = IssueInfo(
            path=original,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = complete_issue_lifecycle(info, sample_config, mock_logger)

        assert result is True
        assert not original.exists()

    def test_complete_source_already_removed(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        mock_logger: MagicMock,
    ) -> None:
        """Test completion when source already removed."""
        info = IssueInfo(
            path=tmp_path / ".issues" / "bugs" / "nonexistent.md",
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        result = complete_issue_lifecycle(info, sample_config, mock_logger)

        assert result is True
        mock_logger.info.assert_called()

    def test_complete_failure_handling(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Test handling of completion failure."""

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if "mv" in cmd:
                raise OSError("Disk full")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = complete_issue_lifecycle(sample_issue_info, sample_config, mock_logger)

        assert result is False
        mock_logger.error.assert_called()

    def test_uses_correct_action_for_category(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        mock_logger: MagicMock,
    ) -> None:
        """Test that correct action verb is used for different categories."""
        # Create feature issue
        feature_path = tmp_path / ".issues" / "features" / "P1-FEAT-001-test.md"
        feature_path.write_text("# FEAT-001: Test Feature")

        info = IssueInfo(
            path=feature_path,
            issue_type="features",
            priority="P1",
            issue_id="FEAT-001",
            title="Test Feature",
        )

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if "mv" in cmd:
                src = Path(cmd[2])
                dst = Path(cmd[3])
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    src.rename(dst)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = complete_issue_lifecycle(info, sample_config, mock_logger)

        assert result is True
        completed = sample_config.get_completed_dir() / feature_path.name
        content = completed.read_text()
        assert "**Action**: implement" in content  # features category action
