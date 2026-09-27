---
id: ENH-3636
type: ENH
title: 'll-issues show: annotate resolved blocked_by/depends_on edges with status'
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T17:29:51Z'
---

# ENH-3636: ll-issues show: annotate resolved blocked_by/depends_on edges with status

## Summary

`ll-issues show` renders the `Blocked by:` and `Depends on:` relationship rows as raw frontmatter IDs without resolving each target's status, so an already-satisfied blocker reads as a live one. Example: ENH-3623 shows `Blocked by: ENH-3630` even though ENH-3630 is `done`.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

`blocked_by` / `depends_on` edges are durable by design — nothing prunes them when the target completes (`set_status.py:268` documents that these association edges never cascade). Resolution is computed at read time: `DependencyGraph.get_blocking_issues()` returns `blockers - completed` (`dependency_graph.py:283`), so schedulers (`next-issue`, sprints, autodev) already treat ENH-3623 as unblocked. Only the display disagrees, which prompted a false "is refine-to-ready-issue broken?" investigation on 2026-09-27 after a refine-to-ready-issue run on ENH-3623 (the run's `gate_unmet` failure was unrelated).

## Proposed Solution

Display-side only — do not mutate frontmatter:

- In `_render_relationships_block` (`scripts/little_loops/cli/issues/show.py`, keys table `_RELATIONSHIP_KEYS`; fields built via `_join_ids` around the `"blocked_by"` / `"depends_on"` entries), resolve each ID's status and annotate resolved ones, e.g. `Blocked by: ENH-3630 (done)`, or split them into a separate `Resolved blockers:` row.
- Only `done` / `cancelled` resolve an edge; `deferred` is non-terminal and must still render as a live blocker.
- Unknown / unresolvable IDs render unchanged (maybe `(missing)`).
- `--json`: consider adding a structured per-edge status (e.g. `blocked_by_status` or `unresolved_blocked_by`) rather than changing the existing string field. Note `--json` status is display-cased ("Completed" = done), so any comparison must normalize.

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

1. Reuse existing status lookup (issue index / `find_issues` or the dependency graph's completed set) to map edge target IDs → status.
2. Annotate or split resolved edges in the text renderer for `blocked_by` and `depends_on`.
3. Add the structured field to `--json` output if chosen.
4. Tests: resolved (`done`, `cancelled`), unresolved (`open`, `deferred`), and missing targets.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- `ll-issues show ENH-3623` makes it visible that ENH-3630 is resolved.
- A `deferred` or `open` blocker renders without a resolved annotation.
- No frontmatter is modified by `show`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-09-27T17:29:56 - `4759cc5d-e905-4259-b830-49d49c1712bf.jsonl`
