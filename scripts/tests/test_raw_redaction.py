"""ENH-3752: bounded, guarded scrub of stored ``raw_events`` payload columns.

Local behavior runs against real SQLite on the current schema; remote behavior runs the public
``LibsqlConnection`` -> ``HranaClient`` -> ``tests.hrana_stub.HranaStub`` path.
"""

from __future__ import annotations

import json
import sqlite3
import zlib
from collections.abc import Iterator
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from little_loops.pii import HISTORY_ERROR_REASONS, HISTORY_REDACTION_VERSION
from little_loops.session_store import raw_redaction as rr
from little_loops.session_store import remote_schema
from little_loops.session_store.backend import (
    BackendConfig,
    HistoryUnavailable,
    LocalTarget,
    RemoteTarget,
)
from little_loops.session_store.hrana import HranaClient
from little_loops.session_store.libsql import LibsqlConnection
from little_loops.session_store.raw_redaction import (
    RawRedactionError,
    redact_raw_events,
)
from little_loops.session_store.schema import SCHEMA_VERSION, ensure_db
from tests.hrana_stub import HranaStub

TOKEN = "sentinel-token-DO-NOT-LEAK"
SECRET = "mail bob@example.com"
CLEAN = "mail [EMAIL]"


def payload(text: str = SECRET) -> str:
    return json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
    )


def blob(text: str) -> bytes:
    return zlib.compress(text.encode("utf-8"), 6)


# -- local fixtures -----------------------------------------------------------------------


class Db:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.conn = sqlite3.connect(path, isolation_level=None)
        self._n = 0

    def insert(
        self,
        row_id: int | None,
        raw: Any,
        parsed: Any,
        host: Any = "claude-code",
        event_type: Any = "assistant",
    ) -> None:
        self._n += 1
        self.conn.execute(
            "INSERT INTO raw_events(id, ts, host, source_path, line_no, event_type, raw_line,"
            " parsed_json) VALUES (?, 't', ?, 'p', ?, ?, ?, ?)",
            (row_id, host, self._n, event_type, raw, parsed),
        )

    def cell(self, row_id: int, col: str) -> tuple[str, bytes]:
        return self.conn.execute(
            f"SELECT typeof({col}), CAST({col} AS BLOB) FROM raw_events WHERE id = ?", (row_id,)
        ).fetchone()

    def other_columns(self) -> list[tuple[Any, ...]]:
        return self.conn.execute(
            "SELECT id, ts, session_id, host, source_path, line_no, event_type, compacted,"
            " summary_node_id, host_basis, ordinal, usage_contract FROM raw_events ORDER BY id"
        ).fetchall()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Db]:
    path = tmp_path / "h.db"
    ensure_db(path)
    d = Db(path)
    yield d
    d.conn.close()


def run(db: Db, **kw: Any) -> rr.RawRedactionReport:
    return redact_raw_events(db.path, **kw)


# -- reasons, decoder, estimator (pure) ---------------------------------------------------


class TestVocabulary:
    def test_reasons_extend_sanitizer_codes_and_are_closed(self) -> None:
        assert set(HISTORY_ERROR_REASONS) <= set(rr.RAW_REDACTION_REASONS)
        extra = {
            "unsupported_context",
            "unsupported_storage",
            "invalid_encoding",
            "invalid_compression",
            "invalid_json",
            "conflict",
            "vanished",
            "unconfirmed",
            "backend_failure",
            "backend_invariant",
            "schema_mismatch",
            "target_unavailable",
            "interrupted",
        }
        assert set(rr.RAW_REDACTION_REASONS) == set(HISTORY_ERROR_REASONS) | extra
        assert len(set(rr.RAW_REDACTION_REASONS)) == len(rr.RAW_REDACTION_REASONS)
        assert set(rr.RAW_REDACTION_STOP_REASONS) == {
            "interrupted",
            "target_unavailable",
            "schema_mismatch",
            "backend_failure",
            "backend_invariant",
            "unconfirmed",
        }


def _refusal(sql_type: str, data: bytes) -> str:
    with pytest.raises(rr._Refusal) as exc:
        rr.decode_payload(sql_type, data)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__
    assert str(exc.value) == exc.value.reason
    return exc.value.reason


