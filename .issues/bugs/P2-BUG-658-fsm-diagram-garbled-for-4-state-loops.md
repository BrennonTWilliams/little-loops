---
type: BUG
id: BUG-658
title: FSM box diagram garbled for 4-state loops
priority: P2
status: open
discovered_date: 2026-03-08
discovered_by: capture-issue
---

# BUG-658: FSM box diagram garbled for 4-state loops

## Summary

`ll-loop show issue-refinement-git` renders a corrupted box diagram when the FSM has 4 states (evaluate, fix, check_commit, commit). The `fix` state is dropped from the diagram entirely, and the `check_commit`/`commit` boxes are rendered at overlapping horizontal positions, producing mangled box borders and truncated action text.

## Current Behavior

```
Diagram:
                                      ┌──────────────────────────────────┐             ┌────────┐
                                      │ → evaluate  [shell]              │───success──▶│ done ◉ │
                                      │ ll-issues refine-status --no-key │             │        │
                                      └──────────────────────────────────┘             └────────┘
                                                    ↺ partial
                                                        ▲
                                                   fail │ next/error
                                                        │
                                      ┌───────────┌──────────────────┐───────────┐
                                    ◄──success─omm│tcommit  [prompt] │           │
                                      │ FILE="/tmp│i/ll:commitement-c│mmit-coun… │
                                      └───────────└──────────────────┘───────────┘
```

Observed problems:
1. **`fix` state is missing** — the `on_failure` transition from `evaluate` leads to `fix`, but `fix` never appears in the rendered diagram
2. **`check_commit` and `commit` boxes overlap** — both boxes are rendered at the same horizontal column, causing their borders to merge and their content to interleave (e.g. `"omm│tcommit"` is `commit` bisected by a shared vertical border)
3. **Edge labels are corrupted** — `◄──success─omm│tcommit` is a mangled `◄──success──` plus the start of the `commit` box label

## Expected Behavior

All 4 states should appear as distinct, non-overlapping boxes:

```
                                      ┌──────────────────────────────────┐             ┌────────┐
                                      │ → evaluate  [shell]              │───success──▶│ done ◉ │
                                      │ ll-issues refine-status --no-key │             │        │
                                      └──────────────────────────────────┘             └────────┘
                                                    ↺ partial
                                                 fail/error │
                                                            ▼
  ┌───────────────────────────────┐  ┌────────────────────────────────────┐  ┌─────────────────────────┐
  │ fix  [prompt]                 │──▶│ check_commit  [shell]              │──▶│ commit  [prompt]         │
  │ Run `ll-issues refine-stat…   │next│ FILE="/tmp/issue-refinement-co…   │suc│ /ll:commit               │
  └───────────────────────────────┘  └────────────────────────────────────┘  └─────────────────────────┘
                                 ◄──failure─                            ◄──next─
```

Key elements (exact widths will vary with terminal):
- Main path: `evaluate → done` on top row (horizontal)
- Off-path row: `fix`, `check_commit`, `commit` as 3 distinct non-overlapping boxes
- Forward arrows between boxes: `fix ──next──▶ check_commit ──success──▶ commit`
- Back-edge arrows: `◄──failure─` to left of `check_commit`; `◄──next─` to left of `commit`
- Down-connector: `fail/error ▼` from `evaluate` into `fix` only
```

Minimum acceptance criteria:
- All 4 non-terminal state names (`evaluate`, `fix`, `check_commit`, `commit`) appear in the diagram output
- No state label is split by a box border character
- No two boxes share the same grid column at the same row (no horizontal overlap)

## Steps to Reproduce

1. Ensure `.loops/issue-refinement-git.yaml` exists (4-state FSM: evaluate, fix, check_commit, commit + done terminal)
2. Run `ll-loop show issue-refinement-git`
3. Observe the **Diagram:** section — `fix` is absent and `check_commit`/`commit` boxes overlap

## Root Cause

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Function**: `_render_2d_diagram()` (lines 463–943), dispatched from `_render_fsm_diagram()` (lines 358–460)
- **Anchor**: Off-path column assignment loop at lines 566–581

The main-path greedy walker (lines 406–424) follows `on_success` from `evaluate` and immediately reaches the terminal `done` state, producing `main_path = [evaluate, done]`. The three non-terminal states `fix`, `check_commit`, and `commit` are correctly collected into `off_path = [fix, check_commit, commit]` via the branch-population loop (lines 481–488).

The column assignment loop (lines 566–581) centers each off-path state under its first discovered neighbor that already has a `col_start`. Because the chain is linear (`evaluate → fix → check_commit → commit`), each state anchors to the previous one, which in turn anchors back to `col_center[evaluate]`. All three off-path states are assigned `col_start` values that center them at approximately the same horizontal position (the center of `evaluate`).

The single shared `off_grid` (line 801) has no collision detection. `fix` is written first; `check_commit` and `commit`, written later at the same column positions, overwrite `fix`'s box border characters entirely — causing `fix` to visually disappear. The connector characters (`│`, arrow tips) for all three states are also written at `col_center[evaluate]`, producing the interleaved border output seen in the bug report.

## Proposed Solution

