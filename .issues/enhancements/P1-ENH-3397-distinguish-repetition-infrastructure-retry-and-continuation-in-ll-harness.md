---
id: ENH-3397
title: Distinguish repetition, infrastructure retry, and continuation in ll-harness
type: ENH
priority: P1
status: open
discovered_date: '2026-09-07'
labels:
- harness
- evaluation
- statistics
---

## Summary

`ll-harness` treats every re-run of a task as another sample, which silently inflates n and makes any pass-rate it reports unsound. Three distinct things are being conflated:

- a **repetition** is a new experimental sample of the same cell;
- an **infrastructure retry** is a replacement attempt for a cell whose prior attempt died for reasons unrelated to the subject (network, host crash, harness bug);
- a **continuation** is in-run agent behavior — the subject retrying itself inside a single attempt.

Only the first increments n. Give the harness an explicit run model — an experiment is `benchmark + executor + subjects + tasks + repetitions`, and a cell is `task × repetition × subject` — so each attempt is recorded against a named cell with its category, and reported n counts repetitions rather than attempts.

The governance half matters more than the accounting half. When a cell has multiple attempts, **the earliest valid attempt is authoritative** and operators cannot select a preferred outcome. Any recovery admission (discarding an attempt as an infra failure and replacing it) is written to an append-only WAL carrying a typed reason and the id of the admission it supersedes, so score-changing operator interventions are tabulated in the run report rather than invisible. This is the anti-p-hacking gate the harness has no substitute for today.

## Current Behavior

`ll-harness` records every re-run of a task as a new sample; there is no `attempt_kind`, `cell_key`, or admission concept in `harness_events`, so a repeated sample, an infra-retried attempt, and an operator's replacement of a bad attempt are all counted identically toward n. There is no `harness_admissions` audit trail, so any score-changing intervention (discarding an attempt and substituting another) is invisible in the run report.

## Expected Behavior

`ll-harness` records each attempt against an explicit cell (`target`, `task`, `subject`) with a typed `attempt_kind` (`repetition` | `infra_retry`). Only repetitions increment n; infra retries replace a dead attempt without inflating n. For a cell with multiple attempts, the earliest non-superseded attempt is authoritative and no operator flag can select a different one. Every admission (an infra retry superseding a prior attempt) is appended to an append-only `harness_admissions` table and tabulated in the run report.

## Motivation

Several existing harness capabilities — repeated sampling with verifier selection, stop-on-first-confirmation, eval saturation detection — all assume repeated runs without defining what a run *is*. Nothing separates a resample from a replacement, and nothing forbids an operator from keeping the attempt they like. Every pass-rate the harness reports today is therefore a number over an undefined denominator.

The score-reproducible-not-byte-reproducible stance already adopted elsewhere in the harness is what makes the earliest-valid rule tolerable in practice: attempts are not expected to be identical, only comparable.

## Design decisions

