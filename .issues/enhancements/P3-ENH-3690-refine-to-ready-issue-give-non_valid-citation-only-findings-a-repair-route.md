---
id: ENH-3690
type: ENH
title: 'refine-to-ready-issue: give NON_VALID citation-only findings a repair route'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-01'
captured_at: '2026-10-01T22:03:25Z'
---

# ENH-3690: refine-to-ready-issue: give NON_VALID citation-only findings a repair route

## Summary

In `refine-to-ready-issue`, a `/ll:verify-issues --check` verdict of `NON_VALID` caused only by wrong file-path or symbol-location citations has no repair route, so the run ends `GATE_UNMET` (observed on BUG-3689, run `refine-to-ready-issue-20261001T151155`, 33 iterations / 19m38s).

Chain: the third verify pass flagged two mis-citations (a bare `runner_spec.py:335` in Current Behavior, whose real path is `scripts/little_loops/runner_spec.py`; and `cli/loop/feed.py:terminal_size()` in Tests/Wiring Phase, which is defined in `cli/output.py`). Because one finding sat in Current Behavior, `commands/verify-issues.md` §2C keeps the verdict `NON_VALID` (never `CLAIMS_OUTDATED`), and `NON_VALID` outranks the Tests-section finding that alone would have been correctable. `route_pre_score_obligation` maps it to `VERIFY:other` -> `check_gate_refine_limit`. That budget (one loopback per run) had already been spent by an earlier `refine_followup`, which is additive-only and cannot fix a stale fact. Route continues to `record_gate_unmet` -> `failed`.

Neither `reconcile_issue` (directive sections only) nor `correct_claims` (`CLAIMS_OUTDATED` only) is reachable.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Options (pick one):
1. Give `VERIFY:other`/`NON_VALID` one `correct_claims`-style attempt before `record_gate_unmet` when `verify_evidence` lists only citation-shaped findings.
2. Relax §2C so a pure path/symbol-location fix in Current Behavior is `CLAIMS_OUTDATED` (premise unchanged), keeping premise changes `NON_VALID`.
3. Have `VERIFY:other` skip `refine_followup` (cannot help) and go straight to a claims-correction state, so the single gate-refine budget isn't wasted.

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

- A run whose only verify findings are wrong path/symbol citations is repaired in-loop or reports a distinct non-quality outcome instead of `GATE_UNMET`.
- Premise-changing findings still persist as `NON_VALID`.
- Covered by a test in `scripts/tests/test_builtin_loops.py` for the new route.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-01 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-01T22:03:38 - `8a253271-7b3f-4496-adff-dcad85be0bc1.jsonl`
