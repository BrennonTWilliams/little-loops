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

## Implementation Steps

1. Initialize `skipped-decomposed.txt` and `skipped-deadend.txt` in `parse_input`.
2. Add decomposed write to `enqueue_children`.
3. Add decomposed write to `enqueue_or_skip` children branch.
4. Add dead-end write to `enqueue_or_skip` dead-end branch.
5. Replace `done` flat-skipped block with 5-row per-category summary.
6. Update test assertions in `test_builtin_loops.py` for the new `done` format.
7. Add per-reason row verification to `test_loops_recursive_refine.py`.

## Impact

- **Priority**: P3 — Prerequisite for ENH-1341 (decomposition tree); standalone observability value.
- **Effort**: Small — Additive writes + `done` reformat; no routing changes.
- **Risk**: Low — `recursive-refine-skipped.txt` is unchanged; outer-loop callers unaffected.
- **Breaking Change**: No — `done` output format changes (new rows), but no machine consumers of `done` output exist.

## Labels

`enhancement`, `recursive-refine`, `fsm-loops`, `observability`, `cli-output`

## Session Log
- `/ll:capture-issue` - 2026-05-03T16:43:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81b5153d-e662-4abf-af0e-b3ec54065e0b.jsonl`
