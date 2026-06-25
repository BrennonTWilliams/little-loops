---
id: BUG-2289
title: "rn-decompose records decomposed parent in both skipped.txt and decomposed_count\
  \ \u2014 summary breakdown double-counts"
priority: P3
type: BUG
status: open
captured_at: '2026-06-25T13:53:17Z'
discovered_date: '2026-06-25'
discovered_by: audit-loop-run
source_loop: rn-implement
source_state: report
affects: scripts/little_loops/loops/rn-decompose.yaml
labels:
- rn-implement
- rn-decompose
- telemetry
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-2289: rn-decompose records decomposed parent in both skipped.txt and decomposed_count — summary breakdown double-counts

## Summary

In the `rn-implement` run `2026-06-25T065113`, `summary.json` reported
`total_processed: 8`, but the outcome buckets sum to **9**:
`implemented: 6 + decomposed: 1 + skipped: 1 + blocked: 1`. The single
decomposed parent (ENH-2272) was tallied in **two** mutually-exclusive
buckets — `decomposed` and `skipped`.

Root cause: when `rn-decompose` decomposes a parent, its `enqueue_children`
state appends the parent ID to `skipped.txt` (`rn-decompose.yaml:209`,
comment "Mark parent as skipped (decomposed)") **and** increments
`decomposed_count.txt` (`rn-decompose.yaml:213`). The `report` state in
`rn-implement` then reads `skipped` from `wc -l skipped.txt` and `decomposed`
from `decomposed_count.txt` as if they were disjoint outcomes
(`rn-implement.yaml:916`), so the decomposed parent is counted once as
`decomposed` and again as `skipped`.

The `skip_issue` state (`rn-implement.yaml:885`, the only *intended* writer to
`skipped.txt`) never executed in this run — verified: 0 routes to `skip_issue`
across all 795 events. The `skipped.txt` entry came entirely from the
`rn-decompose` write.

## Current Behavior

- Run `2026-06-25T065113-rn-implement`, 8 issues dequeued
- `decomposed_count.txt`: `1` (ENH-2272)
- `skipped.txt`: `ENH-2272` (1 entry)
- `subloop_outcome_ENH-2272.txt`: `DECOMPOSED`
- `summary.json`: `total_processed: 8`, buckets sum to 9
- The breakdown over-reports by exactly the number of decomposed parents.

## Expected Behavior

A decomposed parent is counted in exactly one outcome bucket (`decomposed`).
The sum of `implemented + decomposed + skipped + deferred + blocked +
depth_capped + failed` (plus diagnostic tallies) should never exceed
`total_processed`.

## Steps to Reproduce

1. Queue an issue large enough to trigger decomposition (e.g. an ENH that
   `rn-decompose` splits into children).
2. Run `ll-loop run rn-implement "<id>"`.
3. After completion, inspect the run dir:
   `cat .loops/runs/rn-implement-<ts>/skipped.txt` and
   `cat .loops/runs/rn-implement-<ts>/decomposed_count.txt`.
4. Observe the decomposed parent appears in **both** `skipped.txt` and the
   `decomposed_count` tally.
5. In `summary.json`, observe the outcome buckets sum to more than
   `total_processed`.

## Root Cause

