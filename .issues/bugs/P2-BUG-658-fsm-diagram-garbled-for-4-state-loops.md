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
  ┌──────────┐        ┌────────┐
  │ evaluate │──────▶│  done  │
  └──────────┘        └────────┘
       │
       ▼
  ┌─────────┐
  │   fix   │
  └─────────┘
       │
       ▼
  ┌──────────────┐
  │ check_commit │
  └──────────────┘
       │
       ▼
  ┌────────┐
  │ commit │
  └────────┘
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
- **Function**: `_render_2d_diagram()` (line 463 — confirmed; dispatched from `_render_fsm_diagram()` at line 447)
- **Anchor**: Off-path / linear-chain state layout logic

The renderer appears to classify FSM states into "main path" and "off-path" buckets. With 4 non-terminal states in a linear chain (evaluate → fix → check_commit → commit → evaluate), the layout algorithm likely:
- Assigns `evaluate` to the main path (row 0)
- Fails to place `fix` at all (dropped)
- Attempts to place `check_commit` and `commit` as side-by-side off-path states but assigns them the same column, causing overlap

The column-assignment logic in the off-path rendering (fixed in BUG-598 for vertical stacking) does not account for the case where two states must occupy different columns AND different rows when both are in the linear fallback chain.

## Proposed Solution

1. **Detect missing states**: After layout assignment, verify that every non-terminal state is assigned a grid cell. Any unplaced state is a rendering bug.
2. **Ensure unique columns for co-depth off-path states**: Extend the `off_grid` column-assignment logic (introduced in BUG-598) to prevent two states from sharing the same column when they are at different depth levels in the chain.
3. **Regression test**: Add a test with the `issue-refinement-git` YAML (or a minimal 4-state equivalent) asserting that all 4 state names appear in the diagram output and that no state label is split by a box border.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `_render_2d_diagram()` (line 463), off-path state layout and column assignment

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py` — `_render_fsm_diagram()` (line 358) dispatches to `_render_2d_diagram()`

### Tests
- `scripts/tests/test_loop_info.py` (if it exists) — add regression test for 4-state FSM diagram
- Check `scripts/tests/` for existing diagram rendering tests to understand the test fixture pattern

### Similar Patterns
- BUG-598 (`P3-BUG-598-fsm-diagram-off-path-states-stack-vertically-instead-of-side-by-side.md`) — Fixed vertical stacking of off-path states using a shared `off_grid` with bottom-aligned connectors
- BUG-445 (`P3-BUG-445-fsm-diagram-non-main-edges-rendered-as-text-not-2d.md`) — Fixed non-main edges rendered as text

### Documentation
- N/A — internal rendering function, no user-facing docs

### Configuration
- N/A

## Implementation Steps

1. Run `ll-loop show issue-refinement-git` and capture the raw output to understand exact corruption
2. Add a debug mode or trace to `_render_2d_diagram()` to print the state→cell assignment map
3. Identify why `fix` is unplaced (likely: path-finding logic stops after the first off-path branch)
4. Identify why `check_commit` and `commit` share a column (likely: column counter is not incremented for each new off-path state)
5. Fix the path-finding to collect all reachable states, not just the first off-path branch
6. Fix column assignment to allocate distinct columns for each off-path state
7. Add regression test using `issue-refinement-git.yaml` or equivalent 4-state fixture

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

---

## Status

**Open** | Created: 2026-03-08 | Priority: P2
