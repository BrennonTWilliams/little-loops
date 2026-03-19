---
id: ENH-813
type: ENH
priority: P4
status: backlog
discovered_date: 2026-03-19
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-813: Color-code transition lines in FSM loop diagrams

## Summary

FSM loop diagrams currently render all transition lines (edges) in a uniform style. Color-coding these lines by transition type or outcome would make diagrams easier to read at a glance.

## Current Behavior

All transition arrows in FSM loop diagrams are rendered with the same color/style, regardless of whether they represent success paths, error paths, retry paths, or normal flow transitions.

## Expected Behavior

Transition lines are color-coded to convey semantic meaning — for example:
- **Green**: success / happy-path transitions
- **Red/orange**: error or failure transitions
- **Yellow/amber**: retry transitions
- **Gray/blue**: normal/default flow transitions

Colors should match or complement the existing state highlight colors used when a state is active.

## Motivation

When reviewing loop execution history or debugging a loop, engineers scan the diagram to understand the flow. Uniform transition styling forces users to read edge labels to understand the path type. Color-coded transitions make success and error paths immediately visually distinct, reducing cognitive load.

## Proposed Solution

Infer transition semantics from the `next_state` label or edge metadata (e.g., `on_success`, `on_error`, `on_retry` keys in the loop YAML). Apply a color mapping to Mermaid edge styles or equivalent diagram renderer styling.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — ALL diagram rendering logic (1555 lines); this is the only file to change

### Key Functions
- `_EDGE_LABEL_COLORS` at `layout.py:25` — existing color mapping for edge labels ("yes"→green, "no"→orange, "error"→red, "partial"→amber, "next"/"_"→dim); extend with any missing transition types
- `_colorize_label()` at `layout.py:35` — colorizes compound label strings (e.g. "no/error"); used for label text only
- `_colorize_diagram_labels()` at `layout.py:52` — regex post-pass that colorizes known label words in the final diagram string; called at `layout.py:1363` and `layout.py:1555`
- `_collect_edges()` at `layout.py:155` — builds `(src, dst, label)` tuples from `on_yes`, `on_no`, `on_error`, `on_partial`, `next`, `route` verdicts; **note**: `on_blocked` and `on_retry_exhausted` are NOT currently collected here
- `_render_layered_diagram()` at `layout.py:616` — draws inter-layer arrows and back-edges on a character grid; draws lines at `layout.py:996–1083`
- `_render_horizontal_simple()` at `layout.py:1472` — simple horizontal renderer for ≤1-state FSMs

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:16–22` — imports `_colorize_diagram_labels`, `_colorize_label`, `_EDGE_LABEL_COLORS`, `_render_fsm_diagram` from layout; calls `_render_fsm_diagram(fsm, verbose=verbose)` at `info.py:644`
- `scripts/little_loops/cli/loop/_helpers.py:321–324` — calls `_render_fsm_diagram(fsm, highlight_state=state, highlight_color=highlight_color)` on every `state_enter` event when `ll-loop run --show-diagrams` is active

### Similar Patterns
- State box highlight color: `layout.py:515–608` (`_draw_box()`) — uses a `_bc()` closure that calls `colorize(ch, highlight_color)` for each border character when `is_highlighted=True`; exact same `colorize()` from `little_loops.cli.output` can be used for line characters
- Priority/type color maps: `scripts/little_loops/cli/output.py:33–45` — `PRIORITY_COLOR` and `TYPE_COLOR` dicts follow the same `{key: "ANSI_SGR_code"}` pattern as `_EDGE_LABEL_COLORS`
- Brand semantic colors: `diagram-tokens.json` — Sage Green `#85B990` = success/valid, Rose/Pink `#E0989E` = error/failed, Mustard Yellow `#E8C868` = pending/retry — these align with existing `_EDGE_LABEL_COLORS` choices

### Tests
- `scripts/tests/test_ll_loop_display.py` — existing display tests; line 1259 explicitly notes "No ANSI codes in box chars (edge labels may add color but not box borders)"
- Color assertion pattern: `test_ll_loop_display.py:1213–1230` — patches `output_mod._USE_COLOR = True`, then asserts `"\033[36m"` and `"\033[36;1m"` in result; new edge line color tests follow the same `patch.object(output_mod, "_USE_COLOR", True)` convention
- State factory helper at `test_ll_loop_display.py:53–73` can be reused for new tests

### Configuration
- `config-schema.json:~826` — `fsm_active_state` field is the model for adding an edge color config key (e.g., `fsm_edge_colors`) if per-type configurability is desired; optional, not required for this enhancement
- `scripts/little_loops/cli/loop/run.py:153` — reads `BRConfig(Path.cwd()).cli.colors.fsm_active_state` and passes to `_render_fsm_diagram` as `highlight_color`

### Documentation
- `docs/reference/OUTPUT_STYLING.md:134–198` — documents `_render_fsm_diagram` structure; lines 182–184 explicitly describe the existing "Edge label colorization" section; lines 50–58 list current label color codes in a table — will need update after this enhancement

