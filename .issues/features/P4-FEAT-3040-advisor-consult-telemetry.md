---
id: FEAT-3040
title: Advisor consult telemetry in history.db
type: FEAT
parent: EPIC-3041
priority: P4
status: open
testable: true
discovered_date: 2026-08-03
depends_on:
- FEAT-3044
- FEAT-3038
labels:
- planning-hub
verify_verdict: VALID
---

# FEAT-3040: Advisor consult telemetry in history.db

## Summary

Slice 4 of the host-agnostic advisor (FEAT-3037). Persist every consult to
`.ll/history.db` so `ll-ctx-stats` and downstream analytics can answer whether
consults are worth their cost: which signals trigger them, what they cost, and
whether the run outcome improved after one.

## Current Behavior

- Consults leave no durable trace. The verdict lands in a transcript or an
  `EvaluationResult`, and the per-task counter (FEAT-3038) is ephemeral state
  scoped to a run.
- `.ll/history.db` already records `loop_events`, `issue_events`, `cli_events`,
  `usage_events`, `orchestration_runs`, and more via
  `scripts/little_loops/session_store/schema.py` + `writers.py`, and
  `history_reader.py` is the typed read surface — but nothing records escalation
  decisions.
- There is consequently no way to evaluate the design's central claim: that a
  signal-gated consult beats another cheap-model iteration.

## Expected Behavior

- Each consult writes one `advisor_consults` row: timestamp, session, task key,
  signal, advisor host + model, main model, capability-floor status, latency,
  token usage where the host reports it, verdict confidence, and whether it was
  skipped (budget/floor/failure) rather than issued.
- Skipped consults are recorded too — a budget-exhausted or floor-violating
  consult is exactly the datum an operator wants.
- `history_reader.py` gains a typed query; `ll-ctx-stats` reports consult counts
  by signal and their aggregate cost.
- The verdict *body* is not stored by default (it can quote private code);
  storage is opt-in, consistent with how other private content is handled.

## Use Case

After a month of running `autodev` with `confidence_gate` consults enabled, an
operator asks whether they are paying off. `ll-ctx-stats` shows 47 consults, 31
from `confidence_gate`, at a measurable token cost — and that runs with a
consult reached `done` at a materially different rate than runs that blocked
without one. That is the evidence that decides whether to keep the trigger on,
and it is unavailable today.

## Proposed Solution

Follow the existing table-plus-writer-plus-reader pattern rather than inventing
a parallel store:

1. `CREATE TABLE IF NOT EXISTS advisor_consults` in `session_store/schema.py`,
   alongside `usage_events` and `orchestration_runs`.
2. A writer in `session_store/writers.py`, called from
   `little_loops.advisor.consult()` — one write per consult attempt, issued or
   skipped, never on the caller's critical path (a failed write logs and is
   dropped).
3. A typed query in `history_reader.py` and a `ll-ctx-stats` section.

Retention follows existing policy: rows are pruned only by an explicitly-run CLI
action, never automatically.

## Program Design

### Types

- `AdvisorConsultRow: {id: int, ts: str, session_id: str, task_key: str, signal: str, advisor_host: str, advisor_model: str, main_model: str, floor_status: str, outcome: Literal["issued", "skipped_budget", "skipped_floor", "failed", "timeout"], latency_ms: int | None, input_tokens: int | None, output_tokens: int | None, confidence: float | None}`
- `ConsultStats: {by_signal: dict[str, int], total: int, total_tokens: int, skipped: int}`

### Signatures

- `write_advisor_consult(conn: sqlite3.Connection, row: AdvisorConsultRow) -> None`
- `query_advisor_consults(db_path: Path, *, since: str | None = None) -> list[AdvisorConsultRow]`
- `consult_stats(db_path: Path, *, days: int = 30) -> ConsultStats`

### Call Path

`little_loops.advisor.consult` -> `write_advisor_consult` -> `.ll/history.db`

`ll-ctx-stats` -> `consult_stats` -> `query_advisor_consults`

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/schema.py` — `advisor_consults` table +
  schema-version bump if the migration path requires one.
- `scripts/little_loops/session_store/writers.py` — `write_advisor_consult`.
- `scripts/little_loops/history_reader.py` — `query_advisor_consults`,
  `consult_stats`.
- `scripts/little_loops/advisor.py` — call the writer on every attempt.
- `ll-ctx-stats` implementation — new report section.

### Dependent Files (Callers/Importers)

- FEAT-3038's budget counter — consider deriving the per-task count from this
  table once it exists, collapsing two counters into one source of truth.

### Similar Patterns

- `usage_events` / `orchestration_runs` — the closest existing shape (a
  per-invocation row with cost fields).

### Tests

- `scripts/tests/` session-store tests — table creation, migration from a
  pre-existing DB, writer round-trip.
- Reader tests — `since` filtering, `consult_stats` aggregation by signal.
- `advisor.py` — a failing DB write does not fail the consult.
- Verify no verdict body is persisted unless explicitly opted in.

### Documentation

- `docs/reference/API.md` — new reader functions.
- `docs/reference/CLI.md` — `ll-ctx-stats` section.

## Acceptance Criteria

1. Every consult attempt writes exactly one `advisor_consults` row, including
   attempts skipped for budget or capability-floor reasons (distinguishable via
   `outcome`).
2. The table is created on a fresh DB and added cleanly to a pre-existing DB
   without data loss.
3. A DB write failure logs and is dropped — the consult still returns its
   verdict to the caller.
4. `query_advisor_consults` filters by `since`; `consult_stats` aggregates
   counts and token totals by signal.
5. `ll-ctx-stats` reports consult counts by signal and aggregate cost.
6. The verdict body is absent from the DB unless the opt-in is set.
7. No automatic pruning or compaction of these rows is added; deletion remains a
   manually-run CLI action.
8. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` pass.

## Impact

- **Priority**: P4 — pure observability. Nothing depends on it, but it is what
  makes the advisor's cost/benefit answerable rather than assumed.
- **Effort**: Small — the table/writer/reader pattern is well-established; the
  only judgment call is the privacy posture on verdict bodies.
- **Risk**: Low — additive schema, fail-soft writes, off the critical path.
- **Breaking Change**: No.

## Related Key Documentation

- `docs/reference/API.md#little_loopshistory_reader`

## Status

**Open** | Created: 2026-08-03 | Priority: P4


## Session Log
- `/ll:verify-issues` - 2026-08-13T03:05:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:refine-issue` - 2026-08-07T01:37:33 - `43a0ea06-a76f-4e88-9656-365f95bb1daf.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T23:56:02 - `81d59bbb-17b9-42e5-908c-ba7206c84d60.jsonl`
