---
captured_at: "2026-05-02T15:14:39Z"
discovered_date: "2026-05-02"
discovered_by: capture-issue
---

# ENH-1320: Fix issue-size-review wiring split heuristic for TDD projects

## Summary

The `/ll:issue-size-review` skill frequently suggests splitting wiring (integration points) into a separate issue as a size-reduction strategy. In TDD projects this is an anti-pattern: wiring IS part of the implementation cycle because the integration test that drives the wiring must be written alongside the feature, not deferred to a follow-up issue.

## Current Behavior

`/ll:issue-size-review` flags issues that include wiring work alongside core implementation and recommends creating a separate "wiring" issue. Example output:

> "Consider splitting into: (1) core implementation, (2) wiring + docs"

## Expected Behavior

The skill should recognize that in TDD workflows, wiring belongs in the same issue as implementation because:
1. Integration tests that exercise wired behavior are part of the TDD cycle
2. Splitting wiring creates orphaned implementations that can only be tested with mocks — risking mock/prod divergence
3. Docs separation is acceptable; wiring separation is not

The skill should only suggest splitting wiring when it involves a genuinely independent subsystem (e.g., a new transport protocol, a new storage backend) that is separately testable on its own merits.

## Motivation

Splitting wiring from implementation creates artificial issue boundaries that undermine TDD's fast-feedback guarantee. The first issue passes with mock-based tests; the second wires it up; only then does the design get validated end-to-end. This defers feedback to exactly the wrong time. Doc-split suggestions remain appropriate and unaffected.

## Proposed Solution

Update the heuristic in `skills/issue-size-review/SKILL.md` (and any associated logic) to:
- **Keep**: suggest separating docs into a follow-up issue
- **Change**: only suggest separating wiring if the wiring target is a genuinely independent, separately-testable subsystem
- **Add**: a TDD-awareness note in the heuristic rationale — if the project uses TDD, wiring + tests + implementation belong together

## Integration Map

### Files to Modify
- `skills/issue-size-review/SKILL.md` — primary heuristic logic for split suggestions

### Dependent Files (Callers/Importers)
- TBD — search for any shared split-heuristic logic referenced by other skills

### Similar Patterns
- `skills/wire-issue/SKILL.md` — treats wiring as part of the same implementation cycle (consistent reference)

### Tests
- TBD — check if `scripts/tests/` has coverage for issue-size-review skill behavior

## Implementation Steps

1. Read current split heuristic in `skills/issue-size-review/SKILL.md`
2. Identify the wiring-split recommendation logic
3. Add condition: only recommend wiring split if the integration target is an independent subsystem
4. Add TDD context note explaining why wiring + implementation belong together
5. Verify docs-split suggestion is preserved and unaffected
6. Update any examples in the skill that show wiring-split as an output

## Impact

- **Priority**: P3 - Guidance anti-pattern that subtly undermines TDD discipline on every size review
- **Effort**: Small - Single skill file edit with targeted heuristic refinement
- **Risk**: Low - No runtime code; skill prompt change only
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `skills`, `issue-size-review`, `tdd`, `captured`

---

## Status

**Open** | Created: 2026-05-02 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-02T15:14:39Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19344c8e-9db2-4d37-b7f7-d6bf19e299d8.jsonl`
