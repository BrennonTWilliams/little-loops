"""Tests for the opt-in total-deadline budget on strict read-only history connections (ENH-3720).

Backend-boundary tests only: the ``HistoryUnavailable`` / ``HranaUnavailable`` contract of the
primitive, not the reader-fallback seam (ENH-3682). Exact budget accounting uses a fake clock
(``deadline.now``) and a fake transport; the real-I/O cases are a small serial matrix marked
``no_parallel`` that asserts against a named scheduling tolerance smaller than the tested budget.
"""

from __future__ import annotations

import inspect
import json
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from little_loops.session_store import Deadline, remote_schema, remote_telemetry
from little_loops.session_store import deadline as deadline_mod
from little_loops.session_store import hrana as hrana_mod
from little_loops.session_store.backend import (
    Backend,
    BackendConfig,
    HistoryUnavailable,
    HistoryUnsupported,
    RemoteTarget,
    SqliteBackend,
    connect_readonly,
)
from little_loops.session_store.hrana import HranaClient, HranaUnavailable
from little_loops.session_store.libsql import LibsqlBackend
from tests.hrana_stub import HranaStub

TOKEN = "enh3720-token"
# Real-I/O assertions allow this much scheduling slack; it is smaller than every budget below,
# so two complete budgets or a prolonged trickle cannot pass.
TOLERANCE = 0.25
BUDGET = 0.4


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(deadline_mod, "now", fake)
    return fake


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "h.db"
    conn = sqlite3.connect(path)
    conn.execute("create table t(a integer)")
    conn.executemany("insert into t values (?)", [(i,) for i in range(20000)])
    conn.commit()
    conn.close()
    return path


# One cheap-to-start, expensive-to-finish statement: rows arrive slowly, so execution returns
# before the work does and fetching/iteration is where the budget is spent.
SLOW_ROWS = "select x.a, (select count(*) from t y, t z where y.a < x.a) from t x"
SLOW_EXEC = "select count(*) from t a, t b, t c"


class TestDeadlineValue:
    def test_after_remaining_expired(self, clock: FakeClock) -> None:
        d = Deadline.after(5)
        assert d.expires_at == 5.0 and d.remaining() == 5.0 and not d.expired()
        clock.t = 4.0
        assert d.remaining() == 1.0
        clock.t = 7.0
        assert d.remaining() == 0.0 and d.expired()

    def test_exported(self) -> None:
        from little_loops import session_store

        assert session_store.Deadline is Deadline


class TestSignatureParity:
    def test_all_declarations_take_keyword_only_deadline_default_none(self) -> None:
        from little_loops.session_store import backend as backend_mod

        for fn in (
            Backend.connect_readonly,
            SqliteBackend.connect_readonly,
            LibsqlBackend.connect_readonly,
            backend_mod.connect_readonly,
        ):
            param = inspect.signature(fn).parameters["deadline"]
            assert param.kind is inspect.Parameter.KEYWORD_ONLY
            assert param.default is None
            assert inspect.signature(fn).parameters["timeout"].default == 5.0

    def test_wrapper_forwards_deadline(self, monkeypatch: pytest.MonkeyPatch, db: Path) -> None:
        from little_loops.session_store import backend as backend_mod

        seen: dict[str, Any] = {}

        class Spy:
            def connect_readonly(self, target: Any, **kw: Any) -> str:
                seen.update(kw)
                return "conn"

        monkeypatch.setattr(backend_mod, "resolve_backend", lambda provider: Spy())
        d = Deadline.after(5)
        assert connect_readonly(db, timeout=1.5, deadline=d) == "conn"
        assert seen == {"timeout": 1.5, "deadline": d}


