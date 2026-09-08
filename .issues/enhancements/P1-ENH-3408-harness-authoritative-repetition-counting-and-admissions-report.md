---
id: ENH-3408
title: Count authoritative repetitions in harness pass-rate reporting + admissions tabulation
type: ENH
priority: P1
status: open
discovered_date: '2026-09-08'
parent: ENH-3397
blocked_by:
- ENH-3407
labels:
- harness
- evaluation
- statistics
---

# ENH-3408: Count authoritative repetitions in harness pass-rate reporting + admissions tabulation

## Summary

Make ll-harness's pass-rate/abstention-rate reporting count authoritative repetitions
instead of raw attempt rows, and surface admission interventions in the run report. Third
of three issues decomposed from ENH-3397 — depends on the writers/gate from ENH-3407.
This is the issue that actually changes what `n` means in reported numbers — the
anti-p-hacking guarantee ENH-3397 exists to deliver doesn't hold until this issue lands,
even though ENH-3406/ENH-3407 build its plumbing.

## Parent Issue

Decomposed from ENH-3397.

## Design Decisions (inherited from parent + codebase research)

- **Hard blocker, do first**: add `cell_key`/`repetition`/`attempt_kind`/`continuations`/
  `superseded_by` to the `HarnessEvent` dataclass and `_HARNESS_EVENT_COLUMNS` SQL fragment
  in `history_reader/harness.py` before/alongside the counting-logic change.
  `_row_to_dataclass()` (`history_reader/_base.py`) silently drops any DB column not
  present as a `HarnessEvent` field — skipping this step makes the counting change
  silently return stale data instead of failing loudly.
- A third row-counting site exists beyond the two named functions: `_read_target_history()`
  (`cli/harness.py:588-640`) computes its own `pass_scored`/`judged_scored` local counts
  independently of `harness_eval_pass_rate()`/`harness_eval_abstention_rate()`'s SQL
  `COUNT()` queries, gated by `_HISTORY_MIN_SCORED = 3` (line 585). All three sites must be
  converted together, or the threshold gate stays keyed to attempt-row counts (e.g. one
  graded attempt + two `infra_retry` rows would still clear the threshold at
  `pass_scored == 3` backed by one real data point).
- Timeout/error rows already store `semantic_passed=False` (not `NULL`), so they're
  already counted in `harness_eval_pass_rate()`'s denominator but excluded from
  `harness_eval_abstention_rate()`'s — account for this discrepancy when defining what an
  authoritative-but-superseded attempt's `semantic_passed` means.

## Files to Modify

- `scripts/little_loops/history_reader/harness.py` — `HarnessEvent` dataclass +
  `_HARNESS_EVENT_COLUMNS` additions (do first); `harness_eval_pass_rate()` (113) and
  `harness_eval_abstention_rate()` (152) apply the authoritative-attempt filter (via
  `authoritative_attempt()` from ENH-3407).
- `scripts/little_loops/history_reader/__init__.py:184-186,308-309,329` — re-exports if
  signatures change.
- `scripts/little_loops/cli/harness.py:588,623` — `_read_target_history()`'s
  `history_pass_rate_runs` / `pass_scored` / `judged_scored` and the
  `_HISTORY_MIN_SCORED` gate count authoritative repetitions, not raw rows.
- `scripts/little_loops/cli/harness.py:992` onward, `1146` — `cmd_dsl`'s `graded_total`/
  `graded_pass` local variables count authoritative repetitions; insert the admissions
  tabulation (count, by reason) after the existing
  `f"\nDSL pass-rate: {graded_pass}/{graded_total} ..."` line.
- `docs/reference/CLI.md:212-313` — update the `--output json` payload-fields table's
  `history_pass_rate_runs` description (260-266) and exit-code table for the redefinition.
- `docs/guides/EVALUATION_GUIDE.md:308,446` — update the "nothing reads `harness_events`
  from the CLI for pass-rate purposes" line, now stale.
- `docs/reference/API.md` — document new parameters on `recent_harness_events`/
  `harness_eval_pass_rate`-adjacent functions.

## Tests

- `scripts/tests/test_history_reader_harness.py::TestHarnessEventReaders` — update
  `test_harness_eval_pass_rate` (51), `test_harness_eval_pass_rate_excludes_abstained_rows`
  (74), `test_harness_eval_abstention_rate` (97),
  `test_harness_eval_abstention_rate_does_not_match_unrelated_verdict` (121) for the new
  counting rule.
- `scripts/tests/test_cli_harness.py::TestReadTargetHistory` — update
  `test_at_threshold_renders` (1738), `test_distinct_denominators_for_pass_and_abstention`
  (1761, hand-counts `history_pass_rate_runs == 6` in a comment tied to raw row count),
  `test_window_excludes_old_rows` (1798).
- `scripts/tests/test_cli_harness.py:1832`
  `TestTargetHistoryRegression::test_current_run_excluded_from_reported_rate` — update the
  `history_judged_runs == 3` assertion.
- New fixture-based test: two valid repetitions of one cell contribute n=2; one graded
  attempt plus two infra retries contribute n=1 with the earliest graded attempt's
  verdict (the same fixture produces a lower n after a retry chain than before this
  change).
- New test asserting the run report renders an admissions tabulation (count, by reason)
  whenever `harness_admissions` is non-empty for the run.

## Acceptance Criteria

- `history_pass_rate_runs` and the DSL `graded_total` count authoritative repetitions, not
  rows. Test: the same fixture produces a lower n after a retry chain than before this
  change.
- For a cell with several attempts, the earliest non-superseded attempt is authoritative
  and determines the reported verdict. Test: two valid repetitions of one cell contribute
  n=2; one graded attempt plus two infra retries contribute n=1 with the earliest graded
  attempt's verdict.
- The run report tabulates admissions (count, by reason) next to the pass rate whenever
  the table is non-empty for the run.
- No default n and no minimum n are introduced.

## Scope Boundaries

- **In scope**: `HarnessEvent` dataclass/`_HARNESS_EVENT_COLUMNS` fields,
  `harness_eval_pass_rate`/`harness_eval_abstention_rate`/`_read_target_history`/DSL
  counting logic, admissions tabulation in the run report, updating the existing
  row-count-as-n tests, `EVALUATION_GUIDE.md`/`API.md`/`CLI.md` doc updates for the
  redefinition.
- **Out of scope**: `harness_events`/`harness_admissions` schema DDL (ENH-3406);
  `record_attempt`/`admit_retry`/`authoritative_attempt`/`--retry-of` implementation
  (ENH-3407) — this issue only consumes `authoritative_attempt()`, it does not define it.
  Any default or minimum n (deferred to the n-run-redundancy follow-on work).

## Impact

- **Priority**: P1 — this issue is what actually makes previously-reported n sound;
  without it the schema/writer work from ENH-3406/ENH-3407 has no observable effect on
  reported numbers.
- **Effort**: Medium — three counting sites converge on one selection function, plus a new
  report section and five existing test files to update.
- **Risk**: Medium — `history_pass_rate_runs` and DSL `graded_total` change what they
  count, which can shift previously reported n for historical runs re-read under the new
  definition.
- **Breaking Change**: No — live-write-only; existing rows are additive, not rewritten.

## Status

**Open** | Created: 2026-09-08 | Priority: P1 | Blocked by: ENH-3407


## Session Log
- `/ll:issue-size-review` - 2026-09-08T05:34:24 - `5401886d-ebfd-404a-b6ba-9a7d5e921ddb.jsonl`
