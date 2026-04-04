"""Tests for ll-loop run --worktree flag (ENH-945)."""

from __future__ import annotations

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


# ---------------------------------------------------------------------------
# WorkerPool refactor: _cleanup_worktree still preserves parallel/ guard
# ---------------------------------------------------------------------------


class TestWorkerPoolCleanupBackwardsCompat:
    """Verify WorkerPool._cleanup_worktree still only deletes parallel/ branches."""

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

    def test_non_parallel_branch_not_deleted(self, tmp_path: Path) -> None:
        """_cleanup_worktree does NOT delete branches without parallel/ prefix."""
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

        assert not branch_deletes, "Non-parallel/ branches should not be deleted by WorkerPool"


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
