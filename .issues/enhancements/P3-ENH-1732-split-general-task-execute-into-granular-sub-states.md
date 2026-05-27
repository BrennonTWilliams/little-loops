---
title: Split general-task execute state into granular sub-states to limit per-action
  duration
type: ENH
priority: P3
effort: Medium
impact: High
risk: Medium
status: done
captured_at: '2026-05-27T00:00:00Z'
completed_at: '2026-05-27T02:42:29Z'
discovered_date: 2026-05-27
discovered_by: audit-loop-run
labels:
- loops
- general-task
- decomposition
- resilience
confidence_score: 100
decision_needed: false
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1732: Split general-task execute state into granular sub-states

## Summary

The `general-task` loop's `execute` state is monolithic: a single prompt reads the plan, finds the first unchecked step, implements it (including writing code, running tests, debugging failures), then marks it [x]. On 2026-05-26, this ran for ~16 minutes before receiving SIGKILL. Splitting `execute` into `select_step` → `do_work` → `verify_step` → `mark_done` sub-states would keep individual actions under a few minutes, make failures more granular (a test failure routes to fix, not back to the full execute), and allow the progress-tracking states (`check_done`, `count_done`) to interleave more frequently.

## Current Behavior

- Single `execute` prompt per iteration: read plan, find unchecked step, implement it, run tests, debug failures, mark plan [x]
- 969-second observed duration for Step 1 (a moderately complex hook + test file)
- If any part fails (test failure, file conflict, timeout), the entire action is lost and routes to `diagnose`
- Progress is only checkpointed when the full action completes and `check_done` runs

## Expected Behavior

Four sub-states replace the single `execute`:

```
execute → select_step → do_work → verify_step → mark_done → check_done
              ↑                        ↓ (on_no)        ↓
              └────────────────────────┘                ↓
                                                   count_done → ...
```

- **`select_step`**: Finds first unchecked plan step, writes step text to a temp file, prints `SELECTED_STEP: <text>` (shell action, sub-second)
- **`do_work`**: Implements ONLY the selected step (no plan file I/O, no test running — just code changes) (prompt action)
- **`verify_step`**: Runs tests/lint/type-check relevant to the step; prints `VERIFY: pass` or `VERIFY: fail: <reason>` (shell action, with `evaluate` on output)
- **`mark_done`**: Marks the step [x] in the plan file (shell action, sub-second)

Each sub-state has its own `on_error → diagnose` and `timeout`. The `do_work` state is the only expensive prompt, and even it is smaller (no plan I/O, no test debugging).

## Motivation

The audit of the 2026-05-26 `general-task` run revealed that the `execute` state is the bottleneck and single point of failure. Step 1 succeeded (files were created, tests passed) but the process was killed before marking the plan, losing all tracking. Granular states solve this:

1. **Faster failure recovery**: A test failure in `verify_step` routes to a focused fix rather than re-running the entire execute
2. **More frequent checkpoints**: `mark_done` writes plan progress before `check_done` verifies DoD criteria
3. **Per-state timeouts**: `do_work` can have a shorter timeout than the current monolithic execute
4. **Better observability**: Each sub-state appears in event history, making it clear where time is spent

## Scope Boundaries

- **In scope**: Replacing the single `execute` state in `loops/general-task.yaml` with four granular sub-states (`select_step`, `do_work`, `verify_step`, `mark_done`); updating `continue_work` routing; adding tests for the new routing chain
- **Out of scope**: Changes to other loops; changes to the FSM executor engine (`ll-loop`); adding retry logic beyond what `continue_work` already provides; changing the plan file format or DoD file format

## Success Metrics

- `do_work` state completes in < 5 minutes (vs observed 969s monolithic execute)
- No SIGKILL observed on 2+ consecutive `general-task` runs with moderately complex plans
- `verify_step` routes to `continue_work` on test failure (not `diagnose`) — verified by routing test
- Plan file checkpointing occurs after each completed step, not only at task end

## Proposed Solution

Replace the single `execute` state with a chain of four states. The `continue_work` state (used for remediation) would also route into `do_work` instead of the old `execute`:

