"""Tests for subprocess interactions with mocking.

Tests individual subprocess calls used throughout the codebase,
verifying correct command construction and result handling.
"""

from __future__ import annotations

import io
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock, patch, call

import pytest

from little_loops.logger import Logger

if TYPE_CHECKING:
    from typing import Any


class TestRunClaudeCommand:
    """Tests for run_claude_command in issue_manager.py."""

    @pytest.fixture
    def mock_logger(self) -> MagicMock:
        """Create a mock logger."""
        return MagicMock(spec=Logger)

    def test_success_returns_completed_process(self, mock_logger: MagicMock) -> None:
        """Successful command returns CompletedProcess with captured output."""
        mock_stdout = io.StringIO("Output line 1\nOutput line 2\n")
        mock_stderr = io.StringIO("")

        mock_process = Mock()
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector_cls:
                mock_selector = MagicMock()
                mock_selector_cls.return_value = mock_selector
                # Simulate no ready file objects (empty selector)
                mock_selector.get_map.side_effect = [True, False]
                mock_selector.select.return_value = []

                from little_loops.issue_manager import run_claude_command
                result = run_claude_command(
                    "/ll:test_command",
                    mock_logger,
                    timeout=60,
                    stream_output=False,
                )

        assert isinstance(result, subprocess.CompletedProcess)
        assert result.returncode == 0

    def test_command_includes_correct_arguments(self, mock_logger: MagicMock) -> None:
        """Command is constructed with correct claude CLI arguments."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        captured_args = []

        def capture_popen(*args: Any, **kwargs: Any) -> Mock:
            captured_args.append(args[0])
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector_cls:
                mock_selector = MagicMock()
                mock_selector_cls.return_value = mock_selector
                mock_selector.get_map.side_effect = [False]

                from little_loops.issue_manager import run_claude_command
                run_claude_command(
                    "/ll:ready_issue BUG-001",
                    mock_logger,
                    timeout=60,
                    stream_output=False,
                )

        assert len(captured_args) == 1
        assert captured_args[0] == [
            "claude",
            "--dangerously-skip-permissions",
            "-p",
            "/ll:ready_issue BUG-001",
        ]

    def test_timeout_kills_process(self, mock_logger: MagicMock) -> None:
        """Process is killed when timeout expires."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.kill = Mock()

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector_cls:
                mock_selector = MagicMock()
                mock_selector_cls.return_value = mock_selector
                mock_selector.get_map.return_value = True
                mock_selector.select.return_value = []

                with patch("time.time") as mock_time:
                    # First call returns start time, subsequent calls exceed timeout
                    mock_time.side_effect = [0, 0, 100]  # 100 > timeout of 1

                    from little_loops.issue_manager import run_claude_command

                    with pytest.raises(subprocess.TimeoutExpired):
                        run_claude_command(
                            "/ll:test",
                            mock_logger,
                            timeout=1,
                            stream_output=False,
                        )

        mock_process.kill.assert_called_once()

    def test_failure_returns_nonzero_returncode(self, mock_logger: MagicMock) -> None:
        """Failed command returns CompletedProcess with non-zero return code."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("Error occurred\n")
        mock_process.returncode = 1
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector_cls:
                mock_selector = MagicMock()
                mock_selector_cls.return_value = mock_selector
                mock_selector.get_map.side_effect = [False]

                from little_loops.issue_manager import run_claude_command
                result = run_claude_command(
                    "/ll:test",
                    mock_logger,
                    timeout=60,
                    stream_output=False,
                )

        assert result.returncode == 1


class TestCheckGitStatus:
    """Tests for check_git_status in issue_manager.py."""

    @pytest.fixture
    def mock_logger(self) -> MagicMock:
        """Create a mock logger."""
        return MagicMock(spec=Logger)

    def test_clean_returns_false(self, mock_logger: MagicMock) -> None:
        """Returns False when no uncommitted changes exist."""
        with patch("subprocess.run") as mock_run:
            # Both diff commands return 0 (no changes)
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            from little_loops.git_operations import check_git_status
            result = check_git_status(mock_logger)

        assert result is False
        assert mock_run.call_count == 2

    def test_dirty_working_dir_returns_true(self, mock_logger: MagicMock) -> None:
        """Returns True when working directory has uncommitted changes."""
        with patch("subprocess.run") as mock_run:
            # First call (git diff --quiet) returns 1 (has changes)
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )

            from little_loops.git_operations import check_git_status
            result = check_git_status(mock_logger)

        assert result is True
        mock_logger.warning.assert_called()

    def test_staged_changes_returns_true(self, mock_logger: MagicMock) -> None:
        """Returns True when there are staged changes."""
        with patch("subprocess.run") as mock_run:
            # First call returns 0 (no working changes)
            # Second call returns 1 (has staged changes)
            mock_run.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=""),
            ]

            from little_loops.git_operations import check_git_status
            result = check_git_status(mock_logger)

        assert result is True

    def test_correct_git_commands(self, mock_logger: MagicMock) -> None:
        """Verifies correct git commands are executed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            from little_loops.git_operations import check_git_status
            check_git_status(mock_logger)

        assert mock_run.call_count == 2
        calls = mock_run.call_args_list
        assert calls[0][0][0] == ["git", "diff", "--quiet"]
        assert calls[1][0][0] == ["git", "diff", "--cached", "--quiet"]


