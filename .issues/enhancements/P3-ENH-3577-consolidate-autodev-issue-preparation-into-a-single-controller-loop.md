---
id: ENH-3577
type: ENH
title: Consolidate autodev issue preparation into a single controller loop
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:14Z'
parent: EPIC-3565
---

# ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Summary

Consolidate autodev's per-issue preparation into one single-issue controller (extending
`refine-to-ready-issue`), so the outer `autodev` loop owns only queue orchestration and
accounting. Today repair and rescoring policy is split between parent and child. Autodev
re-implements spike, reconcile, size-review, design-remedy and decision routing, with its own
marker files (`autodev-pre-deferral-remedy.txt`, `autodev-decide-ran`, the fired markers),
and `ll-issues show` + inline Python predicates are copied across states. The route-specific
contract gaps in the sibling issues come directly from this duplication.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

- The outer loop has about 87 states, with a large inline `finalize_done`.
- Learning-proof ownership is spread across confidence-check, ready-issue and the learning
  primitive, which each treat refuted/stale records differently.
- Each duplicated route is a place where the readiness invariant can silently fail to apply.

## Proposed Solution

1. The child returns typed outcomes (`ready`, `decomposed`, `cancelled`, `blocked`,
   `deferred`, `retryable_error`) plus child IDs and evidence references, in one per-issue
   run record.
2. One deterministic assessment + repair selector: read the issue once, run
   format/design/AC/decision/proof checks, and choose the next unmet obligation. Replace the
   copied shell/Python predicates and handshake files with a shared implementation that
   emits structured output. Do not replace it with one large LLM prompt.
3. Keep distinct skills for research, wiring, decisions and reconciliation. Their edit
   contracts are useful boundaries.
4. One budget owner for learning proof; risk-conditional go/no-go.

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

- **Priority**: P3
- **Effort**: Very Large
- **Risk**: High. This is a large refactor of heavily used loops.

## Scope Boundaries

- Blocked until the behavioral fixes in the sibling issues land with real-FSM regression
  tests (stateful stub skills/CLIs asserting outcomes and evidence freshness, not state
  names). Consolidating first would lose the behavior those tests protect.
- No state-count target.

## Acceptance Criteria

- [ ] Autodev contains no repair routing that duplicates the child's
- [ ] A single typed per-issue outcome drives the outer ledger
- [ ] The regression scenarios listed in the parent EPIC's audit pass unchanged before and after

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3
