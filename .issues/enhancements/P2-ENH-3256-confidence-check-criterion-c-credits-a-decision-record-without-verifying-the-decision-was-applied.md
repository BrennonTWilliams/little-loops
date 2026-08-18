---
id: ENH-3256
type: ENH
title: confidence-check Criterion C credits a decision record without verifying the
  decision was applied
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-18'
captured_at: '2026-08-18T20:48:19Z'
parent: EPIC-2856
testable: true
relates_to:
- BUG-3249
- ENH-3250
- ENH-3257
- ENH-2852
---

# ENH-3256: confidence-check Criterion C credits a decision record without verifying the decision was applied

## Summary

`/ll:confidence-check`'s Criterion C (Ambiguity) awards its top score for "No
ambiguity — solution is fully specified with single clear approach"
(`skills/confidence-check/rubric.md:311`). Nothing in the criterion checks that
the selected option was propagated into the issue's directive sections, so an
issue carrying a `### Decision Rationale` block scores as unambiguous even when
every other section still specifies the rejected option.

Observed on BUG-3249: `/ll:decide-issue` stamped **"Selected: Option B"** (route
`check_design.on_no` to `check_refine_limit`) at 20:26. `/ll:confidence-check`
ran at 20:38 and set `score_ambiguity: 25` / `confidence_score: 100`. At that
moment five directive sections still specified the rejected Option A:

- Proposed Solution (`:99`) — bolded "Routing target: `refine_followup`, **not**
  `check_refine_limit`"
- Program Design › Decision Rules (`:211`) — "never directly to
  `check_refine_limit`"
- Implementation Steps (`:232`) — "`on_no` routes to `refine_followup`"
- Wiring Phase (`:241`) — new test must assert `on_no == "refine_followup"`
- Acceptance Criteria (`:281`) — "routes ... at the **refine** rung
  (`refine_followup`)"

An implementer reading top-down builds Option A; one reading the Wiring Phase
writes a test that fails the decided design. The rubric treated a decision
*record* as a decision *applied*.

The gap is structural, not a scoring misjudgment: no criterion in the rubric
reads for cross-section agreement, and no deterministic gate covers it either
(`ll-issues check-design` exits 0 — the Program Design section is present and
specific, just specific about the wrong option).

Proposed direction: when an issue contains a `### Decision Rationale` with a
selected option, cap Criterion C unless the selected option's key identifiers
appear in the Proposed Solution / Program Design / Acceptance Criteria — or
route the mismatch to `/ll:reconcile-issue`, which already exists to rewrite
directive sections from findings.

Related: BUG-3249 (the instance), ENH-3250 (same blind-spot family, but targets
the loop's missing prescriptive-review state rather than the rubric),
ENH-2852 (built the Phase 1.6 pre-fetch gate this extends).


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

## Current Pain Point

## Success Metrics

## Scope Boundaries

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:capture-issue` - 2026-08-18T20:48:46 - `fdfd9556-8841-4d2f-baeb-50bd68feb80e.jsonl`
