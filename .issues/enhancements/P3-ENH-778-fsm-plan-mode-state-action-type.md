---
discovered_date: 2026-03-16
discovered_by: capture-issue
---

# ENH-778: Add `plan_call` Action Type for FSM States

## Summary

Introduce a new `action_type: plan_call` for FSM loop states that executes Claude in Plan Mode, captures the resulting plan to a temporary file, and makes that file path available for downstream states to consume — enabling loops that plan before they act.

## Motivation

The current FSM action types (`prompt`, `slash_command`, `shell`, `mcp_tool`) all execute actions directly. There is no way to run a planning step where Claude reasons about what to do next, captures that plan, and routes based on the plan content. This blocks loops from having a deliberate "think → act" rhythm — a common pattern in agentic workflows.

A `plan_call` state would allow a loop to ask Claude to produce a structured plan (e.g., which issues to create, what refactors are needed), write that plan to a known temp path, and then a follow-up state reads the plan and drives the remaining loop transitions.

## Current Behavior

- `StateConfig.action_type` is `Literal["prompt", "slash_command", "shell", "mcp_tool"] | None` (`schema.py:211`)
- All action types execute immediately; none enter Claude Code's Plan Mode
- `EnterPlanMode` / `ExitPlanMode` are available as Claude Code tools but are not wired into the FSM executor

## Expected Behavior

A state configured with `action_type: plan_call` should:

1. Enter Plan Mode (analogous to calling `EnterPlanMode`)
2. Run the `action` string as the planning prompt
3. Exit Plan Mode without executing the plan
4. Write the plan text to a temp file (e.g., `/tmp/ll-loop-plan-<run_id>.md`)
5. Store the file path in a named `capture` variable (or a conventional `$plan_file` variable)
6. Transition to the next state, which can read the file and act on it (create issues, execute steps, etc.)

Example YAML:

```yaml
states:
  plan:
    action: "Analyze the failing tests and produce a step-by-step fix plan"
    action_type: plan_call
    capture: plan_file
    next: execute_plan

  execute_plan:
    action: "Read ${plan_file} and implement each step"
    action_type: prompt
    on_success: done
    on_failure: plan
```

## Implementation Notes

- Add `"plan_call"` to the `action_type` literal in `schema.py:211` and `fsm-loop-schema.json:77`
- In `executor.py`, branch on `action_type == "plan_call"` in the action dispatch section (~line 895)
- The executor should invoke `EnterPlanMode`, run the prompt, capture the plan output, call `ExitPlanMode`, and write the result to a temp file
- The temp file path should be injected into the state's `capture` variable (defaulting to `plan_file` if not set)
- Validation: `plan_call` states that set `capture` and have a `next`/`on_success` transition are valid; warn if no downstream state references the captured variable
- Consider whether the plan file should be cleaned up at loop end or preserved for debugging (suggest: preserve with `--debug`, clean otherwise)

## Acceptance Criteria

- [ ] `action_type: plan_call` is valid in loop YAML (schema validation passes)
- [ ] Executor enters Plan Mode, runs the prompt, captures output, exits Plan Mode
- [ ] Plan text is written to a temp file; path stored in `capture` variable
- [ ] A downstream state can reference the file path via `${plan_file}` (or configured name)
- [ ] Validation warns if `plan_call` state has no `capture` and no downstream consumer
- [ ] Example loop YAML demonstrating the plan → act pattern added to docs or examples

## Related

- `scripts/little_loops/fsm/schema.py:211` — `action_type` literal
- `scripts/little_loops/fsm/executor.py:895` — action type dispatch
- `scripts/little_loops/fsm/validation.py:190` — action_type validation
- `scripts/little_loops/fsm/fsm-loop-schema.json:77` — JSON schema for action_type

## Session Log
- `/ll:capture-issue` - 2026-03-16T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71056193-bbfc-4baa-8002-42476d663c64.jsonl`
