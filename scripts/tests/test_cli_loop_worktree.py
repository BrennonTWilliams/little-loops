"""Tests for ll-loop run --worktree flag (ENH-945)."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from little_loops.parallel.git_lock import GitLock
from little_loops.worktree_utils import cleanup_worktree, setup_worktree

if TYPE_CHECKING:
    from little_loops.parallel.worker_pool import WorkerPool

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_git_lock(logger: MagicMock | None = None) -> GitLock:
    return GitLock(logger=logger)


def _ok(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, "", "")


def _ok_with_stdout(stdout: str) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Return a mock git-lock side_effect that yields stdout for every call."""

    def _impl(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout, "")

    return _impl


# ---------------------------------------------------------------------------
# worktree_utils.setup_worktree
# ---------------------------------------------------------------------------


class TestSetupWorktree:
    """Unit tests for worktree_utils.setup_worktree()."""

    def test_calls_git_worktree_add(self, tmp_path: Path) -> None:
        """setup_worktree() issues 'git worktree add -b <branch> <path>'."""
        repo = tmp_path / "repo"
        repo.mkdir()
        wt = tmp_path / "wt"
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        captured: list[list[str]] = []

        def _mock_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            captured.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(git_lock, "run", side_effect=_mock_run):
            with patch("subprocess.run", return_value=_ok()):
                with patch("shutil.copytree"):
                    setup_worktree(
                        repo_path=repo,
                        worktree_path=wt,
                        branch_name="20260101-000000-my-loop",
                        copy_files=[],
                        logger=logger,
                        git_lock=git_lock,
                    )

        add_calls = [c for c in captured if "add" in c and "worktree" in c]
        assert add_calls, "Expected 'git worktree add' call"
        assert "20260101-000000-my-loop" in add_calls[0]
        assert str(wt) in add_calls[0]

    def test_raises_on_git_failure(self, tmp_path: Path) -> None:
        """setup_worktree() raises RuntimeError when git worktree add fails."""
        repo = tmp_path / "repo"
        repo.mkdir()
        wt = tmp_path / "wt"
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        def _mock_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if "add" in args:
                return subprocess.CompletedProcess(args, 1, "", "fatal: branch exists")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(git_lock, "run", side_effect=_mock_run):
            with pytest.raises(RuntimeError, match="Failed to create worktree"):
                setup_worktree(
                    repo_path=repo,
                    worktree_path=wt,
                    branch_name="test-branch",
                    copy_files=[],
                    logger=logger,
                    git_lock=git_lock,
                )

    def test_copies_claude_directory(self, tmp_path: Path) -> None:
        """setup_worktree() copies .claude/ to worktree via shutil.copytree (BUG-007)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        claude_dir = repo / ".claude"
        claude_dir.mkdir()
        wt = tmp_path / "wt"
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        copytree_calls: list[tuple[Path, Path]] = []

        def _mock_copytree(src: Path, dst: Path, **kw: object) -> Path:
            copytree_calls.append((Path(src), Path(dst)))
            return Path(dst)

        with patch.object(git_lock, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            with patch("subprocess.run", return_value=_ok()):
                with patch("shutil.copytree", side_effect=_mock_copytree):
                    setup_worktree(
                        repo_path=repo,
                        worktree_path=wt,
                        branch_name="branch",
                        copy_files=[],
                        logger=logger,
                        git_lock=git_lock,
                    )

        assert any(".claude" in str(src) for src, _ in copytree_calls), (
            "Expected .claude/ to be copied"
        )

    def test_copies_configured_files(self, tmp_path: Path) -> None:
        """setup_worktree() copies non-.claude/ files from copy_files list."""
        repo = tmp_path / "repo"
        repo.mkdir()
        env_file = repo / ".env"
        env_file.write_text("SECRET=xyz")
        wt = tmp_path / "wt"
        wt.mkdir()
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        copy2_calls: list[tuple[Path, Path]] = []

        def _mock_copy2(src: object, dst: object) -> None:
            copy2_calls.append((Path(str(src)), Path(str(dst))))

        with patch.object(git_lock, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            with patch("subprocess.run", return_value=_ok()):
                with patch("shutil.copytree"):
                    with patch("shutil.copy2", side_effect=_mock_copy2):
                        setup_worktree(
                            repo_path=repo,
                            worktree_path=wt,
                            branch_name="branch",
                            copy_files=[".env"],
                            logger=logger,
                            git_lock=git_lock,
                        )

        assert any(".env" in str(src) for src, _ in copy2_calls)

    def test_skips_claude_prefixed_copy_files(self, tmp_path: Path) -> None:
        """.claude/ prefixed copy_files are not re-copied (already in copytree)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        wt = tmp_path / "wt"
        wt.mkdir()
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        copy2_calls: list[str] = []

        def _mock_copy2(src: object, dst: object) -> None:
            copy2_calls.append(str(src))

        with patch.object(git_lock, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            with patch("subprocess.run", return_value=_ok()):
                with patch("shutil.copytree"):
                    with patch("shutil.copy2", side_effect=_mock_copy2):
                        setup_worktree(
                            repo_path=repo,
                            worktree_path=wt,
                            branch_name="branch",
                            copy_files=[".claude/settings.local.json"],
                            logger=logger,
                            git_lock=git_lock,
                        )

        assert not copy2_calls, ".claude/ prefixed files should not be copied via copy2"

    def test_removes_existing_worktree_before_creating(self, tmp_path: Path) -> None:
        """If worktree_path already exists, setup_worktree() cleans it up first."""
        repo = tmp_path / "repo"
        repo.mkdir()
        wt = tmp_path / "wt"
        wt.mkdir()  # pre-existing
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        remove_calls: list[list[str]] = []

        def _mock_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if "remove" in args:
                remove_calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(git_lock, "run", side_effect=_mock_run):
            with patch("subprocess.run", return_value=_ok()):
                with patch("shutil.copytree"):
                    with patch("shutil.rmtree"):
                        setup_worktree(
                            repo_path=repo,
                            worktree_path=wt,
                            branch_name="branch",
                            copy_files=[],
                            logger=logger,
                            git_lock=git_lock,
                        )

        assert remove_calls, "Expected 'git worktree remove' before creating"

    def test_writes_session_marker(self, tmp_path: Path) -> None:
        """setup_worktree() writes .ll-session-<pid> marker inside the worktree."""
        import os

        repo = tmp_path / "repo"
        repo.mkdir()
        wt = tmp_path / "wt"
        wt.mkdir()
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        # Patch shutil.rmtree so the pre-existing wt dir isn't deleted during cleanup
        with patch.object(git_lock, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            with patch("subprocess.run", return_value=_ok()):
                with patch("shutil.copytree"):
                    with patch("shutil.rmtree"):
                        setup_worktree(
                            repo_path=repo,
                            worktree_path=wt,
                            branch_name="branch",
                            copy_files=[],
                            logger=logger,
                            git_lock=git_lock,
                        )

        marker = wt / f".ll-session-{os.getpid()}"
        assert marker.exists(), f"Expected session marker at {marker}"
        assert marker.read_text() == str(os.getpid())

    def test_base_branch_valid_issues_verify_before_add(self, tmp_path: Path) -> None:
        """When base_branch is provided, git rev-parse --verify is called before worktree add."""
        repo = tmp_path / "repo"
        repo.mkdir()
        wt = tmp_path / "wt"
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        called_args: list[list[str]] = []

        def _mock_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            called_args.append(list(args))
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(git_lock, "run", side_effect=_mock_run):
            with patch("subprocess.run", return_value=_ok()):
                with patch("shutil.copytree"):
                    setup_worktree(
                        repo_path=repo,
                        worktree_path=wt,
                        branch_name="branch",
                        copy_files=[],
                        logger=logger,
                        git_lock=git_lock,
                        base_branch="main",
                    )

        verify_calls = [c for c in called_args if "--verify" in c]
        assert verify_calls, "Expected a 'rev-parse --verify' call"
        assert "main" in verify_calls[0]

        add_calls = [c for c in called_args if "add" in c and "worktree" in c]
        assert add_calls, "Expected 'git worktree add' after verify"
        assert "main" in add_calls[0]

    def test_base_branch_invalid_raises_runtime_error(self, tmp_path: Path) -> None:
        """When base_branch does not resolve, RuntimeError is raised before creating worktree."""
        repo = tmp_path / "repo"
        repo.mkdir()
        wt = tmp_path / "wt"
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        def _mock_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if "--verify" in args:
                return subprocess.CompletedProcess(args, 1, "", "fatal: not a valid object name")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(git_lock, "run", side_effect=_mock_run):
            with pytest.raises(RuntimeError, match="does not resolve"):
                setup_worktree(
                    repo_path=repo,
                    worktree_path=wt,
                    branch_name="branch",
                    copy_files=[],
                    logger=logger,
                    git_lock=git_lock,
                    base_branch="nonexistent-branch",
                )

    def test_copy_files_directory_skipped_with_warning(self, tmp_path: Path) -> None:
        """A directory listed in copy_files logs a warning and is skipped (not copied)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        some_dir = repo / "subdir"
        some_dir.mkdir()
        wt = tmp_path / "wt"
        wt.mkdir()
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        copy2_calls: list[str] = []

        def _mock_copy2(src: object, dst: object) -> None:
            copy2_calls.append(str(src))

        with patch.object(git_lock, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            with patch("subprocess.run", return_value=_ok()):
                with patch("shutil.copytree"):
                    with patch("shutil.rmtree"):
                        with patch("shutil.copy2", side_effect=_mock_copy2):
                            setup_worktree(
                                repo_path=repo,
                                worktree_path=wt,
                                branch_name="branch",
                                copy_files=["subdir"],
                                logger=logger,
                                git_lock=git_lock,
                            )

        assert not any("subdir" in c for c in copy2_calls), (
            "Directory in copy_files should not be copied via copy2"
        )
        logger.warning.assert_called()
        warning_msg = logger.warning.call_args[0][0]
        assert "subdir" in warning_msg or "directory" in warning_msg.lower()


# ---------------------------------------------------------------------------
# worktree_utils.cleanup_worktree
# ---------------------------------------------------------------------------


class TestCleanupWorktree:
    """Unit tests for worktree_utils.cleanup_worktree()."""

    def test_no_op_when_path_missing(self, tmp_path: Path) -> None:
        """cleanup_worktree() returns immediately if the path doesn't exist."""
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        with patch.object(git_lock, "run") as mock_run:
            cleanup_worktree(
                worktree_path=tmp_path / "nonexistent",
                repo_path=tmp_path,
                logger=logger,
                git_lock=git_lock,
            )

        mock_run.assert_not_called()

    def test_calls_git_worktree_remove(self, tmp_path: Path) -> None:
        """cleanup_worktree() calls 'git worktree remove --force'."""
        wt = tmp_path / "wt"
        wt.mkdir()
        repo = tmp_path / "repo"
        repo.mkdir()
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        remove_calls: list[list[str]] = []

        def _mock_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if "remove" in args:
                remove_calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(git_lock, "run", side_effect=_mock_run):
            with patch("subprocess.run", return_value=_ok()):
                cleanup_worktree(
                    worktree_path=wt,
                    repo_path=repo,
                    logger=logger,
                    git_lock=git_lock,
                    delete_branch=False,
                )

        assert remove_calls

    def test_deletes_branch_when_delete_branch_true(self, tmp_path: Path) -> None:
        """cleanup_worktree() deletes the branch when delete_branch=True."""
        wt = tmp_path / "wt"
        wt.mkdir()
        repo = tmp_path / "repo"
        repo.mkdir()
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        branch_cmds: list[list[str]] = []

        def _mock_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["branch", "-D"]:
                branch_cmds.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        # subprocess.run returns branch name for rev-parse
        with patch.object(git_lock, "run", side_effect=_mock_run):
            with patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "20260101-000000-my-loop\n", ""),
            ):
                cleanup_worktree(
                    worktree_path=wt,
                    repo_path=repo,
                    logger=logger,
                    git_lock=git_lock,
                    delete_branch=True,
                )

        assert branch_cmds, "Expected 'git branch -D' call"
        assert "20260101-000000-my-loop" in branch_cmds[0]

    def test_skips_branch_delete_when_delete_branch_false(self, tmp_path: Path) -> None:
        """cleanup_worktree() skips branch deletion when delete_branch=False."""
        wt = tmp_path / "wt"
        wt.mkdir()
        repo = tmp_path / "repo"
        repo.mkdir()
        logger = MagicMock()
        git_lock = _make_git_lock(logger)

        branch_cmds: list[list[str]] = []

        def _mock_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["branch", "-D"]:
                branch_cmds.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(git_lock, "run", side_effect=_mock_run):
            with patch("subprocess.run", return_value=_ok()):
                cleanup_worktree(
                    worktree_path=wt,
                    repo_path=repo,
                    logger=logger,
                    git_lock=git_lock,
                    delete_branch=False,
                )

        assert not branch_cmds

    def test_unlock_called_before_remove(self, tmp_path: Path) -> None:
        """cleanup_worktree() calls 'git worktree unlock' before 'git worktree remove'."""
        wt = tmp_path / "wt"
        wt.mkdir()
        repo = tmp_path / "repo"
        repo.mkdir()
        git_lock = _make_git_lock()
        call_order: list[str] = []

        def _mock_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["worktree", "unlock"]:
                call_order.append("unlock")
            elif args[:2] == ["worktree", "remove"]:
                call_order.append("remove")
            return _ok()

        with patch.object(git_lock, "run", side_effect=_mock_run):
            with patch("subprocess.run", return_value=_ok()):
                cleanup_worktree(
                    worktree_path=wt,
                    repo_path=repo,
                    logger=MagicMock(),
                    git_lock=git_lock,
                    delete_branch=False,
                )

        assert "unlock" in call_order and "remove" in call_order
        assert call_order.index("unlock") < call_order.index("remove")

    def test_remove_proceeds_when_unlock_fails(self, tmp_path: Path) -> None:
        """cleanup_worktree() still calls 'git worktree remove' when unlock returns non-zero."""
        wt = tmp_path / "wt"
        wt.mkdir()
        repo = tmp_path / "repo"
        repo.mkdir()
        git_lock = _make_git_lock()
        remove_calls: list[list[str]] = []

        def _mock_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["worktree", "unlock"]:
                return subprocess.CompletedProcess(args, 1, "", "fatal: worktree is not locked")
            if "remove" in args:
                remove_calls.append(args)
            return _ok()

        with patch.object(git_lock, "run", side_effect=_mock_run):
            with patch("subprocess.run", return_value=_ok()):
                cleanup_worktree(
                    worktree_path=wt,
                    repo_path=repo,
                    logger=MagicMock(),
                    git_lock=git_lock,
                    delete_branch=False,
                )

        assert remove_calls, "'git worktree remove' must run even when unlock returns non-zero"


