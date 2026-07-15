"""Read a file's blob at an arbitrary git ref via `git show <ref>:<path>`.

Proves the net-new mechanism FEAT-2652's optional "spot-check cited symbols
resolve on the declared base" step needs. There is no precedent for a
blob-at-ref read in `scripts/little_loops/`, so this spike establishes the
shape: route through `GitLock.run([...])` (no bare subprocess), classify
absence via returncode rather than exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from little_loops.parallel.git_lock import GitLock


@dataclass(frozen=True)
class BlobResult:
    """Outcome of a blob-at-ref read.

    Attributes:
        ok: True when the blob resolved (returncode 0).
        content: The blob's text when ``ok``; empty string otherwise.
        returncode: The raw git exit code (for diagnostics/classification).
        stderr: Git's error output when the read failed.
    """

    ok: bool
    content: str
    returncode: int
    stderr: str


def read_blob_at_ref(git_lock: GitLock, repo: Path, ref: str, path: str) -> BlobResult:
    """Read ``path`` as it exists at ``ref`` using ``git show <ref>:<path>``.

    A missing path-at-ref or a nonexistent ref both surface as a non-zero
    ``returncode`` (git does not raise), so the caller can classify "symbol
    absent on base" without exception handling.

    Args:
        git_lock: Shared git operation lock (the only sanctioned git entry point).
        repo: Repository working directory.
        ref: Any resolvable ref (branch, tag, SHA).
        path: Repo-relative path to read at that ref.

    Returns:
        BlobResult with ``ok`` reflecting the returncode.
    """
    result = git_lock.run(["show", f"{ref}:{path}"], cwd=repo, timeout=30)
    ok = result.returncode == 0
    return BlobResult(
        ok=ok,
        content=result.stdout if ok else "",
        returncode=result.returncode,
        stderr=result.stderr or "",
    )