class TestLocalBinding:
    def test_no_deadline_is_a_plain_connection(self, db: Path) -> None:
        conn = connect_readonly(db)
        assert type(conn) is sqlite3.Connection
        assert type(conn.cursor()) is sqlite3.Cursor
        assert conn.execute("pragma busy_timeout").fetchone()[0] == 5000
        conn.close()

    def test_expired_before_open(self, db: Path, clock: FakeClock) -> None:
        with pytest.raises(HistoryUnavailable, match="before opening"):
            connect_readonly(db, deadline=Deadline(expires_at=0.0))

    def test_expired_before_statement_rejects_every_read(self, db: Path, clock: FakeClock) -> None:
        conn = connect_readonly(db, deadline=Deadline.after(10))
        assert conn.execute("select 1").fetchone()[0] == 1
        clock.t = 10.0
        with pytest.raises(HistoryUnavailable):
            conn.execute("select 1")
        with pytest.raises(HistoryUnavailable):
            conn.cursor().execute("select 1")
        conn.close()

    def test_fetch_after_expiry_is_refused_even_for_buffered_rows(
        self, db: Path, clock: FakeClock
    ) -> None:
        conn = connect_readonly(db, deadline=Deadline.after(10))
        cur = conn.execute("select a from t limit 3")
        clock.t = 10.0
        for fetch in (
            cur.fetchone,
            cur.fetchall,
            lambda: cur.fetchmany(2),
            lambda: next(iter(cur)),
        ):
            with pytest.raises(HistoryUnavailable):
                fetch()
        conn.close()

    def test_lock_wait_is_reclamped_to_remaining_budget(self, db: Path, clock: FakeClock) -> None:
        conn = connect_readonly(db, timeout=5.0, deadline=Deadline.after(10))
        assert conn.execute("pragma busy_timeout").fetchone()[0] == 5000
        clock.t = 8.0  # earlier statements consumed budget; the wait must shrink, not stay 5s
        assert conn.execute("pragma busy_timeout").fetchone()[0] == 2000
        conn.close()

    def test_unrelated_sqlite_errors_keep_their_taxonomy(self, db: Path) -> None:
        conn = connect_readonly(db, deadline=Deadline.after(30))
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            conn.execute("select * from missing")
        conn.close()

    def test_close_releases_handler_and_is_idempotent(self, db: Path) -> None:
        conn = connect_readonly(db, deadline=Deadline.after(30))
        conn.close()
        conn.close()
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("select 1")

    def test_separate_unbounded_connection_is_unaffected(self, db: Path, clock: FakeClock) -> None:
        bound = connect_readonly(db, deadline=Deadline.after(1))
        free = connect_readonly(db)
        clock.t = 5.0
        assert free.execute("select count(*) from t").fetchone()[0] == 20000
        with pytest.raises(HistoryUnavailable):
            bound.execute("select 1")
        bound.close()
        free.close()


