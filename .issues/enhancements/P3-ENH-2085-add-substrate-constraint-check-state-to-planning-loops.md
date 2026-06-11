---
id: ENH-2085
title: Add substrate constraint check state to planning loops
type: ENH
priority: P3
status: open
captured_at: '2026-06-10T18:12:09Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
relates_to:
- EPIC-2087
confidence_score: 86
outcome_confidence: 70
score_complexity: 20
score_test_coverage: 12
score_ambiguity: 13
score_change_surface: 25
decision_needed: false
---

# ENH-2085: Add substrate constraint check state to planning loops

## Summary

Planning loops (`iterate-plan`, `create-loop`) optimize for logical correctness without explicitly checking whether each proposed action is feasible in the target execution environment. An unsound plan may only surface as a runtime failure in Claude Code, Codex, or a constrained shell. This enhancement adds an optional `check_substrate` state to the `create-loop` wizard's planning template that enumerates environment constraints and validates proposed actions before execution.

## Current Behavior

Planning loops reason about the correctness of their proposed plan but do not validate whether each action is feasible under the execution substrate's constraints (shell command availability, MCP tool access, file write permissions, token budget). Infeasible actions are discovered only at execution time, often producing opaque failures.

## Expected Behavior

An optional `check_substrate` state in the `create-loop` wizard's planning branch prompts the agent to enumerate known target-environment constraints and explicitly validate each proposed action against them. If any action is flagged infeasible, the state routes to `plan`; otherwise execution proceeds normally. The state shape is documented in `HARNESS_OPTIMIZATION_GUIDE.md` as a recommended addition for loops targeting non-standard execution environments.

## Motivation

Planning loops (iterate-plan, create-loop) optimize for correctness without explicitly reasoning about execution environment constraints. Approaches that are sound in principle can fail in practice because Claude Code, Codex, or shell environments have specific limitations — just as a correct algorithm can be impractical in a constrained target language.

## Proposed Solution

Add an optional `check_substrate` state to the `create-loop` wizard's planning template that prompts the agent to enumerate the target environment's known constraints (shell command availability, MCP tool access, file write permissions, token budget) and explicitly validate that each proposed action is feasible under those constraints before committing to the plan. The routing target for infeasible actions was an open decision resolved below.

### Option A — Route to existing `plan` state

> **Selected:** Option A — Route to existing `plan` state — matches the canonical `on_no: plan` pattern from `loop-types.md` and `harness-plan` wizard template; no new state required.

When `check_substrate` flags any action infeasible, route back via `on_no: plan`. The `plan` state is already positioned as the re-entrant planning state in all wizard-generated templates (`loop-types.md:1186`, `harness-plan-research-implement-report.yaml:54`).

### Option B — Define new `revise_plan` co-deliverable

When `check_substrate` flags any action infeasible, route to a dedicated `revise_plan` state that carries the infeasibility diagnosis as context. Follows the `incremental-refactor.yaml` rollback-recovery pattern.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-11.

**Selected**: Option A — Route to existing `plan` state

**Reasoning**: `loop-types.md:1186` and `harness-plan-research-implement-report.yaml:54` both establish `on_no: plan` as the canonical routing pattern when a gate-check fails in a planning loop. No `revise_plan` state exists anywhere in the codebase (zero matches across all 20+ loop YAMLs), while the `on_no: plan` back-link appears in 3+ templates. Option B would introduce a new state with no precedent in wizard-generated planning loops and unnecessarily expands scope.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Route to `plan` | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |
| Option B — New `revise_plan` state | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |

**Key evidence**:
- Option A: `loop-types.md:1186` shows `# on_no: plan` in the optional `review_plan` HITL gate template; `harness-plan-research-implement-report.yaml:54` shows the same. Zero instances of `revise_plan` in the codebase.
- Option B: `incremental-refactor.yaml:56` uses a dedicated `replan` state, but in rollback-recovery context (different from feasibility checking before commitment).

