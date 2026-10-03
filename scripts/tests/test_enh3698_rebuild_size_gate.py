"""ENH-3698: size-gated automatic rebuild decision, doctor surface, and notice wording."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from little_loops.cli import doctor
from little_loops.session_store import (
    REBUILD_AUTO_MAX_BYTES,
    RebuildDisposition,
    RebuildState,
    ensure_db,
    lifecycle,
    rebuild,
    rebuild_disposition,
)
from little_loops.session_store.targets import BackendConfig, LocalTarget, RemoteTarget


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LL_HISTORY_DB", raising=False)


@pytest.fixture
def stale_db(tmp_path: Path) -> Path:
    path = tmp_path / "history.db"
    ensure_db(path)  # no rebuild stamp -> stale/no_stamp
    return path


def _threshold(monkeypatch: pytest.MonkeyPatch, value: int) -> None:
    monkeypatch.setattr(lifecycle, "REBUILD_AUTO_MAX_BYTES", value)


def _no_stat(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    probed: list[Path] = []

    def _boom(path: Path) -> int | None:
        probed.append(path)
        raise AssertionError("size probe must not run")

    monkeypatch.setattr(lifecycle, "_store_bytes", _boom)
    return probed


class TestConstant:
    def test_calibrated_value_is_bytes(self) -> None:
        assert isinstance(REBUILD_AUTO_MAX_BYTES, int)
        assert 2**20 <= REBUILD_AUTO_MAX_BYTES <= 2**30

    def test_disposition_is_frozen(self, stale_db: Path) -> None:
        disposition = rebuild_disposition(stale_db)
        with pytest.raises(AttributeError):
            disposition.outcome = "pending"  # type: ignore[misc]


class TestDisposition:
    def test_below_threshold_is_auto(self, stale_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        size = stale_db.stat().st_size
        _threshold(monkeypatch, size + 1)
        assert rebuild_disposition(stale_db) == RebuildDisposition(
            RebuildState("stale", "no_stamp"), size, "auto"
        )

    def test_equal_to_threshold_is_auto(
        self, stale_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _threshold(monkeypatch, stale_db.stat().st_size)
        assert rebuild_disposition(stale_db).outcome == "auto"

    def test_above_threshold_is_pending(
        self, stale_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        size = stale_db.stat().st_size
        _threshold(monkeypatch, size - 1)
        got = rebuild_disposition(stale_db)
        assert got.outcome == "pending" and got.size_bytes == size
        assert got.state == RebuildState("stale", "no_stamp")

    def test_threshold_read_at_call_time(
        self, stale_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _threshold(monkeypatch, 1)
        assert rebuild_disposition(stale_db).outcome == "pending"
        _threshold(monkeypatch, 2**40)
        assert rebuild_disposition(stale_db).outcome == "auto"

    def test_wal_counts_toward_size(self, stale_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        main = stale_db.stat().st_size
        _threshold(monkeypatch, main + 10)
        stale_db.with_name(stale_db.name + "-wal").write_bytes(b"x" * 100)
        got = rebuild_disposition(stale_db)
        assert got.outcome == "pending" and got.size_bytes == main + 100

    def test_shm_is_ignored(self, stale_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        main = stale_db.stat().st_size
        _threshold(monkeypatch, main)
        stale_db.with_name(stale_db.name + "-shm").write_bytes(b"x" * 4096)
        got = rebuild_disposition(stale_db)
        assert got.outcome == "auto" and got.size_bytes == main

    def test_missing_wal_counts_zero(self, stale_db: Path) -> None:
        assert not stale_db.with_name(stale_db.name + "-wal").exists()
        assert rebuild_disposition(stale_db).size_bytes == stale_db.stat().st_size

    def test_missing_db_is_size_zero_auto_and_not_created(self, tmp_path: Path) -> None:
        path = tmp_path / "nope.db"
        got = rebuild_disposition(path)
        assert got == RebuildDisposition(RebuildState("stale", "db_missing"), 0, "auto")
        assert not path.exists()
        assert not path.with_name("nope.db-wal").exists()

    def test_main_disappearing_during_probe_counts_zero_but_keeps_wal(
        self, stale_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wal = stale_db.with_name(stale_db.name + "-wal")
        wal.write_bytes(b"x" * 77)
        real_stat = Path.stat

        def _stat(self: Path, *a, **kw):  # type: ignore[no-untyped-def]
            if self == stale_db:
                raise FileNotFoundError(str(self))
            return real_stat(self, *a, **kw)

        monkeypatch.setattr(
            lifecycle, "rebuild_needed", lambda _t: RebuildState("stale", "no_stamp")
        )
        monkeypatch.setattr(Path, "stat", _stat)
        got = rebuild_disposition(stale_db)
        assert got.size_bytes == 77 and got.outcome == "auto"

    @pytest.mark.parametrize("which", ["main", "wal"])
    def test_stat_failure_is_unknown_size_never_small(
        self, stale_db: Path, monkeypatch: pytest.MonkeyPatch, which: str
    ) -> None:
        bad = stale_db if which == "main" else stale_db.with_name(stale_db.name + "-wal")
        real_stat = Path.stat

        def _stat(self: Path, *a, **kw):  # type: ignore[no-untyped-def]
            if self == bad:
                raise PermissionError(13, "denied /secret/path")
            return real_stat(self, *a, **kw)

        monkeypatch.setattr(
            lifecycle, "rebuild_needed", lambda _t: RebuildState("stale", "no_stamp")
        )
        monkeypatch.setattr(Path, "stat", _stat)
        got = rebuild_disposition(stale_db)
        assert got == RebuildDisposition(RebuildState("stale", "no_stamp"), None, "unknown_size")

    def test_current_skips_size_probe(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "cur.db"
        ensure_db(path)
        rebuild(path)
        _no_stat(monkeypatch)
        got = rebuild_disposition(path)
        assert got.state.status == "current" and got.outcome == "none" and got.size_bytes is None

    def test_unknown_skips_size_probe(
        self, stale_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            lifecycle, "rebuild_needed", lambda _t: RebuildState("unknown", "read_error")
        )
        _no_stat(monkeypatch)
        got = rebuild_disposition(stale_db)
        assert got == RebuildDisposition(RebuildState("unknown", "read_error"), None, "none")

    def test_resolution_failure_is_read_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(_db):  # type: ignore[no-untyped-def]
            raise RuntimeError("token=abc123")

        monkeypatch.setattr(lifecycle, "resolve_history_target", _boom)
        got = rebuild_disposition("x.db")
        assert got == RebuildDisposition(RebuildState("unknown", "read_error"), None, "none")

    def test_remote_target_never_stats_or_queries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        remote = RemoteTarget(BackendConfig(provider="libsql", url="https://u:tok@h.example"))
        _no_stat(monkeypatch)
        got = rebuild_disposition(remote)
        assert got == RebuildDisposition(RebuildState("unknown", "remote"), None, "none")

    def test_typed_local_target_is_used_as_is(
        self, stale_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _threshold(monkeypatch, 0)
        got = rebuild_disposition(LocalTarget(stale_db))
        assert got.outcome == "pending"

    def test_env_override_is_the_measured_store(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = tmp_path / "elsewhere.db"
        ensure_db(real)
        monkeypatch.setenv("LL_HISTORY_DB", str(real))
        _threshold(monkeypatch, real.stat().st_size - 1)
        # The argument is a missing default-shaped file; the env store is what is measured.
        got = rebuild_disposition(tmp_path / ".ll" / "history.db")
        assert got.size_bytes == real.stat().st_size and got.outcome == "pending"

    def test_configured_path_differs_from_missing_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"history": {"db_path": ".ll/configured.db"}})
        )
        configured = tmp_path / ".ll" / "configured.db"
        ensure_db(configured)
        assert not (tmp_path / ".ll" / "history.db").exists()
        _threshold(monkeypatch, configured.stat().st_size - 1)
        got = rebuild_disposition()
        assert got.state.reason != "db_missing"
        assert got.outcome == "pending" and got.size_bytes == configured.stat().st_size

    def test_report_only_no_migration(self, stale_db: Path) -> None:
        before = stale_db.read_bytes()
        rebuild_disposition(stale_db)
        assert stale_db.read_bytes() == before

    def test_real_wal_growth_is_visible(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sqlite3

        path = tmp_path / "wal.db"
        ensure_db(path)
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA wal_autocheckpoint=0")
            conn.execute("CREATE TABLE IF NOT EXISTS big(x BLOB)")
            conn.execute("INSERT INTO big VALUES (?)", (os.urandom(1 << 20),))
            conn.commit()
            main = path.stat().st_size
            _threshold(monkeypatch, main + 1024)
            got = rebuild_disposition(path)
            assert got.size_bytes is not None and got.size_bytes > main
            assert got.outcome == "pending"
        finally:
            conn.close()


class TestNotice:
    def test_mixed_vs_incomplete_wording(self) -> None:
        mixed = lifecycle.rebuild_pending_notice(RebuildState("stale", "derive_mismatch"), False)
        incomplete = lifecycle.rebuild_pending_notice(RebuildState("stale", "no_stamp"), False)
        assert "mixed" in mixed and "incomplete" not in mixed
        assert "incomplete" in incomplete and "mixed" not in incomplete
        for text in (mixed, incomplete):
            assert text.startswith("[little-loops] ") and "\n" not in text
            assert "ll-session rebuild" in text and "write lock" in text
            assert "clears leaf/condensed summaries" in text
            assert "retention" not in text and "irreversible" not in text

    def test_compaction_wording(self) -> None:
        state = RebuildState("stale", "no_stamp")
        on = lifecycle.rebuild_pending_notice(state, True)
        off = lifecycle.rebuild_pending_notice(state, False)
        unknown = lifecycle.rebuild_pending_notice(state, None)
        assert "is enabled)" in on and "LLM" in on
        assert "disabled" in off and "LLM" not in off
        assert "if history.compaction is enabled" in unknown

    def test_compaction_enabled_reads_raw_json_only(self, tmp_path: Path) -> None:
        cfg = tmp_path / "ll-config.json"
        assert lifecycle.rebuild_compaction_enabled(None) is None
        assert lifecycle.rebuild_compaction_enabled(tmp_path / "missing.json") is None
        cfg.write_text("{not json")
        assert lifecycle.rebuild_compaction_enabled(cfg) is None
        cfg.write_text(json.dumps({"history": {"compaction": {"enabled": True}}}))
        assert lifecycle.rebuild_compaction_enabled(cfg) is True
        cfg.write_text(json.dumps({}))
        assert lifecycle.rebuild_compaction_enabled(cfg) is False
        cfg.write_text(json.dumps({"history": []}))
        assert lifecycle.rebuild_compaction_enabled(cfg) is None


class TestDoctor:
    def _patch(self, monkeypatch: pytest.MonkeyPatch, state: RebuildState, size, outcome) -> None:
        # doctor imports the name from the package at call time
        import little_loops.session_store as pkg

        monkeypatch.setattr(
            pkg, "rebuild_disposition", lambda _db=None: RebuildDisposition(state, size, outcome)
        )

    @pytest.mark.parametrize(
        ("state", "size", "outcome", "status"),
        [
            (RebuildState("current", "derive_match"), None, "none", "full"),
            (RebuildState("stale", "no_stamp"), 10, "auto", "partial"),
            (RebuildState("stale", "derive_mismatch"), 10**12, "pending", "partial"),
            (RebuildState("stale", "db_missing"), 0, "auto", "unsupported"),
            (RebuildState("unknown", "read_error"), None, "none", "unknown"),
            (RebuildState("stale", "no_stamp"), None, "unknown_size", "unknown"),
            (RebuildState("unknown", "remote"), None, "none", "unsupported"),
        ],
    )
    def test_status_mapping(
        self, monkeypatch: pytest.MonkeyPatch, state: RebuildState, size, outcome, status: str
    ) -> None:
        self._patch(monkeypatch, state, size, outcome)
        data = doctor._rebuild_pending_data()
        assert data["status"] == status and data["severity"] == "informational"
        assert data["state"] == state.status and data["reason"] == state.reason
        assert data["size_bytes"] == size and data["outcome"] == outcome
        assert data["threshold_bytes"] == lifecycle.REBUILD_AUTO_MAX_BYTES
        assert data["note"]
        (result,) = doctor._rebuild_pending_check()
        assert (result.name, result.status, result.severity) == (
            "rebuild_pending",
            status,
            "informational",
        )
        assert result.note == data["note"]

    def test_pending_and_unknown_size_wording(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch(monkeypatch, RebuildState("stale", "derive_mismatch"), 10**12, "pending")
        note = doctor._rebuild_pending_data()["note"]
        assert "ll-session rebuild" in note and "mixed" in note
        self._patch(monkeypatch, RebuildState("stale", "no_stamp"), None, "unknown_size")
        data = doctor._rebuild_pending_data()
        assert "unknown_size" in data["note"] and data["reason"] == "no_stamp"

    def test_text_section(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._patch(monkeypatch, RebuildState("stale", "no_stamp"), 123, "auto")
        doctor._print_rebuild_pending_section()
        out = capsys.readouterr().out
        assert "Rebuild Pending" in out and "123 bytes" in out

    def test_registered_and_exit_code_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert doctor._rebuild_pending_check in doctor._CHECKS
        self._patch(monkeypatch, RebuildState("unknown", "remote"), None, "none")
        results = doctor._rebuild_pending_check()
        assert doctor._exit_code_for(results) == 0

    def test_json_key_and_no_creation(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        data = doctor._rebuild_pending_data()
        assert data["reason"] == "db_missing" and data["status"] == "unsupported"
        assert not (tmp_path / ".ll" / "history.db").exists()

    def test_remote_no_token_leak(self, monkeypatch: pytest.MonkeyPatch) -> None:
        secret = "s3cr3t-token-value"
        monkeypatch.setenv("LL_HISTORY_AUTH_TOKEN", secret)
        remote = RemoteTarget(BackendConfig(provider="libsql", url=f"https://u:{secret}@h.example"))
        monkeypatch.setattr(lifecycle, "resolve_history_target", lambda _db=None: remote)
        data = doctor._rebuild_pending_data()
        assert data["status"] == "unsupported" and data["reason"] == "remote"
        assert secret not in json.dumps(data)
