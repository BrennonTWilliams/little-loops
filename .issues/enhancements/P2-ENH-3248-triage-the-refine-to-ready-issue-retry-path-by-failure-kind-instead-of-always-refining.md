---
id: ENH-3248
type: ENH
title: Triage the refine-to-ready-issue retry path by failure kind instead of always
  refining
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T19:24:43Z'
---

# ENH-3248: Triage the refine-to-ready-issue retry path by failure kind instead of always refining

## Summary

`check_refine_limit` routes every gate failure to a single remedy, `refine_followup`
(`/ll:refine-issue --auto --gap-analysis`), which is additive-only. Two of the four gates that reach
it need content *removed* or *rewritten*, so their remedy is structurally incapable of clearing
them. Route by failure kind: deterministic normalize, then self-referential reconcile, then
re-research refine.


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