- **File**: `scripts/little_loops/loops/rn-decompose.yaml`
- **Anchor**: `enqueue_children` state, line 209
- **Cause**: `echo "$ID" >> "$RUN_DIR/skipped.txt"` writes the decomposed
  parent into the report-tally file that `rn-implement`'s `report` state
  treats as a disjoint outcome bucket. The parent is already accounted for via
  `decomposed_count.txt` (incremented four lines later) and via
  `finalize_parent` writing the `DECOMPOSED` outcome token. The `skipped.txt`
  write is redundant for tallying and actively wrong for the breakdown math.
  The original intent ("mark parent as skipped") appears to have been a
  re-dequeue guard, but queue removal + `visited.txt` already prevent
  re-processing — `skipped.txt` is purely a report tally.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **All anchor references verified accurate (no stale refs):**
  - `rn-decompose.yaml:209` — `echo "$ID" >> "$RUN_DIR/skipped.txt"` (the
    redundant write, comment "Mark parent as skipped (decomposed)" at line 208).
  - `rn-decompose.yaml:212-213` — `decomposed_count.txt` increment.
  - `rn-implement.yaml:915` — `DECOMPOSED=$(cat "$RUN_DIR/decomposed_count.txt" …)`.
  - `rn-implement.yaml:916` — `SKIPPED=$(wc -l < "$RUN_DIR/skipped.txt" …)`.
  - `rn-implement.yaml:885-889` — `skip_issue` state, the only *intended*
    writer to `skipped.txt` (`echo "$ID" >> …/skipped.txt` at line 889).
