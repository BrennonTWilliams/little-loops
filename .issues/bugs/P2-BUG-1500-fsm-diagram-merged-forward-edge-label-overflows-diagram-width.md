---
id: BUG-1500
type: BUG
priority: P2
status: done
captured_at: '2026-05-16T14:12:59Z'
completed_at: '2026-05-17T13:27:45Z'
discovered_date: '2026-05-16'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Dual-mechanism bug**: the `label_start + j < total_width` guard at line 1115 prevents array out-of-bounds writes but does NOT prevent the label from overwriting box-border characters (`╔`, `═`, `╗`, `│`) at columns occupied by adjacent state boxes in the same row. Unlike same-layer edges (lines 1187, 1191-1196), the forward-edge label writer has no `_box_occ` check. Characters landing inside `total_width` but on occupied box columns are written unconditionally.
- **Correct clamp boundary**: `total_content_w` (computed at `layout.py:976`, the rightmost column of any box) is the natural right boundary for forward-edge labels. `total_width` (line 981) frequently equals terminal width `tw`, not the content area — clamping to `total_width` alone leaves the label free to overwrite box content between `total_content_w` and `tw`.
- **Multiple merge sites**: `"/" + lbl` concatenation occurs at lines 758-759, 770, 861, 868, and 893 (back-edge reclassification and same-layer passes). The clamp should be applied at the single write site (lines 1110-1116), not at each merge site.
- **`right_edge_margin` gap**: at lines 970-974, `right_edge_margin` is set for skip-layer forward edges only. Consecutive-layer forward edges (the bug's case) get no right-margin reservation, so `total_width` is not inflated to accommodate them.

## Proposed Solution

Two complementary changes (smallest fix first):

1. **Render-time clamp (minimal)**: at the write site (`layout.py:1110-1116`), clamp `label` to `total_width - label_start` characters and append `…` if truncated. This ~5-line change restores the right edge immediately.
2. **Wrap or summarize long labels**: if `len(label) > max_label_width` (e.g. `30` or `box_width[dst] * 2`), wrap across multiple rows in the arrow gap (currently 3 rows: `│`, label, `▼` at `layout.py:998`), widening the gap to fit. Alternatively, compress N labels into a count like `5 outcomes`. Match the `"/"` join convention from `_compact_transitions` (`info.py:538`).
3. **Size layers to fit**: when computing `gap_between` for adjacent layers, grow it by `ceil(label_len / available_w)` extra rows. Factor merged-label width into `total_width` computation so the right margin doesn't get clipped.

Defer the multi-line wrap until the simple clamp is in place and ellipsis is confirmed acceptable.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Clamp boundary**: use `total_content_w` (available at `layout.py:976`) as the right boundary, not `total_width`. The correct guard at the write site: `label_start + j < total_content_w` (mirrors the back-edge dual-bound pattern at lines 1317-1323 with `content_left - 1`).
- **Truncation pattern**: `label = label[: max_label - 1] + "…"` before the write loop, where `max_label = total_content_w - label_start`. This matches the `_box_inner_lines()` convention at lines 181-186 and the `info.py:_truncate()` helper (line 200-206).
- **No merge-site changes needed**: all three proposed options require changes only at the write site (lines 1110-1116) or at sizing (lines 970-981); the "/" merge sites (lines 758-759, 770, 861, 868, 893) are unchanged.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — forward edge label writer in `_render_layered_diagram` (clamp/wrap logic); layer/gap sizing helpers

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py` — `_compact_transitions` produces the merged `/`-joined labels consumed by `layout.py`
- `ll-loop show` CLI entry point — renders the diagram via `_render_layered_diagram`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py` — calls `_render_fsm_diagram()` at lines 410 and 427 inside `run_foreground()`; this is the `ll-loop run --show-diagrams` code path (separate from `ll-loop show`). Verify no regression on this path after the fix. [Agent 1 finding]
- `scripts/little_loops/cli/issues/clusters.py` — imports `_draw_box` from `layout` at line 121 inside `_render_cluster_diagram()`; not in the forward-edge label path but is an importer of the modified module — confirm `_draw_box` signature is unchanged. [Agent 1 finding]

### Similar Patterns
- `_compact_transitions` (`info.py:538`) — owns the `"/"` join convention; any summarization (e.g. `"5 outcomes"`) should be applied consistently here
- Other label-writing paths in `layout.py` (back-edge labels) that may have similar overflow assumptions

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Best fix model — back-edge label writer** (`layout.py:1317-1323`): uses a dual bound check `label_start + j < content_left - 1 AND label_start + j < total_width` — the only existing label writer that clamps to a logical content-area boundary rather than just the grid edge. Forward-edge fix should mirror this pattern, clamping to `total_content_w` instead of `content_left - 1`.
- **Reusable truncation helper** (`info.py:_truncate()`, line 200-206): standalone helper with the exact pattern `text[: max_len - 1] + "…"`. Consider importing or inlining this pattern at the write site.
- **`…` ellipsis already established**: `_box_inner_lines()` at `layout.py:181-186` uses `first[: inner_width - 1] + "…"` — the convention is consistent across the renderer; the fix should use `…` (not `"..."`).
- **Skip-layer writer as structural reference** (`layout.py:1420-1426`): same `for j, ch in enumerate(label): if label_start + j < total_width` idiom as the forward-edge writer but has proper margin reservation via `right_edge_margin`. Forward-edge writer needs equivalent content-area clamping added before this loop.

### Tests
- `scripts/tests/test_ll_loop_display.py` — add a fan-out fixture and assert (a) no rendered line exceeds `total_width`, (b) box-border characters on adjacent rows remain intact

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_commands.py` — `TestLoopShow.test_show_displays_diagram` (line 1289) and `test_diagram_section_before_states_section` (line 1833) exercise `ll-loop show` end-to-end via CLI argv; they assert only section-header presence, not line lengths, so they are unlikely to break but should be confirmed green after the fix. [Agent 3 finding]
- **Tests that may catch regressions** (no update expected, but confirm green):
  - `TestRenderFsmDiagram.test_terminal_width_no_overflow` (line 1440) — ANSI-stripped line-length guard for 80-col terminal; won't reproduce BUG-1500 topology but will catch any new overflow introduced by the fix
  - `TestRenderFsmDiagram.test_issue_refinement_git_topology` (line 909) — asserts `│`-border integrity via `re.findall(r"│[a-zA-Z]", ln)` garbled-label guard; uses a merged `no/error` back-edge label (different topology) but will catch if the fix corrupts adjacent box-border rows

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Test class**: `TestRenderFsmDiagram` at `test_ll_loop_display.py:640` — all diagram regression tests live here; use the `_make_fsm()` class-level helper and call `_render_fsm_diagram(fsm)` (not `_render_layered_diagram` directly).
- **Test methods to model after**: `test_branching_fsm_shows_branches_section` (~line 693) for a two-target fan-out, `test_inter_layer_offset_edge_draws_horizontal_connector` (~line 1066) for same-layer-pair multi-edge topology.
- **Assert pattern**: `lines = result.split("\n")` → check `all(len(ln) <= total_width for ln in lines)` and verify box-border rows with `"│"` (│) are intact after the label row.

### Documentation
- N/A — internal renderer change; no user-facing docs reference the label-truncation behavior

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/OUTPUT_STYLING.md` — Section "FSM Diagram: `scripts/little_loops/cli/loop/layout.py`" → "Edge arrows" subsection documents forward-edge label format; currently has no statement about label-width bounds. If `…` truncation is shipped as user-visible behavior, add a sentence noting that merged labels exceeding available width are truncated with `…`. [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Add render-time clamp at the forward edge label writer (`layout.py:1110-1116`) bounding `label` to `total_width - label_start` characters with an `…` suffix when truncated.
2. Extend `total_width` / `gap_between` calculations so layer sizing factors merged-label length (prevents future regressions when ellipsis is undesirable).
3. (Optional follow-up) Implement multi-row wrap inside the arrow gap (currently 3 rows at `layout.py:998`) for very long merged labels.
4. Add a regression test in `scripts/tests/test_ll_loop_display.py` exercising a ≥5-way merged label — place in `TestRenderFsmDiagram` (line 640), use `_make_fsm()` helper, call `_render_fsm_diagram(fsm)`, model after `test_branching_fsm_shows_branches_section` (~line 693).
5. Verify visually with `ll-loop show eval-specfile-gold` and confirm line 51 and adjacent rows render cleanly.

## Steps to Reproduce

1. `cd ~/AIProjects/ai-workspaces/blender-agents`
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

## Resolution

Fixed in `scripts/little_loops/cli/loop/layout.py` with two complementary changes:

1. **Consecutive-layer forward edge writer** (`layout.py:1110-1122`): When skip-layer forward edges exist, their vertical pipes occupy the right margin starting at `total_content_w + 2`. The consecutive-layer label now clamps to `total_content_w` to avoid overwriting those pipes. When no skip-layer edges exist, the full `total_width` is available as before.

2. **Skip-layer forward edge writer** (`layout.py:1428-1438`): The label is now truncated to `total_width - label_start` characters with a `…` suffix when it exceeds the available space, signaling to users that the label is truncated rather than silently cutting it off.

Regression test added in `scripts/tests/test_ll_loop_display.py::TestRenderFsmDiagram::test_fanout_merged_label_truncated_with_ellipsis` — exercises a ≥5-way merged label, asserts `…` appears, full label absent, and no garbled box-border characters.

## Session Log
- `/ll:manage-issue` - 2026-05-17T13:27:45Z
- `/ll:ready-issue` - 2026-05-17T13:05:53 - `43f5a50f-8ebf-40e9-9a4b-9c36cd7a4146.jsonl`
- `/ll:confidence-check` - 2026-05-17T17:00:00Z - `be08bb09-f628-4cdc-a13b-bcc5cd3d0635.jsonl`
- `/ll:decide-issue` - 2026-05-17T13:01:05 - `87cf1c66-23f6-46ca-b0e5-54b6bd7ec919.jsonl`
- `/ll:confidence-check` - 2026-05-17T14:00:00 - `81bff7e6-c514-4851-970c-0e6cc21a2290.jsonl`
- `/ll:wire-issue` - 2026-05-17T12:53:31 - `ed17fe11-2dda-41a7-bceb-a7ce36fa6817.jsonl`
- `/ll:refine-issue` - 2026-05-17T12:48:25 - `56c7387f-d7b7-4bb7-9b1a-6edb421fdce8.jsonl`
- `/ll:format-issue` - 2026-05-16T14:38:56 - `8f6573c2-17a9-4c6c-8f79-00628f832a5a.jsonl`
- `/ll:capture-issue` - 2026-05-16T14:12:59Z - `f204025d-307a-4f4d-80b2-206dfd3b1de1.jsonl`