```yaml
states:
  select_step:
    action: |
      PLAN="${env.PWD}/.loops/tmp/general-task-plan.md"
      STEP=$(grep -m1 '^- \[ \]' "$PLAN" || echo "")
      if [ -z "$STEP" ]; then
        echo "NO_UNCHECKED_STEPS"
        exit 0
      fi
      echo "$STEP" > "${env.PWD}/.loops/tmp/general-task-current-step.txt"
      echo "SELECTED_STEP: $STEP"
    action_type: shell
    on_error: diagnose
    next: do_work
    capture: selected_step

  do_work:
    action: |
      Your task is: ${context.input}
      The selected step to complete is in ${env.PWD}/.loops/tmp/general-task-current-step.txt.
      Implement ONLY this step. Do NOT modify the plan file or DoD file.
      After completing, print:
      LAST_FILES: <space-separated list of files you created or modified>
    action_type: prompt
    on_error: diagnose
    next: verify_step
    capture: work_result
    timeout: 900

  verify_step:
    action: |
      # Run tests/lint relevant to LAST_FILES from do_work output
      # ...
    action_type: shell
    evaluate:
      type: output_json
      operator: eq
      target: 0
      path: ".failures"
    on_yes: mark_done
    on_no: continue_work
    on_error: diagnose
    capture: verify_result

  mark_done:
    action: |
      PLAN="${env.PWD}/.loops/tmp/general-task-plan.md"
      STEP_FILE="${env.PWD}/.loops/tmp/general-task-current-step.txt"
      STEP=$(cat "$STEP_FILE")
      # Mark first matching unchecked step as [x]
      sed -i '' "0,/- \[ \]/{s/- \[ \]/- [x]/}" "$PLAN"
      rm -f "$STEP_FILE"
    action_type: shell
    on_error: diagnose
    next: check_done
```

## Implementation Steps

