---
id: BUG-1611
type: BUG
priority: P3
title: Add pre-terminal diagnose states to general-task, recursive-refine, prompt-across-issues,
  rl-policy loops
status: done
completed_at: 2026-05-18T08:58:09Z
parent: BUG-1606
size: Small
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1611: Add pre-terminal diagnose states to general-task, recursive-refine, prompt-across-issues, rl-policy loops

## Summary

Add a pre-terminal `diagnose` (or `diagnose_error`) state to `general-task`, `recursive-refine`, `prompt-across-issues`, and `rl-policy` loop YAML files. Update `test_builtin_loops.py` assertions for recursive-refine and prompt-across-issues.

## Current Behavior

The four affected loop YAML files (`general-task`, `recursive-refine`, `prompt-across-issues`, `rl-policy`) have a terminal `failed`/`error` state with no pre-terminal `diagnose` state. `FSMExecutor.run()` calls `return self._finish("terminal")` before executing any terminal state action, so any `action:` field on a `failed`/`error` terminal is silently skipped. Operators receive no diagnostic output when these loops terminate with failure.

## Expected Behavior

Each affected loop has a non-terminal `diagnose` (or `diagnose_error` for `prompt-across-issues`) state inserted immediately before the failure terminal. That state runs a prompt action that reads available artifact files and summarizes the failure cause, then routes to the terminal via `next: failed` (or `next: error`). All states currently routing to the failure terminal are redirected to the new diagnose state first.

## Steps to Reproduce

1. Open `scripts/little_loops/loops/general-task.yaml` and observe the `failed:` terminal state has no preceding `diagnose` state.
2. Run any of the affected loops and trigger a failure (e.g., pass an invalid task to `general-task`).
3. Observe the loop terminates with `failed`/`error` but produces no diagnostic summary.
4. Compare with `svg-image-generator.yaml`, which has a `diagnose` state and produces a summary on failure.

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

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — insert `diagnose` before `failed` (line 97); reroute 5 `on_error` fields
- `scripts/little_loops/loops/recursive-refine.yaml` — insert `diagnose` before `failed` (line 818); reroute `parse_input.on_no` and `parse_input.on_error`
- `scripts/little_loops/loops/prompt-across-issues.yaml` — insert `diagnose_error` before `error` (line 99); reroute `init.on_error`
- `scripts/little_loops/loops/rl-policy.yaml` — insert `diagnose` before `failed` (line 55); reroute `score.route.error`
- `scripts/tests/test_builtin_loops.py` — update `TestRecursiveRefineLoop` (line 1921) and `TestPromptAcrossIssuesLoop` (line 880)

### Existing Test Classes Needing Updates
- `TestRecursiveRefineLoop.test_required_states_exist` (line ~1937): currently asserts `{"parse_input", ..., "done", "failed"}` — add `"diagnose"`
- `TestPromptAcrossIssuesLoop.test_required_states_exist` (line ~896): currently asserts `{"init", "discover", "prepare_prompt", "execute", "advance", "done", "error"}` — add `"diagnose_error"`

### No Dedicated Test Classes (No Test-Side Changes Needed)
- `general-task` — no `TestGeneralTaskLoop` class; covered only by generic `TestBuiltinLoopFiles` sweep
- `rl-policy` — no `TestRlPolicyLoop` class; covered only by generic `TestBuiltinLoopFiles` sweep

### Similar Patterns to Follow
- `scripts/little_loops/loops/rn-refine.yaml` — multiple states route to `diagnose` (closest structural match to `general-task`)
- `scripts/little_loops/loops/svg-image-generator.yaml` — canonical single-state `diagnose` pattern
- `scripts/tests/test_builtin_loops.py:TestSvgImageGeneratorLoop` — reference for `test_diagnose_routes_to_failed` and `test_diagnose_is_not_terminal` method signatures

