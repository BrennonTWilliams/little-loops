---
id: BUG-3691
type: BUG
title: verify-issues citation checking is unstable across passes
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-01'
captured_at: '2026-10-01T22:03:31Z'
---

# BUG-3691: verify-issues citation checking is unstable across passes

## Summary

`/ll:verify-issues <ID> --check --auto` does not check citations consistently between passes of the same loop run, so a citation defect can surface only on a late pass, after the loop's repair budgets are spent.

Observed on BUG-3689 (run `refine-to-ready-issue-20261001T151155`): passes 1 and 2 reported every cited code reference as holding and returned `DIRECTIVE_DRIFT` (Acceptance Criteria gaps). Pass 3, with no relevant citation edits in between, flagged two wrong citations and returned `NON_VALID`, which ended the run `GATE_UNMET` (see the companion ENH on NON_VALID having no repair route). In the same run `refine_followup`'s gap analysis judged the bare name `runner_spec.py` acceptable, while verify pass 3 described it as `fsm/runner_spec.py` (a path the issue text does not contain), i.e. it misread the citation before calling it wrong.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Move `path:line` / `file:symbol` citation resolution into a deterministic CLI check (like `ll-verify-evidence`) that `verify-issues` runs every pass and treats as ground truth; the model only judges semantic claims.

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

## Steps to Reproduce

1. Run `ll-loop run refine-to-ready-issue BUG-3689` against an issue whose Tests section cites a symbol by the importing module rather than the defining module.
2. Compare the per-pass verify summaries in `.loops/.running/<run>.log`.

## Root Cause

Citation verification is performed by the model with ad-hoc reads/greps (the passes reported "direct reads and greps", no graph queries), not by a deterministic check, so coverage varies per pass.

## Acceptance Criteria

- Repeated `--check` passes over an unchanged issue yield the same citation findings.
- A bare filename citation is resolved by search and not reported as a different path.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-01 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-01T22:03:38 - `8a253271-7b3f-4496-adff-dcad85be0bc1.jsonl`
