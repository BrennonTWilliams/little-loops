"""Fixtures and absolute ``tracemalloc`` peak scenarios for the BUG-3762 spike.

Run ``python -m scripts.tests.spike.bug3762_singleton_redaction.driver`` to print the recorded
peaks (with fixture hashes and the Python version). Peaks are recorded, not gated.
"""

from __future__ import annotations

import hashlib
import json
import platform
import random
import sqlite3
import tracemalloc
import zlib
from collections.abc import Callable
from typing import Any

from scripts.tests.spike.bug3762_singleton_redaction import singleton_core as core
from scripts.tests.spike.enh3752_raw_redaction.redaction_core import (
    Accounting,
    Counters,
    fetch_page,
)

DDL = """
CREATE TABLE raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, session_id TEXT,
    host TEXT NOT NULL, source_path TEXT NOT NULL, line_no INTEGER NOT NULL,
    event_type TEXT NOT NULL, raw_line TEXT NOT NULL, parsed_json TEXT NOT NULL);
CREATE UNIQUE INDEX idx_dedup ON raw_events(source_path, line_no);
"""
INSERT = (
    "INSERT INTO raw_events(id, ts, host, source_path, line_no, event_type, raw_line,"
    " parsed_json) VALUES (?, 't', 'claude-code', 'p', ?, 'assistant', ?, ?)"
)
SEED = 3762


