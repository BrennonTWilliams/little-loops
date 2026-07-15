"""Tests for little_loops.worktree_utils.detect_default_branch (BUG-2323).

Uses real ``git init`` repositories (modeled on the ``temp_git_repo`` fixture in
test_merge_coordinator.py) so that origin/HEAD and detached-HEAD behavior is
exercised against actual git, not mocks.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.logger import Logger
from little_loops.parallel.git_lock import GitLock
from little_loops.worktree_utils import (
    cleanup_worktree,
    detect_default_branch,
    format_verify_detail,
    merge_epic_branch_to_base,
    open_pr_for_epic_branch,
    setup_worktree,
    verify_epic_branch_before_merge,
)


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


class TestSetupWorktreeCheckoutExisting:
    """setup_worktree(checkout_existing=True) checks out an existing branch (ENH-2603)."""

    def test_checks_out_existing_branch_without_creating_new_one(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "branch", "epic/existing")
        worktree_path = tmp_path / "wt"
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        setup_worktree(
            repo_path=repo,
            worktree_path=worktree_path,
            branch_name="epic/existing",
            copy_files=[],
            logger=logger,
            git_lock=git_lock,
            checkout_existing=True,
        )

        current = _git(worktree_path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        assert current == "epic/existing"

    def test_base_branch_and_checkout_existing_are_mutually_exclusive(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "branch", "epic/existing")
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        with pytest.raises(ValueError, match="mutually exclusive"):
            setup_worktree(
                repo_path=repo,
                worktree_path=tmp_path / "wt",
                branch_name="epic/existing",
                copy_files=[],
                logger=logger,
                git_lock=git_lock,
                base_branch="main",
                checkout_existing=True,
            )

    def test_cleanup_after_checkout_existing_does_not_delete_the_branch(
        self, tmp_path: Path
    ) -> None:
        """The checked-out branch is not disposable — cleanup must not delete it."""
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "branch", "epic/existing")
        worktree_path = tmp_path / "wt"
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        setup_worktree(
            repo_path=repo,
            worktree_path=worktree_path,
            branch_name="epic/existing",
            copy_files=[],
            logger=logger,
            git_lock=git_lock,
            checkout_existing=True,
        )
        cleanup_worktree(worktree_path, repo, logger, git_lock, delete_branch=False)

        branches = _git(repo, "branch", "--list", "epic/existing").stdout
        assert "epic/existing" in branches
        assert not worktree_path.exists()


class TestMergeEpicBranchToBase:
    """merge_epic_branch_to_base() (BUG-2614: extracted from
    ParallelOrchestrator._merge_epic_branch_to_base) merges an EPIC branch
    into base_branch and deletes it, assuming repo_path is already checked
    out on base_branch."""

    def _repo_with_epic_branch(self, tmp_path: Path) -> Path:
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "checkout", "-b", "epic/epic-1-integration")
        (repo / "feature.txt").write_text("epic work\n")
        _git(repo, "add", "feature.txt")
        _git(repo, "commit", "-m", "epic work")
        _git(repo, "checkout", "main")
        return repo

    def test_merges_and_deletes_branch_on_success(self, tmp_path: Path) -> None:
        repo = self._repo_with_epic_branch(tmp_path)
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        ok = merge_epic_branch_to_base(
            "EPIC-1",
            "epic/epic-1-integration",
            base_branch="main",
            repo_path=repo,
            logger=logger,
            git_lock=git_lock,
        )

        assert ok is True
        assert (repo / "feature.txt").exists()
        branches = _git(repo, "branch", "--list", "epic/epic-1-integration").stdout
        assert "epic/epic-1-integration" not in branches
        log = _git(repo, "log", "--oneline").stdout
        assert "epic work" in log

    def test_conflicting_merge_returns_false_and_aborts(self, tmp_path: Path) -> None:
        """A merge conflict must not leave the repo mid-merge or delete the branch."""
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "checkout", "-b", "epic/epic-1-integration")
        (repo / "README.md").write_text("epic version\n")
        _git(repo, "commit", "-am", "epic edits README")
        _git(repo, "checkout", "main")
        (repo / "README.md").write_text("main version\n")
        _git(repo, "commit", "-am", "main edits README")
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        ok = merge_epic_branch_to_base(
            "EPIC-1",
            "epic/epic-1-integration",
            base_branch="main",
            repo_path=repo,
            logger=logger,
            git_lock=git_lock,
        )

        assert ok is False
        branches = _git(repo, "branch", "--list", "epic/epic-1-integration").stdout
        assert "epic/epic-1-integration" in branches
        status = _git(repo, "status", "--porcelain").stdout
        assert status == ""  # merge --abort left a clean tree, not a conflicted one

    def test_conflict_with_run_dir_persists_diagnostic_artifacts(self, tmp_path: Path) -> None:
        """ENH-2643: on merge failure, persist merge-detail/returncode/conflicts under run_dir."""
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "checkout", "-b", "epic/epic-1-integration")
        (repo / "README.md").write_text("epic version\n")
        _git(repo, "commit", "-am", "epic edits README")
        _git(repo, "checkout", "main")
        (repo / "README.md").write_text("main version\n")
        _git(repo, "commit", "-am", "main edits README")
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        ok = merge_epic_branch_to_base(
            "EPIC-1",
            "epic/epic-1-integration",
            base_branch="main",
            repo_path=repo,
            logger=logger,
            git_lock=git_lock,
            run_dir=run_dir,
        )

        assert ok is False
        assert (run_dir / "merge-returncode.txt").exists()
        assert (run_dir / "merge-detail.txt").exists()
        conflicts = run_dir / "merge-conflicts.txt"
        assert conflicts.exists()
        assert "README.md" in conflicts.read_text()
        # returncode is the non-zero `git merge` exit
        assert run_dir / "merge-returncode.txt"
        assert (run_dir / "merge-returncode.txt").read_text().strip() != "0"
        # tree left clean after --abort
        assert _git(repo, "status", "--porcelain").stdout == ""

    def test_conflict_without_run_dir_writes_nothing(self, tmp_path: Path) -> None:
        """ENH-2643: omitting run_dir (the orchestrator caller) persists no artifact."""
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "checkout", "-b", "epic/epic-1-integration")
        (repo / "README.md").write_text("epic version\n")
        _git(repo, "commit", "-am", "epic edits README")
        _git(repo, "checkout", "main")
        (repo / "README.md").write_text("main version\n")
        _git(repo, "commit", "-am", "main edits README")
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        ok = merge_epic_branch_to_base(
            "EPIC-1",
            "epic/epic-1-integration",
            base_branch="main",
            repo_path=repo,
            logger=logger,
            git_lock=git_lock,
        )

        assert ok is False
        # no run_dir → nothing written anywhere under the repo
        assert not (repo / "merge-detail.txt").exists()
        assert not (repo / "merge-returncode.txt").exists()

    def test_success_with_run_dir_writes_no_artifacts(self, tmp_path: Path) -> None:
        """ENH-2643: a clean merge leaves the diagnostic artifacts absent."""
        repo = self._repo_with_epic_branch(tmp_path)
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        ok = merge_epic_branch_to_base(
            "EPIC-1",
            "epic/epic-1-integration",
            base_branch="main",
            repo_path=repo,
            logger=logger,
            git_lock=git_lock,
            run_dir=run_dir,
        )

        assert ok is True
        assert not (run_dir / "merge-detail.txt").exists()
        assert not (run_dir / "merge-returncode.txt").exists()
        assert not (run_dir / "merge-conflicts.txt").exists()


class TestVerifyEpicBranchBeforeMerge:
    """verify_epic_branch_before_merge() (BUG-2614: extracted from
    ParallelOrchestrator._verify_epic_branch_before_merge) is stateless —
    returns (ok, message, returncode) instead of mutating instance dicts."""

    def _repo_with_epic_branch(self, tmp_path: Path) -> Path:
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "branch", "epic/epic-1-integration")
        return repo

    def test_disabled_gate_returns_true_without_running_anything(self, tmp_path: Path) -> None:
        repo = self._repo_with_epic_branch(tmp_path)
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        with patch("little_loops.worktree_utils.subprocess.run") as mock_run:
            ok, message, returncode = verify_epic_branch_before_merge(
                "EPIC-1",
                "epic/epic-1-integration",
                verify_before_merge=False,
                repo_path=repo,
                worktree_base=repo / ".worktrees",
                test_cmd="true",
                lint_cmd=None,
                logger=logger,
                git_lock=git_lock,
            )

        assert (ok, message, returncode) == (True, None, None)
        mock_run.assert_not_called()

    def test_passing_test_cmd_returns_true(self, tmp_path: Path) -> None:
        repo = self._repo_with_epic_branch(tmp_path)
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        ok, message, returncode = verify_epic_branch_before_merge(
            "EPIC-1",
            "epic/epic-1-integration",
            verify_before_merge=True,
            repo_path=repo,
            worktree_base=repo / ".worktrees",
            test_cmd="true",
            lint_cmd=None,
            logger=logger,
            git_lock=git_lock,
        )

        assert (ok, message, returncode) == (True, None, None)

    def test_failing_test_cmd_returns_false_with_message(self, tmp_path: Path) -> None:
        repo = self._repo_with_epic_branch(tmp_path)
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        ok, message, returncode = verify_epic_branch_before_merge(
            "EPIC-1",
            "epic/epic-1-integration",
            verify_before_merge=True,
            repo_path=repo,
            worktree_base=repo / ".worktrees",
            test_cmd="false",
            lint_cmd=None,
            logger=logger,
            git_lock=git_lock,
        )

        assert ok is False
        assert message is not None
        assert "test_cmd failed" in message
        # ENH-2631: `false` exits 1 (a real failure), surfaced as returncode 1.
        assert returncode == 1

    def test_collection_error_exit_code_surfaces_returncode_2(self, tmp_path: Path) -> None:
        """ENH-2631: a pytest-style exit 2 (collection/usage error) must surface
        returncode 2 so the caller can classify it as collection_error rather
        than a real test failure (exit 1)."""
        repo = self._repo_with_epic_branch(tmp_path)
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        ok, message, returncode = verify_epic_branch_before_merge(
            "EPIC-1",
            "epic/epic-1-integration",
            verify_before_merge=True,
            repo_path=repo,
            worktree_base=repo / ".worktrees",
            test_cmd="sh -c 'exit 2'",
            lint_cmd=None,
            logger=logger,
            git_lock=git_lock,
        )

        assert ok is False
        assert returncode == 2
        assert message is not None and "exit 2" in message

    def test_src_dir_prepends_worktree_source_onto_pythonpath(self, tmp_path: Path) -> None:
        """BUG-2629: when src_dir is set, the worktree's source dir is prepended to
        PYTHONPATH so the editable-install .pth cannot shadow branch-only modules.

        The test_cmd asserts the first PYTHONPATH entry basename is the src_dir,
        confirming the gate injects the isolated import path.
        """
        repo = self._repo_with_epic_branch(tmp_path)
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        check = (
            "import os,sys; "
            "p=os.environ.get('PYTHONPATH','').split(os.pathsep)[0]; "
            "sys.exit(0 if os.path.basename(p)=='scripts' else 1)"
        )

        ok, message, returncode = verify_epic_branch_before_merge(
            "EPIC-1",
            "epic/epic-1-integration",
            verify_before_merge=True,
            repo_path=repo,
            worktree_base=repo / ".worktrees",
            test_cmd=f"python3 -c {shlex.quote(check)}",
            lint_cmd=None,
            logger=logger,
            git_lock=git_lock,
            src_dir="scripts",
        )

        assert (ok, message, returncode) == (True, None, None)

    def test_falsy_src_dir_leaves_pythonpath_uninjected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUG-2629: src_dir=None (default) preserves prior behavior — no injection.

        Hermetic against the epic-merge verify gate: that gate injects the
        worktree's ``scripts/`` at PYTHONPATH[0] before running the suite, and
        the child subprocess here inherits ``os.environ``. Clearing PYTHONPATH
        first ensures we assert the gate's *own* (non-)behavior, not a leaked
        parent env (self-contamination false-negative).
        """
        monkeypatch.delenv("PYTHONPATH", raising=False)
        repo = self._repo_with_epic_branch(tmp_path)
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        check = (
            "import os,sys; "
            "p=os.environ.get('PYTHONPATH','').split(os.pathsep)[0]; "
            "sys.exit(1 if os.path.basename(p)=='scripts' else 0)"
        )

        ok, message, returncode = verify_epic_branch_before_merge(
            "EPIC-1",
            "epic/epic-1-integration",
            verify_before_merge=True,
            repo_path=repo,
            worktree_base=repo / ".worktrees",
            test_cmd=f"python3 -c {shlex.quote(check)}",
            lint_cmd=None,
            logger=logger,
            git_lock=git_lock,
        )

        assert (ok, message, returncode) == (True, None, None)

    def test_falsy_src_dir_does_not_inject_under_ambient_pythonpath(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUG-2649 regression: with ``src_dir`` falsy the gate must inject *nothing*
        onto PYTHONPATH even when the caller already has an ambient PYTHONPATH set —
        exactly the epic-merge verify-gate condition, where the outer suite runs with
        ``PYTHONPATH=<worktree>/scripts`` prepended.

        The child asserts its first PYTHONPATH entry is the caller's *ambient* marker
        verbatim (not a gate-prepended entry). A regression of the ``if src_dir:``
        guard — prepending regardless of ``src_dir`` — would push a different entry to
        the front, the child would exit 1, and this test would fail. Deterministic:
        the marker is a fixed absolute path, not a basename check that a leaked
        ``scripts`` entry could satisfy.
        """
        ambient = str(tmp_path / "ambient_marker")
        monkeypatch.setenv("PYTHONPATH", ambient)
        repo = self._repo_with_epic_branch(tmp_path)
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        check = (
            "import os,sys; "
            "p=os.environ.get('PYTHONPATH','').split(os.pathsep)[0]; "
            f"sys.exit(0 if p=={ambient!r} else 1)"
        )

        ok, message, returncode = verify_epic_branch_before_merge(
            "EPIC-1",
            "epic/epic-1-integration",
            verify_before_merge=True,
            repo_path=repo,
            worktree_base=repo / ".worktrees",
            test_cmd=f"python3 -c {shlex.quote(check)}",
            lint_cmd=None,
            logger=logger,
            git_lock=git_lock,
        )

        assert (ok, message, returncode) == (True, None, None)

    def test_verify_gate_marker_set_in_child_env(self, tmp_path: Path) -> None:
        """BUG-2649: the test/lint subprocess always carries ``LL_VERIFY_GATE=1`` so
        gate-sensitive tests can quarantine themselves deterministically."""
        repo = self._repo_with_epic_branch(tmp_path)
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        check = "import os,sys; sys.exit(0 if os.environ.get('LL_VERIFY_GATE')=='1' else 1)"

        ok, message, returncode = verify_epic_branch_before_merge(
            "EPIC-1",
            "epic/epic-1-integration",
            verify_before_merge=True,
            repo_path=repo,
            worktree_base=repo / ".worktrees",
            test_cmd=f"python3 -c {shlex.quote(check)}",
            lint_cmd=None,
            logger=logger,
            git_lock=git_lock,
        )

        assert (ok, message, returncode) == (True, None, None)

    def test_worktree_setup_failure_returns_false_with_message(self, tmp_path: Path) -> None:
        """A branch that doesn't exist fails worktree setup, not the test_cmd."""
        repo = _init_repo(tmp_path / "repo")
        logger = Logger(verbose=False)
        git_lock = GitLock(logger)

        ok, message, returncode = verify_epic_branch_before_merge(
            "EPIC-1",
            "epic/does-not-exist",
            verify_before_merge=True,
            repo_path=repo,
            worktree_base=repo / ".worktrees",
            test_cmd="true",
            lint_cmd=None,
            logger=logger,
            git_lock=git_lock,
        )

        assert ok is False
        assert message is not None
        assert "worktree setup failed" in message
        # ENH-2631: no command ran (setup failed first) — returncode is None.
        assert returncode is None


class TestOpenPrForEpicBranch:
    """open_pr_for_epic_branch() (BUG-2614: extracted from
    ParallelOrchestrator._open_pr_for_epic_branch) never raises — degrades
    gracefully when gh is unauthenticated, missing, or times out."""

    def test_skips_when_gh_not_authenticated(self, tmp_path: Path) -> None:
        logger = Logger(verbose=False)
        with patch(
            "little_loops.worktree_utils.subprocess.run",
            return_value=subprocess.CompletedProcess([], returncode=1),
        ) as mock_run:
            open_pr_for_epic_branch(
                "EPIC-1",
                "epic/epic-1-integration",
                base_branch="main",
                repo_path=tmp_path,
                logger=logger,
            )
        assert mock_run.call_count == 1  # only the auth-status check, no pr create

    def test_creates_pr_when_authenticated(self, tmp_path: Path) -> None:
        logger = Logger(verbose=False)

        def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            if args[:2] == ["gh", "auth"]:
                return subprocess.CompletedProcess(args, returncode=0)
            return subprocess.CompletedProcess(args, returncode=0, stdout="https://pr/1\n")

        with patch("little_loops.worktree_utils.subprocess.run", side_effect=fake_run):
            open_pr_for_epic_branch(
                "EPIC-1",
                "epic/epic-1-integration",
                base_branch="main",
                repo_path=tmp_path,
                logger=logger,
            )
        # No exception — the pr-create call ran with returncode 0.

    def test_gh_not_found_does_not_raise(self, tmp_path: Path) -> None:
        logger = Logger(verbose=False)
        with patch("little_loops.worktree_utils.subprocess.run", side_effect=FileNotFoundError):
            open_pr_for_epic_branch(
                "EPIC-1",
                "epic/epic-1-integration",
                base_branch="main",
                repo_path=tmp_path,
                logger=logger,
            )


class TestFormatVerifyDetail:
    """format_verify_detail() (ENH-2641): the verify gate must preserve the
    diagnostic *tail* (pytest FAILED / short-summary lines) of a failed command
    rather than a first-500-char prefix that leading stderr warnings crowd out
    (BUG-2640)."""

    def _pytest_streams(self) -> tuple[str, str]:
        # pytest-benchmark / xdist warnings go to stderr; the FAILED / short
        # summary block goes to stdout at the tail. Reproduces BUG-2640's shape.
        stderr = "\n".join(f"PytestBenchmarkWarning: bench line {i}" for i in range(60))
        stdout = (
            "collected 9 items\n\n"
            + "\n".join(f"test_issues_cli.py::test_case_{i} FAILED" for i in range(9))
            + "\n\n=== short test summary info ===\n"
            + "\n".join(f"FAILED test_issues_cli.py::test_case_{i}" for i in range(9))
            + "\n9 failed, 100 passed in 71.02s\n"
        )
        return stdout, stderr

    def test_failure_summary_survives_leading_warnings(self) -> None:
        stdout, stderr = self._pytest_streams()
        detail = format_verify_detail(stdout, stderr)

        assert "short test summary info" in detail
        assert "9 failed, 100 passed" in detail
        assert "FAILED test_issues_cli.py::test_case_8" in detail

    def test_result_is_bounded(self) -> None:
        stdout, stderr = self._pytest_streams()
        detail = format_verify_detail(stdout, stderr, max_lines=40, max_chars=2000)

        assert len(detail) <= 2000
        assert len(detail.splitlines()) <= 40

    def test_stdout_only_failure_preserved(self) -> None:
        # No stderr: the whole tail comes from stdout.
        detail = format_verify_detail("line1\nline2\nFAILED foo\n", "")
        assert "FAILED foo" in detail

    def test_empty_streams_return_empty(self) -> None:
        assert format_verify_detail(None, None) == ""
        assert format_verify_detail("", "   ") == ""
