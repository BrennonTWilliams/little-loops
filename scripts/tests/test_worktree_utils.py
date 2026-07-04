"""Tests for little_loops.worktree_utils.detect_default_branch (BUG-2323).

Uses real ``git init`` repositories (modeled on the ``temp_git_repo`` fixture in
test_merge_coordinator.py) so that origin/HEAD and detached-HEAD behavior is
exercised against actual git, not mocks.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from little_loops.worktree_utils import detect_default_branch


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in cwd, raising on failure."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _init_repo(path: Path, initial_branch: str = "main") -> Path:
    """Initialize a git repo with one commit on the given initial branch."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--initial-branch", initial_branch)
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("test\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "initial commit")
    return path


class TestDetectDefaultBranch:
    """detect_default_branch() resolution order: origin/HEAD -> current branch -> main."""

    def test_origin_head_wins_over_current_branch(self, tmp_path: Path) -> None:
        """origin/HEAD, when present, is preferred and the origin/ prefix is stripped."""
        repo = _init_repo(tmp_path / "repo", initial_branch="master")
        _git(repo, "update-ref", "refs/remotes/origin/develop", "HEAD")
        _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop")

        assert detect_default_branch(repo) == "develop"

    def test_master_default_repo_yields_master(self, tmp_path: Path) -> None:
        """Regression: a master-default repo yields 'master', not the hardcoded 'main'."""
        repo = _init_repo(tmp_path / "repo", initial_branch="master")

        assert detect_default_branch(repo) == "master"

    def test_current_branch_used_when_no_origin_head(self, tmp_path: Path) -> None:
        """Without origin/HEAD, the checked-out branch name is used."""
        repo = _init_repo(tmp_path / "repo", initial_branch="develop")

        assert detect_default_branch(repo) == "develop"

    def test_detached_head_never_returns_literal_head(self, tmp_path: Path) -> None:
        """On detached HEAD (rev-parse yields 'HEAD') the helper falls back to 'main'."""
        repo = _init_repo(tmp_path / "repo", initial_branch="feature-x")
        _git(repo, "checkout", "--detach")

        result = detect_default_branch(repo)
        assert result != "HEAD"
        assert result == "main"

    def test_detached_head_with_origin_head_uses_origin(self, tmp_path: Path) -> None:
        """Detached HEAD still resolves correctly when origin/HEAD exists."""
        repo = _init_repo(tmp_path / "repo", initial_branch="master")
        _git(repo, "update-ref", "refs/remotes/origin/master", "HEAD")
        _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/master")
        _git(repo, "checkout", "--detach")

        assert detect_default_branch(repo) == "master"

    def test_non_repo_returns_main_last_resort(self, tmp_path: Path) -> None:
        """A directory that is not a git repo falls back to 'main'."""
        not_a_repo = tmp_path / "empty"
        not_a_repo.mkdir()

        assert detect_default_branch(not_a_repo) == "main"


class _FakeGitLock:
    """Minimal GitLock stand-in that records calls and returns canned results."""

    def __init__(self, symbolic_ref_stdout: str = "origin/trunk\n") -> None:
        self.calls: list[list[str]] = []
        self._symbolic_ref_stdout = symbolic_ref_stdout

    def run(
        self,
        args: list[str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        if args[0] == "symbolic-ref":
            return subprocess.CompletedProcess(args, 0, self._symbolic_ref_stdout, "")
        return subprocess.CompletedProcess(args, 0, "main\n", "")


class TestDetectDefaultBranchGitLock:
    """With git_lock provided, commands go through the lock (args without 'git' prefix)."""

    def test_git_lock_path_used_and_prefix_stripped(self, tmp_path: Path) -> None:
        """git_lock.run receives git-less args and the origin/ prefix is stripped."""
        lock = _FakeGitLock()

        result = detect_default_branch(tmp_path, git_lock=lock)

        assert result == "trunk"
        assert lock.calls == [["symbolic-ref", "--short", "refs/remotes/origin/HEAD"]]