def payload_json(hex_chars: int, secret: bool = True, *, seed: int = SEED) -> str:
    """Supported assistant payload: seeded incompressible hex plus an optional marker."""
    body = random.Random(seed).randbytes(hex_chars // 2).hex()
    if secret:
        body += " " + core.SECRET
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": body}]}})


def as_blob(text: str) -> bytes:
    return zlib.compress(text.encode("utf-8"), 6)


def padded_json(total_bytes: int) -> str:
    """Valid JSON object of exactly ``total_bytes`` characters (highly compressible)."""
    head, tail = '{"a": "', '"}'
    return head + "x" * (total_bytes - len(head) - len(tail)) + tail


def dense_json(total_bytes: int) -> str:
    """Structurally dense JSON: a list of empty objects (worst-case allocation per byte)."""
    n = (total_bytes - len('{"a": []}')) // 3
    return '{"a": [' + ",".join(["{}"] * n) + "]}"


def digest(*parts: bytes | str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else p.encode())
    return h.hexdigest()[:12]


def _measure(fn: Callable[[], Any]) -> tuple[Any, int]:
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        result = fn()
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    return result, peak


def sqlite_store(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None)
    conn.executescript(DDL)
    return conn


def peak_page_plus_singleton(conn: sqlite3.Connection) -> dict[str, Any]:
    """Ordinary page (8 rows x 2 x 1 MiB) stays retained while a promoted row is processed."""
    full = bytes(random.Random(SEED).randbytes(core.STORED_CAP))
    for i in range(1, 9):
        conn.execute(INSERT, (i, i, full, full))
    a, b = payload_json(8_300_000), payload_json(8_300_000, seed=SEED + 1)
    conn.execute(INSERT, (9, 9, as_blob(a), as_blob(b)))

    def run() -> Any:
        page = fetch_page(conn, snapshot=8, last_id=None, limit=8)  # retained for the duration
        obs = core.fetch_singleton(conn, 9)
        assert obs is not None
        plan, problems = core.plan_row(obs, core.scrub_marker, request_cap=None)
        assert plan is not None and plan.changed and not problems
        return len(page), plan.replacement_bytes

    (rows, repl), peak = _measure(run)
    return {
        "scenario": "ordinary page co-retained + singleton plan (BLOB/BLOB, ~8 MiB decoded)",
        "peak_bytes": peak,
        "page_rows": rows,
        "replacement_bytes": repl,
        "fixture": digest(a, b),
    }


def peak_local_dirty_write(conn: sqlite3.Connection) -> dict[str, Any]:
    """TEXT/TEXT row, ~8 MiB each: both originals + both replacements bound (~32 MiB params)."""
    a, b = payload_json(8_300_000), payload_json(8_300_000, seed=SEED + 1)
    conn.execute(INSERT, (1, 1, a, b))

    def run() -> Any:
        obs = core.fetch_singleton(conn, 1)
        assert obs is not None
        plan, problems = core.plan_row(obs, core.scrub_marker, request_cap=None)
        assert plan is not None and plan.changed and not problems
        acct, counters = Accounting(), Counters()
        core.process_expanded(conn, obs, plan.desired, acct, counters)
        return counters.updates_applied, plan.replacement_bytes

    (applied, repl), peak = _measure(run)
    assert applied == 1
    return {
        "scenario": "local dirty write (TEXT/TEXT ~8 MiB: originals + replacements bound)",
        "peak_bytes": peak,
        "replacement_bytes": repl,
        "param_bytes": 2 * len(a.encode()) + repl,
        "fixture": digest(a, b),
    }


def peak_dense_json(conn: sqlite3.Connection) -> dict[str, Any]:
    """Structurally dense 8 MiB JSON decode + sanitize (allocation per byte is worst-case)."""
    dense = dense_json(core.SINGLE_ROW_DECODED_CAP)
    assert len(dense) <= core.SINGLE_ROW_DECODED_CAP
    blob = as_blob(dense)

    def run() -> int:
        value = core.decode_payload("blob", blob, decoded_cap=core.SINGLE_ROW_DECODED_CAP)
        _out, matches = core.scrub_marker(value)
        return matches

    _, peak = _measure(run)
    return {
        "scenario": "dense JSON ([{},{},...]) decode + walk at the 8 MiB decoded cap",
        "peak_bytes": peak,
        "decoded_bytes": len(dense),
        "stored_bytes": len(blob),
        "fixture": digest(dense),
    }


def peak_expanded_reconcile(stub: Any, conn: Any) -> dict[str, Any]:
    """Remote lost-ack reconciliation retaining original + desired plus the wide read.

    Includes allocations of the in-process ``HranaStub`` server threads, so it overstates the
    client-side peak.
    """
    # dirty raw + large clean sibling: the largest shape whose guarded request fits 8 MiB
    a, b = payload_json(3_000_000), payload_json(3_000_000, False, seed=SEED + 1)
    stub.db.execute(INSERT, (1, 1, as_blob(a), as_blob(b)))
    obs = core.fetch_singleton(conn, 1)
    assert obs is not None
    plan, problems = core.plan_row(obs, core.scrub_marker)
    assert plan is not None and plan.changed and not problems
    stub.stall_body = 2.5

    def run() -> str | None:
        return core.process_expanded(
            conn,
            obs,
            plan.desired,
            Accounting(),
            Counters(),
            after_apply=lambda: setattr(stub, "stall_body", 0.0),
        )

    verdict, peak = _measure(run)
    return {
        "scenario": "remote lost-ack reconcile, plan retained (includes in-process stub)",
        "peak_bytes": peak,
        "verdict": verdict,
        "fixture": digest(a, b),
    }


def main() -> None:  # pragma: no cover - manual recording entry point
    import tempfile
    from pathlib import Path

    from tests.hrana_stub import HranaStub

    from little_loops.session_store.hrana import HranaClient
    from little_loops.session_store.libsql import LibsqlConnection

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for fn, name in (
            (peak_page_plus_singleton, "a.db"),
            (peak_local_dirty_write, "b.db"),
            (peak_dense_json, "c.db"),
        ):
            conn = sqlite_store(str(Path(tmp) / name))
            results.append(fn(conn))
            conn.close()
    stub = HranaStub().start()
    try:
        stub.db.executescript(DDL)
        conn = LibsqlConnection(HranaClient(stub.url, "test-token", timeout=1.0))
        results.append(peak_expanded_reconcile(stub, conn))
    finally:
        stub.stop()
    print(json.dumps({"python": platform.python_version(), "peaks": results}, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