- **The re-dequeue-guard claim is confirmed by an existing comment.**
  `rn-decompose.yaml:198-202` documents that `visited.txt` (written by
  `rn-implement`'s fifo_pop/select_next at dequeue time) is the authoritative
  "dequeued" log, and that `enqueue_children` must *not* write `visited.txt`
  here (BUG-2004). Combined with queue removal, this means re-processing is
  already prevented without `skipped.txt` — directly supporting **Option A**
  (the `skipped.txt` write at line 209 has no guard role; it is pure tally
  double-counting).
- **`report` reads `skipped`/`decomposed` as fully disjoint buckets.**
  `rn-implement.yaml:915-916` plus the `summary.json` emission (lines 937-948)
  print `decomposed` and `skipped` as independent fields; nothing reconciles a
  parent appearing in both, so the over-count equals the number of decomposed
  parents — exactly as observed (8 processed, buckets sum 9).
- **Option A is low-blast-radius:** no other report tally file
  (`deferred.txt`, `blocked.txt`, `depth_capped.txt`, `failures.txt`) is
  double-written by `enqueue_children`; only `skipped.txt` is. Removing line
  209 leaves all other buckets untouched.
- **Both target test files exist:** `scripts/tests/test_rn_decompose.py` and
  `scripts/tests/test_rn_implement.py` are present; the latter already asserts
  on `decomposed_count.txt` (line 370) and routes (`route_dec_decomposed`,
  line 608), giving a natural home for the regression assertions.

## Acceptance Criteria

1. A decomposed parent is no longer written to `skipped.txt` (or, if a
   "decomposed parents" record is wanted, it is kept in a separate file that
   the `report` state does not fold into the `skipped` bucket).
2. After a run containing at least one decomposition, the `summary.json`
   outcome buckets sum to ≤ `total_processed`.
3. A regression test asserts that `enqueue_children` in `rn-decompose.yaml`
   does not append the parent ID to `skipped.txt`, OR that `report`'s tallied
   buckets do not double-count a decomposed parent.

## Proposed Solution

**Option A (preferred)**: Remove the `echo "$ID" >> "$RUN_DIR/skipped.txt"`
line at `rn-decompose.yaml:209`. The parent is already tracked by
`decomposed_count.txt` and the `DECOMPOSED` outcome token; queue removal and
`visited.txt` handle re-dequeue prevention, so the skip-tally write is pure
double-counting.

**Option B**: Keep the parent record but redirect it to a dedicated file
(e.g. `decomposed_parents.txt`) that the `report` state does not sum into the
`skipped` bucket.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-decompose.yaml` — remove `echo "$ID" >> "$RUN_DIR/skipped.txt"` from `enqueue_children` state (~line 209)
- `docs/guides/LOOPS_REFERENCE.md` — remove/rewrite "The parent is recorded as skipped (decomposed) in `skipped.txt`." in the `rn-decompose` Notes paragraph (~line 485) [wiring pass]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/rn-implement.yaml` — `report` state (~line 916) reads `skipped.txt` and `decomposed_count.txt` as disjoint buckets; no changes needed after the fix but verify tallies hold

### Similar Patterns
- N/A — no other loop writes the same parent ID to both a skip-tally file and a separate outcome counter

### Tests

_Wiring pass added by `/ll:wire-issue` — confirmed patterns and specific targets:_
- `scripts/tests/test_rn_decompose.py` — add `test_enqueue_children_does_not_write_skipped_txt` to `TestDecompositionChain`; assert `"skipped.txt" not in data["states"]["enqueue_children"]["action"]` (BUG-2289 regression)
- `scripts/tests/test_rn_implement.py` — add two tests to cover the disjointness invariant:
  - `test_skip_issue_is_sole_skipped_txt_writer` in `TestParentClassifier`: scan all states, assert only `skip_issue` and `init` write to `skipped.txt`
  - `test_report_decomposed_and_skipped_use_distinct_sources` in `TestReportAndTerminal`: assert both `"decomposed_count.txt"` and `"skipped.txt"` appear in `report["action"]` as separate source references
- Pattern: pure YAML-text assertions only (`yaml.safe_load` + `assert "..." in/not in action`); no subprocess or `tmp_path`; bug ID reference in docstring and assertion message; follow `TestDecompositionChain` / `TestReportAndTerminal` class conventions
- No existing tests assert the erroneous `skipped.txt` write — the fix will not break any current test

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — `rn-decompose` Notes paragraph (~line 485) states "The parent is recorded as skipped (decomposed) in `skipped.txt`." — remove or rewrite to state that the decomposed parent is tracked via `decomposed_count.txt` and the `DECOMPOSED` outcome token written by `finalize_parent`

### Configuration
- N/A

## Implementation Steps

1. Remove the `echo "$ID" >> "$RUN_DIR/skipped.txt"` line from `enqueue_children` in `rn-decompose.yaml`
2. Verify the `report` state in `rn-implement.yaml` reads `skipped.txt` and `decomposed_count.txt` without overlap — no further edits expected
3. Add regression test in `test_rn_decompose.py`: `test_enqueue_children_does_not_write_skipped_txt` in `TestDecompositionChain` — assert `"skipped.txt" not in data["states"]["enqueue_children"]["action"]`
4. Add two structural tests in `test_rn_implement.py`: `test_skip_issue_is_sole_skipped_txt_writer` (scan all states, assert only `skip_issue`/`init` write to `skipped.txt`) and `test_report_decomposed_and_skipped_use_distinct_sources` (assert both tally files appear in `report["action"]` as separate references)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/guides/LOOPS_REFERENCE.md` (~line 485) — remove or rewrite "The parent is recorded as skipped (decomposed) in `skipped.txt`." in the `rn-decompose` Notes paragraph to reflect that the decomposed parent is tracked via `decomposed_count.txt` and the `DECOMPOSED` outcome token

## Impact

- **Priority**: P3 — Telemetry inaccuracy in session reports; does not block
  issue implementation but misreports run outcomes (breakdown exceeds total).
- **Effort**: Small — likely a one-line removal in `rn-decompose.yaml` plus a
  test.
- **Risk**: Low — confined to a report-tally write in loop YAML; no Python or
  FSM-engine changes.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-25 | Priority: P3

## Session Log
- `/ll:wire-issue` - 2026-06-25T14:18:38 - `0dd67099-f064-444a-8696-874bdae766b0.jsonl`
- `/ll:refine-issue` - 2026-06-25T14:05:29 - `cd1382df-2f0c-4a2c-9267-f984e7cc89aa.jsonl`
- `/ll:format-issue` - 2026-06-25T14:01:09 - `825fcb47-9057-4fbe-b73f-2ff9366825b5.jsonl`
- `/ll:capture-issue` - 2026-06-25T13:53:17Z - `fe374318-c8a2-454a-82dd-24bd83653458.jsonl`
