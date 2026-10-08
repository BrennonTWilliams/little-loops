"""Current-session Codex rollout refresh and as-of proof (ENH-3549)."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from little_loops.cli import backfill_worker
from little_loops.cli.ctx_stats import _compute_cache_rate_from_usage
from little_loops.hooks.types import LLHookEvent
from little_loops.hooks.usage_stop import handle
from little_loops.session_store import (
    backfill_raw_events,
    ensure_db,
    refresh_usage_source,
    usage_source_freshness,
)
from little_loops.session_store.sessions import SessionHandle

_ROLLOUT = Path(__file__).parent / "fixtures" / "codex" / "rollout-exec-resume-v0.158.0.jsonl"
_STOP_FIXTURES = Path(__file__).parent / "fixtures" / "codex"
_ADAPTER = (
    Path(__file__).resolve().parents[1]
    / "little_loops"
    / "hooks"
    / "adapters"
    / "codex"
    / "usage-stop.sh"
)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is unavailable")
def test_codex_shell_adapter_starts_detached_refresh_for_captured_stop(tmp_path: Path) -> None:
    """Exercise the packaged shell adapter and actual detached worker together."""
    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text("{}")
    source = tmp_path / "rollout-current.jsonl"
    source.write_bytes((_STOP_FIXTURES / "stop-rollout-v0.152.1.jsonl").read_bytes())
    payload = json.loads((_STOP_FIXTURES / "stop-hook-v0.152.1.json").read_text())
    payload["transcript_path"] = str(source)
    db = tmp_path / ".ll" / "history.db"
    env = os.environ.copy()
    env["LL_PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    env.pop("LL_NON_INTERACTIVE", None)
    env.pop("LL_HISTORY_DB", None)

    completed = subprocess.run(
        ["bash", str(_ADAPTER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=tmp_path,
        env=env,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    deadline = time.monotonic() + 10
    rows: list[tuple[int, int, str, str]] = []
    worker_finished = False
    lock = db.with_name(f"{db.name}.usage-refresh.lock")
    while time.monotonic() < deadline:
        if db.exists():
            with sqlite3.connect(db) as conn:
                try:
                    rows = conn.execute(
                        "SELECT input_tokens, output_tokens, channel, session_id FROM usage_events"
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []  # the detached worker is still creating the schema
            if lock.exists():
                try:
                    worker_finished = bool(json.loads(lock.read_text())["last_success_finished_ns"])
                except (json.JSONDecodeError, KeyError):
                    worker_finished = False
            if rows and worker_finished and usage_source_freshness(db, source)["status"] == "fresh":
                break
        time.sleep(0.05)
    assert rows == [(19379, 5, "rollout", payload["session_id"])]
    assert worker_finished
    assert usage_source_freshness(db, source)["status"] == "fresh"
    selected = SessionHandle(
        "codex", payload["session_id"], source, tmp_path, source.stat().st_mtime
    )
    result, diagnostic = _compute_cache_rate_from_usage(selected, db)
    assert diagnostic is None and result is not None
    assert result["freshness"] == "fresh"
    assert result["coverage"] == "unknown"  # 0.152.1 lacks native request identity
    assert result["hit_rate_pct"] is None
    assert result["channel_subtotals"]["rollout"]["events"] == 1


def test_captured_codex_stop_reaches_stored_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verified Stop payload queues a worker that commits its rollout usage."""
    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text("{}")
    source = tmp_path / "rollout-current.jsonl"
    source.write_bytes((_STOP_FIXTURES / "stop-rollout-v0.152.1.jsonl").read_bytes())
    payload = json.loads((_STOP_FIXTURES / "stop-hook-v0.152.1.json").read_text())
    payload["transcript_path"] = str(source)
    monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)
    monkeypatch.setattr(backfill_worker, "_USAGE_THROTTLE_SECONDS", 0.0)
    monkeypatch.setattr(backfill_worker, "_USAGE_SETTLE_SECONDS", 0.0)
    monkeypatch.setattr(backfill_worker, "_USAGE_FINAL_RETRY_SECONDS", 0.0)
    launched: list[list[str]] = []

    def run_worker(args: list[str], **_kwargs: object) -> object:
        launched.append(args)
        assert backfill_worker.main(args[3:]) == 0
        return object()

    monkeypatch.setattr("little_loops.hooks.usage_stop.subprocess.Popen", run_worker)
    event = LLHookEvent(host="codex", intent="usage_stop", cwd=str(tmp_path), payload=payload)
    assert handle(event).exit_code == 0
    assert len(launched) == 1
    assert launched[0][launched[0].index("--host") + 1] == "codex"
    assert usage_source_freshness(tmp_path / ".ll" / "history.db", source)["status"] == "fresh"
    with sqlite3.connect(tmp_path / ".ll" / "history.db") as conn:
        rows = conn.execute(
            "SELECT input_tokens, output_tokens, channel, session_id FROM usage_events"
        ).fetchall()
    assert rows == [(19379, 5, "rollout", payload["session_id"])]