Document the `check_substrate` state shape (with `on_no: plan` routing) in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` as a recommended addition for loops targeting non-standard execution environments.

## Implementation Steps

1. Define `check_substrate` state template in `create-loop` wizard planning branch
2. Prompt template should enumerate: shell availability, MCP tool access, file write permissions, token budget
3. Add routing: feasibility check passes → proceed to apply; any action infeasible → route to `plan`
4. Make the state optional via a wizard prompt ("Does this loop target a non-standard execution environment?")
5. Document `check_substrate` in `HARNESS_OPTIMIZATION_GUIDE.md` with example infeasibility scenarios

## Acceptance Criteria

- [ ] `create-loop` wizard optionally inserts a `check_substrate` state into the planning template
- [ ] State enumerates environment constraints and validates each proposed action
- [ ] Infeasible actions route to `plan`
- [ ] `HARNESS_OPTIMIZATION_GUIDE.md` documents the state shape and example use cases

## Scope Boundaries

- **In scope**: Adding `check_substrate` as an optional state to `create-loop` wizard planning branch; documenting the state shape with example infeasibility scenarios in `HARNESS_OPTIMIZATION_GUIDE.md`
- **Out of scope**: Automatic substrate detection via tooling (the state prompts the agent, not an auto-detect mechanism); retrofitting existing loops to include this state; changes to the FSM executor or runner

## Integration Map

### Files to Modify
- `skills/create-loop/SKILL.md` — wizard planning branch: add optional `check_substrate` state template
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — document `check_substrate` state shape and example use cases

### Dependent Files (Callers/Importers)
- TBD — `grep -r "create-loop" scripts/little_loops/` to find any automation that invokes the wizard

### Similar Patterns
- `loops/iterate-plan.yaml` — existing planning loop; `check_substrate` state shape should be consistent with its state conventions

### Tests
- TBD — `scripts/tests/test_builtin_loops.py` may need a test for loops that include `check_substrate`

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — primary documentation target

### Configuration
- N/A

## Impact

- **Priority**: P3 — Planning loops work correctly today; this is a quality-of-life guard that prevents hard-to-debug substrate failures at execution time
- **Effort**: Small — Adding a wizard state template and updating one guide document; no FSM executor changes required
- **Risk**: Low — The state is optional and opt-in via a wizard prompt; existing loops are entirely unaffected
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `planning`

## Status

**Open** | Created: 2026-06-10 | Priority: P3


## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-11_

**Readiness Score**: 86/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors
- **Routing target — open decision**: `revise_plan` does not exist in any loop template (verified against `loop-types.md` and all built-in loops in `scripts/little_loops/loops/`). Resolve before implementing: route infeasible actions back to the existing `plan` state, or define a new `revise_plan` state as a co-deliverable.
- **Integration Map gap**: `skills/create-loop/loop-types.md` is not listed in Files to Modify, but the actual YAML templates for all loop types (including the specialist-pipeline planning branch) live there (2071 lines). Any wizard change in `SKILL.md` that generates a new optional state must be paired with a matching template addition in `loop-types.md`.
- **Test strategy TBD**: No planned test for the wizard's optional `check_substrate` state generation; `test_builtin_loops.py` tests loop execution, not wizard output generation.

## Session Log
- `/ll:decide-issue` - 2026-06-11T20:43:15 - `434467be-41b0-476c-9ed1-087b016d3835.jsonl`
- `/ll:decide-issue` - 2026-06-11T20:32:12 - `8b1aefbe-0c6a-4b37-85dc-00aedc97dd6e.jsonl`
- `/ll:format-issue` - 2026-06-11T20:10:06 - `c7137f2d-4a6a-4394-aed0-6e8fc886629b.jsonl`
- `/ll:confidence-check` - 2026-06-11T00:00:00 - `6df11c95-7181-4420-9d2a-7fc53f9625e3.jsonl`
- `/ll:confidence-check` - 2026-06-11T00:00:00 - `d45a56f0-fc7e-4c0a-ae3b-49ad79f1097a.jsonl`
