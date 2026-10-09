"""AC suite for the BUG-3762 bounded single-row redaction spike.

Behavior tests run against real SQLite (``local``) and the public ``LibsqlConnection`` over
``HranaClient`` -> ``HranaStub`` (``remote``). See ``.ll/spikes/spike-BUG-3762.md``.
"""

from __future__ import annotations

import ast
import json
import random
import sqlite3
import tracemalloc
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from scripts.tests.spike.bug3762_singleton_redaction import driver
from scripts.tests.spike.bug3762_singleton_redaction import singleton_core as core
from scripts.tests.spike.bug3762_singleton_redaction.driver import (
    DDL,
    INSERT,
    as_blob,
    padded_json,
    payload_json,
)
from scripts.tests.spike.enh3752_raw_redaction.redaction_core import (
    UPDATE_SQL,
    Accounting,
    Counters,
    estimate_request_bytes,
    fetch_one,
    fetch_page,
)

from little_loops.session_store.hrana import HranaClient
from little_loops.session_store.libsql import LibsqlConnection
from tests import hrana_stub
from tests.hrana_stub import HranaStub

SPIKE_DIR = Path(__file__).parent
MIB = 1 << 20
SINGLE = core.SINGLE_ROW_STORED_CAP


@dataclass
class Store:
    kind: str
    conn: Any  # the connection under test
    raw: Any  # out-of-band sqlite connection to the same data
    stub: HranaStub | None = None

    def insert(self, row_id: int, raw_line: Any, parsed: Any) -> None:
        self.raw.execute(INSERT, (row_id, row_id, raw_line, parsed))

    def cell(self, row_id: int, col: str) -> tuple[str, bytes | None]:
        return self.raw.execute(
            f"SELECT typeof({col}), CAST({col} AS BLOB) FROM raw_events WHERE id = ?", (row_id,)
        ).fetchone()


@pytest.fixture
def local(tmp_path: Path) -> Iterator[Store]:
    path = tmp_path / "h.db"
    raw = sqlite3.connect(path, isolation_level=None)
    raw.executescript(DDL)
    conn = sqlite3.connect(path, isolation_level=None)
    yield Store("local", conn, raw)
    conn.close()
    raw.close()


@pytest.fixture
def remote() -> Iterator[Store]:
    stub = HranaStub().start()
    stub.db.executescript(DDL)
    conn = LibsqlConnection(HranaClient(stub.url, "test-token", timeout=60.0))
    yield Store("remote", conn, stub.db, stub)
    stub.stop()


@pytest.fixture
def lossy_remote() -> Iterator[Store]:
    """Remote store whose client gives up after 1 s (the stub's stalled reply never arrives)."""
    stub = HranaStub().start()
    stub.db.executescript(DDL)
    conn = LibsqlConnection(HranaClient(stub.url, "test-token", timeout=1.0))
    yield Store("remote", conn, stub.db, stub)
    stub.stall_body = 0.0
    stub.stop()


@pytest.fixture(params=["local", "remote"])
def store(request: pytest.FixtureRequest) -> Store:
    return request.getfixturevalue(request.param)


@pytest.fixture
def reply_sizes() -> Iterator[list[int]]:
    """Captured stub response body sizes (the real wire bytes)."""
    sizes: list[int] = []
    original = hrana_stub._Handler._reply

    def spy(self: Any, status: int, body: Any) -> Any:
        sizes.append(len(json.dumps(body).encode()))
        return original(self, status, body)

    hrana_stub._Handler._reply = spy  # type: ignore[method-assign]
    yield sizes
    hrana_stub._Handler._reply = original  # type: ignore[method-assign]


def rand_bytes(n: int, seed: int = 1) -> bytes:
    return random.Random(seed).randbytes(n)


def refusal(sql_type: str, data: bytes, **kw: Any) -> core.Refusal:
    with pytest.raises(core.Refusal) as exc:
        core.decode_payload(sql_type, data, **kw)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__
    return exc.value


def obs_of(store: Store, row_id: int = 1) -> core.Observed:
    obs = core.fetch_singleton(store.conn, row_id)
    assert obs is not None
    return obs


# -- singleton read ---------------------------------------------------------


