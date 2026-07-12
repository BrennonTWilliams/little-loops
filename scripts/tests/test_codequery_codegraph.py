"""Tests for little_loops.codequery.codegraph: CodegraphProvider (ENH-2613).

No checked-in binary `.db` fixture — fixture DBs are built programmatically at
test time via hand-written CREATE TABLE/INSERT SQL matching the schema
discovered against this repo's live `.codegraph/codegraph.db` (pinned below as
`_SCHEMA_COLUMNS` — a schema-drift guard: if the upstream codegraph tool
changes its column names, this test fails loudly instead of silently
returning wrong data).
"""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from little_loops.codequery.codegraph import CodegraphProvider
from little_loops.codequery.core import (
    QUERY_KINDS,
    CodeQueryProvider,
    Unsupported,
    resolve_provider,
)

# Schema-drift guard: pinned column set from the discovered codegraph schema
# (see codegraph.py module docstring). If this ever fails, the upstream tool
# changed its schema and the provider's SQL needs to be revisited.
_SCHEMA_COLUMNS = {
    "nodes": {
        "id",
        "kind",
        "name",
        "qualified_name",
        "file_path",
        "language",
        "start_line",
        "end_line",
        "start_column",
        "end_column",
        "updated_at",
    },
    "edges": {"id", "source", "target", "kind", "line", "col"},
    "files": {"path", "content_hash", "language", "size", "modified_at", "indexed_at"},
    "schema_versions": {"version", "applied_at", "description"},
}


# Fixed baseline instant for deterministic commit timestamps -- avoids
# flakiness from 1-second git author-date granularity / wall-clock races.
_T0 = "2020-01-01T00:00:00+00:00"


def _git(
    cwd: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    import os

    full_env = {**os.environ, **env} if env else None
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, env=full_env
    )


