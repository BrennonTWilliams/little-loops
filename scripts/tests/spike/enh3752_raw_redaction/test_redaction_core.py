"""AC suite for the ENH-3752 guarded raw_events redaction spike.

Each behavior test runs against real SQLite (``local``) and the public ``LibsqlConnection``
over ``HranaClient`` -> ``HranaStub`` (``remote``). See ``.ll/spikes/spike-ENH-3752.md``.
"""

from __future__ import annotations

import ast
import sqlite3
import types
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from scripts.tests.spike.enh3752_raw_redaction import redaction_core as core
from scripts.tests.spike.enh3752_raw_redaction.redaction_core import (
    UPDATE_SQL,
    Accounting,
    Counters,
    Desired,
    estimate_request_bytes,
    fetch_page,
    process_unit,
    reconcile,
    snapshot_max_id,
    update_params,
)

from little_loops.session_store.hrana import HranaClient, HranaUnavailable
from little_loops.session_store.libsql import LibsqlConnection
from little_loops.sqlite_uri import sqlite_file_uri
from tests import hrana_stub
from tests.hrana_stub import HranaStub

DDL = """
CREATE TABLE raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, session_id TEXT,
    host TEXT NOT NULL, source_path TEXT NOT NULL, line_no INTEGER NOT NULL,
    event_type TEXT NOT NULL, raw_line TEXT NOT NULL, parsed_json TEXT NOT NULL);
CREATE UNIQUE INDEX idx_dedup ON raw_events(source_path, line_no);
"""

SPIKE_DIR = Path(__file__).parent


@dataclass
class Store:
    kind: str
    conn: Any  # the connection under test
    raw: Any  # out-of-band sqlite connection to the same data
    stub: HranaStub | None = None
    _n: int = 0

    def insert(
        self,
        row_id: int | None,
        raw_line: Any,
        parsed: Any,
        host: Any = "claude-code",
        event_type: Any = "assistant",
    ) -> None:
        self._n += 1
        self.raw.execute(
            "INSERT INTO raw_events(id, ts, host, source_path, line_no, event_type, raw_line,"
            " parsed_json) VALUES (?, 't', ?, 'p', ?, ?, ?, ?)",
            (row_id, host, self._n, event_type, raw_line, parsed),
        )

    def cell(self, row_id: int, col: str) -> tuple[str, bytes | None]:
        return self.raw.execute(
            f"SELECT typeof({col}), CAST({col} AS BLOB) FROM raw_events WHERE id = ?", (row_id,)
        ).fetchone()


@pytest.fixture(params=["local", "remote"])
def store(request, tmp_path):
    if request.param == "local":
        path = tmp_path / "h.db"
        raw = sqlite3.connect(path, isolation_level=None)
        raw.executescript(DDL)
        conn = sqlite3.connect(path, isolation_level=None)
        yield Store("local", conn, raw)
        conn.close()
        raw.close()
        return
    stub = HranaStub().start()
    stub.db.executescript(DDL)
    conn = LibsqlConnection(HranaClient(stub.url, "test-token", timeout=5.0))
    yield Store("remote", conn, stub.db, stub)
    stub.stop()


def _candidates(store: Store, n: int = 3) -> tuple[list[core.Observed], dict[int, Desired]]:
    for i in range(1, n + 1):
        store.insert(i, f'{{"k": "secret{i}"}}', f'{{"k": "secret{i}"}}')
    rows = fetch_page(store.conn, snapshot=n, last_id=None, limit=8)
    return rows, {r.id: Desired(raw=b'{"k": "[X]"}') for r in rows}


# -- guards ----------------------------------------------------------------


