"""Git post-commit handler: record commit metadata into history.db (ENH-2458).

Invoked by ``hooks/scripts/record-commit-post-commit`` (a git ``post-commit``
hook) or directly via ``python -m little_loops.hooks.post_commit``. Reads the
HEAD commit's metadata from git and writes one ``commit_events`` row through
:func:`little_loops.session_store.record_commit_event`.

Wiring is a project-level decision and is not forced by ``ll-init``; enable it
with either::

    git config core.hooksPath <plugin-root>/hooks/git
    # or symlink/copy hooks/scripts/record-commit-post-commit to .git/hooks/post-commit

Everything here is best-effort per the EPIC-1707 graceful-degradation
contract: a missing git binary, detached HEAD, or locked database exits 0
without disturbing the commit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_GIT_TIMEOUT = 10


def _git(repo_root: Path, *args: str) -> str | None:
    """Return stripped stdout of a git command run in *repo_root*, or None."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def record_head_commit(db_path: Path | str, repo_root: Path | None = None) -> bool:
    """Record the repository's HEAD commit as a ``commit_events`` row.

    Returns True when a new row was inserted (False on duplicates or when git
    metadata could not be gathered).
    """
    from little_loops.session_store import record_commit_event

    root = repo_root if repo_root is not None else Path.cwd()
    raw = _git(root, "log", "-1", "--format=%H%x1f%P%x1f%an%x1f%aI%x1f%B")
    if not raw:
        return False
    parts = raw.split("\x1f")
    if len(parts) < 5:
        return False
    sha, parents, author, author_date, message = (
        parts[0].strip(),
        parts[1].strip(),
        parts[2].strip(),
        parts[3].strip(),
        parts[4].strip(),
    )
    if not sha:
        return False
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":  # detached HEAD — no meaningful branch name
        branch = None
    files_raw = _git(root, "show", "--pretty=format:", "--name-only", sha)
    files = [line.strip() for line in (files_raw or "").splitlines() if line.strip()]
    return record_commit_event(
        db_path,
        sha,
        message,
        author=author or None,
        branch=branch,
        files=files,
        parent_sha=parents.split(" ")[0] if parents else None,
        ts=author_date or None,
    )


def main() -> int:
    """Entry point for ``python -m little_loops.hooks.post_commit``. Always exits 0."""
    try:
        from little_loops.session_store import resolve_history_db

        cwd = Path.cwd()
        # Only record inside little-loops projects: require an existing .ll/
        # directory (or an explicit LL_HISTORY_DB override).
        import os

        if not os.environ.get("LL_HISTORY_DB") and not (cwd / ".ll").is_dir():
            return 0
        record_head_commit(resolve_history_db(), cwd)
    except Exception:
        # Never block or fail a commit.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
