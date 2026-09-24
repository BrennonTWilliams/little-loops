---
id: ENH-3575
type: ENH
title: Structured policy gate field replacing prose gate-phrase grep in autodev
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:14Z'
parent: EPIC-3565
---

# ENH-3575: Structured policy gate field replacing prose gate-phrase grep in autodev

## Summary

Autodev detects policy-gated issues by grepping the **whole issue file** for gate phrases
(e.g. "evidence gate", "gate opens", "do not implement before"). It does this in
`check_gate_at_dequeue` (ENH-3148) and again, duplicated inline, in
`recheck_after_size_review`'s `GATE_MARKER` (BUG-3147). A match defers the issue as
`blocked_by_gate` without checking whether the gate is already satisfied, or whether a spike
or learning test could satisfy it. Historical findings, quoted requirements and resolved-gate
notes keep matching, so an issue can stay parked forever unless someone deletes useful
history just to change a routing verdict.

ENH-3148 explicitly left a structural frontmatter gate field out of scope, naming it the
preferred signal.

## Current Behavior

Any occurrence of a gate phrase, current or historical, parks the issue.

## Expected Behavior

Gate state is explicit and routable. External or manual prerequisites park the issue. Proof
obligations that a spike or `explore-api` can satisfy route to that remedy. Satisfied gates do
not block.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Add a structured frontmatter field, e.g.
`gate: {kind: external|manual|proof, satisfied: bool, evidence: <ref>, owner: <who>}` (or a
list). Autodev reads the field first and falls back to the prose grep only when the field is
absent. Extract the duplicated phrase regex into one shared helper (`ll-issues check-gate` or
similar), which is the extraction BUG-3147 and ENH-3148 deferred.

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
- **Effort**: Medium
- **Risk**: Low. The fallback keeps today's behavior for issues without the field.

## Acceptance Criteria

- [ ] A satisfied structured gate does not defer the issue
- [ ] A `proof` gate routes to spike/explore-api rather than parking
- [ ] One shared gate-detection helper; no duplicated phrase regex in autodev

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3