- **Continuations are not attempts.** The subject retrying itself inside one run is invisible to the harness by construction; record it as a nullable counter on the attempt, never as a row. The harness-level enum is therefore two-way: `repetition` | `infra_retry`.
- **Infra retry is a mechanical gate, not a free-text reason.** A retry is admissible only when the superseded attempt ended on the error path (timeout or runner error — the exit-2 branch of `_evaluate_and_report`). A graded attempt can never be retried under this issue; a wrong-but-graded verdict caused by a harness bug belongs to the separate work on deterministically unit-testing grading logic, not to an admission path.
- **Cell identity is explicit.** Cell = (target, task, subject), subject = runner label + head sha; repetition index is a stamped column.
- **No threshold.** This issue defines what n counts; how large n must be is decided by the follow-on n-run-redundancy work.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/session_store/schema.py` — `harness_events` schema lives here (v31 create at line 715; `target_content_hash`/`target_path`/`dirty` ADD COLUMNs at line 975; `idx_harness_semantic_verdict` at line 1008). Schema changes for `cell_key`/`repetition`/`attempt_kind`/`continuations`/`superseded_by` and the new `harness_admissions` table land here. This codebase's migration convention is an ordered list of DDL strings in `_MIGRATIONS` gated by a monotonic `SCHEMA_VERSION`; every entry is a comment citing its issue ID and is never edited after landing (`schema.py:1011-1018`, BUG-3236 precedent).
- `scripts/little_loops/session_store/writers.py` — `record_harness_event()` (line 1024) is the existing single-row `INSERT` writer for `harness_events`. `record_attempt()`/`admit_retry()`/`authoritative_attempt()` would sit alongside or wrap this.
- `scripts/little_loops/cli/harness.py` — `_evaluate_and_report()` (line 659) is the shared evaluation core; its error path (`result.timed_out` or `result.error is not None`, lines 668-671) returns `(2, outcome)` before any grading — this is the exact "exit-2 branch" the issue names as the sole admissible gate for `--retry-of`. Callers: `cmd_skill` (835), `cmd_cmd` (868), `cmd_mcp` (911), `cmd_prompt` (952), `cmd_dsl` (1072) — none currently thread a cell identity through calls, so a re-invocation produces an unrelated row today. `cmd_dsl`'s `graded_total`/`graded_pass` are **local variables** (first assigned line 992), not a function — `wilson_ci(graded_pass, graded_total)` (line 1145) reads them directly.
- `scripts/little_loops/cli/harness.py:588` — `history_pass_rate_runs` is **not a function**; it's a dict key computed inline in `_read_target_history()` as `pass_scored = sum(1 for e in events if e.semantic_passed is not None)` (line 623), gated by `_HISTORY_MIN_SCORED = 3` (line 585). The AC's "count repetitions, not rows" change lands in this function body, not in a separate module.
- `scripts/little_loops/history_reader/harness.py` — `harness_eval_pass_rate()` (line 113) and `harness_eval_abstention_rate()` (line 152) both aggregate unconditionally over every `harness_events` row matching `target`/`since` — no per-cell/per-repetition grouping exists today; these are the two functions the Scope Boundaries names as needing to "count repetitions."

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/harness.py:835,868,911,952,1072` — `cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt`/`cmd_dsl` each call `_evaluate_and_report()` once per invocation and unconditionally record one `harness_events` row.

### Conventions in Force
- Schema migrations are additive `ALTER TABLE`/`CREATE TABLE IF NOT EXISTS` entries appended to `_MIGRATIONS`, never edited after landing, each documented "Fix-forward only: existing rows are not backfilled" — evidence: `schema.py:931,947-948,973,1011-1018`.
- Two disagreeing precedents exist for an "audit-trail" table: `hook_events`/`test_run_events`/`commit_events` (`writers.py` — genuinely INSERT-only, no matching `UPDATE`/`DELETE` anywhere) vs. `correction_retirements` (`lifecycle.py:1390-1410` — `INSERT OR REPLACE`, an UPSERT-audit shape whose own docstring says a second call updates rather than duplicates). `harness_admissions`'s "rows are never updated or deleted" requirement matches the first group, not `correction_retirements`.
- Caveat for scope: `harness_events` itself is not fully append-only today — `cmd_dsl`'s `_update_aggregate()` closure (`cli/harness.py:1113`) already issues `UPDATE harness_events SET exit_code = ?, semantic_passed = ? WHERE id = ?` against the DSL aggregate/parent row. This existing UPDATE path is unrelated to attempt supersession and is presumably unaffected by this issue, but the new "no UPDATE/DELETE path" test must be scoped to `harness_admissions` specifically, not to `harness_events` as a whole.
- No existing test in this codebase asserts "no UPDATE/DELETE path" against a SQLite table by source inspection or otherwise — the only "append-only" tests found are JSONL-file tests (`test_fsm_persistence.py::test_events_file_is_append_only`), not SQL-table tests. This test will need a new pattern, not an adapted one.
- No existing writer validates a `Literal`/enum column against its grammar at the point of SQLite `INSERT` — `observability/schema.py`'s `Literal[...]` discriminators and `fsm/verdicts.py`'s `DEFAULT_VERDICT_ENUM` are both checked only at dataclass-construction/LLM-output time, never at the `session_store/writers.py` INSERT boundary. `attempt_kind`/admission `reason` would be the first case of a session_store writer itself validating an enum value before insert, if that validation is wanted.
- A CLI-flag refusal gated on a prior recorded status has a precedent shape (not the same storage): `cli/queue.py::cmd_requeue`/`cmd_remove` look up an entry, check its persisted `status`, and refuse with a message naming the entry, its status, and the escape hatch — `return 1`. `--retry-of`'s refusal (naming the attempt, non-zero exit) matches this shape, though the existing examples gate on a JSON queue-entry file's status, not a SQLite row's.