## YAML Transition Key Clarification

The issue mentions `on_success`, `on_error`, `on_retry` but the actual schema fields differ:
- `on_success` in YAML → aliased to `on_yes` at `schema.py:295` (not a distinct field)
- `on_failure` in YAML → aliased to `on_no` at `schema.py:296`
- **There is no `on_retry` key** — retry is handled via `max_retries` (int) + `on_retry_exhausted` (state name) at `schema.py:228–229`

Full transition field set in `StateConfig` (`schema.py:218–229`):
`on_yes` (→"yes"), `on_no` (→"no"), `on_error` (→"error"), `on_partial` (→"partial"), `on_blocked` (→"blocked"), `next` (→"next"), `route.routes` (→verdict string), `route.default` (→"_"), `on_retry_exhausted` (→"retry_exhausted")

## Clarification: What's Already Done vs. What's Missing

**Already implemented (label text colorization):**
- `_EDGE_LABEL_COLORS` maps "yes"→green, "no"→orange, "error"→red, "partial"→amber, "next"/"_"→dim
- `_colorize_diagram_labels()` post-processes the final diagram string, applying color to label words (e.g. the word "error" in a transition label)
- `_colorize_label()` colorizes individual label strings

**Not yet implemented (the actual enhancement):**
- The transition **line characters** themselves (│ pipes, ─ dashes, └ ┐ corner connectors, ▼ ▲ arrowheads) are written to a `list[list[str]]` grid as plain characters with no ANSI wrapping
- `_colorize_diagram_labels()` only matches label _words_; the regex `(?<=[─ │▶\n])label(?=[─ │▶\n])` colorizes the word "error" but leaves the surrounding `─`, `│`, `▼` characters uncolored
- Back-edge routing at `layout.py:1145–1310` (margin back-edges) has the same issue

## Implementation Steps

1. **Define edge semantic type helper** in `layout.py`: Map a label string to one of `{success, error, retry, default}` — e.g., "yes" → success, "no"/"error"/"blocked" → error, "partial" → retry, "next"/"_"/unknown → default
2. **Extend `_EDGE_LABEL_COLORS`** to cover missing transition types: add "blocked" (red, same as error), "retry_exhausted" (red/orange), any custom route verdicts get "default" treatment
3. **Update `_collect_edges()` at `layout.py:155`** to also collect `on_blocked` → "blocked" and `on_retry_exhausted` → "retry_exhausted" edges (currently omitted)
4. **Colorize line characters at draw time** in `_render_layered_diagram()` across all three drawing sections:
   - Forward inter-layer edges `layout.py:978–1083`: pipe chars at 1039, arrow tips at 1043, horizontal connectors at 1014–1031, label text at 1049–1051
   - Same-layer horizontal edges `layout.py:1085–1149`: edge text string at 1110/1132, written char-by-char at 1119–1127/1141–1149
   - Back-edge margin edges `layout.py:1151–1249`: vertical lines at 1181–1187, horizontal connectors at 1194–1226, corner chars at 1229–1237, arrow tips at 1240–1241, labels at 1244–1248
5. **Propagate label→color mapping** — the edge label is already available in the drawing loop at `layout.py:997` (`for src, dst, label in inter_edges`); derive ANSI code via `_EDGE_LABEL_COLORS.get(label.split("/")[0])` and wrap each character with `colorize(ch, code)` using the same `_bc()`-closure pattern from `_draw_box()`
6. **Update `_colorize_diagram_labels()` or remove it**: once line characters are colored at draw time, the post-pass regex approach may become redundant for labels too — evaluate whether to keep both or merge
7. **Update test** at `test_ll_loop_display.py:1259` which asserts NO ANSI in box chars — still correct; add complementary tests asserting color IS present on transition connectors using `patch.object(output_mod, "_USE_COLOR", True)` convention from `test_ll_loop_display.py:1213–1230`
8. **Update `docs/reference/OUTPUT_STYLING.md:50–58`** — the color table and section description need updating to reflect that line characters are also colored, not just labels

## Impact

- **Scope**: Diagram rendering only; no change to loop logic or YAML format
- **Users**: Anyone viewing FSM loop diagrams during development or debugging
- **Risk**: Low — visual-only change

## Impact

- **Scope**: Diagram rendering only; no change to loop logic or YAML format
- **Users**: Anyone viewing FSM loop diagrams during development or debugging
- **Risk**: Low — visual-only change

## Related Key Documentation

N/A

## Labels

`diagram`, `fsm`, `visualization`, `ux`

## Session Log
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c179030-87aa-47bd-98f0-dbd231f6dfc2.jsonl`
- `/ll:refine-issue` - 2026-03-19T16:50:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e80258f6-4af5-48f4-ac62-be9934b1952f.jsonl`
- `/ll:capture-issue` - 2026-03-19T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe93df18-9bd8-4ea2-b803-eb08b9798bc3.jsonl`

---

## Status

- **Current**: backlog