### Status Note
BUG-1610 (html-anything, svg-textgrad, svg-image-generator) is **complete** (commit a0e8579e). No sequencing conflict on `test_builtin_loops.py`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — calls `recursive-refine` as a sub-loop (`loop: recursive-refine` at line 42); no changes needed — adding pre-terminal states is backward-compatible [Agent 1 finding]
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — calls `recursive-refine` as a sub-loop (`loop: recursive-refine` at line 78); no changes needed [Agent 1 finding]
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — calls `recursive-refine` as a sub-loop (`loop: recursive-refine` at line 51); no changes needed [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_loops_recursive_refine.py` — dedicated unit tests for `recursive-refine` bash shell snippets and artifact file names; does not assert on state transition names — verify not broken after change [Agent 1 finding]

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Atomicity constraint per YAML**: add the `diagnose`/`diagnose_error` state block AND update all routing redirects in the same file save. `validate_fsm()` enforces reference integrity — if routing points to `diagnose` before the state block exists, `TestBuiltinLoopFiles.test_all_validate_as_valid_fsm` will error with a reference-integrity failure.

7. *(Optional)* Update `docs/guides/LOOPS_GUIDE.md` — the `recursive-refine` FSM flow diagram section (around line 648–668) shows the success path only; the `parse_input` failure path is implicit/not drawn. The change makes the diagram slightly more stale, but no update is strictly required.

### Codebase Research Findings

_Added by `/ll:refine-issue` — exact test method signatures to add (modeled after `TestSvgImageGeneratorLoop`):_

**For `TestRecursiveRefineLoop`** — add these three methods:
```python
def test_diagnose_routes_to_failed(self, data: dict) -> None:
    state = data["states"].get("diagnose", {})
    assert state.get("next") == "failed"

def test_diagnose_is_not_terminal(self, data: dict) -> None:
    state = data["states"].get("diagnose", {})
    assert not state.get("terminal", False)

def test_parse_input_on_error_routes_to_diagnose(self, data: dict) -> None:
    state = data["states"].get("parse_input", {})
    assert state.get("on_error") == "diagnose"
    assert state.get("on_no") == "diagnose"
```

**For `TestPromptAcrossIssuesLoop`** — add these three methods:
```python
def test_diagnose_error_routes_to_error(self, data: dict) -> None:
    state = data["states"].get("diagnose_error", {})
    assert state.get("next") == "error"

def test_diagnose_error_is_not_terminal(self, data: dict) -> None:
    state = data["states"].get("diagnose_error", {})
    assert not state.get("terminal", False)

def test_init_on_error_routes_to_diagnose_error(self, data: dict) -> None:
    state = data["states"].get("init", {})
    assert state.get("on_error") == "diagnose_error"
```

**Note**: `test_builtin_loops.py` is also modified by BUG-1610 (HtmlAnything, SvgTextgrad classes) and BUG-1612 (RefineToReadyIssue). Run this after BUG-1610 is complete to avoid conflicts.

## Acceptance Criteria

- `general-task.yaml`, `recursive-refine.yaml`, `prompt-across-issues.yaml`, `rl-policy.yaml` each have a pre-terminal diagnose state before their failure terminal
- `prompt-across-issues` uses `diagnose_error` → `next: error` pattern (not `diagnose` → `next: failed`)
- Each diagnose state names the loop's actual output artifacts
- `test_builtin_loops.py` updated for RecursiveRefine and PromptAcrossIssues test classes
- All listed tests pass

## Impact

- **Priority**: P3 — Operators cannot diagnose loop failures without diagnostic output; `diagnose` states are established best practice in other loops
- **Effort**: Small — Pattern is established; add 4 YAML state blocks + redirect routing in 4 files + 2 test class updates
- **Risk**: Low — Backward-compatible addition; no callers change behavior; new states are unreachable until a failure occurs
- **Breaking Change**: No

## Labels

`bug`, `loops`, `fsm`, `diagnostics`

---

**Priority**: P3 | **Created**: 2026-05-18

## Session Log
- `/ll:ready-issue` - 2026-05-18T08:54:37 - `432522a5-afac-4f66-8030-82eb31701e84.jsonl`
- `/ll:confidence-check` - 2026-05-18T00:00:00 - `9a910a85-ab3f-4425-9beb-e6f55b2a3509.jsonl`
- `/ll:wire-issue` - 2026-05-18T08:48:45 - `e1a75732-1463-4591-9df1-c93fc0254092.jsonl`
- `/ll:refine-issue` - 2026-05-18T08:42:26 - `0a6af136-3690-4fe3-9864-f6e0f5f3d980.jsonl`
- `/ll:issue-size-review` - 2026-05-18T00:00:00 - `3772e425-1416-4cc8-baac-8e0f351122fa.jsonl`
