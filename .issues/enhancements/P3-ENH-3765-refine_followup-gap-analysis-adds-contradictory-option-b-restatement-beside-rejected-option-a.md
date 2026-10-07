---
id: ENH-3765
type: ENH
title: refine_followup gap-analysis adds contradictory Option B restatement beside
  rejected Option A
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T00:49:19Z'
---

# ENH-3765: refine_followup gap-analysis adds contradictory Option B restatement beside rejected Option A

## Summary

On BUG-3761, `refine_followup` (`/ll:refine-issue --auto --gap-analysis`, ~6 min) was routed a residual `unapplied_decision` finding. Gap-analysis is additive-only, so it could not remove the rejected Option A text. Instead it folded in an Option B restatement inside Program Design plus a note that the older bullets describe the rejected option, and restated Impact Effort/Risk the same way. The issue now holds both designs in the same section; its own report said the gate still failed and that a rewrite was needed.

The loop run: `.loops/.history/2026-10-07T000313-refine-to-ready-issue`.

An implementer or later automated pass reading that section has to guess which design is live, and the next `format-check` still fails on the old identifiers.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

When the remaining finding is not fixable additively (`unapplied_decision` on a rejected option), `refine-issue --gap-analysis` should detect that and either decline to add contradictory text, or hand off with a clear marker so the loop can route to a rewrite rung instead of spending its one gate-refine budget.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

In the refine-issue gap-analysis path, check `ll-issues format-check` for `unapplied_decision` before writing; if present, emit a refuse-and-report result (no body edit) so `check_gate_refine_limit` budget is not burned on a no-op. Pairs with the Program Design rewrite rung bug.

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

- **Severity**: Low-medium; wasted loop time and a less coherent issue file.
- **Affected**: `commands/refine-issue.md`, `scripts/little_loops/loops/refine-to-ready-issue.yaml` (`refine_followup`).

## Acceptance Criteria

- Gap-analysis on an issue with an unapplied-decision residual makes no Program Design/Impact edits that coexist with the rejected-option text.
- Its output states the rewrite requirement in a form the loop can detect.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-07 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-07T00:49:26 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
