---
id: ENH-2336
title: 'll-issues clusters: add scoping flags (--cluster/--limit/--compact) and richer per-cluster headers'
type: ENH
priority: P3
status: open
captured_at: '2026-06-26T23:55:30Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- ENH-2335
- FEAT-2337
labels:
- captured
- cli
- ll-issues
- clusters
- output-styling
---

# ENH-2336: `ll-issues clusters` — scoping flags and richer per-cluster headers

## Summary

`clusters` is all-or-nothing and verbose: it dumps every cluster as a full box stack
(373 lines for the current 52-issue backlog) with no way to scope output, and its
per-cluster headers carry almost no at-a-glance information. Add scoping/compaction
flags and enrich the cluster header so a reader can find or skip a cluster without
scrolling. This sits between the cheap output fixes (ENH-2335) and the full layout
rework (FEAT-2337); it does not change the box-stack layout itself.

## Current Behavior

- **No scoping (A3).** `ll-issues clusters` always renders every cluster. Each issue
  occupies 6 terminal rows (4-line box + 2 gap rows: `_BOX_HEIGHT=4`, `_GAP_HEIGHT=2`
  in `clusters.py:25-26`), so a 24-issue cluster alone is ~150 lines. There is no
  `--cluster N`, `--limit N`, or compact mode.
- **Heavyweight orphans (A4).** `--include-orphans` renders each isolated issue as a
  full 4-line box with no edges — a verbose way to list "no relationships".
- **Thin cluster headers (B4).** The header is `─── Cluster 1 (24 issues) ───`
  (`clusters.py:384`). It omits the hub/root issue, priority spread, and blocked
  count — exactly the at-a-glance info that would let a reader skip a cluster. The
  cycle flag is printed on a separate line rather than folded into the header.
- **Priority-blind ordering (A5).** Within a cluster, ordering is topo-sort then
  alphabetical (`_topo_sort_cluster`, `clusters.py:128-162`); a P2 blocker can sit
  below P5s.

## Expected Behavior

`ll-issues clusters` gains three additive scoping/compaction flags and enriched per-cluster headers:

- `--cluster N` renders exactly the Nth cluster (1-indexed); emits a clear out-of-range message if N exceeds the cluster count.
- `--limit N` renders at most N clusters; the footer reports how many were suppressed (no silent truncation).
- `--compact`/`--summary` prints one line per issue (and per orphan) with its edge annotations instead of a 4-line box.
- Per-cluster headers show hub issue (max-degree node), priority spread (e.g. `P2×1 P3×4`), blocked count, edge count, and cycle flag inline on the header line.
- Default full-box output and `--json` are preserved and unchanged.

## Motivation

A 52-issue backlog already produces 373 lines of output — a single `ll-issues clusters` invocation overflows a terminal window. As the backlog grows, the command becomes progressively harder to use for quick triage or cluster-focused review. Scoping flags let users focus on a single cluster during issue review meetings or sprint planning. Richer headers let a reader assess at a glance whether a cluster warrants detailed inspection without scrolling through it. Compact mode enables fast overviews and piping to other tools.

## Proposed Solution

- **`--cluster N`** — render only the Nth cluster (1-indexed, matching the printed
  cluster numbering).
- **`--limit N`** — cap the number of clusters rendered; note suppressed clusters in
  the footer (no silent truncation).
- **`--compact` / `--summary`** — one-line-per-issue tree/list instead of boxes
  (e.g. `[P3] ENH-2191  depends_on→ ENH-2184, ENH-2185`), and render orphans as a
  single line each rather than a box. (Overlaps conceptually with the compact list
  option in FEAT-2337; this issue can ship the simple list form first.)
- **Richer per-cluster header** — augment with hub issue (max-degree node), priority
  spread (e.g. `P2×1 P3×4 …`), blocked count, and edge count; fold the cycle flag
  into the header line.
- **(Optional) priority-aware tie-break** — when topo order is ambiguous, break ties
  by priority before alphabetical, so higher-priority issues surface earlier.

## API/Interface

New `ll-issues clusters` flags:

```
ll-issues clusters [--cluster N] [--limit N] [--compact | --summary]
                   [--include-orphans] [--json]

  --cluster N   Render only the Nth cluster (1-indexed); error if N out of range
  --limit N     Render at most N clusters; footer reports suppressed count
  --compact     One line per issue with edge annotations (no box rendering)
  --summary     Alias for --compact
```

No changes to `--json` output schema or default box-stack rendering.

## Acceptance Criteria

- `--cluster N` renders exactly the Nth cluster (and a clear message if N is out of
  range).
- `--limit N` renders at most N clusters and the footer reports how many were
  suppressed.
- A compact mode prints one line per issue (and per orphan) with its edges.
- Per-cluster header shows hub, priority spread, blocked count, and edge count;
  cycles are indicated inline in the header.
- Existing default (full box) output and `--json` remain available and unchanged.
- Flags are documented in the subparser help (`cli/issues/__init__.py:398-441`).

## Implementation Steps

1. Register `--cluster`, `--limit`, `--compact`/`--summary` in `add_clusters_parser` in `cli/issues/__init__.py`.
2. Add scoping/filtering logic to `cmd_clusters`: apply `--cluster`/`--limit` before rendering; emit suppressed-count footer.
3. Implement compact renderer: one-line format per issue with edge annotations; render orphans as single-line entries.
4. Enrich `_render_cluster_diagram` header with hub issue, priority spread, blocked count, edge count, and inline cycle flag.
5. (Optional) Add priority-aware tie-break in `_topo_sort_cluster` when topo order is ambiguous.
6. Write tests for each flag and the enriched header format.

## Scope Boundaries

- Legend, filter echo, shared palette, unified edge notation (ENH-2335).
- Replacing the box-stack layout with a tree/adjacency model (FEAT-2337).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/clusters.py` — `cmd_clusters` (scoping/limit logic), `_render_cluster_diagram` (header enrichment, orphan one-liner), new compact renderer, `_topo_sort_cluster` (optional priority tie-break)
- `scripts/little_loops/cli/issues/__init__.py` — `add_clusters_parser` block; register `--cluster`, `--limit`, `--compact`/`--summary`

### Dependent Files (Callers/Importers)
- TBD — run `grep -r "cmd_clusters\|\"clusters\"" scripts/little_loops/cli/` to find dispatch references

### Similar Patterns
- TBD — check `--limit`/`--json`/`--compact` patterns in other `ll-issues` subcommand parsers for registration consistency

### Tests
- `scripts/tests/` — add tests for `--cluster N` (valid and out-of-range), `--limit N` (footer message), `--compact`/`--summary` (one-line output), enriched header fields

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — Usability; the command stays readable as the backlog grows.
- **Effort**: Small-Medium — new flags + a compact renderer + header enrichment;
  reuses existing component/edge computation.
- **Risk**: Low — additive flags; default output preserved.
- **Breaking Change**: No.

---
**Open** | Created: 2026-06-26 | Priority: P3


## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The Acceptance Criteria clause "Existing default (full box) output and `--json` remain available and unchanged" applies within the scope of this issue only — it is not a permanent commitment. FEAT-2337 explicitly plans to change the default layout to `tree` (via `--layout {tree,list,boxes}`), superseding the full-box default. Read the AC clause as: "the full-box default is preserved while this issue ships; the default will change when FEAT-2337 ships." This prevents the AC language from being read as a blocking constraint on FEAT-2337. Related issue: FEAT-2337.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-27T22:09:57 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:format-issue` - 2026-06-27T01:47:42 - `1a5326db-d2cc-4813-89e2-ca0885d6f0c4.jsonl`
