---
id: BUG-1960
type: BUG
priority: P2
status: open
captured_at: '2026-06-05T18:05:10Z'
discovered_date: 2026-06-05
discovered_by: capture-issue
parent: EPIC-1962
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1960: general-task.yaml Uses Shared .loops/tmp/ Paths Causing Cross-Run State Corruption

## Summary

`scripts/little_loops/loops/general-task.yaml` writes all intermediate artifacts (checkpoint, plan, DoD, current-step, last-files) to `.loops/tmp/` with hardcoded filenames. This directory is shared across all runs of the same loop within a project. A stale checkpoint from a prior unrelated task causes `resume_check` to emit a false `RESUME_SKIP`, bypassing `select_step`, leaving `captured.selected_step` unpopulated, and crashing in `check_done` when it references `${captured.selected_step.output}`.

The runner already provides per-run isolation via `${context.run_dir}` (`.loops/runs/<loop>-<timestamp>/`), but `general-task.yaml` doesn't use it. MR-3 in the validator warns about `.loops/tmp/` usage but is only WARNING severity.

Additionally, `resume_check` has two specific defects that compound the shared-state problem: (1) it doesn't verify `current-step.txt` exists (inconsistent file set detection), and (2) it has no task fingerprinting to distinguish checkpoints from different tasks.

## Current Behavior

All 8+ artifact paths in `general-task.yaml` use `.loops/tmp/general-task-*`:

| File | Purpose |
|------|---------|
| `.loops/tmp/general-task-dod.md` | Definition of Done |
| `.loops/tmp/general-task-plan.md` | Task step plan |
| `.loops/tmp/general-task-checkpoint.json` | In-flight step checkpoint |
| `.loops/tmp/general-task-current-step.txt` | Currently selected step text |
| `.loops/tmp/general-task-last-files.txt` | Files modified by worker |
| `.loops/tmp/general-task-summary.md` | Partial completion summary |

**Failure trace** (from a real run, 2026-06-05):
```
[1] define_done → ✅ (wrote DoD)
[2] plan → ✅ (wrote 12-step plan)
[3] resume_check → RESUME_SKIP (FALSE POSITIVE — stale checkpoint from different task)
[4] mark_done → ✅ (marked nothing meaningful — select_step was bypassed)
[5] check_done → ❌ Path 'selected_step' not found in captured → diagnose (terminal)
[6] diagnose → terminal
```

**Two specific defects in `resume_check`:**

1. **No `current-step.txt` existence check**: `mark_done` deletes both `current-step.txt` and `checkpoint.json` (lines 196-197), but not atomically. If only the checkpoint survives (e.g., from a prior run that was interrupted between the two `rm` calls, or from a different task entirely), `resume_check` proceeds to check `last-files.txt` and may emit `RESUME_SKIP` if the referenced files happen to exist.

2. **No task fingerprinting**: The checkpoint JSON `{"in_flight_step":"...","timestamp":"..."}` has no field identifying which task it belongs to. A checkpoint from "Implement the plan in remotion-plan.md" can trigger a false resume for "Fix the bug in auth.py."

## Expected Behavior

1. All per-run artifacts should use `${context.run_dir}/` (e.g., `${context.run_dir}/checkpoint.json`), providing automatic isolation between runs
2. `resume_check` should verify `current-step.txt` exists alongside `checkpoint.json` — if one is missing, the file set is inconsistent and should be treated as `RESUME_CLEAN`
3. `resume_check` (or `select_step`) should include a task fingerprint in the checkpoint so cross-task checkpoints are detected and discarded
4. `check_done.on_error` should route to `select_step` (recoverable) instead of `diagnose` (terminal), as a safety net for any remaining missing-capture edge cases

## Motivation

