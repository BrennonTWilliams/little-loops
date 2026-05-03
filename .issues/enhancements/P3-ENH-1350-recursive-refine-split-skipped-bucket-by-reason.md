---
id: ENH-1350
type: ENH
priority: P3
status: open
discovered_date: 2026-05-03
discovered_by: capture-issue
captured_at: "2026-05-03T16:43:25Z"
related: [ENH-1339, ENH-1340, ENH-1341, ENH-1347, ENH-1348]
---

# ENH-1350: Split `recursive-refine` "Skipped" Bucket Into Meaningful Reason Categories

## Summary

`recursive-refine` currently writes all non-passing issue IDs to a single `recursive-refine-skipped.txt` file, conflating four fundamentally different outcomes: (a) parent decomposed into children, (b) dead-end — no further decomposition possible, (c) depth-capped (once ENH-1347 lands), and (d) budget-exhausted (once ENH-1339 lands). The `done` summary therefore shows a single opaque `Skipped (M): ...` line that tells the user nothing useful. Split the file into per-reason tracking files and update `done` to show a meaningful per-category breakdown.

## Motivation

The current `Skipped (M)` line is actively misleading: an ID listed there might be a successfully-decomposed parent whose children all passed, or it might be an issue that was permanently abandoned. These are completely different outcomes and require different user action (or none). Partitioning by reason is a prerequisite for:

- ENH-1341's decomposition tree (needs to know *why* each ID was skipped to render `(skipped: budget)` vs `[decomposed]`)
- ENH-1348's progress line (skipped count in the progress line becomes meaningful)
- Any future `assess-loop` or `analyze-loop` analysis that interprets outcomes

ENH-1347 (depth tracking) and ENH-1339 (budget cap) already introduce their own reason files (`recursive-refine-skipped-depth.txt`, `recursive-refine-skipped-budget.txt`) alongside `recursive-refine-skipped.txt`, so the per-reason pattern is already emerging — this issue formalizes and completes it for the two currently-untracked reasons.

## Current Behavior

- `enqueue_children` (line 201): `echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped.txt`
- `enqueue_or_skip` children branch (line 334): same write
- `enqueue_or_skip` dead-end branch (line 344): same write
- `done` (line 351): reads `recursive-refine-skipped.txt` and prints a single `Skipped (M): ...` line

## Expected Behavior

### Tracking files

| Reason | File | Written by |
|--------|------|------------|
| Decomposed (parent split into children) | `recursive-refine-skipped-decomposed.txt` | `enqueue_children`, `enqueue_or_skip` (children branch) |
| Dead-end (no further decomposition) | `recursive-refine-skipped-deadend.txt` | `enqueue_or_skip` (no-children branch) |
| Depth-capped | `recursive-refine-skipped-depth.txt` | ENH-1347's `check_depth` state |
| Budget-exhausted | `recursive-refine-skipped-budget.txt` | ENH-1339's `check_attempt_budget` state |

`recursive-refine-skipped.txt` continues to receive **all** skip IDs (unchanged) so outer-loop callers (`auto-refine-and-implement`, `sprint-refine-and-implement`) that read it via `get_passed_issues` are not broken.

### `done` summary

Replace the current single `Skipped (M):` line with:

```
=== Recursive Refine Summary ===

Passed       (3): ENH-1200, ENH-1201, ENH-1300
Decomposed   (2): ENH-1100, ENH-1201     ← parent split into children
Dead-ends    (1): ENH-1202               ← no further decomposition possible
Depth-cap    (0): none
Budget       (0): none
```

When all reason counts are 0 except one, collapse to a single `Skipped (N): ...` line (backwards-compatible display). The `Decomposed` line is omitted from the "Skipped" total since it represents successful processing via children.

## Proposed Solution

### Step 1 — Initialize reason files in `parse_input`

