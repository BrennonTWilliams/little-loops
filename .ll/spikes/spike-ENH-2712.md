# Spike Plan: ENH-2712 — live per-invocation `run_id` writer on `usage_events`

## Context

From ENH-2712's `### Outcome Risk Factors`:

> No existing live per-invocation writer exists yet — only the JSONL-backfill
> path (`_backfill_usage_events()`) currently populates `usage_events`. The
> live write-through is an unproven internal mechanism with no test coverage
> of the live-write path today; a code spike proving this mechanism (schema
> write + `_finish()` hook, minimal case) before full implementation would
> de-risk it.

Both canonical low-confidence drivers apply, and codebase research sharpens
exactly where:

**(a) zero precedent** — `FSMExecutor` (`fsm/executor.py`) only wires the
legacy `on_usage: UsageCallback` (`(input_tokens, output_tokens)` ints) at
lines 1487/2188, never `on_usage_detailed: DetailedUsageCallback` (the richer
`TokenUsage` dataclass with `model`, all four token fields —
`subprocess_utils.py:44-60`). Nothing in the live run path persists a row
anywhere; token totals only ever reach the caller in memory. The only writer
of `usage_events` today is `_backfill_usage_events()`
(`session_store.py:2636`), which derives rows from on-disk transcript JSONL
**after the fact** and has no concept of "the run currently executing." There
is no code today that opens a live-write path and stamps a `run_id` mid-run.

**(b) no test exercises the risky core** — no test invokes a live
`on_usage_detailed` callback and writes to `usage_events` from inside a
running FSM loop, let alone from **multiple concurrent processes** (the
`ll-parallel`/`ll-sprint` scenario the issue's own Option A/B analysis
identifies as the reason Option A was selected over B).

The spike must rule out two concrete failure modes before the real
`_finish()`/`record_loop_run_summary()` sibling wiring is attempted:

1. A per-invocation write, fired synchronously inside a live-run callback,
   correctly stamps the run's `run_id` on the row it writes (the join key
   Option A depends on) — not approximated by session/time matching.
2. Under **concurrent** writers (simulating `ll-parallel` workers each running
   a separate loop against the same on-disk `history.db`), every row still
   lands with the correct `run_id` and no writes are silently lost or
   corrupted — using the *existing* `busy_timeout`/WAL concurrency pragmas
   (`session_store.py:917-936`), not a new locking scheme.

## Approach

Build a small standalone module that mimics the two things `_finish()` and a
live `on_usage_detailed` callback would need, wired together exactly the way
Option A proposes — **without touching `fsm/executor.py` or `session_store.py`**:

- A `record_usage_event(db_path, *, run_id, ts, model, input_tokens,
  output_tokens, cache_read_tokens, cache_creation_tokens)` function that
  opens a connection with the same `busy_timeout` + `WAL` pragmas
  `session_store._configure_connection()` applies, and does a plain
  `INSERT` (no `run_id` UNIQUE constraint — many usage rows share one
  `run_id`) into a schema-identical `usage_events` table (columns copied
  verbatim from `session_store.py:739-763`, plus a `run_id TEXT` column,
  the exact ALTER the real migration would add).
- A `simulate_run(db_path, run_id, n_invocations)` driver standing in for an
  FSM run: it derives `run_id` the same way `_finish()` does
  (`self.started_at` + loop name, `fsm/executor.py:2601`) and calls
  `record_usage_event(...)` once per simulated state — i.e. exactly what a
  live `on_usage_detailed` callback wired at the same call sites as today's
  `on_usage` (lines 1487, 2188) would do per invocation.
- A concurrency harness using Python's `multiprocessing` to launch N
  simulated runs in **separate processes** against the same on-disk SQLite
  file (the real `ll-parallel` topology — separate OS processes, not
  threads), each writing its own `run_id`'s rows interleaved in time.

What's faked: the actual host-CLI subprocess and stream-json parsing (already
proven and unrelated to this risk) — `simulate_run` calls
`record_usage_event` directly with synthetic token counts instead of driving
a real `claude -p` invocation. What's real: the SQLite schema, the
`busy_timeout`/WAL pragma configuration, the `run_id` derivation shape, and
genuine OS-level process concurrency.

