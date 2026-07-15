"""Spike ACs: prove `git show <ref>:<path>` blob-at-ref reads for FEAT-2652.

Builds a real temp repo with a base branch and a feature branch where a symbol
exists only on the feature branch — the exact FEAT-2652 wrong-base scenario —
and proves absence is signalled by returncode, never an exception.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from little_loops.parallel.git_lock import GitLock

from .blob_reader import read_blob_at_ref


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A repo with `base` (no feature symbol) and `feature` (adds it)."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "base")
    _git(r, "config", "user.email", "spike@example.com")
    _git(r, "config", "user.name", "spike")
    (r / "shared.py").write_text("def common():\n    return 1\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "base commit")

    _git(r, "checkout", "-q", "-b", "feature")
    (r / "redesign.py").write_text("def new_symbol():\n    return 42\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "feature adds redesign symbol")
    _git(r, "checkout", "-q", "base")
    return r


def test_reads_blob_present_on_ref(repo: Path) -> None:
    """AC1: content is read at an arbitrary ref via returncode/stdout."""
    res = read_blob_at_ref(GitLock(), repo, "base", "shared.py")
    assert res.ok is True
    assert res.returncode == 0
    assert "def common()" in res.content


def test_missing_path_at_ref_returns_nonzero(repo: Path) -> None:
    """AC2: a path absent at the ref → non-zero, no exception raised."""
    res = read_blob_at_ref(GitLock(), repo, "base", "does_not_exist.py")
    assert res.ok is False
    assert res.returncode != 0
    assert res.content == ""


def test_missing_path_on_base_but_present_on_feature(repo: Path) -> None:
    """AC2 (FEAT-2652 scenario): symbol on feature branch, absent on base.

    This is precisely the wrong-base false-negative the feature guards against.
    """
    on_base = read_blob_at_ref(GitLock(), repo, "base", "redesign.py")
    on_feature = read_blob_at_ref(GitLock(), repo, "feature", "redesign.py")

    assert on_base.ok is False  # absent on base → would be a false NOT_READY
    assert on_feature.ok is True  # resolves on the branch the EPIC intends
    assert "def new_symbol()" in on_feature.content


def test_nonexistent_ref_returns_nonzero(repo: Path) -> None:
    """AC3: a bad ref → non-zero cleanly, no exception."""
    res = read_blob_at_ref(GitLock(), repo, "no-such-branch", "shared.py")
    assert res.ok is False
    assert res.returncode != 0


def test_uses_gitlock_no_bare_subprocess() -> None:
    """Regression guard: blob_reader must route git through GitLock, not bare subprocess."""
    src = (Path(__file__).parent / "blob_reader.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            offending = node.value.id == "subprocess" and node.attr in {"run", "call", "Popen"}
            assert not offending, "blob_reader must not call subprocess directly; use GitLock.run"
