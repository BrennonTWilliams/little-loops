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
confidence_score: 50
outcome_confidence: 9
score_complexity: 9
score_test_coverage: 0
score_ambiguity: 0
score_change_surface: 0
decision_needed: true
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

## Scope Boundaries

**Spike first — deliberately not sprint-scheduled.** Removed from the
`refine-issue-pipeline` sprint on 2026-08-17. This issue is design-decision-first,
not implementation-ready: its `## Proposed Solution` is unresolved, and its own
first acceptance criterion requires the three Open Questions below to be answered
*before any implementation*. Two of those questions (new adversarial state vs.
routable `confidence_check` risk factors; this loop vs. a widened
`verify-issues` mandate) change what gets built, not just how. Run `/ll:spike`
to settle them, then re-refine and re-schedule.

The companion defect BUG-3249 stays in the sprint: it is a pure wiring omission
with a factored CLI already available, and does not depend on this issue's
outcome.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- **Write-verdict/read-verdict is the established shape for gating on a prior LLM state's output** — never read raw LLM structured output directly in a later gate. `verify_issue` (`scripts/little_loops/loops/refine-to-ready-issue.yaml:279-287`) persists `verify_verdict: VALID|NON_VALID` to frontmatter; `check_verify_verdict` (`:289-299`) reads it via `ll-issues check-verify-verdict` (`scripts/little_loops/cli/issues/check_verify_verdict.py`). The same pair-shape recurs at `check_decision_mid_refine` (`:200`, reads `decision_needed` via `ll-issues check-flag`) and `check_missing_artifacts` (`:471-480`, reads `missing_artifacts`). Any new adversarial state should write a persisted verdict and add a sibling gate to read it, not branch on raw LLM output inline.
- **The routing gap is concrete and already located**: `check_outcome` (`refine-to-ready-issue.yaml:392`) routes `on_yes` straight to `done` (`:434`) when `outcome_confidence` clears `outcome_threshold` — bypassing `check_decision_needed` (`:438-449`), which is reachable only via `check_outcome`'s `on_no` path. A `decision_needed: true` flag stamped by `confidence-check`'s Phase 4.6 write-back (`skills/confidence-check/SKILL.md:425-439`, via `ll-issues set-flags` → `apply_flags_from_notes()` in `scripts/little_loops/cli/issues/set_flags.py:238-331`) is therefore never consulted on the passing-outcome path — this is the exact routing gap that let BUG-3243's recorded "either/or" risk factor go unrouted to `done`.
- **`confidence_check` is a `loop:`-call to a self-contained oracle sub-loop**, not inlined prompt states: `refine-to-ready-issue.yaml:346-358` calls `oracles/verify-confidence-scores.yaml`. A second oracle example with a deterministic (non-LLM) `classify`/`route:` aggregation shape is `oracles/code-run-gate.yaml:399-468`. A new adversarial-review state, if added as its own oracle, would follow this `loop:`-call convention rather than being written inline.
- **`/ll:go-no-go` (`skills/go-no-go/SKILL.md`) is not wired into any FSM loop.** `grep go-no-go scripts/little_loops/loops/` matches only a comment in `autodev.yaml:2001` describing a manually-or-go-no-go-stamped `outcome_gate_waived` frontmatter flag, read at `recheck_after_size_review` (`autodev.yaml:1990-2013`) via the same read-a-frontmatter-flag shape as above — not a direct state invocation. `go-no-go` already exposes a `--check` flag (`SKILL.md:41`, Phase 5, `:444-461`) documented as integrating with FSM `evaluate: type: exit_code` routing, the same contract `verify_issue --check` uses — so it is FSM-portable if wired, but isn't today. Its judge verdict (`VERDICT: GO|NO-GO`, `SKILL.md:307-333`) is prose, not a tagged-JSON trailer like `confidence-check`'s `VERDICT_JSON` convention (`skills/confidence-check/rubric.md:412-418`, consumed in `scripts/little_loops/cli/action.py`) — a new state modeled on go-no-go would need to add that trailer to fit the write-verdict/read-verdict shape above.
- **`verify_issue --check`'s contract is claim-verification only**, not prescriptive review: `commands/verify-issues.md` §B "Verify Against Codebase" (`:126-130`) checks "files exist / line numbers / code snippets / is the described behavior accurate" — it loads related code only to corroborate claims about *current* state, never to trace consequences of implementing the Proposed Solution (exception-handler compatibility, mock-fixture reuse, AC-vs-integration-point coverage). This confirms the issue's own Current Behavior table.
- **Model tier**: no loop in `scripts/little_loops/loops/*.yaml` (incl. `oracles/`) currently sets the per-state `model:` schema field (`scripts/little_loops/fsm/fsm-loop-schema.json:611-617`, exists but unused repo-wide). Model tier is pinned at the invoked skill's frontmatter instead — `skills/go-no-go/SKILL.md:4` and `skills/confidence-check/SKILL.md:5` both declare `model: sonnet`; `skills/analyze-history/SKILL.md:5` is the one `haiku` exception found. A new state invoking a slash-command/skill inherits that skill's pinned model rather than needing its own override.
- **The cited baseline (4 LLM calls, 17m49s, ~$1.47/run) has no backing artifact.** No postmortem, run log, or `.loops/.history` entry for BUG-3243 contains these figures (`postmortems/**/*3243*` and `.loops/.history/**/*3243*` both empty). BUG-3243's own `## Session Log` records `/ll:wire-issue` 19:42:10, `/ll:verify-issues` 19:43:38, `/ll:confidence-check` 19:45:58 — a ~4-minute span across three of the four states, with no `/ll:refine-issue` entry logged — consistent with but not itself establishing the cited numbers.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Types
- `verify_verdict: VALID|NON_VALID` — frontmatter field written by `verify_issue` (`refine-to-ready-issue.yaml:279-287`), read by `ll-issues check-verify-verdict`
- `decision_needed` / `missing_artifacts` / `implementation_order_risk` / `spike_needed` — frontmatter flags written by `apply_flags_from_notes()` (`scripts/little_loops/cli/issues/set_flags.py:238-331`), each read via `ll-issues check-flag <flag>` (`fragment: shell_exit`)
- Any new adversarial verdict this issue introduces must follow the same shape: a frontmatter-persisted enum/bool, not a value read directly off LLM output — this is required by the "write-verdict/read-verdict" convention documented in Integration Map above, not optional stylistic preference