- **Silent data corruption**: Stale checkpoint state from a prior run silently corrupts the current run with zero errors until the crash
- **User impact**: The loop terminates after 6 iterations with zero productive work done; user must manually clean `.loops/tmp/` and re-run
- **MR-3 is unenforceable**: The validator can't elevate MR-3 from WARNING to ERROR while a built-in loop violates it
- **Template hazard**: `general-task.yaml` is the most-copied loop template; its pattern of `.loops/tmp/` usage propagates to user-created loops

## Steps to Reproduce

1. Run `ll-loop run general-task "Task A: write foo.py"` — let it complete `plan` state, then interrupt (Ctrl+C) during `do_work`
2. Run `ll-loop run general-task "Task B: write bar.py"` — observe `resume_check` may emit `RESUME_SKIP` if `last-files.txt` from Task A references files that still exist, causing the loop to skip `select_step` and crash in `check_done`

## Root Cause

- **File**: `scripts/little_loops/loops/general-task.yaml`
- **Anchor**: `resume_check` state (lines 84-115), `select_step` state (lines 117-137), `check_done` state (line 254)
- **Cause**: Three compounding factors:
  1. **Shared state**: All artifacts in `.loops/tmp/` with no per-run or per-task isolation
  2. **Incomplete resume validation**: `resume_check` checks checkpoint file existence + last-files existence, but not `current-step.txt` consistency or task identity
  3. **Fragile error routing**: `check_done` references `${captured.selected_step.output}` but `on_error: diagnose` makes this terminal rather than recoverable

## Proposed Solution

### Fix 1: Migrate to `${context.run_dir}/` (structural)

Replace all `.loops/tmp/general-task-*` paths with `${context.run_dir}/*`:

```
.loops/tmp/general-task-dod.md          → ${context.run_dir}/dod.md
.loops/tmp/general-task-plan.md         → ${context.run_dir}/plan.md
.loops/tmp/general-task-checkpoint.json → ${context.run_dir}/checkpoint.json
.loops/tmp/general-task-current-step.txt → ${context.run_dir}/current-step.txt
.loops/tmp/general-task-last-files.txt  → ${context.run_dir}/last-files.txt
.loops/tmp/general-task-summary.md      → ${context.run_dir}/summary.md
```

The runner creates `${context.run_dir}` before execution and it's timestamped per-run, so no two runs share state.

### Fix 2: Add `current-step.txt` consistency check (defensive)

In `resume_check`, after confirming checkpoint exists, add:

```bash
CURRENT_STEP="${context.run_dir}/current-step.txt"
if [ ! -f "$CURRENT_STEP" ]; then
  # Inconsistent: checkpoint exists but current-step.txt doesn't.
  # mark_done deletes both, so this is a stale/corrupt checkpoint.
  rm -f "$CHECKPOINT"
  echo "RESUME_CLEAN"
  exit 0
fi
```

### Fix 3: Add task fingerprint to checkpoint (defense-in-depth)

ENH-1959 `input_hash` is **already implemented** (injected at `run.py:167-169` and `lifecycle.py:468-470`). Use `${context.input_hash}` directly in `select_step`:

```bash
printf '{"in_flight_step":"%s","timestamp":"%s","task_hash":"%s"}\n' \
  "$STEP" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${context.input_hash}" > "$CHECKPOINT"
```

And validate in `resume_check`:

```bash
STORED_HASH=$(grep -o '"task_hash":"[^"]*"' "$CHECKPOINT" | sed 's/"task_hash":"//;s/"//')
if [ -n "$STORED_HASH" ] && [ "${context.input_hash}" != "$STORED_HASH" ]; then
  rm -f "$CHECKPOINT" "$CURRENT_STEP" "${context.run_dir}/last-files.txt"
  echo "RESUME_CLEAN"
  exit 0
fi
```

### Fix 4: Make `check_done.on_error` recoverable (safety net)

