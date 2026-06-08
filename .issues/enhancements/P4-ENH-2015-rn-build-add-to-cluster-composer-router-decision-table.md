---
id: ENH-2015
title: "rn-build — Add to Cluster vs. Composer vs. Router decision table in LOOPS_GUIDE"
type: ENH
priority: P4
status: open
parent: EPIC-1811
captured_at: '2026-06-08T01:29:25Z'
discovered_date: 2026-06-08
discovered_by: capture-issue
size: XSmall
testable: false
blocked_by:
- FEAT-1992
relates_to:
- FEAT-1990
- FEAT-1992
- FEAT-1994
labels:
- loops
- docs
- rn-build
---

# ENH-2015: `rn-build` — Add to "Cluster vs. Composer vs. Router" decision table in LOOPS_GUIDE

## Summary

The canonical "Cluster vs. Composer vs. Router" decision table in
`docs/guides/LOOPS_GUIDE.md` (around line 2104) covers `loop-router`,
`loop-composer` / `loop-composer-adaptive`, and `goal-cluster` — but omits
`rn-build`. A user reading that table to decide which orchestration loop to
reach for will not discover `rn-build` as the answer for spec-file / zero-to-project
builds. FEAT-1994 adds a separate input-shape decision table; this ENH updates
the existing table to include `rn-build` alongside the other orchestration loops.

## Current Behavior

The "Cluster vs. Composer vs. Router" decision table in `docs/guides/LOOPS_GUIDE.md` (around line 2104) covers three orchestration loops — `loop-router`, `loop-composer`/`loop-composer-adaptive`, and `goal-cluster` — but does not include `rn-build`. A user consulting the table to choose an orchestration loop will not discover `rn-build` as the answer for spec-file / zero-to-project builds.

## Expected Behavior

The decision table includes a fourth row for `rn-build` describing when to use it (spec file → zero-to-project with fully automated pipeline). The decision rule paragraph below the table references `rn-build` for spec-driven greenfield projects.

## Motivation

The existing table is the first thing users read when choosing an orchestration
loop. Omitting `rn-build` from it means the loop is effectively invisible to
anyone who hasn't already read the full LOOPS_GUIDE catalog. Since FEAT-1994's
input-shape table is additive, it complements but does not replace the existing
table — both should reference `rn-build`.

## Proposed Solution

### Current table

```markdown
| Loop | When to use |
|---|---|
| `loop-router` | Single goal, best-fit single loop. Use as the default entry point. |
| `loop-composer` / `loop-composer-adaptive` | Single decomposable goal ... |
| `goal-cluster` | Multiple related goals that share context. ... |
```

### Updated table

Add a fourth row:

```markdown
| `rn-build` | Spec file → zero-to-project. Orchestrates the full pipeline: tech research → design → scope EPIC → `goal-cluster` (batched `rn-implement`) → eval gate. Use when you have a spec document and want fully automated spec-to-implementation with no manual handoffs. |
```

Also update the **Decision rule** paragraph below the table to mention `rn-build`:

> For spec-driven greenfield projects (you have a spec file and want a full
> automated build), use `rn-build`.

## Implementation Steps

1. Locate the "Cluster vs. Composer vs. Router" table in `docs/guides/LOOPS_GUIDE.md`
2. Add the `rn-build` row (see Proposed Solution)
3. Update the "Decision rule" paragraph to reference `rn-build` for spec-driven use
4. Run `ll-check-links` to verify no broken references

## Integration Map

### Files to Modify
- `docs/guides/LOOPS_GUIDE.md` — add `rn-build` row to decision table; update decision rule paragraph

### Dependent Files (Callers/Importers)
- N/A — documentation-only change; no code imports this doc

### Similar Patterns
- FEAT-1994 input-shape decision table (also in `LOOPS_GUIDE.md`) — both tables should consistently reference `rn-build`

### Tests
- Run `ll-check-links` after edit to verify no broken anchors or references

### Documentation
- `docs/guides/LOOPS_GUIDE.md` only

### Configuration
- N/A

## Acceptance Criteria

- The "Cluster vs. Composer vs. Router" table has a `rn-build` row.
- The decision rule paragraph references `rn-build` for spec-driven projects.
- `ll-check-links` reports no broken references.

## Impact

- **Priority**: P4 — discoverability improvement; no functional change
- **Effort**: XSmall — two-line table edit and one sentence update
- **Risk**: Low
- **Breaking Change**: No

## Scope Boundaries

- Only modifies the "Cluster vs. Composer vs. Router" decision table and its rule paragraph in `docs/guides/LOOPS_GUIDE.md`
- Does not change `rn-build` loop behavior or any YAML configuration
- Does not add a full tutorial, deep-dive section, or usage examples for `rn-build`
- Does not update any other documentation files beyond what is specified in Implementation Steps

## Status

**Open** | Created: 2026-06-08

## Session Log
- `/ll:format-issue` - 2026-06-08T01:36:13 - `b59e4b87-6e2b-4690-bb43-64f1327b0c7e.jsonl`
- `/ll:capture-issue` - 2026-06-08T01:29:25Z - `00fefddf-56f7-43f8-8a57-dd53f6c3526d.jsonl`
