---
id: FEAT-3039
title: Advisor FSM stall escalation and routable verdicts
type: FEAT
parent: EPIC-3041
priority: P4
status: open
testable: true
discovered_date: 2026-08-03
depends_on:
- FEAT-3044
- FEAT-3038
labels:
- planning-hub
---

# FEAT-3039: Advisor FSM stall escalation and routable verdicts

## Summary

Slice 3 of the host-agnostic advisor (FEAT-3037). Let an FSM loop escalate to
the advisor when a stall evaluator fires, and make the consult verdict a
first-class routable evaluator output so a state can branch on
`recommendation` / `confidence` rather than only logging it.

## Current Behavior

- `evaluate_diff_stall`, `evaluate_score_stall`, `evaluate_action_stall`, and
  `evaluate_open_question_stall` (`fsm/evaluators.py`) all produce verdicts that
  a loop can route on today, but the only available responses are terminate,
  retry the same cheap model, or hand off.
- There is **no `on_stall` key in the FSM schema** — stall handling goes through
  the ordinary transition table. Any escalation must be expressed that way.
- After FEAT-3038 the advisor is reachable from hooks and the confidence gate,
  but not from inside a loop's state machine.
- `evaluate_llm_structured` returns a verdict + details; there is no evaluator
  whose output *is* an advisor consult.

## Expected Behavior

- A loop can declare a state that consults the advisor and routes on the
  verdict, reachable from any stall evaluator's `stall` branch through the
  normal transition table.
- A new `advisor_consult` evaluator type runs a consult and produces a routable
  verdict, with `confidence` available for threshold routing the same way
  `llm_structured` exposes its confidence today.
- The consult context includes the stuck-state context (recent action output,
  the stall evaluator's details) — assembled explicitly, never an auto-slurp.
- `ll-loop validate` accepts the new evaluator type and, per MR-1, does **not**
  flag an advisor consult as a substitute for a non-LLM signal — the stall
  evaluator that routes into it *is* the external signal.

## Use Case

A `refine-to-ready-issue` loop hits `score_stall` on its third iteration: the
readiness score has not improved. Rather than terminating or burning a fourth
identical Sonnet pass, the loop routes to an `advisor_consult` state. Opus sees
the stuck-state context and returns `recommendation: "the criteria prompt is
underspecified — the artifact is passing but the gate asks for evidence the
artifact format cannot carry"` with `confidence: 0.85`. The loop routes on that
verdict to a prompt-repair state instead of another refine iteration.

## Proposed Solution

Add `advisor_consult` alongside the existing evaluator types in
`fsm/evaluators.py` (registered in the dispatch at `evaluators.py:~1830-1944`,
where `score_stall` and friends are wired), delegating to
`little_loops.advisor.consult()` with the signal derived from the state that
routed into it.

Verdict mapping: the evaluator's routable verdict comes from a configurable
map on the state (e.g. `proceed` / `revise` / `abort`), with `confidence`
surfaced in `details` for threshold routing. Falling back to a neutral verdict
on consult failure keeps a failed consult from stranding the loop.

Budget and signal accounting flow through FEAT-3038's `should_consult` /
`record_consult`, so loop-driven consults count against the same per-task cap.

Determinism: consults stay excluded from the resume/replay input hash
(established in FEAT-3037), so a resumed run does not re-bill or re-consult.

## Program Design

### Types

- `AdvisorConsultConfig: {question: str, context_from: list[str], verdict_map: dict[str, str], signal: str | None}`

### Signatures

- `evaluate_advisor_consult(output: str, *, question: str, verdict_map: dict[str, str], signal: str, timeout: int) -> EvaluationResult`
- `_advisor_context(state_name: str, output: str, details: dict) -> str`

### Call Path

`FSM executor` -> evaluator dispatch (`eval_type == "advisor_consult"`) -> `evaluate_advisor_consult` -> `should_consult` -> `little_loops.advisor.consult` -> `EvaluationResult`

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/evaluators.py` — `evaluate_advisor_consult` + the
  two dispatch registration sites.
- `scripts/little_loops/fsm/schema.py` — evaluator type + config validation.
- `scripts/little_loops/fsm/validation/evaluator_rules.py` — `ll-loop validate`
  support for the new evaluator type.
- `scripts/little_loops/fsm/validation/meta_rules.py` — ensure MR-1 (`meta-loop
  must have at least one non-LLM evaluator`, `meta_rules.py:74-76`) does not
  misfire on an advisor state paired with a stall evaluator.
- `scripts/little_loops/cli/loop/info.py` — display name for the new type
  (alongside the `score_stall` entry at ~line 1452).

### Dependent Files (Callers/Importers)

- `scripts/little_loops/advisor.py` — signal/budget accounting reused as-is.
- Built-in loops under `scripts/little_loops/loops/` — none change in this
  slice; adoption is opt-in.

### Tests

- `scripts/tests/test_fsm_evaluators.py` — verdict mapping, confidence in
  details, neutral fallback on consult failure, budget-exhausted path.
- `scripts/tests/test_builtin_loops.py` / loop validation tests — the new type
  validates; MR-1 does not flag a stall→advisor route.

### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — stall escalation as a sanctioned
  pattern and its relationship to MR-1.
- `docs/reference/API.md` — new evaluator.

## Acceptance Criteria

1. A loop state with `evaluate: {type: advisor_consult, ...}` runs a consult and
   returns a routable verdict drawn from its `verdict_map`.
2. `confidence` is present in `EvaluationResult.details` and usable for
   threshold routing.
3. A stall evaluator's `stall` branch can transition into an advisor state
   through the ordinary transition table — no new schema key is introduced.
4. A failed, timed-out, or budget-exhausted consult returns the configured
   neutral verdict; the loop never strands.
5. Loop-driven consults increment the FEAT-3038 per-task counter and carry a
   signal naming the routing state.
6. `ll-loop validate` accepts the type, and MR-1 does not flag a
   stall-evaluator→advisor route as an unpaired LLM judgment.
7. A resumed run does not re-issue a consult recorded before the resume point.
8. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` pass.

## Impact

- **Priority**: P4 — genuinely useful but strictly downstream of a working,
  budget-counted advisor. Loops function without it.
- **Effort**: Medium — the evaluator itself is small; validation-rule
  interaction and the resume/determinism path are where the care goes.
- **Risk**: Medium — adds a network call inside the FSM execution loop. Mitigated
  by neutral-verdict fallback and opt-in adoption.
- **Breaking Change**: No — new evaluator type; no existing loop changes.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md#the-design-rules-mr-1mr-14`

## Status

**Open** | Created: 2026-08-03 | Priority: P4


## Session Log
- `/ll:verify-issues` - 2026-08-04T21:29:47 - `e72897bf-a708-4dcd-aeaa-907564ef9e34.jsonl`