class TestBoundedDecode:
    def test_text_and_blob_round_trip(self) -> None:
        assert rr.decode_payload("text", b'{"a": 1}') == {"a": 1}
        assert rr.decode_payload("blob", blob('{"a": 1}')) == {"a": 1}

    def test_invalid_utf8(self) -> None:
        assert _refusal("text", b'{"a": "\xff"}') == "invalid_encoding"
        assert _refusal("blob", zlib.compress(b'{"a": "\xff"}')) == "invalid_encoding"

    def test_compression_failures(self) -> None:
        good = blob('{"a": 1}')
        assert _refusal("blob", b"not zlib at all") == "invalid_compression"
        assert _refusal("blob", good[:-3]) == "invalid_compression"  # truncated
        assert _refusal("blob", good + b"\x00") == "invalid_compression"  # trailing
        assert _refusal("blob", good + good) == "invalid_compression"  # concatenated

    def test_decoded_cap_boundary(self) -> None:
        pad = rr.DECODED_CAP - len('{"a": ""}')
        at_cap = '{"a": "' + "x" * pad + '"}'
        assert len(at_cap) == rr.DECODED_CAP
        assert rr.decode_payload("blob", blob(at_cap))["a"] == "x" * pad
        assert _refusal("blob", blob(at_cap + " ")) == "resource_limit"  # cap + 1 (a bomb)

    def test_json_failures(self) -> None:
        assert _refusal("text", b'{"a": 1, "a": 2}') == "invalid_json"  # duplicate keys
        assert _refusal("text", b'{"a": NaN}') == "invalid_json"
        assert _refusal("text", b'{"a": Infinity}') == "invalid_json"
        assert _refusal("text", b"[1, 2]") == "invalid_json"  # non-object root
        assert _refusal("text", b'{"a": ') == "invalid_json"
        assert _refusal("text", ('{"a": ' + "9" * 5000 + "}").encode()) == "invalid_json"

    def test_deep_nesting_is_resource_limit(self) -> None:
        deep = "[" * 100_000 + "]" * 100_000
        assert _refusal("text", ('{"a": ' + deep + "}").encode()) == "resource_limit"


class TestEstimator:
    def test_component_tiers(self) -> None:
        arg = rr._ARG
        assert rr._component_bytes(None) == arg
        assert rr._component_bytes(b"abc") == 4 + arg
        assert rr._component_bytes("abc") == 6 + arg  # printable ASCII: 2x
        assert rr._component_bytes("a\x00") == 12 + arg  # control chars: 6x
        assert rr._component_bytes("é") == 12 + arg  # non-ASCII: 12x
        assert rr._component_bytes("a\x7f") == 4 + arg  # DEL is not JSON-escaped

    def test_unknown_shape_rejected(self) -> None:
        with pytest.raises(ValueError):
            rr._estimate_request_bytes(rr.UPDATE_SQL, [], shape="nope")


def _stub_conn(stub: HranaStub) -> LibsqlConnection:
    return LibsqlConnection(HranaClient(stub.url, "test-token", timeout=30.0))


class TestWireBounds:
    DDL = (
        "CREATE TABLE raw_events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,"
        " session_id TEXT, host TEXT NOT NULL, source_path TEXT NOT NULL, line_no INTEGER NOT NULL,"
        " event_type TEXT NOT NULL, raw_line TEXT NOT NULL, parsed_json TEXT NOT NULL)"
    )

    def _body(self, stub: HranaStub) -> int:
        return len(stub.requests[-1]["body"].encode())

    def test_estimator_bounds_captured_executemany_and_execute_bodies(self) -> None:
        stub = HranaStub().start()
        try:
            stub.db.execute(self.DDL)
            conn = _stub_conn(stub)
            texts = ['q"u\\o', "ctrl\x00\x01\x1f\x7f", "é ü 中 𝔘", '"' * 5000]
            params = []
            for i, text in enumerate(texts, 1):
                stub.db.execute(
                    "INSERT INTO raw_events VALUES (?, 't', NULL, 'claude-code', 'p', ?, 'assistant',"
                    " ?, ?)",
                    (i, i, text.encode(), b"\x00blob\xff"),
                )
                params.append(
                    (
                        '"' * 3000,
                        None,
                        i,
                        "blob",
                        text.encode(),
                        "blob",
                        b"\x00blob\xff",
                        "claude-code",
                        "assistant",
                    )
                )
            conn.executemany(rr.UPDATE_SQL, params)
            est = rr._estimate_request_bytes(rr.UPDATE_SQL, params, shape="batch")
            assert self._body(stub) <= est
            for p in params:
                conn.execute(rr.UPDATE_SQL, p)
                assert self._body(stub) <= rr._estimate_request_bytes(
                    rr.UPDATE_SQL, [p], shape="execute"
                )
            astral = (None, None, 1, "blob", b"", "blob", b"", "𝔘" * 10, "中" * 10)
            conn.execute(rr.UPDATE_SQL, astral)
            assert self._body(stub) <= rr._estimate_request_bytes(
                rr.UPDATE_SQL, [astral], shape="execute"
            )
        finally:
            stub.stop()

    def test_two_max_text_replacements_fit_one_request(self) -> None:
        big = "x" * rr.STORED_CAP
        params = (
            big,
            big,
            1,
            "blob",
            b"\xaa" * rr.STORED_CAP,
            "blob",
            b"\xaa" * rr.STORED_CAP,
            "claude-code",
            "assistant",
        )
        est = rr._estimate_request_bytes(rr.UPDATE_SQL, [params], shape="execute")
        assert est < 7 * (1 << 20) <= rr.REQUEST_BYTES_CAP

    def test_captured_page_response_under_32mib(self) -> None:
        sizes: list[int] = []
        from tests import hrana_stub

        original = hrana_stub._Handler._reply

        def spy(self: Any, status: int, body: Any) -> Any:
            sizes.append(len(json.dumps(body).encode()))
            return original(self, status, body)

        stub = HranaStub().start()
        try:
            hrana_stub._Handler._reply = spy  # type: ignore[method-assign]
            stub.db.execute(self.DDL)
            full = b"\xff" * rr.STORED_CAP
            for i in range(1, 9):
                stub.db.execute(
                    "INSERT INTO raw_events VALUES (?, 't', NULL, 'claude-code', 'p', ?,"
                    " 'assistant', ?, ?)",
                    (i, i, full, full),
                )
            conn = _stub_conn(stub)
            rows = rr._fetch_page(conn, snapshot=8, last_id=None, limit=8)
            assert len(rows) == 8 and rows[0].raw.value == full
            assert max(sizes) <= 32 << 20
        finally:
            hrana_stub._Handler._reply = original  # type: ignore[method-assign]
            stub.stop()