### Signatures
- `cmd_check_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int` — `scripts/little_loops/cli/issues/check_verify_verdict.py:41`, invoked as `ll-issues check-verify-verdict ${captured.issue_id.output}`
- `apply_flags_from_notes(config: BRConfig, issue_id: str, notes: str | None, dry_run: bool) -> FlagResult` — `scripts/little_loops/cli/issues/set_flags.py:238-331`, invoked via `ll-issues set-flags [ISSUE-ID]` from `skills/confidence-check/SKILL.md:429-437`

### Call Path
`apply_flags_from_notes` (`scripts/little_loops/cli/issues/set_flags.py:238`) -> `cmd_set_flags` (`:360`, invoked as `ll-issues set-flags`) writes `decision_needed` to frontmatter -> `cmd_check_verify_verdict` (`scripts/little_loops/cli/issues/check_verify_verdict.py:41`, invoked as `ll-issues check-verify-verdict`) is the sibling read-side pattern a new adversarial verdict's own read-gate would mirror. The FSM-level routing gap these resolve against (state names, not Python symbols, so not cited as anchors here) is documented with exact `refine-to-ready-issue.yaml` line numbers in Integration Map above: `check_outcome`'s `on_yes` reaches `done` without passing through `check_decision_needed`.

### Decision Rules
N/A — this issue's own Open Questions (new adversarial state vs. routable risk factors; this loop vs. widened verify-issues mandate; model tier) are the unresolved decision inputs a spike must settle before any Decision Rules can be specified. Populating this subsection now would invent the answer the Acceptance Criteria explicitly require a design decision to produce first.

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


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-17_

**Readiness Score**: 50/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 9/100 → VERY LOW

### Concerns
- Hard override: `ll-issues check-design ENH-3250` fails (Program Design gate not
  satisfied) — the issue's own `## Proposed Solution` is "TBD - requires
  investigation" by design, since this is explicitly a spike-first,
  design-decision-first issue (per Scope Boundaries).
- Hard override: `blocked_by: ENH-3248` is unresolved (status `open`, not
  `done`/`completed`/`cancelled`). The issue's Related Issues section says
  ENH-3248 should be "designed together" with this one.

### Gaps to Address
- All three Open Questions (new adversarial state vs. routable risk factors;
  scope in `refine-to-ready-issue` vs. widened `verify-issues` mandate; model
  tier) remain unresolved — Acceptance Criterion 1 explicitly requires these be
  answered via `/ll:spike` before any implementation, which has not yet run.
- No concrete Proposed Solution exists to assess Architecture Compliance or
  Change Surface against.

### Outcome Risk Factors
- Approach is fundamentally undetermined (three unresolved design decisions),
  so complexity, test coverage, and change surface cannot be meaningfully
  estimated from the current issue content.
- Depends on ENH-3248's design outcome per the issue's own text, compounding
  uncertainty until that dependency resolves.

## Session Log
- `/ll:spike (declined — decision ambiguity, not a mechanism risk)` - 2026-08-17T21:38:52 - `71139c18-5abb-4bd8-97d3-e9c138f42ce3.jsonl`
- `/ll:refine-issue` - 2026-08-17T21:36:15 - `d6cdea96-295f-4261-adf4-630f2bde0344.jsonl`
- `/ll:confidence-check` - 2026-08-17T21:34:52 - `878d0e98-a6e4-41e7-80a9-53a56e3db6f7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:54 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:capture-issue` - 2026-08-17T20:04:12 - `86ab77f1-d20d-487b-9f55-2f4d8abf9a06.jsonl`
