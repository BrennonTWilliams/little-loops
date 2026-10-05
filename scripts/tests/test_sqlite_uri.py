"""BUG-3737: literal-path SQLite ``file:`` URIs select exactly the intended database.

Every intended path lives under a plain fixture-owned container so truncated/decoded aliases
(``hash`` for ``hash#name.db``, ...) land inside the container and can be snapshotted.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

from little_loops.codequery.codegraph import _open_db
from little_loops.issue_history import workspace_quality
from little_loops.session_store.backend import HistoryUnavailable, resolve_backend
from little_loops.session_store.deadline import Deadline
from little_loops.session_store.queries import _connect_readonly, build_snapshot_db
from little_loops.session_store.sessions import _query_threads_db
from little_loops.sqlite_uri import sqlite_file_uri

# (intended filename, alias that the unescaped URI would select instead)
CASES = [
    ("hash#name.db", "hash"),
    ("query?name.db", "query"),
    ("percent%23name.db", "percent#name.db"),
    ("percent%3Fname.db", "percent?name.db"),
    ("percent%00name.db", "percent"),
    ("option?mode=rw&x.db", "option"),
    ("with space.db", None),
    ("ünï.db", None),
]
IDS = [c[0] for c in CASES]


def _make_db(path: Path, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE evidence(label TEXT)")
    conn.execute("INSERT INTO evidence VALUES (?)", (label,))
    conn.commit()
    conn.close()


def _label(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT label FROM evidence").fetchone()[0]


def _tree(root: Path) -> set[str]:
    """Every path under *root*, ignoring SQLite-managed WAL/SHM sidecars (documented exception)."""
    return {
        str(p.relative_to(root)) for p in root.rglob("*") if not p.name.endswith(("-wal", "-shm"))
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(container: Path, name: str, alias: str | None, *, populate_alias: bool) -> Path:
    intended = container / name
    _make_db(intended, "literal")
    if alias is not None and populate_alias:
        _make_db(container / alias, "decoy")
    return intended


class TestHelperContract:
    @pytest.mark.parametrize(("name", "alias"), CASES, ids=IDS)
    @pytest.mark.parametrize("populate_alias", [False, True])
    def test_ro_selects_intended_file(self, tmp_path, name, alias, populate_alias) -> None:
        container = tmp_path / "box"
        intended = _fixture(container, name, alias, populate_alias=populate_alias)
        before = _tree(container)
        conn = sqlite3.connect(sqlite_file_uri(intended), uri=True)
        try:
            assert _label(conn) == "literal"
            with pytest.raises(sqlite3.OperationalError):
                conn.execute("INSERT INTO evidence VALUES ('x')")
        finally:
            conn.close()
        assert _tree(container) == before

    @pytest.mark.parametrize(("name", "alias"), CASES, ids=IDS)
    def test_rw_commits_only_to_intended_file(self, tmp_path, name, alias) -> None:
        container = tmp_path / "box"
        intended = _fixture(container, name, alias, populate_alias=True)
        alias_sha = _sha(container / alias) if alias else None
        conn = sqlite3.connect(sqlite_file_uri(intended, mode="rw"), uri=True)
        conn.execute("INSERT INTO evidence VALUES ('written')")
        conn.commit()
        conn.close()
        check = sqlite3.connect(intended)
        assert check.execute("SELECT count(*) FROM evidence").fetchone()[0] == 2
        check.close()
        if alias:
            assert _sha(container / alias) == alias_sha

    @pytest.mark.parametrize("mode", ["ro", "rw"])
    @pytest.mark.parametrize(("name", "alias"), CASES, ids=IDS)
    @pytest.mark.parametrize("populate_alias", [False, True])
    def test_missing_intended_file_fails_without_creating(
        self, tmp_path, mode, name, alias, populate_alias
    ) -> None:
        container = tmp_path / "box"
        container.mkdir()
        if alias is not None and populate_alias:
            _make_db(container / alias, "decoy")
        before = _tree(container)
        alias_sha = _sha(container / alias) if alias and populate_alias else None
        with pytest.raises(sqlite3.OperationalError):
            sqlite3.connect(sqlite_file_uri(container / name, mode=mode), uri=True)
        assert _tree(container) == before
        if alias_sha:
            assert _sha(container / alias) == alias_sha

    def test_special_character_directory(self, tmp_path) -> None:
        container = tmp_path / "box"
        _make_db(container / "dir#x?y%23" / "history.db", "literal")
        _make_db(container / "dir", "decoy-dir-file")  # truncation alias target
        conn = sqlite3.connect(sqlite_file_uri(container / "dir#x?y%23" / "history.db"), uri=True)
        assert _label(conn) == "literal"
        conn.close()

    def test_relative_path_is_made_absolute(self, tmp_path, monkeypatch) -> None:
        _make_db(tmp_path / "rel#.db", "literal")
        monkeypatch.chdir(tmp_path)
        uri = sqlite_file_uri(Path("rel#.db"))
        assert uri.startswith("file:///")
        conn = sqlite3.connect(uri, uri=True)
        assert _label(conn) == "literal"
        conn.close()

    def test_symlink_and_dotdot_spelling_preserved(self, tmp_path) -> None:
        real = tmp_path / "real"
        _make_db(real / "a.db", "literal")
        (tmp_path / "link").symlink_to(real, target_is_directory=True)
        spelled = tmp_path / "link" / ".." / "real" / "a.db"
        assert ".." in sqlite_file_uri(spelled)
        assert "link" in sqlite_file_uri(spelled)
        conn = sqlite3.connect(sqlite_file_uri(spelled), uri=True)
        assert _label(conn) == "literal"
        conn.close()

    def test_literal_percent_00_is_valid_and_encoded(self, tmp_path) -> None:
        assert sqlite_file_uri(tmp_path / "a%00b.db").endswith("a%2500b.db?mode=ro")

    def test_actual_nul_rejected_before_alias_can_open(self, tmp_path) -> None:
        _make_db(tmp_path / "nul", "alias")
        sha = _sha(tmp_path / "nul")
        for mode in ("ro", "rw"):
            with pytest.raises(ValueError):
                sqlite_file_uri(Path(str(tmp_path / "nul") + "\x00tail.db"), mode=mode)
        assert _sha(tmp_path / "nul") == sha

    @pytest.mark.parametrize("mode", ["rwc", "memory", "ro&immutable=1", "", "RO"])
    def test_unsupported_mode_rejected(self, tmp_path, mode) -> None:
        with pytest.raises(ValueError):
            sqlite_file_uri(tmp_path / "a.db", mode=mode)  # type: ignore[arg-type]


class TestBackendReadonly:
    @pytest.mark.parametrize("bound", [False, True], ids=["ordinary", "deadline"])
    @pytest.mark.parametrize(("name", "alias"), CASES, ids=IDS)
    def test_reads_intended_not_alias(self, tmp_path, name, alias, bound) -> None:
        container = tmp_path / "box"
        intended = _fixture(container, name, alias, populate_alias=True)
        kwargs = {"deadline": Deadline.after(10)} if bound else {}
        conn = resolve_backend("sqlite").connect_readonly(intended, **kwargs)
        try:
            assert _label(conn) == "literal"
        finally:
            conn.close()

    @pytest.mark.parametrize("bound", [False, True], ids=["ordinary", "deadline"])
    @pytest.mark.parametrize(("name", "alias"), CASES[:6], ids=IDS[:6])
    def test_missing_store_never_creates_alias(self, tmp_path, name, alias, bound) -> None:
        container = tmp_path / "box"
        container.mkdir()
        before = _tree(container)
        kwargs = {"deadline": Deadline.after(10)} if bound else {}
        with pytest.raises(HistoryUnavailable):
            resolve_backend("sqlite").connect_readonly(container / name, **kwargs)
        assert _tree(container) == before


class TestDirectReaders:
    def test_codegraph_open_db(self, tmp_path) -> None:
        container = tmp_path / "box"
        intended = _fixture(container, "index#1?x.db", "index", populate_alias=True)
        conn = _open_db(intended)
        assert conn is not None
        assert _label(conn) == "literal"
        conn.close()

    def test_native_session_index_threads(self, tmp_path) -> None:
        container = tmp_path / "home#1?x%23"
        db = container / ".codex" / "state_1.sqlite"
        db.parent.mkdir(parents=True)
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE threads (id TEXT, rollout_path TEXT, cwd TEXT, source TEXT,"
            " created_at TEXT, updated_at TEXT)"
        )
        conn.commit()
        conn.close()
        before = _tree(tmp_path)
        assert _query_threads_db(db, Path("/nonexistent/cwd")) == []  # usable, no rows
        # A missing decoy-adjacent path is unusable and creates nothing.
        assert _query_threads_db(container / ".codex" / "state_9#.sqlite", Path("/x")) is None
        assert _tree(tmp_path) == before

    def test_export_source_opener(self, tmp_path) -> None:
        container = tmp_path / "box"
        intended = _fixture(container, "src#1?x.db", "src", populate_alias=True)
        conn = _connect_readonly(intended)
        assert _label(conn) == "literal"
        conn.close()


class TestExport:
    def _source(self, container: Path, name: str) -> Path:
        src = container / name
        src.parent.mkdir(parents=True, exist_ok=True)
        resolve_backend("sqlite").ensure_schema(src)
        return src

    def test_special_character_source_and_scratch(self, tmp_path) -> None:
        container = tmp_path / "box"
        src = self._source(container, "history#1?x.db")
        _make_db(container / "history", "decoy")
        src_sha, decoy_sha = _sha(src), _sha(container / "history")
        dest = container / "scratch#1?x.db"
        build_snapshot_db(src, dest, tables=["session"], local_mode=True)
        assert dest.exists()
        assert not (container / "scratch").exists()
        assert _sha(src) == src_sha
        assert _sha(container / "history") == decoy_sha

    def test_relative_file_prefixed_destination_is_literal(self, tmp_path, monkeypatch) -> None:
        container = tmp_path / "box"
        src = self._source(container, "history.db")
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        build_snapshot_db(src, Path("file:dest#name.db"), tables=["session"], local_mode=True)
        assert sorted(os.listdir(cwd)) == ["file:dest#name.db"]


class TestWorkspaceUnion:
    def test_attach_uses_intended_special_character_path(self, tmp_path) -> None:
        container = tmp_path / "box"
        a = container / "repo#1" / "a-history.db"
        b = container / "repo?2" / "b-history.db"
        for p in (a, b):
            p.parent.mkdir(parents=True)
            resolve_backend("sqlite").ensure_schema(p)
        before = _tree(container)
        conn = workspace_quality._open_union([a, b])
        try:
            attached = {
                row[1]: Path(row[2]) for row in conn.execute("PRAGMA database_list") if row[2]
            }
        finally:
            conn.close()
        assert {Path(p).resolve() for p in attached.values()} == {a.resolve(), b.resolve()}
        assert _tree(container) == before
