---
id: ENH-3407
title: record_attempt/admit_retry/authoritative_attempt writers + --retry-of CLI gate
type: ENH
priority: P1
status: open
discovered_date: '2026-09-08'
parent: ENH-3397
blocked_by:
- ENH-3406
labels:
- harness
- evaluation
- statistics
---

# ENH-3407: record_attempt/admit_retry/authoritative_attempt writers + --retry-of CLI gate

## Summary

Implement the write path for ll-harness's run model: `record_attempt()`/
`admit_retry()`/`authoritative_attempt()` in `session_store/writers.py`, and thread a new
`--retry-of` CLI flag through ll-harness's evaluators (`cmd_skill`/`cmd_cmd`/`cmd_mcp`/
`cmd_prompt`/`cmd_dsl`) with the admissibility gate and refusal behavior. Second of three
issues decomposed from ENH-3397 — depends on the schema/table from ENH-3406. This issue's
`--retry-of` flag is fully functional and records correct data, but existing pass-rate
calculations do not yet reflect it (that's ENH-3408).

## Parent Issue

Decomposed from ENH-3397.

## Design Decisions (inherited from parent + codebase research)

- **`--retry-of` admissibility gate**: per the parent issue, admissible only when the
  superseded attempt's `exit_code == 2` (the timeout/runner-error branch inside
  `_evaluate_and_report`, `cli/harness.py:659,668-671`); any other exit code is a graded
  outcome and refuses the retry (non-zero exit, message names the attempt id). No escape
  hatch.

  ⚠ **Known gap, carried from parent's codebase research** — `exit_code` alone does not
  reliably identify this branch: skill-runner timeouts store `exit_code=124`, not `2`
  (`runner_spec.py:195-201`), and an ordinary graded `--exit-code 2` mismatch also stores
  `exit_code=2`. `harness_events` has no column carrying `result.error`/`timed_out`
  today. Resolve this signal gap during implementation (e.g. persist `timed_out`/`error`
  on the row, or a dedicated flag) rather than gating on `exit_code == 2` literally — doing
  so as specified would both reject legitimate timeout retries (124) and admit retries of
  ordinary graded failures (2).
- **Authoritative-attempt selection**: for a `cell_key`, the earliest attempt where
  `superseded_by IS NULL` is authoritative; no CLI flag may override this. Non-destructive
  — losing attempts remain in `harness_events`.
- No existing `session_store` writer validates a `Literal`/enum column at the INSERT
  boundary in Python; this codebase enforces closed-set columns via SQLite `CHECK`
  constraints instead (`verdict_events.verdict`, `research_triage_events.axis` —
  `schema.py:1216-1220,1291-1298`). Prefer a CHECK constraint on `attempt_kind`/`reason`
  over inventing Python-side validation.
- `--retry-of`'s refusal shape should match `cli/queue.py::cmd_requeue`/`cmd_remove` (id
  lookup → persisted-status check → refuse naming id/status, exit 1), not
  `cli/issues/create.py:485-494`'s `--parent` (silent no-op on unresolved reference).

## Files to Modify

- `scripts/little_loops/session_store/writers.py` — add
  `record_attempt(cell_key, repetition, attempt_kind, retry_of=None) -> int`,
  `admit_retry(attempt_id, superseded_id, reason) -> None`,
  `authoritative_attempt(cell_key) -> AttemptRow`, alongside the existing
  `record_harness_event()` (line 1024).
- `scripts/little_loops/session_store/__init__.py:147,234` (+ docstring line 54) — export
  `record_attempt`/`admit_retry`/`authoritative_attempt`, mirroring
  `record_harness_event`.
- `scripts/little_loops/cli/harness.py` — add `--retry-of` flag; thread cell identity +
  `attempt_kind` through `cmd_skill` (835), `cmd_cmd` (868), `cmd_mcp` (911), `cmd_prompt`
  (952), `cmd_dsl` (1072); gate reads the exit signal from the row
  `_evaluate_and_report()` (659) already produces.
- `docs/reference/CLI.md:212-313` — add `--retry-of` to the shared-evaluator-flags table
  (226-234) and document its exit-code/refusal semantics.

## Tests

- `scripts/tests/test_session_store_writers.py` — `record_attempt`/`admit_retry`/
  `authoritative_attempt` unit tests; a test asserting the writers module has no
  UPDATE/DELETE path against `harness_admissions` (source-inspection pattern, adapted from
  `test_git_operations.py:306-320`'s `TestNoGitStash`, since no existing test targets a SQL
  statement kind against a specific table).
- `scripts/tests/test_cli_harness.py` — a retry of a graded FAIL is rejected (non-zero
  exit, message names the attempt); a retry of a timeout is accepted and records
  `infra_retry` with `superseded_by` set and the same repetition index.
- Verify `scripts/tests/test_ll_session.py:1345,1348,1359,1362` and
  `scripts/tests/test_ll_logs.py:4677,4688-4771` (`_parse_harness_args` round-trip,
  `TestEvalExportMapping`/`TestEvalExportRoundTrip`) still pass unmodified after the writer
  signature and CLI-flag changes.

## Acceptance Criteria

- A fresh invocation records `attempt_kind = repetition` with the next free repetition
  index for its cell. `--retry-of <id>` records `infra_retry`, sets `superseded_by` on the
  prior row, and reuses its repetition index.
- `--retry-of` is refused (non-zero exit, message names the attempt) when the prior
  attempt reached grading. Test: a retry of a graded FAIL is rejected; a retry of a timeout
  is accepted.
- Every admission is appended to `harness_admissions`: attempt id, superseded id, typed
  reason, ts. Rows are never updated or deleted; a test asserts the writer has no
  UPDATE/DELETE path.
- For a cell with several attempts, `authoritative_attempt()` returns the earliest attempt
  that is not superseded, with no way to override via flag.

## Scope Boundaries

- **In scope**: `writers.py` functions, `--retry-of` flag + gate + refusal,
  `harness_admissions` writes, exports, `CLI.md` flag docs, resolving the exit-signal
  ambiguity flagged above.
- **Out of scope**: `harness_events`/`harness_admissions` schema DDL (ENH-3406, must land
  first), `history_pass_rate_runs` / DSL `graded_total` / `harness_eval_pass_rate` /
  `harness_eval_abstention_rate` counting logic and the run-report admissions tabulation
  (ENH-3408).

## Impact

- **Priority**: P1.
- **Effort**: Medium — new writer functions plus a CLI flag threaded through 5 call sites
  in one existing code path.
- **Risk**: Medium — the `exit_code` admissibility signal is not reliable as specified in
  the parent issue and needs resolving during implementation (see Design Decisions note
  above).
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-08 | Priority: P1 | Blocked by: ENH-3406


## Session Log
- `/ll:issue-size-review` - 2026-09-08T05:34:24 - `5401886d-ebfd-404a-b6ba-9a7d5e921ddb.jsonl`
