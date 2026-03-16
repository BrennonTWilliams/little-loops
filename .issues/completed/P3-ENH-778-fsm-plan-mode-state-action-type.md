---
id: ENH-778
title: "Add plan_call Action Type for FSM States"
type: ENH
priority: P3
status: wont_do
discovered_date: 2026-03-16
discovered_by: capture-issue
confidence_score: 90
outcome_confidence: 48
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

## Integration Map

### Files to Modify

| File | Change |
|------|--------|
| `scripts/little_loops/fsm/schema.py:211` | Add `"plan_call"` to the `Literal["prompt", "slash_command", "shell", "mcp_tool"]` type |
| `scripts/little_loops/fsm/fsm-loop-schema.json:77-81` | Add `"plan_call"` to `"enum": [...]` array; update `description` |
| `scripts/little_loops/fsm/executor.py:893-904` | Add `if state.action_type == "plan_call": return "plan_call"` branch in `_action_mode()` |
| `scripts/little_loops/fsm/executor.py:636-647` | Add `elif action_mode == "plan_call":` branch in `_run_action()` — enters plan mode, runs prompt, writes temp file, returns `ActionResult` with file path as `output` |
| `scripts/little_loops/fsm/executor.py:762-795` | Add `plan_call` branch to default evaluator selection (use `evaluate_llm_structured` or `evaluate_exit_code` for the write success) |
| `scripts/little_loops/fsm/validation.py:176-198` | In `_validate_state_action()`, warn if `action_type == "plan_call"` and `state.capture` is `None` |

### Dependent Files (Callers/Importers that reference action_type)

- `scripts/little_loops/cli/loop/_helpers.py` — references action_type for display; may need `plan_call` label
- `scripts/little_loops/cli/loop/info.py` — references action_type for display
- `scripts/little_loops/cli/loop/layout.py` — references action_type for display
- `scripts/little_loops/cli/loop/testing.py` — references action_type; may need mock support

### Tests

- `scripts/tests/test_fsm_executor.py:233-531` — `TestActionType` / `TestActionTypeMcpTool` classes; add `TestActionTypePlanCall` following `TestActionTypeMcpTool` pattern (patches `_run_subprocess` since `plan_call` bypasses `action_runner`)
- `scripts/tests/test_fsm_executor.py:585-869` — `TestCapture` / `TestCaptureWorkflow`; add test that `plan_call` capture stores file path in `captured["varname"]["output"]`
- `scripts/tests/test_fsm_schema.py:1501-1610` — `TestMcpToolSchema`; add `TestPlanCallSchema` following same pattern
- `scripts/tests/test_builtin_loops.py` — validates all loop YAMLs; will need a new example fixture

### Documentation / Skill Files

- `docs/guides/LOOPS_GUIDE.md` — add `plan_call` to action type reference table
- `skills/create-loop/reference.md` — add `plan_call` entry to action type docs
- `skills/create-loop/loop-types.md` — add "plan → act" loop type

---

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Variable Reference Syntax Correction

The example YAML in **Expected Behavior** uses `${plan_file}`, but the actual interpolation namespace syntax in `interpolation.py:25` is `${namespace.path}`. The correct reference for a captured variable named `plan_file` is:

```
${captured.plan_file.output}
```

The `captured` namespace resolves via `interpolation.py:78-82`: `self._get_nested(self.captured, path, "captured")`. The capture dict always has keys `output`, `stderr`, `exit_code`, `duration_ms` (set at `executor.py:662-668`). For `plan_call`, store the temp file path as the `output` value.

**Corrected example YAML:**

```yaml
states:
  plan:
    action: "Analyze the failing tests and produce a step-by-step fix plan"
    action_type: plan_call
    capture: plan_file
    next: execute_plan

  execute_plan:
    action: "Read ${captured.plan_file.output} and implement each step"
    action_type: prompt
    on_success: done
    on_failure: plan
```

### `run_id` Is Not a Direct Executor Field

`FSMExecutor` does not expose a `run_id` attribute. The `run_id` used for archiving is derived in `persistence.py:252-261` via:

```python
run_id = state.started_at.replace(":", "").replace(".", "").replace("+", "")[:17]
```

For the temp file path, derive from `self.started_at` (set at `executor.py:414`) using the same formula, or substitute `self.fsm.name` as the discriminator:

```python
run_id = self.started_at.replace(":", "").replace(".", "").replace("+", "")[:17]
plan_path = Path(f"/tmp/ll-loop-plan-{self.fsm.name}-{run_id}.md")
```

