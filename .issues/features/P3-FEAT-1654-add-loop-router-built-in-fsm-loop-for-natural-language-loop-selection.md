---
id: FEAT-1654
type: FEAT
priority: P3
status: open
discovered_date: '2026-05-24'
discovered_by: capture-issue
captured_at: '2026-05-24T02:32:39Z'
---

# FEAT-1654: Add `loop-router` built-in FSM loop for natural language loop selection and sub-loop dispatch

## Summary

Add a new built-in FSM loop `loop-router` that accepts a natural language description of a task or goal, reasons over the catalog of available built-in and project-level FSM loops, selects the best fit, runs it as a sub-loop with derived parameters, then reviews the sub-loop's output and presents a synthesized result to the user. Provides a single entry point for users who know *what they want done* but not *which loop to run*.

## Current Behavior

- Users must already know the name of the loop they want and call `ll-loop run <name>` directly.
- `/ll:loop-suggester` analyzes message history to suggest *new loops to author*, not which existing loop to dispatch right now (FEAT-219, FEAT-716).
- `ll-loop next-loop` (FEAT-1546, done) picks the next loop based on execution history under `.loops/.history/`, not from a natural language goal.
- `general-task.yaml` exists as a generic task harness but does not perform loop selection — it just runs a single agent over the input.
- There is no path from "natural language goal" → "best-fit existing loop" → "executed sub-loop" → "reviewed result".

## Expected Behavior

`ll-loop run loop-router --input "<natural language goal>"` (or `/loop /loop-router <goal>`):

1. **Catalog** — collect all available loops: built-ins under `scripts/little_loops/loops/*.yaml` and project loops under `loops/*.yaml` (excluding `loops/lib/` fragments per [[feedback_nested_loops_runnable]]). Read each loop's name, description, and accepted inputs.
2. **Reason** — use an LLM evaluator (Tier 2, per FEAT-044) to score candidate loops against the natural language input. Pick the top candidate and derive sensible parameters (input string, `--context key=value`) from the goal text.
3. **Confirm (optional)** — if confidence is below a threshold or `--auto=false`, surface the top 1-3 candidates to the user for selection. With `--auto=true` (default for unattended use), proceed with the top pick.
4. **Dispatch** — invoke the selected loop as a sub-loop via the existing sub-loop mechanism (`run_sub_loop` state type, see FEAT-1311 typed parameter contract).
5. **Review** — after the sub-loop terminates, read its final state output and `.loops/.history/<run>/` artifacts. Synthesize a concise summary of what was attempted, what was produced, and whether it succeeded.
6. **Present** — emit a structured result (human summary + machine-readable JSON with `loop_chosen`, `confidence`, `sub_loop_output_path`, `success`).

## Motivation

The loop catalog has grown to 30+ built-ins plus project loops. Even experienced users default to running 2-3 familiar loops because picking the right one from a long list is friction. New users have no entry point — they know they want to "research X" or "refine that issue" but don't know whether to reach for `deep-research`, `recursive-refine`, `issue-refinement`, `rn-plan`, or something else.

`loop-router` collapses that decision into a single command. It also unlocks higher-level automation: `/loop`, scheduled agents, and on-completion hooks can dispatch *intent* ("research the auth migration") instead of hard-coding loop names, so adding a new loop to the catalog automatically makes it available to those entry points.

**Why:** Catalog growth (30+ loops) is making manual loop selection a bottleneck and a barrier to onboarding.
**How to apply:** This is a routing/dispatch layer, not a replacement for individual loops — keep selection logic in `loop-router` and leave the actual work to the sub-loops it picks.

## Proposed Solution

Add `scripts/little_loops/loops/loop-router.yaml` with these states (rough sketch — refine during design):

1. `discover_loops` — shell out to list built-in + project loops, parse names/descriptions/inputs into a catalog JSON.
2. `score_candidates` — Tier 2 LLM evaluator: input = (user goal, loop catalog), output = ranked list with confidence scores and proposed parameters.
3. `select_loop` — pick top candidate; if confidence < threshold and `auto != true`, transition to `present_choices` (HITL state pattern, see `hitl-compare.yaml`); else go to `dispatch`.
4. `present_choices` — HITL state showing top 3 with reasoning; user picks one.
5. `dispatch` — `run_sub_loop` state, passing the chosen loop name and derived params via the typed sub-loop contract (FEAT-1311).
6. `review` — read sub-loop output + history artifacts; LLM synthesizes a result summary.
7. `present_result` — emit final structured output.

