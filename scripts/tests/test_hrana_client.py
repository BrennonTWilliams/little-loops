"""Tests for the stdlib Hrana-over-HTTP client (FEAT-3535, Step 3).

Runs against ``tests/hrana_stub.py`` (a real ``127.0.0.1`` server), so timeouts, error-code
mapping and batch encoding cross a real socket. Wire facts mirror
``.ll/learning-tests/hrana-http.md``.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator

import pytest

from little_loops.session_store.backend import (
    HistoryError,
    HistoryIntegrityError,
    HistoryOperationError,
    HistoryUnavailable,
)
from little_loops.session_store.hrana import (
    BatchStep,
    HranaClient,
    HranaError,
    HranaStreamLost,
    classify_error,
    cond_not,
    cond_ok,
    normalize_url,
)
from tests.hrana_stub import HranaStub

TOKEN = "sentinel-token-DO-NOT-LEAK"


@pytest.fixture
def stub() -> Iterator[HranaStub]:
    s = HranaStub(token=TOKEN).start()
    try:
        yield s
    finally:
        s.stop()


@pytest.fixture
def client(stub: HranaStub) -> HranaClient:
    c = HranaClient(stub.url, TOKEN, timeout=5.0)
    c.execute("create table t (id integer primary key, v text not null, n real, b blob)")
    return c


class TestExecute:
    def test_round_trips_every_value_type(self, client: HranaClient) -> None:
        client.execute("insert into t values (?, ?, ?, ?)", (7, "x", 1.5, b"\x00\xff"))
        client.execute("insert into t values (?, ?, ?, ?)", (8, "y", None, None))
        rows = client.execute("select id, v, n, b from t order by id").rows
        assert rows == [(7, "x", 1.5, b"\x00\xff"), (8, "y", None, None)]

    def test_large_integer_survives_the_string_encoding(self, client: HranaClient) -> None:
        big = 2**62 + 1
        assert client.execute("select ? as n", (big,)).rows == [(big,)]

    def test_result_metadata(self, client: HranaClient) -> None:
        res = client.execute("insert into t(v) values ('a'), ('b')")
        assert res.affected_row_count == 2
        assert res.last_insert_rowid == 2
        sel = client.execute("select id, v from t")
        assert sel.cols == ["id", "v"]

    def test_one_round_trip_per_execute_with_close(
        self, stub: HranaStub, client: HranaClient
    ) -> None:
        before = len(stub.requests)
        client.execute("select 1")
        assert len(stub.requests) - before == 1
        assert '"close"' in stub.requests[-1]["body"]

    def test_bearer_token_is_sent(self, stub: HranaStub, client: HranaClient) -> None:
        client.execute("select 1")
        assert stub.requests[-1]["auth"] == f"Bearer {TOKEN}"


class TestErrorMapping:
    def test_constraint_maps_to_integrity_error_by_code(self, client: HranaClient) -> None:
        client.execute("insert into t(id, v) values (1, 'a')")
        with pytest.raises(HistoryIntegrityError) as ei:
            client.execute("insert into t(id, v) values (1, 'dup')")
        assert isinstance(ei.value, HranaError) and ei.value.code == "SQLITE_CONSTRAINT"

    def test_not_null_constraint_shares_the_code(self, client: HranaClient) -> None:
        with pytest.raises(HistoryIntegrityError):
            client.execute("insert into t(id, v) values (2, null)")

    @pytest.mark.parametrize(
        ("sql", "code"),
        [("selec 1", "SQL_PARSE_ERROR"), ("select * from no_such_tbl", "SQLITE_UNKNOWN")],
    )
    def test_parse_and_unknown_map_to_operation_error(
        self, client: HranaClient, sql: str, code: str
    ) -> None:
        with pytest.raises(HistoryOperationError) as ei:
            client.execute(sql)
        assert ei.value.code == code  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        ("code", "message", "expected"),
        [
            ("SQLITE_CONSTRAINT", "anything", HistoryIntegrityError),
            ("SQL_PARSE_ERROR", "anything", HistoryOperationError),
            ("SQLITE_UNKNOWN", "anything", HistoryOperationError),
            ("STREAM_EXPIRED", "anything", HranaStreamLost),
            ("BLOCKED", "anything", HistoryUnavailable),
            ("SOMETHING_NEW", "anything", HistoryOperationError),
        ],
    )
    def test_classification_is_code_driven_not_message_driven(
        self, code: str, message: str, expected: type[HistoryError]
    ) -> None:
        assert isinstance(classify_error(code, message), expected)

    def test_turso_idle_transaction_busy_is_stream_lost(self) -> None:
        err = classify_error(
            "SQLITE_BUSY", "interactive transaction was rolled back because the stream was idle"
        )
        assert isinstance(err, HranaStreamLost)

    def test_plain_busy_is_not_stream_lost(self) -> None:
        assert not isinstance(classify_error("SQLITE_BUSY", "database is locked"), HranaStreamLost)

    def test_sqld_stream_expired_http_400_top_level_body(
        self, stub: HranaStub, client: HranaClient
    ) -> None:
        stub.fail_next.append((400, {"message": "stream expired", "code": "STREAM_EXPIRED"}))
        with pytest.raises(HranaStreamLost):
            client.execute("select 1")

    def test_blocked_read_only_token_write(self, stub: HranaStub, client: HranaClient) -> None:
        stub.fail_next.append(
            (
                200,
                {
                    "baton": None,
                    "results": [
                        {"type": "error", "error": {"message": "x", "code": "BLOCKED"}},
                        {"type": "ok", "response": {"type": "close"}},
                    ],
                },
            )
        )
        with pytest.raises(HistoryUnavailable):
            client.execute("insert into t(v) values ('a')")

    @pytest.mark.parametrize("status", [400, 401, 403, 500, 503])
    def test_http_errors_are_unavailable(
        self, stub: HranaStub, client: HranaClient, status: int
    ) -> None:
        stub.fail_next.append((status, {"message": "nope"}))
        with pytest.raises(HistoryUnavailable):
            client.execute("select 1")

    def test_wrong_token_is_unavailable(self, stub: HranaStub) -> None:
        with pytest.raises(HistoryUnavailable):
            HranaClient(stub.url, "wrong", timeout=2.0).execute("select 1")


class TestBatch:
    def test_atomic_batch_rolls_back_on_failed_step(self, client: HranaClient) -> None:
        client.execute("insert into t(id, v) values (1, 'a')")
        steps = [
            BatchStep("begin"),
            BatchStep("insert into t(id, v) values (10, 'ok')", condition=cond_ok(0)),
            BatchStep("insert into t(id, v) values (1, 'dup')", condition=cond_ok(1)),
            BatchStep("commit", condition=cond_ok(2)),
            BatchStep("rollback", condition=cond_not(cond_ok(3))),
        ]
        res = client.batch(steps)
        assert res.step_errors[2] is not None
        assert res.step_errors[2]["code"] == "SQLITE_CONSTRAINT"
        assert res.step_results[3] is None and res.step_results[4] is not None
        assert client.execute("select count(*) from t where id = 10").rows == [(0,)]

    def test_successful_batch_commits(self, client: HranaClient) -> None:
        steps = [
            BatchStep("begin"),
            BatchStep("insert into t(id, v) values (20, 'x')", condition=cond_ok(0)),
            BatchStep("insert into t(id, v) values (21, 'y')", condition=cond_ok(1)),
            BatchStep("commit", condition=cond_ok(2)),
        ]
        res = client.batch(steps)
        assert all(e is None for e in res.step_errors)
        assert client.execute("select count(*) from t where id in (20, 21)").rows == [(2,)]

    def test_execute_many_is_one_atomic_request(self, stub: HranaStub, client: HranaClient) -> None:
        before = len(stub.requests)
        client.execute_many("insert into t(id, v) values (?, ?)", [(1, "a"), (2, "b")])
        assert len(stub.requests) - before == 1
        with pytest.raises(HistoryIntegrityError):
            client.execute_many("insert into t(id, v) values (?, ?)", [(3, "c"), (1, "dup")])
        assert client.execute("select count(*) from t").rows == [(2,)]

    def test_concurrent_batches_serialize(self, client: HranaClient) -> None:
        steps = [
            BatchStep("begin immediate"),
            BatchStep("insert or ignore into t(id, v) values (99, 'once')", condition=cond_ok(0)),
            BatchStep("commit", condition=cond_ok(1)),
            BatchStep("rollback", condition=cond_not(cond_ok(2))),
        ]
        outcomes: list[bool] = []

        def run() -> None:
            outcomes.append(client.batch(steps).step_results[2] is not None)

        threads = [threading.Thread(target=run) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert outcomes == [True] * 4
        assert client.execute("select count(*) from t where id = 99").rows == [(1,)]


class TestTimeouts:
    def test_read_timeout_raises_unavailable_within_the_bound(self, stub: HranaStub) -> None:
        stub.delay = 2.0
        c = HranaClient(stub.url, TOKEN, timeout=0.3)
        t0 = time.monotonic()
        with pytest.raises(HistoryUnavailable):
            c.execute("select 1")
        assert time.monotonic() - t0 < 1.5

    def test_silent_server_is_bounded(self) -> None:
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        try:
            c = HranaClient(f"http://127.0.0.1:{srv.getsockname()[1]}", TOKEN, timeout=0.3)
            t0 = time.monotonic()
            with pytest.raises(HistoryUnavailable):
                c.execute("select 1")
            assert time.monotonic() - t0 < 1.5
        finally:
            srv.close()

    def test_connection_refused_is_unavailable(self) -> None:
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
        srv.close()
        with pytest.raises(HistoryUnavailable):
            HranaClient(f"http://127.0.0.1:{port}", TOKEN, timeout=1.0).execute("select 1")

    def test_other_threads_keep_running_during_a_slow_request(self, stub: HranaStub) -> None:
        stub.delay = 0.6
        c = HranaClient(stub.url, TOKEN, timeout=5.0)
        stamps: list[float] = []
        stop = threading.Event()

        def ticker() -> None:
            while not stop.is_set():
                stamps.append(time.monotonic())
                time.sleep(0.01)

        t = threading.Thread(target=ticker)
        t.start()
        c.execute("select 1")
        stop.set()
        t.join()
        assert max(b - a for a, b in zip(stamps, stamps[1:], strict=False)) < 0.2


class TestSecrets:
    def test_token_never_appears_in_error_text_or_repr(self, stub: HranaStub) -> None:
        bad = HranaClient(stub.url, TOKEN + "-x", timeout=2.0)
        with pytest.raises(HistoryUnavailable) as ei:
            bad.execute("select 1")
        for text in (str(ei.value), repr(ei.value), repr(bad), str(bad)):
            assert TOKEN not in text

    def test_token_never_in_transport_error_text(self) -> None:
        with pytest.raises(HistoryUnavailable) as ei:
            HranaClient("http://127.0.0.1:1", TOKEN, timeout=0.5).execute("select 1")
        assert TOKEN not in str(ei.value)


class TestUrl:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("libsql://db.example.turso.io", "https://db.example.turso.io"),
            ("https://db.example.turso.io/", "https://db.example.turso.io"),
            ("http://127.0.0.1:8080", "http://127.0.0.1:8080"),
            ("wss://db.example.turso.io", "https://db.example.turso.io"),
        ],
    )
    def test_normalize_url(self, raw: str, expected: str) -> None:
        assert normalize_url(raw) == expected

    def test_rejects_unknown_scheme(self) -> None:
        with pytest.raises(ValueError):
            normalize_url("ftp://x")
