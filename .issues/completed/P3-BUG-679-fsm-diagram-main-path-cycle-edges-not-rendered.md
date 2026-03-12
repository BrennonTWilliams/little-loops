---
discovered_date: 2026-03-12
discovered_by: capture-issue
confidence_score: 100
resolved: true
resolved_date: 2026-03-12
---

# BUG-679: FSM diagram main-path cycle edges not rendered

## Summary

Main-path edges that form cycles (e.g. `commit → count_baseline` via `next`) are silently dropped by the FSM diagram renderer. The edge exists in `forward_edge_labels` but no rendering path handles it because: (1) the inter-layer renderer only draws consecutive-layer edges, and (2) the reclassification block only scans `back_edges`, not `forward_edge_labels`.

## Steps to Reproduce

1. Define a loop where the main path cycles back to the initial state (e.g. `issue-discovery-triage.yaml`: `commit` has `next: count_baseline`)
2. Run `ll-loop s issue-discovery-triage`
3. Observe: no arrow from `commit` back to `count_baseline`

## Current Behavior

The `commit` box has no outgoing arrow — the cycle is invisible. The diagram looks like a dead-end at `commit`.

## Expected Behavior

A left-margin back-edge arrow from `commit → count_baseline` with the "next" label, similar to how `back_edges` are rendered.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Anchor**: in `_render_layered_diagram()`, `_classify_edges()` and reclassification block
- **Cause**: `_classify_edges()` classifies `commit → count_baseline` as a main edge. It enters `forward_edge_labels` but never enters `back_edges`. The reclassification block (line ~692) only iterates `back_edges`, so this backward-pointing main edge is never moved to `back_edge_labels_reclass`. The inter-layer renderer only handles consecutive layers, so it's skipped there too.

## Proposed Solution

Two-part fix applied:

1. **Conservative margin estimate**: Pre-compute `prelim_layer_of` from `layers` before column layout. Scan `forward_edge_labels` for backward-pointing edges and include them in `back_edge_margin` calculation so column positions are correct from the start.

2. **Extended reclassification**: After the existing `back_edges` reclassification loop, scan `forward_edge_labels` for entries where `dst_layer < src_layer`. Move these to `back_edge_labels_reclass` (and remove from `forward_edge_labels`) so they get rendered as left-margin back-edges.

## Impact

- **Priority**: P3 - Diagram misleading but state table shows correct transitions
- **Effort**: Small - Fix is localized to reclassification block
- **Risk**: Low - Only affects edges that were previously invisible
- **Breaking Change**: No

## Labels

`diagram`, `rendering`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4cb1a514-1752-4f1f-9c34-c6be12fca682.jsonl`
- `/ll:verify-issues` - 2026-03-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ce22b31f-c86d-405e-81b7-51f36fa9812d.jsonl` — Moved to completed/ (fix in commit 564df03; frontmatter already marked resolved)

---

## Status

**Completed** | Created: 2026-03-12 | Resolved: 2026-03-12 | Priority: P3
