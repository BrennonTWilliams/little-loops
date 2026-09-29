"""Remote schema migration, open-time policy and ``ll-session migrate`` (FEAT-3535, Step 5).

Runs against ``tests/hrana_stub.py``. Each pending migration is one atomic ``batch``
(``begin immediate``, a stale-read guard, the migration's statements, the version upsert,
conditional ``commit``, ``not ok`` conditional ``rollback``); nothing migrates on open.
"""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from little_loops.session_store import db as db_mod
from little_loops.session_store import remote_schema
from little_loops.session_store import schema as schema_mod
from little_loops.session_store.backend import (
    BackendConfig,
    HistoryOperationError,
    HistoryUnsupported,
    RemoteTarget,
    open_history,
    open_history_readonly,
)
from little_loops.session_store.hrana import HranaClient
from little_loops.session_store.libsql import LibsqlBackend
from tests.hrana_stub import HranaStub

TOKEN = "sentinel-token-DO-NOT-LEAK"
N = len(schema_mod._MIGRATIONS)


@pytest.fixture
def stub() -> Iterator[HranaStub]:
    s = HranaStub(token=TOKEN).start()
    try:
        yield s
    finally:
        s.stop()


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LL_HISTORY_AUTH_TOKEN", TOKEN)
    remote_schema.clear_verification_cache()
    db_mod.clear_backend_config_cache()
    yield
    remote_schema.clear_verification_cache()
    db_mod.clear_backend_config_cache()


def _client(stub: HranaStub) -> HranaClient:
    return HranaClient(stub.url, TOKEN, timeout=10.0)


def _target(stub: HranaStub, project_id: str | None = "acme-api") -> RemoteTarget:
    return RemoteTarget(BackendConfig(provider="libsql", url=stub.url, project_id=project_id))


def _meta(stub: HranaStub, key: str) -> str | None:
    row = stub.db.execute("select value from meta where key = ?", (key,)).fetchone()
    return row[0] if row else None