1. **Detect missing states**: After layout assignment, verify that every non-terminal state is assigned a grid cell. Any unplaced state is a rendering bug.
2. **Ensure unique columns for co-depth off-path states**: Extend the `off_grid` column-assignment logic (introduced in BUG-598) to prevent two states from sharing the same column when they are at different depth levels in the chain.
3. **Regression test**: Add a test with the `issue-refinement-git` YAML (or a minimal 4-state equivalent) asserting that all 4 state names appear in the diagram output and that no state label is split by a box border.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `_render_2d_diagram()` (lines 463–943), specifically the off-path column assignment loop at lines 566–581 (no collision detection between chained off-path states)

### Key Code Sections (Confirmed Line Ranges)
- `info.py:358–460` — `_render_fsm_diagram()` entry point: edge list, BFS ordering, main-path walk, branch/back-edge classification
- `info.py:406–424` — Main path greedy walk; stops at terminal `done`, leaving `fix`/`check_commit`/`commit` as off-path
- `info.py:426–444` — Branch vs back-edge classification
- `info.py:481–488` — `off_path` population from `branches` only
- `info.py:548–581` — Column assignment: main-path states first, then off-path by neighbor lookup (no collision detection)
- `info.py:566–581` — **Bug site**: off-path column assignment loop; each state centers on its neighbor, causing all three to converge to `col_center[evaluate]`
- `info.py:727–793` — Phase 1: pre-compute `off_spec` per off-path state
- `info.py:795–939` — Phase 2: single shared `off_grid`; later-written states overwrite earlier ones at same column

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py` — `_render_fsm_diagram()` (lines 358–460) dispatches to `_render_2d_diagram()`

### Tests
- `scripts/tests/test_ll_loop_display.py` — primary test file for diagram rendering; `TestRenderFsmDiagram` class at lines 634–917
- Add regression test to `TestRenderFsmDiagram` following the pattern of `test_multiple_off_path_states_same_depth` (line 813) — which was added for BUG-598 and tests the side-by-side layout

### Test Patterns to Follow
- **FSM builder**: use `_make_fsm()` helper (line 637) with inline `StateConfig` objects; no YAML file needed
- **State-in-box assertion**: `[line for line in lines if "fix" in line and "│" in line]` (see line 706–708)
- **No-overlap assertion**: verify that box lines for different states do not share any overlapping column ranges (extend the pattern from line 838–849)

### Similar Patterns
- `test_multiple_off_path_states_same_depth` at `scripts/tests/test_ll_loop_display.py:813` — BUG-598 regression test for side-by-side layout; closest model for the new regression test
- BUG-598 completed fix: `.issues/completed/P3-BUG-598-fsm-diagram-off-path-states-stack-vertically-instead-of-side-by-side.md` — introduced the shared `off_grid` two-phase approach that this fix must extend
- `loops/fix-quality-and-tests.yaml` — the 4-state FSM that BUG-598 was fixed against (different topology: two parallel off-path pairs vs. linear chain)
- `.loops/issue-refinement-git.yaml` — the exact 5-state FSM (4 non-terminal + `done`) that reproduces BUG-658

### Documentation
- N/A — internal rendering function, no user-facing docs

### Configuration
- N/A

## Implementation Steps

1. **Confirm the exact column collision** by tracing `col_start` values after `info.py:566–581` for a 4-state chain; verify all three off-path states converge to `col_center[evaluate]`
2. **Fix `info.py:566–581`** — extend the off-path column assignment loop to track occupied column ranges; when a new off-path state would overlap an already-placed state, shift it rightward by `max_right_edge_so_far + gap` (mirror the main-path `x` accumulation pattern at lines 548–564)
3. **Verify `off_grid` width** — `total_width` at lines 583–587 must be recomputed after all off-path column positions are assigned, not before, to accommodate the rightward-shifted states
4. **Add regression test** in `scripts/tests/test_ll_loop_display.py` inside `TestRenderFsmDiagram` (after line 855):
   - Build a 5-state FSM matching `issue-refinement-git` topology using `_make_fsm()` + inline `StateConfig` objects
   - Assert all four non-terminal state names (`evaluate`, `fix`, `check_commit`, `commit`) appear in a box line containing `│`
   - Assert no two box lines for different states share any overlapping column range at the same row index
5. **Run existing tests** to confirm BUG-598 regression (`test_multiple_off_path_states_same_depth`) still passes: `python -m pytest scripts/tests/test_ll_loop_display.py -v`
6. **Manual verification**: `ll-loop show issue-refinement-git` — all 4 state boxes must appear non-overlapping

## Impact

- **Priority**: P2 — Diagram is the primary visual output of `ll-loop show`; a 4-state FSM (common pattern with a commit cadence state) renders completely incorrectly
- **Effort**: Medium — Root cause is in the off-path layout algorithm; prior fixes (BUG-598) provide a good foundation
- **Risk**: Low — Isolated to the diagram renderer, no side effects on loop execution
- **Breaking Change**: No

## Labels

`bug`, `fsm`, `diagram`, `rendering`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb375f02-a71a-47c9-ae7a-093f1e745985.jsonl`
- `/ll:format-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9758ffe9-ca61-495a-8a6e-a093a200b26b.jsonl`
- `/ll:refine-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c8e431c-a142-441d-87b6-09c026581cf6.jsonl`

---

## Status

**Open** | Created: 2026-03-08 | Priority: P2
