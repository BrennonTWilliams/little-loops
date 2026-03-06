# BUG-598: FSM diagram off-path states stack vertically instead of side-by-side

## Summary

`ll-loop show fix-quality-and-tests` rendered a broken diagram where the `fix-tests` box appeared far below its expected position and disconnected from the vertical connector arrows. When two off-path states (e.g., `fix-quality` under `check-quality` and `fix-tests` under `check-tests`) both exist, they stacked vertically instead of appearing side-by-side at the same depth. A secondary bug drew a dangling right-going arrow for `fix-tests → check-quality (next)`, which targets a main-path state to the LEFT of the off-path box.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Function**: `_render_2d_diagram()`
- **Lines**: 664–822 (off-path state rendering section)

The rendering loop processed each off-path state sequentially, appending connector rows then box rows to `lines` for each state independently. With two off-path states having different connector heights (4 rows for `fix-quality` with bidirectional edges, 3 rows for `fix-tests` with down-only edges), their boxes landed at different vertical positions.

Concrete stacking bug:
```
row N+1:  self-loop row
row N+2..N+5:  fix-quality connectors (4 rows)
row N+6..N+9:  fix-quality box
row N+10..N+12: fix-tests connectors ← 8 rows below main, not adjacent
row N+13..N+16: fix-tests box        ← far below check-tests
```

Secondary bug: `fix-tests → check-quality (next)` has `target_col < start_col` (target is LEFT), but the code drew `─next──▶` from the right, producing a dangling arrow with no visible target.

## Fix

### Primary fix — shared grid with bottom-aligned connectors

Replaced the sequential loop with a two-phase approach:

**Phase 1**: Pre-compute specs for all off-path states (anchor, edge classification, connector row count `n_conn`) without writing any rows.

**Phase 2**: Create a single shared `off_grid` of height `max_conn_h + max_box_h`. Each off-path state renders its connectors bottom-aligned (`conn_offset = max_conn_h - n_conn`) so all `▼` arrows land on the same row immediately above the box tops. All boxes start at `max_conn_h` — same row for every off-path state.

Result: `fix-quality` (n_conn=4, conn_offset=0) and `fix-tests` (n_conn=3, conn_offset=1) both have their `▼` on row 3 and their box tops on row 4.

### Secondary fix — left-going outgoing edges

Added a `elif target_col < start_col:` branch that draws `◄──next─` at the left edge of the box instead of a right-going arrow into empty space.

## Verification

```
  ┌───────────────────────────┐             ┌───────────────────────┐             ┌────────┐
  │ → check-quality  [prompt] │───success──▶│ check-tests  [prompt] │───success──▶│ done ◉ │
  └───────────────────────────┘             └───────────────────────┘             └────────┘
            ↺ partial                               ↺ partial
               │ ▲
    fail/error │ │                                      │
               │ │ next                      fail/error │
               ▼ │                                      ▼
    ┌───────────────────────┐               ┌──────────────────────┐
    │ fix-quality  [prompt] │       ◄──next─│ fix-tests  [prompt]  │
    └───────────────────────┘               └──────────────────────┘
```

- Both off-path boxes appear at the same vertical depth
- `▼` on each is directly connected to its box top
- `fix-tests` shows `◄──next─` pointing left toward `check-quality`

## Tests

Added `test_multiple_off_path_states_same_depth` to `scripts/tests/test_ll_loop_display.py`:
- Asserts `fix-quality` and `fix-tests` name rows share the same line index
- Asserts `◄` appears on the `fix-tests` name row for the left-going cross-edge

All 57 tests in `test_ll_loop_display.py` pass; no regressions.
