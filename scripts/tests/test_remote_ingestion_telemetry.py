"""Remote ingestion, env relay and the telemetry latency budget (FEAT-3535, Steps 7-8).

Ingestion: a per-machine watermark (a global key would let one machine's progress skip
another's older transcripts), batched inserts, and dedup on ``(session_id, line_no)`` for a
copied session file. Telemetry: paths that must never stall a 5s hook use
``telemetry_timeout_ms``, an unreachable marker (TTL 60s) and a file-backed verification
cache (TTL 300s); explicit reads ignore both. Every file is under ``.ll/*.lock`` so the
existing gitignore glob covers it, and none holds a token.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from little_loops.session_store import db as db_mod
from little_loops.session_store import lifecycle, remote_schema, remote_telemetry
from little_loops.session_store.backend import (
    HistoryOperationError,
    HistorySuppressed,
    HistoryUnavailable,
    open_history,
)
from little_loops.session_store.hrana import HranaClient
from little_loops.session_store.libsql import machine_id
from little_loops.session_store.schema import connect
from little_loops.session_store.sessions import handles_from_paths
from tests.hrana_stub import HranaStub

TOKEN = "sentinel-token-DO-NOT-LEAK"


def _write_config(root: Path, timeout_ms: int = 1500) -> None:
    (root / ".ll").mkdir(exist_ok=True)
    (root / ".ll" / "ll-config.json").write_text(
        json.dumps(
            {
                "history": {
                    "backend": {
                        "provider": "libsql",
                        "url_env": "LL_HISTORY_URL",
                        "project_id": "acme-api",
                        "telemetry_timeout_ms": timeout_ms,
                    }
                }
            }
        )
    )


@pytest.fixture
def remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[HranaStub]:
    stub = HranaStub(token=TOKEN).start()
    monkeypatch.setenv("LL_HISTORY_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("LL_HISTORY_URL", stub.url)
    monkeypatch.delenv("LL_HISTORY_DB", raising=False)
    monkeypatch.setenv("LL_MACHINE_ID", "machine-a")
    _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    remote_schema.clear_verification_cache()
    remote_telemetry.reset_for_tests()
    db_mod.clear_backend_config_cache()
    remote_schema.migrate_remote(HranaClient(stub.url, TOKEN), "acme-api")
    try:
        yield stub
    finally:
        stub.stop()
        remote_schema.clear_verification_cache()
        remote_telemetry.reset_for_tests()
        db_mod.clear_backend_config_cache()


def _tconnect():
    """``schema.connect`` the way the event writers call it: inside the telemetry scope."""
    with remote_telemetry.telemetry_scope():
        return connect(Path.cwd() / ".ll" / "history.db")


def _transcript(directory: Path, name: str, session: str, n: int = 3) -> Path:
    path = directory / f"{name}.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": f"2026-01-01T00:00:{i:02d}Z",
                    "sessionId": session,
                    "message": {"role": "user", "content": f"hello {i}"},
                }
            )
            for i in range(n)
        )
        + "\n"
    )
    return path


def _meta(stub: HranaStub, key: str) -> str | None:
    row = stub.db.execute("select value from meta where key = ?", (key,)).fetchone()
    return row[0] if row else None


class TestMachineId:
    def test_env_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_MACHINE_ID", "from-env")
        assert machine_id() == "from-env"

    def test_generated_once_and_stable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LL_MACHINE_ID", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        first = machine_id()
        assert first == machine_id() and len(first) >= 16
        assert (tmp_path / ".ll" / "machine-id").read_text().strip() == first

    def test_unwritable_home_still_returns_an_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LL_MACHINE_ID", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "missing" / "deeper")
        monkeypatch.setattr(os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(OSError("ro")))
        assert machine_id()


class TestRemoteIngestion:
    def test_watermark_is_per_machine_and_the_global_key_is_untouched(
        self, remote: HranaStub, tmp_path: Path
    ) -> None:
        f = _transcript(tmp_path, "s1", "s1")
        lifecycle.backfill_raw_events(handles=handles_from_paths([f], "claude-code"))
        assert _meta(remote, "last_raw_event_ts:machine-a") is not None
        assert _meta(remote, "last_raw_event_ts") is None

    def test_another_machines_progress_does_not_skip_older_transcripts(
        self, remote: HranaStub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        older = _transcript(tmp_path, "old", "old-session")
        os.utime(older, (1_000, 1_000))
        # Machine A has already advanced its watermark to "now".
        lifecycle.backfill_raw_events(handles=[])
        assert _meta(remote, "last_raw_event_ts:machine-a") is not None
        # Machine B has never ingested: its own (absent) watermark means "everything".
        monkeypatch.setenv("LL_MACHINE_ID", "machine-b")
        lifecycle.backfill_incremental(handles=handles_from_paths([older], "claude-code"))
        n = remote.db.execute(
            "select count(*) from raw_events where session_id = 'old-session'"
        ).fetchone()[0]
        assert n == 3

    def test_sqlite_keeps_the_global_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = tmp_path / "local.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(db))
        f = _transcript(tmp_path, "s1", "s1")
        lifecycle.backfill_raw_events(db, handles=handles_from_paths([f], "claude-code"))
        import sqlite3

        with sqlite3.connect(db) as conn:
            keys = {r[0] for r in conn.execute("select key from meta")}
        assert "last_raw_event_ts" in keys
        assert not any(k.startswith("last_raw_event_ts:") for k in keys)

    def test_inserts_are_batched_not_one_round_trip_per_event(
        self, remote: HranaStub, tmp_path: Path
    ) -> None:
        f = _transcript(tmp_path, "big", "big", n=450)
        before = len(remote.requests)
        assert lifecycle.backfill_raw_events(handles=handles_from_paths([f], "claude-code")) == 450
        assert len(remote.requests) - before < 20

    def test_a_copied_session_file_is_not_double_ingested(
        self, remote: HranaStub, tmp_path: Path
    ) -> None:
        a = _transcript(tmp_path, "sess", "sess")
        other = tmp_path / "copy"
        other.mkdir()
        b = _transcript(other, "sess", "sess")
        lifecycle.backfill_raw_events(handles=handles_from_paths([a], "claude-code"))
        added = lifecycle.backfill_raw_events(handles=handles_from_paths([b], "claude-code"))
        assert added == 0
        assert remote.db.execute("select count(*) from raw_events").fetchone()[0] == 3

    def test_reingesting_the_same_file_is_idempotent(
        self, remote: HranaStub, tmp_path: Path
    ) -> None:
        f = _transcript(tmp_path, "s1", "s1")
        for _ in range(2):
            lifecycle.backfill_raw_events(handles=handles_from_paths([f], "claude-code"))
        assert remote.db.execute("select count(*) from raw_events").fetchone()[0] == 3


class TestEnvRelay:
    def test_remote_target_exports_nothing_and_does_not_raise(
        self, remote: HranaStub, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.worktree_utils import export_history_db_env

        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        export_history_db_env()
        assert "LL_HISTORY_DB" not in os.environ

    def test_an_existing_local_override_is_left_alone(
        self, remote: HranaStub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.worktree_utils import export_history_db_env

        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / "mine.db"))
        export_history_db_env()
        assert os.environ["LL_HISTORY_DB"] == str(tmp_path / "mine.db")

    def test_local_provider_still_exports_the_resolved_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.worktree_utils import export_history_db_env

        (tmp_path / ".ll").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        db_mod.clear_backend_config_cache()
        export_history_db_env()
        assert os.environ["LL_HISTORY_DB"].endswith(".ll/history.db")
        monkeypatch.delenv("LL_HISTORY_DB")


class TestTelemetryBudget:
    def test_a_slow_endpoint_is_cut_off_at_the_telemetry_timeout(
        self, remote: HranaStub, tmp_path: Path
    ) -> None:
        _write_config(tmp_path, timeout_ms=200)
        db_mod.clear_backend_config_cache()
        remote.delay = 1.5
        t0 = time.monotonic()
        with pytest.raises(HistoryUnavailable):
            _tconnect().execute("insert into meta values ('t', '1')")
        assert time.monotonic() - t0 < 1.0

    def test_explicit_opens_use_the_longer_bound(self, remote: HranaStub, tmp_path: Path) -> None:
        _write_config(tmp_path, timeout_ms=200)
        db_mod.clear_backend_config_cache()
        remote.delay = 0.6
        assert open_history().execute("select 1").fetchone()[0] == 1

    def test_a_failure_writes_an_unreachable_marker_and_later_writes_skip(
        self, remote: HranaStub, tmp_path: Path
    ) -> None:
        _write_config(tmp_path, timeout_ms=200)
        db_mod.clear_backend_config_cache()
        remote.delay = 1.0
        with pytest.raises(HistoryUnavailable):
            _tconnect().execute("insert into meta values ('t', '1')")
        markers = list((tmp_path / ".ll").glob("libsql-*.unreachable.lock"))
        assert len(markers) == 1
        remote.delay = 0.0
        before = len(remote.requests)
        with pytest.raises(HistorySuppressed):
            _tconnect().execute("insert into meta values ('t', '2')")
        assert len(remote.requests) == before  # no network attempt

    def test_explicit_reads_ignore_the_marker(self, remote: HranaStub, tmp_path: Path) -> None:
        remote_telemetry.mark_unreachable(remote.url)
        assert open_history().execute("select 1").fetchone()[0] == 1

    def test_the_marker_expires_after_its_ttl(
        self, remote: HranaStub, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        remote_telemetry.mark_unreachable(remote.url)
        assert remote_telemetry.unreachable_active(remote.url)
        now = time.time()
        monkeypatch.setattr(remote_telemetry, "_now", lambda: now + 61)
        assert not remote_telemetry.unreachable_active(remote.url)

    def test_state_files_hold_no_token_and_match_the_gitignore_glob(
        self, remote: HranaStub, tmp_path: Path
    ) -> None:
        _tconnect().execute("insert into meta values ('a', '1')")
        remote_telemetry.mark_unreachable(remote.url)
        files = [p for p in (tmp_path / ".ll").glob("libsql-*") if p.is_file()]
        assert files and all(p.name.endswith(".lock") for p in files)
        for p in files:
            assert TOKEN not in p.read_text()

    def test_a_warm_file_cache_skips_the_verification_round_trip(self, remote: HranaStub) -> None:
        _tconnect().execute("insert into meta values ('a', '1')")
        remote_schema.clear_verification_cache()  # a new hook process: in-process cache is empty
        before = len(remote.requests)
        _tconnect().execute("insert into meta values ('b', '1')")
        new = remote.requests[before:]
        assert len(new) == 1 and "sqlite_master" not in new[0]["body"]

    def test_a_schema_failure_invalidates_the_file_cache(
        self, remote: HranaStub, tmp_path: Path
    ) -> None:
        conn = _tconnect()
        conn.execute("insert into meta values ('a', '1')")
        assert list((tmp_path / ".ll").glob("libsql-*.verified.lock"))
        with pytest.raises(HistoryOperationError):
            conn.execute("insert into no_such_table values (1)")
        assert not list((tmp_path / ".ll").glob("libsql-*.verified.lock"))

    def test_explicit_opens_ignore_the_file_cache(self, remote: HranaStub) -> None:
        _tconnect().execute("insert into meta values ('a', '1')")
        remote_schema.clear_verification_cache()
        before = len(remote.requests)
        open_history().execute("select 1")
        assert any("sqlite_master" in r["body"] for r in remote.requests[before:])

    def test_a_stale_file_cache_entry_is_ignored(
        self, remote: HranaStub, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _tconnect().execute("insert into meta values ('a', '1')")
        remote_schema.clear_verification_cache()
        now = time.time()
        monkeypatch.setattr(remote_telemetry, "_now", lambda: now + 301)
        before = len(remote.requests)
        _tconnect().execute("insert into meta values ('b', '1')")
        assert any("sqlite_master" in r["body"] for r in remote.requests[before:])


class TestBestEffortNeverAborts:
    def test_cli_event_context_body_runs_when_the_endpoint_is_down_and_warns_once(
        self, remote: HranaStub, caplog: pytest.LogCaptureFixture
    ) -> None:
        from little_loops.session_store import cli_event_context

        remote.stop()
        ran = []
        with caplog.at_level(logging.DEBUG):
            for _ in range(3):
                with cli_event_context(".ll/history.db", "ll-x", []):
                    ran.append(1)
        assert ran == [1, 1, 1]
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) <= 1
        assert not any(TOKEN in r.getMessage() for r in caplog.records)

    def test_a_behind_store_warns_once_and_skips_telemetry(
        self, remote: HranaStub, caplog: pytest.LogCaptureFixture
    ) -> None:
        remote.db.execute("update meta set value = '5' where key = 'schema_version'")
        remote_schema.clear_verification_cache()
        remote_telemetry.reset_for_tests()
        with caplog.at_level(logging.DEBUG):
            for _ in range(3):
                with pytest.raises(HistoryUnavailable):
                    _tconnect().execute("insert into meta values ('a', '1')")
        behind = [
            r
            for r in caplog.records
            if r.levelno >= logging.WARNING and "migrate" in r.getMessage()
        ]
        assert len(behind) == 1
