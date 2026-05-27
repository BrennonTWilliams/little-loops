---
id: ENH-1735
title: Persist plan step index before execute for crash recovery in general-task loop
type: ENH
priority: P3
effort: Low
impact: Medium
risk: Low
status: open
captured_at: '2026-05-27T00:00:00Z'
discovered_date: 2026-05-27
discovered_by: audit-loop-run
parent: EPIC-1744
labels:
- loops
- general-task
- resilience
- crash-recovery
confidence_score: 95
decision_needed: false
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-1735: Persist plan step index before execute for crash recovery

## Summary

The `general-task` loop's `execute` state runs a monolithic prompt that can take 10+ minutes. If the process is killed (SIGKILL, OOM) during execution, the loop loses track of which plan step it was working on. Saving the current plan step index to `state.json` (or a checkpoint file) before launching the execute prompt would enable the loop to resume from where it left off on restart, rather than re-running completed steps.

## Current Behavior

- `execute` state reads the plan file, finds the first unchecked step, does all work, then marks it [x]
- If the process is killed mid-execute, the plan step remains [ ] even though work was completed (files were written)
- On restart, the loop re-executes the same step, potentially duplicating work or conflicting with already-created files
- The `state.json` captures `current_state` and `iteration` but not which plan step is in progress

## Expected Behavior

- Before launching the expensive prompt action, `execute` (or a new pre-execute state) writes the current plan step text and index to a checkpoint key in `state.json` or a `.loops/tmp/general-task-checkpoint.json` file
- On loop restart, if a checkpoint exists and the plan step is still [ ], the loop can detect that the step was in-flight and either:
  - Skip it if the expected output files already exist, or
  - Re-execute it cleanly with awareness of partial state
- The checkpoint is cleared when `check_done` confirms the step is complete

## Motivation

The `general-task` loop was audited on 2026-05-26 after a SIGKILL during `execute`. Step 1 (implement `useWalkthrough` hook + tests) produced real artifact files (287-line hook, 872-line test file) but the plan step remained [ ] because the process was killed before the plan file was updated. On restart, the loop would re-execute Step 1 despite the files already existing. Persisting the step index prevents this class of recovery failure.

## Proposed Solution

Add a lightweight `capture` or pre-action shell command in `execute` that writes the current step to a checkpoint file before invoking the LLM:

```yaml
states:
  execute:
    action: |
      PLAN="${env.PWD}/.loops/tmp/general-task-plan.md"
      CHECKPOINT="${env.PWD}/.loops/tmp/general-task-checkpoint.json"
      STEP=$(grep -m1 '^- \[ \]' "$PLAN" | head -1)
      echo "{\"in_flight_step\": \"$STEP\"}" > "$CHECKPOINT"
      # ... existing execute prompt follows
```

On `define_done` or `plan` (early states), check for an existing checkpoint and handle accordingly.

## Integration Map

| File | Change |
|------|--------|
| `loops/general-task.yaml` | Add checkpoint write to `execute` action; add checkpoint check to `plan` or a new `resume_check` state |
| `scripts/tests/fixtures/fsm/` | Optional: fixture with partial state to test resume path |

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Important context — ENH-1732 (DONE):** The `execute` state referenced above no longer exists. It was decomposed into `select_step → do_work → verify_step → mark_done`. The actual implementation target is `select_step` and `mark_done`.

**Files to Modify**
- `scripts/little_loops/loops/general-task.yaml` — three changes:
  - `select_step` (line 77): augment existing `echo "$STEP" > current-step.txt` to also write `general-task-checkpoint.json` with `{"in_flight_step": "$STEP", "timestamp": "..."}` before routing to `do_work`
  - `mark_done` (line 138): add `rm -f "${env.PWD}/.loops/tmp/general-task-checkpoint.json"` alongside the existing `rm -f "$STEP_FILE"` at line 143
  - `plan` (line 57) or a new `resume_check` state inserted before `select_step`: detect in-flight checkpoint on startup

