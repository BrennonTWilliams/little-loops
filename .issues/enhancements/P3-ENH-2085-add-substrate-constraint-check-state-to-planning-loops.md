---
id: ENH-2085
title: Add substrate constraint check state to planning loops
type: ENH
priority: P3
status: open
captured_at: "2026-06-10T18:12:09Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
relates_to: [EPIC-2087]
---

# ENH-2085: Add substrate constraint check state to planning loops

## Summary

Planning loops (`iterate-plan`, `create-loop`) optimize for logical correctness without explicitly checking whether each proposed action is feasible in the target execution environment. An unsound plan may only surface as a runtime failure in Claude Code, Codex, or a constrained shell. This enhancement adds an optional `check_substrate` state to the `create-loop` wizard's planning template that enumerates environment constraints and validates proposed actions before execution.

## Current Behavior

Planning loops reason about the correctness of their proposed plan but do not validate whether each action is feasible under the execution substrate's constraints (shell command availability, MCP tool access, file write permissions, token budget). Infeasible actions are discovered only at execution time, often producing opaque failures.

## Expected Behavior

An optional `check_substrate` state in the `create-loop` wizard's planning branch prompts the agent to enumerate known target-environment constraints and explicitly validate each proposed action against them. If any action is flagged infeasible, the state routes to `revise_plan`; otherwise execution proceeds normally. The state shape is documented in `HARNESS_OPTIMIZATION_GUIDE.md` as a recommended addition for loops targeting non-standard execution environments.

## Motivation

Planning loops (iterate-plan, create-loop) optimize for correctness without explicitly reasoning about execution environment constraints. Approaches that are sound in principle can fail in practice because Claude Code, Codex, or shell environments have specific limitations — just as a correct algorithm can be impractical in a constrained target language.

## Proposed Solution

Add an optional `check_substrate` state to the `create-loop` wizard's planning template that prompts the agent to enumerate the target environment's known constraints (shell command availability, MCP tool access, file write permissions, token budget) and explicitly validate that each proposed action is feasible under those constraints before committing to the plan. The state should route to `revise_plan` if any action is flagged infeasible. Document this state shape in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` as a recommended addition for loops targeting non-standard execution environments.

## Implementation Steps

1. Define `check_substrate` state template in `create-loop` wizard planning branch
2. Prompt template should enumerate: shell availability, MCP tool access, file write permissions, token budget
3. Add routing: feasibility check passes → proceed to apply; any action infeasible → route to `revise_plan`
4. Make the state optional via a wizard prompt ("Does this loop target a non-standard execution environment?")
5. Document `check_substrate` in `HARNESS_OPTIMIZATION_GUIDE.md` with example infeasibility scenarios

## Acceptance Criteria

- [ ] `create-loop` wizard optionally inserts a `check_substrate` state into the planning template
- [ ] State enumerates environment constraints and validates each proposed action
- [ ] Infeasible actions route to `revise_plan`
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


## Session Log
- `/ll:format-issue` - 2026-06-11T20:10:06 - `c7137f2d-4a6a-4394-aed0-6e8fc886629b.jsonl`
