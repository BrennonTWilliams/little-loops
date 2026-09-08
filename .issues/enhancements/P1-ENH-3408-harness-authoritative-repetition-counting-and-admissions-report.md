---
id: ENH-3408
title: Count authoritative repetitions in harness pass-rate reporting + admissions
  tabulation
type: ENH
priority: P1
status: open
discovered_date: '2026-09-08'
verify_verdict: NON_VALID
parent: ENH-3397
blocked_by:
- ENH-3407
labels:
- harness
- evaluation
- statistics
size: Large
confidence_score: 80
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
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
  `_HARNESS_EVENT_COLUMNS` additions (`id` + the five v49 fields) are **provided by
  ENH-3407** (landed) — no longer this issue's own first step; `harness_eval_pass_rate()`
  (113) and `harness_eval_abstention_rate()` (152) apply the authoritative-attempt filter by
  consuming `authoritative_attempts(cell_key)` / `authoritative_attempt(cell_key,
  repetition)`, both also provided by ENH-3407.
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

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — the `HarnessEvent` code block (~lines 8918-8936) is already
  stale independent of this issue: it's missing `target_content_hash`/`target_path`/`dirty`
  fields that a prior change (ENH-141) added to the live dataclass. When adding
  `cell_key`/`repetition`/`attempt_kind`/`continuations`/`superseded_by`, backfill the full
  current field list rather than appending only the five new fields onto the already-
  incomplete block. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- `scripts/little_loops/history_reader/__init__.py` — re-export block confirmed at exact
  lines: `HarnessEvent`, `HighConfidenceAbstention`, `check_high_confidence_abstention` at
  lines 63/182/183; `harness_eval_abstention_rate`, `harness_eval_pass_rate`,
  `recent_harness_events` at lines 184-186; docstring block describing the same functions at
  lines 121-124; `__all__` entries at lines 271, 296, 308-309, 329.
- `scripts/little_loops/session_store/writers.py` — `record_harness_event()` (line 1024):
  its `INSERT` column list is hardcoded (no `**kwargs` passthrough), confirming the
  ENH-3406 columns aren't written yet and this writer itself is ENH-3407's (not this
  issue's) surface — listed here only so an implementer knows not to touch it directly.
- `scripts/little_loops/session_store/schema.py` — confirmed 0 hits for `harness_admissions`
  (table not yet created; current `SCHEMA_VERSION = 48`). The `credential_scope_events`
  kinded-table precedent (`_KIND_TABLE` entry line 82, `CREATE TABLE` line 1319, index
  lines 1327-1328) is the shape ENH-3406 is meant to mirror for `harness_admissions` — cited
  as context for what this issue will read from once ENH-3406/3407 land, not as work item
  for this issue.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- Existing fixture convention (both target test files build rows via direct, repeated calls
  to the real `record_harness_event()` writer with explicit kwargs — no row-dataclass
  literal construction, no mock DB layer):
  - `test_history_reader_harness.py::TestHarnessEventReaders` — one `record_harness_event()`
    call per row, e.g. `for semantic_passed in (True, True, False): record_harness_event(db,
    ts=..., target="foo", semantic_passed=semantic_passed)`.
  - `test_cli_harness.py::TestReadTargetHistory` — wraps the same writer in a class-local
    `_seed(self, target: str, rows: list[dict])` helper taking a list of kwarg-dicts
    (`**row`); this is the helper a `cell_key`/`repetition`/`attempt_kind` fixture should
    extend rather than inventing a new fixture shape. `test_distinct_denominators_for_pass_and_abstention`'s
    inline hand-count comment (`# 3 non-abstained judged + 3 exit-only`) is the existing
    convention for documenting an expected `n` next to the assertion — matches what this
    issue's own Tests section says needs updating (`history_pass_rate_runs == 6` tied to raw
    row count).