1. Replace `execute` state with `select_step`, `do_work`, `verify_step`, `mark_done` states in `loops/general-task.yaml`
2. Update `continue_work` to route into `do_work` instead of old `execute`; update initial routing (`plan → select_step`)
3. Implement `verify_step` shell action with test/lint runner using `LAST_FILES` captured from `do_work` output
4. Add tests for the split-state routing chain (`select_step → do_work → verify_step → mark_done → check_done`) and the failure path (`verify_step on_no → continue_work → do_work`)
5. Run `ll-loop validate loops/general-task.yaml` and execute a full task end-to-end to confirm no regressions

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_general_task_loop.py:57` — replace `"execute"` in `test_expected_states_present` expected-states set with `"select_step"`, `"do_work"`, `"verify_step"`, `"mark_done"`
7. Rename and rewrite `TestChange5ExecuteCapture` → `TestChange5DoWorkCapture` — all 3 methods KeyError on `raw_data["states"]["execute"]`; repoint to `raw_data["states"]["do_work"]` and assert `capture: work_result`
8. Update `TestChange3ContinueWorkDodFallback.test_continue_work_diverges_from_execute` — compare against `do_work` state instead of removed `execute` state (or delete if the invariant is now trivially satisfied)
9. Update `TestChange6CheckDoneDeltaAware.test_check_done_references_captured_execute_result` — assert `"${captured.work_result.output}"` not `"${captured.execute_result.output}"` in `check_done.action`
10. Add shell-action unit tests in `test_general_task_loop.py` for `select_step`, `verify_step`, and `mark_done` — follow `_load_count_done_script()` + `_bash()` helper pattern already in the file; for `mark_done` use `awk+mv` (cross-platform, not `sed -i ''`)
11. Update `docs/guides/LOOPS_GUIDE.md` lines 335, 338, 346 — replace `execute` state name and `captured.execute_result` references with 4-state chain and `captured.work_result`; add note at line 348 about 6 iterations/step iteration budget

## Integration Map

### Files to Modify
| File | Change |
|------|--------|
| `scripts/little_loops/loops/general-task.yaml` (state: `execute`) | Remove; replace with `select_step`, `do_work`, `verify_step`, `mark_done` state chain |
| `scripts/little_loops/loops/general-task.yaml` (state: `plan`) | Single line: `next: execute` → `next: select_step` |
| `scripts/little_loops/loops/general-task.yaml` (state: `check_done`) | Update `${captured.execute_result.output}` references — `LAST_FILES` from `${captured.work_result.output}`, `LAST_STEP` from `${captured.selected_step.output}` or `.loops/tmp/general-task-current-step.txt` |
| `scripts/little_loops/loops/general-task.yaml` (state: `continue_work`) | Handle only DoD remediation (Case B — append new plan step); route to `select_step` afterward; drop inline Case A (step-execute logic moves to `select_step`+`do_work`) |
| `scripts/little_loops/loops/general-task.yaml` (state: `diagnose`) | Add `select_step`, `do_work`, `verify_step`, `mark_done` to the state name list in the prompt text |
| `scripts/tests/test_general_task_loop.py` | Update state-presence assertion (~line 52–70): replace `"execute"` with `"select_step"`, `"do_work"`, `"verify_step"`, `"mark_done"`; also update/remove `TestChange5ExecuteCapture` class and `test_continue_work_diverges_from_execute` (see Tests section) |
| `docs/guides/LOOPS_GUIDE.md` | **Required** (not optional): lines 335, 338, 346 reference `execute` state and `captured.execute_result` by name in the general-task flow description — must be updated to the 4-state chain |

### Dependent Files (Callers/Importers)
- `scripts/tests/test_fsm_flow.py` (`TestBuiltinLoopRegression.test_all_builtin_loops_still_load`) — auto-validates YAML still parses; no manual update needed but will surface schema errors

### Issue Dependencies

_Wiring pass added by `/ll:wire-issue`:_
- `P3-ENH-1731-persist-plan-step-index-before-execute-for-crash-recovery.md` — ENH-1731 targets `execute` state by name throughout its scope description and proposed solution; if ENH-1732 lands first, ENH-1731's implementation target shifts to `select_step` (the shell state that already writes the step text to `general-task-current-step.txt`, which is effectively a checkpoint). ENH-1731's issue file would need updating to reference the new sub-states. **Implement ENH-1732 before ENH-1731.**

### Similar Patterns
- `scripts/little_loops/loops/prompt-across-issues.yaml` (state: `advance`) — atomic plan-file mutation via `tail -n +2 ... > .tmp && mv` (macOS-safe alternative to `sed -i ''` for `mark_done`)
- `scripts/little_loops/loops/rn-refine.yaml` (state: `verify_score`) — shell state emitting sentinel token, routed via `output_contains` (pattern to follow for `verify_step`)
- `scripts/little_loops/loops/incremental-refactor.yaml` (states: `execute_step` → `verify_tests` → `commit_step`) — shell-prompt-shell interleaving chain; closest structural analog to the new 4-state chain
- `scripts/little_loops/loops/backlog-flow-optimizer.yaml` (states: `measure` → `diagnose`) — shell capture → prompt reads `${captured.X.output}` (pattern for `do_work` reading `selected_step` capture)

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Tests that WILL BREAK (KeyError or assertion failure — must update):**
- `scripts/tests/test_general_task_loop.py:57` (`TestGeneralTaskLoopFile.test_expected_states_present`) — hardcoded set contains `"execute"`; replace with `"select_step"`, `"do_work"`, `"verify_step"`, `"mark_done"`
- `scripts/tests/test_general_task_loop.py:136-142` (`TestChange3ContinueWorkDodFallback.test_continue_work_diverges_from_execute`) — `raw_data["states"]["execute"]` raises `KeyError` once `execute` is removed; update to compare `continue_work` against `do_work` instead, or remove the test (the invariant it guards no longer applies)
- `scripts/tests/test_general_task_loop.py:219-235` (`TestChange5ExecuteCapture` — all 3 methods) — all three methods key into `raw_data["states"]["execute"]` (KeyError); rename class to `TestChange5DoWorkCapture` and rewrite for `do_work` state (`capture: work_result`, `LAST_FILES` in prompt, `LAST_STEP` handoff via temp file)
- `scripts/tests/test_general_task_loop.py:241` (`TestChange6CheckDoneDeltaAware.test_check_done_references_captured_execute_result`) — asserts `"${captured.execute_result.output}" in action`; after the split, `check_done.action` must reference `${captured.work_result.output}` — update assertion

**Tests to add (new shell-action unit tests in `test_general_task_loop.py`):**
- `select_step` shell action: empty plan → emits `NO_UNCHECKED_STEPS`; unchecked step exists → emits `SELECTED_STEP: <text>` and writes step to `general-task-current-step.txt`; follow `_load_count_done_script()` + `_bash()` helper pattern from lines 287-299
- `verify_step` shell action: reads `general-task-last-files.txt`; tests pass → emits `VERIFY_PASS`; tests fail → emits `VERIFY_FAIL`; uses `output_contains` evaluator pattern (same as `rn-refine.yaml:verify_score`)
- `mark_done` shell action: marks first `[ ]` step as `[x]` (awk+mv, not `sed -i ''`); removes `general-task-current-step.txt`; plan file is correctly mutated

**Tests that may break depending on implementation choice:**
- `scripts/tests/test_general_task_loop.py:197-200` (`TestBUG1687ContinueWorkCapture.test_continue_work_has_capture_execute_result`) — asserts `continue_work` has `capture: execute_result`; if the `continue_work` restructuring changes this capture key, this test must be updated; if `continue_work` retains `capture: execute_result` for the Case B remediation step, this test remains valid

**Tests that are safe (no changes needed):**
- `scripts/tests/test_fsm_flow.py` (`TestBuiltinLoopRegression`) — validates YAML loads; enumerates no specific state names
- `scripts/tests/test_builtin_loops.py` — checks loop file names and FSM validity only
- `scripts/tests/test_fsm_executor.py` — uses synthetic `FSMLoop` mock, not real YAML
- `scripts/tests/test_ll_loop_errors.py` — writes its own synthetic YAML to `tmp_path`
- `scripts/tests/test_ll_loop_commands.py` — uses `"general-task"` only as a string literal in context parsing

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

These lines in `docs/guides/LOOPS_GUIDE.md` describe the general-task state machine by name and will become stale:
- **Line 335**: `3. **Execute** — completes the first unchecked step and marks it done in the plan` → replace with 4-state chain description (`select_step → do_work → verify_step → mark_done`)
- **Line 338**: "every work-producing state (`execute` and `continue_work`) captures `LAST_STEP` and `LAST_FILES`... stored under the shared `captured.execute_result` key" → update to reference `do_work` state and `captured.work_result` key; `LAST_FILES` handoff via `.loops/tmp/general-task-last-files.txt`
- **Line 346**: "Like `execute`, `continue_work` must emit `LAST_STEP: <step>` and `LAST_FILES: <paths>`" → `continue_work` now handles only DoD remediation (Case B); no longer emits `LAST_FILES`
- **Line 348**: "The loop runs up to 100 iterations" → add note that each plan step now consumes ~6 iterations minimum (select_step + do_work + verify_step + mark_done + check_done + count_done); `max_iterations: 100` supports ~16 steps before the cap fires

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**1. `mark_done` portability: avoid `sed -i ''`**
`sed -i '' "0,/- \[ \]/{s/- \[ \]/- [x]/}"` is macOS-only; Linux requires `sed -i` (no empty string arg). Codebase convention (`prompt-across-issues.yaml:advance`, `autodev.yaml:dequeue_next`) uses atomic `awk + tmp+mv`:
```bash
awk 'found==0 && /^- \[ \]/ { sub(/^- \[ \]/, "- [x]"); found=1 } 1' "$PLAN" > "$PLAN.tmp" && mv "$PLAN.tmp" "$PLAN"
rm -f "$STEP_FILE"
```

**2. `check_done` capture variable must be updated (non-obvious coupling)**
`check_done` currently reads `${captured.execute_result.output}` to extract both `LAST_STEP:` and `LAST_FILES:` lines. After the split, neither `select_step` (`capture: selected_step`) nor `do_work` (`capture: work_result`) sets `execute_result`. The `check_done` prompt must be updated to source:
- `LAST_FILES` from `${captured.work_result.output}` (do_work capture)
- `LAST_STEP` from `.loops/tmp/general-task-current-step.txt` (still on disk at check_done time) or `${captured.selected_step.output}`

**3. `verify_step` evaluate: prefer `output_contains` over `output_json`**
The proposed `evaluate: { type: output_json, path: ".failures" }` requires the shell script to produce JSON. Simpler and consistent with `rn-refine.yaml:verify_score` and `issue-refinement.yaml:check_commit`: emit a sentinel and use `output_contains`:
```yaml
verify_step:
  action: |
    FILES=$(grep 'LAST_FILES:' "${env.PWD}/.loops/tmp/general-task-last-files.txt" | sed 's/LAST_FILES: //')
    if python -m pytest $FILES --tb=short -q 2>&1 | tail -1 | grep -qE "passed|no tests ran"; then
      echo "VERIFY_PASS"
    else
      echo "VERIFY_FAIL"
    fi
  action_type: shell
  capture: verify_result
  evaluate:
    type: output_contains
    pattern: "VERIFY_PASS"
  on_yes: mark_done
  on_no: continue_work
  on_error: diagnose
