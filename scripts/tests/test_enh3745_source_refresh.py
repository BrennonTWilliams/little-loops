"""ENH-3745 phases 3-4: acquisition accounting, pending/failure state, publication, invalidation."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from little_loops.pii import HistorySanitizationError
from little_loops.session_store import (
    backfill_raw_events,
    backfill_usage_incremental,
    connect,
    ensure_db,
    lifecycle,
    prune,
    rebuild,
    refresh_usage_source,
    usage_source_freshness,
)
from little_loops.session_store import usage_source_state as uss
from little_loops.session_store import usage_source_tracking as tracking
from little_loops.session_store.sessions import SessionHandle
from little_loops.session_store.usage_refresh import refresh_raw_events

_FIXTURES = Path(__file__).parent / "fixtures"
_CLAUDE = _FIXTURES / "claude"
_CODEX = _FIXTURES / "codex" / "rollout-exec-resume-v0.158.0.jsonl"
_SECRET = "SUPERSECRETMARKER"


def _records() -> list[str]:
    return (_CLAUDE / "transcript-changing-usage-observed.jsonl").read_text().splitlines()


def _unkeyed_tail() -> list[str]:
    """The appended snapshots without a producer message id (unkeyed audit candidates)."""
    out = []
    for line in _records()[2:]:
        record = json.loads(line)
        record["message"].pop("id", None)
        out.append(json.dumps(record))
    return out


def _completion(db: Path, source: Path) -> uss.SourceDeriveCompletion:
    conn = connect(db)
    try:
        return uss.read_source_derive_completion(conn, str(source))
    finally:
        conn.close()


def _obligations(db: Path, source: Path) -> list[tuple[str, str]]:
    conn = connect(db)
    try:
        return [(o.kind, o.reason) for o in uss.pending_obligations(conn, str(source))]
    finally:
        conn.close()


def _sql(db: Path, statement: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(statement, params).fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()


def _dump(db: Path) -> bytes:
    conn = sqlite3.connect(str(db))
    try:
        return "\n".join(conn.iterdump()).encode("utf-8", "replace")
    finally:
        conn.close()


@pytest.fixture
def claude(tmp_path: Path) -> tuple[Path, Path]:
    tmp = tmp_path.resolve()
    source = tmp / "session.jsonl"
    source.write_text("\n".join(_records()[:2]) + "\n")
    db = tmp / "history.db"
    return db, source


class TestClaudePublication:
    def test_first_refresh_from_zero_publishes_semantic_completion(
        self, claude: tuple[Path, Path]
    ) -> None:
        db, source = claude
        assert refresh_usage_source(db, source)["status"] == "complete"
        done = _completion(db, source)
        assert (done.status, done.basis, done.outstanding) == ("complete", "semantic", "none")
        assert done.boundary is not None and done.boundary.offset == source.stat().st_size
        assert done.boundary.acquisition_version == tracking.USAGE_ACQUISITION_VERSION
        assert done.scope is not None and done.scope.session_id  # native sessionId seen
        assert usage_source_freshness(db, source)["status"] == "fresh"

    def test_append_extends_only_after_prefix_reverification(
        self, claude: tuple[Path, Path]
    ) -> None:
        db, source = claude
        refresh_usage_source(db, source)
        first = _completion(db, source)
        with source.open("a") as handle:
            handle.write("\n".join(_records()[2:]) + "\n")
        assert usage_source_freshness(db, source)["status"] == "stale"
        assert refresh_usage_source(db, source)["status"] == "complete"
        second = _completion(db, source)
        assert second.status == "complete"
        assert second.boundary is not None and first.boundary is not None
        assert second.boundary.offset > first.boundary.offset
        assert second.scope is not None and first.scope is not None
        assert second.scope.generation_id == first.scope.generation_id

    def test_pruned_prefix_cannot_extend_and_keeps_the_older_boundary(
        self, claude: tuple[Path, Path]
    ) -> None:
        db, source = claude
        refresh_usage_source(db, source)
        older = _completion(db, source).boundary
        _sql(db, "DELETE FROM raw_events WHERE line_no = 1")  # retained prefix no longer checkable
        with source.open("a") as handle:
            handle.write("\n".join(_records()[2:]) + "\n")
        result = refresh_usage_source(db, source)
        assert result["raw_events"] >= 1  # ingestion still advanced
        done = _completion(db, source)
        assert done.status == "pending" and done.basis == "none"
        assert done.boundary == older  # historical success preserved, not extended
        assert ("derive_gap", "acquisition_unprovable") in _obligations(db, source)

    def test_legacy_cursor_without_provable_prefix_stays_on_the_public_fallback(
        self, claude: tuple[Path, Path]
    ) -> None:
        db, source = claude
        refresh_usage_source(db, source)
        _sql(db, "DELETE FROM usage_source_state")  # a legacy-only source: cursor, no semantic head
        _sql(db, "DELETE FROM usage_source_pending")
        _sql(db, "DELETE FROM raw_events WHERE line_no = 1")
        assert _completion(db, source).reason == "untracked"
        result = refresh_usage_source(db, source)
        assert result["status"] == "complete"  # nothing negative: legacy compatibility
        assert _completion(db, source).basis == "none"  # fallback never becomes semantic proof
        assert usage_source_freshness(db, source)["status"] == "fresh"

    def test_legacy_cursor_with_intact_prefix_establishes_semantic_completion(
        self, claude: tuple[Path, Path]
    ) -> None:
        db, source = claude
        refresh_usage_source(db, source)
        _sql(db, "DELETE FROM usage_source_state")
        _sql(db, "DELETE FROM usage_source_pending")
        assert _completion(db, source).basis == "none"
        refresh_usage_source(db, source)
        assert _completion(db, source).basis == "semantic"


class TestRejectedInput:
    def _bad(self, claude: tuple[Path, Path], tail: bytes) -> tuple[Path, Path]:
        db, source = claude
        refresh_usage_source(db, source)
        with source.open("ab") as handle:
            handle.write(tail)
        return db, source

    @pytest.mark.parametrize(
        ("tail", "reason"),
        [
            (b"{not json " + _SECRET.encode() + b"\n", "json_failure"),
            (b'[1, 2, "' + _SECRET.encode() + b'"]\n', "non_object_record"),
            (b"\xff\xfe" + _SECRET.encode() + b"\n", "decode_failure"),
        ],
    )
    def test_rejected_complete_line_is_durable_content_free_and_blocks_completion(
        self, claude: tuple[Path, Path], tail: bytes, reason: str
    ) -> None:
        db, source = self._bad(claude, tail)
        result = refresh_usage_source(db, source)
        assert (result["status"], result["reason"]) == ("incomplete", "acquisition_failure")
        assert ("acquisition_failure", reason) in _obligations(db, source)
        done = _completion(db, source)
        assert (done.status, done.basis) == ("unprovable", "none")
        fresh = usage_source_freshness(db, source)
        assert (fresh["status"], fresh["reason"]) == ("unknown", reason)
        assert _SECRET.encode() not in _dump(db)

    def test_neither_a_later_valid_append_nor_unchanged_refresh_clears_it(
        self, claude: tuple[Path, Path]
    ) -> None:
        db, source = self._bad(claude, b"{broken\n")
        refresh_usage_source(db, source)
        with source.open("a") as handle:
            handle.write(_records()[0] + "\n")
        refresh_usage_source(db, source)
        refresh_usage_source(db, source)
        assert ("acquisition_failure", "json_failure") in _obligations(db, source)
        assert _completion(db, source).basis == "none"

    def test_blank_lines_are_recognized_benign(self, claude: tuple[Path, Path]) -> None:
        db, source = self._bad(claude, b"\n   \n")
        assert refresh_usage_source(db, source)["status"] == "complete"
        assert _obligations(db, source) == []
        assert _completion(db, source).basis == "semantic"

    def test_unterminated_tail_stays_pending_until_it_completes(
        self, claude: tuple[Path, Path]
    ) -> None:
        db, source = claude
        refresh_usage_source(db, source)
        record = _records()[2]
        with source.open("a") as handle:
            handle.write(record[:40])
        assert refresh_usage_source(db, source)["status"] == "partial"
        assert ("partial_tail", "partial_tail") in _obligations(db, source)
        assert _completion(db, source).basis == "none"
        with source.open("a") as handle:
            handle.write(record[40:] + "\n")
        assert refresh_usage_source(db, source)["status"] == "complete"
        assert _obligations(db, source) == []
        assert _completion(db, source).basis == "semantic"

    def test_physical_accounting_classifies_without_retaining_bytes(self, tmp_path: Path) -> None:
        path = tmp_path / "x.jsonl"
        path.write_bytes(b'{"a": 1}\n\n{oops\n[1]\n\xc3\x28\n{"b": 2}\n{"partial": ')
        accounting = tracking.account_physical_lines(path)
        assert accounting.line_count == 6
        reasons = {r.reason: (r.first_line_no, r.last_line_no) for r in accounting.rejected}
        assert reasons == {
            "json_failure": (3, 3),
            "non_object_record": (4, 4),
            "decode_failure": (5, 5),
        }
        assert accounting.partial_tail is not None
        assert all(not hasattr(r, "raw") for r in accounting.rejected)


class TestSanitizerRefusal:
    def _refuse_line(self, monkeypatch: pytest.MonkeyPatch, marker: str) -> None:
        real = lifecycle.sanitize_history_payload

        def refuse(payload: dict[str, Any], **kw: Any) -> Any:
            if marker in json.dumps(payload):
                raise HistorySanitizationError("unsafe_identity")
            return real(payload, **kw)

        monkeypatch.setattr(lifecycle, "sanitize_history_payload", refuse)

    def test_whole_call_rolls_back_and_a_failure_only_transaction_records_the_reason(
        self, claude: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, source = claude
        records = _records()
        records[1] = records[1][:-1] + f', "marker": "{_SECRET}"' + "}"
        source.write_text("\n".join(records[:2]) + "\n")
        self._refuse_line(monkeypatch, _SECRET)
        with pytest.raises(HistorySanitizationError):
            refresh_usage_source(db, source)
        # ENH-3751: ingestion, cursor and checkpoint all rolled back (valid line 1 too).
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(0,)]
        assert _sql(db, "SELECT COUNT(*) FROM usage_source_cursors") == [(0,)]
        assert _sql(db, "SELECT COUNT(*) FROM meta WHERE key LIKE 'usage_derive_%'") == [(0,)]
        # ... while a separate guarded transaction recorded bounded, content-free evidence.
        assert ("acquisition_failure", "sanitization_refused") in _obligations(db, source)
        row = _sql(
            db,
            "SELECT refusal_code, first_line_no, first_offset FROM usage_source_pending",
        )[0]
        assert row[0] == "unsafe_identity" and row[1] == 2 and row[2] > 0
        assert _SECRET.encode() not in _dump(db)
        fresh = usage_source_freshness(db, source)  # no cursor: still reports the reason
        assert (fresh["status"], fresh["reason"], fresh["as_of"]) == (
            "unknown",
            "sanitization_refused",
            None,
        )
        assert _completion(db, source).status == "unprovable"

    def test_stale_refusal_cannot_taint_a_newer_successful_refresh(
        self, claude: tuple[Path, Path]
    ) -> None:
        db, source = claude
        refresh_usage_source(db, source)
        conn = connect(db)
        try:
            conn.execute("BEGIN IMMEDIATE")
            attempt = tracking.begin_attempt(conn, str(source), lifecycle._USAGE_DERIVE_VERSION)
            conn.rollback()
        finally:
            conn.close()
        with source.open("a") as handle:  # a newer successful refresh lands first
            handle.write("\n".join(_records()[2:]) + "\n")
        refresh_usage_source(db, source)
        before = _completion(db, source)
        written = tracking.record_failure_only(
            lambda: connect(db),
            attempt,
            reason="sanitization_refused",
            refusal_code="unsafe_identity",
        )
        assert written is False
        assert _obligations(db, source) == []
        assert _completion(db, source) == before

    def test_failed_diagnostic_write_never_turns_rollback_into_success(
        self, claude: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, source = claude
        self._refuse_line(monkeypatch, "assistant")
        monkeypatch.setattr(
            uss, "record_source_pending", lambda *a, **k: (_ for _ in ()).throw(sqlite3.Error("x"))
        )
        monkeypatch.setattr(tracking, "record_source_pending", uss.record_source_pending)
        with pytest.raises(HistorySanitizationError):
            refresh_usage_source(db, source)
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(0,)]
        assert _sql(db, "SELECT COUNT(*) FROM usage_source_pending") == [(0,)]

    def test_codex_refusal_and_decode_failure_are_recorded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tmp = tmp_path.resolve()
        db, source = tmp / "h.db", tmp / "rollout.jsonl"
        lines = _CODEX.read_text().splitlines(keepends=True)
        source.write_text("".join(lines[:6]))
        real = lifecycle.sanitize_history_payload
        calls = {"n": 0}

        def refuse(payload: dict[str, Any], **kw: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 3:
                raise HistorySanitizationError("invalid_payload")
            return real(payload, **kw)

        monkeypatch.setattr(lifecycle, "sanitize_history_payload", refuse)
        with pytest.raises(HistorySanitizationError):
            refresh_usage_source(db, source, host="codex")
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(0,)]
        assert ("acquisition_failure", "sanitization_refused") in _obligations(db, source)
        monkeypatch.undo()
        # A strict-UTF-8 failure after a valid header, before any event is yielded.
        bad = tmp / "rollout-bad.jsonl"
        bad.write_bytes(lines[0].encode() + b"\xff\xfe" + _SECRET.encode() + b"\n")
        with pytest.raises((UnicodeDecodeError, ValueError, RuntimeError)):
            refresh_usage_source(db, bad, host="codex")
        assert _SECRET.encode() not in _dump(db)
        assert any(r == "decode_failure" for _, r in _obligations(db, bad))


class TestHeldSources:
    def test_held_append_stays_pending_while_an_unrelated_source_remains_complete(
        self, tmp_path: Path
    ) -> None:
        tmp = tmp_path.resolve()
        db = tmp / "h.db"
        held, other = tmp / "held.jsonl", tmp / "other.jsonl"
        held.write_text("\n".join(_records()[:2]) + "\n")
        other.write_text((_CLAUDE / "transcript-v2.1.284.jsonl").read_text())
        refresh_usage_source(db, held)
        refresh_usage_source(db, other)
        assert _completion(db, held).basis == "semantic"
        _sql(
            db,
            "INSERT INTO usage_replay_holds(source_path, host, channel, reason, created_at) "
            "VALUES(?, '*', '*', 'dangling_raw_link', '2026-01-01T00:00:00Z')",
            (str(held),),
        )
        # Unkeyed audit candidates cannot be proved distinct from a held source's protected
        # history (ENH-3770), so they stay pending; proved-distinct keyed requests derive.
        with held.open("a") as handle:
            handle.write("\n".join(_unkeyed_tail()) + "\n")
        result = refresh_usage_source(db, held)
        assert result["status"] == "incomplete"
        assert ("derive_gap", "held_source_skipped") in _obligations(db, held) or (
            "derive_gap",
            "usage_derive_gap",
        ) in _obligations(db, held)
        assert _completion(db, held).basis == "none"
        assert _completion(db, other).basis == "semantic"
        assert usage_source_freshness(db, other)["status"] == "fresh"

    def test_scan_advance_past_another_sources_held_rows_commits_its_pending_bound(
        self, tmp_path: Path
    ) -> None:
        tmp = tmp_path.resolve()
        db = tmp / "h.db"
        held, other = tmp / "held.jsonl", tmp / "other.jsonl"
        held.write_text("\n".join(_records()[:2]) + "\n")
        other.write_text((_CLAUDE / "transcript-v2.1.284.jsonl").read_text())
        refresh_usage_source(db, held)
        _sql(
            db,
            "INSERT INTO usage_replay_holds(source_path, host, channel, reason, created_at) "
            "VALUES(?, '*', '*', 'dangling_raw_link', '2026-01-01T00:00:00Z')",
            (str(held),),
        )
        with held.open("a") as handle:
            handle.write("\n".join(_unkeyed_tail()) + "\n")
        # Raw-only ingestion of the held source's append, then another source's refresh
        # advances the global scan past it.
        backfill_raw_events(db, jsonl_files=[held], host="claude-code")
        refresh_usage_source(db, other)
        assert ("derive_gap", "held_source_skipped") in _obligations(db, held)
        row = _sql(
            db,
            "SELECT first_raw_id, last_raw_id FROM usage_source_pending WHERE source_path = ?",
            (str(held),),
        )[0]
        assert row[0] is not None and row[1] >= row[0]
        assert _completion(db, other).basis == "semantic"
        assert usage_source_freshness(db, held)["reason"] in {"new_append", "derive_pending"}

    def test_pending_and_scan_publication_roll_back_together(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tmp = tmp_path.resolve()
        db = tmp / "h.db"
        held = tmp / "held.jsonl"
        held.write_text("\n".join(_records()[:2]) + "\n")
        refresh_usage_source(db, held)
        _sql(
            db,
            "INSERT INTO usage_replay_holds(source_path, host, channel, reason, created_at) "
            "VALUES(?, '*', '*', 'dangling_raw_link', '2026-01-01T00:00:00Z')",
            (str(held),),
        )
        with held.open("a") as handle:
            handle.write("\n".join(_unkeyed_tail()) + "\n")
        backfill_raw_events(db, jsonl_files=[held], host="claude-code")
        floor = _sql(db, "SELECT value FROM meta WHERE key = 'usage_derive_raw_id'")
        pending = _sql(db, "SELECT COUNT(*) FROM usage_source_pending")
        monkeypatch.setattr(
            tracking,
            "record_replay_outcomes",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        monkeypatch.setattr(lifecycle, "record_replay_outcomes", tracking.record_replay_outcomes)
        with pytest.raises(RuntimeError, match="boom"):
            backfill_usage_incremental(db)
        assert _sql(db, "SELECT value FROM meta WHERE key = 'usage_derive_raw_id'") == floor
        assert _sql(db, "SELECT COUNT(*) FROM usage_source_pending") == pending


class TestPruneVeto:
    def _old_source(self, tmp_path: Path, name: str) -> tuple[Path, Path]:
        tmp = tmp_path.resolve()
        db = tmp / "h.db"
        source = tmp / name
        source.write_text((_CLAUDE / "transcript-v2.1.284.jsonl").read_text())
        refresh_usage_source(db, source)
        return db, source

    def _age(self, db: Path, source: Path) -> None:
        _sql(
            db,
            "UPDATE raw_events SET ts = '2000-01-01T00:00:00Z', compacted = 1 WHERE source_path = ?",
            (str(source),),
        )

    _CFG = {
        "analytics": {
            "retention": {
                "raw_event_max_age_days": 30,
                "min_project_age_days": 0,
                "min_db_size_mb": 0,
            }
        }
    }

    def test_unresolved_obligation_vetoes_only_its_source(self, tmp_path: Path) -> None:
        db, first = self._old_source(tmp_path, "a.jsonl")
        second = tmp_path.resolve() / "b.jsonl"
        second.write_text((_CLAUDE / "transcript-v2.1.284.jsonl").read_text())
        refresh_usage_source(db, second)
        for source in (first, second):
            self._age(db, source)
        conn = connect(db)
        try:
            conn.execute("BEGIN IMMEDIATE")
            head = uss.read_source_head(conn, str(first))
            assert head is not None
            uss.record_source_pending(
                conn,
                uss.SourcePending(
                    head.scope,
                    "refresh",
                    "parser_refresh",
                    raw_cache_pending=True,
                    usage_pending=False,
                ),
                expected_head_revision=head.revision,
            )
            conn.commit()
        finally:
            conn.close()
        result = prune(db, config=self._CFG)
        assert result["retention_reasons"] == ["source_recovery_pending"]
        remaining = _sql(db, "SELECT DISTINCT source_path FROM raw_events")
        assert remaining == [(str(first),)]  # cache-only pending vetoes; resolved neighbor pruned
        # Prune never acknowledged or deleted the obligation.
        assert _obligations(db, first) == [("refresh", "parser_refresh")]

    def test_dry_run_matches_and_resolved_sources_stay_eligible(self, tmp_path: Path) -> None:
        db, source = self._old_source(tmp_path, "a.jsonl")
        self._age(db, source)
        dry = prune(db, config=self._CFG, dry_run=True)
        assert dry["retention_reasons"] == []


class TestInvalidationSeams:
    def test_standalone_rebuild_preserves_current_completion_and_rolls_back_atomically(
        self, claude: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, source = claude
        refresh_usage_source(db, source)
        before = _completion(db, source)
        usage_before = _sql(db, "SELECT * FROM usage_events ORDER BY id")
        deps_before = _sql(db, "SELECT COUNT(*) FROM usage_completion_dependencies")
        with monkeypatch.context() as patcher:
            patcher.setattr(
                lifecycle,
                "_compact_sessions",
                lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")),
            )
            with pytest.raises(RuntimeError):
                rebuild(db)
        assert _completion(db, source) == before  # forced failure restored the facts
        assert _sql(db, "SELECT * FROM usage_events ORDER BY id") == usage_before
        rebuild(db)
        # ENH-3770: an unchanged rebuild is a no-op for usage -- it neither replaces the
        # observations completion consumed nor creates obligations merely because it ran.
        done = _completion(db, source)
        assert (done.status, done.basis, done.outstanding) == ("complete", "semantic", "none")
        assert done.boundary == before.boundary
        assert _sql(db, "SELECT * FROM usage_events ORDER BY id") == usage_before
        assert _sql(db, "SELECT COUNT(*) FROM usage_completion_dependencies") == deps_before
        assert _obligations(db, source) == []

    def test_rebuild_leaves_unrelated_live_usage_alone(self, claude: tuple[Path, Path]) -> None:
        db, source = claude
        refresh_usage_source(db, source)
        _sql(
            db,
            "INSERT INTO usage_events(ts, session_id, model, input_tokens, output_tokens, channel) "
            "VALUES('2026-01-01T00:00:00Z', 'live', 'm', 1, 2, 'live')",
        )
        rebuild(db)
        assert _sql(db, "SELECT COUNT(*) FROM usage_events WHERE channel = 'live'") == [(1,)]

    def test_parser_refresh_replacement_invalidates_with_scoped_pending(
        self, tmp_path: Path
    ) -> None:
        tmp = tmp_path.resolve()
        db = tmp / "h.db"
        source = tmp / "session.jsonl"
        source.write_text((_CLAUDE / "transcript-v2.1.284.jsonl").read_text())
        other = tmp / "other.jsonl"
        other.write_text("\n".join(_records()[:2]) + "\n")
        refresh_usage_source(db, source)
        refresh_usage_source(db, other)
        assert _completion(db, source).basis == "semantic"
        handle = SessionHandle("claude-code", "s", source, tmp, source.stat().st_mtime)
        # A NULL stored qualification is promotable from the original source: replacement runs.
        _sql(
            db, "UPDATE raw_events SET usage_contract = NULL WHERE source_path = ?", (str(source),)
        )
        refreshed = refresh_raw_events(db, handles=[handle])
        assert refreshed.sources[0].status == "refreshed"
        done = _completion(db, source)
        assert (done.status, done.basis, done.outstanding) == ("pending", "none", "both")
        assert ("refresh", "parser_refresh") in _obligations(db, source)
        assert _completion(db, other).basis == "semantic"  # unrelated source untouched

    def test_unchanged_parser_output_still_accounts_rejected_physical_lines(
        self, tmp_path: Path
    ) -> None:
        tmp = tmp_path.resolve()
        db = tmp / "h.db"
        source = tmp / "session.jsonl"
        source.write_text((_CLAUDE / "transcript-v2.1.284.jsonl").read_text())
        refresh_usage_source(db, source)
        with source.open("a") as handle:
            handle.write("{bad " + _SECRET + "\n")
        handle = SessionHandle("claude-code", "s", source, tmp, source.stat().st_mtime)
        result = refresh_raw_events(db, handles=[handle])
        assert result.sources[0].status == "unchanged"
        assert ("acquisition_failure", "json_failure") in _obligations(db, source)
        assert _SECRET.encode() not in _dump(db)

    def test_codex_catchup_invalidates_before_replay_and_recompletes(self, tmp_path: Path) -> None:
        tmp = tmp_path.resolve()
        db, source = tmp / "h.db", tmp / "rollout.jsonl"
        lines = _CODEX.read_text().splitlines(keepends=True)
        source.write_text("".join(lines[:6]))
        assert refresh_usage_source(db, source, host="codex")["status"] == "complete"
        first = _completion(db, source)
        assert first.basis == "semantic"
        with source.open("a") as handle:
            handle.writelines(lines[6:])
        assert refresh_usage_source(db, source, host="codex")["status"] == "complete"
        second = _completion(db, source)
        assert second.basis == "semantic"
        assert second.boundary is not None and first.boundary is not None
        assert second.boundary.offset > first.boundary.offset
        assert _obligations(db, source) == []  # catch-up pending resolved by committed proof

    def test_codex_catchup_failure_restores_rows_and_facts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tmp = tmp_path.resolve()
        db, source = tmp / "h.db", tmp / "rollout.jsonl"
        lines = _CODEX.read_text().splitlines(keepends=True)
        source.write_text("".join(lines[:6]))
        refresh_usage_source(db, source, host="codex")
        before_usage = _sql(db, "SELECT id FROM usage_events ORDER BY id")
        before = _completion(db, source)
        with source.open("a") as handle:
            handle.writelines(lines[6:])
        monkeypatch.setattr(
            tracking,
            "finalize_source_refresh",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("after invalidation")),
        )
        monkeypatch.setattr(lifecycle, "finalize_source_refresh", tracking.finalize_source_refresh)
        with pytest.raises(RuntimeError, match="after invalidation"):
            refresh_usage_source(db, source, host="codex")
        assert _sql(db, "SELECT id FROM usage_events ORDER BY id") == before_usage
        assert _completion(db, source) == before
        assert _obligations(db, source) == []

    def test_unchanged_codex_fast_path_cannot_waive_pending_or_checkpoint_state(
        self, tmp_path: Path
    ) -> None:
        tmp = tmp_path.resolve()
        db, source = tmp / "h.db", tmp / "rollout.jsonl"
        source.write_text(_CODEX.read_text())
        assert refresh_usage_source(db, source, host="codex")["status"] == "complete"
        assert refresh_usage_source(db, source, host="codex")["status"] == "complete"
        _sql(db, "UPDATE meta SET value = 'old' WHERE key = 'usage_derive_version'")
        again = refresh_usage_source(db, source, host="codex")
        assert again["status"] == "incomplete" and again["raw_events"] == 0
        assert again["reason"].startswith("checkpoint_") or again["reason"] == "derive_pending"
        _sql(
            db,
            "UPDATE meta SET value = ? WHERE key = 'usage_derive_version'",
            (lifecycle._USAGE_DERIVE_VERSION,),
        )
        conn = connect(db)
        try:
            conn.execute("BEGIN IMMEDIATE")
            head = uss.read_source_head(conn, str(source))
            assert head is not None
            uss.record_source_pending(
                conn,
                uss.SourcePending(head.scope, "native_conflict", "native_conflict"),
                expected_head_revision=head.revision,
            )
            conn.commit()
        finally:
            conn.close()
        again = refresh_usage_source(db, source, host="codex")
        assert (again["status"], again["reason"]) == ("incomplete", "native_conflict")
        assert usage_source_freshness(db, source)["status"] == "unknown"


class TestRawOnlyAndHeader:
    def test_raw_only_bootstrap_derives_and_a_failure_does_not_certify(
        self, tmp_path: Path
    ) -> None:
        tmp = tmp_path.resolve()
        db = tmp / "h.db"
        ensure_db(db)
        source = tmp / "session.jsonl"
        source.write_text("\n".join(_records()[:2]) + "\n{broken\n")
        backfill_raw_events(db, jsonl_files=[source], host="claude-code")
        assert backfill_usage_incremental(db) == 1  # bootstrap proceeds
        assert _completion(db, source).basis == "none"


class TestRawOnlyOwners:
    def _source(self, tmp_path: Path) -> tuple[Path, Path]:
        tmp = tmp_path.resolve()
        source = tmp / "session.jsonl"
        source.write_text("\n".join(_records()[:2]) + "\n")
        return tmp / "h.db", source

    def _refuse(self, monkeypatch: pytest.MonkeyPatch, marker: str) -> None:
        real = lifecycle.sanitize_history_payload

        def refuse(payload: dict[str, Any], **kw: Any) -> Any:
            if marker in json.dumps(payload):
                raise HistorySanitizationError("key_collision")
            return real(payload, **kw)

        monkeypatch.setattr(lifecycle, "sanitize_history_payload", refuse)

    def test_raw_only_refusal_after_valid_lines_rolls_back_and_records_a_diagnostic(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, source = self._source(tmp_path)
        ensure_db(db)
        before_ts = _sql(db, "SELECT value FROM meta WHERE key = 'last_raw_event_ts'")
        self._refuse(monkeypatch, "assistant")
        with pytest.raises(HistorySanitizationError):
            backfill_raw_events(db, jsonl_files=[source], host="claude-code")
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(0,)]
        assert _sql(db, "SELECT value FROM meta WHERE key = 'last_raw_event_ts'") == before_ts
        assert ("acquisition_failure", "sanitization_refused") in _obligations(db, source)
        assert _sql(db, "SELECT refusal_code FROM usage_source_pending") == [("key_collision",)]

    def test_full_backfill_rolls_back_every_write_before_the_diagnostic(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, source = self._source(tmp_path)
        issues = tmp_path.resolve() / "issues"
        issues.mkdir()
        self._refuse(monkeypatch, "assistant")
        with pytest.raises(HistorySanitizationError):
            lifecycle.backfill(
                db,
                issues_dir=issues,
                loops_dir=tmp_path / "none",
                jsonl_files=[source],
                host="claude-code",
                registry_dir=tmp_path / "none",
            )
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(0,)]
        assert ("acquisition_failure", "sanitization_refused") in _obligations(db, source)

    def test_refused_range_clears_only_after_a_successful_reingest(
        self, claude: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, source = claude
        with monkeypatch.context() as patcher:
            self._refuse(patcher, "assistant")
            with pytest.raises(HistorySanitizationError):
                refresh_usage_source(db, source)
        assert ("acquisition_failure", "sanitization_refused") in _obligations(db, source)
        assert _completion(db, source).status == "unprovable"
        result = refresh_usage_source(db, source)  # the refusal is gone: same continuity
        assert result["status"] == "complete"
        assert _obligations(db, source) == []
        assert _completion(db, source).basis == "semantic"

    def test_codex_header_followed_by_invalid_utf8_is_accounted_before_any_yield(
        self, tmp_path: Path
    ) -> None:
        tmp = tmp_path.resolve()
        db, source = tmp / "h.db", tmp / "rollout-x.jsonl"
        header = _CODEX.read_text().splitlines(keepends=True)[0]
        source.write_bytes(header.encode() + b"\xff\xfe" + _SECRET.encode() + b"\n")
        with pytest.raises((UnicodeDecodeError, ValueError)):
            backfill_raw_events(db, jsonl_files=[source], host="codex")
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(0,)]
        assert ("acquisition_failure", "decode_failure") in _obligations(db, source)
        assert _SECRET.encode() not in _dump(db)
        fresh = usage_source_freshness(db, source)  # no cursor: still has a durable reason
        assert (fresh["status"], fresh["reason"]) == ("unknown", "decode_failure")

    def test_successful_raw_only_ingestion_records_rejected_lines_with_its_inserts(
        self, tmp_path: Path
    ) -> None:
        db, source = self._source(tmp_path)
        with source.open("a") as handle:
            handle.write("{broken " + _SECRET + "\n")
        assert backfill_raw_events(db, jsonl_files=[source], host="claude-code") == 2
        assert ("acquisition_failure", "json_failure") in _obligations(db, source)
        assert _SECRET.encode() not in _dump(db)
        assert backfill_usage_incremental(db) >= 0
        assert _completion(db, source).basis == "none"

    def test_accounting_failure_does_not_roll_back_valid_ingestion(self, tmp_path: Path) -> None:
        db, source = self._source(tmp_path)
        assert backfill_raw_events(db, jsonl_files=[source], host="claude-code") == 2
        assert _obligations(db, source) == []


class TestDecodeGapRecovery:
    """A rejected line clears only via full re-acquisition from zero plus a verified prefix."""

    def _gapped(self, tmp_path: Path) -> tuple[Path, Path]:
        tmp = tmp_path.resolve()
        db, source = tmp / "h.db", tmp / "session.jsonl"
        records = _records()
        # Line 3 is malformed; later lines are long enough that the cursor's 64-byte tail
        # witness at the committed offset never covers the repaired line.
        source.write_text("\n".join(records[:2]) + "\n{broken\n" + "\n".join(records[2:]) + "\n")
        refresh_usage_source(db, source)
        assert ("acquisition_failure", "json_failure") in _obligations(db, source)
        return db, source

    def test_repairing_the_gap_with_an_intact_prefix_clears_the_marker(
        self, tmp_path: Path
    ) -> None:
        db, source = self._gapped(tmp_path)
        text = source.read_text().replace("{broken\n", '{"a":1}\n', 1)
        source.write_text(text)
        result = refresh_usage_source(db, source)
        assert result["status"] == "complete", result
        assert _obligations(db, source) == []
        assert _completion(db, source).basis == "semantic"
        # The repaired line was ingested by the re-acquisition.
        assert _sql(db, "SELECT COUNT(*) FROM raw_events WHERE line_no = 3") == [(1,)]

    def test_an_unrepaired_gap_keeps_the_marker_across_refreshes(self, tmp_path: Path) -> None:
        db, source = self._gapped(tmp_path)
        refresh_usage_source(db, source)
        refresh_usage_source(db, source)
        assert ("acquisition_failure", "json_failure") in _obligations(db, source)

    def test_a_pruned_prefix_keeps_the_marker_even_when_the_gap_is_repaired(
        self, tmp_path: Path
    ) -> None:
        db, source = self._gapped(tmp_path)
        _sql(db, "DELETE FROM raw_events WHERE line_no = 1")  # prior prefix is uncheckable
        source.write_text(source.read_text().replace("{broken\n", '{"a":1}\n', 1))
        refresh_usage_source(db, source)
        assert ("acquisition_failure", "json_failure") in _obligations(db, source)
        assert _completion(db, source).basis == "none"

    def test_deleting_the_bad_line_shifts_positions_and_does_not_clear(
        self, tmp_path: Path
    ) -> None:
        db, source = self._gapped(tmp_path)
        source.write_text(source.read_text().replace("{broken\n", "", 1))
        try:
            refresh_usage_source(db, source)
        except RuntimeError:
            pass  # a shifted prefix may be refused outright; either way nothing is certified
        assert ("acquisition_failure", "json_failure") in _obligations(db, source)
        assert _completion(db, source).basis == "none"

    def test_parser_refresh_failure_before_commit_rolls_back_invalidation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.session_store import usage_refresh

        tmp = tmp_path.resolve()
        db, source = tmp / "h.db", tmp / "session.jsonl"
        source.write_text((_CLAUDE / "transcript-v2.1.284.jsonl").read_text())
        refresh_usage_source(db, source)
        before = _completion(db, source)
        _sql(
            db, "UPDATE raw_events SET usage_contract = NULL WHERE source_path = ?", (str(source),)
        )
        handle = SessionHandle("claude-code", "s", source, tmp, source.stat().st_mtime)
        monkeypatch.setattr(
            usage_refresh,
            "_record_replacement_acquisition",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("before commit")),
        )
        with pytest.raises(RuntimeError, match="before commit"):
            refresh_raw_events(db, handles=[handle])
        assert _completion(db, source) == before
        assert _obligations(db, source) == []
        assert _sql(db, "SELECT COUNT(*) FROM usage_events WHERE channel = 'transcript'")[0][0] > 0

    def test_partial_rebuild_does_not_count_as_refresh_acknowledgement(
        self, tmp_path: Path
    ) -> None:
        tmp = tmp_path.resolve()
        db, source = tmp / "h.db", tmp / "session.jsonl"
        source.write_text("\n".join(_records()[:2]) + "\n")
        refresh_usage_source(db, source)
        # A parser refresh left cache + usage work; a bounded rebuild must not hide it.
        conn = connect(db)
        try:
            conn.execute("BEGIN IMMEDIATE")
            head = uss.read_source_head(conn, str(source))
            assert head is not None
            uss.invalidate_usage_dependencies(conn, (), (head.scope,), reason="parser_refresh")
            conn.commit()
        finally:
            conn.close()
        assert _completion(db, source).outstanding == "both"
        rebuild(db, max_sessions=0)
        # max_sessions limits summary compaction only: the deterministic caches consumed all
        # retained raw, and guarded usage replay resolved its own component.
        done = _completion(db, source)
        assert (done.status, done.outstanding) == ("complete", "none")  # republished from proof


class TestCodexGapRecovery:
    def _corrupt(self, text: str, index: int) -> str:
        lines = text.splitlines(keepends=True)
        body = lines[index].rstrip("\n")
        lines[index] = "{" + "x" * (len(body) - 1) + "\n"  # same length, invalid JSON
        return "".join(lines)

    def test_codex_rejected_line_is_sticky_until_a_verified_repair(self, tmp_path: Path) -> None:
        tmp = tmp_path.resolve()
        db, source = tmp / "h.db", tmp / "rollout.jsonl"
        original = _CODEX.read_text()
        source.write_text(self._corrupt(original, 3))
        result = refresh_usage_source(db, source, host="codex")
        assert result["status"] == "incomplete"
        assert ("acquisition_failure", "json_failure") in _obligations(db, source)
        refresh_usage_source(db, source, host="codex")
        assert ("acquisition_failure", "json_failure") in _obligations(db, source)
        assert _completion(db, source).basis == "none"
        source.write_text(original)  # byte-identical repair of the failed range
        result = refresh_usage_source(db, source, host="codex")
        # The failure marker clears (full re-acquisition matched the retained prefix), but
        # the repaired line now has a later raw ID than its neighbors: ENH-3744 cannot prove
        # Codex order, so completion stays pending until reconciliation (ENH-3770).
        assert not any(kind == "acquisition_failure" for kind, _ in _obligations(db, source))
        assert (result["status"], result["reason"]) == ("incomplete", "usage_proof_unprovable")
        assert _completion(db, source).basis == "none"

    def test_codex_pruned_prefix_cannot_extend_semantic_completion(self, tmp_path: Path) -> None:
        tmp = tmp_path.resolve()
        db, source = tmp / "h.db", tmp / "rollout.jsonl"
        lines = _CODEX.read_text().splitlines(keepends=True)
        source.write_text("".join(lines[:6]))
        refresh_usage_source(db, source, host="codex")
        older = _completion(db, source).boundary
        _sql(db, "DELETE FROM raw_events WHERE line_no = 2")  # retained prefix pruned
        with source.open("a") as handle:
            handle.writelines(lines[6:])
        refresh_usage_source(db, source, host="codex")
        done = _completion(db, source)
        assert done.basis == "none" and done.boundary == older


class TestAcquisitionStaging:
    """ENH-3770: verified acquisition is staged before reconciliation, then reused."""

    _WITNESS = uss.AcquisitionWitness(1, 2, 100, 3, "ab")

    @staticmethod
    def _open(tmp_path: Path) -> sqlite3.Connection:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        conn.execute("BEGIN IMMEDIATE")
        return conn

    def _attempt(self, conn: sqlite3.Connection, source: str = "/s.jsonl") -> tracking.Attempt:
        attempt = tracking.begin_attempt(
            conn, source, lifecycle._USAGE_DERIVE_VERSION, host="claude-code", session_id="sess"
        )
        assert attempt is not None
        return attempt

    def _finalize(
        self,
        conn: sqlite3.Connection,
        attempt: tracking.Attempt,
        accounting: tracking.PhysicalAccounting,
    ) -> tracking.FinalizeResult:
        return tracking.finalize_source_refresh(
            conn,
            attempt,
            accounting=accounting,
            witness=self._WITNESS,
            coverage_proved=True,
            derive_status="derived",
            derive_reason=None,
            held_skipped=(),
            source_max_raw_id=0,
            now="2026-10-08T00:00:00Z",
        )

    def test_staging_creates_the_head_and_acquisition_without_completion(
        self, tmp_path: Path
    ) -> None:
        conn = self._open(tmp_path)
        try:
            attempt = self._attempt(conn)
            accounting = tracking.PhysicalAccounting(100, 4)
            staged = tracking.stage_source_acquisition(
                conn, attempt, accounting=accounting, witness=self._WITNESS, coverage_proved=True
            )
            assert staged is not None
            head = uss.read_source_head(conn, "/s.jsonl")
            assert head is not None and head.revision == staged.head_revision
            assert (head.status, head.reason) == ("pending", "not_yet_derived")
            assert (head.acquired_offset, head.acquired_line_no) == (100, 4)
            assert head.scope.generation_id == attempt.scope.generation_id
            assert head.successful is None  # acquisition alone never publishes completion
            assert uss.read_source_derive_completion(conn, "/s.jsonl").basis == "none"
        finally:
            conn.rollback()
            conn.close()

    def test_unproved_coverage_stages_nothing(self, tmp_path: Path) -> None:
        conn = self._open(tmp_path)
        try:
            staged = tracking.stage_source_acquisition(
                conn,
                self._attempt(conn),
                accounting=tracking.PhysicalAccounting(100, 4),
                witness=self._WITNESS,
                coverage_proved=False,
            )
            assert staged is None
            assert uss.read_source_head(conn, "/s.jsonl") is None
        finally:
            conn.rollback()
            conn.close()

    def test_unclean_accounting_and_missing_attempt_stage_nothing(self, tmp_path: Path) -> None:
        conn = self._open(tmp_path)
        try:
            rejected = tracking.PhysicalAccounting(
                100, 4, (tracking.RejectedRange("json_failure", 2, 2, 10, 20),)
            )
            assert (
                tracking.stage_source_acquisition(
                    conn,
                    self._attempt(conn),
                    accounting=rejected,
                    witness=self._WITNESS,
                    coverage_proved=True,
                )
                is None
            )
            assert (
                tracking.stage_source_acquisition(
                    conn,
                    None,
                    accounting=tracking.PhysicalAccounting(100, 4),
                    witness=self._WITNESS,
                    coverage_proved=True,
                )
                is None
            )
            assert uss.read_source_head(conn, "/s.jsonl") is None
        finally:
            conn.rollback()
            conn.close()

    def test_restaging_an_identical_acquisition_writes_nothing(self, tmp_path: Path) -> None:
        conn = self._open(tmp_path)
        try:
            attempt = self._attempt(conn)
            accounting = tracking.PhysicalAccounting(100, 4)
            first = tracking.stage_source_acquisition(
                conn, attempt, accounting=accounting, witness=self._WITNESS, coverage_proved=True
            )
            again = tracking.stage_source_acquisition(
                conn,
                self._attempt(conn),
                accounting=accounting,
                witness=self._WITNESS,
                coverage_proved=True,
            )
            assert first is not None and again is not None
            assert again.head_revision == first.head_revision
            assert uss.head_revision(conn, "/s.jsonl") == first.head_revision
        finally:
            conn.rollback()
            conn.close()

    def test_advanced_acquisition_restages_with_a_new_revision(self, tmp_path: Path) -> None:
        conn = self._open(tmp_path)
        try:
            attempt = self._attempt(conn)
            first = tracking.stage_source_acquisition(
                conn,
                attempt,
                accounting=tracking.PhysicalAccounting(100, 4),
                witness=self._WITNESS,
                coverage_proved=True,
            )
            later = tracking.stage_source_acquisition(
                conn,
                self._attempt(conn),
                accounting=tracking.PhysicalAccounting(180, 7),
                witness=uss.AcquisitionWitness(1, 2, 180, 3, "cd"),
                coverage_proved=True,
            )
            assert first is not None and later is not None
            assert later.head_revision == first.head_revision + 1
            head = uss.read_source_head(conn, "/s.jsonl")
            assert head is not None and (head.acquired_offset, head.acquired_line_no) == (180, 7)
        finally:
            conn.rollback()
            conn.close()

    def test_finalize_reuses_a_staged_acquisition_without_a_second_write(
        self, tmp_path: Path
    ) -> None:
        conn = self._open(tmp_path)
        try:
            attempt = self._attempt(conn)
            accounting = tracking.PhysicalAccounting(100, 4)
            staged = tracking.stage_source_acquisition(
                conn, attempt, accounting=accounting, witness=self._WITNESS, coverage_proved=True
            )
            assert staged is not None
            result = self._finalize(conn, attempt, accounting)
            assert result.complete
            # staging inserted revision 1; finalize only published completion (one bump).
            assert uss.head_revision(conn, "/s.jsonl") == staged.head_revision + 1
            assert uss.read_source_derive_completion(conn, "/s.jsonl").basis == "semantic"
        finally:
            conn.rollback()
            conn.close()

    def test_unchanged_retry_finalize_does_not_restage_a_matching_acquisition(
        self, tmp_path: Path
    ) -> None:
        conn = self._open(tmp_path)
        try:
            attempt = self._attempt(conn)
            accounting = tracking.PhysicalAccounting(100, 4)
            assert self._finalize(conn, attempt, accounting).complete
            before = uss.head_revision(conn, "/s.jsonl")
            retry = self._finalize(conn, self._attempt(conn), accounting)
            assert retry.complete
            # No acquisition rewrite: only the completion publication bumps the head.
            assert uss.head_revision(conn, "/s.jsonl") == (before or 0) + 1
        finally:
            conn.rollback()
            conn.close()

    def test_rollback_restores_every_staged_fact(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            conn.execute("BEGIN IMMEDIATE")
            attempt = self._attempt(conn)
            tracking.stage_source_acquisition(
                conn,
                attempt,
                accounting=tracking.PhysicalAccounting(100, 4),
                witness=self._WITNESS,
                coverage_proved=True,
            )
            conn.rollback()
            assert conn.execute("SELECT COUNT(*) FROM usage_source_state").fetchone()[0] == 0
        finally:
            conn.close()
