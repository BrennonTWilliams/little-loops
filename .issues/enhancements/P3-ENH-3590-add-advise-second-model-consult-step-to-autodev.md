---
id: ENH-3590
type: ENH
title: Add advise second-model consult step to autodev
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T03:36:09Z'
parent: EPIC-3565
---

# ENH-3590: Add advise second-model consult step to autodev

## Summary

Add an `/ll:advise` (second-model consult, `ll-advise`) step to `scripts/little_loops/loops/autodev.yaml` so autodev gets a review from a stronger/different model.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

autodev currently has no review by a stronger or different model. Its only adversarial check is `run_go_no_go` (~line 2244, `/ll:go-no-go --auto`), a same-model (sonnet) `Agent` subagent debate that fires only for `oversized_atomic` deferrals; a GO verdict stamps `outcome_gate_waived: true`. `/ll:confidence-check` and `oracles/resolve-decision` also run on the default model, and neither `autodev.yaml` nor `oracles/resolve-decision.yaml` references `advise`, `ll-advise`, or a `model:` override.

## Proposed Solution

Add an advise state (alongside or after `run_go_no_go`, or before repair/defer decisions) that consults a stronger model via `/ll:advise --signal ... --question ...` non-interactively.

- Read the verdict back deterministically from frontmatter/JSON, never by parsing stdout (MR-1).
- Use the `with_rate_limit_handling` fragment (route `on_rate_limit_exhausted: finalize_rate_limited`).
- Resolve the host via `resolve_host()` / `host_runner`; add no new `"claude"` literals.
- Make it configurable and opt-out so it adds no cost by default.

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

## Open Questions

- Which decision points warrant the consult (oversized_atomic deferral, repair/defer, decision resolution)?
- Can an advise verdict waive or override a go-no-go result?
- What cost/latency budget applies per issue and per run?

## Acceptance Criteria

- [ ] autodev has an advise state that invokes a second-model consult at the chosen decision point(s)
- [ ] Verdict is persisted to frontmatter/JSON and read back without stdout parsing
- [ ] Disabled by default; enabled via config/context flag
- [ ] `ll-loop validate autodev` passes

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-25T03:36:14 - `d36455b9-41a7-4bb9-9928-6288b5c7fed1.jsonl`
