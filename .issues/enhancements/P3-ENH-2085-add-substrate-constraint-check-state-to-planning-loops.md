---
id: ENH-2085
title: Add substrate constraint check state to planning loops
type: ENH
priority: P3
status: open
captured_at: "2026-06-10T18:12:09Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
---

# ENH-2085: Add substrate constraint check state to planning loops

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

## Status

open
