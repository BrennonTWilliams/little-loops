---
id: BUG-3411
type: BUG
title: 'll-issues clusters tree layout: arrow direction relative to hub, not semantic
  source'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-08'
captured_at: '2026-09-08T19:25:17Z'
---

# BUG-3411: ll-issues clusters tree layout: arrow direction relative to hub, not semantic source

## Summary

`ll-issues clusters` in the default `--layout tree` renders the same relationship type
(e.g. `blocked_by`) with opposite arrow glyphs depending on which endpoint of the edge
happens to be the tree's hub/root, even though the legend documents a single fixed
meaning per relationship type.

## Current Behavior

In the default `--layout tree`, `_annot()` computes each edge's arrow glyph relative
to which endpoint is the current tree-walk parent, not the edge's stored `from_id`/
`to_id` semantic direction. When the hub node is the `from_id` for one neighbor and
the `to_id` for another neighbor of the same relationship type, the arrow flips
between `→` and `←` for that same relationship type within one cluster render,
contradicting the fixed meaning documented in `_EDGE_MEANING`.

## Expected Behavior

The same relationship type should always render with the same arrow glyph, reflecting
the edge's fixed semantic direction (`from_id → to_id` as stored in frontmatter),
regardless of which node the tree layout picked as hub/root or which direction the
tree walk is traversing — matching the behavior `--layout list` already has.

## Motivation

`clusters` (default `--layout tree`) is meant to let a reader scan dependency
direction at a glance. A relationship glyph that flips depending on hub selection
undermines the documented legend and can lead a reader to misjudge dependency
direction between issues. It's rendering-only (frontmatter data is unaffected), but
it erodes trust in the tool's default, most-used view.

## Proposed Solution

Make the tree's arrow direction reflect the edge's fixed semantic direction (arrow
always points from `from_id` to `to_id` as stored) instead of direction-relative-to-parent:

```python
def _annot(parent: str, child: str) -> str:
    from_id, _to_id, rel = rel_of[frozenset({parent, child})]
    arrow = "→" if from_id == parent else "←"
    return f"{arrow} {colorize(rel, EDGE_COLOR.get(rel, '37'))}"
```

Derive the arrow from whether the *child* is `to_id`, independent of walk direction —
i.e. always show `from_id → to_id` semantics (e.g. render as `blocked_by →` when the
child is the target), or restructure the label to name both IDs explicitly (e.g.
`blocked_by ENH-3406`) so the same relationship type never flips glyphs within one
cluster. `_render_cluster_compact` (lines 148-177, `--layout list`) already renders
each node's edges from its own fixed perspective and can serve as the reference for
correct fixed-direction semantics.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/clusters.py` — `_annot()` (lines 210-214)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/clusters.py` — `_render_cluster_tree()` (calls `_annot()`, root selection at line 248)

### Similar Patterns
- `_render_cluster_compact()` (lines 148-177) already renders edges from each node's fixed perspective — use as the reference implementation, no change needed there

### Tests
- No dedicated test file exists for `clusters` tree rendering; add coverage (e.g. `scripts/tests/test_issues_cli.py` or a new `test_clusters_cli.py`) asserting the same relationship type renders with a consistent glyph across both neighbors of a hub

### Documentation
- N/A — legend text in `_EDGE_MEANING` already documents the intended fixed semantics; no doc change needed

## Program Design

### Signatures

- `_annot(parent: str, child: str) -> str` — unchanged signature; internal arrow-direction logic changes to key off `to_id` fixed semantics instead of `parent`

### Call Path

`_render_cluster_tree()` -> `_annot(parent, child)` -> `rel_of[frozenset({parent, child})]`

## Implementation Steps

1. Change `_annot()`'s arrow derivation to depend on the edge's stored `from_id`/`to_id`, not on which side is the current tree-walk `parent`
2. Verify against the repro case (`ENH-3407` hub with two `blocked_by` edges) that both render the same glyph
3. Add a regression test asserting consistent glyphs for a hub with edges on both sides of the same relationship type
4. Run `--layout list` alongside `--layout tree` on the same cluster to confirm both agree on direction

## Impact

- **Priority**: P3 - rendering-only bug in a diagnostic/reporting view; no data corruption, but reduces trust in the default cluster visualization
- **Effort**: Small - single-function fix in `_annot()`, no schema or data changes
- **Risk**: Low - isolated to tree-layout arrow rendering; `--layout list` and underlying frontmatter data are unaffected
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-08 | Priority: P3

## Steps to Reproduce

1. In a repo with a cluster where the hub node is the `from_id` for one edge and the `to_id` for another edge of the same relationship type (e.g. `blocked_by`), run `ll-issues clusters` (default `--layout tree`).
2. Observe the hub's two neighbors of the same relationship type render with opposite arrow glyphs — e.g. hub `ENH-3407` shows `ENH-3406 → blocked_by` for one edge and `ENH-3408 ← blocked_by` for the other, despite both being `blocked_by` edges and both frontmatter records being internally consistent with a single forward dependency chain.
3. Compare against `ll-issues clusters --layout list` on the same cluster: it renders both edges consistently from each node's own fixed perspective, with no flip.

## Root Cause

- **File**: `scripts/little_loops/cli/issues/clusters.py`
- **Anchor**: `in function _annot()` (lines 210-214)
- **Cause**: The arrow glyph is computed as `"→" if from_id == parent else "←"`, i.e. relative to the current tree-walk `parent`, not the edge's fixed `from_id`/`to_id`. The tree picks the max-degree node as hub/root (`_render_cluster_tree`'s root selection at line 248, mirroring the hub heuristic in `_cluster_header` at line 131) and walks outward from it. When the hub is `from_id` for one neighbor and `to_id` for another, the same relationship type gets opposite glyphs even though `_EDGE_MEANING` (line 38, e.g. `"blocked_by": "source is blocked by target"`) defines a single fixed, non-relative meaning.

## Error Messages

N/A - rendering-only bug, no exceptions or error output

## Location

- **File**: `scripts/little_loops/cli/issues/clusters.py`
- **Line(s)**: 210-214
- **Anchor**: `in function _annot()`
- **Code**:
```python
def _annot(parent: str, child: str) -> str:
    from_id, _to_id, rel = rel_of[frozenset({parent, child})]
    arrow = "→" if from_id == parent else "←"
    return f"{arrow} {colorize(rel, EDGE_COLOR.get(rel, '37'))}"
```

## Session Log
- `/ll:format-issue` - 2026-09-08T19:31:30 - `0c192ccc-320f-40d5-b594-123949e3b0f3.jsonl`
- `/ll:capture-issue` - 2026-09-08T19:25:23 - `11906448-7df7-4fe2-877f-bca8a2a33d89.jsonl`