### Tests
- `scripts/tests/test_session_store_schema.py` — existing `harness_events` migration coverage: `test_harness_events_columns` (1573), `test_harness_events_indexes_exist` (1604), `test_v30_db_upgrades_gains_harness_events` (1621), `test_harness_is_kinded` (1635), `test_harness_events_excluded_from_rebuild_tables` (1639), `test_harness_events_has_content_pin_columns` (1972) — the schema migration this issue adds should follow this file's existing coverage shape.
- `scripts/tests/test_session_store_writers.py` — `record_harness_event()` INSERT tests (2080-2177).
- `scripts/tests/test_history_reader_harness.py` — `harness_eval_pass_rate`/`harness_eval_abstention_rate` coverage, built via direct `record_harness_event(db, ...)` calls, no ORM/factory layer (e.g. `test_harness_eval_pass_rate` line 51).
- `scripts/tests/test_cli_harness.py` — `cmd_dsl`/`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt` coverage, including DSL aggregate-row tests (`test_cmd_dsl_task_row_records_host_exit_code_and_verdict` 1487, `test_cmd_dsl_aggregate_row_carries_run_outcome` 1511) that already exercise the `_update_aggregate()` UPDATE path noted above.

### Documentation
- `docs/guides/EVALUATION_GUIDE.md:308,446` — documents `harness_events`/`recent_harness_events`/`harness_eval_pass_rate` and notes today that "nothing reads `harness_events` from the CLI" for pass-rate purposes beyond display — this line becomes stale once the run-model/admissions reporting lands.
- `docs/reference/API.md` — `recent_harness_events`/`harness_eval_pass_rate`/`record_harness_event` reference entries will need new parameters documented.
- `CHANGELOG.md:1249-1251` — prior `harness_events` work (ENH-2739/2740/2741) for context on the table's history.

## Program Design

### Types

- `harness_events.cell_key: str` — `(target, task, subject)` identity
- `harness_events.repetition: int` — stamped repetition index for the cell
- `harness_events.attempt_kind: Literal["repetition", "infra_retry"]`
- `harness_events.continuations: int | None` — nullable in-run retry counter
- `harness_events.superseded_by: int | None` — nullable attempt id
- `harness_admissions` row: `attempt_id: int`, `superseded_id: int`, `reason: Literal["timeout", "host_crash", "harness_error", "network"]`, `ts: datetime`

### Signatures

- `record_attempt(cell_key: str, repetition: int, attempt_kind: AttemptKind, retry_of: int | None = None) -> int`
- `admit_retry(attempt_id: int, superseded_id: int, reason: AdmissionReason) -> None`
- `authoritative_attempt(cell_key: str) -> AttemptRow`

### Call Path

`harness_eval_pass_rate` -> `authoritative_attempt(cell_key)` -> `record_attempt` / `admit_retry` write `harness_events` / `harness_admissions`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

### Decision Rules

- **`--retry-of` admissibility gate**: admissible only when the superseded attempt's `exit_code == 2` (the timeout/runner-error branch inside `_evaluate_and_report`, `scripts/little_loops/cli/harness.py:659,668-671`) — any other exit code (0 pass, 1 fail, 3 abstain) is a graded outcome and refuses the retry, non-zero exit, message names the attempt id. Escape hatch: none — a wrong-but-graded verdict is out of scope for this issue (belongs to separate grading-determinism work).
- **Authoritative-attempt selection**: for a `cell_key`, the earliest attempt where `superseded_by IS NULL` is authoritative; no CLI flag may override this. Non-destructive — losing attempts remain in `harness_events`, they are simply excluded from n and from the reported verdict.
- **Cell identity**: `cell_key = (target, task, subject)` where `subject = runner_label + head_sha`; `repetition` is a stamped index per cell, reused (not incremented) by an `infra_retry`.
- **Admission reason enum**: `timeout | host_crash | harness_error | network` — no free-text reason accepted; no existing session_store writer validates an enum at the INSERT boundary today (see Integration Map → Conventions in Force), so this is the first case of that validation existing in this codebase, if enforced at write time rather than only in the type annotation.

## Scope Boundaries

- **In scope**: `harness_events` schema migration, the `repetition`/`infra_retry` distinction, the `--retry-of` gate and its refusal rule, the `harness_admissions` audit table, authoritative-attempt selection, and updating `history_pass_rate_runs`/DSL `graded_total` to count repetitions.
- **Out of scope**: any default or minimum n (deferred to the n-run-redundancy work), re-grading a wrong-but-graded verdict caused by a harness bug (separate grading-determinism work), and continuations as first-class rows (recorded only as a nullable counter).

