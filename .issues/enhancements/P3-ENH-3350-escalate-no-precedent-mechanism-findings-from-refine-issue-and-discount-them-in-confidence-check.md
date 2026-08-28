---
id: ENH-3350
type: ENH
title: Escalate no-precedent mechanism findings from refine-issue and discount them
  in confidence-check
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-28'
captured_at: '2026-08-28T01:42:06Z'
---

# ENH-3350: Escalate no-precedent mechanism findings from refine-issue and discount them in confidence-check

## Summary

Refine-issue findings that state a proposed remedy relies on a mechanism with no confirming precedent in the codebase are currently deposited silently and nothing downstream acts on them. On BUG-3349, the refine pass recorded exactly the warning sign ("no existing site applies :shell to a captured.* reference — no direct precedent confirming the combination works"), yet the flawed remedy survived format-issue, refine-issue, and confidence-check (outcome_confidence 84) even though its core primitive — a bare :shell binding on a capture that is always missing on one of two mutually exclusive branches — would have raised InterpolationError on every run. No skill in the chain is tasked with falsifying a proposed mechanism: refine-issue only annotates contradictions (the directive line had pre-emptively acknowledged the mutual-exclusivity fact, so no Superseded marker fired), and confidence-check takes the issue's internal reasoning at face value.

Two changes:

1. /ll:refine-issue: when a codebase research finding this pass is depositing states that a proposed mechanism has no confirming precedent (no existing usage site exercises the combination the remedy depends on), emit an explicit escalation — recommend /ll:spike in the completion report and set a frontmatter flag (e.g. unproven_mechanism: true) or decision_needed, analogous to the existing superseded-marker -> /ll:reconcile-issue recommendation path (ENH-2992 pattern).

2. /ll:confidence-check: cap or discount outcome_confidence when the issue contains an unresolved no-precedent finding against its own Proposed Solution / Expected Behavior (e.g. cap at a threshold below the outcome gate, or subtract a fixed penalty until a spike or reconcile pass clears the flag).


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
- `/ll:capture-issue` - 2026-08-28T01:42:14 - `ba0fc777-8ec0-4b16-9e56-2a5dee8b5dea.jsonl`