class TestSingletonRead:
    def test_cap_boundary_local_and_remote(self, store: Store) -> None:
        at_cap, over = b"\xaa" * SINGLE, b"\xbb" * (SINGLE + 1)
        store.insert(1, at_cap, over)
        obs = obs_of(store)
        assert obs.raw.value == at_cap and obs.raw.length == SINGLE
        assert obs.parsed.value is None and obs.parsed.length == SINGLE + 1  # withheld, size known
        assert obs.host.value == b"claude-code" and obs.event_type.value == b"assistant"
        ordinary = fetch_one(store.conn, 1)  # the page-tier projection still caps at 1 MiB
        assert ordinary is not None
        assert ordinary.raw.value is None and ordinary.raw.length == SINGLE

    def test_one_statement_coherent_read(self, store: Store) -> None:
        store.insert(1, rand_bytes(MIB + 10), rand_bytes(MIB + 11, 2))
        statements: list[str] = []
        if store.stub is None:
            store.conn.set_trace_callback(statements.append)
        before = len(store.stub.requests) if store.stub else 0
        obs = obs_of(store)
        assert obs.raw.value is not None and obs.parsed.value is not None
        if store.stub is None:
            store.conn.set_trace_callback(None)
            selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
            assert len(selects) == 1
            for column in ("raw_line", "parsed_json", "host", "event_type"):
                assert column in selects[0]
        else:
            assert len(store.stub.requests) - before == 1  # no chunk requests

    def test_remote_wire_response_under_32mib_and_not_above_page(
        self, remote: Store, reply_sizes: list[int]
    ) -> None:
        full = rand_bytes(core.STORED_CAP)
        for i in range(1, 9):
            remote.insert(i, full, full)
        remote.insert(9, rand_bytes(SINGLE, 3), rand_bytes(SINGLE, 4))
        reply_sizes.clear()
        page = fetch_page(remote.conn, snapshot=8, last_id=None, limit=8)
        page_size = max(reply_sizes)
        assert len(page) == 8 and page[0].raw.value == full
        reply_sizes.clear()
        obs = obs_of(remote, 9)
        singleton_size = max(reply_sizes)
        assert obs.raw.length == obs.parsed.length == SINGLE
        assert obs.raw.value is not None and obs.parsed.value is not None
        assert singleton_size < 32 << 20
        assert singleton_size <= page_size  # never above the full-page maximum

    def test_over_cap_values_are_not_shipped(self, remote: Store, reply_sizes: list[int]) -> None:
        remote.insert(1, rand_bytes(SINGLE + 1), rand_bytes(SINGLE + 1, 2))
        reply_sizes.clear()
        obs = obs_of(remote)
        assert obs.raw.value is None and obs.parsed.value is None
        assert obs.raw.length == obs.parsed.length == SINGLE + 1
        assert max(reply_sizes) < 64 * 1024


# -- bounded strict decode --------------------------------------------------