Reuse existing primitives wherever possible:
- Catalog discovery: lift logic from `/ll:loop-suggester --from-commands` and `ll-loop list`.
- Sub-loop dispatch: use `run_sub_loop` state type already wired by FEAT-1311 / FEAT-837.
- HITL fallback: model on `hitl-compare.yaml` and `hitl-md.yaml`.
- Review/synthesis: reuse the Tier 2 evaluator pattern (FEAT-044).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/loop-router.yaml` (new)
- Documentation references in `docs/` for built-in loops index (if one exists)

### Dependent Files (Callers/Importers)
- None at creation time; consumers are users and `/loop`/scheduled agents that may later default to `loop-router` for natural-language dispatch.

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml` — generic single-agent harness (closest existing primitive but doesn't route)
- `scripts/little_loops/loops/recursive-refine.yaml` — multi-state loop with sub-loop dispatch shape
- `scripts/little_loops/loops/hitl-compare.yaml` — HITL state pattern for user confirmation
- `scripts/little_loops/loops/outer-loop-eval.yaml` — orchestrating-loop pattern (FEAT-933)

### Tests
- `scripts/tests/loops/test_loop_router.py` (new) — schema validation, dry-run with mocked catalog, end-to-end against a small fixture catalog
- Possibly extend `ll-loop validate` coverage if router introduces new state-type combinations

### Documentation
- `docs/ARCHITECTURE.md` — note router as the recommended natural-language entry point
- `docs/reference/API.md` — if a public Python helper is exposed
- Loop index / catalog docs (location TBD)

### Configuration
- May want a config knob like `orchestration.router.confidence_threshold` and `orchestration.router.exclude_loops: []` in `.ll/ll-config.json`.

## Implementation Steps

1. **Design the YAML** — draft `loop-router.yaml` states, transitions, and inputs; validate with `ll-loop validate`.
2. **Catalog discovery** — implement (or reuse) catalog enumeration that excludes `loops/lib/` and surfaces name + description + inputs.
3. **Scoring + selection** — wire the Tier 2 evaluator with a prompt that ranks loops against the goal and proposes parameters.
4. **Sub-loop dispatch** — connect to `run_sub_loop` via the typed parameter contract (FEAT-1311). Handle missing/partial params gracefully.
5. **HITL fallback** — confidence-gated branch to present 1-3 choices; user picks or cancels.
6. **Review state** — read sub-loop output + `.loops/.history/<run>/` and synthesize a result summary.
7. **Tests + docs** — unit and end-to-end tests; update relevant docs.
8. **Verification** — run against a handful of representative goals (research, refine an issue, scan codebase, build greenfield) and confirm correct routing.

## Use Case

> "I want to dig into how our auth middleware handles refresh tokens — research the patterns and current pitfalls."

`loop-router` ingests this, scores candidates, picks `deep-research` (FEAT-1540), derives `--input "auth middleware refresh token handling: patterns and pitfalls"`, dispatches it as a sub-loop, then summarizes the produced research report and points the user to the artifact path.

> "Refine FEAT-1654 so it's ready to implement."

Router picks `issue-refinement` (or `rn-refine` per [[project_recursive_refine_standalone]]) and dispatches it with the issue ID parsed from the goal.

## API/Interface

```yaml
# loops/loop-router.yaml (sketch)
name: loop-router
description: Route a natural language goal to the best-fit FSM loop and run it.
inputs:
  goal: "Natural language description of the task or outcome."
  auto: "If true, dispatch top candidate without confirmation. Default true."
  confidence_threshold: "Min confidence to skip HITL. Default 0.7."
  exclude: "List of loop names to exclude from candidates."
states:
  discover_loops: { ... }
  score_candidates: { ... }
  select_loop: { ... }
  present_choices: { ... }   # HITL branch
  dispatch: { type: run_sub_loop, ... }
  review: { ... }
  present_result: { type: terminal }
```

Output schema (structured):

```json
{
  "loop_chosen": "deep-research",
  "confidence": 0.86,
  "parameters": { "input": "..." },
  "sub_loop_run_id": ".loops/.history/2026-05-24T...-deep-research/",
  "success": true,
  "summary": "Produced a research report at .../report.md covering ..."
}
```

## Edge Cases

- **No good match** — all candidates score below the floor: report "no suitable loop" with the top-3 weak candidates and exit cleanly, do not force-dispatch.
- **Ambiguous goal** — two or more candidates score within a small delta: always go to HITL regardless of `auto`.
- **Sub-loop fails** — review state must surface the failure (not retry by default) and include the sub-loop's error in the summary.
- **Project loop with same name as built-in** — prefer project loop (matches existing precedence elsewhere).
- **Goal includes a loop name** — short-circuit ("just run `autodev`"): skip scoring, dispatch directly.
- **Recursion guard** — `loop-router` must not select `loop-router` as the sub-loop (catalog filter).

## Acceptance Criteria

- [ ] `scripts/little_loops/loops/loop-router.yaml` exists and passes `ll-loop validate`.
- [ ] `ll-loop run loop-router --input "..."` produces a structured result and a sub-loop run under `.loops/.history/`.
- [ ] Catalog includes both built-in and project loops, excludes `loops/lib/` fragments and `loop-router` itself.
- [ ] When confidence < threshold, HITL surfaces top 3 candidates with reasoning.
- [ ] Final output includes `loop_chosen`, `confidence`, `sub_loop_run_id`, `success`, and a human summary.
- [ ] Test coverage for: routing correctness on 3+ representative goals, no-match path, HITL path, sub-loop failure path.
- [ ] Docs reference `loop-router` as the recommended natural-language entry point.

## Impact

- **Priority**: P3 — meaningful UX improvement and unlocks downstream automation, but not blocking. Several similar built-in loops (`deep-research`, `rn-plan`) shipped at P3.
- **Effort**: Medium — composes existing primitives (catalog discovery, Tier 2 evaluator, `run_sub_loop`, HITL fragments). Most work is in the routing prompt and the review/synthesis state.
- **Risk**: Low-medium — the failure mode is "picks the wrong loop", which is recoverable (user re-runs with explicit loop name). Watch for recursion (router → router) and prompt-injection in the goal text.

## Related Key Documentation

| Document | Why Relevant |
|----------|-------------|
| `docs/ARCHITECTURE.md` | Where router fits in the FSM/loop architecture |
| `docs/reference/API.md` | Sub-loop dispatch and state-type APIs |
| `.claude/CLAUDE.md` | Built-in loop conventions and CLI tooling overview |

## Labels

built-in-loop, fsm, routing, dispatch, sub-loop

## Session Log
- `/ll:format-issue` - 2026-05-24T02:35:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9eaefb33-d00d-4955-9bd3-f90c748f44ef.jsonl`
- `/ll:capture-issue` - 2026-05-24T02:32:39Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ba66e45-43d3-4537-a63b-088dff9cbb2f.jsonl`

---

**Open** | Created: 2026-05-24 | Priority: P3