# -- local scrub --------------------------------------------------------------------------


class TestLocalScrub:
    def test_columns_scrub_independently_with_types_preserved(self, db: Db) -> None:
        db.insert(1, payload(), payload())  # TEXT / TEXT
        db.insert(2, blob(payload()), blob(payload()))  # BLOB / BLOB
        db.insert(3, payload(), blob(payload()))  # mixed
        db.insert(4, payload(CLEAN), blob(payload()))  # one clean, one dirty
        before = db.other_columns()
        report = run(db)
        assert report.complete and report.stop_reason is None
        assert (report.scanned, report.would_change, report.updates_applied) == (4, 4, 4)
        assert report.counts_complete and report.unattributed_updates_applied == 0
        assert report.counts_by_column == {
            "raw_line": {"email": 3},
            "parsed_json": {"email": 4},
        }
        for rid, raw_type, parsed_type in [
            (1, "text", "text"),
            (2, "blob", "blob"),
            (3, "text", "blob"),
            (4, "text", "blob"),
        ]:
            assert db.cell(rid, "raw_line")[0] == raw_type
            assert db.cell(rid, "parsed_json")[0] == parsed_type
        assert json.loads(db.cell(1, "raw_line")[1])["message"]["content"][0]["text"] == CLEAN
        assert zlib.decompress(db.cell(2, "parsed_json")[1]).decode().count("[EMAIL]") == 1
        assert db.cell(4, "raw_line")[1] == payload(CLEAN).encode()  # untouched sibling bytes
        assert db.other_columns() == before

    def test_second_pass_writes_nothing(self, db: Db) -> None:
        db.insert(1, payload(), blob(payload()))
        run(db)
        snapshot = db.conn.execute("SELECT * FROM raw_events").fetchall()
        again = run(db)
        assert again.complete and again.would_change == 0 and again.updates_applied == 0
        assert again.counts_by_column == {}
        assert db.conn.execute("SELECT * FROM raw_events").fetchall() == snapshot

    def test_noop_rows_keep_exact_bytes_and_whitespace(self, db: Db) -> None:
        spaced = '{ "type" :  "assistant" ,"message":{"content":[]}}'
        db.insert(1, spaced, spaced)
        report = run(db)
        assert report.would_change == 0 and report.complete
        assert db.cell(1, "raw_line") == ("text", spaced.encode())

    def test_dry_run_changes_nothing_and_reports_plan(self, db: Db) -> None:
        db.insert(1, payload(), payload())
        db.insert(2, payload(CLEAN), payload(CLEAN))
        data_before = db.path.read_bytes()
        report = run(db, dry_run=True)
        assert report.dry_run and report.complete
        assert (report.scanned, report.would_change) == (2, 1)
        assert (
            report.updates_applied == report.unattributed_updates_applied == report.reconciled == 0
        )
        assert report.counts_by_column == {"raw_line": {"email": 1}, "parsed_json": {"email": 1}}
        assert db.path.read_bytes() == data_before

    def test_preview_of_a_live_wal_store_sees_wal_rows_and_leaves_bytes(self, db: Db) -> None:
        db.conn.execute("PRAGMA journal_mode=WAL")
        db.conn.execute("PRAGMA wal_autocheckpoint=0")
        db.insert(1, payload(), payload())  # lives only in the WAL while the writer stays open
        wal = Path(f"{db.path}-wal")
        before = (db.path.read_bytes(), wal.read_bytes())
        report = run(db, dry_run=True)
        assert report.would_change == 1 and report.scanned == 1
        assert (db.path.read_bytes(), wal.read_bytes()) == before

    def test_metadata_and_links_untouched(self, db: Db) -> None:
        db.insert(1, payload(), payload())
        db.conn.execute(
            "UPDATE raw_events SET session_id='s', compacted=1, host_basis=NULL, ordinal=7,"
            " usage_contract='c' WHERE id=1"
        )
        before = db.other_columns()
        run(db)
        assert db.other_columns() == before

    def test_codex_native_and_normalized_context_supported(self, db: Db) -> None:
        native = json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "content": [{"type": "output_text", "text": SECRET}],
                },
            }
        )
        db.insert(1, native, native, host="codex", event_type="response_item")
        db.insert(2, payload(), payload(), host="codex", event_type="assistant")
        report = run(db)
        assert report.complete and report.would_change == 2

    def test_empty_table_has_none_cursors(self, db: Db) -> None:
        report = run(db)
        assert report.complete and report.scanned == 0
        assert report.snapshot_max_id is None and report.last_scanned_id is None

    def test_zero_negative_ids_and_holes(self, db: Db) -> None:
        ids = [-(2**63), -5, 0, 3, 7]
        for i in ids:
            db.insert(i, payload(), payload())
        db.conn.execute("DELETE FROM raw_events WHERE id = 7")
        report = run(db, batch_size=2)
        assert report.complete and report.scanned == 4 and report.would_change == 4
        assert report.snapshot_max_id == 3 and report.last_scanned_id == 3
        assert all(db.cell(i, "raw_line")[1] != payload().encode() for i in (-(2**63), -5, 0, 3))

    def test_report_is_json_ready_and_policy_versioned(self, db: Db) -> None:
        db.insert(1, payload(), payload())
        report = run(db)
        assert report.policy_version == HISTORY_REDACTION_VERSION
        assert report.target == {"provider": "sqlite", "path": str(db.path)}
        json.dumps(asdict(report))
        assert str(TOKEN) not in json.dumps(asdict(report))

    @pytest.mark.parametrize("bad", [0, -1, True, 1.5, "3", None])
    def test_batch_validation(self, db: Db, bad: Any) -> None:
        with pytest.raises(ValueError):
            run(db, batch_size=bad)