## Critical files

Read-only references (contract the spike must honor, not modify):

- `scripts/little_loops/session_store.py:739-763` — `usage_events` schema the
  spike's table must match column-for-column (plus the new `run_id` column).
- `scripts/little_loops/session_store.py:913-936` — `_BUSY_TIMEOUT_MS` /
  `_configure_connection()` pragma pattern the spike's connection setup must
  replicate.
- `scripts/little_loops/fsm/executor.py:2598-2613` — `_finish()`'s `run_id`
  derivation (`self.started_at` sanitized + `-{loop_name}`) the spike's
  `simulate_run` must reproduce exactly.
- `scripts/little_loops/subprocess_utils.py:44-60` — `TokenUsage` field shape
  the spike's synthetic per-invocation record must mirror.

New spike paths to create under `scripts/tests/spike/usage_events_run_id_writer/`.

## Implementation

```
scripts/tests/spike/usage_events_run_id_writer/
├── __init__.py
├── writer.py                 # record_usage_event(), simulate_run(), schema DDL
└── test_writer.py             # the AC test class
```

`writer.py` sketch:

```python
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
"""

def _connect(db_path: str) -> sqlite3.Connection: ...
    # busy_timeout + WAL, mirroring session_store._configure_connection()

def record_usage_event(db_path, *, run_id, ts, model,
                        input_tokens, output_tokens,
                        cache_read_tokens, cache_creation_tokens) -> None: ...

def derive_run_id(started_at: str, loop_name: str) -> str: ...
    # exact port of fsm/executor.py:2601's sanitization

def simulate_run(db_path, loop_name, started_at, n_invocations) -> str:
    # returns run_id; calls record_usage_event() n_invocations times
```

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_single_run_stamps_correct_run_id` | Risk (a): no live per-invocation writer exists; proves a mid-run write correctly stamps its own `run_id` | behavior |
| `test_concurrent_runs_do_not_cross_attribute` | Risk (b) + Option A's core justification: N concurrent processes writing to the same db each retain correct `run_id` attribution, no cross-contamination | behavior |
| `test_concurrent_runs_lose_no_writes` | Risk (b): busy_timeout/WAL pragma reuse survives real process-level contention with zero dropped rows | behavior |
| `test_run_id_derivation_matches_executor_format` | Confirms the spike's `derive_run_id()` produces byte-identical output to `_finish()`'s inline derivation, so the real wiring is a drop-in | behavior |
| `test_spike_does_not_import_production_modules` | isolation guard | regression |

## Verification

```bash
python -m pytest scripts/tests/spike/usage_events_run_id_writer/ -v
python -m pytest scripts/tests/test_session_store.py -k "UsageEvents or SchemaV28" -v
python -m pytest scripts/tests/test_history_reader.py -k "CostAttribution" -v
```

## Out of Scope

- The real `v29` schema migration and `_MIGRATIONS` entry (that's a one-line
  `ALTER TABLE` once this spike proves the write pattern — no risk to retire).
- Wiring `on_usage_detailed` into `FSMExecutor` itself, or the `_finish()` /
  `record_loop_run_summary()` call-site change.
- `waste_attribution()` / `ctx_stats.py` CLI surface (separate, low-risk query
  + presentation layer, not the risky mechanism).
- Reconciling with `ARCHITECTURE-145` (ENH-2461) precedent — a decision-log
  question, not a technical-proof question; handled by re-running
  `/ll:confidence-check` / `/ll:decide-issue` after this spike, not by code.

## Promotion

On acceptance, promote `record_usage_event()` / `derive_run_id()` from
`scripts/tests/spike/usage_events_run_id_writer/writer.py` into
`scripts/little_loops/spike/usage_events_run_id_writer/` in a **separate PR**,
then wire the real `v29` migration and the `_finish()` call-site change as the
actual ENH-2712 implementation.
