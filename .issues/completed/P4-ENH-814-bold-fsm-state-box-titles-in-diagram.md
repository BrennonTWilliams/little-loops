---
id: ENH-814
type: ENH
priority: P4
status: backlog
discovered_date: 2026-03-19
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
---

# ENH-814: Bold FSM state box titles in diagram

## Summary

FSM state boxes in loop diagrams render their titles in normal weight text. Bolding the state name within each box would improve scanability and visual hierarchy.

## Current Behavior

State box titles (state names) in FSM loop diagrams are displayed in normal/regular font weight, making them visually indistinct from any label or metadata text within the box.

## Expected Behavior

State box titles are rendered in **bold**, making each state's name immediately prominent and easy to scan when reading the diagram.

## Motivation

When reviewing an FSM loop diagram, users first scan for state names to orient themselves. Bold titles create a clear visual hierarchy — state name stands out from other text — reducing the time needed to parse the diagram structure.

## Proposed Solution

The FSM diagram renderer uses a **custom ANSI terminal renderer** (not Mermaid or HTML). Bold is applied via `colorize(text, "1")` from `scripts/little_loops/cli/output.py:90`, where ANSI SGR code `1` = bold.

The fix is in `_draw_box()` at `layout.py:611-614`. Currently the non-highlighted path writes name row characters as plain text:
```python
else:
    for j, ch in enumerate(line):
        if col + 2 + j < col + width - 1:
            grid[r][col + 2 + j] = ch
```

The highlighted path (lines 604-610) already applies bold via `colorize(line, f"{highlight_color};1")`. The same pattern should be extended to non-highlighted states using `colorize(line, "1")` for the first content row (`i == 0`):

```python
elif i == 0:
    bold_line = colorize(line, "1")
    if col + 2 < total_width:
        grid[r][col + 2] = bold_line
    for j in range(1, len(line)):
        if col + 2 + j < col + width - 1:
            grid[r][col + 2 + j] = ""
else:
    for j, ch in enumerate(line):
        if col + 2 + j < col + width - 1:
            grid[r][col + 2 + j] = ch
```

**Important**: Bold must NOT be applied to `display_label` before `_draw_box` — `_compute_box_sizes()` at `layout.py:494` uses `len(display_label[s])` at line 518 for box width, and ANSI escape bytes would corrupt box sizing.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — primary change: `_draw_box()` at lines 604-614 (the `else` branch for non-highlighted name rows)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:644` — calls `_render_fsm_diagram()` for `ll-loop show`
- `scripts/little_loops/cli/loop/_helpers.py:319-324` — calls `_render_fsm_diagram()` for live diagram display during `ll-loop run --show-diagrams`

### Supporting Utilities
- `scripts/little_loops/cli/output.py:90` — `colorize(text, code)` utility; `colorize(text, "1")` = bold only

### Similar Patterns
- `layout.py:605` — existing bold pattern: `colorize(line, f"{highlight_color};1")` for highlighted states
- `layout.py:604-610` — full highlighted-state name row block to mirror for non-highlighted states

### Tests
- `scripts/tests/test_ll_loop_display.py` — `TestRenderFsmDiagram` class (line 639); ANSI color tests (lines 1213–1264); add new test asserting `"\033[1m"` appears in non-highlighted state name rows when `_USE_COLOR=True`

### Documentation
- `docs/reference/OUTPUT_STYLING.md` — FSM diagram rendering section (line 134); may need a note about bold state titles

## Implementation Steps

1. Modify `_draw_box()` in `layout.py:604-614` — in the `else` branch, split the first row (`i == 0`) to call `colorize(line, "1")` and write it as a single grid cell (same pattern as highlighted path at lines 604-610)
2. Add a test in `test_ll_loop_display.py` patching `_USE_COLOR=True` and asserting `"\033[1m"` appears in non-highlighted state name rows (model after lines 1213-1243)
3. Run `python -m pytest scripts/tests/test_ll_loop_display.py -v` to confirm no regressions

## Impact

- **Scope**: Diagram rendering only; no change to loop logic or YAML format
- **Users**: Anyone viewing FSM loop diagrams during development or debugging
- **Risk**: Low — visual-only change

## Related Key Documentation

N/A

## Labels

`diagram`, `fsm`, `visualization`, `ux`

## Session Log
- `/ll:ready-issue` - 2026-03-19T17:14:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8885b6c6-b523-4aca-887d-d1c1d2e74574.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e1709cc-3da4-40dd-ac67-c9dfe86a860b.jsonl`
- `/ll:refine-issue` - 2026-03-19T16:49:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e80258f6-4af5-48f4-ac62-be9934b1952f.jsonl`
- `/ll:capture-issue` - 2026-03-19T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e80258f6-4af5-48f4-ac62-be9934b1952f.jsonl`
- `/ll:manage-issue` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Resolution

- **Status**: completed
- **Completed**: 2026-03-19
- **Changes**:
  - Modified `_draw_box()` in `layout.py:611-614` to bold non-highlighted state name rows via `colorize(line, "1")`
  - Added `test_non_highlighted_state_name_bold` test in `test_ll_loop_display.py`
- **Verification**: 3715 tests passed, lint clean

## Status

- **Current**: completed
