"""Spike harness for BUG-2650: repeatedly drive the real epic verify gate.

Proves the fixed-repeat-loop-through-the-gate shape (Option A) is both bounded
(does not trip the suite's CPU-starvation/beachball constraint) and useful
(can actually observe the gate's checkout -> subprocess -> file-read path),
independent of whether the target flake reproduces.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from little_loops.logger import Logger
from little_loops.parallel.git_lock import GitLock
from little_loops.worktree_utils import verify_epic_branch_before_merge

MAX_ITERATIONS = 25
MAX_WORKERS = 2


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def build_repo_with_needle(tmp_path: Path, needle: str = "spike") -> Path:
    """Init a repo whose epic branch has ``needle`` in a tracked file."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "--initial-branch", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial commit")

    _git(repo, "checkout", "-b", "epic/epic-1-integration")
    (repo / "sentinel.txt").write_text(f"needle: {needle}\n")
    _git(repo, "add", "sentinel.txt")
    _git(repo, "commit", "-m", "add needle sentinel")
    _git(repo, "checkout", "main")
    return repo


def _write_runner_script(repo: Path, needle: str, max_workers: int) -> Path:
    """Write a standalone runner script (outside any worktree) that, given a
    worktree cwd, drops a needle-check pytest file next to sentinel.txt and
    runs it under xdist. Passed to verify_epic_branch_before_merge() as a
    single-word test_cmd so shlex.split() has nothing to mis-tokenize.
    """
    needle_test_source = (
        "from pathlib import Path\n\n"
        "def test_needle_present():\n"
        "    text = Path(__file__).parent.joinpath('sentinel.txt').read_text()\n"
        f"    assert {needle!r} in text\n"
    )
    pytest_argv = [
        "python",
        "-m",
        "pytest",
        "-n",
        str(max_workers),
        "--no-header",
        "-q",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=",
        "test_needle_present.py",
    ]
    script = repo / "_spike_runner.py"
    script.write_text(
        "import subprocess\n"
        "from pathlib import Path\n\n"
        f"Path('test_needle_present.py').write_text({needle_test_source!r})\n"
        f"raise SystemExit(subprocess.run({pytest_argv!r}).returncode)\n"
    )
    return script


def run_gate_n_times(
    repo: Path,
    *,
    iterations: int,
    max_workers: int = MAX_WORKERS,
    needle: str = "spike",
) -> list[tuple[bool, str | None, int | None]]:
    """Drive verify_epic_branch_before_merge() ``iterations`` times.

    Bounded by MAX_ITERATIONS/MAX_WORKERS regardless of caller input, so the
    spike itself cannot reproduce the beachball trigger documented against the
    full suite (project_test_suite_beachball_fix memory).
    """
    if iterations > MAX_ITERATIONS:
        raise ValueError(f"iterations={iterations} exceeds spike cap of {MAX_ITERATIONS}")
    if max_workers > MAX_WORKERS:
        raise ValueError(f"max_workers={max_workers} exceeds spike cap of {MAX_WORKERS}")

    logger = Logger(verbose=False)
    git_lock = GitLock(logger)
    results: list[tuple[bool, str | None, int | None]] = []

    script = _write_runner_script(repo, needle, max_workers)
    worktree_base = ".worktrees"
    (repo / worktree_base).mkdir(exist_ok=True)

    for _ in range(iterations):
        ok, message, returncode = verify_epic_branch_before_merge(
            "EPIC-1",
            "epic/epic-1-integration",
            verify_before_merge=True,
            repo_path=repo,
            worktree_base=worktree_base,
            test_cmd=f"python {script}",
            lint_cmd=None,
            logger=logger,
            git_lock=git_lock,
        )
        results.append((ok, message, returncode))

    return results
