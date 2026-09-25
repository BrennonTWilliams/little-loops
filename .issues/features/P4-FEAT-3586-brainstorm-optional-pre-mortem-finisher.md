---
id: FEAT-3586
type: FEAT
title: Brainstorm optional pre-mortem finisher
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:14Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
---

# FEAT-3586: Brainstorm optional pre-mortem finisher

## Summary

Add an optional `premortem` finisher (approach D from EPIC-3581): the portfolio
winner (and optionally the runner-up) is attacked by a critic, a defender revises,
and the final report ships each idea with its known risks and kill criteria.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

- Enabled per profile (`functional`, `business` default on) or via `premortem=true`.
- Critic produces the top failure modes ("it's 12 months later and this failed
  because…"); defender revises the idea or concedes; a bounded number of rounds.
- Report gains a `Risks & Kill Criteria` section per finalist; an idea the defender
  concedes is demoted and the next finalist promoted.

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

## Acceptance Criteria

- Round count is bounded by context and enforced by the FSM (no unbounded debate).
- Demotion/promotion is recorded in `ideas.jsonl` and reflected in `winners`.
- Skipped cleanly when disabled; no change to output shape otherwise.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-09-25T00:33:52 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