This matches the `/tmp/ll-<purpose>-<discriminator>.<ext>` naming convention from `evaluators.py:421-423`.

### Capture Mechanism Is Already Implemented

No new capture infrastructure is needed. The existing `capture` field on `StateConfig` (`schema.py:222`) and the write-back block at `executor.py:662-668` already handle any action type. The `plan_call` implementation only needs to ensure that the `ActionResult.output` it returns contains the temp file path string — the existing capture write-back will then store it as `captured["plan_file"]["output"]`.

### Evaluator for `plan_call`

The default evaluator branch at `executor.py:762-795` selects per action_mode. For `plan_call`:
- The plan write itself succeeds/fails via exit code (whether the temp file was written) → use `evaluate_exit_code`
- Or treat like `prompt` and run LLM evaluation → use `evaluate_llm_structured`

Recommend `evaluate_exit_code` (success = file written) to keep the plan state non-evaluative — the downstream `execute_plan` state should judge quality, not the plan state.

### `EnterPlanMode`/`ExitPlanMode` Are Not Wired Anywhere

Zero existing usages of `EnterPlanMode`/`ExitPlanMode` in `scripts/`. These are Claude Code tool definitions only (documented at `docs/claude-code/settings.md:841`). There is no Python API to invoke them. The `plan_call` implementation cannot programmatically enter Claude's Plan Mode from inside the executor — it would need to use the `claude` CLI with a flag or prompt injection.

**Implication**: The issue's step 1 ("Enter Plan Mode analogous to calling `EnterPlanMode`") may not be achievable as described. Consider whether `plan_call` should instead run a specially framed prompt that instructs Claude to _output a plan_ (without actually entering Plan Mode), writing the response to the temp file — effectively the same outcome without requiring Plan Mode integration.

---

## Related

- `scripts/little_loops/fsm/schema.py:211` — `action_type` literal
- `scripts/little_loops/fsm/executor.py:893-904` — `_action_mode()` dispatch (not ~895)
- `scripts/little_loops/fsm/executor.py:636-647` — `_run_action()` branching
- `scripts/little_loops/fsm/executor.py:662-668` — capture write-back
- `scripts/little_loops/fsm/executor.py:762-795` — default evaluator selection
- `scripts/little_loops/fsm/executor.py:906-922` — `_build_context()` (where `started_at` flows to interpolation)
- `scripts/little_loops/fsm/interpolation.py:25` — variable regex; `78-82` — `captured` namespace
- `scripts/little_loops/fsm/validation.py:176-198` — `_validate_state_action()` (not 190)
- `scripts/little_loops/fsm/fsm-loop-schema.json:77-81` — `action_type` enum
- `scripts/little_loops/fsm/persistence.py:252-261` — `run_id` derivation from `started_at`
- `scripts/little_loops/fsm/evaluators.py:421-423` — `/tmp/ll-*` naming convention
- `docs/claude-code/settings.md:841` — `EnterPlanMode`/`ExitPlanMode` docs reference

## Resolution

**Status**: Won't Do — 2026-03-16

`EnterPlanMode`/`ExitPlanMode` are Claude Code UI tools that toggle session state in the *parent* process. The FSM executor spawns Claude as a child subprocess (`claude -p`), which has no connection to the parent session's plan mode. There is no CLI flag or API to invoke plan mode programmatically from a subprocess.

The "think before acting" intent can already be achieved with a regular `prompt` action using a planning-framed prompt (e.g., "Produce a step-by-step plan only, do not implement"). No new action type is needed.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-03-16:_

- **Frontmatter was incomplete**: Missing `id`, `title`, `type`, `priority`, and `status` fields — corrected during verification.
- All file references verified accurate: `schema.py:211`, `executor.py:893-904`, `executor.py:636-647`, `fsm-loop-schema.json:77-81` all match current codebase state.
- The codebase research note (EnterPlanMode/ExitPlanMode not wired in Python) is confirmed: no usages in `scripts/` — this is a key implementation constraint to resolve before coding.

## Session Log
- `/ll:verify-issues` - 2026-03-16T17:32:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8de8f7f-036d-410c-b49a-697d879afa38.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8de8f7f-036d-410c-b49a-697d879afa38.jsonl`
- `/ll:verify-issues` - 2026-03-16T17:28:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8de8f7f-036d-410c-b49a-697d879afa38.jsonl`
- `/ll:refine-issue` - 2026-03-16T17:25:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef6f9fdc-6be2-4332-a31a-ac306dde4386.jsonl`
- `/ll:capture-issue` - 2026-03-16T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71056193-bbfc-4baa-8002-42476d663c64.jsonl`