class TestBoundedDecode:
    def test_decoded_cap_boundary_8mib(self) -> None:
        at_cap = padded_json(core.SINGLE_ROW_DECODED_CAP)
        assert len(at_cap) == core.SINGLE_ROW_DECODED_CAP
        got = core.decode_payload("blob", as_blob(at_cap), decoded_cap=core.SINGLE_ROW_DECODED_CAP)
        assert len(got["a"]) == core.SINGLE_ROW_DECODED_CAP - len('{"a": ""}')
        over = refusal(
            "blob",
            as_blob(at_cap + " "),
            decoded_cap=core.SINGLE_ROW_DECODED_CAP,
        )
        assert (over.reason, over.limit_kind, over.limit_bytes) == (
            "resource_limit",
            "decoded",
            core.SINGLE_ROW_DECODED_CAP,
        )
        # the ordinary default is unchanged
        ordinary = refusal("blob", as_blob(at_cap))
        assert (ordinary.limit_kind, ordinary.limit_bytes) == ("decoded", core.DECODED_CAP)
        assert core.SINGLE_ROW_STORED_CAP == 8 * core.STORED_CAP == 8 * MIB

    def test_highly_compressed_small_blob_needs_promotion(self) -> None:
        blob = as_blob(padded_json(5 * MIB))
        assert len(blob) < core.STORED_CAP // 16  # tiny stored size, decoded > ordinary cap
        assert refusal("blob", blob).limit_kind == "decoded"
        got = core.decode_payload("blob", blob, decoded_cap=core.SINGLE_ROW_DECODED_CAP)
        assert len(got["a"]) > core.DECODED_CAP

    def test_bomb_decode_is_hard_bounded(self) -> None:
        bomb = as_blob(padded_json(48 * MIB))
        assert len(bomb) < MIB
        tracemalloc.start()
        try:
            tracemalloc.reset_peak()
            exc = refusal("blob", bomb, decoded_cap=core.SINGLE_ROW_DECODED_CAP)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        assert exc.limit_kind == "decoded"
        # measured transient peak is ~2x the cap (output buffer + final bytes copy), not 48 MiB
        assert peak < 2 * core.SINGLE_ROW_DECODED_CAP + MIB
        print("RECORDED_PEAK " + json.dumps({"scenario": "zlib bomb refusal", "peak_bytes": peak}))

    def test_decoded_exhaustion_precedes_unestablishable_defects(self) -> None:
        big = as_blob(padded_json(10 * MIB))
        cap = core.SINGLE_ROW_DECODED_CAP
        for bad in (big[:-4], big + b"\x00", big + big):  # truncated, trailing, concatenated
            exc = refusal("blob", bad, decoded_cap=cap)
            assert (exc.reason, exc.limit_kind, exc.limit_bytes) == (
                "resource_limit",
                "decoded",
                cap,
            )
        good = as_blob(padded_json(MIB))
        for bad in (good[:-4], good + b"\x00", good + good):  # defect detectable within the bound
            exc = refusal("blob", bad, decoded_cap=cap)
            assert (exc.reason, exc.limit_kind) == ("invalid_compression", None)

    def test_oversized_zero_blob_is_invalid_compression(self) -> None:
        exc = refusal("blob", b"\x00" * SINGLE, decoded_cap=core.SINGLE_ROW_DECODED_CAP)
        assert (exc.reason, exc.limit_kind, exc.limit_bytes) == ("invalid_compression", None, None)

    def test_recursion_has_no_byte_budget(self) -> None:
        deep = ('{"a": ' + "[" * 100_000 + "]" * 100_000 + "}").encode()
        exc = refusal("text", deep, decoded_cap=core.SINGLE_ROW_DECODED_CAP)
        assert (exc.reason, exc.limit_kind, exc.limit_bytes) == ("resource_limit", None, None)


# -- planning bounds --------------------------------------------------------