# ---------------------------------------------------------------------------
# WorkerPool refactor: _cleanup_worktree still preserves parallel/ guard
# ---------------------------------------------------------------------------


class TestWorkerPoolCleanupBranchGuard:
    """Verify WorkerPool._cleanup_worktree deletes ll-managed branches (parallel/ and loop-style)."""

    def _make_pool(self, tmp_path: Path) -> WorkerPool:
        from little_loops.config import BRConfig
        from little_loops.parallel.types import ParallelConfig
        from little_loops.parallel.worker_pool import WorkerPool

        # Minimal repo structure required by BRConfig
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (ll_dir / "ll-config.json").write_text("{}")

        config = ParallelConfig(
            max_workers=1,
            p0_sequential=False,
            worktree_base=tmp_path / ".worktrees",
            state_file=tmp_path / ".parallel-state.json",
            timeout_per_issue=60,
            max_merge_retries=0,
            stream_subprocess_output=False,
            command_prefix="/ll:",
            ready_command="ready-issue {{issue_id}}",
            manage_command="manage-issue {{issue_type}} {{action}} {{issue_id}}",
        )
        br_config = BRConfig(tmp_path)
        logger = MagicMock()
        return WorkerPool(
            parallel_config=config,
            br_config=br_config,
            logger=logger,
        )

    def test_parallel_branch_is_deleted(self, tmp_path: Path) -> None:
        """_cleanup_worktree deletes branches with parallel/ prefix (legacy)."""
        pool = self._make_pool(tmp_path)
        wt = tmp_path / "wt"
        wt.mkdir()

        branch_deletes: list[str] = []

        def _mock_git(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["branch", "-D"]:
                branch_deletes.append(args[2])
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(pool._git_lock, "run", side_effect=_mock_git):
            with patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "parallel/bug-001\n", ""),
            ):
                pool._cleanup_worktree(wt)

        assert "parallel/bug-001" in branch_deletes

    def test_loop_branch_is_deleted(self, tmp_path: Path) -> None:
        """_cleanup_worktree deletes loop-style YYYYMMDD-HHMMSS-* branches (BUG-2324)."""
        pool = self._make_pool(tmp_path)
        wt = tmp_path / "wt"
        wt.mkdir()

        branch_deletes: list[str] = []

        def _mock_git(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["branch", "-D"]:
                branch_deletes.append(args[2])
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(pool._git_lock, "run", side_effect=_mock_git):
            with patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "20260101-000000-my-loop\n", ""),
            ):
                pool._cleanup_worktree(wt)

        assert "20260101-000000-my-loop" in branch_deletes, (
            "Loop-style YYYYMMDD-HHMMSS-* branches must be deleted by WorkerPool"
        )

    def test_main_branch_not_deleted(self, tmp_path: Path) -> None:
        """_cleanup_worktree never deletes main/master/HEAD (safe guard)."""
        pool = self._make_pool(tmp_path)
        wt = tmp_path / "wt"
        wt.mkdir()

        branch_deletes: list[str] = []

        def _mock_git(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["branch", "-D"]:
                branch_deletes.append(args[2])
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(pool._git_lock, "run", side_effect=_mock_git):
            with patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "main\n", ""),
            ):
                pool._cleanup_worktree(wt)

        assert not branch_deletes, "main/master/HEAD must never be deleted by WorkerPool"