## Acceptance Criteria

- `harness_events` gains `cell_key`, `repetition`, `attempt_kind` (`repetition` | `infra_retry`), `continuations` (nullable int) and `superseded_by` (nullable attempt id). Schema migration, live-write-only like the rest of the table.
- A fresh invocation records `attempt_kind = repetition` with the next free repetition index for its cell. `--retry-of <id>` records `infra_retry`, sets `superseded_by` on the prior row, and reuses its repetition index.
- `--retry-of` is refused (non-zero exit, message names the attempt) when the prior attempt reached grading — any exit other than the timeout / runner-error path. Test: a retry of a graded FAIL is rejected; a retry of a timeout is accepted.
- Every admission is appended to a new `harness_admissions` table: attempt id, superseded id, typed reason (`timeout` | `host_crash` | `harness_error` | `network`), ts. Rows are never updated or deleted; a test asserts the writer has no UPDATE/DELETE path.
- For a cell with several attempts, the earliest attempt that is not superseded is authoritative. No flag selects a different one. Test: two valid repetitions of one cell contribute n=2; one graded attempt plus two infra retries contribute n=1 with the earliest graded attempt's verdict.
- `history_pass_rate_runs` and the DSL `graded_total` count authoritative repetitions, not rows. Test: the same fixture produces a lower n after a retry chain than before this change.
- The run report tabulates admissions (count, by reason) next to the pass rate whenever the table is non-empty for the run, so an operator intervention that changed a score is visible.
- No default n and no minimum n are introduced; those belong to the n-run-redundancy work that builds on this run model.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

1. `harness_events` gains `cell_key`, `repetition`, `attempt_kind`, `continuations`, `superseded_by` via an additive migration in `scripts/little_loops/session_store/schema.py`'s `_MIGRATIONS` list, following the existing "Fix-forward only" comment convention (see `schema.py:931,947-948,973`); verified by `python -m pytest scripts/tests/test_session_store_schema.py -v`.
2. A new `harness_admissions` table is added the same way, matching the INSERT-only shape of `hook_events`/`test_run_events`/`commit_events` in `scripts/little_loops/session_store/writers.py` rather than the UPSERT shape of `correction_retirements`; a new test establishes that the writer has no UPDATE/DELETE path for this table, since no existing test in this codebase does this against a SQLite table.
3. `record_attempt()`/`admit_retry()`/`authoritative_attempt()` are added to `scripts/little_loops/session_store/writers.py` alongside the existing `record_harness_event()` (line 1024); `--retry-of`'s admissibility gate reads the superseded attempt's `exit_code` from the row `_evaluate_and_report()` (`cli/harness.py:659`) already produces.
4. `history_pass_rate_runs` (the dict key computed inline in `_read_target_history()`, `cli/harness.py:588,623`) and the DSL's `graded_total`/`graded_pass` local variables (`cli/harness.py:992` onward) are updated to count authoritative repetitions per the new selection rule, not raw rows; verified by a fixture producing a lower n after a retry chain than before, per the Acceptance Criteria.
5. `harness_eval_pass_rate()`/`harness_eval_abstention_rate()` (`scripts/little_loops/history_reader/harness.py:113,152`) apply the same authoritative-attempt filter; verified by `python -m pytest scripts/tests/test_history_reader_harness.py -v`.
6. The run report gains an admissions tabulation (count, by reason) rendered whenever `harness_admissions` is non-empty for the run — no existing render call path was found for this; place it alongside wherever `_read_target_history()`'s existing history summary is already printed in `cli/harness.py`.

## Impact

- **Priority**: P1 - every pass-rate the harness reports today is over an undefined denominator; this is the anti-p-hacking gate the harness has no substitute for.
- **Effort**: Medium - a schema migration plus a new append-only table and gating logic in one existing code path (`_evaluate_and_report`), no new subsystem.
- **Risk**: Medium - `history_pass_rate_runs` and DSL `graded_total` change what they count, which can shift previously reported n for historical runs re-read under the new definition.
- **Breaking Change**: No - live-write-only schema migration; existing rows are additive, not rewritten.

## Status

**Open** | Created: 2026-09-07 | Priority: P1


## Session Log
- `/ll:format-issue` - 2026-09-08T00:09:20 - `fd8050c6-8bbf-4735-ba8f-b83f5f588867.jsonl`