**Scope note — `ll-loop resume` already works:** `PersistentExecutor._handle_event()` in `scripts/little_loops/fsm/persistence.py` emits `state_enter` and calls `_save_state()` before each state's action runs. On a crash during `do_work`, `state.json` already records `current_state: "do_work"` and `captured["selected_step"]`. On resume, `general-task-current-step.txt` is still on disk (not yet deleted by `mark_done`), so `do_work` re-runs correctly. **The gap is only for fresh `ll-loop run` (not resume):** `cmd_run()` in `cli/loop/run.py` calls `PersistentExecutor(clear_previous=True)`, wiping the state file, causing the loop to re-enter `define_done` and re-select the same `[ ]` step.

**Dependent Files (no changes needed — reference only)**
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor._save_state()`, `LoopState` dataclass; `LoopState.captured` stores `selected_step` output but not a numeric index
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()` with `clear_previous=True`; recovery gap lives here
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()`, `_reconcile_stale_running()` for stale PID detection

**Tests**
- `scripts/tests/test_general_task_loop.py` — extend with checkpoint write/clear/detect assertions; follow `TestGeneralTaskLoopFile.test_validates_as_fsm` pattern using `load_and_validate()` + `validate_fsm()`
- `scripts/tests/fixtures/fsm/` — no existing checkpoint-recovery fixtures; add new fixture for partial-state simulation

_Wiring pass added by `/ll:wire-issue`:_
- `TestCheckpointWriteShellAction` (new class in `scripts/tests/test_general_task_loop.py`) — verify checkpoint file written by `select_step` shell action (follow `TestSelectStepShellAction` pattern)
- `TestCheckpointClearShellAction` (new class in `scripts/tests/test_general_task_loop.py`) — verify checkpoint file removed by `mark_done` shell action (follow `TestMarkDoneShellAction.test_removes_current_step_temp_file` pattern)
- `TestResumeCheckShellAction` (new class, if `resume_check` state added) — verify checkpoint detect/skip routing logic
- `TestENH1732StateSplit.test_plan_routes_to_select_step` (`scripts/tests/test_general_task_loop.py:281`) — **will break** if `plan` routes to `resume_check` instead of `select_step`; update assertion to match new routing
- `TestBUG1687ContinueWorkCapture.test_continue_work_routes_to_select_step` (`scripts/tests/test_general_task_loop.py:197`) — **may break** if `continue_work` routing changes; verify after edit

**Documentation**

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — "General-purpose task loop" section describes `select_step` and `mark_done` actions and sidecar files by name; update to reflect checkpoint write in `select_step`, checkpoint clear in `mark_done`, and add `resume_check` if inserted; update iteration-count math (6 → 7 iterations per step if new state added)

**Intra-file Coupling**

_Wiring pass added by `/ll:wire-issue`:_
- `diagnose` state in `scripts/little_loops/loops/general-task.yaml` — action text enumerates all state names (`define_done, plan, select_step, do_work, verify_step, mark_done, check_done, count_done, final_verify, count_final, continue_work, or summarize_partial`); add `resume_check` to this list if that state is added

**Similar Patterns in Other Loops**
- `scripts/little_loops/loops/harness-optimize.yaml` — `dequeue_state`: writes selected state name to sidecar file before the prompt state using `head -1` + atomic `mv` (closest match)
- `scripts/little_loops/loops/loop-router.yaml` — `parse_project_score`: writes multiple sidecar files before routing to next prompt
- `scripts/little_loops/loops/scan-and-implement.yaml` — `snapshot_pre`: dedicated pre-action snapshot state before an expensive sub-loop

## Scope Boundaries

- **In scope**: Writing current plan step index to `general-task-checkpoint.json` before the execute prompt; detecting an in-flight checkpoint on restart and skipping the step (if output files exist) or re-executing cleanly; clearing the checkpoint when `check_done` confirms step completion
- **Out of scope**: Crash recovery for loops other than `general-task`; full replay or undo of already-completed steps; multi-level or per-substep checkpoint granularity; persistent step history across multiple runs

## Implementation Steps

1. Add checkpoint write shell snippet to `execute` state in `loops/general-task.yaml` (write `in_flight_step` to `.loops/tmp/general-task-checkpoint.json`)
2. Add checkpoint detection logic to `plan` or a new `resume_check` state to handle in-flight steps on restart (check if checkpoint file exists and if output files for that step already exist)
3. Clear checkpoint in `check_done` (or equivalent completion state) after step is marked `[x]`
4. Add optional FSM fixture under `scripts/tests/fixtures/fsm/` with partial checkpoint state to test resume path
5. Run `ll-loop validate loops/general-task.yaml` to confirm no routing regressions

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correction:** Steps 1–3 above reference `execute` state which no longer exists (split by ENH-1732). Corrected concrete steps:

1. In `select_step` (`scripts/little_loops/loops/general-task.yaml:85`): after `echo "$STEP" > "${env.PWD}/.loops/tmp/general-task-current-step.txt"`, add:
   ```bash
   CHECKPOINT="${env.PWD}/.loops/tmp/general-task-checkpoint.json"
   printf '{"in_flight_step":"%s","timestamp":"%s"}\n' "$STEP" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$CHECKPOINT"
   ```
2. In `plan` (`scripts/little_loops/loops/general-task.yaml:57`) or a new `resume_check` state (inserted between `plan` and `select_step`): add logic to detect `general-task-checkpoint.json`; if present and the in-flight step's expected output files already exist (from `general-task-last-files.txt`), mark the step `[x]` and skip re-execution
3. In `mark_done` (`scripts/little_loops/loops/general-task.yaml:143`): add `rm -f "${env.PWD}/.loops/tmp/general-task-checkpoint.json"` on the line after the existing `rm -f "$STEP_FILE"`
4. Add test in `scripts/tests/test_general_task_loop.py` following `TestGeneralTaskLoopFile.test_validates_as_fsm` using `load_and_validate()` + `validate_fsm()`; add fixture at `scripts/tests/fixtures/fsm/checkpoint-recovery.yaml` with a partial-state scenario
5. Run `ll-loop validate scripts/little_loops/loops/general-task.yaml` to confirm no routing regressions

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/guides/LOOPS_GUIDE.md` — reflect checkpoint write in `select_step`, checkpoint clear in `mark_done`; add `resume_check` state if inserted; update iteration-count math (6 → 7)
7. Update `TestENH1732StateSplit.test_plan_routes_to_select_step` (`scripts/tests/test_general_task_loop.py:281`) if `plan` routes to `resume_check` instead of `select_step`
8. Update `TestBUG1687ContinueWorkCapture.test_continue_work_routes_to_select_step` (`scripts/tests/test_general_task_loop.py:197`) if `continue_work` routing changes
9. Update `diagnose` state action text in `general-task.yaml` to include `resume_check` in the enumerated state names list (if state is added)

## Impact

- **Priority**: P3 — Improves robustness for an edge case (SIGKILL/OOM during execute); not blocking for normal operation
- **Effort**: Low — Small shell snippet added to existing states; no new dependencies
- **Risk**: Low — Additive change; doesn't alter existing routing or evaluation logic

## Labels

- loops
- general-task
- resilience
- crash-recovery

## Status

**Open** | Created: 2026-05-27 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-05-27T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/88f2fc64-a60a-4bdb-80d0-9adf7d6a62c9.jsonl`
- `/ll:wire-issue` - 2026-05-27T23:35:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bdf71221-6071-432b-bbc4-72085ee3754e.jsonl`
- `/ll:refine-issue` - 2026-05-27T23:25:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/abccc340-0707-4df4-86fc-a611f1735bf0.jsonl`
- `/ll:format-issue` - 2026-05-27T23:19:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cff51961-5730-4e30-9a41-1339eda2b782.jsonl`