class TestRowFailures:
    def test_failures_advance_progress_and_leave_rows_unchanged(self, db: Db) -> None:
        db.insert(1, "{not json", payload())  # invalid_json
        db.insert(2, payload(), payload(), host=b"claude-code")  # BLOB context
        db.insert(3, payload(), payload(), host="codex", event_type="nonesuch")  # unknown
        db.insert(4, payload(), payload(), host="mystery-host")  # unregistered host
        db.insert(5, b"\xff\xfe", payload())  # blob that is not zlib
        db.insert(6, payload(), payload())  # fine
        db.conn.execute("UPDATE raw_events SET raw_line = CAST(x'ff41' AS TEXT) WHERE id = 5")
        rows_before = {i: (db.cell(i, "raw_line"), db.cell(i, "parsed_json")) for i in range(1, 6)}
        report = run(db)
        assert report.scanned == 6 and report.last_scanned_id == 6
        assert report.failed == 5 and report.would_change == 1 and report.updates_applied == 1
        assert not report.complete and report.stop_reason is None
        for i in range(1, 6):
            assert (db.cell(i, "raw_line"), db.cell(i, "parsed_json")) == rows_before[i]
        by_id = {p.row_id: p for p in report.problems}
        assert by_id[1] == rr.RawRedactionProblem(1, "raw_line", "invalid_json")
        assert by_id[2].reason == by_id[3].reason == by_id[4].reason == "unsupported_context"
        assert by_id[2].column is None
        assert by_id[5].reason == "invalid_encoding"
        assert json.loads(db.cell(6, "raw_line")[1])["message"]["content"][0]["text"] == CLEAN

    def test_failed_sibling_discards_planned_replacement(self, db: Db) -> None:
        db.insert(1, payload(), "{broken")
        report = run(db)
        assert report.failed == 1 and report.would_change == 0 and report.updates_applied == 0
        assert report.counts_by_column == {}
        assert db.cell(1, "raw_line")[1] == payload().encode()

    def test_unsupported_storage_and_resource_limit(self, db: Db) -> None:
        db.insert(1, 42, payload())  # INTEGER stored in a TEXT column (affinity coerces -> text)
        db.conn.execute(
            "UPDATE raw_events SET parsed_json = zeroblob(?) WHERE id = 1", (rr.STORED_CAP + 1,)
        )
        db.insert(2, payload(), payload())
        db.conn.execute("UPDATE raw_events SET raw_line = x'ff' WHERE id = 2")
        report = run(db)
        reasons = {(p.row_id, p.column): p.reason for p in report.problems}
        assert reasons[(1, "parsed_json")] == "resource_limit"
        assert reasons[(2, "raw_line")] == "invalid_compression"
        assert report.failed == 2 and report.scanned == 2

    def test_problem_cap_keeps_stop_reason_independent(
        self, db: Db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rr, "PROBLEM_CAP", 2)
        for i in range(1, 6):
            db.insert(i, "{x", payload())
        report = run(db)
        assert len(report.problems) == 2 and report.omitted_problems == 3 and report.failed == 5

    def test_no_content_in_problems(self, db: Db) -> None:
        db.insert(1, "{" + SECRET, payload())
        report = run(db)
        assert "bob@example.com" not in json.dumps(asdict(report))