def _counting(fn: Any) -> Any:
    def wrapped(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        wrapped.calls += 1  # type: ignore[attr-defined]
        return fn(payload)

    wrapped.calls = 0  # type: ignore[attr-defined]
    return wrapped


class TestPlanBounds:
    def test_clean_expanded_row_needs_no_write(self, store: Store) -> None:
        clean = payload_json(4_000_000, secret=False)
        blob = as_blob(clean)
        assert len(blob) > core.STORED_CAP  # stored overflow only: decoded fits the ordinary cap
        assert len(clean) <= core.DECODED_CAP
        store.insert(1, blob, blob)
        ordinary = fetch_one(store.conn, 1)
        assert ordinary is not None and ordinary.raw.value is None  # today: refused every run
        plan, problems = core.plan_row(obs_of(store), core.scrub_marker)
        assert problems == () and plan is not None and not plan.changed

    def test_local_dirty_expanded_scrubbed_beyond_request_estimate(self, local: Store) -> None:
        a, b = payload_json(7_000_000), payload_json(7_000_000, seed=2)
        local.insert(1, as_blob(a), as_blob(b))
        obs = obs_of(local)
        remote_view, remote_problems = core.plan_row(obs, core.scrub_marker)
        assert remote_view is None
        assert remote_problems == (
            core.Problem(None, "resource_limit", "request", core.REQUEST_BYTES_CAP),
        )
        plan, problems = core.plan_row(obs, core.scrub_marker, request_cap=None)
        assert problems == () and plan is not None and plan.changed
        assert len(plan.params[4]) + len(plan.params[6]) + plan.replacement_bytes > 12 * MIB
        acct, counters = Accounting(), Counters()
        assert core.process_expanded(local.conn, obs, plan.desired, acct, counters) is None
        assert counters.updates_applied == 1
        for col, original in (("raw_line", a), ("parsed_json", b)):
            sql_type, data = local.cell(1, col)
            assert sql_type == "blob" and data is not None
            text = zlib.decompress(data).decode()
            assert core.SECRET not in text and core.CLEAN in text and len(text) < len(original)
        again, problems = core.plan_row(obs_of(local), core.scrub_marker, request_cap=None)
        assert problems == () and again is not None and not again.changed  # rerun is clean

    def test_remote_dirty_over_request_refused_unchanged(self, remote: Store) -> None:
        a, b = as_blob(payload_json(7_000_000)), as_blob(payload_json(7_000_000, seed=2))
        remote.insert(1, a, b)
        obs = obs_of(remote)
        before = len(remote.stub.requests)  # type: ignore[union-attr]
        plan, problems = core.plan_row(obs, core.scrub_marker)
        assert plan is None
        assert problems == (core.Problem(None, "resource_limit", "request", 8 * MIB),)
        assert len(remote.stub.requests) == before  # type: ignore[union-attr]  # nothing written
        assert remote.cell(1, "raw_line") == ("blob", a)
        assert remote.cell(1, "parsed_json") == ("blob", b)

    def test_request_estimate_exact_boundary(self, remote: Store) -> None:
        remote.insert(1, as_blob(payload_json(3_000_000)), as_blob(payload_json(3_000_000, False)))
        obs = obs_of(remote)
        assert obs.raw.length is not None and obs.raw.length > core.STORED_CAP
        plan, problems = core.plan_row(obs, core.scrub_marker, request_cap=None)
        assert problems == () and plan is not None and plan.changed
        est = estimate_request_bytes(UPDATE_SQL, [plan.params], shape="batch")
        assert est < core.REQUEST_BYTES_CAP
        ok, ok_problems = core.plan_row(obs, core.scrub_marker, request_cap=est)
        assert ok_problems == () and ok is not None  # cap
        no, no_problems = core.plan_row(obs, core.scrub_marker, request_cap=est - 1)
        assert no is None and no_problems == (
            core.Problem(None, "resource_limit", "request", est - 1),
        )
        # the estimate really bounds the captured wire body and the write succeeds
        assert remote.conn.executemany(UPDATE_SQL, [plan.params]).rowcount == 1
        body = len(remote.stub.requests[-1]["body"].encode())  # type: ignore[union-attr]
        assert body <= est <= core.REQUEST_BYTES_CAP

    def test_incremental_estimate_skips_later_column(self, remote: Store) -> None:
        remote.insert(1, as_blob(payload_json(7_000_000)), as_blob(payload_json(7_000_000, seed=2)))
        counting = _counting(core.scrub_marker)
        plan, problems = core.plan_row(obs_of(remote), counting)
        assert plan is None
        assert problems == (core.Problem(None, "resource_limit", "request", 8 * MIB),)
        assert counting.calls == 1  # the first candidate alone overflowed; column 2 not planned

    def test_replacement_output_budgets(self, local: Store) -> None:
        small = payload_json(100)
        local.insert(1, small, small)
        obs = obs_of(local)
        base = len(json.dumps({"t": ""}))

        def grow(size: int, *, as_text: bool = True) -> Any:
            def sanitize(_payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
                return {"t": "y" * (size - base)}, 1

            return sanitize

        kw = {"request_cap": None}
        ok, problems = core.plan_row(obs, grow(2000), stored_cap=2000, decoded_cap=1 << 20, **kw)
        assert problems == () and ok is not None  # replacement == stored cap
        no, problems = core.plan_row(obs, grow(2001), stored_cap=2000, decoded_cap=1 << 20, **kw)
        assert no is None and problems[0] == core.Problem(
            "raw_line", "resource_limit", "replacement_stored", 2000, obs.raw.length
        )
        # decoded budget: BLOB replacements compress, so stored fits while decoded overflows
        blob_small = as_blob(small)
        local.insert(2, blob_small, blob_small)
        o2 = obs_of(local, 2)
        no, problems = core.plan_row(o2, grow(50_000), stored_cap=1 << 20, decoded_cap=4096, **kw)
        assert no is None and problems[0].limit_kind == "replacement_decoded"
        assert problems[0].limit_bytes == 4096
        # real constants: a TEXT replacement one byte over the 8 MiB singleton budget
        no, problems = core.plan_row(obs, grow(SINGLE + 1), **kw)
        assert no is None and problems[0].limit_kind == "replacement_stored"
        assert problems[0].limit_bytes == SINGLE
        ok, problems = core.plan_row(obs, grow(SINGLE), **kw)
        # both columns grow to exactly the per-column budget: 8 MiB each, 16 MiB retained locally
        assert problems == () and ok is not None and ok.replacement_bytes == 2 * SINGLE

    def test_failed_sibling_discards_other_plan(self, local: Store) -> None:
        local.insert(1, payload_json(1000), as_blob(padded_json(9 * MIB)))
        plan, problems = core.plan_row(obs_of(local), core.scrub_marker, request_cap=None)
        assert plan is None  # raw_line was dirty and plannable, but the row is atomic
        assert [(p.column, p.limit_kind, p.limit_bytes) for p in problems] == [
            ("parsed_json", "decoded", core.SINGLE_ROW_DECODED_CAP)
        ]


# -- expanded reconciliation ------------------------------------------------


def _lost_ack_row(s: Store, row_id: int) -> tuple[core.Observed, core.Plan]:
    s.insert(row_id, as_blob(payload_json(3_000_000)), as_blob(payload_json(3_000_000, False)))
    obs = obs_of(s, row_id)
    assert (
        obs.parsed.length is not None and obs.parsed.length > core.STORED_CAP
    )  # big clean sibling
    plan, problems = core.plan_row(obs, core.scrub_marker)
    assert problems == () and plan is not None and plan.changed and plan.parsed is None
    return obs, plan


def _lose_ack(s: Store, obs: core.Observed, plan: core.Plan, **kw: Any) -> tuple[Any, ...]:
    stub = s.stub
    assert stub is not None
    stub.stall_body = 2.5  # reply stalls AFTER the batch executed and committed
    acct, counters = Accounting(), Counters()
    verdict = core.process_expanded(
        s.conn,
        obs,
        plan.desired,
        acct,
        counters,
        after_apply=lambda: setattr(stub, "stall_body", 0.0),
        **kw,
    )
    return verdict, acct, counters


class TestExpandedReconciliation:
    def test_lost_ack_found_desired_with_expanded_read(self, lossy_remote: Store) -> None:
        obs, plan = _lost_ack_row(lossy_remote, 1)
        original_parsed = lossy_remote.cell(1, "parsed_json")
        verdict, acct, counters = _lose_ack(lossy_remote, obs, plan)
        assert verdict == "desired"
        assert acct.state.unconfirmed == (1,) and not counters.counts_complete
        assert counters.reconciled == 1 and counters.updates_applied == 0
        assert counters.retries == 0 and counters.conflicts == 0  # no rewrite, no false conflict
        assert lossy_remote.cell(1, "raw_line") == ("blob", plan.raw)
        assert lossy_remote.cell(1, "parsed_json") == original_parsed  # exact untouched sibling

    def test_ordinary_read_misclassifies_oversized_sibling(self, lossy_remote: Store) -> None:
        obs, plan = _lost_ack_row(lossy_remote, 1)
        verdict, _acct, counters = _lose_ack(lossy_remote, obs, plan, read_cap=core.STORED_CAP)
        assert verdict == "changed"  # the 1 MiB read cannot see the sibling: false conflict
        assert counters.conflicts == 1 and counters.reconciled == 0
        assert lossy_remote.cell(1, "raw_line") == ("blob", plan.raw)  # it did converge

    def test_replacement_grown_past_ordinary_cap(self, lossy_remote: Store) -> None:
        original = payload_json(2000)
        lossy_remote.insert(1, original, original)
        obs = obs_of(lossy_remote)
        grown = json.dumps({"t": "z" * (MIB + MIB // 2)}).encode("ascii")
        _v, _a, ordinary = _lose_ack(
            lossy_remote, obs, core.Plan(obs, grown, None, {}, (), 0), read_cap=core.STORED_CAP
        )
        assert ordinary.conflicts == 1  # only the replacement exceeds the page cap
        lossy_remote.raw.execute("UPDATE raw_events SET raw_line = ? WHERE id = 1", (original,))
        verdict, _acct, wide = _lose_ack(lossy_remote, obs, core.Plan(obs, grown, None, {}, (), 0))
        assert verdict == "desired" and wide.reconciled == 1 and wide.conflicts == 0

    def test_over_cap_version_is_conflict_not_convergence(self, lossy_remote: Store) -> None:
        obs, plan = _lost_ack_row(lossy_remote, 1)
        stub = lossy_remote.stub
        assert stub is not None
        stub.stall_body = 2.5
        acct, counters = Accounting(), Counters()

        def other_writer() -> None:
            stub.stall_body = 0.0
            stub.db.execute(
                "UPDATE raw_events SET raw_line = ? WHERE id = 1", (rand_bytes(SINGLE + 1),)
            )

        verdict = core.process_expanded(
            lossy_remote.conn, obs, plan.desired, acct, counters, after_apply=other_writer
        )
        assert verdict == "changed"
        assert counters.conflicts == 1 and counters.reconciled == 0 and counters.retries == 0
        assert lossy_remote.cell(1, "raw_line")[1] is not None  # the other writer's version stays
        assert len(lossy_remote.cell(1, "raw_line")[1] or b"") == SINGLE + 1

    def test_concurrent_change_and_vanish_never_overwrite(self, local: Store) -> None:
        text = payload_json(1_500_000)
        sibling = payload_json(1_500_000, False, seed=2)
        local.insert(1, text, sibling)
        local.insert(2, text, sibling)
        for row_id, mutate, expect in (
            (1, "UPDATE raw_events SET parsed_json = ? WHERE id = 1", "changed"),
            (2, "DELETE FROM raw_events WHERE id = 2", "vanished"),
        ):
            obs = obs_of(local, row_id)
            assert obs.raw.length is not None and obs.raw.length > core.STORED_CAP
            plan, problems = core.plan_row(obs, core.scrub_marker, request_cap=None)
            assert problems == () and plan is not None and plan.changed
            same_size_other = payload_json(1_500_000, False, seed=9)
            assert len(same_size_other) == len(sibling)
            params = (same_size_other,) if row_id == 1 else ()
            local.raw.execute(mutate, params)  # another writer acts between fetch and write
            acct, counters = Accounting(), Counters()
            verdict = core.process_expanded(local.conn, obs, plan.desired, acct, counters)
            assert verdict == expect and counters.conflicts == 1
            assert counters.updates_applied == 0 and counters.retries == 0
        assert local.cell(1, "raw_line") == ("text", text.encode())  # not overwritten
        assert local.cell(1, "parsed_json") == ("text", same_size_other.encode())  # other writer


# -- recorded absolute peaks ------------------------------------------------

PEAK_SANITY_CEILING = 1 << 30  # recorded, not gated; only a surprising peak fails


class TestRecordedPeaks:
    def _record(self, result: dict[str, Any]) -> None:
        print("RECORDED_PEAK " + json.dumps(result))
        assert 0 < result["peak_bytes"] < PEAK_SANITY_CEILING

    def test_page_co_retention_plus_singleton(self, local: Store, tmp_path: Path) -> None:
        local.conn.close()
        conn = driver.sqlite_store(str(tmp_path / "peak1.db"))
        try:
            self._record(driver.peak_page_plus_singleton(conn))
        finally:
            conn.close()

    def test_local_dirty_write_binds_originals_and_replacements(self, tmp_path: Path) -> None:
        conn = driver.sqlite_store(str(tmp_path / "peak2.db"))
        try:
            result = driver.peak_local_dirty_write(conn)
            assert result["param_bytes"] > 16 * MIB  # the ~32 MiB-class parameter binding
            self._record(result)
        finally:
            conn.close()

    def test_dense_json_decode_at_8mib(self, tmp_path: Path) -> None:
        conn = driver.sqlite_store(str(tmp_path / "peak3.db"))
        try:
            self._record(driver.peak_dense_json(conn))
        finally:
            conn.close()

    def test_expanded_lost_ack_reconcile(self, lossy_remote: Store) -> None:
        assert lossy_remote.stub is not None
        result = driver.peak_expanded_reconcile(lossy_remote.stub, lossy_remote.conn)
        assert result["verdict"] == "desired"
        self._record(result)


# -- guards -------------------------------------------------------------------


def _imports(path: Path) -> list[str]:
    out: list[str] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append(node.module or "")
    return out


def test_guard_spike_does_not_import_production_raw_redaction() -> None:
    for path in SPIKE_DIR.glob("*.py"):
        for module in _imports(path):
            scrubbed = module.replace("enh3752_raw_redaction", "").replace(
                "bug3762_singleton_redaction", ""
            )
            assert "raw_redaction" not in scrubbed, (path, module)


def test_guard_no_private_client_calls() -> None:
    tree = ast.parse((SPIKE_DIR / "singleton_core.py").read_text())
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attrs & {"client", "batch", "_post", "execute_many", "_stmt"}
    calls = [
        ast.unparse(n.func)
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    ]
    assert "sqlite3.connect" not in calls


def test_guard_no_chunked_or_hash_reads() -> None:
    source = (SPIKE_DIR / "singleton_core.py").read_text()
    assert "substr(" not in source.lower() and "hashlib" not in source
    assert not any("hashlib" in m or m == "hmac" for m in _imports(SPIKE_DIR / "singleton_core.py"))
