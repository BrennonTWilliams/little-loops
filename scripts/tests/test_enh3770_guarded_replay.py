"""ENH-3770: guarded replay -- compare before mutate, plan before pricing (public-call controls)."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from little_loops.pricing import estimate_cost_usd
from little_loops.session_store import (
    backfill_raw_events,
    backfill_usage_incremental,
    connect,
    ensure_db,
    lifecycle,
)
from little_loops.session_store.writers import _backfill_usage_events

_FIXTURES = Path(__file__).parent / "fixtures"
_CLAUDE = _FIXTURES / "claude" / "transcript-v2.1.284.jsonl"
_CHANGING = _FIXTURES / "claude" / "transcript-changing-usage-observed.jsonl"
_CODEX = _FIXTURES / "codex" / "rollout-exec-resume-v0.158.0.jsonl"

_COLUMNS = (
    "id, ts, session_id, model, input_tokens, output_tokens, cache_read_input_tokens, "
    "cache_creation_input_tokens, cost_usd, run_id, channel, provenance, host, "
    "observation_key, usage_contract, source_raw_event_id, source_path, source_line_no, "
    "source_ordinal, request_id, turn_id, observed_at"
)


def _priced() -> Any:
    """Pricing that fails the test when invoked."""
    return patch("little_loops.pricing.estimate_cost_usd", side_effect=AssertionError("priced"))


def _rows(db: Path) -> list[tuple]:
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(
            f"SELECT {_COLUMNS} FROM usage_events WHERE channel IS NOT 'live' ORDER BY id"
        ).fetchall()
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


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n")
    return path


def _ingest(db: Path, source: Path, host: str) -> None:
    backfill_raw_events(db, jsonl_files=[source], host=host)


def _replay_all(db: Path) -> int:
    """Replay every retained raw row through the shared writer (what rebuild/catch-up do)."""
    conn = connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        count = lifecycle._backfill_usage_events(conn, lifecycle._usage_raw_cursor(conn))
        conn.commit()
        return count
    finally:
        conn.close()


def _lines(path: Path) -> list[str]:
    return path.read_text().splitlines()


def _bump_output(lines: list[str], by: int = 1) -> list[str]:
    out = []
    for line in lines:
        record = json.loads(line)
        usage = record.get("message", {}).get("usage")
        if isinstance(usage, dict) and isinstance(usage.get("output_tokens"), int):
            usage["output_tokens"] += by
        out.append(json.dumps(record))
    return out


def _bump_codex_output(lines: list[str], by: int = 1) -> list[str]:
    """Codex rollout copy whose response usage disagrees with the original's."""
    out = []
    for line in lines:
        record = json.loads(line)
        payload = record.get("payload", record)
        usage = payload.get("usage")
        if isinstance(usage, dict) and "output_tokens" in usage:
            usage["output_tokens"] += by
        info = payload.get("info")
        if isinstance(info, dict):
            for key in ("last_token_usage", "total_token_usage"):
                if isinstance(info.get(key), dict) and "output_tokens" in info[key]:
                    info[key]["output_tokens"] += by
        out.append(json.dumps(record))
    return out


