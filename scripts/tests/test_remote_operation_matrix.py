"""Shared-store operation matrix under ``provider: libsql`` (FEAT-3535, Step 6).

A rejected operation raises ``HistoryUnsupported`` naming the operation *before any
mutation* -- and, since the refusal needs no server, before any network call. Supported
operations (reads, event writes, search, ``ll_grep``) round-trip against the stub.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from little_loops.session_store import db as db_mod
from little_loops.session_store import lifecycle, remote_schema
from little_loops.session_store.backend import (
    HistoryUnsupported,
    open_history,
    open_history_readonly,
)
from little_loops.session_store.hrana import HranaClient
from tests.hrana_stub import HranaStub

TOKEN = "sentinel-token-DO-NOT-LEAK"


@pytest.fixture
def remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[HranaStub]:
    stub = HranaStub(token=TOKEN).start()
    monkeypatch.setenv("LL_HISTORY_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("LL_HISTORY_URL", stub.url)
    monkeypatch.delenv("LL_HISTORY_DB", raising=False)
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
    remote_schema.clear_verification_cache()
    db_mod.clear_backend_config_cache()
    remote_schema.migrate_remote(HranaClient(stub.url, TOKEN), "acme-api")
    try:
        yield stub
    finally:
        stub.stop()
        remote_schema.clear_verification_cache()
        db_mod.clear_backend_config_cache()


def _snapshot(db: Path) -> None:
    from little_loops.session_store import queries

    queries.build_snapshot_db(db, Path("snap.db"), tables=["skill"])


_REJECTED = [
    ("rebuild", lambda: lifecycle.rebuild()),
    ("backfill", lambda: lifecycle.backfill()),
    ("prune", lambda: lifecycle.prune()),
    ("compact", lambda: lifecycle.compact()),
    ("compact", lambda: lifecycle.compact(and_prune=True)),
    ("recompress", lambda: lifecycle.recompress_raw_events()),
    ("rebuild", lambda: lifecycle.backfill_incremental(also_rebuild=True)),
    ("snapshot_export", lambda: _snapshot(Path(".ll/history.db"))),
]


class TestRejectedOperations:
    @pytest.mark.parametrize(("operation", "call"), _REJECTED)
    def test_raises_naming_the_operation_before_any_network_call(
        self, remote: HranaStub, operation: str, call
    ) -> None:
        before = len(remote.requests)
        with pytest.raises(HistoryUnsupported) as ei:
            call()
        assert ei.value.operation == operation
        assert "libsql" in str(ei.value)
        assert len(remote.requests) == before

    def test_local_sqlite_still_runs_the_same_operations(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / "local.db"))
        db_mod.clear_backend_config_cache()
        assert isinstance(lifecycle.rebuild(), dict)
        assert isinstance(lifecycle.prune(dry_run=True), dict)

    def test_explicit_local_path_is_not_rejected_under_libsql(
        self, remote: HranaStub, tmp_path: Path
    ) -> None:
        assert isinstance(lifecycle.rebuild(tmp_path / "scratch.db"), dict)


class TestSupportedOperations:
    def test_event_write_round_trips(self, remote: HranaStub) -> None:
        from little_loops.session_store import record_skill_event

        record_skill_event(Path(".ll/history.db"), "s1", "commit", "--all")
        row = remote.db.execute("select skill_name, args from skill_events").fetchone()
        assert row == ("commit", "--all")

    def test_reads_round_trip(self, remote: HranaStub) -> None:
        remote.db.execute("insert into skill_events(ts, skill_name) values ('t', 'x')")
        ro = open_history_readonly(ensure=True)
        assert ro.execute("select skill_name from skill_events").fetchone()["skill_name"] == "x"

    def test_fts5_search_round_trips(self, remote: HranaStub) -> None:
        conn = open_history()
        conn.execute(
            "insert into search_index(content, kind, ref, anchor, ts) values (?, ?, ?, ?, ?)",
            ("remote history backend works", "message", "1", "a", "t"),
        )
        rows = conn.execute(
            "select ref, bm25(search_index) as score from search_index where search_index match ?",
            ("backend",),
        ).fetchall()
        assert [r["ref"] for r in rows] == ["1"]

    def test_backfill_incremental_without_rebuild_is_allowed(self, remote: HranaStub) -> None:
        result = lifecycle.backfill_incremental(jsonl_files=[])
        assert isinstance(result, dict)


class TestRedactIsASupportedRemoteOperation:
    """ENH-3752: ``redact`` is logical maintenance, not a retention refusal."""

    def test_redact_is_not_in_the_refusal_table(self) -> None:
        from little_loops.session_store.backend import _REMOTE_REFUSALS

        assert "redact" not in _REMOTE_REFUSALS
        assert "redact" not in {operation for operation, _ in _REJECTED}

    def test_default_target_resolves_to_the_configured_remote_store(
        self, remote: HranaStub
    ) -> None:
        from little_loops.session_store import redact_raw_events

        remote.db.execute(
            "INSERT INTO raw_events(id, ts, host, source_path, line_no, event_type, raw_line,"
            " parsed_json) VALUES (1, 't', 'claude-code', 'p', 1, 'assistant', ?, ?)",
            (json.dumps({"type": "assistant", "x": "a@b.co"}),) * 2,
        )
        preview = redact_raw_events(dry_run=True)
        assert preview.target == {"provider": "libsql", "project_id": "acme-api"}
        assert preview.would_change == 1 and preview.complete
        applied = redact_raw_events()
        assert applied.updates_applied == 1 and applied.complete
        assert "[EMAIL]" in remote.db.execute("SELECT raw_line FROM raw_events").fetchone()[0]

    def test_explicit_local_path_stays_local_under_a_remote_config(self, tmp_path: Path) -> None:
        from little_loops.session_store import ensure_db, redact_raw_events

        local = tmp_path / "other.db"
        ensure_db(local)
        report = redact_raw_events(local, dry_run=True)
        assert report.target == {"provider": "sqlite", "path": str(local)}


class TestLlGrepWithoutCreateFunction:
    def _messages(self, stub: HranaStub) -> None:
        for i, text in enumerate(["alpha needle one", "beta haystack", "Needle Two", "gamma"]):
            stub.db.execute(
                "insert into message_events(ts, session_id, content) values (?, 's', ?)",
                (f"2026-01-0{i + 1}", text),
            )

    def test_regex_is_applied_in_python(self, remote: HranaStub) -> None:
        from little_loops.history_reader.formatting import ll_grep

        self._messages(remote)
        got = ll_grep(r"needle\s+(one|two)")
        assert [g.content for g in got] == ["alpha needle one", "Needle Two"]

    def test_literal_prefilter_keeps_the_scan_bounded(self, remote: HranaStub) -> None:
        from little_loops.history_reader.formatting import ll_grep

        self._messages(remote)
        ll_grep(r"needle")
        sql = remote.requests[-1]["body"].lower()
        assert "like" in sql and "regexp_match" not in sql

    def test_limit_and_order_are_preserved(self, remote: HranaStub) -> None:
        from little_loops.history_reader.formatting import ll_grep

        self._messages(remote)
        got = ll_grep(r"needle", limit=1)
        assert [g.content for g in got] == ["alpha needle one"]

    def test_alternation_falls_back_to_a_bounded_scan(self, remote: HranaStub) -> None:
        from little_loops.history_reader.formatting import ll_grep

        self._messages(remote)
        got = ll_grep(r"gamma|beta")
        assert [g.content for g in got] == ["beta haystack", "gamma"]

    def test_invalid_regex_returns_nothing(self, remote: HranaStub) -> None:
        from little_loops.history_reader.formatting import ll_grep

        self._messages(remote)
        assert ll_grep(r"(unclosed") == []