```bash
printf '' > .loops/tmp/recursive-refine-skipped-decomposed.txt
printf '' > .loops/tmp/recursive-refine-skipped-deadend.txt
```
(ENH-1347 and ENH-1339 already initialize `skipped-depth.txt` and `skipped-budget.txt` respectively; if those issues haven't landed yet, `done` reads them defensively with `2>/dev/null`.)

### Step 2 — Write decomposed reason in `enqueue_children` and `enqueue_or_skip` (children branch)

After the existing write to `recursive-refine-skipped.txt`, add:
```bash
echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped-decomposed.txt
```

### Step 3 — Write dead-end reason in `enqueue_or_skip` (no-children branch)

After the existing write to `recursive-refine-skipped.txt`, add:
```bash
echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped-deadend.txt
```

### Step 4 — Update `done` summary

Replace the current `SKIPPED_IDS` / `SKIPPED_COUNT` / `SKIPPED_LIST` block with per-category reads:

```bash
read_ids() { cat "$1" 2>/dev/null | grep -v '^[[:space:]]*$' | sort -u || true; }
count_ids() { echo "$1" | grep -c '[^[:space:]]' 2>/dev/null || echo 0; }
join_ids()  { echo "$1" | tr '\n' ',' | sed 's/,$//'; }

PASSED_IDS=$(read_ids .loops/tmp/recursive-refine-passed.txt)
DECOMPOSED_IDS=$(read_ids .loops/tmp/recursive-refine-skipped-decomposed.txt)
DEADEND_IDS=$(read_ids .loops/tmp/recursive-refine-skipped-deadend.txt)
DEPTH_IDS=$(read_ids .loops/tmp/recursive-refine-skipped-depth.txt)
BUDGET_IDS=$(read_ids .loops/tmp/recursive-refine-skipped-budget.txt)

PASSED_COUNT=$(count_ids "$PASSED_IDS")
DECOMPOSED_COUNT=$(count_ids "$DECOMPOSED_IDS")
DEADEND_COUNT=$(count_ids "$DEADEND_IDS")
DEPTH_COUNT=$(count_ids "$DEPTH_IDS")
BUDGET_COUNT=$(count_ids "$BUDGET_IDS")

printf '\n=== Recursive Refine Summary ===\n\n'
printf 'Passed       (%d): %s\n' "$PASSED_COUNT"    "${$(join_ids "$PASSED_IDS"):-none}"
printf 'Decomposed   (%d): %s\n' "$DECOMPOSED_COUNT" "${$(join_ids "$DECOMPOSED_IDS"):-none}"
printf 'Dead-ends    (%d): %s\n' "$DEADEND_COUNT"   "${$(join_ids "$DEADEND_IDS"):-none}"
printf 'Depth-cap    (%d): %s\n' "$DEPTH_COUNT"     "${$(join_ids "$DEPTH_IDS"):-none}"
printf 'Budget       (%d): %s\n' "$BUDGET_COUNT"    "${$(join_ids "$BUDGET_IDS"):-none}"
printf '\n'
```

## Acceptance Criteria

- [ ] `parse_input` initializes `recursive-refine-skipped-decomposed.txt` and `recursive-refine-skipped-deadend.txt`.
- [ ] `enqueue_children` writes to both `recursive-refine-skipped.txt` (unchanged) and `recursive-refine-skipped-decomposed.txt`.
- [ ] `enqueue_or_skip` children branch writes to both `recursive-refine-skipped.txt` and `recursive-refine-skipped-decomposed.txt`.
- [ ] `enqueue_or_skip` dead-end branch writes to both `recursive-refine-skipped.txt` and `recursive-refine-skipped-deadend.txt`.
- [ ] `done` summary shows 5 labelled rows (Passed, Decomposed, Dead-ends, Depth-cap, Budget).
- [ ] `done` reads `skipped-depth.txt` and `skipped-budget.txt` defensively (empty counts if files absent).
- [ ] Outer-loop callers (`auto-refine-and-implement`, `sprint-refine-and-implement`) that read `recursive-refine-skipped.txt` are unaffected.
- [ ] Test: synthetic run with 1 decomposed parent, 1 dead-end, 1 passed verifies all 5 rows in `done` output.

## Scope Boundaries

- **In scope**: `parse_input` init, per-reason writes in `enqueue_*`, `done` summary partition.
- **Out of scope**: Removing or changing the `recursive-refine-skipped.txt` aggregation file (must stay for outer-loop compat).
- **Out of scope**: Depth-cap and budget-cap tracking files (owned by ENH-1347 and ENH-1339 respectively); this issue only reads them defensively.
- **Out of scope**: Decomposition tree rendering (ENH-1341); this issue is the prerequisite for that work.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml`:
  - `parse_input` — init two new reason files
  - `enqueue_children` — add decomposed write
  - `enqueue_or_skip` — add decomposed or deadend write per branch
  - `done` — replace flat skipped block with 5-row summary

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — reads `recursive-refine-skipped.txt` (no change needed)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — same (no change needed)
- `scripts/tests/test_builtin_loops.py` — `TestRecursiveRefineLoop`: update `done` output assertions
- `scripts/tests/test_loops_recursive_refine.py` — add per-reason row verification

### Enables
- ENH-1341 (decomposition tree) — now has clean per-reason data to drive the tree render
- ENH-1348 (progress line) — skipped count in progress line now reflects true skips, not decomposed parents

### Similar Patterns
- `recursive-refine-skipped-depth.txt` (ENH-1347) and `recursive-refine-skipped-budget.txt` (ENH-1339) are the precedent pattern being generalized here

### Tests
- `scripts/tests/test_builtin_loops.py` — update `TestRecursiveRefineLoop` `done` output assertions
- `scripts/tests/test_loops_recursive_refine.py` — add per-reason row verification

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break (existing assertions on old format):**
- `TestDoneSummary._DONE_SCRIPT` (line ~602) — verbatim copy of `done` bash body; all 8 `TestDoneSummary` test methods run against this variable; must be replaced with the new bash body [Agent 3 finding]
- `TestDoneSummary.test_depth_cap_line_shows_capped_ids` (line ~731) — asserts `"Skipped (2):"` (flat aggregate row removed) and `"Skipped (depth-cap 1):"` (label changes) [Agent 3 finding]
- `TestDoneSummary.test_depth_cap_line_shows_none_when_no_capped_issues` (line ~748) — asserts `"Skipped (depth-cap 0): none"` (label changes) [Agent 3 finding]
- `TestDoneSummary.test_cycle_line_shows_cycle_ids` (line ~762) — asserts `"Skipped (cycle 1):"` (label changes) [Agent 3 finding]
- `TestDoneSummary.test_cycle_line_shows_none_when_no_cycle_issues` (line ~777) — asserts `"Skipped (cycle 0): none"` (label changes) [Agent 3 finding]
- `TestDoneSummary.test_budget_line_shows_budget_ids` (line ~791) — asserts `"Skipped (budget 1):"` (label changes to `Budget`) [Agent 3 finding]
- `TestDoneSummary.test_budget_line_shows_none_when_no_budget_issues` (line ~807) — asserts `"Skipped (budget 0): none"` (label changes) [Agent 3 finding]
- `scripts/tests/test_enh1345_doc_wiring.py` — `TestLoopsGuideWiring.test_depth_cap_summary_line_present` asserts `"Skipped (depth-cap"` in `LOOPS_GUIDE.md`; will break if the doc example block is updated to the new named-row format [Agent 2 finding]

**New tests to write:**
- `TestDepthMapInit` (or new `TestParseInputInit`): two tests for `parse_input` initializing `skipped-decomposed.txt` and `skipped-deadend.txt` — follow `test_skipped_depth_file_is_cleared` pattern (line ~40) [Agent 3 finding]
- New class for `enqueue_children` dual-write: assert parent ID appears in both `skipped.txt` AND `skipped-decomposed.txt` — follow `TestCheckDepth.test_at_max_depth_echoes_1_and_writes_both_skip_files` pattern (line ~236) [Agent 3 finding]
- New tests for `enqueue_or_skip` children branch: assert parent written to both `skipped.txt` AND `skipped-decomposed.txt` (same dual-file assertion pattern) [Agent 3 finding]
- New tests for `enqueue_or_skip` dead-end branch: assert parent written to both `skipped.txt` AND `skipped-deadend.txt` (same dual-file assertion pattern) [Agent 3 finding]
- Two paired `TestDoneSummary` tests for `Decomposed` row (IDs-present + none) — follow `test_depth_cap_line_shows_capped_ids` / `test_depth_cap_line_shows_none_when_no_capped_issues` pattern [Agent 3 finding]
- Two paired `TestDoneSummary` tests for `Dead-ends` row (IDs-present + none) — same pattern [Agent 3 finding]
- `TestRecursiveRefineLoop` in `test_builtin_loops.py`: two YAML-level assertions that `recursive-refine-skipped-decomposed.txt` and `recursive-refine-skipped-deadend.txt` appear in the `parse_input` action string — follow `test_parse_input_initializes_dequeued_count_and_total_enqueued` pattern (line ~1917) [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — "Summary output" subsection contains a verbatim code block showing the current `Skipped (N):` format; must be updated to show the new named-row format (`Passed`, `Decomposed`, `Dead-ends`, `Depth-cap`, `Budget`). The "Notes" paragraph inventories every `.loops/tmp/recursive-refine-*.txt` file and is missing `recursive-refine-skipped-decomposed.txt` and `recursive-refine-skipped-deadend.txt`. [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Precise write locations in `recursive-refine.yaml`** (line numbers differ from original issue estimates):
- `parse_input` initializes `skipped.txt` at line ~44, `skipped-depth.txt` at line ~56, `skipped-budget.txt` at line ~58 — new files slot in the same block using `printf '' > ...` form
- `enqueue_children` skipped.txt write: `echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped.txt` at line ~294
- `enqueue_or_skip` children-branch write: same echo pattern at line ~510 (after the Python cycle-filter block at lines ~472–495)
- `enqueue_or_skip` dead-end-branch write: same echo pattern at line ~533

**`done` state already has 5 rows, not a single `Skipped (M)` line:**
The current `done` already emits: `Passed (N)`, `Skipped (N)` (aggregate), `Skipped (depth-cap N)`, `Skipped (cycle N)`, `Skipped (budget N)`. The change here is to ADD two more rows (`Decomposed` and `Dead-ends`) and decide whether to keep the flat `Skipped (N)` aggregate row. The issue's Expected Behavior omits both the aggregate `Skipped` row and the `Skipped (cycle)` row — implementer must decide whether those rows stay, and how to handle the cycle row that is not mentioned in the expected output format.

**`TestDoneSummary._DONE_SCRIPT`** in `test_loops_recursive_refine.py` (line ~602) is a verbatim copy of the `done` action bash body. This class variable must be updated alongside the YAML or test assertions will fail against the old shell behavior.

**Test patterns to follow:**
- `parse_input` init test: `TestDepthMapInit.test_skipped_depth_file_is_cleared` (line ~40) — pre-seed stale content, run shell snippet, assert empty
- Dual-file write test: `TestCheckDepth.test_at_max_depth_echoes_1_and_writes_both_skip_files` (line ~228) — assert ID appears in both per-reason file and `skipped.txt`
- `done` per-reason row tests: `TestDoneSummary.test_depth_cap_line_shows_capped_ids` (line ~731) and `test_depth_cap_line_shows_none_when_no_capped_issues` (line ~748) — two paired tests per reason (IDs-present case + none case)
- YAML file-reference assertion: `TestRecursiveRefineLoop.test_parse_input_initializes_dequeued_count_and_total_enqueued` (line ~1917) — assert file name substring exists in state action string

## Implementation Steps

1. In `recursive-refine.yaml` `parse_input` (~line 58), after the `skipped-budget.txt` init, add:
   ```bash
   printf '' > .loops/tmp/recursive-refine-skipped-decomposed.txt
   printf '' > .loops/tmp/recursive-refine-skipped-deadend.txt
   ```
2. In `enqueue_children` (~line 294), after the existing `echo ... >> skipped.txt` append, add:
   ```bash
   echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped-decomposed.txt
   ```
3. In `enqueue_or_skip` children branch (~line 510), after the existing `skipped.txt` append, add the same decomposed write.
4. In `enqueue_or_skip` dead-end branch (~line 533), after the existing `skipped.txt` append, add:
   ```bash
   echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped-deadend.txt
   ```
5. In `done` (~lines 589–620): add reads for `skipped-decomposed.txt` and `skipped-deadend.txt` (defensive `2>/dev/null`, same pattern as depth/cycle/budget) and add two new `printf` rows. Decide whether the flat `Skipped (N)` aggregate row and the `Skipped (cycle N)` row remain — the issue's Expected Behavior omits both, but both currently exist; align with the expected format in the issue unless there is a reason to preserve them.
6. Update `TestDoneSummary._DONE_SCRIPT` in `test_loops_recursive_refine.py` (~line 602) to match the new `done` bash body exactly.
7. Add two paired `TestDoneSummary` tests per new reason (IDs-present + none) following the pattern at lines ~731 and ~748.
8. In `test_builtin_loops.py` `TestRecursiveRefineLoop`, add assertions that `recursive-refine-skipped-decomposed.txt` and `recursive-refine-skipped-deadend.txt` appear in the `parse_input` action string, following the pattern at line ~1917.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `docs/guides/LOOPS_GUIDE.md` — replace the "Summary output" code block with the new named-row format; add `recursive-refine-skipped-decomposed.txt` and `recursive-refine-skipped-deadend.txt` to the "Notes" file-inventory paragraph
10. Update `TestDoneSummary._DONE_SCRIPT` (~line 602 in `test_loops_recursive_refine.py`) to exactly match the new `done` bash body; update all 7 existing `TestDoneSummary` assertion strings that reference the old `Skipped (N):` / `Skipped (depth-cap N):` / `Skipped (cycle N):` / `Skipped (budget N):` labels; add `skipped-decomposed.txt` and `skipped-deadend.txt` file creation to each test's fixture setup so the new `cat 2>/dev/null` reads don't fail
11. Update `test_enh1345_doc_wiring.py` `TestLoopsGuideWiring.test_depth_cap_summary_line_present` to assert against the new `Depth-cap` label (or whatever the doc example uses after step 9)
12. Add new `parse_input` init tests to `test_loops_recursive_refine.py` (2 tests) for the new tracking files, following the `test_skipped_depth_file_is_cleared` pattern (~line 40)
13. Add new dual-file write tests for `enqueue_children` and both `enqueue_or_skip` branches (4 tests), following the `TestCheckDepth.test_at_max_depth_echoes_1_and_writes_both_skip_files` pattern (~line 236)
14. Add 4 paired `TestDoneSummary` tests (2 for `Decomposed`, 2 for `Dead-ends`), following the `test_depth_cap_line_shows_capped_ids` / `test_depth_cap_line_shows_none` pattern (~lines 731, 748)
15. Add 2 YAML-level assertions to `TestRecursiveRefineLoop` in `test_builtin_loops.py` confirming `parse_input` action references both new file names, following `test_parse_input_initializes_dequeued_count_and_total_enqueued` (~line 1917)

## Impact

- **Priority**: P3 — Prerequisite for ENH-1341 (decomposition tree); standalone observability value.
- **Effort**: Small — Additive writes + `done` reformat; no routing changes.
- **Risk**: Low — `recursive-refine-skipped.txt` is unchanged; outer-loop callers unaffected.
- **Breaking Change**: No — `done` output format changes (new rows), but no machine consumers of `done` output exist.


## Blocked By

- ENH-1348

## Labels

`enhancement`, `recursive-refine`, `fsm-loops`, `observability`, `cli-output`

## Status

**Open** | Created: 2026-05-03 | Priority: P3

## Session Log
- `/ll:wire-issue` - 2026-05-03T21:55:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee908308-1c25-4a99-aeca-3c787c3838d9.jsonl`
- `/ll:refine-issue` - 2026-05-03T21:50:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1873aa88-61fd-4251-9283-38981a2c0599.jsonl`
- `/ll:format-issue` - 2026-05-03T19:20:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16a69f6f-62b6-4282-8d76-179c33de8c88.jsonl`
- `/ll:capture-issue` - 2026-05-03T16:43:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81b5153d-e662-4abf-af0e-b3ec54065e0b.jsonl`
