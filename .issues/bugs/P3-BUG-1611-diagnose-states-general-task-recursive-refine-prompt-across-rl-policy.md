---
id: BUG-1611
type: BUG
priority: P3
title: Add pre-terminal diagnose states to general-task, recursive-refine, prompt-across-issues, rl-policy loops
status: open
parent: BUG-1606
size: Small
---

# BUG-1611: Add pre-terminal diagnose states to general-task, recursive-refine, prompt-across-issues, rl-policy loops

## Summary

Add a pre-terminal `diagnose` (or `diagnose_error`) state to `general-task`, `recursive-refine`, `prompt-across-issues`, and `rl-policy` loop YAML files. Update `test_builtin_loops.py` assertions for recursive-refine and prompt-across-issues.

## Parent Issue

Decomposed from BUG-1606: Add pre-terminal diagnose states to 12 affected loop YAML files

## Background

`scripts/little_loops/fsm/executor.py` `FSMExecutor.run()` calls `return self._finish("terminal")` BEFORE executing any terminal state action. An `action:` field on a `failed`/`error` terminal never executes. The correct pattern is a separate non-terminal `diagnose` state that runs the diagnostic prompt and routes `next: failed` (or `next: error` for `prompt-across-issues`).

Note: `prompt-across-issues` uses `error` as the terminal state name instead of `failed` — the new pre-terminal state is named `diagnose_error` and routes `next: error`.

## Affected Loops

| Loop | File | Failed State Line | States routing to `failed`/`error` |
|------|------|-------------------|--------------------------------------|
| `general-task` | `scripts/little_loops/loops/general-task.yaml` | 97 | `define_done`, `plan`, `execute`, `check_done`, `continue_work` → `on_error: failed` (5 states) |
| `recursive-refine` | `scripts/little_loops/loops/recursive-refine.yaml` | 818 | `parse_input` → `on_no: failed` and `on_error: failed` |
| `prompt-across-issues` | `scripts/little_loops/loops/prompt-across-issues.yaml` | 99 (state: `error`) | `init` → `on_error: error` |
| `rl-policy` | `scripts/little_loops/loops/rl-policy.yaml` | 55 | `score` → convergence evaluator `route: error: failed` |

## Implementation Steps

### For each loop:

1. Read the loop YAML and identify all states routing to the failure terminal.

2. Add the appropriate `diagnose` state immediately before the terminal:

**`general-task`** — artifacts: `.loops/tmp/general-task-plan.md`, `.loops/tmp/general-task-dod.md`:
```yaml
diagnose:
  action_type: prompt
  action: |
    The general-task loop has terminated with an unrecoverable failure.

    Diagnose what happened:
    - If ${env.PWD}/.loops/tmp/general-task-plan.md exists, read it and summarize completed steps.
    - If ${env.PWD}/.loops/tmp/general-task-dod.md exists, report which done-criteria were met.
    - Identify the most likely failure cause and which state failed (define_done, plan, execute, check_done, or continue_work).

    Write a one-paragraph diagnostic summary the operator can use to re-run or adjust the task description.
  next: failed

failed:
  terminal: true
```

**`recursive-refine`** — artifacts: `.loops/tmp/recursive-refine-queue.txt`, `.loops/tmp/recursive-refine-visited.txt`:
```yaml
diagnose:
  action_type: prompt
  action: |
    The recursive-refine loop has terminated with an unrecoverable failure.

    Diagnose what happened:
    - If ${env.PWD}/.loops/tmp/recursive-refine-queue.txt exists, report its contents (remaining issues).
    - If ${env.PWD}/.loops/tmp/recursive-refine-visited.txt exists, report how many issues were processed.
    - If failure was in parse_input, report whether the input issue list was empty or malformed.
    - Identify the most likely failure cause.

    Write a one-paragraph diagnostic summary the operator can use to re-run with corrected input.
  next: failed
```

**`prompt-across-issues`** — artifact: `.loops/tmp/prompt-across-issues-pending.txt`; note terminal is `error` not `failed`:
```yaml
diagnose_error:
  action_type: prompt
  action: |
    The prompt-across-issues loop has terminated with an unrecoverable error.

    Diagnose what happened:
    - If ${env.PWD}/.loops/tmp/prompt-across-issues-pending.txt exists, report its contents.
    - If failure was in the init state, report whether the prompt argument was provided and whether ll-issues list succeeded.
    - Identify the most likely failure cause.

    Write a one-paragraph diagnostic summary the operator can use to re-run with a valid prompt argument.
  next: error

error:
  terminal: true
```

**`rl-policy`** — stub loop, no file artifacts:
```yaml
diagnose:
  action_type: prompt
  action: |
    The rl-policy loop has terminated with an unrecoverable failure.

    Diagnose what happened:
    - Identify the most likely failure cause (convergence evaluator error in the score state).
    - Note that this is a template/stub loop — no file artifacts are written.

    Write a one-paragraph diagnostic summary the operator can use to debug the policy stub.
  next: failed
```

3. Update routing for each loop:
   - `general-task`: `define_done.on_error`, `plan.on_error`, `execute.on_error`, `check_done.on_error`, `continue_work.on_error` — all `failed` → `diagnose` (5 states)
   - `recursive-refine`: `parse_input.on_no` and `parse_input.on_error` → `diagnose`
   - `prompt-across-issues`: `init.on_error: error` → `init.on_error: diagnose_error`
   - `rl-policy`: convergence evaluator `route: error: failed` → `route: error: diagnose`

4. Update `scripts/tests/test_builtin_loops.py`:
   - `TestRecursiveRefineLoop.test_required_states_exist`: add `"diagnose"` to required set
   - `TestPromptAcrossIssuesLoop.test_required_states_exist`: add `"diagnose_error"` to required set
   - Add `test_diagnose_routes_to_failed` and `test_diagnose_is_not_terminal` to TestRecursiveRefineLoop
   - Add `test_diagnose_error_routes_to_error` and `test_diagnose_error_is_not_terminal` to TestPromptAcrossIssuesLoop

5. Run `python -m pytest scripts/tests/test_builtin_loops.py -k "RecursiveRefine or PromptAcrossIssues" scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py -v` and confirm all pass.

**Note**: `test_builtin_loops.py` is also modified by BUG-1610 (HtmlAnything, SvgTextgrad classes) and BUG-1612 (RefineToReadyIssue). Run this after BUG-1610 is complete to avoid conflicts.

## Acceptance Criteria

- `general-task.yaml`, `recursive-refine.yaml`, `prompt-across-issues.yaml`, `rl-policy.yaml` each have a pre-terminal diagnose state before their failure terminal
- `prompt-across-issues` uses `diagnose_error` → `next: error` pattern (not `diagnose` → `next: failed`)
- Each diagnose state names the loop's actual output artifacts
- `test_builtin_loops.py` updated for RecursiveRefine and PromptAcrossIssues test classes
- All listed tests pass

---

**Priority**: P3 | **Created**: 2026-05-18

## Session Log
- `/ll:issue-size-review` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3772e425-1416-4cc8-baac-8e0f351122fa.jsonl`
