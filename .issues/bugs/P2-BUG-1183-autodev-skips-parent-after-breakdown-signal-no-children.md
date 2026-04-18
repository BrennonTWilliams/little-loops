---
captured_at: "2026-04-18T22:20:25Z"
discovered_date: 2026-04-18
discovered_by: capture-issue
---

# BUG-1183: autodev silently skips parent when breakdown flag is set but no children were created

## Summary

When `refine-to-ready-issue` routes through `breakdown_issue` → `write_broke_down` but the invoked `/ll:issue-size-review --auto` only *recommends* breakdown without actually creating child issue files, the outer `autodev` loop takes its "already size-reviewed" shortcut, finds no children, logs `"Skipped: <ID> (no further decomposition possible)"`, and drops the parent from further processing. The parent is never moved to `.issues/completed/` and never re-attempted. Observed on FEAT-1181 during autodev run `2026-04-18T194126` (final event at `22:07:08`).

## Current Behavior

For a parent issue that fails confidence/outcome thresholds:

1. Sub-loop `refine-to-ready-issue` runs `breakdown_issue` → invokes `/ll:issue-size-review <ID> --auto` (70s on FEAT-1181). The skill returns analysis recommending breakdown **but does not create any child issue files**.
2. Sub-loop then runs `write_broke_down` → writes `1` to `.loops/tmp/recursive-refine-broke-down`. Sub-loop exits via `done`.
3. Outer `autodev` loop runs `copy_broke_down` → copies flag into `.loops/tmp/autodev-broke-down` (value: `1`).
4. `check_passed` → exit 1 (issue still below thresholds) → route to `detect_children`.
5. `detect_children` → diffs pre-/post-sub-loop issue IDs filtered by the `Decomposed from <PARENT>` marker → finds **none** → exit 1 → route to `size_review_snap`.
6. `size_review_snap` snapshots post-ids into pre-ids (pre == post going forward).
7. `check_broke_down` evaluates flag: `1 < 1` is false → routes via `on_no` to **`enqueue_or_skip`**, bypassing `recheck_scores` → `run_size_review`.
8. `enqueue_or_skip` re-scans for children (still none, because pre == post and none were ever created) → logs `"Skipped: FEAT-1181 (no further decomposition possible)"`, appends ID to `.loops/tmp/autodev-skipped.txt`, **does not** `git mv` the parent to `.issues/completed/`.
9. `dequeue_next` → queue empty → exit 1 → loop routes to `done` and terminates normally.

Net effect: the parent remains in the active backlog, was never actually decomposed, was never implemented, and the loop reports success.

## Expected Behavior

If the sub-loop's breakdown signal is set (`autodev-broke-down == 1`) **but `detect_children` found no new child issues**, the outer loop should fall through to `run_size_review` (its own size-review state) rather than shortcut to `enqueue_or_skip`. That state would re-invoke `/ll:issue-size-review` in a context where child creation is expected, or route to a terminal "needs human" state with a clearer signal than `"no further decomposition possible"`. Either way, the loop must not silently drop a parent that has never produced children.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `in state check_broke_down` (lines 248–261)
- **Cause**: The `check_broke_down` guard (added in the fix for BUG-1079) treats `broke_down == 1` as proof that size-review already ran *and produced children*. It routes `on_no` straight to `enqueue_or_skip`, skipping `run_size_review`. This collapses two distinct sub-loop outcomes into one branch:
  - (a) sub-loop created children → `detect_children` already caught them; skip is correct.
  - (b) sub-loop only produced analysis → no children exist; skipping `run_size_review` means the outer loop never gets its own chance to create them.
- The contract between `refine-to-ready-issue.breakdown_issue` (which writes the flag unconditionally based on sub-loop state) and `autodev.check_broke_down` (which reads the flag as a proxy for "children exist") is broken when `/ll:issue-size-review --auto` returns without creating files.

## Motivation

The `autodev` loop exists to drive issues to an implementable state. Silently skipping an issue that never decomposed defeats that purpose and is invisible in the summary (appears as a normal skip). When a user submits a targeted list like `ll-loop run autodev "FEAT-1181"`, the expected outcome is either implementation or at minimum a clear failure/decomposition; getting `"Skipped: ... (no further decomposition possible)"` with the parent still in the backlog is a silent no-op that burns ~10 minutes of LLM wall-clock time (refine + wire + confidence + size-review) with zero forward progress. Since `autodev` is the primary driver for targeted multi-issue runs, this regression blocks its use as a reliable pipeline.

## Proposed Solution

Change the semantics of `check_broke_down` so the shortcut is only taken when children actually exist. Two candidate fixes (pick one during implementation):

**Option A — Outer-loop guard:** Have `check_broke_down` AND-combine the flag with a child-existence check:
- If `autodev-broke-down == 1` **and** the `autodev-new-children.txt` (written by `detect_children`) is non-empty → route to `enqueue_or_skip`.
- Otherwise (flag=1 but no children, or flag=0) → route to `recheck_scores` / `run_size_review`.

**Option B — Source-of-truth flag:** Move the flag write out of `write_broke_down` (which fires on sub-loop terminal state) and into the `breakdown_issue` action itself, conditioned on "did `/ll:issue-size-review` create new child files". This keeps `check_broke_down`'s current binary semantics but makes the flag accurately reflect reality.

Option A is smaller and localized to `autodev.yaml`. Option B requires a cross-loop contract change and touches every caller of `refine-to-ready-issue`.

## Implementation Steps

1. Decide Option A vs B (recommend A — smaller surface area and doesn't disturb BUG-1079's fix).
2. For Option A: add a shell check in `check_broke_down.action` that reads both flag and child count; emit a numeric value the existing `output_numeric` evaluator can route on (e.g., `0` = fall through, `1` = shortcut).
3. Add a regression test that exercises the "breakdown signaled, no children created" path and asserts `autodev` routes through `run_size_review`.
4. Replay against FEAT-1181 (currently in `.issues/features/`) to verify the parent either decomposes or reaches a clear terminal state.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml:248-261` — change `check_broke_down` evaluate/routing so flag=1 + no-children falls through to `recheck_scores`/`run_size_review`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:226-232` — owns `breakdown_issue` + `write_broke_down`; no behavior change needed for Option A.
- `.loops/tmp/autodev-new-children.txt` — written by `detect_children` (autodev.yaml ~line 173), consumed today by `enqueue_or_skip`. Option A adds a second reader in `check_broke_down`.

### Similar Patterns
- BUG-1079 (completed) introduced the `check_broke_down` shortcut to avoid double size-review. Review its fix commit before changing the semantics to avoid regressing the double-invocation problem.

### Tests
- `scripts/tests/` — find existing `autodev` or `refine-to-ready-issue` loop tests; add a scenario where `breakdown_issue` writes the flag but no child files appear.

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — any FSM diagram or prose that documents the `check_broke_down` branching table should be updated to show the new three-way decision.

### Configuration
- None.

## Impact

- **Priority**: P2 — silently drops issues from autodev's targeted queue; primary-function failure but bounded (loop exits cleanly, parent still on disk).
- **Effort**: Small — localized YAML + evaluator change if Option A is chosen.
- **Risk**: Medium — tangled with BUG-1079's fix; must preserve the "no double size-review" invariant.
- **Breaking Change**: No — loop config change only; existing callers unaffected.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `autodev`, `captured`

## Status

**Open** | Created: 2026-04-18 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-04-18T22:20:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ccc8368e-06c9-482f-96d4-4fbb17a0fbbf.jsonl`