class TestTypedGuards:
    def test_type_only_difference_misses_guard(self, store):
        store.insert(1, "abc", "{}")
        store.insert(2, b"abc", "{}")
        text_row, blob_row = fetch_page(store.conn, snapshot=2, last_id=None, limit=8)
        assert (text_row.raw.sql_type, blob_row.raw.sql_type) == ("text", "blob")
        assert text_row.raw.value == blob_row.raw.value == b"abc"
        wrong = list(update_params(text_row, b"[X]", None))
        wrong[3] = "blob"  # same bytes, wrong type
        assert store.conn.execute(UPDATE_SQL, wrong).rowcount == 0
        wrong_b = list(update_params(blob_row, b"[X]", None))
        wrong_b[3] = "text"
        assert store.conn.execute(UPDATE_SQL, wrong_b).rowcount == 0
        assert store.cell(1, "raw_line") == ("text", b"abc")
        assert store.conn.execute(UPDATE_SQL, update_params(text_row, b"[X]", None)).rowcount == 1
        assert store.cell(1, "raw_line") == ("text", b"[X]")

    def test_blob_context_misses_text_context_guard(self, store):
        store.insert(1, "a", "{}", host=b"claude-code")
        store.insert(2, "a", "{}", event_type=b"assistant")
        store.insert(3, "a", "{}")
        r1, r2, r3 = fetch_page(store.conn, snapshot=3, last_id=None, limit=8)
        assert not core.context_supported(r1) and not core.context_supported(r2)
        assert core.context_supported(r3)
        forced = list(update_params(r3, b"[X]", None))
        forced[2] = r1.id  # aim a text-context guard at the BLOB-host row
        forced[7] = "claude-code"
        assert store.conn.execute(UPDATE_SQL, forced).rowcount == 0

    def test_null_param_retains_sibling_bytes_and_type(self, store):
        store.insert(1, "plain-secret", b"\x78\x9c-blob-bytes")
        (row,) = fetch_page(store.conn, snapshot=1, last_id=None, limit=8)
        params = update_params(row, b"plain-[X]", None)
        assert params[1] is None
        assert store.conn.execute(UPDATE_SQL, params).rowcount == 1
        assert store.cell(1, "raw_line") == ("text", b"plain-[X]")
        assert store.cell(1, "parsed_json") == ("blob", b"\x78\x9c-blob-bytes")
        # independent mixed update: BLOB column replaced as BLOB, TEXT sibling retained
        (row,) = fetch_page(store.conn, snapshot=1, last_id=None, limit=8)
        assert store.conn.execute(UPDATE_SQL, update_params(row, None, b"NEWBLOB")).rowcount == 1
        assert store.cell(1, "raw_line") == ("text", b"plain-[X]")
        assert store.cell(1, "parsed_json") == ("blob", b"NEWBLOB")

    def test_not_null_prerequisite_rejects_null_write(self, store):
        assert core.has_not_null_payload_columns(store.conn)
        store.insert(1, "a", "b")
        with pytest.raises(Exception):  # noqa: B017 - sqlite3.IntegrityError or Hrana mapping
            store.conn.execute("UPDATE raw_events SET raw_line = NULL WHERE id = 1")
        (row,) = fetch_page(store.conn, snapshot=1, last_id=None, limit=8)
        assert store.conn.execute(UPDATE_SQL, update_params(row, None, None)).rowcount == 1
        assert store.cell(1, "raw_line") == ("text", b"a")  # COALESCE kept both, never NULL


# -- projections and keyset ---------------------------------------------------


