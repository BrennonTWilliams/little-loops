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
from little_loops.frontmatter import parse_frontmatter
from little_loops.issue_lifecycle import (
    FailureType,
    _build_closure_resolution,
    _build_completion_resolution,
    _commit_issue_completion,
    _prepare_issue_content,
    classify_failure,
    close_issue,
    complete_issue_lifecycle,
    create_issue_from_failure,
    defer_issue,
    undefer_issue,
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
    issue_path.write_text(
        "---\nstatus: open\ncaptured_at: '2026-05-20T10:00:00Z'\n---\n\n# BUG-001: Test Bug\n\n## Summary\nTest content."
    )
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
            "priorities": ["P0", "P1", "P2", "P3"],
        },
    }
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    config_path = ll_dir / "ll-config.json"
    config_path.write_text(json.dumps(config_data, indent=2))

    # Create issue type directories (status now lives in frontmatter, not directories)
    issues_dir = tmp_path / ".issues"
    (issues_dir / "bugs").mkdir(parents=True, exist_ok=True)
    (issues_dir / "features").mkdir(parents=True, exist_ok=True)
    (issues_dir / "enhancements").mkdir(parents=True, exist_ok=True)

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
        assert "**Closure**: Automated (ready-issue validation)" in result
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
        assert "### Files Changed" in result
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
    """Tests for verify_issue_completed function (frontmatter-based, ENH-1418)."""

    def test_status_done(
        self, tmp_path: Path, sample_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """status: done frontmatter on a file in its type dir verifies as completed."""
        issue_path = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        issue_path.parent.mkdir(parents=True, exist_ok=True)
        issue_path.write_text("---\nstatus: done\n---\n\n# BUG-001: Test")

        info = IssueInfo(
            path=issue_path,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        result = verify_issue_completed(info, sample_config, mock_logger)

        assert result is True
        mock_logger.success.assert_called()

    def test_status_cancelled(
        self, tmp_path: Path, sample_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """status: cancelled is also a valid completion state."""
        issue_path = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        issue_path.parent.mkdir(parents=True, exist_ok=True)
        issue_path.write_text("---\nstatus: cancelled\n---\n\n# BUG-001: Test")

        info = IssueInfo(
            path=issue_path,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        result = verify_issue_completed(info, sample_config, mock_logger)

        assert result is True
        mock_logger.success.assert_called()

    def test_status_open_returns_false(
        self, tmp_path: Path, sample_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """status: open or missing means not yet completed."""
        issue_path = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        issue_path.parent.mkdir(parents=True, exist_ok=True)
        issue_path.write_text("---\nstatus: open\n---\n\n# BUG-001: Test")

        info = IssueInfo(
            path=issue_path,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        result = verify_issue_completed(info, sample_config, mock_logger)

        assert result is False
        mock_logger.warning.assert_called()

    def test_status_completed_synonym_verified(
        self, tmp_path: Path, sample_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """status: completed is normalized to done, so verify_issue_completed returns True."""
        issue_path = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        issue_path.parent.mkdir(parents=True, exist_ok=True)
        issue_path.write_text("---\nstatus: completed\n---\n\n# BUG-001: Test")

        info = IssueInfo(
            path=issue_path,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        result = verify_issue_completed(info, sample_config, mock_logger)

        assert result is True
        mock_logger.success.assert_called()

    def test_source_missing_returns_true(
        self, tmp_path: Path, sample_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """If file has been removed entirely, treat as completed for back-compat."""
        info = IssueInfo(
            path=tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md",
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        result = verify_issue_completed(info, sample_config, mock_logger)

        assert result is True
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
        assert "Created:" in content
        assert "+00:00" in content
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
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        (ll_dir / "ll-config.json").write_text(json.dumps(config_data))
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

    def test_has_frontmatter_with_captured_at_and_status(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Failure-created issues have YAML frontmatter with captured_at and status: open (BUG-1647)."""
        from datetime import datetime

        from little_loops.frontmatter import parse_frontmatter

        result = create_issue_from_failure(
            "ValueError: test", sample_issue_info, sample_config, mock_logger
        )

        assert result is not None
        content = result.read_text()
        fm = parse_frontmatter(content)
        assert "captured_at" in fm, f"captured_at missing from frontmatter: {fm}"
        assert fm.get("status") == "open", f"status not 'open': {fm}"
        # captured_at should be a parseable ISO datetime
        captured = str(fm["captured_at"])
        dt = datetime.fromisoformat(captured.rstrip("Z").replace("+00:00", ""))
        assert dt.year >= 2026


# =============================================================================
# Tests: Failure Classification
# =============================================================================


class TestClassifyFailure:
    """Tests for classify_failure function."""

    @pytest.mark.parametrize(
        ("error_output", "expected_type", "expected_reason_contains"),
        [
            # API quota/rate limit patterns
            (
                "Error: You're out of extra usage · resets 2pm",
                "TRANSIENT",
                "quota",
            ),
            ("Rate limit exceeded. Please retry after 60s", "TRANSIENT", "quota"),
            ("Error 429: Too many requests", "TRANSIENT", "quota"),
            ("API quota exceeded for model", "TRANSIENT", "quota"),
            ("ResourceExhausted: quota limit reached", "TRANSIENT", "quota"),
            # Network/connectivity patterns
            ("Connection refused: localhost:8080", "TRANSIENT", "network"),
            ("Error: Connection timeout after 30s", "TRANSIENT", "network"),
            ("DNS resolution failed for api.example.com", "TRANSIENT", "network"),
            ("503 Service Unavailable", "TRANSIENT", "network"),
            ("502 Bad Gateway", "TRANSIENT", "network"),
            ("Error: ECONNREFUSED", "TRANSIENT", "network"),
            # Timeout patterns
            ("Command timed out after 3600 seconds", "TRANSIENT", "timeout"),
            ("Operation timed out waiting for response", "TRANSIENT", "timeout"),
            ("Deadline exceeded for RPC call", "TRANSIENT", "timeout"),
            # Resource patterns
            ("Error: No space left on device", "TRANSIENT", "resource"),
            ("Out of memory while processing", "TRANSIENT", "resource"),
            ("Too many open files", "TRANSIENT", "resource"),
            # API server error patterns
            (
                "API Error: The server had an error while processing your request",
                "TRANSIENT",
                "api server",
            ),
            ("529 overloaded_error: model capacity exceeded", "TRANSIENT", "api server"),
            ("internal server error from upstream", "TRANSIENT", "api server"),
            ("Error: overloaded — please retry", "TRANSIENT", "api server"),
            # Context window exhaustion patterns (BUG-1375)
            ("Prompt is too long", "TRANSIENT", "context"),
            ("Context length exceeded for model claude-3-opus", "TRANSIENT", "context"),
            ("Error: context window limit reached", "TRANSIENT", "context"),
            ("Maximum context exceeded", "TRANSIENT", "context"),
            # CLI session continuation errors (BUG-1386)
            (
                "Error: --resume requires a valid session ID or session title when used with --print.",
                "TRANSIENT",
                "session",
            ),
            (
                "Error: --continue requires a valid session title when used with --print.",
                "TRANSIENT",
                "session",
            ),
            # Shell sandbox environment errors (exit 127 indicators)
            ("(eval): command not found: grep", "TRANSIENT", "sandbox"),
            ("bash: status: read-only variable", "TRANSIENT", "sandbox"),
            # Process killed by OS (exit 137 / SIGKILL / OOM)
            ("Killed", "TRANSIENT", "killed"),
            ("Process was Killed by signal 9", "TRANSIENT", "killed"),
            # User-cancelled tool calls
            ("<tool_use_error>Cancelled", "TRANSIENT", "cancelled"),
            # Ad-hoc Python snippet tracebacks
            ('File "<string>", line 1\nNameError: name \'true\' is not defined', "TRANSIENT", "snippet"),
            ('File "<stdin>", line 3\nSyntaxError: invalid syntax', "TRANSIENT", "snippet"),
            # Real failure patterns
            ("SyntaxError: unexpected token at line 42", "REAL", "implementation"),
            (
                "FAILED tests/test_foo.py::test_bar - AssertionError",
                "REAL",
                "implementation",
            ),
            ("ValueError: Invalid input provided", "REAL", "implementation"),
            ("TypeError: 'NoneType' has no attribute 'foo'", "REAL", "implementation"),
            ("ModuleNotFoundError: No module named 'missing'", "REAL", "implementation"),
        ],
    )
    def test_classify_failure_patterns(
        self, error_output: str, expected_type: str, expected_reason_contains: str
    ) -> None:
        """Test that failure patterns are classified correctly."""

        failure_type, reason = classify_failure(error_output, 1)
        expected = FailureType[expected_type]
        assert failure_type == expected, f"Expected {expected} for: {error_output[:50]}"
        assert expected_reason_contains in reason.lower(), (
            f"Expected '{expected_reason_contains}' in: {reason}"
        )

    def test_classify_failure_case_insensitive(self) -> None:
        """Test that pattern matching is case insensitive."""

        # Uppercase
        failure_type, _ = classify_failure("RATE LIMIT EXCEEDED", 1)
        assert failure_type == FailureType.TRANSIENT

        # Mixed case
        failure_type, _ = classify_failure("Connection Timeout occurred", 1)
        assert failure_type == FailureType.TRANSIENT

    def test_classify_failure_empty_output(self) -> None:
        """Test classification of empty error output."""

        failure_type, reason = classify_failure("", 1)
        assert failure_type == FailureType.REAL
        assert "implementation" in reason.lower()

    def test_classify_failure_unknown_error(self) -> None:
        """Test classification of unknown error types."""

        failure_type, reason = classify_failure("Some random error message", 1)
        assert failure_type == FailureType.REAL
        assert "implementation" in reason.lower()

    def test_classify_failure_multiline_output(self) -> None:
        """Test pattern matching works on multiline output."""

        error_output = """Some context here
Traceback (most recent call last):
  File "test.py", line 10
Error: You're out of extra usage · resets 2pm
More context after"""

        failure_type, _ = classify_failure(error_output, 1)
        assert failure_type == FailureType.TRANSIENT


# =============================================================================
# Tests: Close Issue Flow
# =============================================================================


class TestCloseIssue:
    """Tests for close_issue function (frontmatter-based, ENH-1418)."""

    def test_full_close_flow(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """close_issue writes status: done + completed_at to frontmatter at the original path."""

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
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

        # File stays in its type dir; only frontmatter changes
        assert sample_issue_info.path.exists()
        content = sample_issue_info.path.read_text()
        assert "## Resolution" in content
        assert "Already Fixed" in content

        fm = parse_frontmatter(content)
        assert fm.get("status") == "done"
        completed_at = fm.get("completed_at", "").strip("'\"")
        assert completed_at.endswith("Z")

    def test_close_with_defaults(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Test close with default reason and status."""

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = close_issue(sample_issue_info, sample_config, mock_logger, None, None)

        assert result is True
        content = sample_issue_info.path.read_text()
        assert "Closed - Invalid" in content
        assert "unknown" in content
        assert parse_frontmatter(content).get("status") == "done"

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

    def test_interceptor_veto_prevents_close(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Interceptor returning False vetoes close; frontmatter is not updated."""
        veto_interceptor = MagicMock()
        veto_interceptor.before_issue_close.return_value = False

        original_content = sample_issue_info.path.read_text()

        result = close_issue(
            sample_issue_info,
            sample_config,
            mock_logger,
            close_reason="already_fixed",
            close_status="Closed - Already Fixed",
            interceptors=[veto_interceptor],
        )

        assert result is False
        veto_interceptor.before_issue_close.assert_called_once_with(sample_issue_info)
        # File untouched (frontmatter still status: open)
        assert sample_issue_info.path.read_text() == original_content
        assert parse_frontmatter(sample_issue_info.path.read_text()).get("status") == "open"

    def test_interceptor_passthrough_allows_close(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Interceptor returning None allows close to proceed normally."""
        allow_interceptor = MagicMock()
        allow_interceptor.before_issue_close.return_value = None

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = close_issue(
                sample_issue_info,
                sample_config,
                mock_logger,
                close_reason="already_fixed",
                close_status="Closed - Already Fixed",
                interceptors=[allow_interceptor],
            )

        assert result is True
        allow_interceptor.before_issue_close.assert_called_once_with(sample_issue_info)
        assert parse_frontmatter(sample_issue_info.path.read_text()).get("status") == "done"

    def test_multiple_interceptors_called_in_order(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Multiple interceptors are called in registration order."""
        call_order: list[str] = []

        interceptor_a = MagicMock()
        interceptor_a.before_issue_close.side_effect = lambda info: call_order.append("a") or None
        interceptor_b = MagicMock()
        interceptor_b.before_issue_close.side_effect = lambda info: call_order.append("b") or None

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = close_issue(
                sample_issue_info,
                sample_config,
                mock_logger,
                close_reason="already_fixed",
                close_status="Closed - Already Fixed",
                interceptors=[interceptor_a, interceptor_b],
            )

        assert result is True
        assert call_order == ["a", "b"]

    def test_first_veto_short_circuits_remaining_interceptors(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """First interceptor returning False short-circuits remaining interceptors."""
        interceptor_a = MagicMock()
        interceptor_a.before_issue_close.return_value = False
        interceptor_b = MagicMock()
        interceptor_b.before_issue_close.return_value = None

        original_content = sample_issue_info.path.read_text()

        result = close_issue(
            sample_issue_info,
            sample_config,
            mock_logger,
            close_reason="already_fixed",
            close_status="Closed - Already Fixed",
            interceptors=[interceptor_a, interceptor_b],
        )

        assert result is False
        interceptor_a.before_issue_close.assert_called_once_with(sample_issue_info)
        interceptor_b.before_issue_close.assert_not_called()
        # File untouched
        assert sample_issue_info.path.read_text() == original_content


# =============================================================================
# Tests: Complete Issue Lifecycle Flow
# =============================================================================


class TestCompleteIssueLifecycle:
    """Tests for complete_issue_lifecycle function (frontmatter-based, ENH-1418)."""

    def test_full_complete_flow(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """complete_issue_lifecycle writes status: done + completed_at to frontmatter at the original path."""

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if "commit" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="[main def456] commit", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = complete_issue_lifecycle(sample_issue_info, sample_config, mock_logger)

        assert result is True
        mock_logger.success.assert_called()

        # File stays at the original path
        assert sample_issue_info.path.exists()
        content = sample_issue_info.path.read_text()
        assert "## Resolution" in content
        assert "**Action**: fix" in content  # bugs category action

        fm = parse_frontmatter(content)
        assert fm.get("status") == "done"
        completed_at = fm.get("completed_at", "").strip("'\"")
        assert completed_at.endswith("Z")

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
        """Test handling of write failure."""

        with patch.object(Path, "write_text", side_effect=OSError("Disk full")):
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
        feature_path = tmp_path / ".issues" / "features" / "P1-FEAT-001-test.md"
        feature_path.write_text("---\nstatus: open\n---\n\n# FEAT-001: Test Feature")

        info = IssueInfo(
            path=feature_path,
            issue_type="features",
            priority="P1",
            issue_id="FEAT-001",
            title="Test Feature",
        )

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = complete_issue_lifecycle(info, sample_config, mock_logger)

        assert result is True
        content = feature_path.read_text()
        assert "**Action**: implement" in content  # features category action
        assert parse_frontmatter(content).get("status") == "done"

    def test_appends_session_log_on_successful_completion(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """append_session_log_entry is called after frontmatter is updated to status: done."""

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with (
            patch("subprocess.run", side_effect=mock_run),
            patch("little_loops.issue_lifecycle.append_session_log_entry") as mock_log,
        ):
            result = complete_issue_lifecycle(sample_issue_info, sample_config, mock_logger)

        assert result is True
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args.args[1] == "ll-auto"


# =============================================================================
# Defer / Undefer Tests
# =============================================================================


class TestDeferIssue:
    """Tests for defer_issue function (frontmatter-based, ENH-1418)."""

    def test_defer_success(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """defer_issue writes status: deferred to frontmatter at the original path."""

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if "commit" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="[main abc123] commit", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = defer_issue(
                sample_issue_info,
                sample_config,
                mock_logger,
                reason="Waiting for dependency",
            )

        assert result is True
        mock_logger.success.assert_called()
        # File stays in its type dir
        assert sample_issue_info.path.exists()
        content = sample_issue_info.path.read_text()
        assert "## Deferred" in content
        assert "Waiting for dependency" in content
        assert parse_frontmatter(content).get("status") == "deferred"

    def test_defer_source_missing(
        self,
        sample_config: BRConfig,
        mock_logger: MagicMock,
    ) -> None:
        """Test deferring when source file is missing."""
        info = IssueInfo(
            path=Path("/nonexistent/P1-BUG-999-missing.md"),
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-999",
            title="Missing",
        )

        result = defer_issue(info, sample_config, mock_logger, reason="test")

        assert result is True
        mock_logger.info.assert_called()

    def test_defer_default_reason(
        self,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Test deferral uses default reason when none provided."""

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = defer_issue(sample_issue_info, sample_config, mock_logger, reason=None)

        assert result is True
        content = sample_issue_info.path.read_text()
        assert "Intentionally set aside" in content
        assert parse_frontmatter(content).get("status") == "deferred"


class TestUndeferIssue:
    """Tests for undefer_issue function (frontmatter-based, ENH-1418)."""

    def test_undefer_success(
        self,
        sample_config: BRConfig,
        mock_logger: MagicMock,
    ) -> None:
        """undefer_issue writes status: open to frontmatter at the existing path."""
        bugs_dir = sample_config.get_issue_dir("bugs")
        deferred_path = bugs_dir / "P1-BUG-001-test-bug.md"
        deferred_path.write_text(
            "---\nstatus: deferred\n---\n\n# BUG-001: Test Bug\n\n## Summary\nTest."
        )

        call_log: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_log.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = undefer_issue(
                sample_config, deferred_path, mock_logger, reason="Ready to work on"
            )

        assert result is not None
        # File stays in its type dir; same path returned
        assert result == deferred_path
        assert result.parent.name == "bugs"
        content = result.read_text()
        assert "## Undeferred" in content
        assert "Ready to work on" in content
        assert parse_frontmatter(content).get("status") == "open"
        mock_logger.success.assert_called()

        # Verify git commit was called with correct message
        commit_cmds = [cmd for cmd in call_log if "commit" in cmd]
        assert len(commit_cmds) == 1
        commit_msg = commit_cmds[0][commit_cmds[0].index("-m") + 1]
        assert "undefer(bugs):" in commit_msg
        assert "BUG-001" in commit_msg

    def test_undefer_source_missing(
        self,
        sample_config: BRConfig,
        mock_logger: MagicMock,
    ) -> None:
        """Test undeferring when deferred file doesn't exist."""
        result = undefer_issue(sample_config, Path("/nonexistent.md"), mock_logger, reason="test")
        assert result is None
        mock_logger.error.assert_called()

    def test_undefer_commits(
        self,
        sample_config: BRConfig,
        mock_logger: MagicMock,
    ) -> None:
        """Test that undefer_issue creates a git commit with the correct message."""
        bugs_dir = sample_config.get_issue_dir("bugs")
        deferred_path = bugs_dir / "P2-BUG-007-old-bug.md"
        deferred_path.write_text(
            "---\nstatus: deferred\n---\n\n# BUG-007: Old Bug\n\n## Summary\nDeferred before."
        )

        committed_messages: list[str] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if "commit" in cmd:
                idx = cmd.index("-m")
                committed_messages.append(cmd[idx + 1])
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="[main abc1234] commit", stderr=""
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = undefer_issue(
                sample_config, deferred_path, mock_logger, reason="Dependency resolved"
            )

        assert result is not None
        assert len(committed_messages) == 1
        msg = committed_messages[0]
        assert msg.startswith("undefer(bugs):")
        assert "BUG-007 - Undeferred" in msg
        assert "Dependency resolved" in msg


# =============================================================================
# EventBus Emission Tests
# =============================================================================


class TestEventBusEmission:
    """Tests for EventBus event emission in lifecycle functions."""

    def test_close_issue_emits_event(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """close_issue() emits issue.closed event when event_bus is provided."""
        from little_loops.events import EventBus

        received: list[dict[str, Any]] = []
        bus = EventBus()
        bus.register(lambda e: received.append(e))

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[main abc] commit", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = close_issue(
                sample_issue_info,
                sample_config,
                mock_logger,
                close_reason="already_fixed",
                close_status="Closed - Already Fixed",
                event_bus=bus,
            )

        assert result is True
        assert len(received) == 1
        event = received[0]
        assert event["event"] == "issue.closed"
        assert event["issue_id"] == sample_issue_info.issue_id
        # file_path is the type-dir path; file stays in place
        assert event["file_path"] == str(sample_issue_info.path)
        assert event["close_reason"] == "already_fixed"
        assert "ts" in event
        assert event["captured_at"] == "2026-05-20T10:00:00Z"

    def test_complete_issue_lifecycle_emits_event(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """complete_issue_lifecycle() emits issue.completed event."""
        from little_loops.events import EventBus

        received: list[dict[str, Any]] = []
        bus = EventBus()
        bus.register(lambda e: received.append(e))

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[main abc] commit", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = complete_issue_lifecycle(
                sample_issue_info,
                sample_config,
                mock_logger,
                event_bus=bus,
            )

        assert result is True
        assert len(received) == 1
        event = received[0]
        assert event["event"] == "issue.completed"
        assert event["issue_id"] == sample_issue_info.issue_id
        assert event["file_path"] == str(sample_issue_info.path)
        assert "ts" in event
        assert event["captured_at"] == "2026-05-20T10:00:00Z"

    def test_defer_issue_emits_event(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """defer_issue() emits issue.deferred event with type-dir file_path."""
        from little_loops.events import EventBus

        received: list[dict[str, Any]] = []
        bus = EventBus()
        bus.register(lambda e: received.append(e))

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[main abc] commit", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = defer_issue(
                sample_issue_info,
                sample_config,
                mock_logger,
                reason="Waiting for dependency",
                event_bus=bus,
            )

        assert result is True
        assert len(received) == 1
        event = received[0]
        assert event["event"] == "issue.deferred"
        assert event["issue_id"] == sample_issue_info.issue_id
        # file_path points to the type-dir path (no longer moves to deferred/)
        assert event["file_path"] == str(sample_issue_info.path)
        assert event["reason"] == "Waiting for dependency"
        assert "ts" in event
        assert event["captured_at"] == "2026-05-20T10:00:00Z"

    def test_create_issue_from_failure_emits_event(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """create_issue_from_failure() emits issue.failure_captured event."""
        from little_loops.events import EventBus

        received: list[dict[str, Any]] = []
        bus = EventBus()
        bus.register(lambda e: received.append(e))

        result = create_issue_from_failure(
            "ValueError: test error",
            sample_issue_info,
            sample_config,
            mock_logger,
            event_bus=bus,
        )

        assert result is not None
        assert len(received) == 1
        event = received[0]
        assert event["event"] == "issue.failure_captured"
        assert "issue_id" in event
        assert "file_path" in event
        assert event["parent_issue_id"] == sample_issue_info.issue_id
        assert "ts" in event
        assert "captured_at" in event
        assert event["captured_at"] is not None

    def test_no_emission_without_event_bus(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Functions work without event_bus (backward compat, no error)."""
        result = create_issue_from_failure(
            "Error occurred",
            sample_issue_info,
            sample_config,
            mock_logger,
        )
        assert result is not None

    def test_skip_issue_emits_event(self, tmp_path: Path) -> None:
        """skip_issue() emits issue.skipped event when event_bus is provided."""
        from little_loops.events import EventBus
        from little_loops.issue_lifecycle import skip_issue

        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        original = bugs_dir / "P3-BUG-042-slow-query.md"
        original.write_text(
            "---\nstatus: open\ncaptured_at: '2026-05-20T10:00:00Z'\n---\n\n# BUG-042: Slow Query\n"
        )
        new_path = bugs_dir / "P5-BUG-042-slow-query.md"

        received: list[dict] = []
        bus = EventBus()
        bus.register(lambda e: received.append(e))

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            skip_issue(original, new_path, reason="low priority", event_bus=bus)

        assert len(received) == 1
        event = received[0]
        assert event["event"] == "issue.skipped"
        assert event["issue_id"] == "BUG-042"
        assert event["file_path"] == str(new_path)
        assert event["reason"] == "low priority"
        assert "ts" in event
        assert event["captured_at"] == "2026-05-20T10:00:00Z"

    def test_undefer_issue_emits_event(
        self,
        sample_config: BRConfig,
        mock_logger: MagicMock,
    ) -> None:
        """undefer_issue() emits issue.started event when event_bus is provided."""
        from little_loops.events import EventBus
        from little_loops.issue_lifecycle import undefer_issue

        bugs_dir = sample_config.get_issue_dir("bugs")
        deferred_path = bugs_dir / "P2-BUG-007-old-bug.md"
        deferred_path.write_text(
            "---\nid: BUG-007\nstatus: deferred\ntype: BUG\npriority: P2\ncaptured_at: '2026-05-20T10:00:00Z'\n---\n"
            "\n# BUG-007: Old Bug\n\n## Summary\nDeferred before."
        )

        received: list[dict] = []
        bus = EventBus()
        bus.register(lambda e: received.append(e))

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[main abc] commit", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = undefer_issue(
                sample_config, deferred_path, mock_logger, reason="Ready", event_bus=bus
            )

        assert result is not None
        assert len(received) == 1
        event = received[0]
        assert event["event"] == "issue.started"
        assert event["issue_id"] == "BUG-007"
        assert event["file_path"] == str(deferred_path)
        assert event["reason"] == "Ready"
        assert "ts" in event
        assert event["captured_at"] == "2026-05-20T10:00:00Z"

    def test_skip_issue_no_emission_without_event_bus(self, tmp_path: Path) -> None:
        """skip_issue() works without event_bus (backward compat, no error)."""
        from little_loops.issue_lifecycle import skip_issue

        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        original = bugs_dir / "P3-BUG-099-noise.md"
        original.write_text("---\nstatus: open\n---\n\n# BUG-099: Noise\n")
        new_path = bugs_dir / "P5-BUG-099-noise.md"

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            skip_issue(original, new_path)  # no event_bus — should not raise

        assert new_path.exists()

    def test_undefer_issue_no_emission_without_event_bus(
        self,
        sample_config: BRConfig,
        mock_logger: MagicMock,
    ) -> None:
        """undefer_issue() works without event_bus (backward compat, no error)."""
        from little_loops.issue_lifecycle import undefer_issue

        bugs_dir = sample_config.get_issue_dir("bugs")
        deferred_path = bugs_dir / "P2-BUG-008-silent.md"
        deferred_path.write_text(
            "---\nid: BUG-008\nstatus: deferred\ntype: BUG\npriority: P2\n---\n"
            "\n# BUG-008: Silent\n\n## Summary\nDeferred."
        )

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[main abc] commit", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            result = undefer_issue(sample_config, deferred_path, mock_logger)

        assert result is not None


# =============================================================================
# Skip Tests
# =============================================================================


class TestSkip:
    """Tests for skip_issue() basic behavior."""

    def test_skip_issue_success(self, tmp_path: Path) -> None:
        """skip_issue renames file and appends Skip Log section."""
        from little_loops.issue_lifecycle import skip_issue

        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        original = bugs_dir / "P3-BUG-010-noisy.md"
        original.write_text("---\nstatus: open\n---\n\n# BUG-010: Noisy\n")
        new_path = bugs_dir / "P5-BUG-010-noisy.md"

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            skip_issue(original, new_path, reason="low priority")

        assert new_path.exists()
        assert not original.exists()
        content = new_path.read_text()
        assert "## Skip Log" in content
        assert "low priority" in content

    def test_skip_issue_raises_when_missing(self, tmp_path: Path) -> None:
        """skip_issue raises FileNotFoundError when original path doesn't exist."""
        from little_loops.issue_lifecycle import skip_issue

        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        with pytest.raises(FileNotFoundError):
            skip_issue(bugs_dir / "nonexistent.md", bugs_dir / "P5-BUG-000-x.md")

    def test_skip_issue_raises_when_target_exists(self, tmp_path: Path) -> None:
        """skip_issue raises FileExistsError when target path already exists."""
        from little_loops.issue_lifecycle import skip_issue

        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        original = bugs_dir / "P3-BUG-011-dupe.md"
        original.write_text("---\nstatus: open\n---\n")
        target = bugs_dir / "P5-BUG-011-dupe.md"
        target.write_text("already here")
        with pytest.raises(FileExistsError):
            skip_issue(original, target)