class TestMigrate:
    def test_fresh_store_is_fully_migrated_and_stamped(self, stub: HranaStub) -> None:
        report = remote_schema.migrate_remote(_client(stub), "acme-api")
        assert (report.before, report.after, report.applied) == (0, N, N)
        assert _meta(stub, "schema_version") == str(N)
        assert _meta(stub, "project_id") == "acme-api"
        assert stub.db.execute("select count(*) from tool_events").fetchone()[0] == 0

    def test_each_migration_is_one_atomic_batch(self, stub: HranaStub) -> None:
        remote_schema.migrate_remote(_client(stub), "acme-api")
        batches = [r for r in stub.requests if "begin immediate" in r["body"].lower()]
        assert len(batches) == N
        for r in batches:
            assert "begin immediate" in r["body"].lower()
            assert '"not"' in r["body"]  # the conditional rollback
        assert not any('"baton": "' in r["body"] for r in stub.requests)

    def test_current_store_is_a_no_op(self, stub: HranaStub) -> None:
        remote_schema.migrate_remote(_client(stub), "acme-api")
        before = len(stub.requests)
        report = remote_schema.migrate_remote(_client(stub), "acme-api")
        assert (report.before, report.after, report.applied) == (N, N, 0)
        assert not any("begin immediate" in r["body"].lower() for r in stub.requests[before:])

    def test_resumes_a_partially_migrated_store(self, stub: HranaStub) -> None:
        remote_schema.migrate_remote(_client(stub), "acme-api", upto=10)
        assert _meta(stub, "schema_version") == "10"
        report = remote_schema.migrate_remote(_client(stub), "acme-api")
        assert (report.before, report.after, report.applied) == (10, N, N - 10)

    def test_concurrent_migrations_leave_one_schema_row(self, stub: HranaStub) -> None:
        errors: list[BaseException] = []

        def run() -> None:
            try:
                remote_schema.migrate_remote(_client(stub), "acme-api")
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert errors == []
        assert (
            stub.db.execute("select count(*) from meta where key = 'schema_version'").fetchone()[0]
            == 1
        )
        assert _meta(stub, "schema_version") == str(N)

    def test_failed_migration_rolls_back_and_leaves_the_version(
        self, stub: HranaStub, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad = list(schema_mod._MIGRATIONS[:3])
        bad[2] = "CREATE TABLE half_done (x INTEGER); INSERT INTO no_such_table VALUES (1)"
        monkeypatch.setattr(schema_mod, "_MIGRATIONS", bad)
        monkeypatch.setattr(remote_schema, "_migrations", lambda: bad)
        with pytest.raises(HistoryOperationError):
            remote_schema.migrate_remote(_client(stub), "acme-api")
        assert _meta(stub, "schema_version") == "2"
        tables = {r[0] for r in stub.db.execute("select name from sqlite_master")}
        assert "half_done" not in tables

    def test_store_ahead_of_the_client_is_refused_and_untouched(self, stub: HranaStub) -> None:
        remote_schema.migrate_remote(_client(stub), "acme-api")
        stub.db.execute("update meta set value = ? where key = 'schema_version'", (str(N + 5),))
        with pytest.raises(HistoryUnsupported, match="upgrade little-loops"):
            remote_schema.migrate_remote(_client(stub), "acme-api")
        assert _meta(stub, "schema_version") == str(N + 5)

    def test_project_id_mismatch_is_refused_and_never_overwritten(self, stub: HranaStub) -> None:
        remote_schema.migrate_remote(_client(stub), "acme-api")
        with pytest.raises(HistoryUnsupported, match="project_id"):
            remote_schema.migrate_remote(_client(stub), "someone-else")
        assert _meta(stub, "project_id") == "acme-api"


class TestOpenPolicy:
    def test_opens_never_migrate(self, stub: HranaStub) -> None:
        conn = LibsqlBackend().connect(_target(stub))
        with pytest.raises(HistoryUnsupported):
            conn.execute("insert into meta values ('x', 'y')")
        assert not any("begin immediate" in r["body"].lower() for r in stub.requests)

    def test_behind_store_refuses_writes_naming_the_migrate_command(self, stub: HranaStub) -> None:
        remote_schema.migrate_remote(_client(stub), "acme-api", upto=5)
        conn = LibsqlBackend().connect(_target(stub))
        with pytest.raises(HistoryUnsupported, match="ll-session migrate") as ei:
            conn.execute("insert into meta values ('x', 'y')")
        assert ei.value.operation == "write"

    def test_behind_store_still_serves_strict_reads(self, stub: HranaStub) -> None:
        remote_schema.migrate_remote(_client(stub), "acme-api", upto=5)
        ro = LibsqlBackend().connect_readonly(_target(stub))
        assert ro.execute("select count(*) from tool_events").fetchone()[0] == 0

    def test_ensure_schema_refuses_a_behind_store(self, stub: HranaStub) -> None:
        remote_schema.migrate_remote(_client(stub), "acme-api", upto=5)
        with pytest.raises(HistoryUnsupported, match="ll-session migrate"):
            LibsqlBackend().ensure_schema(_target(stub))

    def test_ahead_store_serves_reads_and_refuses_writes(self, stub: HranaStub) -> None:
        remote_schema.migrate_remote(_client(stub), "acme-api")
        stub.db.execute("update meta set value = ? where key = 'schema_version'", (str(N + 1),))
        assert (
            LibsqlBackend().connect_readonly(_target(stub)).execute("select 1").fetchone()[0] == 1
        )
        with pytest.raises(HistoryUnsupported, match="upgrade little-loops"):
            LibsqlBackend().connect(_target(stub)).execute("insert into meta values ('x', 'y')")

    def test_current_store_accepts_writes(self, stub: HranaStub) -> None:
        remote_schema.migrate_remote(_client(stub), "acme-api")
        conn = LibsqlBackend().connect(_target(stub))
        conn.execute("insert into meta values ('probe', '1')")
        assert conn.execute("select value from meta where key = 'probe'").fetchone()[0] == "1"

    def test_project_id_mismatch_refuses_even_reads(self, stub: HranaStub) -> None:
        remote_schema.migrate_remote(_client(stub), "acme-api")
        with pytest.raises(HistoryUnsupported, match="project_id"):
            LibsqlBackend().connect_readonly(_target(stub, "other")).execute("select 1")

    def test_project_id_is_required(self, stub: HranaStub) -> None:
        with pytest.raises(HistoryUnsupported, match="project_id"):
            LibsqlBackend().connect(_target(stub, None)).execute("select 1")

    def test_unstamped_migrated_store_refuses_writes(self, stub: HranaStub) -> None:
        remote_schema.migrate_remote(_client(stub), "acme-api")
        stub.db.execute("delete from meta where key = 'project_id'")
        with pytest.raises(HistoryUnsupported, match="ll-session migrate"):
            LibsqlBackend().connect(_target(stub)).execute("insert into meta values ('x', 'y')")

    def test_the_check_runs_once_per_process(self, stub: HranaStub) -> None:
        remote_schema.migrate_remote(_client(stub), "acme-api")
        conn = LibsqlBackend().connect(_target(stub))
        before = len(stub.requests)
        conn.execute("select 1")
        conn.execute("select 2")
        LibsqlBackend().connect(_target(stub)).execute("select 3")
        assert sum("sqlite_master" in r["body"] for r in stub.requests[before:]) == 1

    def test_empty_store_reads_fail_naturally_without_a_migration(self, stub: HranaStub) -> None:
        ro = LibsqlBackend().connect_readonly(_target(stub))
        with pytest.raises(HistoryOperationError):
            ro.execute("select count(*) from tool_events")


class TestMigrateCommand:
    @pytest.fixture
    def project(
        self, stub: HranaStub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> HranaStub:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps(
                {
                    "history": {
                        "backend": {
                            "provider": "libsql",
                            "url_env": "LL_HISTORY_URL",
                            "project_id": "acme-api",
                        }
                    }
                }
            )
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        monkeypatch.setenv("LL_HISTORY_URL", stub.url)
        return stub

    def test_migrates_a_remote_store_and_reports_versions(
        self,
        project: HranaStub,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from little_loops.cli.session import main_session

        monkeypatch.setattr(sys, "argv", ["ll-session", "migrate"])
        assert main_session() == 0
        out = capsys.readouterr().out
        assert f"0 -> {N}" in out
        assert _meta(project, "schema_version") == str(N)

    def test_second_run_is_a_no_op(
        self,
        project: HranaStub,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from little_loops.cli.session import main_session

        monkeypatch.setattr(sys, "argv", ["ll-session", "migrate"])
        main_session()
        capsys.readouterr()
        assert main_session() == 0
        assert "already current" in capsys.readouterr().out

    def test_migrate_does_not_write_telemetry_into_the_store(
        self, project: HranaStub, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.cli.session import main_session

        monkeypatch.setattr(sys, "argv", ["ll-session", "migrate"])
        main_session()
        assert project.db.execute("select count(*) from cli_events").fetchone()[0] == 0

    def test_local_provider_is_a_no_op_that_reports_the_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.cli.session import main_session

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / "h.db"))
        monkeypatch.setattr(sys, "argv", ["ll-session", "migrate"])
        assert main_session() == 0
        assert f"0 -> {N}" in capsys.readouterr().out
        capsys.readouterr()
        assert main_session() == 0
        assert "already current" in capsys.readouterr().out

    def test_mismatched_project_id_exits_nonzero(
        self,
        project: HranaStub,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from little_loops.cli.session import main_session

        remote_schema.migrate_remote(_client(project), "someone-else")
        monkeypatch.setattr(sys, "argv", ["ll-session", "migrate"])
        assert main_session() == 1
        assert "project_id" in capsys.readouterr().err

    def test_open_history_after_migrate_round_trips(
        self, project: HranaStub, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.cli.session import main_session

        monkeypatch.setattr(sys, "argv", ["ll-session", "migrate"])
        main_session()
        conn = open_history()
        conn.execute("insert into meta values ('probe', '1')")
        assert (
            open_history_readonly(ensure=True)
            .execute("select value from meta where key = 'probe'")
            .fetchone()[0]
            == "1"
        )