class TestProjectionAndKeyset:
    def test_capped_projection_bounds_value_and_reports_length(self, store):
        cap = 1024
        store.insert(1, "x" * cap, "y" * (cap + 1))
        store.insert(2, "ok", "ok")
        store.raw.execute("UPDATE raw_events SET raw_line = CAST(x'fffe41' AS TEXT) WHERE id = 2")
        r1, r2 = fetch_page(store.conn, snapshot=2, last_id=None, limit=8, cap=cap)
        assert r1.raw.value == b"x" * cap and r1.raw.length == cap  # exactly at cap
        assert r1.parsed.value is None and r1.parsed.length == cap + 1  # cap+1 -> NULL + length
        assert (r2.raw.sql_type, r2.raw.value) == ("text", b"\xff\xfeA")  # TEXT fetched as bytes
        with pytest.raises(Exception):  # noqa: B017 - a direct SELECT must decode the TEXT
            store.conn.execute("SELECT raw_line FROM raw_events WHERE id = 2").fetchall()

    def test_keyset_nullable_nonpositive_and_holes(self, store):
        assert snapshot_max_id(store.conn) is None  # empty table: None, not COALESCE'd to 0
        ids = [-(2**63), -5, 0, 3, 7]
        for i in ids:
            store.insert(i, "a", "b")
        store.raw.execute("DELETE FROM raw_events WHERE id = 3")  # hole
        snap = snapshot_max_id(store.conn)
        assert snap == 7
        seen: list[int] = []
        last: int | None = None
        while True:
            page = fetch_page(store.conn, snapshot=snap, last_id=last, limit=2)
            if not page:
                break
            seen += [r.id for r in page]
            last = page[-1].id
            if last == -5:  # explicit insert within the bound, ahead of the cursor: observed
                store.insert(5, "a", "b")
            if last == 0:  # beyond the captured max: excluded
                store.insert(100, "a", "b")
        assert seen == [-(2**63), -5, 0, 5, 7]
        assert 100 not in seen

    def test_projection_one_statement_caps_whole_page(self, store):
        for i in range(1, 4):
            store.insert(i, "z" * 5000, "z" * 5000)
        rows = fetch_page(store.conn, snapshot=3, last_id=None, limit=8, cap=1000)
        assert all(r.raw.value is None and r.raw.length == 5000 for r in rows)


# -- counts, reconciliation --------------------------------------------------


class TestAckAndReconcile:
    def test_full_ack_unit_counts_all_candidates(self, store):
        rows, desired = _candidates(store)
        acct, counters = Accounting(), Counters()
        process_unit(store.conn, rows, desired, acct, counters)
        assert counters.updates_applied == 3 and counters.unattributed_updates_applied == 0
        assert counters.reconciled == 0 and counters.counts_complete
        assert acct.state.applied == 3 and acct.state.pending == ()
        assert all(store.cell(i, "raw_line") == ("text", b'{"k": "[X]"}') for i in (1, 2, 3))

    def test_short_ack_is_committed_unit_with_misses(self, store):
        rows, desired = _candidates(store)
        store.raw.execute("UPDATE raw_events SET raw_line = 'moved' WHERE id = 2")
        acct = Accounting()
        ack = core.apply_unit(store.conn, rows, desired, acct)
        assert ack == 2  # committed, not rolled back
        assert store.cell(1, "raw_line")[1] == b'{"k": "[X]"}'
        assert store.cell(3, "raw_line")[1] == b'{"k": "[X]"}'
        assert store.cell(2, "raw_line")[1] == b"moved"

    def test_reconcile_classifies_desired_original_changed_missing(self, store):
        rows, desired = _candidates(store, 4)
        store.raw.execute('UPDATE raw_events SET raw_line = \'{"k": "[X]"}\' WHERE id = 1')
        store.raw.execute("UPDATE raw_events SET raw_line = 'other' WHERE id = 3")
        store.raw.execute("DELETE FROM raw_events WHERE id = 4")
        counters = Counters()
        verdicts = [reconcile(store.conn, r, desired[r.id], counters) for r in rows]
        assert verdicts == ["desired", "retried", "changed", "vanished"]
        assert store.cell(3, "raw_line")[1] == b"other"  # never overwritten
        assert (counters.reconciled, counters.conflicts, counters.vanished) == (1, 2, 1)
        assert counters.updates_applied == 1 and counters.retries == 1

    def test_retry_once_then_second_zero_is_conflict_no_loop(self, store):
        rows, desired = _candidates(store, 1)
        calls: list[str] = []

        class ZeroAck:
            def __getattr__(self, name):
                return getattr(store.conn, name)

            def execute(self, sql, params=()):
                if sql.startswith("UPDATE"):
                    calls.append("update")
                    return types.SimpleNamespace(rowcount=0)
                return store.conn.execute(sql, params)

        counters = Counters()
        assert reconcile(ZeroAck(), rows[0], desired[1], counters) == "changed"
        assert calls == ["update"] and counters.conflicts == 1 and counters.updates_applied == 0

    @pytest.mark.parametrize("who", ["A_updated_B_misses", "B_updated_A_misses"])
    def test_aba_counts_inequalities(self, store, who):
        rows, desired = _candidates(store, 2)
        missed, done = (rows[1], rows[0]) if who == "A_updated_B_misses" else (rows[0], rows[1])
        store.raw.execute("UPDATE raw_events SET raw_line = 'tmp' WHERE id = ?", (missed.id,))

        def other_writer() -> None:  # restore `done` to original, make `missed` desired
            store.raw.execute(
                "UPDATE raw_events SET raw_line = ? WHERE id = ?", (done_original(done), done.id)
            )
            store.raw.execute(
                'UPDATE raw_events SET raw_line = \'{"k": "[X]"}\' WHERE id = ?', (missed.id,)
            )

        counters = Counters()
        process_unit(store.conn, rows, desired, Accounting(), counters, after_apply=other_writer)
        # short ack 1 (anonymous) + one attributed retry; the other ID is observed desired
        assert counters.updates_applied == 2
        assert counters.unattributed_updates_applied == 1
        assert counters.reconciled == 1 and counters.retries == 1
        assert not counters.counts_complete
        assert 0 <= counters.unattributed_updates_applied <= counters.updates_applied
        assert counters.updates_applied - counters.unattributed_updates_applied <= len(rows)
        assert counters.updates_applied + counters.reconciled == 3  # not a distinct-row partition


