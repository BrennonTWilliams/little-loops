"""Concurrency regression test for worktree setup/cleanup (ENH-2326).

Guards against regressions of BUG-140 (create/merge race), BUG-142
(active-worktree delete), and BUG-579 (orphan-vs-live race) by running
N concurrent workers against a real temporary git repository.
"""

from __future__ import annotations

import concurrent.futures
import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from little_loops.parallel.git_lock import GitLock
from little_loops.worktree_utils import cleanup_worktree, setup_worktree

pytestmark = pytest.mark.integration


@pytest.fixture
def temp_git_repo() -> Generator[Path, None, None]:
    """Create a temporary git repository with an initial commit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            capture_output=True,
        )

        test_file = repo_path / "test.txt"
        test_file.write_text("initial content")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial commit"],
            cwd=repo_path,
            capture_output=True,
        )

        yield repo_path


class TestWorktreeConcurrency:
    """Concurrent setup+cleanup leaves no orphaned worktrees or branches."""

    def test_concurrent_setup_cleanup_leaves_no_orphans(self, temp_git_repo: Path) -> None:
        """N concurrent workers each create + clean up a worktree with a shared GitLock.

        After all workers finish:
        - No .worktrees/ directories remain (BUG-140, BUG-579)
        - No dangling parallel/* branches remain
        - No index.lock leak detected

        Regression guard for BUG-140 (create/merge race) and BUG-579 (orphan-vs-live).
        """
        repo_path = temp_git_repo
        git_lock = GitLock(logger=MagicMock())
        K = 4

        def worker(n: int) -> None:
            branch_name = f"parallel/worker-{n}"
            wt_path = repo_path / ".worktrees" / f"worker-{n}"
            logger = MagicMock()
            setup_worktree(
                repo_path=repo_path,
                worktree_path=wt_path,
                branch_name=branch_name,
                copy_files=[],
                logger=logger,
                git_lock=git_lock,
            )
            cleanup_worktree(
                worktree_path=wt_path,
                repo_path=repo_path,
                logger=logger,
                git_lock=git_lock,
                delete_branch=True,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=K) as executor:
            futures = [executor.submit(worker, n) for n in range(K)]
            for future in concurrent.futures.as_completed(futures):
                future.result()  # re-raise any exceptions from workers

        worktree_base = repo_path / ".worktrees"
        remaining = list(worktree_base.glob("worker-*")) if worktree_base.exists() else []
        assert not remaining, f"Orphaned worktrees after concurrent run: {remaining}"

        branches = subprocess.run(
            ["git", "branch", "--list", "parallel/*"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        dangling = [b.strip() for b in branches.stdout.splitlines() if b.strip()]
        assert not dangling, f"Dangling parallel/* branches after concurrent run: {dangling}"

        index_lock = repo_path / ".git" / "index.lock"
        assert not index_lock.exists(), "index.lock leaked after concurrent worktree run"