- `scripts/tests/test_session_store_writers.py::TestRecordHarnessEvent` (line 2205) —
  nearest existing coverage for the writer this issue's read-path counting logic consumes
  output from; not itself in scope for this issue (ENH-3407's writer), but the precedent for
  how `record_harness_event()` kwargs are exercised in tests.
- `scripts/tests/test_session_store_schema.py::TestSchemaV47CredentialScopeEvents` (line
  2753) — the precedent test-class shape ENH-3406 (this issue's blocker) is meant to mirror
  for a `harness_admissions`-equivalent schema test; no such class exists yet (0 hits for
  `harness_admissions` in this file). Cited for context only — schema DDL tests are
  ENH-3406's scope, not this issue's.

### Wiring Findings

_Wiring pass added by `/ll:wire-issue`:_
- No test file beyond those already listed above needs updating. Confirmed codebase-wide:
  every fixture in `TestCmdDsl` (`test_cli_harness.py:1070-1605`) and
  `TestHarnessEventPersistence::test_dsl_batch_writes_aggregate_and_per_task_rows` (line
  1674) uses one attempt per distinct task file — no retry-chain/repeated-`cell_key`
  fixture exists — so none silently break under the new counting rule.
  `TestReadTargetHistory::test_below_threshold_returns_none` (1723) and
  `test_none_when_db_empty` (1818) likewise seed only distinct single-attempt rows and are
  unaffected. [Agent 1 + 3 findings]
- Pattern for the new admissions-tabulation test (Acceptance Criteria #3): no existing
  "count-by-category, non-empty-gated" renderer in this codebase (`ctx_stats.py`'s
  `crossings`, `sprint/show.py`'s `_print_composition`, `logs.py`'s `outcome_counts`) is
  tested via a full rendered-string assertion — each is tested either at the
  data-aggregation layer (dict equality, e.g. `test_cli_ctx_stats.py::test_aggregates_peak_avg_and_crossings`)
  or via a coarse literal-prefix substring check (`test_sprint.py::test_show_composition_line`
  asserts `"Composition:" in captured.out`, not the breakdown text that follows). Follow
  that same substring-assertion convention — consistent with `TestCmdDsl`'s own existing
  style (e.g. `assert "pass-rate" in out`) — rather than asserting an exact rendered line.
  [Agent 3 finding]

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

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

Findings below, organized by Types, Signatures, Call Path, and Decision Rules.

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- Confirmed no fourth attempt-counting/aggregation site exists over `harness_events` beyond the three already named (`harness_eval_pass_rate`, `harness_eval_abstention_rate`, `_read_target_history`). A repo-wide search for callers of those three symbols plus a scan for other `harness_events` readers found only: the writer (`session_store/writers.py::record_harness_event`, ENH-3407's surface), schema DDL/migrations (`session_store/schema.py`, ENH-3406's surface), and a raw-row export path — `session_store/queries.py`'s `_EXPORT_TABLE_MAP["harness_event"]`, consumed by `ll-artifact dashboard` (`cli/artifact/dashboard.py`) for a browser-side sql.js snapshot. That export echoes raw rows, not an aggregated rate, so it does not need conversion under this issue; it will surface the new `cell_key`/`repetition`/`attempt_kind`/`superseded_by` columns once ENH-3406 adds them, subject to the existing shareable-column allowlist (which does not currently include `harness_event` under shareable mode's default table selection). Noted for awareness — not an integration point this issue must touch.
- `_evaluate_and_report()` (`cli/harness.py:726`) has no caching across calls — each `_read_target_history()` call opens a fresh read-only connection. Call sites confirmed at lines 835/868/911/952 (once each, for `cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt`) and 1072 (the `cmd_dsl` per-task loop, `skip_history=True`, so history is never read there). No multi-call-per-run or ordering hazard beyond what the existing Call Path already documents.

### Types

No new data shape is introduced by this issue — `cell_key`/`repetition`/`attempt_kind`/
`continuations`/`superseded_by` are `HarnessEvent` fields owned by ENH-3406 (schema) and
populated by ENH-3407 (writers); this issue only reads them once present. Confirmed absent
today from both `HarnessEvent` (`history_reader/harness.py`, dataclass fields: `ts`,
`runner`, `target`, `exit_code`, `semantic_verdict`, `semantic_passed`, `timed_out`,
`duration_ms`, `head_sha`, `branch`, `parent_id`, `semantic_prompt`, `semantic_confidence`,
`semantic_reason`, `semantic_evidence`, `semantic_model`, `target_content_hash`,
`target_path`, `dirty`) and from the live `harness_events` DDL (`session_store/schema.py`,
`SCHEMA_VERSION = 48`).

### Signatures

Current signatures this issue's counting-logic change touches (no new public signature is
proposed; each of the three counting sites narrows its existing filter, consuming
`authoritative_attempt()` from ENH-3407 once it exists):
- `harness_eval_pass_rate(target, since=None, db=None) -> float | None` — `history_reader/harness.py:113`. Denominator today is raw `COUNT(semantic_passed)` (non-NULL `semantic_passed`, including `False` timeout/error rows).
- `harness_eval_abstention_rate(target, since=None, db=None) -> float | None` — `history_reader/harness.py:152`. Denominator today is raw `COUNT(semantic_verdict)` (non-NULL `semantic_verdict`) — a deliberately different column from the pass-rate denominator, per the function's own docstring.
- `_read_target_history(target: str) -> dict | None` — `cli/harness.py:588`. Independently re-derives `pass_scored`/`judged_scored` in Python from `recent_harness_events(target=target, since=since, limit=1000, db=db_path)` rather than reusing the SQL functions' internal counts — its own comment states why: "return only a rate, not the row count behind it — pull the events once to derive both denominators." `limit=1000` means this path can under-count relative to true SQL `COUNT()` for a target with more than 1000 events in the `since` window; the two paths are not guaranteed identical in that edge case even under the current (pre-ENH-3408) row-counting rule.
- `_row_to_dataclass(row: sqlite3.Row, dc: type[Any]) -> Any` — `history_reader/_base.py:87`. Builds `field_names` from the target dataclass, filters `row.keys()` to that set — a DB column present in the row but absent from the dataclass is simply omitted from `kwargs`, no error/warning. Confirms the issue's "silently drops" claim exactly; this is why the `HarnessEvent` field additions are a hard blocker to do first.

### Call Path

`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt`/`cmd_dsl`'s per-task loop -> `_evaluate_and_report()` (`cli/harness.py:726` calls `_read_target_history()` *before* the current run's own write, so history figures exclude the current run) -> `_read_target_history()` -> `recent_harness_events()` -> conditionally, if the Python-computed `pass_scored`/`judged_scored` clears `_HISTORY_MIN_SCORED = 3` (`cli/harness.py:585`) -> `harness_eval_pass_rate()` / `harness_eval_abstention_rate()` (each its own separate SQL aggregate query over the same raw rows) -> `_format_target_history_line()`.