class TestVerifyWorkWasDone:
    """Tests for verify_work_was_done in issue_manager.py."""

    @pytest.fixture
    def mock_logger(self) -> MagicMock:
        """Create a mock logger."""
        return MagicMock(spec=Logger)

    def test_with_code_changes_returns_true(self, mock_logger: MagicMock) -> None:
        """Returns True when code files were changed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="src/main.py\nsrc/utils.py\n",
                stderr="",
            )

            from little_loops.git_operations import verify_work_was_done
            result = verify_work_was_done(mock_logger)

        assert result is True
        mock_logger.info.assert_called()

    def test_only_issue_files_returns_false(self, mock_logger: MagicMock) -> None:
        """Returns False when only issue files were changed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=".issues/bugs/BUG-001.md\n",
                stderr="",
            )

            from little_loops.git_operations import verify_work_was_done
            result = verify_work_was_done(mock_logger)

        assert result is False

    def test_no_changes_returns_false(self, mock_logger: MagicMock) -> None:
        """Returns False when no files were changed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            from little_loops.git_operations import verify_work_was_done
            result = verify_work_was_done(mock_logger)

        assert result is False

    def test_staged_code_changes_returns_true(self, mock_logger: MagicMock) -> None:
        """Returns True when staged code files exist."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # First call: no working changes
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                # Second call: staged code changes
                subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="src/feature.py\n", stderr=""
                ),
            ]

            from little_loops.git_operations import verify_work_was_done
            result = verify_work_was_done(mock_logger)

        assert result is True

    def test_markdown_files_count_as_work(self, mock_logger: MagicMock) -> None:
        """Markdown files outside excluded dirs count as meaningful work."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="README.md\nCHANGELOG.md\n",
                stderr="",
            )

            from little_loops.git_operations import verify_work_was_done
            result = verify_work_was_done(mock_logger)

        # Markdown files are now considered valid work
        assert result is True

    def test_excludes_thoughts_directory(self, mock_logger: MagicMock) -> None:
        """Files in thoughts/ directory are excluded from work detection."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="thoughts/notes.md\nthoughts/scratch.txt\n",
                stderr="",
            )

            from little_loops.git_operations import verify_work_was_done
            result = verify_work_was_done(mock_logger)

        assert result is False

    def test_exception_returns_false(self, mock_logger: MagicMock) -> None:
        """Returns False when an exception occurs."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError("Git not found")

            from little_loops.git_operations import verify_work_was_done
            result = verify_work_was_done(mock_logger)

        assert result is False
        mock_logger.error.assert_called()


class TestWorkerPoolSetupWorktree:
    """Tests for WorkerPool worktree setup subprocess calls."""

    @pytest.fixture
    def mock_logger(self) -> MagicMock:
        """Create a mock logger without spec to allow any method calls."""
        return MagicMock()

    def test_setup_worktree_creates_branch(self, mock_logger: MagicMock) -> None:
        """Worktree setup calls git worktree add with correct branch name."""
        import tempfile
        from pathlib import Path
        from little_loops.parallel.worker_pool import WorkerPool
        from little_loops.parallel.types import ParallelConfig
        from little_loops.config import BRConfig

        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured_commands.append(cmd)
            if cmd[0] == "git" and cmd[1] == "config":
                if "user.email" in cmd:
                    return subprocess.CompletedProcess(
                        cmd, 0, stdout="test@example.com\n", stderr=""
                    )
                if "user.name" in cmd:
                    return subprocess.CompletedProcess(
                        cmd, 0, stdout="Test User\n", stderr=""
                    )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            claude_dir = repo_path / ".claude"
            claude_dir.mkdir()
            (claude_dir / "ll-config.json").write_text("{}")
            (claude_dir / "settings.local.json").write_text("{}")

            worktree_base = repo_path / ".worktrees"
            worktree_base.mkdir()

            config = ParallelConfig(
                max_workers=2,
                worktree_base=worktree_base,
            )
            br_config = BRConfig(repo_path)

            pool = WorkerPool(config, br_config, mock_logger, repo_path)

            worktree_path = worktree_base / "ll-BUG-001"
            branch_name = "ll-BUG-001"

            with patch("subprocess.run", side_effect=mock_run):
                with patch("shutil.copy2"):
                    pool._setup_worktree(worktree_path, branch_name)

        # Check that git worktree add was called
        worktree_cmd = [c for c in captured_commands if "worktree" in c and "add" in c]
        assert len(worktree_cmd) >= 1
        assert "worktree" in worktree_cmd[0]
        assert "add" in worktree_cmd[0]
        assert "ll-BUG-001" in worktree_cmd[0]  # branch name should be in command

    def test_cleanup_worktree_removes_worktree(self, mock_logger: MagicMock) -> None:
        """Worktree cleanup calls git worktree remove."""
        import tempfile
        from pathlib import Path
        from little_loops.parallel.worker_pool import WorkerPool
        from little_loops.parallel.types import ParallelConfig
        from little_loops.config import BRConfig

        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured_commands.append(cmd)
            if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                # Return main so it skips branch deletion (won't delete main branch)
                return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            claude_dir = repo_path / ".claude"
            claude_dir.mkdir()
            (claude_dir / "ll-config.json").write_text("{}")

            worktree_base = repo_path / ".worktrees"
            worktree_base.mkdir()
            worktree_path = worktree_base / "ll-BUG-001"
            worktree_path.mkdir()

            config = ParallelConfig(
                max_workers=2,
                worktree_base=worktree_base,
            )
            br_config = BRConfig(repo_path)

            pool = WorkerPool(config, br_config, mock_logger, repo_path)

            with patch("subprocess.run", side_effect=mock_run):
                with patch("shutil.rmtree"):
                    pool._cleanup_worktree(worktree_path)

        # Check that git worktree remove was called
        remove_cmds = [c for c in captured_commands if "worktree" in c and "remove" in c]
        assert len(remove_cmds) >= 1


class TestMergeCoordinatorGitOperations:
    """Tests for MergeCoordinator git subprocess calls."""

    @pytest.fixture
    def mock_logger(self) -> MagicMock:
        """Create a mock logger without spec to allow any method calls."""
        return MagicMock()

    def test_stash_local_changes_command(self, mock_logger: MagicMock) -> None:
        """Stash local changes executes correct git commands."""
        import tempfile
        from pathlib import Path
        from little_loops.parallel.merge_coordinator import MergeCoordinator
        from little_loops.parallel.types import ParallelConfig

        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured_commands.append(cmd)
            if cmd[:3] == ["git", "status", "--porcelain"]:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="M src/file.py\n", stderr=""
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            config = ParallelConfig(max_workers=2)
            coordinator = MergeCoordinator(config, mock_logger, Path(tmpdir))

            with patch("subprocess.run", side_effect=mock_run):
                result = coordinator._stash_local_changes()

        assert result is True
        # Check git status --porcelain was called
        status_cmds = [c for c in captured_commands if "status" in c]
        assert len(status_cmds) >= 1
        # Check git stash push was called
        stash_cmds = [c for c in captured_commands if "stash" in c and "push" in c]
        assert len(stash_cmds) >= 1

    def test_pop_stash_command(self, mock_logger: MagicMock) -> None:
        """Pop stash executes correct git command when stash was applied."""
        import tempfile
        from pathlib import Path
        from little_loops.parallel.merge_coordinator import MergeCoordinator
        from little_loops.parallel.types import ParallelConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            config = ParallelConfig(max_workers=2)
            coordinator = MergeCoordinator(config, mock_logger, Path(tmpdir))
            coordinator._stash_active = True  # Use _stash_active not _stash_applied

            captured_commands: list[list[str]] = []

            def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                captured_commands.append(cmd)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run):
                coordinator._pop_stash()

            # Check git stash pop was called
            pop_cmds = [c for c in captured_commands if "stash" in c and "pop" in c]
            assert len(pop_cmds) >= 1

    def test_pop_stash_skips_when_no_stash(self, mock_logger: MagicMock) -> None:
        """Pop stash does nothing when no stash was applied."""
        import tempfile
        from pathlib import Path
        from little_loops.parallel.merge_coordinator import MergeCoordinator
        from little_loops.parallel.types import ParallelConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            config = ParallelConfig(max_workers=2)
            coordinator = MergeCoordinator(config, mock_logger, Path(tmpdir))
            # _stash_active defaults to False

            captured_commands: list[list[str]] = []

            def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                captured_commands.append(cmd)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run):
                coordinator._pop_stash()

            # No git commands should be called
            assert len(captured_commands) == 0

    def test_process_merge_uses_merge_request(self, mock_logger: MagicMock) -> None:
        """Process merge correctly uses MergeRequest wrapper."""
        import tempfile
        from pathlib import Path
        from little_loops.parallel.merge_coordinator import MergeCoordinator
        from little_loops.parallel.types import ParallelConfig, WorkerResult, MergeRequest

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            worktree_path = repo_path / ".worktrees" / "ll-BUG-001"
            worktree_path.mkdir(parents=True)

            config = ParallelConfig(max_workers=2, worktree_base=repo_path / ".worktrees")
            coordinator = MergeCoordinator(config, mock_logger, repo_path)

            worker_result = WorkerResult(
                issue_id="BUG-001",
                success=True,
                branch_name="ll-BUG-001",
                worktree_path=worktree_path,
            )
            merge_request = MergeRequest(worker_result=worker_result)

            captured_commands: list[list[str]] = []

            def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                captured_commands.append(cmd)
                if cmd == ["git", "status", "--porcelain"]:
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run):
                coordinator._process_merge(merge_request)

            # Verify checkout main was called
            checkout_cmds = [c for c in captured_commands if "checkout" in c and "main" in c]
            assert len(checkout_cmds) >= 1

            # Verify merge command was called with branch name
            merge_cmds = [c for c in captured_commands if "merge" in c and "ll-BUG-001" in c]
            assert len(merge_cmds) >= 1

    def test_restash_after_pull_with_local_changes(self, mock_logger: MagicMock) -> None:
        """Test that local changes appearing after pull are re-stashed."""
        import tempfile
        from pathlib import Path
        from little_loops.parallel.merge_coordinator import MergeCoordinator
        from little_loops.parallel.types import ParallelConfig, WorkerResult, MergeRequest

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            worktree_path = repo_path / ".worktrees" / "ll-BUG-001"
            worktree_path.mkdir(parents=True)

            config = ParallelConfig(max_workers=2, worktree_base=repo_path / ".worktrees")
            coordinator = MergeCoordinator(config, mock_logger, repo_path)

            worker_result = WorkerResult(
                issue_id="BUG-001",
                success=True,
                branch_name="ll-BUG-001",
                worktree_path=worktree_path,
            )
            merge_request = MergeRequest(worker_result=worker_result)

            captured_commands: list[list[str]] = []
            call_count = {"status": 0}

            def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                captured_commands.append(cmd)

                # First status check: clean (no changes)
                # Second status check (after pull fails): has changes
                if cmd[:3] == ["git", "status", "--porcelain"]:
                    call_count["status"] += 1
                    if call_count["status"] == 1:
                        # Initial check: clean
                        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                    else:
                        # After pull: local changes appeared
                        return subprocess.CompletedProcess(
                            cmd, 0, stdout="M .issues/completed/test.md\n", stderr=""
                        )

                # Checkout main: success
                if cmd[:3] == ["git", "checkout", "main"]:
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

                # Pull --rebase: fails with local changes error
                if cmd[:4] == ["git", "pull", "--rebase", "origin"]:
                    return subprocess.CompletedProcess(
                        cmd,
                        1,
                        stdout="",
                        stderr="error: Your local changes to the following files would be overwritten by merge:\n"
                        "  .issues/completed/test.md\n"
                        "Please commit your changes or stash them before you merge.",
                    )

                # Stash push: success
                if "stash" in cmd and "push" in cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

                # Stash pop: success
                if "stash" in cmd and "pop" in cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

                # Merge: success
                if "merge" in cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=mock_run):
                coordinator._process_merge(merge_request)

            # Verify that status was checked twice (initial + after pull failure)
            status_cmds = [c for c in captured_commands if "status" in c and "--porcelain" in c]
            assert len(status_cmds) >= 2, f"Expected 2+ status checks, got {len(status_cmds)}"

            # Verify that stash push was called (for re-stash)
            stash_push_cmds = [c for c in captured_commands if "stash" in c and "push" in c]
            assert len(stash_push_cmds) >= 1, "Expected stash push for re-stash"

            # Verify re-stash was logged
            mock_logger.info.assert_any_call("Re-stashed local changes after pull conflict")
