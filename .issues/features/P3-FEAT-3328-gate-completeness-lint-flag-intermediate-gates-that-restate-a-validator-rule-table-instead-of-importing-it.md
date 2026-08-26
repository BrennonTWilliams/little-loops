---
id: FEAT-3328
type: FEAT
title: 'Gate-completeness lint: flag intermediate gates that restate a validator rule
  table instead of importing it'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T17:33:30Z'
---

# FEAT-3328: Gate-completeness lint: flag intermediate gates that restate a validator rule table instead of importing it

## Summary

A meta-loop that gates each lowering pass with an inline `python3 -c` assertion can
restate a validator's rule table instead of importing it. When the restatement is a
proper *subset* of what the terminal gate checks, the intermediate gate does not
merely miss defects — it launders them, giving every downstream pass false
confidence and pushing detection to a point where the retry topology can no longer
reach the state that made the mistake.

This is exactly what happened in `workflow-generator` run `2026-08-26T171218`:
`validate_evaluators` checked `evaluate.type` membership but not required companion
fields, so four states carrying bare `type: output_json` passed the gate, propagated
through two more passes, and first surfaced 4 states downstream as 12 errors at
`validate_artifact` — where `count_emit_retry` routes back to `emit_artifact`, a
state structurally incapable of fixing an `attach_evaluators` defect.

The instance is fixed. This issue is about making the *class* detectable.

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

## Proposed Rule

**Gate-completeness (MR-rule candidate).** For a loop whose terminal gate is a
little-loops validator, flag any intermediate `shell` gate that hardcodes a literal
set of values which the validator exposes as an importable table — e.g. a literal
evaluator-type set instead of `NON_LLM_EVALUATOR_TYPES`, or literal required-field
lists instead of `EVALUATOR_REQUIRED_FIELDS`. Where the terminal gate exposes its
rules as data, import rather than restate.

Detection sketch: in `fsm/validation`, for each `action_type: shell` state whose
action contains `python3`, look for a literal set/frozenset whose members are a
subset of a known exported table's keys. Severity `warning` is probably right to
start — a restatement is sometimes deliberate (a *narrower* curated vocabulary), so
an escape hatch comment should suppress it.

Current blast radius: `workflow-generator.yaml` was the only built-in doing this,
and it has been fixed, so the rule would ship with zero violations and act purely as
a forward guard.

## Non-Goal (document, don't mechanize)

**Retry reachability** — for each bounded-retry edge, can the state it routes to
actually repair every fault class that triggers it? Real and worth checking, but the
fault-class-to-state mapping is semantic and resists static analysis. Add this to
`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` as a review heuristic alongside the MR
rule table rather than attempting a lint.

Source: `postmortems/workflow-generator-output-json-gate-gap.md` §6.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P3