class TestEnh3751Parity:
    """Scrubbing keeps the stored rows canonically equal to what refresh/certification compare."""

    def test_scrubbed_rows_stay_canonically_equal_to_legacy_rows(self, db: Db) -> None:
        from little_loops.session_store.usage_refresh import (
            _canonical_payload,
            _decode_stored_payload,
            _payload_equal,
        )

        db.insert(1, payload(), blob(payload()))
        legacy = {
            col: _decode_stored_payload(db.cell(1, col)[1], storage_type=db.cell(1, col)[0])
            for col in ("raw_line", "parsed_json")
        }
        run(db)
        for col in ("raw_line", "parsed_json"):
            kind, data = db.cell(1, col)
            scrubbed = _decode_stored_payload(data, storage_type=kind)
            canon = _canonical_payload(legacy[col], host="claude-code", event_type="assistant")
            assert _payload_equal(scrubbed, canon)  # same value a refresh would certify against
            assert _payload_equal(
                _canonical_payload(scrubbed, host="claude-code", event_type="assistant"), scrubbed
            )
            assert not _payload_equal(scrubbed, legacy[col])  # the secret really went away

    def test_replay_fields_and_nonsecret_content_are_preserved(self, db: Db) -> None:
        original = {
            "type": "assistant",
            "uuid": "u-1",
            "message": {"role": "assistant", "content": [{"type": "text", "text": SECRET}]},
            "usage": {"input_tokens": 3, "ratio": 0.5, "ok": True, "none": None},
        }
        db.insert(1, json.dumps(original), json.dumps(original))
        run(db)
        after = json.loads(db.cell(1, "raw_line")[1])
        assert after["uuid"] == "u-1" and after["usage"] == original["usage"]
        assert after["message"]["role"] == "assistant"
        assert after["message"]["content"][0]["text"] == CLEAN


# -- target preflight -----------------------------------------------------------------------