Separately: `cmd_dsl()` (`cli/harness.py`) accumulates `graded_pass`/`graded_total`/`ungraded_count`/`abstain_count`/`errored_count`/`failures` purely from its own per-task loop's in-memory outcomes — it never re-reads `harness_events` for its own report. Counters initialize around line 991-992; the report line `f"\nDSL pass-rate: {graded_pass}/{graded_total}  [{lo:.2f}, {hi:.2f}] (95% CI)"` is the first element of a `lines` list (conditionally followed by an "ungradable" sub-line and a "failed:" sub-line), printed once via `print("\n".join(lines))`. The admissions tabulation's natural insertion point is one more conditional append onto that same `lines` list, following the existing non-empty-gated append convention (`if ungraded_count: lines.append(...)`, `if failures: lines.append(...)`) — both `_update_aggregate()`'s call and the `print()` call remain after this insertion point, since `_update_aggregate()` needs the already-in-scope `failures`/`ungraded_count`/`abstain_count`/`errored_count` regardless.

Timeout/error-row denominator asymmetry, confirmed exactly as the issue's Design Decisions
section claims: every non-abstained-run path (`_evaluate_and_report()`'s timeout/error
early returns, `HarnessEvalOutcome.abstained` defaults to `False`) writes
`semantic_passed = None if outcome.abstained else outcome.passed`, so a timeout/error row
gets `semantic_passed = 0` (counted in pass-rate's denominator) but `semantic_verdict = NULL`
(excluded from abstention-rate's denominator). A real `cannot_judge` abstain is the mirror
case: `semantic_passed = NULL` (excluded from pass-rate's denominator) but
`semantic_verdict` non-NULL (included in abstention-rate's denominator) — the two
denominators diverge in opposite directions depending on which kind of non-graded row it is.

### Decision Rules

N/A — no new decision logic. This issue narrows an existing filter (which attempt rows
count) by consuming `authoritative_attempt()`'s selection rule, which ENH-3407 defines; it
does not introduce a new gap kind, gate, threshold, or keyword list of its own.

## Current Behavior

`harness_eval_pass_rate()`, `harness_eval_abstention_rate()`, and
`_read_target_history()` all count raw `harness_events` rows. A cell retried after an
infra timeout contributes one row per attempt to the reported `n`, so an infra retry
inflates the sample size instead of replacing the attempt it superseded — the same
issue for `cmd_dsl`'s `graded_total`. The run report has no visibility into admission
interventions at all.

## Expected Behavior

The three counting sites (plus `cmd_dsl`'s `graded_total`) count authoritative
repetitions per cell via `authoritative_attempt()` (ENH-3407) instead of raw rows: a
cell with a graded attempt plus two infra retries contributes `n=1`, not `n=3`, using
the earliest graded attempt's verdict. The run report additionally tabulates admissions
(count, by reason) whenever `harness_admissions` is non-empty for the run. This is the
issue that makes ENH-3397's anti-p-hacking guarantee actually hold in reported numbers.

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


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 75/100 → MODERATE

### Gaps to Address
- Blocking dependency ENH-3407 (status: open, not done/cancelled) is unresolved. This issue
  consumes `authoritative_attempt()` from ENH-3407 directly — implementation cannot proceed
  until ENH-3407 lands. Wait for ENH-3407 to reach `done`/`cancelled`, or remove the
  `blocked_by` entry if it no longer applies.

## Session Log
- `/ll:confidence-check` - 2026-09-08T19:15:36 - `3dfd0114-2334-4e08-9e14-e44fec8303b9.jsonl`
- `/ll:format-issue` - 2026-09-08T18:36:35 - `204483fb-0035-4a22-9571-7e0656ebef10.jsonl`
- `/ll:verify-issues` - 2026-09-08T17:09:42 - `3b8d2d10-26d6-4407-8c50-28fe3b34bf14.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-08T17:05:29 - `bd30e086-08dc-4823-aa37-f5118816aece.jsonl`
- `/ll:verify-issues` - 2026-09-08T16:57:01 - `ca004fd7-16f8-4917-8714-ea9456f5383b.jsonl`
- `/ll:wire-issue` - 2026-09-08T16:52:50 - `840e5cd3-969c-4a9b-8f06-5c2b03b57a03.jsonl`
- `/ll:refine-issue` - 2026-09-08T16:41:46 - `32a13f82-52a5-4a4d-99b8-67b2074972cb.jsonl`
- `/ll:issue-size-review` - 2026-09-08T05:34:24 - `5401886d-ebfd-404a-b6ba-9a7d5e921ddb.jsonl`

## Design Decisions

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **No shared "render breakdown dict as string" helper exists in `cli/`** — each existing
  count-by-category report line is bespoke. Three precedents share the same non-empty-gated
  shape ("tabulate count-by-category, print only when non-empty") but differ in join/format
  convention: `ctx_stats.py`'s `crossings` (`defaultdict(int)`, `"level%×count"`
  comma-joined, gated behind `if pressure["crossings"]:`), `sprint/show.py`'s
  `_print_composition()` (`Counter`, `"N type"` pipe-joined groups), and `logs.py`'s
  `_cmd_loop_fleet` `outcome_counts` (`Counter`, `"key:count"` comma-joined inside a
  markdown table cell). The admissions tabulation should follow this same non-empty-gate
  shape but has no existing helper to call — it will be one more bespoke renderer, matching
  `cmd_dsl`'s own existing convention of conditionally appending onto its `lines` list
  (`if ungraded_count: lines.append(...)`, `if failures: lines.append(...)`).
- **No existing "N by reason" breakdown keyed off a typed/CHECK-constrained `reason`
  column** exists anywhere in the codebase today — `harness_admissions.reason` (ENH-3406)
  would be the first. The closest precedent (`ctx_stats.py`'s `crossings` by
  `crossed_level`) breaks down by a different kind of category column.
- **Shared filter-predicate precedent**: `history_reader/usage.py`'s
  `_WASTED_RUN_PREDICATE` (module-level SQL-fragment string, line ~310) is interpolated
  into two different `CASE WHEN`/`COUNT(DISTINCT CASE WHEN...)` clauses within one query
  (`waste_attribution()`), with a comment in `schema.py` cross-referencing it by dotted
  name from a migration. This is the one existing example in this codebase of a
  single-source-of-truth SQL filter fragment reused across multiple aggregate expressions
  in the same query — relevant precedent for keeping the pass-rate/abstention-rate/DSL
  counting sites' "authoritative attempt" filter from drifting once `authoritative_attempt()`
  exists, though `CANNOT_JUDGE`/`is_abstention_verdict()` (`fsm/verdicts.py`, re-exported via
  `history_reader/_base.py`) shows the codebase's alternative pattern: a shared Python-level
  constant with independently-duplicated SQL vs. Python predicate logic per call site,
  which is what `harness_eval_abstention_rate()` already does today for `CANNOT_JUDGE`.
- **No existing "pick one/authoritative row per group" Python helper** exists in
  `history_reader/` or `session_store/` — the only precedent for "pick a survivor row per
  group" is one-off SQL embedded directly in `schema.py` `_MIGRATIONS` DDL entries
  (`ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` at the v36 migration,
  `MIN(rowid)`/`MIN(id)` at the v43 migration) — both are one-shot dedup passes against
  existing data at migration time, not a reusable per-query read-path filter function. This
  means `authoritative_attempt()` (ENH-3407) has no existing Python helper shape to align
  with in this codebase; it is establishing a new pattern, not following one.

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- A landed precedent exists for exactly this class of change — "redefine what n means in a reporting denominator, with an exclusion-count disclosure" — at `scripts/little_loops/issue_manager.py` (`AutoManager._log_timing_summary`, ~lines 2089-2104) plus its routing arm (~lines 2259-2266), landed as BUG-3252 Parts 3/4 (`status: done`; companion route-survey issue BUG-3253 was cancelled/superseded into it). It narrows `Auto-corrections: N/total` by moving confidence-gate skips out of the denominator into a separate bucket, then discloses the exclusion inline: `f"Auto-corrections: {total_corrected}/{total_issues} ({correction_rate:.1f}%){gated_suffix}"` where `gated_suffix = f" ({gated_count} gated before Phase 1)" if gated_count else ""`. Its governing rule is numerator/denominator symmetry — anything excluded from the denominator must also be excluded from the numerator, or the rate can exceed 100% or divide by zero with a nonzero numerator. Its test (`test_issue_manager.py::test_auto_corrections_annotates_gated_exclusion`, line 6233) asserts the exact rendered string via joined `logger.info.call_args_list`, a different assertion shape from `cmd_dsl`'s own `print("\n".join(lines))`/substring-check convention — cited as evidence for the open design questions this issue still has to answer (exclusion-disclosure format, symmetry invariant), not as a shape to copy verbatim into `cmd_dsl`.
- A fourth non-empty-gated count-by-category report convention (beyond the three already catalogued: `ctx_stats.py`'s `crossings`, `sprint/show.py`'s `_print_composition()`, `logs.py`'s `outcome_counts`) exists at `issue_manager.py`'s "Corrections by type:" block (~lines 1848-1867): one `logger.info()` line per category under a header line, sorted count-descending, rather than joining categories into a single string. A fifth, unconditional (not non-empty-gated) variant exists at `cli/issues/clusters.py:134-135`'s `_cluster_header()` (`"P2×1 P3×4"`-style, space-joined, key-sorted). Together these confirm the codebase holds no single shared convention for this rendering shape — five distinct call sites, five different join/format choices — so the admissions tabulation's own format is a genuinely open implementer choice, not one constrained by an existing pattern.