def done_original(obs: core.Observed) -> str:
    assert obs.raw.value is not None
    return obs.raw.value.decode()


# -- committed-but-lost acknowledgement (remote) -----------------------------------


def test_committed_but_lost_ack_is_found_desired():
    stub = HranaStub().start()
    try:
        stub.db.executescript(DDL)
        s = Store(
            "remote",
            LibsqlConnection(HranaClient(stub.url, "test-token", timeout=0.4)),
            stub.db,
            stub,
        )
        rows, desired = _candidates(s, 2)
        stub.stall_body = 1.5  # reply stalls AFTER the batch executed and committed
        with pytest.raises(HranaUnavailable):
            s.conn.executemany(UPDATE_SQL, [update_params(r, b'{"k": "[X]"}', None) for r in rows])
        assert all(s.cell(i, "raw_line")[1] == b'{"k": "[X]"}' for i in (1, 2))  # it committed
        stub.stall_body = 0.0
        # the same ambiguity through process_unit: ack unknown -> re-read finds desired, no rewrite
        for r in rows:
            s.raw.execute(
                "UPDATE raw_events SET raw_line = ? WHERE id = ?", (done_original(r), r.id)
            )
        stub.stall_body = 1.5
        acct, counters = Accounting(), Counters()
        process_unit(
            s.conn,
            rows,
            desired,
            acct,
            counters,
            after_apply=lambda: setattr(stub, "stall_body", 0.0),
        )
        assert acct.state.applied == 0 and acct.state.unconfirmed == (1, 2)
        assert counters.reconciled == 2 and counters.updates_applied == 0
        assert not counters.counts_complete and counters.retries == 0
    finally:
        stub.stop()


# -- wire bounds ---------------------------------------------------------------


def _body_len(stub: HranaStub, index: int = -1) -> int:
    return len(stub.requests[index]["body"].encode())


