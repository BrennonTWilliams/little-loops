---
id: ENH-3250
type: ENH
title: refine-to-ready-issue never reviews the Proposed Solution against the code
  it will touch
priority: P3
status: open
testable: true
relates_to:
- BUG-3249
- ENH-3248
- BUG-3243
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T20:04:02Z'
blocked_by:
- ENH-3248
---

# ENH-3250: refine-to-ready-issue never reviews the Proposed Solution against the code it will touch

## Summary

Every LLM state in `refine-to-ready-issue.yaml` evaluates *descriptive* content
-- what the issue says about the code. No state evaluates the *prescriptive*
content -- what happens if the Proposed Solution is implemented as written.
Defects that only appear when the proposal is read against the code it will
touch pass the whole chain.

## Current Behavior

The four LLM states and the question each asks:

| state | question | on BUG-3243 |
|---|---|---|
| `refine_issue` | what's missing about the code? | worked -- diagnosis accurate |
| `wire_issue` | what else touches this? | worked -- found both call sites |
| `verify_issue --check` | are the issue's claims true? | worked -- every claim was true |
| `confidence_check` | score a rubric | 100 / 82 |

`verify_issue` is the only state that consults the codebase adversarially, and
its contract is claim verification: it tests assertions the issue makes. On
BUG-3243 every such assertion was correct, so it returned VALID -- correctly.

A manual review of the same issue then found three defects none of the four
could have surfaced:

1. The Proposed Solution said to add `timeout=` to a `subprocess.run` call
   whose handler is `except (OSError, ValueError)`. `subprocess.TimeoutExpired`
   subclasses `SubprocessError`, not `OSError`, so implementing the proposal
   verbatim converts a hang into an uncaught exception. This is not a false
   claim in the issue -- it is a consequence of the proposal.
2. Two existing tests patch `subprocess.run` with a single `return_value`; the
   proposal adds a second git call that would silently receive the same mock,
   putting the tests on a code path that contradicts the issue's own
   acceptance criteria.
3. An acceptance criterion was missing for the two CLI surfaces `wire_issue`
   had already correctly identified as affected -- the wiring pass found them,
   but nothing checks that the ACs cover what the wiring found.

## Expected Behavior

Before an issue is declared ready, something evaluates the Proposed Solution
against the code it names and reports consequences the issue does not
anticipate -- exception-handling interactions, test fixtures the change
invalidates, acceptance criteria that do not cover the identified integration
points.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` -- new state, or a
  routable consumer of confidence_check's risk factors
- possibly `commands/verify-issues.md` -- if the mandate is widened there
  instead (verify-issues is a command, not a skill)
- possibly `skills/confidence-check/SKILL.md` -- if risk factors become a
  machine-readable verdict rather than prose

### Related Issues
- ENH-3248 (triage the refine-to-ready-issue retry path by failure kind
  instead of always refining) -- **design these together**. A new gate whose
  only recourse is `refine_followup` is precisely the always-refine pattern
  ENH-3248 argues against; the failure kind here ("proposal is unsound") likely
  needs a different remedy than "refine again".
- BUG-3249 (refine-to-ready-issue has no `check-design` gate) -- companion
  defect in the same loop, captured in the same pass.

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

The chain has no adversarial pass over the Proposed Solution. `/ll:go-no-go`
is the closest existing shape and is not invoked anywhere in this loop.
`confidence_check` scores a rubric rather than reasoning about implementation
consequences; a proposal can score well on every axis (specific, unambiguous,
small, testable) and still not survive contact with the code.

A related observation, cheaper to fix and possibly sufficient on its own:
`confidence_check` *did* record the Proposed Solution's unresolved either/or
under "Outcome Risk Factors", and the loop terminated `done` anyway. The gap
there is not detection but that a recorded risk factor routes nowhere.

## Open Questions

- Is a new adversarial state warranted, or is it enough to make
  `confidence_check`'s already-recorded "Outcome Risk Factors" routable? The
  latter is far cheaper and would have caught defect 3 (the either/or) though
  not 1 or 2.
- Does this belong in `refine-to-ready-issue` at all, or in `verify-issues` as
  a widened mandate (claims *and* proposals)? `verify_issue` already loads the
  relevant code, so a widened prompt may cost little beyond tokens.
- Model tier: all four states ran on sonnet in the observed run. Depth of
  adversarial reasoning is model-sensitive; measure before adding a state.

## Acceptance Criteria

- [ ] Design decision recorded for the three Open Questions above before any
      implementation.
- [ ] An issue whose Proposed Solution contradicts the code it names (e.g. the
      `TimeoutExpired` case above) does not reach `done` unflagged.
- [ ] Acceptance criteria are checked for coverage of the integration points
      `wire_issue` identified.
- [ ] Added cost is measured against the observed baseline (4 LLM calls,
      17m49s, ~$1.47 per run) and reported.
- [ ] `ll-loop validate refine-to-ready-issue` exits 0.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Discovered by hand-reviewing BUG-3243 after `ll-loop run refine-to-ready-issue
BUG-3243` reported `done`. Distinct from the missing `check-design` gate: that
one is a routing defect (the verdict existed and was ignored); this one is a
coverage gap (the verdict was never computed).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `fsm`, `issue-management`

## Status

**Open** | Created: 2026-08-17 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:54 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:capture-issue` - 2026-08-17T20:04:12 - `86ab77f1-d20d-487b-9f55-2f4d8abf9a06.jsonl`