class TestClaudeGuardedReplay:
    def _derived(self, tmp_path: Path, fixture: Path = _CLAUDE, name: str = "a.jsonl") -> tuple:
        db = tmp_path / "history.db"
        source = tmp_path / name
        shutil.copy(fixture, source)
        _ingest(db, source, "claude-code")
        backfill_usage_incremental(db)
        return db, source

    def test_unchanged_replay_is_a_noop_that_never_prices(self, tmp_path: Path) -> None:
        db, _ = self._derived(tmp_path)
        before = _rows(db)
        assert len(before) == 2
        with _priced():
            assert _replay_all(db) == 0
        assert _rows(db) == before

    def test_newer_snapshot_replaces_in_place_and_prices_once(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        source = _write(tmp_path / "s.jsonl", _lines(_CHANGING)[:2])
        _ingest(db, source, "claude-code")
        backfill_usage_incremental(db)
        (before,) = _rows(db)
        with source.open("a") as handle:
            handle.write("\n".join(_lines(_CHANGING)[2:]) + "\n")
        _ingest(db, source, "claude-code")
        with patch("little_loops.pricing.estimate_cost_usd", wraps=estimate_cost_usd) as spy:
            assert backfill_usage_incremental(db) == 0  # a replacement is not a new observation
        assert spy.call_count == 1  # only the final selected snapshot is priced
        (after,) = _rows(db)
        assert after[0] == before[0]  # row identity preserved
        assert after[5] == 481 and before[5] == 4
        assert after[16] == before[16] and after[17] == 5  # supplier is the newest native line

    def test_older_native_position_with_a_larger_raw_id_cannot_roll_back(
        self, tmp_path: Path
    ) -> None:
        db, source = self._derived(tmp_path, _CHANGING, "s.jsonl")
        (before,) = _rows(db)
        assert before[5] == 481
        # Re-ingest an older snapshot (line 3) so it carries a larger raw id than line 5.
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT ts, session_id, host, host_basis, source_path, line_no, event_type, "
                "raw_line, parsed_json, usage_contract, compacted FROM raw_events WHERE line_no = 3"
            ).fetchone()
            conn.execute("DELETE FROM raw_events WHERE line_no = 3")
            conn.execute(
                "INSERT INTO raw_events(ts, session_id, host, host_basis, source_path, line_no, "
                "event_type, raw_line, parsed_json, usage_contract, compacted) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            conn.commit()
        finally:
            conn.close()
        assert _sql(db, "SELECT MAX(id) FROM raw_events WHERE line_no = 3") > _sql(
            db, "SELECT id FROM raw_events WHERE line_no = 5"
        )
        with _priced():
            assert _replay_all(db) == 0
        assert _rows(db) == [before]

    def test_payload_envelope_session_disagreement_creates_no_row(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        source = tmp_path / "a.jsonl"
        shutil.copy(_CLAUDE, source)
        _ingest(db, source, "claude-code")
        _sql(db, "UPDATE raw_events SET session_id = 'other-session'")
        with _priced():
            assert backfill_usage_incremental(db) == 0
        assert _rows(db) == []

    def test_disagreement_never_mutates_existing_protected_values(self, tmp_path: Path) -> None:
        db, _ = self._derived(tmp_path)
        before = _rows(db)
        _sql(db, "UPDATE raw_events SET session_id = 'other-session'")
        with _priced():
            assert _replay_all(db) == 0
        assert _rows(db) == before

    def test_already_linked_unkeyed_audit_replays_without_a_duplicate(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        source = tmp_path / "a.jsonl"
        shutil.copy(_CLAUDE, source)
        _ingest(db, source, "claude-code")
        _sql(db, "UPDATE raw_events SET usage_contract = NULL")
        backfill_usage_incremental(db)
        before = _rows(db)
        assert len(before) == 4 and {row[11] for row in before} == {"unknown"}
        with _priced():
            assert _replay_all(db) == 0  # no duplicate and no unique-index failure
        assert _rows(db) == before

    def test_rawless_direct_file_input_writes_nothing_and_never_prices(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            conn.execute("BEGIN IMMEDIATE")
            with _priced():
                assert _backfill_usage_events(conn, [_CLAUDE]) == 0
            conn.commit()
        finally:
            conn.close()
        assert _rows(db) == []

    def test_cross_source_conflict_demotes_qualification_only(self, tmp_path: Path) -> None:
        db, _ = self._derived(tmp_path)
        before = _rows(db)
        other = _write(tmp_path / "b.jsonl", _bump_output(_lines(_CLAUDE)))
        _ingest(db, other, "claude-code")
        with _priced():  # a conflicting copy is never priced
            assert backfill_usage_incremental(db) == 2
        after = _rows(db)
        originals = after[:2]
        for old, new in zip(before, originals, strict=True):
            # identity, numbers, cost, timestamps and supplier survive; only provenance changes
            assert new[:11] == old[:11] and new[12] == old[12]
            assert new[13] == old[13] and new[15:] == old[15:]
            assert (old[11], new[11], new[14]) == ("measured", "unknown", None)
        copies = after[2:]
        assert len(copies) == 2
        assert {row[16] for row in copies} == {str(other)}
        assert {(row[11], row[13], row[14], row[8]) for row in copies} == {
            ("unknown", None, None, None)
        }
        assert sorted(row[5] for row in copies) == sorted(row[5] + 1 for row in originals)

    @pytest.mark.parametrize("order", [("a.jsonl", "b.jsonl"), ("b.jsonl", "a.jsonl")])
    def test_first_derivation_conflicts_are_recognized_before_any_priced_insert(
        self, tmp_path: Path, order: tuple[str, str]
    ) -> None:
        db = tmp_path / "history.db"
        files = {
            "a.jsonl": _write(tmp_path / "a.jsonl", _lines(_CLAUDE)),
            "b.jsonl": _write(tmp_path / "b.jsonl", _bump_output(_lines(_CLAUDE))),
        }
        for name in order:
            _ingest(db, files[name], "claude-code")
        with _priced():
            assert backfill_usage_incremental(db) == 4
        rows = _rows(db)
        assert len(rows) == 4
        assert {(row[11], row[13], row[14], row[8]) for row in rows} == {
            ("unknown", None, None, None)
        }
        assert {row[16] for row in rows} == {str(files["a.jsonl"]), str(files["b.jsonl"])}

    def test_repeated_replay_cannot_restore_a_proved_conflict(self, tmp_path: Path) -> None:
        db, _ = self._derived(tmp_path)
        other = _write(tmp_path / "b.jsonl", _bump_output(_lines(_CLAUDE)))
        _ingest(db, other, "claude-code")
        backfill_usage_incremental(db)
        settled = _rows(db)
        with _priced():
            assert _replay_all(db) == 0
            assert _replay_all(db) == 0
        assert _rows(db) == settled
        assert {row[11] for row in settled[:2]} == {"unknown"}

    def test_identical_copy_shares_representation_and_keeps_the_first_supplier(
        self, tmp_path: Path
    ) -> None:
        db, first = self._derived(tmp_path)
        before = _rows(db)
        copy = _write(tmp_path / "b.jsonl", _lines(_CLAUDE))
        _ingest(db, copy, "claude-code")
        with _priced():
            assert backfill_usage_incremental(db) == 0
        assert _rows(db) == before
        assert {row[16] for row in _rows(db)} == {str(first)}


class TestCodexGuardedReplay:
    def _derived(self, tmp_path: Path, count: int | None = None, name: str = "r.jsonl") -> tuple:
        db = tmp_path / "history.db"
        lines = _lines(_CODEX)
        source = _write(tmp_path / name, lines if count is None else lines[:count])
        _ingest(db, source, "codex")
        backfill_usage_incremental(db)
        return db, source

    def test_closure_arriving_later_qualifies_the_same_row_once(self, tmp_path: Path) -> None:
        db, source = self._derived(tmp_path, 4)
        (before,) = _rows(db)
        assert before[11] == "unknown" and before[8] is None  # no closure yet: audit, unpriced
        with source.open("a") as handle:
            handle.write("\n".join(_lines(_CODEX)[4:6]) + "\n")  # duplicate notification + close
        _ingest(db, source, "codex")
        with patch("little_loops.pricing.estimate_cost_usd", wraps=estimate_cost_usd) as spy:
            assert backfill_usage_incremental(db) == 0
        (after,) = _rows(db)
        assert after[0] == before[0]  # same request row
        assert (after[1], after[4:8], after[15:19]) == (before[1], before[4:8], before[15:19])
        assert after[11] == "measured" and after[3]  # qualification facts only
        assert spy.call_count == 1  # a newly eligible unpriced request is priced exactly once
        with _priced():
            assert _replay_all(db) == 0  # and never again
        assert _rows(db) == [after]

    def test_unchanged_codex_replay_preserves_rows_and_never_prices(self, tmp_path: Path) -> None:
        db, _ = self._derived(tmp_path)
        before = _rows(db)
        assert len(before) == 2 and {row[11] for row in before} == {"measured"}
        with _priced():
            assert _replay_all(db) == 0
        assert _rows(db) == before

    def test_new_turn_append_keeps_existing_rows_and_inserts_only_the_new_request(
        self, tmp_path: Path
    ) -> None:
        db, source = self._derived(tmp_path, 6)
        (before,) = _rows(db)
        with source.open("a") as handle:
            handle.write("\n".join(_lines(_CODEX)[6:]) + "\n")
        _ingest(db, source, "codex")
        assert backfill_usage_incremental(db) == 1
        rows = _rows(db)
        assert len(rows) == 2 and rows[0] == before

    def test_identical_copy_from_another_source_shares_the_survivor(self, tmp_path: Path) -> None:
        db, first = self._derived(tmp_path)
        before = _rows(db)
        copy = _write(tmp_path / "copy.jsonl", _lines(_CODEX))
        _ingest(db, copy, "codex")
        with _priced():
            assert backfill_usage_incremental(db) == 0
        assert _rows(db) == before
        assert {row[16] for row in _rows(db)} == {str(first)}

    def test_conflicting_copy_demotes_committed_rows_and_is_kept_unpriced(
        self, tmp_path: Path
    ) -> None:
        db, _ = self._derived(tmp_path)
        before = _rows(db)
        lines = []
        for line in _lines(_CODEX):
            record = json.loads(line)
            payload = record.get("payload", record)
            usage = payload.get("usage")
            if isinstance(usage, dict) and "output_tokens" in usage:
                usage["output_tokens"] += 1
            info = payload.get("info")
            if isinstance(info, dict):
                for key in ("last_token_usage", "total_token_usage"):
                    if isinstance(info.get(key), dict) and "output_tokens" in info[key]:
                        info[key]["output_tokens"] += 1
            lines.append(json.dumps(record))
        copy = _write(tmp_path / "copy.jsonl", lines)
        _ingest(db, copy, "codex")
        with _priced():
            assert backfill_usage_incremental(db) == 2
        after = _rows(db)
        for old, new in zip(before, after[:2], strict=True):
            assert new[:11] == old[:11] and new[12:] == old[12:]
            assert (old[11], new[11]) == ("measured", "unknown")
        assert {row[16] for row in after[2:]} == {str(copy)}
        assert {(row[11], row[8]) for row in after[2:]} == {("unknown", None)}
        with _priced():
            assert _replay_all(db) == 0
        assert _rows(db) == after

    def test_equal_counts_with_an_incompatible_model_are_not_an_identical_copy(
        self, tmp_path: Path
    ) -> None:
        db, _ = self._derived(tmp_path)
        lines = []
        for line in _lines(_CODEX):
            record = json.loads(line)
            payload = record.get("payload", record)
            if "model" in payload:
                payload["model"] = "another-model"
            lines.append(json.dumps(record))
        copy = _write(tmp_path / "copy.jsonl", lines)
        _ingest(db, copy, "codex")
        with _priced():
            backfill_usage_incremental(db)
        rows = _rows(db)
        assert len(rows) == 4
        assert {row[11] for row in rows} == {"unknown"}


_OLD = "2020-01-01T00:00:00Z"
_PRUNE_CFG = {
    "analytics": {
        "retention": {
            "raw_event_max_age_days": 1,
            "min_project_age_days": 0,
            "min_db_size_mb": 0,
        }
    }
}


def _pending(db: Path, source: Path | None = None) -> list[tuple]:
    where = " WHERE source_path = ?" if source is not None else ""
    params = (str(source),) if source is not None else ()
    return _sql(
        db,
        "SELECT source_path, kind, reason, range_kind, first_raw_id, last_raw_id, revision, "
        f"usage_pending, raw_cache_pending FROM usage_source_pending{where} ORDER BY obligation_id",
        params,
    )


def _head_revision(db: Path, source: Path) -> int | None:
    rows = _sql(db, "SELECT revision FROM usage_source_state WHERE source_path = ?", (str(source),))
    return rows[0][0] if rows else None


class TestHeldSourceAdditiveDerive:
    def _pruned(self, tmp_path: Path) -> tuple[Path, Path, list[tuple]]:
        db = tmp_path / "history.db"
        source = tmp_path / "held.jsonl"
        shutil.copy(_CLAUDE, source)
        _ingest(db, source, "claude-code")
        backfill_usage_incremental(db)
        _sql(db, "UPDATE raw_events SET compacted = 1, ts = ?", (_OLD,))
        from little_loops.session_store import prune

        result = prune(db, config=_PRUNE_CFG)
        assert result["deleted"] == {"raw_events": 4}
        assert _sql(db, "SELECT COUNT(*) FROM usage_replay_holds") == [(1,)]
        return db, source, _rows(db)

    def test_proved_distinct_append_derives_while_protection_and_rows_survive(
        self, tmp_path: Path
    ) -> None:
        db, source, before = self._pruned(tmp_path)
        # A new raw row for the held source (the pruned prefix stays gone).
        sess = before[0][2]
        record = json.loads(_lines(_CLAUDE)[0])
        record["message"]["id"] = "msg_after_prune"
        _sql(
            db,
            "INSERT INTO raw_events(ts, session_id, host, host_basis, source_path, line_no, "
            "event_type, raw_line, parsed_json, usage_contract) "
            "VALUES('2026-09-29T07:30:00Z', ?, 'claude-code', 'handle', ?, 5, 'assistant', ?, ?, "
            "'claude-code/2.1.284')",
            (sess, str(source), json.dumps(record), json.dumps(record)),
        )
        with patch("little_loops.pricing.estimate_cost_usd", wraps=estimate_cost_usd) as spy:
            assert backfill_usage_incremental(db) == 1
        assert spy.call_count == 1  # only the new request is priced
        after = _rows(db)
        assert after[: len(before)] == before  # protected rows are untouched
        assert len(after) == len(before) + 1 and after[-1][11] == "measured"
        assert _sql(db, "SELECT COUNT(*) FROM usage_replay_holds") == [(1,)]  # hold survives
        with _priced():
            assert _replay_all(db) == 0
        assert _rows(db) == after

    def test_wildcard_population_hold_keeps_new_requests_conservative(self, tmp_path: Path) -> None:
        db, source, before = self._pruned(tmp_path)
        _sql(
            db,
            "INSERT INTO usage_replay_holds(source_path, host, channel, reason, created_at) "
            "VALUES(NULL, '*', '*', 'legacy_population', '2026-01-01T00:00:00Z')",
        )
        record = json.loads(_lines(_CLAUDE)[0])
        record["message"]["id"] = "msg_ambiguous"
        _sql(
            db,
            "INSERT INTO raw_events(ts, session_id, host, host_basis, source_path, line_no, "
            "event_type, raw_line, parsed_json, usage_contract) "
            "VALUES('2026-09-29T07:30:00Z', ?, 'claude-code', 'handle', ?, 5, 'assistant', ?, ?, "
            "'claude-code/2.1.284')",
            (before[0][2], str(source), json.dumps(record), json.dumps(record)),
        )
        with _priced():
            assert backfill_usage_incremental(db) == 0
        assert _rows(db) == before  # a wildcard hold cannot prove the request distinct
        assert any(row[2] == "held_source_skipped" for row in _pending(db, source))


def _reingest_older_snapshot_with_larger_raw_id(db: Path) -> int:
    """Delete and re-insert Claude line 3 so it carries the largest raw id; return that id."""
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT ts, session_id, host, host_basis, source_path, line_no, event_type, "
            "raw_line, parsed_json, usage_contract, compacted FROM raw_events WHERE line_no = 3"
        ).fetchone()
        conn.execute("DELETE FROM raw_events WHERE line_no = 3")
        cursor = conn.execute(
            "INSERT INTO raw_events(ts, session_id, host, host_basis, source_path, line_no, "
            "event_type, raw_line, parsed_json, usage_contract, compacted) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
        conn.commit()
        return int(cursor.lastrowid or 0)
    finally:
        conn.close()


class TestUnresolvedScopes:
    def _unprovable(self, tmp_path: Path) -> tuple[Path, Path, int]:
        db = tmp_path / "history.db"
        source = tmp_path / "s.jsonl"
        shutil.copy(_CHANGING, source)
        _ingest(db, source, "claude-code")
        backfill_usage_incremental(db)
        new_id = _reingest_older_snapshot_with_larger_raw_id(db)
        return db, source, new_id

    def test_unprovable_scope_records_pending_atomically_with_the_scan_advance(
        self, tmp_path: Path
    ) -> None:
        db, source, new_id = self._unprovable(tmp_path)
        (before,) = _rows(db)
        with _priced():
            assert backfill_usage_incremental(db) == 0
        assert _rows(db) == [before]  # the protected newer snapshot is not rolled back
        assert _sql(db, "SELECT value FROM meta WHERE key = 'usage_derive_raw_id'") == [
            (str(new_id),)
        ]
        (row,) = _pending(db, source)
        assert row[1:4] == ("derive_gap", "usage_proof_unprovable", "bounded")
        assert (row[4], row[5]) == (new_id, new_id) and row[7] == 1

    def test_later_sufficient_proof_resolves_work_below_the_checkpoint(
        self, tmp_path: Path
    ) -> None:
        db, source, new_id = self._unprovable(tmp_path)
        backfill_usage_incremental(db)
        assert _pending(db, source)
        # The out-of-order restore is withdrawn: nothing new is appended, the checkpoint is
        # already past every remaining row, yet the retained evidence is now sufficient.
        _sql(db, "DELETE FROM raw_events WHERE id = ?", (new_id,))
        floor = _sql(db, "SELECT value FROM meta WHERE key = 'usage_derive_raw_id'")
        assert int(floor[0][0]) >= _sql(db, "SELECT MAX(id) FROM raw_events")[0][0]
        before = _rows(db)
        with _priced():
            assert backfill_usage_incremental(db) == 0
        assert _pending(db, source) == []
        assert _rows(db) == before
        assert _sql(db, "SELECT value FROM meta WHERE key = 'usage_derive_raw_id'") == floor

    def test_identical_repeated_failure_does_not_churn_revisions(self, tmp_path: Path) -> None:
        db, source, _ = self._unprovable(tmp_path)
        backfill_usage_incremental(db)
        pending = _pending(db, source)
        head = _head_revision(db, source)
        for _ in range(3):
            backfill_usage_incremental(db)
        assert _pending(db, source) == pending
        assert _head_revision(db, source) == head

    def test_pending_and_checkpoint_publication_roll_back_together(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, source, new_id = self._unprovable(tmp_path)
        floor = _sql(db, "SELECT value FROM meta WHERE key = 'usage_derive_raw_id'")

        def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("publication failed")

        monkeypatch.setattr(lifecycle, "_publish_usage_derive_checkpoint", boom)
        with pytest.raises(RuntimeError, match="publication failed"):
            backfill_usage_incremental(db)
        assert _sql(db, "SELECT value FROM meta WHERE key = 'usage_derive_raw_id'") == floor
        assert _pending(db, source) == []  # the pending capture rolled back with it
        monkeypatch.undo()
        backfill_usage_incremental(db)
        assert _pending(db, source)

    def test_pristine_bootstrap_captures_unresolved_scopes_too(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        good = _write(tmp_path / "good.jsonl", _lines(_CLAUDE))
        bad = _write(tmp_path / "bad.jsonl", _lines(_CLAUDE))
        _ingest(db, good, "claude-code")
        _ingest(db, bad, "claude-code")
        _sql(
            db,
            "UPDATE raw_events SET session_id = 'other-session' WHERE source_path = ?",
            (str(bad),),
        )
        assert _sql(db, "SELECT COUNT(*) FROM meta WHERE key = 'usage_derive_raw_id'") == [(0,)]
        # `bad` is an identical copy of `good`, but its envelope disagrees with its payload.
        assert backfill_usage_incremental(db) == 2
        assert _sql(db, "SELECT COUNT(*) FROM meta WHERE key = 'usage_derive_raw_id'") == [(1,)]
        rows = _pending(db, bad)
        assert [r[1:3] for r in rows] == [("derive_gap", "usage_proof_unprovable")]
        assert _pending(db, good) == []

    def test_identity_disagreement_stays_pending_and_never_qualifies(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        source = _write(tmp_path / "s.jsonl", _lines(_CLAUDE))
        _ingest(db, source, "claude-code")
        _sql(db, "UPDATE raw_events SET session_id = 'other-session'")
        with _priced():
            assert backfill_usage_incremental(db) == 0
        assert _rows(db) == []
        assert any(row[2] == "usage_proof_unprovable" for row in _pending(db, source))


class TestRebuildPreservesCommittedUsage:
    def test_claude_rebuild_keeps_ids_costs_and_witnessless_rows_without_pricing(
        self, tmp_path: Path
    ) -> None:
        from little_loops.session_store import rebuild

        db = tmp_path / "history.db"
        source = _write(tmp_path / "s.jsonl", _lines(_CLAUDE))
        _ingest(db, source, "claude-code")
        backfill_usage_incremental(db)
        before = _rows(db)
        with _priced():
            assert rebuild(db)["usage_events"] == 0
            assert rebuild(db)["usage_events"] == 0
        assert _rows(db) == before

    def test_codex_rebuild_keeps_rows_and_never_prices(self, tmp_path: Path) -> None:
        from little_loops.session_store import rebuild

        db = tmp_path / "history.db"
        source = _write(tmp_path / "r.jsonl", _lines(_CODEX))
        _ingest(db, source, "codex")
        backfill_usage_incremental(db)
        before = _rows(db)
        with _priced():
            assert rebuild(db)["usage_events"] == 0
        assert _rows(db) == before

    def test_rebuild_restores_the_search_population_from_committed_rows(
        self, tmp_path: Path
    ) -> None:
        from little_loops.session_store import rebuild

        db = tmp_path / "history.db"
        source = _write(tmp_path / "s.jsonl", _lines(_CLAUDE))
        _ingest(db, source, "claude-code")
        backfill_usage_incremental(db)
        fts = "SELECT content, kind, ref, anchor, ts FROM search_index WHERE kind = 'usage'"
        before = sorted(_sql(db, fts))
        assert before
        with _priced():
            rebuild(db)
        assert sorted(_sql(db, fts)) == before

    def test_rebuild_failure_rolls_back_everything(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.session_store import rebuild

        db = tmp_path / "history.db"
        source = _write(tmp_path / "s.jsonl", _lines(_CLAUDE))
        _ingest(db, source, "claude-code")
        backfill_usage_incremental(db)
        extra = _write(tmp_path / "b.jsonl", _bump_output(_lines(_CLAUDE)))
        _ingest(db, extra, "claude-code")
        snapshot = (_rows(db), _pending(db), _sql(db, "SELECT * FROM usage_source_state"))

        def boom(*args: object, **kwargs: object) -> int:
            raise RuntimeError("compaction failed")

        monkeypatch.setattr(lifecycle, "_compact_sessions", boom)
        with pytest.raises(RuntimeError):
            rebuild(db)
        assert (_rows(db), _pending(db), _sql(db, "SELECT * FROM usage_source_state")) == snapshot


def _witnesses(db: Path) -> list[tuple]:
    return _sql(
        db,
        "SELECT usage_event_id, supplier_source_path, supplier_line_no, supplier_raw_id, "
        "value_status, qualification_status FROM usage_observation_witnesses "
        "ORDER BY usage_event_id",
    )


def _frontier(db: Path) -> list[tuple]:
    return _sql(
        db,
        "SELECT usage_event_id, role, line_no, raw_event_id FROM usage_observation_dependencies "
        "ORDER BY usage_event_id, role",
    )


class TestSupplierAndContextWitnesses:
    def test_acquired_insert_records_the_actual_supplier(self, tmp_path: Path) -> None:
        from little_loops.session_store import refresh_usage_source

        db = tmp_path / "history.db"
        source = _write(tmp_path / "s.jsonl", _lines(_CLAUDE))
        refresh_usage_source(db, source)
        rows = _rows(db)
        witnesses = _witnesses(db)
        assert [w[0] for w in witnesses] == [r[0] for r in rows]
        for row, witness in zip(rows, witnesses, strict=True):
            assert witness[1:4] == (str(source.resolve()), row[17], row[15])
            assert witness[4:] == ("known", "not_consumed")

    def test_unacquired_insert_grants_no_affirmative_witness(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        source = _write(tmp_path / "s.jsonl", _lines(_CLAUDE))
        _ingest(db, source, "claude-code")
        backfill_usage_incremental(db)  # raw-only: no verified acquisition head
        assert len(_rows(db)) == 2 and _witnesses(db) == []

    def test_replacement_moves_the_supplier_atomically(self, tmp_path: Path) -> None:
        from little_loops.session_store import refresh_usage_source

        db = tmp_path / "history.db"
        source = _write(tmp_path / "s.jsonl", _lines(_CHANGING)[:2])
        refresh_usage_source(db, source)
        ((witness,),) = [(w,) for w in _witnesses(db)]
        assert witness[2] == 2
        with source.open("a") as handle:
            handle.write("\n".join(_lines(_CHANGING)[2:]) + "\n")
        refresh_usage_source(db, source)
        (row,) = _rows(db)
        (after,) = _witnesses(db)
        assert after[0] == witness[0] == row[0]
        assert (after[2], after[3]) == (5, row[15])  # the newest native line supplies the value

    def test_codex_measured_request_records_the_consumed_context(self, tmp_path: Path) -> None:
        from little_loops.session_store import refresh_usage_source

        db = tmp_path / "history.db"
        source = _write(tmp_path / "r.jsonl", _lines(_CODEX))
        refresh_usage_source(db, source, host="codex")
        rows = _rows(db)
        assert len(rows) == 2 and {r[11] for r in rows} == {"measured"}
        assert [w[4:] for w in _witnesses(db)] == [("known", "known")] * 2
        frontier = _frontier(db)
        first = [f for f in frontier if f[0] == rows[0][0]]
        assert [(f[1], f[2]) for f in first] == [("closure", 6), ("model", 3)]
        # value supplier is the response record, not a later context row
        assert _witnesses(db)[0][2] == 4

    def test_closure_arrival_changes_only_the_context_witness(self, tmp_path: Path) -> None:
        from little_loops.session_store import refresh_usage_source

        db = tmp_path / "history.db"
        source = _write(tmp_path / "r.jsonl", _lines(_CODEX)[:4])
        refresh_usage_source(db, source, host="codex")
        (before,) = _rows(db)
        (supplier_before,) = _witnesses(db)
        assert supplier_before[4:] == ("known", "unavailable") and _frontier(db) == []
        with source.open("a") as handle:
            handle.write("\n".join(_lines(_CODEX)[4:6]) + "\n")
        refresh_usage_source(db, source, host="codex")
        (after,) = _rows(db)
        (supplier_after,) = _witnesses(db)
        assert after[0] == before[0] and after[11] == "measured"
        assert supplier_after[:4] == supplier_before[:4]  # same value supplier
        assert supplier_after[4:] == ("known", "known")
        assert [(f[1], f[2]) for f in _frontier(db)] == [("closure", 6), ("model", 3)]

    def test_noop_replay_preserves_every_witness(self, tmp_path: Path) -> None:
        from little_loops.session_store import rebuild, refresh_usage_source

        db = tmp_path / "history.db"
        source = _write(tmp_path / "r.jsonl", _lines(_CODEX))
        refresh_usage_source(db, source, host="codex")
        before = (_witnesses(db), _frontier(db), _rows(db))
        with _priced():
            rebuild(db)
            assert _replay_all(db) == 0
        assert (_witnesses(db), _frontier(db), _rows(db)) == before

    def test_conflict_demotion_keeps_the_supplier_and_marks_qualification_invalidated(
        self, tmp_path: Path
    ) -> None:
        from little_loops.session_store import refresh_usage_source

        db = tmp_path / "history.db"
        source = _write(tmp_path / "r.jsonl", _lines(_CODEX))
        refresh_usage_source(db, source, host="codex")
        supplier_before = [w[:4] for w in _witnesses(db)]
        lines = []
        for line in _lines(_CODEX):
            record = json.loads(line)
            payload = record.get("payload", record)
            usage = payload.get("usage")
            if isinstance(usage, dict) and "output_tokens" in usage:
                usage["output_tokens"] += 1
            info = payload.get("info")
            if isinstance(info, dict):
                for key in ("last_token_usage", "total_token_usage"):
                    if isinstance(info.get(key), dict) and "output_tokens" in info[key]:
                        info[key]["output_tokens"] += 1
            lines.append(json.dumps(record))
        copy = _write(tmp_path / "copy.jsonl", lines)
        refresh_usage_source(db, copy, host="codex")
        committed = [w for w in _witnesses(db) if w[0] <= 2]
        assert [w[:4] for w in committed] == supplier_before
        assert {w[4:] for w in committed} == {("known", "invalidated")}
        assert all(f[0] > 2 or f[1] in {"model", "closure"} for f in _frontier(db))


class TestReviewRegressions:
    """Defects an independent adversarial review confirmed, kept as permanent controls."""

    def _demoted_pair(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        db = tmp_path / "history.db"
        a = _write(tmp_path / "a.jsonl", _lines(_CHANGING)[:2])
        _ingest(db, a, "claude-code")
        backfill_usage_incremental(db)
        b = _write(tmp_path / "b.jsonl", _bump_output(_lines(_CHANGING)[:2]))
        _ingest(db, b, "claude-code")
        backfill_usage_incremental(db)
        assert _rows(db)[0][11] == "unknown"  # the committed row was demoted by the conflict
        return db, a, b

    def test_a_newer_snapshot_cannot_re_promote_a_demoted_row(self, tmp_path: Path) -> None:
        db, a, _ = self._demoted_pair(tmp_path)
        before = _rows(db)
        with a.open("a") as handle:
            handle.write("\n".join(_lines(_CHANGING)[2:]) + "\n")
        _ingest(db, a, "claude-code")
        with _priced():
            # The newer evidence is retained as unpriced audit; the protected row stays put.
            assert backfill_usage_incremental(db) == 1
            settled = _rows(db)
            assert _replay_all(db) == 0
        assert _rows(db) == settled
        assert settled[: len(before)] == before
        assert settled[-1][11] == "unknown" and settled[-1][8] is None and settled[-1][5] == 481
        assert any(row[1] == "native_conflict" for row in _pending(db))

    def test_original_source_recovery_cannot_re_promote_a_demoted_row(self, tmp_path: Path) -> None:
        from little_loops.session_store import rebuild
        from little_loops.session_store.sessions import SessionHandle
        from little_loops.session_store.usage_refresh import refresh_raw_events

        db, a, _ = self._demoted_pair(tmp_path)
        before = _rows(db)
        session = json.loads(_lines(_CHANGING)[0])["sessionId"]
        _sql(db, "UPDATE raw_events SET usage_contract = NULL WHERE source_path = ?", (str(a),))
        handle = SessionHandle("claude-code", session, a, tmp_path, a.stat().st_mtime)
        assert refresh_raw_events(db, handles=[handle]).sources[0].status == "refreshed"
        with _priced():
            backfill_usage_incremental(db)
            rebuild(db)
        assert _rows(db)[0][11] == "unknown" and _rows(db)[: len(before)] == before

    def test_parser_refresh_obligation_resolves_in_one_catch_up_even_with_an_append(
        self, tmp_path: Path
    ) -> None:
        from little_loops.session_store.sessions import SessionHandle
        from little_loops.session_store.usage_refresh import (
            outstanding_refresh_work,
            refresh_raw_events,
        )
        from little_loops.session_store.writers import _pack_payload, _unpack_payload

        db = tmp_path / "history.db"
        source = _write(tmp_path / "s.jsonl", _lines(_CLAUDE)[:1])
        _ingest(db, source, "claude-code")
        record = json.loads(_unpack_payload(_sql(db, "SELECT raw_line FROM raw_events")[0][0]))
        usage = record["message"].pop("usage")
        packed = _pack_payload(json.dumps(record))
        _sql(
            db,
            "UPDATE raw_events SET raw_line = ?, parsed_json = ?, usage_contract = NULL",
            (packed, packed),
        )
        raw_id = _sql(db, "SELECT id FROM raw_events")[0][0]
        _sql(
            db,
            "INSERT INTO usage_events(ts, session_id, model, host, host_basis, channel, "
            "provenance, input_tokens, output_tokens, cache_read_input_tokens, "
            "cache_creation_input_tokens, source_raw_event_id, source_path, source_line_no) "
            "VALUES('2026-09-29T07:10:24.136Z', ?, ?, 'claude-code', 'handle', 'transcript', "
            "'unknown', ?, ?, ?, ?, ?, ?, 1)",
            (
                json.loads(_lines(_CLAUDE)[0])["sessionId"],
                record["message"]["model"],
                usage["input_tokens"],
                usage["output_tokens"],
                usage["cache_read_input_tokens"],
                usage["cache_creation_input_tokens"],
                raw_id,
                str(source),
            ),
        )
        # An append lands before the refresh, so the refresh both recovers line 1 in place
        # and appends line 2 (which sits above the derive checkpoint).
        _sql(
            db,
            "INSERT INTO meta(key, value) VALUES('usage_derive_version', 'enh3651-v1'), "
            "('usage_derive_raw_id', ?)",
            (str(raw_id),),
        )  # an established, valid checkpoint covering line 1
        with source.open("a") as handle:
            handle.write(_lines(_CLAUDE)[2] + "\n")
        handle_obj = SessionHandle(
            "claude-code",
            json.loads(_lines(_CLAUDE)[0])["sessionId"],
            source,
            tmp_path,
            source.stat().st_mtime,
        )
        assert refresh_raw_events(db, handles=[handle_obj]).needs_rebuild
        backfill_usage_incremental(db)  # one ordinary catch-up replays the whole source
        assert _rows(db)[0][11] == "measured"
        assert outstanding_refresh_work(db, [source]) is True  # parser cache work remains
        assert all(row[7] == 0 for row in _pending(db, source))  # usage component resolved

    def test_conflicting_new_codex_requests_across_sources_are_all_seen_before_pricing(
        self, tmp_path: Path
    ) -> None:
        def build(order: tuple[str, str]) -> list[tuple]:
            root = tmp_path / "".join(order)
            root.mkdir()
            db = root / "history.db"
            base = _write(root / "base.jsonl", _lines(_CLAUDE))
            _ingest(db, base, "claude-code")
            backfill_usage_incremental(db)  # an established checkpoint
            files = {
                "c1": _write(root / "c1.jsonl", _lines(_CODEX)),
                "c2": _write(root / "c2.jsonl", _bump_codex_output(_lines(_CODEX))),
            }
            for name in order:
                _ingest(db, files[name], "codex")
            with _priced():
                backfill_usage_incremental(db)
            return sorted(
                (Path(row[16]).name, row[11], row[8]) for row in _rows(db) if row[10] == "rollout"
            )

        forward, backward = build(("c1", "c2")), build(("c2", "c1"))
        assert forward == backward
        assert {state for _, state, _ in forward} == {"unknown"}
        assert {cost for _, _, cost in forward} == {None}

    def test_rebuild_resolves_a_refreshed_source_that_has_no_usage_bearing_record(
        self, tmp_path: Path
    ) -> None:
        from little_loops.session_store import rebuild
        from little_loops.session_store.sessions import SessionHandle
        from little_loops.session_store.usage_refresh import (
            outstanding_refresh_work,
            refresh_raw_events,
        )
        from little_loops.session_store.writers import _pack_payload

        db = tmp_path / "history.db"
        source = tmp_path / "s.jsonl"
        record = {
            "type": "user",
            "sessionId": "s1",
            "timestamp": "2026-09-29T01:00:00Z",
            "message": {"role": "user", "content": "hi", "extra": 1},
        }
        source.write_text(json.dumps(record) + "\n")
        _ingest(db, source, "claude-code")
        del record["message"]["extra"]
        packed = _pack_payload(json.dumps(record))
        _sql(db, "UPDATE raw_events SET raw_line = ?, parsed_json = ?", (packed, packed))
        handle = SessionHandle("claude-code", "s1", source, tmp_path, source.stat().st_mtime)
        assert refresh_raw_events(db, handles=[handle]).needs_rebuild
        rebuild(db)
        assert _pending(db, source) == []
        assert outstanding_refresh_work(db, [source]) is False


def _hold(db: Path, source: Path | None, host: str = "*", channel: str = "*") -> None:
    _sql(
        db,
        "INSERT INTO usage_replay_holds(source_path, host, channel, reason, created_at) "
        "VALUES(?, ?, ?, 'dangling_raw_link', '2026-01-01T00:00:00Z')",
        (str(source) if source is not None else None, host, channel),
    )


def _holds(db: Path) -> list[tuple]:
    return _sql(db, "SELECT source_path, host, channel FROM usage_replay_holds ORDER BY rowid")


class TestHoldRelease:
    def _store(self, tmp_path: Path, name: str = "a.jsonl") -> tuple[Path, Path]:
        db = tmp_path / "history.db"
        source = _write(tmp_path / name, _lines(_CLAUDE))
        _ingest(db, source, "claude-code")
        backfill_usage_incremental(db)
        return db, source

    def test_fully_reconstructible_population_releases_only_its_exact_hold(
        self, tmp_path: Path
    ) -> None:
        db, source = self._store(tmp_path)
        other = _write(tmp_path / "other.jsonl", _lines(_CLAUDE))
        _hold(db, source)
        _hold(db, other)  # another source's protection
        _hold(db, None, "opencode", "rollout")  # a wildcard population hold
        before = _rows(db)
        with _priced():
            backfill_usage_incremental(db)
        assert _holds(db) == [(str(other), "*", "*"), (None, "opencode", "rollout")]
        assert _rows(db) == before

    def test_an_unmatched_historical_observation_keeps_the_hold(self, tmp_path: Path) -> None:
        db, source = self._store(tmp_path)
        _hold(db, source)
        _sql(
            db,
            "INSERT INTO usage_events(ts, session_id, model, host, channel, provenance, "
            "input_tokens, output_tokens, source_path) VALUES('2026-01-01T00:00:00Z', 'old', "
            "'claude-x', 'claude-code', 'transcript', 'unknown', 1, 1, ?)",
            (str(source),),
        )
        with _priced():
            backfill_usage_incremental(db)
        assert _holds(db) == [(str(source), "*", "*")]

    def test_a_mixed_host_channel_row_under_the_source_predicate_keeps_the_hold(
        self, tmp_path: Path
    ) -> None:
        db, source = self._store(tmp_path)
        _hold(db, source)
        _sql(
            db,
            "INSERT INTO usage_events(ts, session_id, model, host, channel, provenance, "
            "input_tokens, output_tokens, source_path) VALUES('2026-01-01T00:00:00Z', 'x', "
            "'m', 'opencode', 'rollout', 'unknown', 1, 1, ?)",
            (str(source),),
        )
        backfill_usage_incremental(db)
        assert _holds(db) == [(str(source), "*", "*")]

    def test_pruned_source_with_no_retained_raw_cannot_conceal_its_observations(
        self, tmp_path: Path
    ) -> None:
        from little_loops.session_store import prune

        db, source = self._store(tmp_path)
        _sql(db, "UPDATE raw_events SET compacted = 1, ts = ?", (_OLD,))
        assert prune(db, config=_PRUNE_CFG)["deleted"] == {"raw_events": 4}
        before = (_rows(db), _holds(db))
        backfill_usage_incremental(db)
        assert (_rows(db), _holds(db)) == before

    def test_unresolved_pending_work_keeps_the_hold(self, tmp_path: Path) -> None:
        db, source = self._store(tmp_path)
        _hold(db, source)
        # A new request whose envelope disagrees with its payload stays pending, never a row.
        _append_new_request(db, source, "msg_bad", 5, envelope_session="other-session")
        backfill_usage_incremental(db)
        assert _pending(db, source) != []
        assert _holds(db) == [(str(source), "*", "*")]
        # Repairing the evidence resolves the work; only then may the hold be lifted.
        _sql(
            db,
            "UPDATE raw_events SET session_id = "
            "(SELECT session_id FROM raw_events WHERE line_no = 1) WHERE line_no = 5",
        )
        backfill_usage_incremental(db)
        assert _pending(db, source) == []
        assert _holds(db) == []

    def test_a_proved_conflict_keeps_the_hold(self, tmp_path: Path) -> None:
        db, source = self._store(tmp_path)
        other = _write(tmp_path / "b.jsonl", _bump_output(_lines(_CLAUDE)))
        _ingest(db, other, "claude-code")
        backfill_usage_incremental(db)  # demotes a's rows
        _hold(db, source)
        backfill_usage_incremental(db)
        assert (str(source), "*", "*") in _holds(db)

    def test_proof_limit_permits_no_release(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.session_store import usage_proof_scope as scope_mod

        db, source = self._store(tmp_path)
        _hold(db, source)
        monkeypatch.setattr(scope_mod, "PROOF_LIMITS", scope_mod.ProofLimits(max_items=1))
        before = _rows(db)
        backfill_usage_incremental(db)
        assert _holds(db) == [(str(source), "*", "*")] and _rows(db) == before

    def test_release_commits_atomically_with_the_scan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, source = self._store(tmp_path)
        _hold(db, source)
        _append_new_request(db, source, "msg_atomic", 5)
        floor = _sql(db, "SELECT value FROM meta WHERE key = 'usage_derive_raw_id'")

        def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("publication failed")

        monkeypatch.setattr(lifecycle, "_publish_usage_derive_checkpoint", boom)
        before = _rows(db)
        with pytest.raises(RuntimeError):
            backfill_usage_incremental(db)
        assert _holds(db) == [(str(source), "*", "*")]  # the release rolled back with it
        assert _rows(db) == before
        assert _sql(db, "SELECT value FROM meta WHERE key = 'usage_derive_raw_id'") == floor


def _append_new_request(
    db: Path,
    source: Path,
    message_id: str,
    line_no: int,
    *,
    envelope_session: str | None = None,
) -> None:
    record = json.loads(_lines(_CLAUDE)[0])
    record["message"]["id"] = message_id
    sample = _sql(
        db,
        "SELECT session_id, usage_contract FROM raw_events WHERE source_path = ? LIMIT 1",
        (str(source),),
    )[0]
    _sql(
        db,
        "INSERT INTO raw_events(ts, session_id, host, host_basis, source_path, line_no, "
        "event_type, raw_line, parsed_json, usage_contract) "
        "VALUES('2026-09-29T07:30:00Z', ?, 'claude-code', 'handle', ?, ?, 'assistant', ?, ?, ?)",
        (
            envelope_session or sample[0],
            str(source),
            line_no,
            json.dumps(record),
            json.dumps(record),
            sample[1],
        ),
    )


class TestDecodeFailuresAndRawOnlyAcquisition:
    def test_an_undecodable_retained_row_keeps_its_scope_pending_instead_of_vanishing(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "history.db"
        source = _write(tmp_path / "s.jsonl", _lines(_CLAUDE))
        _ingest(db, source, "claude-code")
        _sql(db, "UPDATE raw_events SET raw_line = ? WHERE line_no = 3", ("{not json",))
        bad_id = _sql(db, "SELECT id FROM raw_events WHERE line_no = 3")[0][0]
        assert backfill_usage_incremental(db) == 2  # every decodable candidate still derives
        pending = _pending(db, source)
        assert [(row[1], row[2], row[3]) for row in pending] == [
            ("derive_gap", "usage_proof_unprovable", "bounded")
        ]
        assert (pending[0][4], pending[0][5]) == (bad_id, bad_id)
        # The evidence is repaired in place: the retry resolves the work and nothing churns.
        packed = _sql(db, "SELECT raw_line FROM raw_events WHERE line_no = 1")[0][0]
        _sql(db, "UPDATE raw_events SET raw_line = ? WHERE line_no = 3", (packed,))
        backfill_usage_incremental(db)
        assert _pending(db, source) == []

    def test_pristine_codex_raw_only_ingestion_stages_acquisition_and_derives_without_the_file(
        self, tmp_path: Path
    ) -> None:
        from little_loops.session_store import read_source_derive_completion

        db = tmp_path / "history.db"
        source = _write(tmp_path / "r.jsonl", _lines(_CODEX))
        _ingest(db, source, "codex")
        head = _sql(
            db,
            "SELECT acquisition_version, acquired_line_no, status FROM usage_source_state "
            "WHERE source_path = ?",
            (str(source),),
        )
        assert head == [("enh3745-v1", 11, "pending")]
        source.unlink()
        assert backfill_usage_incremental(db) == 2
        conn = connect(db)
        try:
            done = read_source_derive_completion(conn, str(source))
        finally:
            conn.close()
        assert (done.status, done.basis) == ("complete", "semantic")
        assert [w[4:] for w in _witnesses(db)] == [("known", "known")] * 2

    def test_raw_only_staging_rolls_back_with_the_ingestion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.session_store import usage_source_tracking as tracking

        db = tmp_path / "history.db"
        ensure_db(db)
        # Named after its native session ID, as a Claude transcript is, so identity verifies.
        source = _write(
            tmp_path / f"{json.loads(_lines(_CLAUDE)[0])['sessionId']}.jsonl", _lines(_CLAUDE)
        )

        def boom(*args: object, **kwargs: object) -> bool:
            raise RuntimeError("staging failed")

        monkeypatch.setattr(lifecycle, "stage_raw_only_source", boom)
        with pytest.raises(RuntimeError, match="staging failed"):
            _ingest(db, source, "claude-code")
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(0,)]
        assert _sql(db, "SELECT COUNT(*) FROM usage_source_state") == [(0,)]
        del tracking