def test_codex_stop_rollout_refresh_derives_each_completed_turn_once(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    source = tmp_path / "rollout-current.jsonl"
    lines = _ROLLOUT.read_text().splitlines(keepends=True)
    ensure_db(db)
    source.write_text("".join(lines[:6]))

    first = refresh_usage_source(db, source, host="codex")
    assert first["status"] == "complete"
    assert first["raw_events"] == 6
    assert usage_source_freshness(db, source)["status"] == "fresh"
    with sqlite3.connect(db) as conn:
        first_rows = conn.execute(
            "SELECT request_id FROM usage_events WHERE channel = 'rollout'"
        ).fetchall()
    assert len(first_rows) == 1

    with source.open("a") as handle:
        handle.writelines(lines[6:])
    assert usage_source_freshness(db, source)["status"] == "stale"
    second = refresh_usage_source(db, source, host="codex")
    assert second["status"] == "complete"
    assert second["raw_events"] == 5
    assert usage_source_freshness(db, source)["status"] == "fresh"
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT request_id FROM usage_events WHERE channel = 'rollout'"
        ).fetchall()
    assert len(rows) == 2
    assert len({row[0] for row in rows}) == 2

    again = refresh_usage_source(db, source, host="codex")
    assert again["raw_events"] == again["usage_events"] == 0
    with sqlite3.connect(db) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM usage_events WHERE channel = 'rollout'").fetchone()[
                0
            ]
            == 2
        )


def test_codex_existing_raw_rows_gain_a_verified_cursor_without_duplicates(
    tmp_path: Path,
) -> None:
    db = tmp_path / "history.db"
    source = tmp_path / "rollout-current.jsonl"
    source.write_text(_ROLLOUT.read_text())
    ensure_db(db)
    assert backfill_raw_events(db, jsonl_files=[source], host="codex") == 11
    # Verified raw-only ingestion staged an acquisition head and a derive handoff, so the
    # source is truthfully stale (derive pending) rather than unknown.
    assert usage_source_freshness(db, source)["status"] in {"unknown", "stale"}

    refreshed = refresh_usage_source(db, source, host="codex")
    assert refreshed["raw_events"] == 0
    assert usage_source_freshness(db, source)["status"] == "fresh"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0] == 11
        assert (
            conn.execute("SELECT COUNT(*) FROM usage_events WHERE channel = 'rollout'").fetchone()[
                0
            ]
            == 2
        )


def test_codex_partial_or_changed_rollout_never_gets_a_fresh_boundary(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    source = tmp_path / "rollout-current.jsonl"
    source.write_text(_ROLLOUT.read_text())
    ensure_db(db)
    assert refresh_usage_source(db, source, host="codex")["status"] == "complete"

    with source.open("a") as handle:
        handle.write('{"type":"event_msg"')
    assert usage_source_freshness(db, source)["status"] == "unknown"
    assert refresh_usage_source(db, source, host="codex")["status"] == "partial"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0] == 11

    source.write_text(_ROLLOUT.read_text().splitlines()[0] + "\n")
    with pytest.raises(RuntimeError, match="rotated|truncated|overwritten"):
        refresh_usage_source(db, source, host="codex")
    assert usage_source_freshness(db, source)["status"] == "unknown"
