---
id: BUG-1500
type: BUG
priority: P2
status: open
captured_at: "2026-05-16T14:12:59Z"
discovered_date: "2026-05-16"
discovered_by: capture-issue
---

# BUG-1500: FSM diagram merged forward-edge label overflows diagram width and breaks adjacent boxes

## Summary

When several transitions share the same `(src, dst)` pair, their labels are merged with `/` (e.g. five outcomes → `system_problem/max_rounds_exhausted/degrade_give_up/retry_flood/blender_5_incompatible`, ~80 chars). The forward-edge label writer in `_render_layered_diagram` writes this label past the right edge of the diagram, breaking the surrounding box characters. Visible in the `eval-specfile-gold` loop diagram on `investigate_failure → create_issue`.

## Current Behavior

Line 51 of the rendered diagram contains an 80-character merged label written into the box region of adjacent layers, corrupting the right margin and box borders.

## Expected Behavior

Merged labels should be truncated, wrapped, or summarized so they fit within the gap between source and destination layers, leaving box borders and the diagram's right edge intact.

## Motivation

`ll-loop show` is the primary tool authors use to read and debug FSM loops; a corrupted diagram undermines that purpose. The bug reproduces on a shipped loop (`eval-specfile-gold`), so any user with a fan-out state — common when an `investigate_failure`-style node has many failure outcomes — sees broken box borders and misaligned columns, making the diagram unreadable in exactly the cases where it would be most useful.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Anchor**: forward edge label writer at `layout.py:1110-1116`; layer/gap sizing at `layout.py:977-981` and `layout.py:998` (the `y += 3` arrow gap); label merging via `"/" + lbl` concatenation at `layout.py:759`.
- **Cause**: Forward labels are emitted character-by-character starting at `label_start = dst_cc + 2` with only a `total_width` bound check. Neither layer sizing nor `back_edge_margin` measures the merged label length, so a 5-way merge collapses into one giant label that exceeds the available width.

## Proposed Solution

Two complementary changes (smallest fix first):

1. **Render-time clamp (minimal)**: at the write site (`layout.py:1110-1116`), clamp `label` to `total_width - label_start` characters and append `…` if truncated. This ~5-line change restores the right edge immediately.
2. **Wrap or summarize long labels**: if `len(label) > max_label_width` (e.g. `30` or `box_width[dst] * 2`), wrap across multiple rows in the arrow gap (currently 3 rows: `│`, label, `▼` at `layout.py:998`), widening the gap to fit. Alternatively, compress N labels into a count like `5 outcomes`. Match the `"/"` join convention from `_compact_transitions` (`info.py:538`).
3. **Size layers to fit**: when computing `gap_between` for adjacent layers, grow it by `ceil(label_len / available_w)` extra rows. Factor merged-label width into `total_width` computation so the right margin doesn't get clipped.

Defer the multi-line wrap until the simple clamp is in place and ellipsis is confirmed acceptable.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — forward edge label writer in `_render_layered_diagram` (clamp/wrap logic); layer/gap sizing helpers

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py` — `_compact_transitions` produces the merged `/`-joined labels consumed by `layout.py`
- `ll-loop show` CLI entry point — renders the diagram via `_render_layered_diagram`

### Similar Patterns
- `_compact_transitions` (`info.py:538`) — owns the `"/"` join convention; any summarization (e.g. `"5 outcomes"`) should be applied consistently here
- Other label-writing paths in `layout.py` (back-edge labels) that may have similar overflow assumptions

### Tests
- `scripts/tests/test_ll_loop_display.py` — add a fan-out fixture and assert (a) no rendered line exceeds `total_width`, (b) box-border characters on adjacent rows remain intact

### Documentation
- N/A — internal renderer change; no user-facing docs reference the label-truncation behavior

### Configuration
- N/A

## Implementation Steps

1. Add render-time clamp at the forward edge label writer (`layout.py:1110-1116`) bounding `label` to `total_width - label_start` characters with an `…` suffix when truncated.
2. Extend `total_width` / `gap_between` calculations so layer sizing factors merged-label length (prevents future regressions when ellipsis is undesirable).
3. (Optional follow-up) Implement multi-row wrap inside the arrow gap (currently 3 rows at `layout.py:998`) for very long merged labels.
4. Add a regression test in `scripts/tests/test_ll_loop_display.py` exercising a ≥5-way merged label.
5. Verify visually with `ll-loop show eval-specfile-gold` and confirm line 51 and adjacent rows render cleanly.

## Steps to Reproduce

1. `cd /Users/brennon/AIProjects/ai-workspaces/blender-agents`
2. `ll-loop show eval-specfile-gold`
3. Inspect line 51 — observe the merged label overflowing the right edge and the surrounding box borders corrupted.

## Impact

- **Priority**: P2 - Visual corruption of a diagnostic view; doesn't block execution but is the highest visual severity in the parent investigation plan and reproduces on a shipped loop.
- **Effort**: Small - The minimal clamp is ~5 lines at one write site in `layout.py`; full wrap/sizing changes are Medium.
- **Risk**: Low - Localized to the renderer's forward-edge label path; covered by `test_ll_loop_display.py` and visually verifiable via `ll-loop show`.
- **Breaking Change**: No

- **Affects**: Any FSM where a single source has many transitions to the same destination (fan-out collapse), e.g. multi-outcome `investigate_failure` states.
- **Workaround**: None at render time.

## Test Plan

Add a case in `scripts/tests/test_ll_loop_display.py`:

- Fixture: FSM with one source emitting ≥5 transitions (long labels) into the same destination.
- Assert the rendered diagram's lines do not exceed `total_width` and that box-border characters on adjacent rows are intact (e.g., regex match on `│ ... │` shape).
- If wrap is implemented: assert the label appears across consecutive rows in the arrow gap.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/cli/loop/layout.py` | Renderer under repair |
| `scripts/little_loops/cli/loop/info.py` | `_compact_transitions` (label-join convention to match) |
| `~/.claude/plans/investigate-the-fsm-loop-twinkly-bear.md` | Source investigation plan (Bug C) |

## Labels

- area:fsm-diagram
- area:renderer

## Status

- **Discovered**: 2026-05-16 via investigation plan against `eval-specfile-gold`
- **Captured by**: `/ll:capture-issue`

## Session Log
- `/ll:format-issue` - 2026-05-16T14:38:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f6573c2-17a9-4c6c-8f79-00628f832a5a.jsonl`
- `/ll:capture-issue` - 2026-05-16T14:12:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f204025d-307a-4f4d-80b2-206dfd3b1de1.jsonl`
