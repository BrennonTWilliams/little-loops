# ENH-813: Color-code transition lines in FSM loop diagrams

**Date**: 2026-03-19
**Issue**: ENH-813
**Action**: improve

## Summary

Color-code FSM diagram transition **line characters** (│ pipes, ─ dashes, corner connectors, ▼▶ arrowheads) to match the semantic color of their edge label. Label text colorization already exists via `_colorize_diagram_labels()`; the enhancement extends colorization to the connector characters themselves.

## Design

### Single helper function

Add `_edge_line_color(label: str) -> str` that maps a (possibly compound) label string to an ANSI code. Logic mirrors the priority cascade in `_colorize_label()`:

```
"no" or "error" or "blocked" or "retry_exhausted" → red/orange (error family)
"partial" → amber
"yes"     → green
"next" or "_" or unknown → dim
```

Return the code (or `""` for no color). Use `colorize(ch, code)` on each grid character at draw time.

### Changes to layout.py

1. **`_EDGE_LABEL_COLORS`** — add `"blocked": "31"` (red, same as error) and `"retry_exhausted": "38;5;208"` (orange, same as no).

2. **`_collect_edges()`** — append `on_blocked → "blocked"` and `on_retry_exhausted → "retry_exhausted"` edges (currently omitted).

3. **New `_edge_line_color(label: str) -> str`** helper after `_colorize_label`.

4. **`_render_layered_diagram()`** — colorize at draw time in all four sections:
   - Forward inter-layer edges (lines ~1002–1051): wrap `─`, `┘`, `┌`, `│`, `▼`, `┐`, `└` chars with `colorize(ch, code)` derived from `label`.
   - Same-layer horizontal edges (lines ~1097–1149): construct `edge_text` using colored characters.
   - Back-edge margin edges (lines ~1151–1249): wrap `│`, `─`, corner chars, `▶` with `colorize(ch, code)`.
   - Skip-forward right-margin edges (lines ~1263–1348): same as back-edge.

5. **`_colorize_diagram_labels()`** — keep as-is; it still colorizes label words. At draw time the line chars are already colored, so this remains complementary.

### Changes to test_ll_loop_display.py

Add a new test class `TestEdgeLineColorization` (or append to existing `TestHighlightState` class) with:

- `test_error_edge_lines_are_red`: FSM with `on_error`, patch `_USE_COLOR=True`, assert `"\033[31m"` appears in the result (pipe/arrow chars colored red).
- `test_yes_edge_lines_are_green`: FSM with `on_yes`, assert green (`\033[32m`) on transition chars.
- `test_no_edge_lines_are_orange`: FSM with `on_no`, assert orange.
- `test_blocked_edge_lines_are_red`: FSM with `on_blocked`, assert red.
- `test_retry_exhausted_edge_lines_are_orange`: FSM with `on_retry_exhausted`, assert orange.
- `test_no_color_when_disabled`: Without patching `_USE_COLOR=True`, no ANSI codes in transition chars.

### Changes to docs/reference/OUTPUT_STYLING.md

Update the edge label color table (lines ~50-58) to:
- Fix `success` → `yes`, `fail` → `no` (existing table uses wrong key names)
- Add `blocked` (red) and `retry_exhausted` (orange)
- Note that colors apply to both label text AND line characters

## Implementation Steps

- [x] Write plan
- [ ] Phase 0 (TDD Red): Write failing tests
- [ ] Phase 1: Extend `_EDGE_LABEL_COLORS` + `_collect_edges()`
- [ ] Phase 2: Add `_edge_line_color()` helper
- [ ] Phase 3: Colorize forward inter-layer edges
- [ ] Phase 4: Colorize same-layer horizontal edges
- [ ] Phase 5: Colorize back-edge margin edges
- [ ] Phase 6: Colorize skip-forward right-margin edges
- [ ] Phase 7: Update `OUTPUT_STYLING.md`
- [ ] Phase 8: Run tests (green), lint, type-check
