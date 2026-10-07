---
id: BUG-3764
type: BUG
title: verify-issues labels Program Design drift inconsistently between DIRECTIVE_DRIFT
  and NON_VALID
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T00:49:19Z'
---

# BUG-3764: verify-issues labels Program Design drift inconsistently between DIRECTIVE_DRIFT and NON_VALID

## Summary

`/ll:verify-issues --check --auto` returned different verdicts for the same Program Design drift across three consecutive passes on BUG-3761 (run `.loops/.history/2026-10-07T000313-refine-to-ready-issue`):

- Pass 1 and pass 2: `DIRECTIVE_DRIFT` (routed to `check_reconcile_limit`).
- Pass 3: `NON_VALID`, which `ll-issues next-obligation` surfaces as `VERIFY:other` (routed to `check_gate_refine_limit`). The pass-3 output reasoned that Program Design is not among the sections `DIRECTIVE_DRIFT` covers.

`commands/verify-issues.md` defines `DIRECTIVE_DRIFT` as a check-B6 finding whose fix is confined to Implementation Steps / Acceptance Criteria / Integration Map, and names `reconcile-issue --from-verify-evidence` as its remedy. Program Design drift fits neither that definition nor any other verdict, so the model picks one non-deterministically. And when it does pick `DIRECTIVE_DRIFT`, the remedy refuses the section (see the companion Program Design rewrite-gap bug).

Side effect: `record_gate_unmet` only emits the `GATE_UNMET:DIRECTIVE_DRIFT_NON_CONVERGENCE` evidence tag when `check-verify-verdict --directive-drift` passes, so the flip to `NON_VALID` suppressed it on this run.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

Program Design / Impact drift against a selected decision gets one deterministic verdict, with a defined remedy rung.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Decide where Program Design drift belongs: either widen `DIRECTIVE_DRIFT`'s section list (only sound if reconcile's contract also widens) or add an explicit verdict/obligation for it. Make the check-B6 classification text and the `next-obligation` token mapping agree.

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

- **Severity**: Low on its own (the end state was the same here); makes loop failures harder to diagnose and breaks the non-convergence tag.
- **Affected**: `commands/verify-issues.md`, `scripts/little_loops/loops/refine-to-ready-issue.yaml` (`route_pre_score_obligation`, `record_gate_unmet`).

## Acceptance Criteria

- `commands/verify-issues.md` names the verdict for Program Design / Impact drift explicitly.
- Repeated `--check` passes on the same unchanged issue return the same verdict.
- `record_gate_unmet` tags non-convergence for that verdict.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-07 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-07T00:49:25 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
