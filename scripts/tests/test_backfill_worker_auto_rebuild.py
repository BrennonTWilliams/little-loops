"""ENH-3698: the worker's ``--auto-rebuild`` ingests first, then rechecks before replay."""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.cli import backfill_worker
from little_loops.session_store import RebuildDisposition, RebuildState

_AUTO = RebuildDisposition(RebuildState("stale", "no_stamp"), 10, "auto")
_PENDING = RebuildDisposition(RebuildState("stale", "no_stamp"), 10**12, "pending")
_CURRENT = RebuildDisposition(RebuildState("current", "derive_match"), None, "none")
_UNSIZED = RebuildDisposition(RebuildState("stale", "no_stamp"), None, "unknown_size")


class _Recorder:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, dispositions: list[RebuildDisposition]):
        self.calls: list[tuple] = []
        self._queue = list(dispositions)
        import little_loops.session_store as pkg

        def _incremental(db, **kw):  # type: ignore[no-untyped-def]
            self.calls.append(("ingest", kw.get("also_rebuild")))
            return {"raw_events": 0}

        def _disposition(db=None):  # type: ignore[no-untyped-def]
            self.calls.append(("disposition",))
            return self._queue.pop(0)

        def _rebuild(db, config=None):  # type: ignore[no-untyped-def]
            self.calls.append(("rebuild", config))
            return {}

        monkeypatch.setattr(pkg, "backfill_incremental", _incremental)
        monkeypatch.setattr(pkg, "rebuild_disposition", _disposition)
        monkeypatch.setattr(pkg, "rebuild", _rebuild)


@pytest.fixture
def argv(tmp_path: Path) -> list[str]:
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "s.jsonl").write_text("{}\n")
    return [str(tmp_path / "h.db"), str(folder)]


def test_ingest_commits_before_the_final_decision_then_replays_once(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = _Recorder(monkeypatch, [_AUTO])
    assert backfill_worker.main([*argv, "--auto-rebuild"]) == 0
    assert rec.calls == [("ingest", False), ("disposition",), ("rebuild", None)]


def test_backlog_over_limit_skips_replay(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _Recorder(monkeypatch, [_PENDING])
    assert backfill_worker.main([*argv, "--auto-rebuild"]) == 0
    assert rec.calls == [("ingest", False), ("disposition",)]


@pytest.mark.parametrize("final", [_CURRENT, _UNSIZED])
def test_now_current_or_unreadable_skips_replay(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, final: RebuildDisposition
) -> None:
    rec = _Recorder(monkeypatch, [final])
    assert backfill_worker.main([*argv, "--auto-rebuild"]) == 0
    assert ("rebuild", None) not in rec.calls


def test_plain_incremental_never_checks_or_replays(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = _Recorder(monkeypatch, [])
    assert backfill_worker.main(argv) == 0
    assert rec.calls == [("ingest", False)]


def test_explicit_rebuild_stays_ungated(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _Recorder(monkeypatch, [])
    assert backfill_worker.main([*argv, "--rebuild"]) == 0
    assert rec.calls == [("ingest", True)]


def test_conflicting_flags_fail_before_ingestion(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    rec = _Recorder(monkeypatch, [])
    assert backfill_worker.main([*argv, "--rebuild", "--auto-rebuild"]) == 1
    assert rec.calls == []
    assert "mutually exclusive" in capsys.readouterr().err


def test_auto_rebuild_rejected_with_usage_trigger(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = _Recorder(monkeypatch, [])
    code = backfill_worker.main(
        [*argv, "--auto-rebuild", "--usage-trigger", "--requested-at-ns", "1", "--host", "codex"]
    )
    assert code == 1 and rec.calls == []


def test_real_missing_store_small_backlog_end_to_end(tmp_path: Path) -> None:
    """No mocks: a missing store ingests nothing, is size 0 -> auto, and is rebuilt."""
    from little_loops.session_store import rebuild_needed

    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "s.jsonl").write_text("")
    db = tmp_path / "h.db"
    assert backfill_worker.main([str(db), str(folder), "--auto-rebuild"]) == 0
    assert rebuild_needed(db).status == "current"


def test_real_over_limit_store_is_not_replayed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from little_loops.session_store import lifecycle, rebuild_needed

    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "s.jsonl").write_text("")
    db = tmp_path / "h.db"
    monkeypatch.setattr(lifecycle, "REBUILD_AUTO_MAX_BYTES", 1)
    assert backfill_worker.main([str(db), str(folder), "--auto-rebuild"]) == 0
    assert rebuild_needed(db).status == "stale"


def test_real_auto_rebuild_preserves_live_telemetry_and_stamps_current(tmp_path: Path) -> None:
    """BUG-3761: the real worker replay keeps hook tool rows/corrections and their index."""
    import sqlite3

    from little_loops.session_store import (
        connect,
        ensure_db,
        rebuild_needed,
        record_correction,
    )
    from little_loops.session_store.writers import _index

    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "s.jsonl").write_text("")
    db = tmp_path / "h.db"
    ensure_db(db)
    conn = connect(db)
    try:
        conn.execute(
            "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, result_size, "
            "bytes_in, bytes_out, cache_hit, latency_ms) "
            "VALUES('2026-01-01T00:00:00Z', 's1', 'Bash', 'h', 4, 7, 4, 0, 12)"
        )
        _index(
            conn, content="Bash", kind="tool", ref="Bash", anchor="s1", ts="2026-01-01T00:00:00Z"
        )
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('rebuild_derive_version', 'stale-tag') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        conn.commit()
    finally:
        conn.close()
    record_correction(db, "s1", "no, actually use pytest", "user_prompt_submit")
    assert rebuild_needed(db).status == "stale"

    assert backfill_worker.main([str(db), str(folder), "--auto-rebuild"]) == 0

    assert rebuild_needed(db).status == "current"
    raw = sqlite3.connect(str(db))
    try:
        assert raw.execute(
            "SELECT bytes_in, bytes_out, latency_ms FROM tool_events"
        ).fetchall() == [(7, 4, 12)]
        assert raw.execute("SELECT source FROM user_corrections").fetchall() == [
            ("user_prompt_submit",)
        ]
        kinds = raw.execute(
            "SELECT kind, COUNT(*) FROM search_index GROUP BY kind ORDER BY kind"
        ).fetchall()
    finally:
        raw.close()
    assert kinds == [("correction", 1), ("tool", 1)]
