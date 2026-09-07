---
id: 3397
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

## Motivation

Several existing harness capabilities — repeated sampling with verifier selection, stop-on-first-confirmation, eval saturation detection — all assume repeated runs without defining what a run *is*. Nothing separates a resample from a replacement, and nothing forbids an operator from keeping the attempt they like. Every pass-rate the harness reports today is therefore a number over an undefined denominator.

The score-reproducible-not-byte-reproducible stance already adopted elsewhere in the harness is what makes the earliest-valid rule tolerable in practice: attempts are not expected to be identical, only comparable.

## Design decisions

- **Continuations are not attempts.** The subject retrying itself inside one run is invisible to the harness by construction; record it as a nullable counter on the attempt, never as a row. The harness-level enum is therefore two-way: `repetition` | `infra_retry`.
- **Infra retry is a mechanical gate, not a free-text reason.** A retry is admissible only when the superseded attempt ended on the error path (timeout or runner error — the exit-2 branch of `_evaluate_and_report`). A graded attempt can never be retried under this issue; a wrong-but-graded verdict caused by a harness bug belongs to the separate work on deterministically unit-testing grading logic, not to an admission path.
- **Cell identity is explicit.** Cell = (target, task, subject), subject = runner label + head sha; repetition index is a stamped column.
- **No threshold.** This issue defines what n counts; how large n must be is decided by the follow-on n-run-redundancy work.

## Acceptance Criteria

- `harness_events` gains `cell_key`, `repetition`, `attempt_kind` (`repetition` | `infra_retry`), `continuations` (nullable int) and `superseded_by` (nullable attempt id). Schema migration, live-write-only like the rest of the table.
- A fresh invocation records `attempt_kind = repetition` with the next free repetition index for its cell. `--retry-of <id>` records `infra_retry`, sets `superseded_by` on the prior row, and reuses its repetition index.
- `--retry-of` is refused (non-zero exit, message names the attempt) when the prior attempt reached grading — any exit other than the timeout / runner-error path. Test: a retry of a graded FAIL is rejected; a retry of a timeout is accepted.
- Every admission is appended to a new `harness_admissions` table: attempt id, superseded id, typed reason (`timeout` | `host_crash` | `harness_error` | `network`), ts. Rows are never updated or deleted; a test asserts the writer has no UPDATE/DELETE path.
- For a cell with several attempts, the earliest attempt that is not superseded is authoritative. No flag selects a different one. Test: two valid repetitions of one cell contribute n=2; one graded attempt plus two infra retries contribute n=1 with the earliest graded attempt's verdict.
- `history_pass_rate_runs` and the DSL `graded_total` count authoritative repetitions, not rows. Test: the same fixture produces a lower n after a retry chain than before this change.
- The run report tabulates admissions (count, by reason) next to the pass rate whenever the table is non-empty for the run, so an operator intervention that changed a score is visible.
- No default n and no minimum n are introduced; those belong to the n-run-redundancy work that builds on this run model.