class TestPreflight:
    @pytest.mark.parametrize("dry_run", [True, False])
    def test_missing_target_is_not_created(self, tmp_path: Path, dry_run: bool) -> None:
        missing = tmp_path / "nope.db"
        with pytest.raises(RawRedactionError) as exc:
            redact_raw_events(missing, dry_run=dry_run)
        assert exc.value.reason == "target_unavailable" and not missing.exists()
        assert str(exc.value) == "target_unavailable"

    def test_behind_and_ahead_schemas_refuse_without_changes(self, db: Db) -> None:
        db.insert(1, payload(), payload())
        before = db.path.read_bytes()
        db.conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION - 1),)
        )
        before = db.path.read_bytes()
        with pytest.raises(RawRedactionError) as behind:
            run(db)
        assert (behind.value.reason, behind.value.guidance) == ("schema_mismatch", "migrate")
        db.conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION + 1),)
        )
        before = db.path.read_bytes()
        with pytest.raises(RawRedactionError) as ahead:
            run(db, dry_run=True)
        assert (ahead.value.reason, ahead.value.guidance) == ("schema_mismatch", "upgrade")
        assert db.path.read_bytes() == before

    def test_not_a_database_is_unavailable(self, tmp_path: Path) -> None:
        junk = tmp_path / "junk.db"
        junk.write_bytes(b"this is not a sqlite database" * 100)
        with pytest.raises(RawRedactionError) as exc:
            redact_raw_events(junk)
        assert exc.value.reason in ("target_unavailable", "backend_failure")

    def test_explicit_local_path_ignores_remote_config(
        self, db: Db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db.insert(1, payload(), payload())
        report = redact_raw_events(LocalTarget(db.path))
        assert report.target["provider"] == "sqlite" and report.complete


# -- guarded persistence, reconciliation, interruption ---------------------------------------


class TestGuardedLocalWrites:
    def _three(self, db: Db) -> None:
        for i in (1, 2, 3):
            db.insert(i, payload(), payload())

    def test_concurrent_change_is_conflict_never_overwritten(
        self, db: Db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._three(db)
        original = rr._write_unit

        def racing(run_: Any, plans: Any) -> Any:
            db.conn.execute("UPDATE raw_events SET raw_line = 'moved' WHERE id = 2")
            return original(run_, plans)

        monkeypatch.setattr(rr, "_write_unit", racing)
        report = run(db)
        assert db.cell(2, "raw_line")[1] == b"moved"
        assert report.conflicts == 1 and report.updates_applied == 2
        assert report.unattributed_updates_applied == 2 and not report.counts_complete
        assert not report.complete and report.stop_reason is None
        assert report.counts_by_column == {}  # anonymous applications carry no breakdown
        assert any(p.reason == "conflict" and p.row_id == 2 for p in report.problems)

    def test_deleted_row_is_vanished_conflict(
        self, db: Db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._three(db)
        original = rr._write_unit

        def racing(run_: Any, plans: Any) -> Any:
            db.conn.execute("DELETE FROM raw_events WHERE id = 3")
            return original(run_, plans)

        monkeypatch.setattr(rr, "_write_unit", racing)
        report = run(db)
        assert report.conflicts == 1 and report.updates_applied == 2
        assert any(p.reason == "vanished" and p.row_id == 3 for p in report.problems)

    @pytest.mark.parametrize("variant", ["A_restored_B_desired", "A_desired_B_restored"])
    def test_aba_accounting_inequalities(
        self, db: Db, monkeypatch: pytest.MonkeyPatch, variant: str
    ) -> None:
        db.insert(1, payload(), payload())
        db.insert(2, payload(), payload())
        original = rr._write_unit
        orig_text = payload()
        clean = json.dumps(json.loads(payload().replace("bob@example.com", "[EMAIL]")))

        def racing(run_: Any, plans: Any) -> Any:
            db.conn.execute("UPDATE raw_events SET raw_line = 'tmp' WHERE id = 2")
            result = original(run_, plans)  # short ack 1: id 1 applied, id 2 missed
            if variant == "A_restored_B_desired":  # A back to original, B already desired
                db.conn.execute(
                    "UPDATE raw_events SET raw_line = ?, parsed_json = ? WHERE id = 1",
                    (orig_text, orig_text),
                )
                db.conn.execute(
                    "UPDATE raw_events SET raw_line = ?, parsed_json = ? WHERE id = 2",
                    (clean, clean),
                )
            else:  # A stays desired, B restored to original so its retry succeeds
                db.conn.execute("UPDATE raw_events SET raw_line = ? WHERE id = 2", (orig_text,))
            return result

        monkeypatch.setattr(rr, "_write_unit", racing)
        report = run(db)
        assert report.updates_applied == 2 and report.unattributed_updates_applied == 1
        assert report.reconciled == 1 and not report.counts_complete
        assert report.conflicts == 0 and report.failed == 0 and report.complete
        assert report.counts_by_column == {"raw_line": {"email": 1}, "parsed_json": {"email": 1}}
        assert 0 <= report.unattributed_updates_applied <= report.updates_applied
        assert report.updates_applied - report.unattributed_updates_applied <= report.would_change
        assert report.reconciled <= report.would_change
        # applications + reconciled is not a distinct-row partition
        assert report.updates_applied + report.reconciled == 3 > report.would_change

    def test_zero_ack_retries_once_through_the_guard(
        self, db: Db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db.insert(1, payload(), payload())
        monkeypatch.setattr(rr, "_write_unit", lambda run_, plans: 0)
        report = run(db)
        # ack 0 of 1: reconcile sees "original", retries once through the real guard (which
        # applies), so no conflict is manufactured when the guard matches
        assert report.updates_applied == 1 and report.conflicts == 0 and report.complete

    def test_snapshot_bound_excludes_later_autoallocated_ids(
        self, db: Db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for i in (1, 2, 3):
            db.insert(i, payload(), payload())
        original = rr._fetch_page
        calls = {"n": 0}

        def fetch(conn: Any, **kw: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 2:
                db.insert(None, payload(), payload())  # id 4: beyond the captured maximum
            return original(conn, **kw)

        monkeypatch.setattr(rr, "_fetch_page", fetch)
        report = run(db, batch_size=2)
        assert report.scanned == 3 and report.snapshot_max_id == 3
        assert db.cell(4, "raw_line")[1] == payload().encode()

    def test_page_rows_never_exceed_eight(self, db: Db, monkeypatch: pytest.MonkeyPatch) -> None:
        for i in range(1, 21):
            db.insert(i, payload(CLEAN), payload(CLEAN))
        limits: list[int] = []
        original = rr._fetch_page

        def spy(conn: Any, **kw: Any) -> Any:
            limits.append(kw["limit"])
            return original(conn, **kw)

        monkeypatch.setattr(rr, "_fetch_page", spy)
        run(db, batch_size=2000)
        assert max(limits) == 8


class TestInterruptionAndFailures:
    def test_interrupt_before_snapshot_raises_content_free_error(
        self, db: Db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(conn: Any) -> Any:
            raise KeyboardInterrupt

        monkeypatch.setattr(rr, "_snapshot_max_id", boom)
        with pytest.raises(RawRedactionError) as exc:
            run(db)
        assert exc.value.reason == "interrupted" and exc.value.__cause__ is None

    def test_interrupt_after_snapshot_returns_report(
        self, db: Db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db.insert(1, payload(), payload())
        db.insert(2, payload(), payload())
        original = rr._fetch_page
        n = {"c": 0}

        def fetch(conn: Any, **kw: Any) -> Any:
            n["c"] += 1
            if n["c"] == 2:
                raise KeyboardInterrupt
            return original(conn, **kw)

        monkeypatch.setattr(rr, "_fetch_page", fetch)
        report = run(db, batch_size=1)
        assert report.stop_reason == "interrupted" and not report.complete
        assert report.updates_applied == 1 and report.last_scanned_id == 1

    def test_interrupt_after_commit_before_accounting_is_unconfirmed(
        self, db: Db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for i in (1, 2):
            db.insert(i, payload(), payload())
        original = rr._commit

        def commit_then_interrupt(conn: Any) -> None:
            original(conn)
            raise KeyboardInterrupt

        monkeypatch.setattr(rr, "_commit", commit_then_interrupt)
        report = run(db)
        assert report.stop_reason == "interrupted" and not report.complete
        assert report.updates_applied == 0 and not report.counts_complete
        assert report.unconfirmed == 2
        assert json.loads(db.cell(1, "raw_line")[1])["message"]["content"][0]["text"] == CLEAN

    def test_interrupt_before_commit_rolls_back_to_zero(
        self, db: Db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for i in (1, 2):
            db.insert(i, payload(), payload())

        def interrupt(conn: Any) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(rr, "_commit", interrupt)
        report = run(db)
        assert report.stop_reason == "interrupted"
        assert report.updates_applied == 0 and report.unconfirmed == 0
        assert db.cell(1, "raw_line")[1] == payload().encode()  # rolled back

    def test_backend_failure_after_snapshot_keeps_accrued_counts(
        self, db: Db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for i in (1, 2):
            db.insert(i, payload(), payload())
        original = rr._fetch_page
        n = {"c": 0}

        def fetch(conn: Any, **kw: Any) -> Any:
            n["c"] += 1
            if n["c"] == 2:
                raise HistoryUnavailable("secret endpoint detail")
            return original(conn, **kw)

        monkeypatch.setattr(rr, "_fetch_page", fetch)
        report = run(db, batch_size=1)
        assert report.stop_reason == "backend_failure" and not report.complete
        assert report.updates_applied == 1
        assert "secret endpoint detail" not in json.dumps(asdict(report))

    def test_full_diagnostic_buffer_cannot_hide_stop(
        self, db: Db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rr, "PROBLEM_CAP", 1)
        db.insert(1, "{x", payload())
        db.insert(2, payload(), payload())
        original = rr._fetch_page
        n = {"c": 0}

        def fetch(conn: Any, **kw: Any) -> Any:
            n["c"] += 1
            if n["c"] == 2:
                raise HistoryUnavailable("x")
            return original(conn, **kw)

        monkeypatch.setattr(rr, "_fetch_page", fetch)
        report = run(db, batch_size=1)
        assert report.stop_reason == "backend_failure" and len(report.problems) == 1

    def test_impossible_ack_stops_as_backend_invariant(
        self, db: Db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db.insert(1, payload(), payload())
        monkeypatch.setattr(rr, "_write_unit", lambda run_, plans: len(plans) + 5)
        report = run(db)
        assert report.stop_reason == "backend_invariant" and not report.complete


# -- remote ----------------------------------------------------------------------------------


@pytest.fixture
def remote() -> Iterator[tuple[HranaStub, RemoteTarget]]:
    remote_schema.clear_verification_cache()
    stub = HranaStub(token=TOKEN).start()
    try:
        remote_schema.migrate_remote(HranaClient(stub.url, TOKEN), "acme")
        cfg = BackendConfig(provider="libsql", url=stub.url, project_id="acme")
        yield stub, RemoteTarget(cfg)
    finally:
        stub.stop()
        remote_schema.clear_verification_cache()


def _rinsert(stub: HranaStub, i: int, raw: Any, parsed: Any, host: str = "claude-code") -> None:
    stub.db.execute(
        "INSERT INTO raw_events(id, ts, host, source_path, line_no, event_type, raw_line,"
        " parsed_json) VALUES (?, 't', ?, 'p', ?, 'assistant', ?, ?)",
        (i, host, i, raw, parsed),
    )


def _rcell(stub: HranaStub, i: int, col: str) -> tuple[str, bytes]:
    return stub.db.execute(
        f"SELECT typeof({col}), CAST({col} AS BLOB) FROM raw_events WHERE id = ?", (i,)
    ).fetchone()


class TestRemote:
    def test_apply_scrubs_all_machines_rows(
        self, remote: tuple[HranaStub, RemoteTarget], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HISTORY_AUTH_TOKEN", TOKEN)
        stub, target = remote
        monkeypatch.setenv(target.config.auth_token_env, TOKEN)
        _rinsert(stub, 1, payload(), blob(payload()))
        _rinsert(stub, 2, blob(payload()), payload())
        report = redact_raw_events(target)
        assert report.complete and report.updates_applied == 2 and report.counts_complete
        assert report.target == {"provider": "libsql", "project_id": "acme"}
        assert _rcell(stub, 1, "raw_line")[0] == "text"
        assert _rcell(stub, 1, "parsed_json")[0] == "blob"
        assert b"[EMAIL]" in _rcell(stub, 1, "raw_line")[1]
        assert TOKEN not in json.dumps(asdict(report)) and stub.url not in json.dumps(
            asdict(report)
        )

    def test_preview_sends_reads_only(
        self, remote: tuple[HranaStub, RemoteTarget], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub, target = remote
        monkeypatch.setenv(target.config.auth_token_env, TOKEN)
        _rinsert(stub, 1, payload(), payload())
        stub.requests.clear()
        report = redact_raw_events(target, dry_run=True)
        assert report.complete and report.would_change == 1 and report.updates_applied == 0
        bodies = " ".join(r["body"].lower() for r in stub.requests)
        assert "update raw_events" not in bodies and "begin" not in bodies
        assert b"bob@example.com" in _rcell(stub, 1, "raw_line")[1]

    def test_wrong_project_stamp_and_behind_schema_refuse(
        self, remote: tuple[HranaStub, RemoteTarget], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub, target = remote
        monkeypatch.setenv(target.config.auth_token_env, TOKEN)
        remote_schema.clear_verification_cache()
        other = RemoteTarget(replace(target.config, project_id="someone-else"))
        with pytest.raises(RawRedactionError) as exc:
            redact_raw_events(other, dry_run=True)
        assert exc.value.reason == "schema_mismatch"
        stub.db.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION - 1),)
        )
        with pytest.raises(RawRedactionError) as behind:
            redact_raw_events(target)
        assert (behind.value.reason, behind.value.guidance) == ("schema_mismatch", "migrate")

    def test_preflight_ignores_populated_verification_cache(
        self, remote: tuple[HranaStub, RemoteTarget], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub, target = remote
        monkeypatch.setenv(target.config.auth_token_env, TOKEN)
        redact_raw_events(target, dry_run=True)  # populates the in-process cache as current
        stub.db.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION + 1),)
        )
        with pytest.raises(RawRedactionError) as exc:
            redact_raw_events(target, dry_run=True)
        assert (exc.value.reason, exc.value.guidance) == ("schema_mismatch", "upgrade")

    def test_unreachable_target(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = BackendConfig(provider="libsql", url="http://127.0.0.1:1", project_id="acme")
        monkeypatch.setenv(cfg.auth_token_env, TOKEN)
        with pytest.raises(RawRedactionError) as exc:
            redact_raw_events(RemoteTarget(cfg))
        assert exc.value.reason == "target_unavailable"

    def test_committed_but_lost_ack_reconciles_desired(
        self, remote: tuple[HranaStub, RemoteTarget], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub, target = remote
        monkeypatch.setenv(target.config.auth_token_env, TOKEN)
        _rinsert(stub, 1, payload(), payload())
        _rinsert(stub, 2, payload(), payload())
        original = LibsqlConnection.executemany

        def lossy(self: LibsqlConnection, sql: str, seq: Any) -> Any:
            original(self, sql, seq)  # the batch commits...
            raise HistoryUnavailable("reply lost")  # ...but the acknowledgement does not arrive

        monkeypatch.setattr(LibsqlConnection, "executemany", lossy)
        report = redact_raw_events(target)
        assert report.updates_applied == 0 and report.reconciled == 2
        assert not report.counts_complete and report.stop_reason is None
        assert b"[EMAIL]" in _rcell(stub, 1, "raw_line")[1]

    def test_unknown_outcome_and_unreadable_reconcile_is_unconfirmed(
        self, remote: tuple[HranaStub, RemoteTarget], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub, target = remote
        monkeypatch.setenv(target.config.auth_token_env, TOKEN)
        _rinsert(stub, 1, payload(), payload())
        monkeypatch.setattr(
            LibsqlConnection,
            "executemany",
            lambda self, sql, seq: (_ for _ in ()).throw(HistoryUnavailable("down")),
        )
        monkeypatch.setattr(
            rr, "_fetch_one", lambda conn, row_id: (_ for _ in ()).throw(HistoryUnavailable("down"))
        )
        report = redact_raw_events(target)
        assert report.stop_reason == "unconfirmed" and report.unconfirmed == 1
        assert not report.complete and not report.counts_complete
