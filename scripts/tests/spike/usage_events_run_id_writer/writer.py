"""Spike: prove a live per-invocation ``usage_events`` writer stamped with
``run_id`` survives real multi-process concurrency (ENH-2712 Option A).

Isolated from production code — mirrors, but does not import, the
``usage_events`` schema (``session_store.py:739-763``), the busy_timeout/WAL
pragma pattern (``session_store.py:913-936``), and the ``run_id`` derivation
FSMExecutor._finish() uses (``fsm/executor.py:2601``).
"""

from __future__ import annotations

import sqlite3

_BUSY_TIMEOUT_MS = 5000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    model TEXT,
    state TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_input_tokens INTEGER,
    cache_creation_input_tokens INTEGER,
    cost_usd REAL,
    run_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_events_run_id ON usage_events(run_id);
"""


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a connection with the same concurrency pragmas as
    ``session_store._configure_connection()``: ``busy_timeout`` so a
    contended open waits instead of failing instantly, and WAL so concurrent
    readers/writers don't serialize on every access.
    """
    conn = sqlite3.connect(db_path, timeout=_BUSY_TIMEOUT_MS / 1000)
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(db_path: str) -> None:
    """Create the spike's ``usage_events`` table if absent."""
    conn = _connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def derive_run_id(started_at: str, loop_name: str) -> str:
    """Byte-identical port of ``FSMExecutor._finish()``'s run_id derivation
    (``fsm/executor.py:2601,2604``), so the real wiring is a drop-in.
    """
    run_id = started_at.replace(":", "").replace(".", "").replace("+", "")[:17]
    return f"{run_id}-{loop_name}"


def record_usage_event(
    db_path: str,
    *,
    run_id: str,
    ts: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_creation_tokens: int,
) -> None:
    """Write one ``usage_events`` row stamped with ``run_id`` — the live
    per-invocation write ``on_usage_detailed`` would perform mid-run, in
    place of today's post-hoc ``_backfill_usage_events()``.
    """
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO usage_events("
            "ts, model, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens, run_id"
            ") VALUES(?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                model,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_creation_tokens,
                run_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def simulate_run(
    db_path: str,
    loop_name: str,
    started_at: str,
    n_invocations: int,
    model: str = "claude-sonnet-5",
) -> str:
    """Stand in for an FSM run: derive this run's ``run_id`` the way
    ``_finish()`` does, then write one usage row per simulated per-state
    invocation — exactly what a live ``on_usage_detailed`` callback wired at
    the same call sites as today's ``on_usage`` would do.
    """
    run_id = derive_run_id(started_at, loop_name)
    for i in range(n_invocations):
        record_usage_event(
            db_path,
            run_id=run_id,
            ts=f"{started_at}+{i}",
            model=model,
            input_tokens=1000 + i,
            output_tokens=200 + i,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
    return run_id