# ---------------------------------------------------------------------------
# Branch name generation (used in cmd_run)
# ---------------------------------------------------------------------------


class TestBranchNameGeneration:
    """Verify branch name format for loop worktrees."""

    def test_sanitizes_loop_name(self) -> None:
        """Non-alphanumeric/dash characters in loop name are replaced with '-'."""
        import re

        loop_name = "fix types & stuff"
        safe_name = re.sub(r"[^a-zA-Z0-9-]", "-", loop_name)
        assert safe_name == "fix-types---stuff"

    def test_branch_name_format(self) -> None:
        """Branch name starts with a timestamp segment."""
        import re
        from datetime import datetime

        loop_name = "my-loop"
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_name = re.sub(r"[^a-zA-Z0-9-]", "-", loop_name)
        branch = f"{ts}-{safe_name}"

        assert re.match(r"^\d{8}-\d{6}-my-loop$", branch)


class TestIsLLWorktree:
    """Verify _is_ll_worktree() predicate matches both naming patterns."""

    def test_worker_prefix_matches(self) -> None:
        from little_loops.worktree_utils import _is_ll_worktree

        assert _is_ll_worktree("worker-bug-001") is True

    def test_timestamp_prefix_matches(self) -> None:
        from little_loops.worktree_utils import _is_ll_worktree

        assert _is_ll_worktree("20260101-000000-my-loop") is True

    def test_other_directory_does_not_match(self) -> None:
        from little_loops.worktree_utils import _is_ll_worktree

        assert _is_ll_worktree("other-directory") is False