class TestWireBounds:
    def test_estimator_bounds_captured_executemany_and_execute_bodies(self):
        stub = HranaStub().start()
        try:
            stub.db.executescript(DDL)
            conn = LibsqlConnection(HranaClient(stub.url, "test-token", timeout=30.0))
            s = Store("remote", conn, stub.db, stub)
            payloads = [
                'plain "quoted" \\back\\ slash',
                "ctrl\x00\x01\x1f\x7f del",
                "é ü 中文 𝔘𝔫𝔦",  # BMP and astral
                '"' * 5000,
            ]
            for i, text in enumerate(payloads, 1):
                s.insert(
                    i,
                    text.encode(),
                    b"\x00\x01blob\xff",
                    host="claude-code",
                    event_type="assistant",
                )
            rows = fetch_page(conn, snapshot=len(payloads), last_id=None, limit=8)
            params = [update_params(r, ('"' * 3000).encode(), b'{"a": "\\"x\\""}') for r in rows]
            conn.executemany(UPDATE_SQL, params)
            assert _body_len(stub) <= estimate_request_bytes(UPDATE_SQL, params, shape="batch")
            for p in params:
                conn.execute(UPDATE_SQL, p)
                assert _body_len(stub) <= estimate_request_bytes(UPDATE_SQL, [p], shape="execute")
            # non-ASCII context text: a flat sixfold bound would undercount astral characters
            ctx = ("𝔘" * 10, "中" * 10)
            p = (None, None, 1, "blob", b"", "blob", b"", *ctx)
            conn.execute(UPDATE_SQL, p)
            assert _body_len(stub) <= estimate_request_bytes(UPDATE_SQL, [p], shape="execute")
            assert len(ctx[0]) * 6 + 64 < len(json_component(ctx[0]))  # sixfold would undercount
        finally:
            stub.stop()

    def test_two_1mib_text_replacements_fit_8mib_request(self):
        stub = HranaStub().start()
        try:
            stub.db.executescript(DDL)
            conn = LibsqlConnection(HranaClient(stub.url, "test-token", timeout=60.0))
            s = Store("remote", conn, stub.db, stub)
            big = b"\xaa" * core.PAYLOAD_CAP
            s.insert(1, big, big)
            (row,) = fetch_page(conn, snapshot=1, last_id=None, limit=1)
            assert row.raw.value == big and row.parsed.value == big
            new = (b'"' * core.PAYLOAD_CAP, b'"' * core.PAYLOAD_CAP)  # worst-case escaping, ASCII
            row_t = replace(
                row,
                raw=replace(row.raw, sql_type="text"),
                parsed=replace(row.parsed, sql_type="text"),
            )
            params = update_params(row_t, *new)
            est = estimate_request_bytes(UPDATE_SQL, [params], shape="execute")
            assert est <= core.MAX_REQUEST_BYTES  # conforming single row is not needlessly refused
            # guards are real BLOBs; replacements are TEXT params -> measure the true body
            p = list(params)
            p[3] = row.raw.sql_type
            p[5] = row.parsed.sql_type
            conn.execute(UPDATE_SQL, p)  # may match 0 rows; only the body size matters here
            body = _body_len(stub)
            assert body <= est <= core.MAX_REQUEST_BYTES
            assert est < 7 * (1 << 20)  # ~6.7 MiB: two 2 MiB replacements + two 1.33 MiB guards
        finally:
            stub.stop()

    def test_captured_page_response_under_32mib(self, monkeypatch):
        sizes: list[int] = []
        original = hrana_stub._Handler._reply

        def spy(self, status, body):
            sizes.append(len(hrana_stub.json.dumps(body).encode()))
            return original(self, status, body)

        monkeypatch.setattr(hrana_stub._Handler, "_reply", spy)
        stub = HranaStub().start()
        try:
            stub.db.executescript(DDL)
            conn = LibsqlConnection(HranaClient(stub.url, "test-token", timeout=60.0))
            s = Store("remote", conn, stub.db, stub)
            full = b"\xff" * core.PAYLOAD_CAP  # exactly at cap -> returned
            for i in range(1, 9):
                s.insert(i, full, full)
            rows = fetch_page(conn, snapshot=8, last_id=None, limit=8)
            assert all(r.raw.value == full and r.parsed.value == full for r in rows)
            assert max(sizes) <= 32 << 20
            # derived: 8 rows * 2 cols * base64(1 MiB) plus metadata/headroom
            assert max(sizes) >= 8 * 2 * 4 * core.PAYLOAD_CAP // 3
            sizes.clear()
            s.raw.execute("UPDATE raw_events SET raw_line = zeroblob(?)", (core.PAYLOAD_CAP * 5,))
            fetch_page(conn, snapshot=8, last_id=None, limit=8)
            assert sizes[-1] < 20 << 20  # over-cap raw_line values never cross the wire
        finally:
            stub.stop()


def json_component(text: str) -> str:
    return hrana_stub.json.dumps({"type": "text", "value": text})


# -- local mode=rw open, preview, interruption ---------------------------------------