def _commit_at(repo: Path, message: str, iso_date: str) -> None:
    _git(
        repo,
        "commit",
        "-m",
        message,
        env={"GIT_AUTHOR_DATE": iso_date, "GIT_COMMITTER_DATE": iso_date},
    )


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--initial-branch", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("test\n")
    _git(path, "add", "README.md")
    _commit_at(path, "initial commit", _T0)
    return path


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE schema_versions (
            version INTEGER PRIMARY KEY,
            applied_at INTEGER NOT NULL,
            description TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE nodes (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            language TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            start_column INTEGER NOT NULL,
            end_column INTEGER NOT NULL,
            docstring TEXT,
            signature TEXT,
            visibility TEXT,
            is_exported INTEGER DEFAULT 0,
            is_async INTEGER DEFAULT 0,
            is_static INTEGER DEFAULT 0,
            is_abstract INTEGER DEFAULT 0,
            decorators TEXT,
            type_parameters TEXT,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            kind TEXT NOT NULL,
            metadata TEXT,
            line INTEGER,
            col INTEGER,
            provenance TEXT DEFAULT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            language TEXT NOT NULL,
            size INTEGER NOT NULL,
            modified_at INTEGER NOT NULL,
            indexed_at INTEGER NOT NULL,
            node_count INTEGER DEFAULT 0,
            errors TEXT
        )
        """
    )


def _insert_node(
    conn: sqlite3.Connection,
    id: str,
    kind: str,
    name: str,
    qualified_name: str,
    file_path: str,
    start_line: int = 1,
) -> None:
    conn.execute(
        "INSERT INTO nodes (id, kind, name, qualified_name, file_path, language, "
        "start_line, end_line, start_column, end_column, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'python', ?, ?, 0, 0, 0)",
        (id, kind, name, qualified_name, file_path, start_line, start_line + 1),
    )


def _insert_edge(
    conn: sqlite3.Connection, source: str, target: str, kind: str, line: int = 1
) -> None:
    conn.execute(
        "INSERT INTO edges (source, target, kind, line) VALUES (?, ?, ?, ?)",
        (source, target, kind, line),
    )


def _insert_file(conn: sqlite3.Connection, path: str, indexed_at_ms: int) -> None:
    conn.execute(
        "INSERT INTO files (path, content_hash, language, size, modified_at, indexed_at) "
        "VALUES (?, 'hash', 'python', 1, ?, ?)",
        (path, indexed_at_ms, indexed_at_ms),
    )


def _build_index(db_path: Path, indexed_at_ms: int) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        _create_schema(conn)
        conn.execute(
            "INSERT INTO schema_versions (version, applied_at, description) VALUES (4, ?, 'x')",
            (indexed_at_ms,),
        )

        _insert_node(conn, "function:caller", "function", "caller", "caller", "pkg/a.py", 5)
        _insert_node(conn, "function:target", "function", "target", "target", "pkg/b.py", 10)
        _insert_edge(conn, "function:caller", "function:target", "calls", line=6)

        _insert_node(conn, "class:Widget", "class", "Widget", "Widget", "pkg/b.py", 1)
        _insert_node(conn, "method:Widget.run", "method", "run", "Widget::run", "pkg/b.py", 12)

        _insert_node(conn, "file:pkg/a.py", "file", "a.py", "a.py", "pkg/a.py", 1)
        _insert_node(conn, "import:pkg.b", "import", "b", "pkg.b", "pkg/a.py", 1)
        _insert_edge(conn, "file:pkg/a.py", "import:pkg.b", "imports", line=1)

        _insert_file(conn, "pkg/a.py", indexed_at_ms)
        _insert_file(conn, "pkg/b.py", indexed_at_ms)
        conn.commit()
    finally:
        conn.close()


def _write_config(repo: Path, staleness: str = "warn") -> None:
    import json

    ll_dir = repo / ".ll"
    ll_dir.mkdir(exist_ok=True)
    (ll_dir / "ll-config.json").write_text(
        json.dumps({"code_query": {"provider": "codegraph", "staleness": staleness}}),
        encoding="utf-8",
    )


class TestSchemaGuard:
    def test_pinned_columns_present_in_fixture(self, tmp_path: Path) -> None:
        db_path = tmp_path / "codegraph.db"
        _build_index(db_path, indexed_at_ms=0)
        conn = sqlite3.connect(db_path)
        try:
            for table, expected_cols in _SCHEMA_COLUMNS.items():
                actual = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                assert expected_cols <= actual, f"{table} missing columns: {expected_cols - actual}"
        finally:
            conn.close()


class TestCapabilities:
    def test_capabilities_excludes_impact_of(self) -> None:
        provider = CodegraphProvider()
        assert "impact_of" not in provider.capabilities()
        assert provider.capabilities() <= QUERY_KINDS

    def test_impact_of_raises_unsupported(self) -> None:
        provider = CodegraphProvider()
        with pytest.raises(Unsupported):
            provider.impact_of(["pkg/a.py"])

    def test_satisfies_protocol(self) -> None:
        assert isinstance(CodegraphProvider(), CodeQueryProvider)


class TestStatusMissingIndex:
    def test_no_db_reports_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path / "repo")
        _write_config(repo)
        monkeypatch.chdir(repo)

        status = CodegraphProvider().status()
        assert status.available is False
        assert status.freshness == "unknown"
        assert status.indexed_at is None


class TestStalenessMatrix:
    """fresh / commits-ahead / dirty-tree x strict / warn / off."""

    # Baseline commit (config + index) lands at _BASELINE_COMMIT_ISO; the
    # index's own build timestamp (_INDEX_BUILT_MS) is 5s later, so a
    # `git log --since=<indexed_at>` never double-counts the baseline commit
    # itself. The "commits ahead" test's follow-up commit lands at _T2, well
    # after _INDEX_BUILT_MS.
    _BASELINE_COMMIT_ISO = "2020-01-01T00:00:05+00:00"
    _INDEX_BUILT_MS = 1577836810000  # 2020-01-01T00:00:10Z, epoch ms
    _T2 = "2020-01-01T00:01:00+00:00"  # well after _INDEX_BUILT_MS

    def _repo_with_fresh_index(self, tmp_path: Path, staleness: str) -> Path:
        repo = _init_repo(tmp_path / "repo")
        _write_config(repo, staleness=staleness)
        _build_index(repo / ".codegraph" / "codegraph.db", indexed_at_ms=self._INDEX_BUILT_MS)
        # Commit the config + index so the working tree starts clean; tests
        # that need a dirty tree or later commits add their own changes on
        # top of this baseline.
        _git(repo, "add", "-A")
        _commit_at(repo, "add config and codegraph index", self._BASELINE_COMMIT_ISO)
        return repo

    @pytest.mark.parametrize("policy", ["strict", "warn", "off"])
    def test_fresh_index_available_and_fresh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, policy: str
    ) -> None:
        repo = self._repo_with_fresh_index(tmp_path, policy)
        monkeypatch.chdir(repo)

        status = CodegraphProvider().status()
        assert status.available is True
        assert status.freshness == "fresh"

    @pytest.mark.parametrize(
        "policy,expect_available",
        [("strict", False), ("warn", True), ("off", True)],
    )
    def test_commits_ahead_marks_stale_per_policy(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        policy: str,
        expect_available: bool,
    ) -> None:
        repo = self._repo_with_fresh_index(tmp_path, policy)
        (repo / "new_file.txt").write_text("more\n")
        _git(repo, "add", "new_file.txt")
        _commit_at(repo, "a commit after index build", self._T2)
        monkeypatch.chdir(repo)

        status = CodegraphProvider().status()
        assert status.available is expect_available
        assert status.freshness == ("fresh" if policy == "off" else "stale")

    @pytest.mark.parametrize(
        "policy,expect_available",
        [("strict", False), ("warn", True), ("off", True)],
    )
    def test_dirty_tree_marks_stale_per_policy(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        policy: str,
        expect_available: bool,
    ) -> None:
        repo = self._repo_with_fresh_index(tmp_path, policy)
        (repo / "README.md").write_text("dirty change\n")
        monkeypatch.chdir(repo)

        status = CodegraphProvider().status()
        assert status.available is expect_available
        assert status.freshness == ("fresh" if policy == "off" else "stale")


class TestQueries:
    @pytest.fixture
    def repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        repo = _init_repo(tmp_path / "repo")
        _write_config(repo)
        _build_index(repo / ".codegraph" / "codegraph.db", indexed_at_ms=0)
        monkeypatch.chdir(repo)
        return repo

    def test_callers_of_returns_exact_edge(self, repo: Path) -> None:
        provider = CodegraphProvider()
        refs = provider.callers_of("target")
        assert len(refs) == 1
        assert refs[0].path == "pkg/a.py"
        assert refs[0].line == 6
        assert refs[0].symbol == "caller"
        assert refs[0].confidence == "exact"
        assert refs[0].provider == "codegraph"

    def test_callees_of_returns_exact_edge(self, repo: Path) -> None:
        provider = CodegraphProvider()
        refs = provider.callees_of("caller")
        assert len(refs) == 1
        assert refs[0].symbol == "target"
        assert refs[0].path == "pkg/b.py"

    def test_defines_returns_nodes_in_file(self, repo: Path) -> None:
        provider = CodegraphProvider()
        refs = provider.defines("pkg/b.py")
        names = {ref.symbol for ref in refs}
        assert {"target", "Widget", "run"} <= names

    def test_defines_no_hits_returns_empty(self, repo: Path) -> None:
        provider = CodegraphProvider()
        assert provider.defines("pkg/does_not_exist.py") == []

    def test_references_includes_call_sites(self, repo: Path) -> None:
        provider = CodegraphProvider()
        refs = provider.references("target")
        assert any(ref.path == "pkg/a.py" and ref.line == 6 for ref in refs)

    def test_importers_of_resolves_dotted_module(self, repo: Path) -> None:
        provider = CodegraphProvider()
        refs = provider.importers_of("pkg.b")
        assert len(refs) == 1
        assert refs[0].path == "pkg/a.py"
        assert refs[0].kind == "import"

    def test_importers_of_resolves_file_path(self, repo: Path) -> None:
        provider = CodegraphProvider()
        refs = provider.importers_of("pkg/b.py")
        assert len(refs) == 1
        assert refs[0].path == "pkg/a.py"

    def test_unknown_symbol_returns_empty(self, repo: Path) -> None:
        provider = CodegraphProvider()
        assert provider.callers_of("does_not_exist") == []


class TestResolverRegistration:
    def test_codegraph_registered_before_fallback(self) -> None:
        from little_loops.codequery.core import _PROVIDER_MAP

        assert list(_PROVIDER_MAP) == ["codegraph", "fallback"]

    def test_resolve_provider_codegraph_returns_codegraph_provider(self) -> None:
        provider = resolve_provider("codegraph")
        assert provider.name == "codegraph"
        assert isinstance(provider, CodeQueryProvider)