class TestCmdRunWorktree:
    """Integration tests for the cmd_run(worktree=True) code path (ENH-1254)."""

    def _make_args(self, **kwargs: object) -> argparse.Namespace:
        defaults = {
            "input": None,
            "context": [],
            "max_steps": None,
            "max_iterations": None,
            "delay": None,
            "no_llm": False,
            "llm_model": None,
            "dry_run": False,
            "background": False,
            "foreground_internal": False,
            "quiet": False,
            "verbose": False,
            "follow": False,
            "show_diagrams": None,
            "diagram_edge_labels": None,
            "diagram_state_detail": None,
            "diagram_scope": None,
            "clear": False,
            "queue": False,
            "handoff_threshold": None,
            "worktree": True,
            "program_md": None,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def _make_loop(self, tmp_path: Path) -> Path:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test-loop.yaml").write_text(
            "name: test-loop\ninitial: done\nstates:\n  done:\n    terminal: true\n"
        )
        return loops_dir

    def test_worktree_atexit_registration(self, tmp_path: Path) -> None:
        """cmd_run(worktree=True) registers atexit cleanup handlers including _cleanup_worktree_on_exit."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = self._make_loop(tmp_path)
        args = self._make_args()
        logger = Logger(use_color=False)

        registered: list = []
        with (
            patch("little_loops.config.BRConfig") as mock_cfg,
            patch("little_loops.worktree_utils.setup_worktree", return_value=None),
            patch("little_loops.cli.loop.run.os.chdir"),
            patch("little_loops.cli.loop.run.atexit.register", side_effect=registered.append),
            patch("little_loops.cli.loop.run.run_foreground", return_value=0),
            patch("little_loops.transport.wire_transports"),
        ):
            mock_cfg.return_value.get_worktree_base.return_value = tmp_path / ".worktrees"
            mock_cfg.return_value.parallel.worktree_copy_files = []
            mock_cfg.return_value.cli.colors.fsm_edge_labels.to_dict.return_value = {}
            mock_cfg.return_value.cli.colors.fsm_active_state = None
            mock_cfg.return_value.loops.glyphs.to_dict.return_value = {}
            mock_cfg.return_value.commands.rate_limits.circuit_breaker_enabled = False
            mock_cfg.return_value.design_tokens.enabled = False
            mock_cfg.return_value.extensions = []
            mock_cfg.return_value.events = MagicMock(transports=[])

            result = cmd_run("test-loop", args, loops_dir, logger)

        assert result == 0
        # At least _cleanup_pid (line 145) and _cleanup_worktree_on_exit (line 240)
        assert len(registered) >= 2

    def test_worktree_path_name_format(self, tmp_path: Path) -> None:
        """cmd_run(worktree=True) creates a worktree path with timestamp-loop-name format."""
        import re

        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = self._make_loop(tmp_path)
        args = self._make_args()
        logger = Logger(use_color=False)

        chdir_calls: list = []
        with (
            patch("little_loops.config.BRConfig") as mock_cfg,
            patch("little_loops.worktree_utils.setup_worktree", return_value=None),
            patch("little_loops.cli.loop.run.os.chdir", side_effect=chdir_calls.append),
            patch("little_loops.cli.loop.run.atexit.register"),
            patch("little_loops.cli.loop.run.run_foreground", return_value=0),
            patch("little_loops.transport.wire_transports"),
        ):
            mock_cfg.return_value.get_worktree_base.return_value = tmp_path / ".worktrees"
            mock_cfg.return_value.parallel.worktree_copy_files = []
            mock_cfg.return_value.cli.colors.fsm_edge_labels.to_dict.return_value = {}
            mock_cfg.return_value.cli.colors.fsm_active_state = None
            mock_cfg.return_value.loops.glyphs.to_dict.return_value = {}
            mock_cfg.return_value.commands.rate_limits.circuit_breaker_enabled = False
            mock_cfg.return_value.design_tokens.enabled = False
            mock_cfg.return_value.extensions = []
            mock_cfg.return_value.events = MagicMock(transports=[])

            cmd_run("test-loop", args, loops_dir, logger)

        assert chdir_calls, "os.chdir must be called for worktree=True"
        worktree_path = Path(chdir_calls[-1])
        assert re.match(r"^\d{8}-\d{6}-test-loop$", worktree_path.name), (
            f"Worktree path name {worktree_path.name!r} must match "
            r"^\d{8}-\d{6}-test-loop$"
        )

    def test_worktree_and_background_rejected(self, tmp_path: Path) -> None:
        """cmd_run rejects --worktree + --background with SystemExit (BUG-1414)."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = self._make_loop(tmp_path)
        args = self._make_args(background=True, worktree=True)
        logger = Logger(use_color=False)

        with patch("little_loops.config.BRConfig") as mock_cfg:
            mock_cfg.return_value.cli.colors.fsm_edge_labels.to_dict.return_value = {}
            mock_cfg.return_value.cli.colors.fsm_active_state = None
            mock_cfg.return_value.loops.glyphs.to_dict.return_value = {}
            mock_cfg.return_value.design_tokens.enabled = False

            with pytest.raises(SystemExit) as exc_info:
                cmd_run("test-loop", args, loops_dir, logger)

        assert "--worktree and --background cannot be combined" in str(exc_info.value)