@pytest.mark.no_parallel
class TestLocalCancellationTiming:
    def _assert_bounded(self, started: float) -> None:
        assert time.monotonic() - started < BUDGET + TOLERANCE

    def test_execution_is_cancelled(self, db: Path) -> None:
        conn = connect_readonly(db, deadline=Deadline.after(BUDGET))
        started = time.monotonic()
        with pytest.raises(HistoryUnavailable) as info:
            conn.execute(SLOW_EXEC).fetchall()
        self._assert_bounded(started)
        assert isinstance(info.value.__cause__, sqlite3.OperationalError)
        conn.close()

    @pytest.mark.parametrize("via", ["shortcut", "cursor"])
    @pytest.mark.parametrize("how", ["fetchone", "fetchmany", "fetchall", "iterate"])
    def test_fetch_and_iteration_are_cancelled(self, db: Path, via: str, how: str) -> None:
        conn = connect_readonly(db, deadline=Deadline.after(BUDGET))
        started = time.monotonic()
        with pytest.raises(HistoryUnavailable):
            cur = conn.execute(SLOW_ROWS) if via == "shortcut" else conn.cursor().execute(SLOW_ROWS)
            if how == "fetchone":
                while cur.fetchone() is not None:
                    pass
            elif how == "fetchmany":
                while cur.fetchmany(50):
                    pass
            elif how == "fetchall":
                cur.fetchall()
            else:
                for _ in cur:
                    pass
        self._assert_bounded(started)
        conn.close()

    def test_lock_wait_after_prior_budget_consumption_mechanism(self, db: Path) -> None:
        """The deadline's remaining budget clamps the lock-wait on a separate writer.

        Asserts the *mechanism*: with a 0.4s deadline and 0.1s of prior budget
        consumed, a per-statement ``timeout=5.0`` is ignored and the connection
        raises ``HistoryUnavailable`` (``OperationalError`` cause) when the lock
        can't be acquired within the deadline's remaining 0.3s.

        Wall-clock is intentionally NOT bounded here — macos sqlite's
        ``busy_timeout=300`` takes ~0.7s of internal polling to raise
        SQLITE_BUSY (≈3× the Linux cost) regardless of where the deadline's
        remaining budget ends. Tight-budget timing is covered by
        ``test_execution_is_cancelled`` (no prior consumption, single OS).
        """
        writer = sqlite3.connect(db, isolation_level=None)
        writer.execute("begin exclusive")
        try:
            conn = connect_readonly(db, timeout=5.0, deadline=Deadline.after(BUDGET))
            time.sleep(0.1)  # earlier work consumed part of the budget
            with pytest.raises(HistoryUnavailable) as info:
                conn.execute("select count(*) from t").fetchall()
            assert isinstance(info.value.__cause__, sqlite3.OperationalError)
            conn.close()
        finally:
            writer.rollback()
            writer.close()


# -- remote ---------------------------------------------------------------


def _batch_ok(version: int) -> dict[str, Any]:
    def text(v: str) -> dict[str, str]:
        return {"type": "text", "value": v}

    one = {"cols": [{"name": "1"}], "rows": [[{"type": "integer", "value": "1"}]]}
    meta = {
        "cols": [{"name": "key"}, {"name": "value"}],
        "rows": [
            [text("schema_version"), text(str(version))],
            [text("project_id"), text("acme-api")],
        ],
    }
    return {
        "type": "ok",
        "response": {
            "type": "batch",
            "result": {"step_results": [one, meta], "step_errors": [None, None]},
        },
    }


def _execute_ok() -> dict[str, Any]:
    result = {"cols": [{"name": "x"}], "rows": [[{"type": "integer", "value": "1"}]]}
    return {"type": "ok", "response": {"type": "execute", "result": result}}


def _wire(*items: dict[str, Any]) -> tuple[int, bytes]:
    results = [*items, {"type": "ok", "response": {"type": "close"}}]
    return 200, json.dumps({"results": results}).encode()


def _target(url: str = "http://127.0.0.1:1") -> RemoteTarget:
    return RemoteTarget(BackendConfig(provider="libsql", url=url, project_id="acme-api"))


@pytest.fixture(autouse=True)
def _fresh_verification_cache() -> Iterator[None]:
    remote_schema.clear_verification_cache()
    yield
    remote_schema.clear_verification_cache()


class FakeTransport:
    """Replaces ``HranaClient._exchange_bound``: records each request's effective expiry."""

    def __init__(self, clock: FakeClock, script: list[tuple[float, tuple[int, bytes]]]) -> None:
        self.clock = clock
        self.script = script
        self.expiries: list[float] = []

    def __call__(self, client: Any, parts: Any, body: str, headers: Any, expiry: float) -> Any:
        self.expiries.append(expiry)
        advance, response = self.script[len(self.expiries) - 1]
        self.clock.t += advance
        return response


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> Any:
    def install(script: list[tuple[float, tuple[int, bytes]]]) -> FakeTransport:
        fake = FakeTransport(clock, script)
        monkeypatch.setattr(HranaClient, "_exchange_bound", lambda self, *args: fake(self, *args))
        return fake

    return install