Change `check_done.on_error` from `diagnose` to `select_step` so that any remaining missing-capture edge case recovers by re-selecting a step instead of terminating.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — migrate all artifact paths to `${context.run_dir}/`, add `current-step.txt` check, add task fingerprinting, change `check_done.on_error` routing
- `scripts/tests/test_general_task_loop.py` — add tests for: inconsistent file set detection, cross-task checkpoint rejection, `check_done` recovery routing

### Dependent Files (Callers/Importers)
- `scripts/tests/test_builtin_loops.py` — validates all built-in loops parse; no changes needed if YAML remains valid
- Any user loops modeled after `general-task.yaml` — they benefit from the fixed pattern but aren't automatically updated

### Similar Patterns
- BUG-744 (done): Cross-project `/tmp/` conflicts — fixed by moving to `.loops/tmp/`, but didn't address cross-run isolation within a project
- BUG-817 (done): Same pattern as BUG-744
- ENH-1957 (open): Per-iteration artifact versioning in `run_dir` — complementary; this bug fixes cross-run isolation, that enhancement adds intra-run versioning
- ENH-1958 (open): Safe interpolation syntax — would make `check_done` resilient to missing captures regardless of routing
- ENH-1959 (open): Auto-inject `input_hash` — provides the fingerprinting primitive used in Fix 3

### Tests
- `test_general_task_loop.py::TestResumeCheckShellAction`:
  - `test_checkpoint_without_current_step_emits_resume_clean` — checkpoint exists but `current-step.txt` missing
  - `test_checkpoint_task_hash_mismatch_emits_resume_clean` — checkpoint from different task
- `test_general_task_loop.py::TestSelectStepShellAction`:
  - `test_checkpoint_contains_task_hash` — verify checkpoint JSON includes `task_hash` field
- `test_general_task_loop.py::TestCheckDoneErrorRouting`:
  - `test_check_done_on_error_routes_to_select_step` — structural test

### Documentation
- `docs/guides/LOOPS_GUIDE.md:368` — references `.loops/tmp/general-task-dod.md` path pattern; needs update to `${context.run_dir}/dod.md` after migration

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Reference Implementations (Loops Already Using `${context.run_dir}`)

These loops correctly use `${context.run_dir}/` for per-run artifact isolation — model the migration after them:

- `scripts/little_loops/loops/autodev.yaml` — all per-run artifacts (`queue.txt`, `passed.txt`, `skipped.txt`, etc.) under `${context.run_dir}/`
- `scripts/little_loops/loops/rn-implement.yaml` — captures `RUN_DIR="${context.run_dir}"` as local shell variable, writes `checkpoint.json` at line 239
- `scripts/little_loops/loops/rn-remediate.yaml` — per-issue artifacts and counter files in `run_dir`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — state flags (`refine-count`, `wire-done`, `broke-down`) in `run_dir`
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — per-iteration snapshots with `iter-N/` subdirectories in `run_dir`

**Common pattern**: Capture `RUN_DIR="${context.run_dir}"` once at the top of each shell action, then use `"$RUN_DIR/..."` for all paths. The runner creates `run_dir` before execution at `run.py:405` (`Path(fsm.context["run_dir"]).mkdir(parents=True, exist_ok=True)`), so no additional `mkdir -p` is needed in most states.

#### ENH-1959 `input_hash` — Already Available

The `${context.input_hash}` context variable is **already implemented and injectable** (12-char SHA-256 hex digest):

- **Injected** at `run.py:167-169` (`cmd_run()`) and `lifecycle.py:468-470` (`cmd_resume()`)
- **Registered** in `RUNNER_INJECTED` at `validation.py:422`
- **Tests exist** at `test_ll_loop_program_md.py:333`, `test_cli_loop_lifecycle.py:665`, `test_ll_loop_commands.py:2660`

Fix 3 can use `${context.input_hash}` directly — no `md5`/`md5sum` fallback needed.

#### Widespread `.loops/tmp/` Usage