# ---------------------------------------------------------------------------
# BUG-2386: absolute loops_dir regression
# ---------------------------------------------------------------------------


def _mock_br_config(mock_cfg: MagicMock, tmp_path: Path) -> None:
    """Configure a minimal BRConfig mock for worktree cmd_run tests."""
    mock_cfg.return_value.get_worktree_base.return_value = tmp_path / ".worktrees"
    mock_cfg.return_value.parallel.worktree_copy_files = []
    mock_cfg.return_value.cli.colors.fsm_edge_labels.to_dict.return_value = {}
    mock_cfg.return_value.cli.colors.fsm_active_state = None
    mock_cfg.return_value.loops.glyphs.to_dict.return_value = {}
    mock_cfg.return_value.loops.run_defaults.include = None
    mock_cfg.return_value.loops.queue_wait_timeout_seconds = 60
    mock_cfg.return_value.commands.rate_limits.circuit_breaker_enabled = False
    mock_cfg.return_value.design_tokens.enabled = False
    mock_cfg.return_value.extensions = []
    mock_cfg.return_value.events = MagicMock(transports=[])


class TestCmdRunWorktreeAbsoluteLoopsDir:
    """Regression (BUG-2386 Step 1): cmd_run must resolve loops_dir to absolute
    before any os.chdir so tracking files always land in the main repo."""

    def _make_args(self, **kwargs: object) -> argparse.Namespace:
        defaults = {
            "input": None,
            "context": [],
            "max_steps": None,
            "max_iterations": None,
            "delay": None,
            "no_llm": False,
            "llm_model": None,
            "dry_run": False,
            "background": False,
            "foreground_internal": False,
            "quiet": False,
            "verbose": False,
            "follow": False,
            "show_diagrams": None,
            "diagram_edge_labels": None,
            "diagram_state_detail": None,
            "diagram_scope": None,
            "clear": False,
            "queue": False,
            "handoff_threshold": None,
            "worktree": True,
            "program_md": None,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def _make_loop(self, tmp_path: Path) -> Path:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test-loop.yaml").write_text(
            "name: test-loop\ninitial: done\nstates:\n  done:\n    terminal: true\n"
        )
        return loops_dir

    def test_loops_dir_resolved_to_absolute(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PersistentExecutor must receive an absolute loops_dir even when a
        relative Path('.loops') is passed to cmd_run."""
        import little_loops.fsm.persistence as _fsmpers
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        # Set cwd to tmp_path so Path(".loops") resolves there
        monkeypatch.chdir(tmp_path)
        self._make_loop(tmp_path)  # creates .loops/test-loop.yaml under tmp_path
        expected_abs = tmp_path / ".loops"

        captured_loops_dirs: list[Path] = []
        _OrigPE = _fsmpers.PersistentExecutor

        class _CapturingPE(_OrigPE):  # type: ignore[misc]
            def __init__(self, fsm, loops_dir=None, **kw):  # type: ignore[override]
                captured_loops_dirs.append(Path(loops_dir) if loops_dir is not None else None)
                super().__init__(fsm, loops_dir=loops_dir, **kw)

        args = self._make_args()
        logger = Logger(use_color=False)

        with (
            patch("little_loops.config.BRConfig") as mock_cfg,
            patch("little_loops.worktree_utils.setup_worktree"),
            patch("little_loops.cli.loop.run.os.chdir"),
            patch("little_loops.cli.loop.run.atexit.register"),
            patch("little_loops.cli.loop.run.run_foreground", return_value=0),
            patch("little_loops.transport.wire_transports"),
            patch("little_loops.fsm.persistence.PersistentExecutor", _CapturingPE),
            patch("little_loops.fsm.persistence._reconcile_stale_runs"),
            patch("little_loops.cli.loop.run.subprocess.run",
                  return_value=subprocess.CompletedProcess([], 0, "abc123\n", "")),
        ):
            _mock_br_config(mock_cfg, tmp_path)

            # Pass a RELATIVE loops_dir — cmd_run must resolve it internally
            cmd_run("test-loop", args, Path(".loops"), logger)

        assert captured_loops_dirs, "PersistentExecutor was never instantiated"
        actual = captured_loops_dirs[0]
        assert actual.is_absolute(), (
            f"PersistentExecutor must receive an absolute loops_dir; got {actual!r}"
        )
        assert actual == expected_abs, (
            f"Expected {expected_abs}, got {actual}"
        )


# ---------------------------------------------------------------------------
# BUG-2386: fail-loud on pending worktree work
# ---------------------------------------------------------------------------


class TestCleanupWorktreeFailLoud:
    """Regression (BUG-2386 Step 3): _cleanup_worktree_on_exit must retain the
    branch when the worktree has uncommitted changes or commits ahead of base."""

    def _make_args(self, **kwargs: object) -> argparse.Namespace:
        defaults = {
            "input": None,
            "context": [],
            "max_steps": None,
            "max_iterations": None,
            "delay": None,
            "no_llm": False,
            "llm_model": None,
            "dry_run": False,
            "background": False,
            "foreground_internal": False,
            "quiet": False,
            "verbose": False,
            "follow": False,
            "show_diagrams": None,
            "diagram_state_detail": None,
            "diagram_edge_labels": None,
            "diagram_scope": None,
            "clear": False,
            "queue": False,
            "handoff_threshold": None,
            "worktree": True,
            "program_md": None,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def _make_loop(self, tmp_path: Path) -> Path:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test-loop.yaml").write_text(
            "name: test-loop\ninitial: done\nstates:\n  done:\n    terminal: true\n"
        )
        return loops_dir

    def _run_and_capture_cleanup(
        self,
        tmp_path: Path,
        subprocess_side_effect: Callable[..., subprocess.CompletedProcess[str]],
    ) -> tuple[list[dict], MagicMock]:
        """Run cmd_run, invoke the registered _cleanup_worktree_on_exit closure,
        and return (cleanup_worktree call kwargs list, logger mock)."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = self._make_loop(tmp_path)
        args = self._make_args()
        logger = Logger(use_color=False)
        registered: list = []
        cleanup_calls: list[dict] = []
        chdir_calls: list = []

        with (
            patch("little_loops.config.BRConfig") as mock_cfg,
            patch("little_loops.worktree_utils.setup_worktree"),
            patch("little_loops.worktree_utils.cleanup_worktree",
                  side_effect=lambda **kw: cleanup_calls.append(kw)),
            patch("little_loops.cli.loop.run.os.chdir",
                  side_effect=chdir_calls.append),
            patch("little_loops.cli.loop.run.atexit.register",
                  side_effect=registered.append),
            patch("little_loops.cli.loop.run.run_foreground", return_value=0),
            patch("little_loops.transport.wire_transports"),
            patch("little_loops.fsm.persistence._reconcile_stale_runs"),
            patch("little_loops.cli.loop.run.subprocess.run",
                  side_effect=subprocess_side_effect),
        ):
            _mock_br_config(mock_cfg, tmp_path)

            mock_pe = MagicMock()
            mock_pe.event_bus = MagicMock()
            mock_pe.close_transports = MagicMock()

            with patch("little_loops.fsm.persistence.PersistentExecutor",
                       return_value=mock_pe):
                cmd_run("test-loop", args, loops_dir, logger)

            # Create the worktree directory so .exists() → True during cleanup
            if chdir_calls:
                Path(chdir_calls[-1]).mkdir(parents=True, exist_ok=True)

            # Invoke _cleanup_worktree_on_exit while patches are still active
            cleanup_fn = next(
                fn for fn in registered if fn.__name__ == "_cleanup_worktree_on_exit"
            )
            cleanup_fn()

        return cleanup_calls, logger

    def test_branch_retained_when_uncommitted_changes(self, tmp_path: Path) -> None:
        """When git status --porcelain returns output, delete_branch must be False."""

        def _subprocess(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if list(cmd)[1:3] == ["rev-parse", "HEAD"]:  # base commit capture
                return subprocess.CompletedProcess(cmd, 0, "deadbeef\n", "")
            if list(cmd)[1:3] == ["status", "--porcelain"]:  # dirty!
                return subprocess.CompletedProcess(cmd, 0, " M modified.py\n", "")
            if list(cmd)[1:2] == ["rev-list"]:
                return subprocess.CompletedProcess(cmd, 0, "0\n", "")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        calls, _ = self._run_and_capture_cleanup(tmp_path, _subprocess)

        assert calls, "cleanup_worktree must have been called"
        assert calls[0].get("delete_branch") is False, (
            "Branch must be retained (delete_branch=False) when uncommitted changes exist"
        )

    def test_branch_retained_when_commits_ahead(self, tmp_path: Path) -> None:
        """When the worktree branch has commits ahead of base, delete_branch must be False."""

        def _subprocess(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if list(cmd)[1:3] == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(cmd, 0, "deadbeef\n", "")
            if list(cmd)[1:3] == ["status", "--porcelain"]:  # clean working tree
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if list(cmd)[1:2] == ["rev-list"]:  # 3 commits ahead!
                return subprocess.CompletedProcess(cmd, 0, "3\n", "")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        calls, _ = self._run_and_capture_cleanup(tmp_path, _subprocess)

        assert calls, "cleanup_worktree must have been called"
        assert calls[0].get("delete_branch") is False, (
            "Branch must be retained (delete_branch=False) when commits exist ahead of base"
        )

    def test_branch_deleted_when_clean(self, tmp_path: Path) -> None:
        """When working tree is clean and no commits ahead, delete_branch must be True."""

        def _subprocess(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if list(cmd)[1:3] == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(cmd, 0, "deadbeef\n", "")
            if list(cmd)[1:3] == ["status", "--porcelain"]:  # clean
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if list(cmd)[1:2] == ["rev-list"]:  # 0 commits ahead
                return subprocess.CompletedProcess(cmd, 0, "0\n", "")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        calls, _ = self._run_and_capture_cleanup(tmp_path, _subprocess)

        assert calls, "cleanup_worktree must have been called"
        assert calls[0].get("delete_branch") is True, (
            "Branch must be deleted (delete_branch=True) when worktree is clean"
        )

    def test_warning_logged_with_branch_name_on_pending_work(self, tmp_path: Path) -> None:
        """A warning mentioning the branch name must be logged when pending work is detected."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = self._make_loop(tmp_path)
        args = self._make_args()
        logger = MagicMock(spec=Logger)
        registered: list = []
        chdir_calls: list = []

        def _subprocess(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            if list(cmd)[1:3] == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(cmd, 0, "deadbeef\n", "")
            if list(cmd)[1:3] == ["status", "--porcelain"]:
                return subprocess.CompletedProcess(cmd, 0, " M modified.py\n", "")
            if list(cmd)[1:2] == ["rev-list"]:
                return subprocess.CompletedProcess(cmd, 0, "0\n", "")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with (
            patch("little_loops.config.BRConfig") as mock_cfg,
            patch("little_loops.worktree_utils.setup_worktree"),
            patch("little_loops.worktree_utils.cleanup_worktree"),
            patch("little_loops.cli.loop.run.os.chdir",
                  side_effect=chdir_calls.append),
            patch("little_loops.cli.loop.run.atexit.register",
                  side_effect=registered.append),
            patch("little_loops.cli.loop.run.run_foreground", return_value=0),
            patch("little_loops.transport.wire_transports"),
            patch("little_loops.fsm.persistence._reconcile_stale_runs"),
            patch("little_loops.cli.loop.run.subprocess.run",
                  side_effect=_subprocess),
        ):
            _mock_br_config(mock_cfg, tmp_path)
            mock_pe = MagicMock()
            mock_pe.event_bus = MagicMock()
            mock_pe.close_transports = MagicMock()
            with patch("little_loops.fsm.persistence.PersistentExecutor",
                       return_value=mock_pe):
                cmd_run("test-loop", args, loops_dir, logger)

            if chdir_calls:
                Path(chdir_calls[-1]).mkdir(parents=True, exist_ok=True)

            cleanup_fn = next(
                fn for fn in registered if fn.__name__ == "_cleanup_worktree_on_exit"
            )
            cleanup_fn()

        # A warning must mention the branch name
        warning_calls = [str(c) for c in logger.warning.call_args_list]
        branch_mentioned = any("test-loop" in w or "20" in w for w in warning_calls)
        assert branch_mentioned, (
            f"logger.warning must be called with branch name info; got: {warning_calls}"
        )