class TestRemoteBudgetAccounting:
    def test_cold_two_posts_warm_one_sharing_one_expiry(self, transport: Any) -> None:
        fake = transport(
            [
                (1.0, _wire(_batch_ok(99))),
                (1.0, _wire(_execute_ok())),
                (1.0, _wire(_execute_ok())),
            ]
        )
        conn = LibsqlBackend().connect_readonly(_target(), deadline=Deadline.after(100))
        assert conn.execute("select 1").fetchone()[0] == 1
        assert len(fake.expiries) == 2  # lazy verification + data query
        assert conn.execute("select 1").fetchone()[0] == 1
        assert len(fake.expiries) == 3  # warm: the in-process verification cache is reused

    def test_effective_cap_is_earlier_of_caller_expiry_and_request_timeout(
        self, transport: Any
    ) -> None:
        fake = transport([(2.0, _wire(_batch_ok(99))), (0.0, _wire(_execute_ok()))])
        conn = LibsqlBackend().connect_readonly(_target(), deadline=Deadline(expires_at=11.0))
        conn.execute("select 1")
        # POST 1: min(0 + 10, 11) = 10. POST 2 (clock now 2): min(2 + 10, 11) = 11. The caller
        # budget is never reset by a later request.
        assert fake.expiries == [10.0, 11.0]

    def test_expiry_before_dispatch_sends_nothing(self, transport: Any, clock: FakeClock) -> None:
        fake = transport([])
        conn = LibsqlBackend().connect_readonly(_target(), deadline=Deadline(expires_at=5.0))
        clock.t = 5.0
        with pytest.raises(HranaUnavailable):
            conn.execute("select 1")
        assert fake.expiries == []

    def test_open_with_an_expired_deadline_raises(self, clock: FakeClock) -> None:
        with pytest.raises(HranaUnavailable):
            LibsqlBackend().connect_readonly(_target(), deadline=Deadline(expires_at=0.0))

    def test_verification_consuming_the_budget_prevents_the_data_post(self, transport: Any) -> None:
        fake = transport([(6.0, _wire(_batch_ok(99))), (0.0, _wire(_execute_ok()))])
        conn = LibsqlBackend().connect_readonly(_target(), deadline=Deadline(expires_at=5.0))
        with pytest.raises(HranaUnavailable):
            conn.execute("select 1")
        assert len(fake.expiries) == 1

    def test_expired_connection_refuses_even_cache_hit_reads(
        self, transport: Any, clock: FakeClock
    ) -> None:
        fake = transport([(0.0, _wire(_batch_ok(99))), (0.0, _wire(_execute_ok()))])
        conn = LibsqlBackend().connect_readonly(_target(), deadline=Deadline(expires_at=5.0))
        conn.execute("select 1")
        clock.t = 5.0
        with pytest.raises(HranaUnavailable):
            conn.execute("select 1")
        assert len(fake.expiries) == 2

    def test_late_success_after_synchronous_work_is_not_reported(self, transport: Any) -> None:
        transport([(0.0, _wire(_batch_ok(99))), (9.0, _wire(_execute_ok()))])
        conn = LibsqlBackend().connect_readonly(_target(), deadline=Deadline(expires_at=5.0))
        with pytest.raises(HranaUnavailable):
            conn.execute("select 1")

    def test_strict_reads_refuse_writes_and_skip_telemetry_state(
        self, transport: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = transport([(0.0, _wire(_batch_ok(99))), (0.0, _wire(_execute_ok()))])

        def boom(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("telemetry state touched by a strict read")

        monkeypatch.setattr(LibsqlBackend, "connect_telemetry", boom)
        for name in ("load_verified", "store_verified", "mark_unreachable", "unreachable_active"):
            monkeypatch.setattr(remote_telemetry, name, boom)
        conn = LibsqlBackend().connect_readonly(_target(), deadline=Deadline.after(100))
        with pytest.raises(HistoryUnsupported):
            conn.execute("insert into t values (1)")
        assert fake.expiries == []
        conn.execute("select 1")

    def test_no_deadline_client_keeps_the_legacy_transport(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(HranaClient, "_exchange_bound", lambda *a: pytest.fail("bound path"))
        monkeypatch.setattr(
            HranaClient, "_exchange", lambda self, parts, body, headers: _wire(_execute_ok())
        )
        client = HranaClient("http://127.0.0.1:1", TOKEN)
        assert client.deadline is None
        assert client.execute("select 1").rows == [(1,)]


# -- real sockets ---------------------------------------------------------


@pytest.fixture
def stub() -> Iterator[HranaStub]:
    s = HranaStub(token=TOKEN).start()
    try:
        yield s
    finally:
        s.stop()


@pytest.fixture
def sockets(monkeypatch: pytest.MonkeyPatch) -> list[hrana_mod._DeadlineSocket]:
    made: list[hrana_mod._DeadlineSocket] = []
    original = hrana_mod._DeadlineSocket.__init__

    def spy(self: hrana_mod._DeadlineSocket, sock: Any, expiry: float) -> None:
        original(self, sock, expiry)
        made.append(self)

    monkeypatch.setattr(hrana_mod._DeadlineSocket, "__init__", spy)
    return made


@pytest.mark.no_parallel
class TestRemoteSocketEnforcement:
    def _client(self, stub: HranaStub, budget: float, timeout: float = 5.0) -> HranaClient:
        return HranaClient(stub.url, TOKEN, timeout=timeout, deadline=Deadline.after(budget))

    def _expect_unavailable(self, client: HranaClient) -> float:
        started = time.monotonic()
        with pytest.raises(HranaUnavailable):
            client.execute("select 1")
        return time.monotonic() - started

    def test_success_on_a_connection_closing_response_releases_resources(
        self, stub: HranaStub, sockets: list[Any]
    ) -> None:
        assert self._client(stub, 5.0).execute("select 7").rows == [(7,)]
        assert len(sockets) == 1 and sockets[0]._closed

    def test_stalled_headers(self, stub: HranaStub, sockets: list[Any]) -> None:
        stub.delay = 3.0
        assert self._expect_unavailable(self._client(stub, BUDGET)) < BUDGET + TOLERANCE
        assert all(s._closed for s in sockets)

    def test_stalled_body(self, stub: HranaStub, sockets: list[Any]) -> None:
        stub.stall_body = 3.0
        assert self._expect_unavailable(self._client(stub, BUDGET)) < BUDGET + TOLERANCE
        assert all(s._closed for s in sockets)

    @pytest.mark.parametrize("part", ["headers", "body"])
    def test_trickle_inside_one_buffered_read_cannot_outlive_the_budget(
        self, stub: HranaStub, sockets: list[Any], part: str
    ) -> None:
        stub.trickle = 0.05  # each receive succeeds well inside the budget; the sum does not
        stub.trickle_part = part
        assert self._expect_unavailable(self._client(stub, BUDGET)) < BUDGET + TOLERANCE
        assert all(s._closed for s in sockets)

    def test_request_cap_still_applies_when_the_caller_budget_is_larger(
        self, stub: HranaStub
    ) -> None:
        stub.delay = 3.0
        client = self._client(stub, 30.0, timeout=BUDGET)
        assert self._expect_unavailable(client) < BUDGET + TOLERANCE

    def test_connect_failure_is_unavailable_not_a_hang(self) -> None:
        client = HranaClient("http://127.0.0.1:1", TOKEN, deadline=Deadline.after(BUDGET))
        started = time.monotonic()
        with pytest.raises(HranaUnavailable):
            client.execute("select 1")
        assert time.monotonic() - started < BUDGET + TOLERANCE