class TestLocalOpenAndInterrupt:
    def test_mode_rw_open_never_creates_and_ro_preview_leaves_bytes(self, tmp_path):
        missing = tmp_path / "missing.db"
        with pytest.raises(sqlite3.OperationalError):
            sqlite3.connect(sqlite_file_uri(missing, mode="rw"), uri=True)
        assert not missing.exists()

        db = tmp_path / "live.db"
        writer = sqlite3.connect(db, isolation_level=None)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.executescript(DDL)
        writer.execute(
            "INSERT INTO raw_events(ts, host, source_path, line_no, event_type, raw_line,"
            " parsed_json) VALUES ('t','claude-code','p',1,'assistant','secret','{}')"
        )
        wal = Path(f"{db}-wal")
        before = (db.read_bytes(), wal.read_bytes())
        ro = sqlite3.connect(sqlite_file_uri(db), uri=True)
        ro.execute("PRAGMA query_only = ON")
        (row,) = fetch_page(ro, snapshot=snapshot_max_id(ro), last_id=None, limit=8)
        assert row.raw.value == b"secret"  # WAL-resident row visible
        with pytest.raises(sqlite3.OperationalError):
            ro.execute("UPDATE raw_events SET raw_line = 'x'")
        ro.close()
        assert (db.read_bytes(), wal.read_bytes()) == before
        writer.close()

    def _local(self, tmp_path):
        db = tmp_path / "i.db"
        raw = sqlite3.connect(db, isolation_level=None)
        raw.executescript(DDL)
        conn = sqlite3.connect(db, isolation_level=None)
        s = Store("local", conn, raw)
        rows, desired = _candidates(s)
        return s, rows, desired

    def test_interrupt_after_commit_before_accounting_is_unconfirmed(self, tmp_path):
        s, rows, desired = self._local(tmp_path)
        acct = Accounting()

        def boom():
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            core.apply_unit(s.conn, rows, desired, acct, after_commit=boom)
        assert acct.state.applied == 0 and acct.state.pending == ()
        assert acct.state.unconfirmed == (1, 2, 3)  # committed, never acknowledged
        assert s.cell(1, "raw_line")[1] == b'{"k": "[X]"}'

    def test_interrupt_before_commit_rolled_back_counts_zero(self, tmp_path):
        s, rows, desired = self._local(tmp_path)
        acct = Accounting()

        def boom():
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            core.apply_unit(s.conn, rows, desired, acct, before_commit=boom)
        assert acct.state == core._State()  # acknowledged rollback: zero, nothing unconfirmed
        assert s.cell(1, "raw_line")[1] == b'{"k": "secret1"}'  # unchanged

    def test_interrupt_with_failed_rollback_is_unconfirmed(self, tmp_path):
        s, rows, desired = self._local(tmp_path)
        acct = Accounting()

        class Proxy:
            in_transaction = True

            def __init__(self, inner):
                self._inner = inner

            def execute(self, sql, params=()):
                if sql == "ROLLBACK":
                    raise sqlite3.OperationalError("rollback failed")
                return self._inner.execute(sql, params)

        acct.begin([1, 2, 3])
        acct.on_interrupt(Proxy(s.conn))
        assert acct.state.unconfirmed == (1, 2, 3) and acct.state.applied == 0

    def test_accounting_transition_is_a_single_state_swap(self):
        acct = Accounting()
        acct.begin([1, 2])
        before = acct.state
        acct.acknowledge(2)
        after = acct.state
        assert (before.applied, before.pending) == (0, (1, 2))
        assert (after.applied, after.pending) == (2, ())


# -- regression guards -------------------------------------------------------------


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append(node.module or "")
    return out


def test_guard_spike_does_not_import_production_raw_redaction():
    for path in SPIKE_DIR.glob("*.py"):
        assert not any(
            "raw_redaction" in m.replace("enh3752_raw_redaction", "") for m in _imports(path)
        ), path


def test_guard_no_private_client_calls():
    tree = ast.parse((SPIKE_DIR / "redaction_core.py").read_text())
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attrs & {"client", "batch", "_post", "execute_many", "_stmt"}
    calls = [
        ast.unparse(n.func)
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    ]
    assert "sqlite3.connect" not in calls