```

**4. `continue_work` restructuring scope**
Currently handles 3 inline cases (A: unchecked plan step → work it; B: DoD criteria fail → append remediation step; C: both done → nothing). After the split, Case A moves to `select_step`+`do_work`. `continue_work` should handle only Case B (append new plan step), then route to `select_step` (not `do_work` directly) so the newly-appended step goes through the full `select_step → do_work → verify_step → mark_done` chain normally.

**5. `LAST_FILES` handoff from `do_work` to `verify_step`**
`do_work` prints `LAST_FILES: <paths>` in its final output, captured as `work_result`. The `verify_step` shell action cannot interpolate `${captured.work_result.output}` inline in bash. Write it to a dedicated temp file in `do_work`'s prompt instructions:
```
After completing, write to ${env.PWD}/.loops/tmp/general-task-last-files.txt exactly:
LAST_FILES: <space-separated list of files you created or modified>
```
Then `verify_step` reads `.loops/tmp/general-task-last-files.txt` directly.

**6. `max_iterations` impact**
Each plan step now consumes 4 iterations (`select_step` + `do_work` + `verify_step` + `mark_done`) plus 2 (`check_done` + `count_done`) = 6 iterations minimum per step. The `default_timeout: 1800` and `max_iterations` at the top of `general-task.yaml` should be reviewed; a 10-step plan needs ~60 iterations minimum.

**7. SIGKILL / crash recovery behavior**
FSM persists `current_state` at `state_enter` (before the action runs). SIGKILL cannot be caught — no Python code runs after it. On restart, `_reconcile_stale_runs()` detects the dead PID and re-runs from scratch. Granular states improve this: `mark_done` writes plan progress before `check_done`, so a SIGKILL during `do_work` loses at most one step's output (not an entire multi-step execute). ENH-1731 addresses full crash recovery separately.

## Impact

- **Priority**: P3 — Structural improvement to an existing loop; the current loop works for smaller tasks, this enables it to handle larger ones
- **Effort**: Medium — 4 new states replacing 1; routing needs careful testing; `continue_work` integration point
- **Risk**: Medium — Changes the core execution flow of a harness loop; routing errors could break the progress loop; needs thorough test coverage
- **Breaking Change**: Yes for anyone relying on the internal state names of general-task (unlikely — states are internal implementation details)

## Labels

- loops
- general-task
- decomposition
- resilience

## Status

**Open** | Created: 2026-05-27 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-05-27T02:28:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eb13003f-ba8f-40f1-84e6-077a0739deb1.jsonl`
- `/ll:confidence-check` - 2026-05-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/147823b3-5677-4a95-9394-0e44304c03ce.jsonl`
- `/ll:wire-issue` - 2026-05-27T01:08:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71ba2e27-21e9-408e-8681-668910c7758a.jsonl`
- `/ll:refine-issue` - 2026-05-27T00:36:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bab12386-1d63-4f54-900d-e9f3196d5409.jsonl`
- `/ll:format-issue` - 2026-05-27T00:28:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/abc07224-3eb5-43f2-aa50-5c5476afdc3d.jsonl`
