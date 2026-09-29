"""Detached Stop worker coalesces starts but preserves a trailing refresh."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from little_loops.cli import backfill_worker


class _Clock:
    def __init__(self, now: int) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def time_ns(self) -> int:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += int(seconds * 1e9)


def test_trailing_request_runs_after_throttle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "session.jsonl"
    source.write_text("{}\n")
    db = tmp_path / "history.db"
    clock = _Clock(10_000_000_000)
    calls: list[tuple[Path, Path, str]] = []
    monkeypatch.setattr(backfill_worker.time, "time_ns", clock.time_ns)
    monkeypatch.setattr(backfill_worker.time, "sleep", clock.sleep)
    monkeypatch.setattr(
        backfill_worker,
        "_refresh_usage_source",
        lambda d, s, *, host: calls.append((d, s, host)),
    )

    assert backfill_worker._run_usage_trigger(db, source, "claude-code", 10_000_000_000) == 0
    assert len(calls) == 2  # immediate settled pass and final bounded retry
    first_state = json.loads((tmp_path / "history.db.usage-refresh.lock").read_text())
    assert first_state["last_success_started_ns"] == 10_000_000_000

    # This Stop fired while the first worker ran. It must get a trailing pass,
    # even though the prior worker completed after the request timestamp.
    assert backfill_worker._run_usage_trigger(db, source, "claude-code", 11_000_000_000) == 0
    assert len(calls) == 4
    assert clock.sleeps[2] == 5.0
    second_state = json.loads((tmp_path / "history.db.usage-refresh.lock").read_text())
    assert second_state["last_success_started_ns"] == 17_000_000_000

    # A queued request from before the second worker began is already covered.
    assert backfill_worker._run_usage_trigger(db, source, "claude-code", 16_000_000_000) == 0
    assert len(calls) == 4


def test_failure_keeps_request_retryable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "session.jsonl"
    source.write_text("{}\n")
    db = tmp_path / "history.db"
    clock = _Clock(10_000_000_000)
    monkeypatch.setattr(backfill_worker.time, "time_ns", clock.time_ns)
    monkeypatch.setattr(backfill_worker.time, "sleep", clock.sleep)
    attempts = 0

    def refresh(*args: object, **kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("injected failure")

    monkeypatch.setattr(backfill_worker, "_refresh_usage_source", refresh)
    assert backfill_worker._run_usage_trigger(db, source, "claude-code", clock.now) == 1
    assert (tmp_path / "history.db.usage-refresh.lock").read_text() == ""
    assert backfill_worker._run_usage_trigger(db, source, "claude-code", 10_000_000_000) == 0
    assert attempts == 3


def test_other_session_is_not_coalesced_by_first_sessions_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first.write_text("{}\n")
    second.write_text("{}\n")
    db = tmp_path / "history.db"
    clock = _Clock(10_000_000_000)
    calls: list[Path] = []
    monkeypatch.setattr(backfill_worker.time, "time_ns", clock.time_ns)
    monkeypatch.setattr(backfill_worker.time, "sleep", clock.sleep)
    monkeypatch.setattr(
        backfill_worker,
        "_refresh_usage_source",
        lambda _db, source, *, host: calls.append(source),
    )
    assert backfill_worker._run_usage_trigger(db, first, "claude-code", clock.now) == 0
    # The second Stop was queued before the first worker completed. A global
    # started-at watermark would incorrectly discard its different source.
    assert backfill_worker._run_usage_trigger(db, second, "claude-code", 11_000_000_000) == 0
    assert calls == [first, first, second, second]


def test_cli_requires_explicit_supported_trigger(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    source = tmp_path / "session.jsonl"
    assert backfill_worker.main([str(db), str(source), "--usage-trigger"]) == 1
    assert (
        backfill_worker.main(
            [str(db), str(source), "--host", "pi", "--usage-trigger", "--requested-at-ns", "1"]
        )
        == 1
    )


def test_trigger_reaches_stored_usage_without_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "claude" / "stop-transcript-v2.1.284.jsonl"
    source = tmp_path / "session.jsonl"
    source.write_bytes(fixture.read_bytes())
    db = tmp_path / "history.db"
    monkeypatch.setattr(backfill_worker, "_USAGE_THROTTLE_SECONDS", 0.0)
    monkeypatch.setattr(backfill_worker, "_USAGE_SETTLE_SECONDS", 0.0)
    monkeypatch.setattr(backfill_worker, "_USAGE_FINAL_RETRY_SECONDS", 0.0)
    assert (
        backfill_worker.main(
            [
                str(db),
                str(source),
                "--host",
                "claude-code",
                "--usage-trigger",
                "--requested-at-ns",
                str(time.time_ns()),
            ]
        )
        == 0
    )
    from little_loops.session_store import connect, usage_source_freshness

    conn = connect(db)
    try:
        rows = conn.execute(
            "SELECT output_tokens, provenance FROM usage_events WHERE channel = 'transcript'"
        ).fetchall()
        assert len(rows) == 1  # two Stop-visible snapshots of one message ID
        assert rows[-1][0] == 176
        assert all(row[1] == "measured" for row in rows)
    finally:
        conn.close()
    assert usage_source_freshness(db, source)["status"] == "fresh"
