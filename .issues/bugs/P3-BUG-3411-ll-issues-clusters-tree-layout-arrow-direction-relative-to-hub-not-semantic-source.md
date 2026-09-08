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

## Root Cause

`_annot()` in `scripts/little_loops/cli/issues/clusters.py:210-214` computes the arrow
direction relative to the current tree-walk parent, not the edge's stored semantic
direction:

```python
def _annot(parent: str, child: str) -> str:
    from_id, _to_id, rel = rel_of[frozenset({parent, child})]
    arrow = "→" if from_id == parent else "←"
    return f"{arrow} {colorize(rel, EDGE_COLOR.get(rel, '37'))}"
```

The tree picks the max-degree node as hub/root (`_render_cluster_tree`'s root selection
at line 248, mirroring the hub heuristic in `_cluster_header` at line 131) and walks
outward from it. When the hub is the edge's `from_id` for one neighbor and the `to_id`
for another, the arrow flips between `→` and `←` for the *same relationship type*, even
though `_EDGE_MEANING` (line 38, `"blocked_by": "source is blocked by target"`) states a
fixed, non-relative meaning.

## Repro

On this repo, `ll-issues clusters` rendered cluster hub `ENH-3407` as:

```
[P1] ENH-3407  record_attempt/admit_retry/authoritative_attempt writers + --retry-of CLI gate
├── [P1] ENH-3406  harness_events run-model columns + harness_admissions table (schema)  → blocked_by
└── [P1] ENH-3408  Count authoritative repetitions ...  ← blocked_by
```

Both edges are the same relationship type (`blocked_by`) and both frontmatter records
are internally consistent with a forward dependency chain
(`ENH-3407 blocked_by: [ENH-3406]`, `ENH-3408 blocked_by: [ENH-3407]`), but the arrows
point in opposite visual directions because `ENH-3407` is the hub and is the edge
*source* for one pair and the edge *target* for the other. The underlying frontmatter
data is correct — this is a rendering-only bug.

`--layout list` (the compact renderer, `_render_cluster_compact` at line 148-177) does
not have this problem: it always renders a node's outgoing edges from that node's own
fixed perspective, never relative to a shared hub.

## Suggested Fix

Make the tree's arrow direction reflect the edge's fixed semantic direction (arrow
always points from `from_id` to `to_id` as stored) instead of direction-relative-to-parent.
Concretely, in `_annot()`, derive the arrow from whether `parent == from_id`
unconditionally in the same way regardless of walk direction — i.e. always show
`from_id → to_id` semantics (e.g. render as `blocked_by →` when the *child* is the
target, or restructure the label to name both IDs explicitly, e.g. `blocked_by ENH-3406`)
so the same relationship type never flips glyphs within one cluster.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Steps to Reproduce

1. [Step 1]
2. [Step 2]
3. [Observe: description of the bug]

## Root Cause

- **File**: `path/to/file.py`
- **Anchor**: `in function buggy_func()`
- **Cause**: [Explanation of why bug happens]

## Error Messages

## Environment

## Frequency

## Location

- **File**: `path/to/file`
- **Line(s)**: [lines] (at scan commit: [COMMIT_HASH_SHORT])
- **Anchor**: `in function name()`
- **Code**:
```
# Relevant code snippet
```

## Reproduction Steps

## Proposed Fix


## Session Log
- `/ll:capture-issue` - 2026-09-08T19:25:23 - `11906448-7df7-4fe2-877f-bca8a2a33d89.jsonl`
