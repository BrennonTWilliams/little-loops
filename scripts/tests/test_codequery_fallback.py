"""Tests for little_loops.codequery.fallback.FallbackProvider.

Uses a real git repo under tmp_path (pattern from test_worktree_utils.py) since
FallbackProvider shells out to ``git grep``/``git ls-files``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from little_loops.codequery.fallback import FallbackProvider


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--initial-branch", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    return path


def _write_and_commit(repo: Path, rel_path: str, content: str) -> None:
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", rel_path)
    _git(repo, "commit", "-m", f"add {rel_path}")


def test_defines_finds_functions_and_classes(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path / "repo")
    _write_and_commit(
        repo,
        "pkg/mod.py",
        "def helper():\n    pass\n\n\nclass Thing:\n    pass\n",
    )
    monkeypatch.chdir(repo)

    provider = FallbackProvider()
    refs = provider.defines("pkg/mod.py")

    names = {ref.symbol for ref in refs}
    assert names == {"helper", "Thing"}
    assert all(ref.confidence == "exact" for ref in refs)


def test_defines_skips_unparsable_file(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path / "repo")
    _write_and_commit(repo, "pkg/broken.py", "def helper(:\n")
    monkeypatch.chdir(repo)

    provider = FallbackProvider()
    refs = provider.defines("pkg/broken.py")

    assert refs == []


def test_callers_of_returns_heuristic_hits(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path / "repo")
    _write_and_commit(
        repo,
        "pkg/mod.py",
        "def helper():\n    pass\n",
    )
    _write_and_commit(
        repo,
        "pkg/user.py",
        "from pkg.mod import helper\n\nhelper()\n",
    )
    monkeypatch.chdir(repo)

    provider = FallbackProvider()
    refs = provider.callers_of("pkg.mod.helper")

    assert refs, "expected at least one caller hit"
    assert all(ref.confidence == "heuristic" for ref in refs)
    call_sites = [ref for ref in refs if ref.path == "pkg/user.py"]
    assert call_sites


def test_references_includes_definition_and_uses(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path / "repo")
    _write_and_commit(repo, "pkg/mod.py", "def helper():\n    pass\n\nhelper()\n")
    monkeypatch.chdir(repo)

    provider = FallbackProvider()
    refs = provider.references("helper")

    assert len(refs) >= 2


def test_importers_of_finds_import_statements(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path / "repo")
    _write_and_commit(repo, "pkg/mod.py", "x = 1\n")
    _write_and_commit(repo, "pkg/user.py", "import pkg.mod\n")
    monkeypatch.chdir(repo)

    provider = FallbackProvider()
    refs = provider.importers_of("pkg/mod.py")

    assert any(ref.path == "pkg/user.py" for ref in refs)


def test_impact_of_walks_import_graph(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path / "repo")
    _write_and_commit(repo, "pkg/base.py", "x = 1\n")
    _write_and_commit(repo, "pkg/mid.py", "import pkg.base\n")
    _write_and_commit(repo, "pkg/top.py", "import pkg.mid\n")
    monkeypatch.chdir(repo)

    provider = FallbackProvider()
    refs = provider.impact_of(["pkg/base.py"], depth=2)

    impacted_paths = {ref.path for ref in refs}
    assert "pkg/mid.py" in impacted_paths


def test_status_is_always_available_and_fresh():
    provider = FallbackProvider()
    status = provider.status()
    assert status.available is True
    assert status.freshness == "fresh"


def test_capabilities_returns_all_query_kinds():
    from little_loops.codequery.core import QUERY_KINDS

    provider = FallbackProvider()
    assert provider.capabilities() == set(QUERY_KINDS)