19 other built-in loop YAMLs also reference `.loops/tmp/` paths (same vulnerability pattern but not part of this bug):
`fix-quality-and-tests.yaml`, `scan-and-implement.yaml`, `auto-refine-and-implement.yaml`, `evaluation-quality.yaml`, `recursive-refine.yaml` (128 refs), `loop-router.yaml`, `harness-optimize.yaml`, `prompt-across-issues.yaml`, `dead-code-cleanup.yaml`, `issue-refinement.yaml`, `test-coverage-improvement.yaml`, `autodev.yaml` (1 ref — mixed with `run_dir` usage), `harness-multi-item.yaml`, `prompt-regression-test.yaml`, `context-health-monitor.yaml`, `hitl-md.yaml`, `sprint-refine-and-implement.yaml`, `lib/common.yaml`, `oracles/implement-issue-chain.yaml`

#### Error Propagation Chain

When `check_done` interpolation fails, the error propagates through:
1. `executor.py:1041` — `interpolate(action_template, ctx)` raises `InterpolationError`
2. `executor.py:1554` — caught by `_run_action_or_route()`, routes to `on_error: diagnose`
3. `executor.py:850-852` — `routed` target `"diagnose"` returned from `_execute_state()`
4. `diagnose` → `failed` (terminal) — loop terminates with zero productive work

Changing `check_done.on_error` to `select_step` would make this a graceful recovery: the loop re-selects the next unchecked step and continues. Precedent exists in `autodev.yaml` (`on_error: dequeue_next` pattern).

## Implementation Steps

1. **Migrate paths to `${context.run_dir}`** — replace all 6+ `.loops/tmp/general-task-*` paths in shell actions and prompt text
2. **Add `current-step.txt` consistency check** to `resume_check` — if checkpoint exists but `current-step.txt` doesn't, emit `RESUME_CLEAN`
3. **Add task fingerprint** to `select_step` checkpoint write and `resume_check` validation using `${context.input_hash}` (already injected by runner — see Codebase Research Findings)
4. **Change `check_done.on_error`** from `diagnose` to `select_step`
5. **Add regression tests** — all scenarios listed above
6. **Validate**: `ll-loop validate general-task` and `python -m pytest scripts/tests/test_general_task_loop.py -x --tb=short`
7. **Manual verification**: Run the loop, interrupt during `do_work`, re-run with same task (should `RESUME_SKIP`), re-run with different task (should `RESUME_CLEAN`)

## Impact

- **Priority**: P2 — Causes silent cross-run state corruption; loop terminates with zero productive work
- **Effort**: Medium — ~30 lines changed in YAML + tests + validation
- **Risk**: Medium — path migration touches every state in the loop; careful testing required
- **Breaking Change**: No — `${context.run_dir}` is already injected by the runner

## Related Key Documentation

- `docs/guides/LOOPS_GUIDE.md:342-368` — Documents the general-task loop cycle and references `.loops/tmp/general-task-dod.md` path (stale after migration)
- `docs/generalized-fsm-loop.md` — Documents `${context.run_dir}` and `${context.input_hash}` context variables
- `scripts/little_loops/loops/README.md` — Lists all built-in loops including `general-task`

## Labels

`bug`, `loops`, `general-task`, `checkpoint`, `state-corruption`, `cross-run`

## Status

**Open** | Created: 2026-06-05 | Priority: P2

## Session Log
- `/ll:refine-issue` - 2026-06-05T18:53:22 - `47a35864-3a17-4930-ab95-a305446443dc.jsonl`
- `/ll:format-issue` - 2026-06-05T18:13:23 - `3eca5207-7b01-419b-a330-d3c0b875236c.jsonl`
- `/ll:capture-issue` - 2026-06-05T18:05:10Z - `6111e846-8894-477b-81b3-17824f89e659.jsonl`
- `/ll:confidence-check` - 2026-06-05T19:00:00Z - `019fd1ab-9146-492e-9c9c-c7136c94137c.jsonl`
