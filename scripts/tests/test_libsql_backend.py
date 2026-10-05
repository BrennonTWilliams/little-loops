"""Tests for the remote libSQL history backend (FEAT-3535, Steps 2-4).

Backend, config resolution, provider selection through the chokepoint and the
``schema.connect`` seam, all against ``tests/hrana_stub.py``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from little_loops.session_store import db as db_mod
from little_loops.session_store import remote_schema
from little_loops.session_store.backend import (
    Backend,
    BackendConfig,
    HistoryBackendNotLocal,
    HistoryConnection,
    HistoryUnsupported,
    LocalTarget,
    RemoteTarget,
    SqliteBackend,
    _resolve_once,
    connect_readonly,
    open_history,
    open_history_readonly,
    resolve_backend,
)
from little_loops.session_store.hrana import HranaClient
from little_loops.session_store.libsql import LibsqlBackend
from tests.hrana_stub import HranaStub

TOKEN = "sentinel-token-DO-NOT-LEAK"


@pytest.fixture
def stub() -> Iterator[HranaStub]:
    """A stub whose schema is already migrated and stamped for ``acme-api``.

    Opens never migrate (open-time policy), so backend behavior is tested against a
    current store; migration and the behind/ahead policy have their own tests.
    """
    remote_schema.clear_verification_cache()
    s = HranaStub(token=TOKEN).start()
    try:
        remote_schema.migrate_remote(HranaClient(s.url, TOKEN), "acme-api")
        yield s
    finally:
        s.stop()
        remote_schema.clear_verification_cache()


def _write_config(root: Path, backend: dict | None, local_md: str | None = None) -> None:
    (root / ".ll").mkdir(exist_ok=True)
    cfg: dict = {"history": {}}
    if backend is not None:
        cfg["history"]["backend"] = backend
    (root / ".ll" / "ll-config.json").write_text(json.dumps(cfg))
    if local_md is not None:
        (root / ".ll" / "ll.local.md").write_text(local_md)


@pytest.fixture
def remote(stub: HranaStub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> HranaStub:
    """A project configured for ``provider: libsql`` pointing at the stub."""
    _write_config(
        tmp_path,
        {
            "provider": "libsql",
            "url_env": "LL_HISTORY_URL",
            "auth_token_env": "LL_HISTORY_AUTH_TOKEN",
            "project_id": "acme-api",
        },
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LL_HISTORY_DB", raising=False)
    monkeypatch.setenv("LL_HISTORY_URL", stub.url)
    monkeypatch.setenv("LL_HISTORY_AUTH_TOKEN", TOKEN)
    db_mod.clear_backend_config_cache()
    yield stub
    db_mod.clear_backend_config_cache()


def _target(stub: HranaStub) -> RemoteTarget:
    return RemoteTarget(
        BackendConfig(provider="libsql", url=stub.url, project_id="acme-api"),
    )


@pytest.fixture(autouse=True)
def _token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LL_HISTORY_AUTH_TOKEN", TOKEN)


class TestConfigResolution:
    def test_unset_backend_is_sqlite_and_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, None)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        db_mod.clear_backend_config_cache()
        assert isinstance(_resolve_once(None), LocalTarget)
        assert db_mod.resolve_history_db() == tmp_path / ".ll" / "history.db"

    def test_explicit_sqlite_provider_is_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, {"provider": "sqlite"})
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        db_mod.clear_backend_config_cache()
        assert isinstance(_resolve_once(None), LocalTarget)

    @pytest.mark.parametrize("base", [{}, {"history": "scalar"}])
    def test_local_null_under_absent_backend_ancestor_is_dropped(
        self, tmp_path: Path, base: dict
    ) -> None:
        """FEAT-3681: the raw block no longer carries a null under a new mapping."""
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(json.dumps(base))
        (tmp_path / ".ll" / "ll.local.md").write_text(
            "---\nhistory:\n  backend:\n    provider: libsql\n    url: null\n---\n"
        )
        assert db_mod._read_backend_block(tmp_path) == {"provider": "libsql"}


    def test_libsql_default_shaped_selects_the_remote_target(self, remote: HranaStub) -> None:
        target = _resolve_once(None)
        assert isinstance(target, RemoteTarget)
        assert target.provider == "libsql"
        assert target.config.project_id == "acme-api"
        assert _resolve_once(Path(".ll/history.db")) == target

    def test_explicit_non_default_path_stays_a_local_target(
        self, remote: HranaStub, tmp_path: Path
    ) -> None:
        explicit = tmp_path / "scratch" / "x.db"
        assert _resolve_once(explicit) == LocalTarget(explicit)

    def test_history_db_env_stays_a_local_target(
        self, remote: HranaStub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / "local.db"))
        assert _resolve_once(None) == LocalTarget(tmp_path / "local.db")

    def test_resolve_history_db_raises_for_the_remote_target(self, remote: HranaStub) -> None:
        with pytest.raises(HistoryBackendNotLocal):
            db_mod.resolve_history_db()

    def test_local_md_frontmatter_overrides_the_endpoint(
        self, stub: HranaStub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(
            tmp_path,
            {"provider": "libsql", "url_env": "LL_HISTORY_URL", "project_id": "p"},
            local_md=f"---\nhistory:\n  backend:\n    url: {stub.url}\n    url_env: null\n---\n",
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        monkeypatch.delenv("LL_HISTORY_URL", raising=False)
        db_mod.clear_backend_config_cache()
        target = _resolve_once(None)
        assert isinstance(target, RemoteTarget)
        assert target.config.endpoint() == stub.url

    def test_malformed_config_means_sqlite_with_one_warning(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text("{not json")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        db_mod.clear_backend_config_cache()
        with caplog.at_level("WARNING"):
            assert isinstance(_resolve_once(None), LocalTarget)
            assert isinstance(_resolve_once(None), LocalTarget)
        assert sum("history.backend" in r.message for r in caplog.records) <= 1

    def test_config_is_cached_per_process(
        self, remote: HranaStub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = []
        real = json.loads
        monkeypatch.setattr(json, "loads", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
        _resolve_once(None)
        first = len(calls)
        _resolve_once(None)
        assert len(calls) == first

    def test_endpoint_and_token_come_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = BackendConfig(provider="libsql", url_env="MY_URL", auth_token_env="MY_TOKEN")
        monkeypatch.setenv("MY_URL", "libsql://x.turso.io")
        monkeypatch.setenv("MY_TOKEN", "tok")
        assert cfg.endpoint() == "libsql://x.turso.io"
        assert cfg.auth_token() == "tok"
        monkeypatch.delenv("MY_URL")
        from little_loops.session_store.backend import HistoryUnavailable

        with pytest.raises(HistoryUnavailable, match="MY_URL"):
            cfg.endpoint()

    def test_config_repr_holds_no_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_HISTORY_AUTH_TOKEN", TOKEN)
        cfg = BackendConfig(provider="libsql", url="http://x", project_id="p")
        assert TOKEN not in repr(cfg)


class TestBackendRegistry:
    def test_libsql_resolves(self) -> None:
        backend = resolve_backend("libsql")
        assert isinstance(backend, LibsqlBackend)
        assert isinstance(backend, Backend)
        assert backend.provider == "libsql"

    def test_supports_nothing_sqlite_specific(self) -> None:
        backend = LibsqlBackend()
        assert not any(
            backend.supports(c)
            for c in ("attach", "vacuum", "create_function", "wal", "snapshot_export")
        )

    def test_sqlite_rejects_a_remote_target_and_libsql_a_local_one(
        self, stub: HranaStub, tmp_path: Path
    ) -> None:
        with pytest.raises(HistoryUnsupported):
            SqliteBackend().connect(_target(stub))
        with pytest.raises(HistoryUnsupported):
            LibsqlBackend().connect(LocalTarget(tmp_path / "x.db"))
        with pytest.raises(HistoryUnsupported):
            LibsqlBackend().connect(tmp_path / "x.db")


class TestConnection:
    @pytest.fixture
    def conn(self, stub: HranaStub):
        c = LibsqlBackend().connect(_target(stub))
        c.execute("create table t (id integer primary key, v text, n real)")
        yield c
        c.close()

    def test_is_a_history_connection(self, conn) -> None:
        assert isinstance(conn, HistoryConnection)

    def test_no_wal_pragma_is_sent(self, stub: HranaStub, conn) -> None:
        assert not any("pragma" in r["body"].lower() for r in stub.requests)

    def test_row_supports_index_name_keys_and_dict(self, conn) -> None:
        conn.execute("insert into t values (?, ?, ?)", (1, "a", 2.5))
        row = conn.execute("select id, v, n from t").fetchone()
        assert row[0] == 1 and row["v"] == "a" and row[2] == 2.5
        assert row.keys() == ["id", "v", "n"]
        assert dict(row) == {"id": 1, "v": "a", "n": 2.5}

    def test_cursor_surface(self, conn) -> None:
        cur = conn.execute("insert into t(v) values ('x'), ('y')")
        assert cur.rowcount == 2 and cur.lastrowid == 2
        sel = conn.execute("select id, v from t order by id")
        assert [d[0] for d in sel.description] == ["id", "v"]
        assert len(sel.fetchmany(1)) == 1
        assert [r["v"] for r in sel.fetchall()] == ["y"]
        assert [r["id"] for r in conn.execute("select id from t order by id")] == [1, 2]
        assert conn.execute("select id from t where id = 99").fetchone() is None

    def test_executemany_is_atomic(self, conn) -> None:
        conn.executemany("insert into t(id, v) values (?, ?)", [(1, "a"), (2, "b")])
        from little_loops.session_store.backend import HistoryIntegrityError

        with pytest.raises(HistoryIntegrityError):
            conn.executemany("insert into t(id, v) values (?, ?)", [(3, "c"), (1, "dup")])
        assert conn.execute("select count(*) from t").fetchone()[0] == 2

    def test_commit_rollback_close_are_safe_no_ops(self, conn) -> None:
        assert conn.in_transaction is False
        conn.commit()
        conn.rollback()

    def test_check_same_thread_false_is_accepted(self, stub: HranaStub) -> None:
        LibsqlBackend().connect(_target(stub), check_same_thread=False).close()


class TestReadOnly:
    def test_reads_work_and_writes_are_refused_client_side(self, stub: HranaStub) -> None:
        LibsqlBackend().connect(_target(stub)).execute("create table t (v text)")
        ro = LibsqlBackend().connect_readonly(_target(stub))
        assert ro.execute("select count(*) from t").fetchone()[0] == 0
        before = len(stub.requests)
        with pytest.raises(HistoryUnsupported) as ei:
            ro.execute("insert into t values ('x')")
        assert ei.value.operation == "write"
        assert len(stub.requests) == before  # refused before any network call


class TestEntryPointsSelectTheProvider:
    def test_open_history_returns_a_remote_connection(self, remote: HranaStub) -> None:
        conn = open_history()
        conn.execute("create table t (v text)")
        conn.execute("insert into t values ('x')")
        assert conn.execute("select v from t").fetchone()["v"] == "x"

    def test_open_history_readonly_and_connect_readonly(self, remote: HranaStub) -> None:
        open_history().execute("create table t (v text)")
        assert open_history_readonly().execute("select count(*) from t").fetchone()[0] == 0
        assert connect_readonly().execute("select count(*) from t").fetchone()[0] == 0

    def test_explicit_local_path_still_opens_sqlite(
        self, remote: HranaStub, tmp_path: Path
    ) -> None:
        conn = open_history(tmp_path / "local.db")
        try:
            assert conn.execute("SELECT 1").fetchone()[0] == 1
        finally:
            conn.close()
        assert (tmp_path / "local.db").exists()


class TestSchemaSeam:
    def test_connect_with_a_default_shaped_path_reaches_the_remote_store(
        self, remote: HranaStub
    ) -> None:
        from little_loops.session_store.schema import connect

        conn = connect(Path.cwd() / ".ll" / "history.db")
        assert conn.execute("select 1").fetchone()[0] == 1
        assert any(r["path"] == "/v3/pipeline" for r in remote.requests)

    def test_ensure_db_refuses_a_remote_target_before_any_mutation(self, remote: HranaStub) -> None:
        from little_loops.session_store.schema import ensure_db

        before = len(remote.requests)
        with pytest.raises(HistoryBackendNotLocal):
            ensure_db(Path.cwd() / ".ll" / "history.db")
        assert len(remote.requests) == before
