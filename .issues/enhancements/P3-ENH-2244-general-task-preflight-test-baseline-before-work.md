---
id: ENH-2244
type: ENH
priority: P3
status: open
captured_at: '2026-06-20T00:00:00Z'
discovered_date: 2026-06-20
discovered_by: audit-loop-run
labels:
- enhancement
- fsm
- general-task
- reliability
---

# ENH-2244: Add pre-flight test baseline state to general-task loop

## Motivation

Without a pre-task baseline, the `general-task` loop cannot distinguish pre-existing test failures from regressions introduced by its own changes. This caused a concrete failure mode:
- 18 × `run_final_tests` failures consumed 144/201 iterations in the `2026-06-20T035602` run
- All 18 failures were pre-existing (introduced by unrelated commit `82b1248d`)
- Loop terminated via `summarize_partial` (max_steps exhausted) despite all task work being complete
- Cost: ~8 FSM states per false failure × 18 = 144 wasted iterations; misleading "partial" outcome reported

## Summary

The `general-task` loop has no way to distinguish "tests are failing because of my
changes" from "tests were already failing before I started." In the `2026-06-20T035602`
run, 45 pre-existing test failures (from ENH-2243 commit `82b1248d`, unrelated to the
doc-audit task) caused 18 consecutive `run_final_tests` failures before the loop fixed
them. Each failure consumed ~8 FSM states, burning 144 of 201 total iterations on
pre-existing breakage — causing the loop to terminate via `summarize_partial` (max_steps
exhausted) rather than the normal `done` path, even though all task work was complete.

## Current Behavior

`general-task` begins at `define_done` with no knowledge of the test suite's pre-task
baseline. When `run_final_tests` fails (exit_code=1), the loop always treats this as a
task defect and appends remediation steps, even when the failure pre-dates the loop's
first action.

## Expected Behavior

A new `check_baseline_tests` state runs the test suite once before `define_done` and
writes the baseline exit code to `${context.run_dir}/baseline-exit.txt`. The final
`run_final_tests` evaluator then compares against the baseline: if the baseline was
already exit_code=1, a matching final exit_code=1 is treated as pass (no regression);
if the baseline was exit_code=0, the evaluator requires exit_code=0.

## Implementation Steps

1. Add `check_baseline_tests` state before `define_done` in
   `scripts/little_loops/loops/general-task.yaml`:
   ```yaml
   check_baseline_tests:
     action: |
       CMD=$(python3 -c "import json,pathlib; p=pathlib.Path('.ll/ll-config.json'); cfg=json.loads(p.read_text()) if p.exists() else {}; print(cfg.get('project',{}).get('test_cmd','pytest'))")
       eval "$CMD" > "${context.run_dir}/baseline-test-output.txt" 2>&1
       echo "BASELINE_EXIT:$?"
     action_type: shell
     capture: baseline_test_result
     next: define_done
     on_error: define_done
   ```
2. Update `run_final_tests` to write its exit code to a capture, then add a
   `compare_baseline` shell state that reads both exit codes and outputs
   `BASELINE_MATCH` or `REGRESSION`:
   ```yaml
   compare_baseline:
     action: |
       BASELINE=$(grep 'BASELINE_EXIT:' "${context.run_dir}/baseline-test-result" | sed 's/BASELINE_EXIT://')
       FINAL=$?   # captured from run_final_tests
       [ "$FINAL" = "$BASELINE" ] && echo "BASELINE_MATCH" || echo "REGRESSION"
     action_type: shell
     evaluate:
       type: output_contains
       pattern: BASELINE_MATCH
     on_yes: count_final
     on_no: continue_work
   ```
3. Update `initial: define_done` → `initial: check_baseline_tests`.
4. Add unit test in `scripts/tests/test_builtin_loops.py` verifying the new state
   routes correctly when baseline is exit_code=1.

## Scope Boundaries

- **In scope**: Adding `check_baseline_tests` state to `general-task.yaml`; baseline vs. final exit-code comparison; unit test coverage for both baseline-pass and baseline-fail paths
- **Out of scope**: Modifying other loop types; baseline comparison for non-test evaluators; persisting baselines across separate `ll-loop run` invocations

## Acceptance Criteria

- [ ] `check_baseline_tests` runs before `define_done` in all new general-task runs
- [ ] When baseline tests are already failing (exit_code=1), `run_final_tests` exit_code=1
  is treated as `BASELINE_MATCH` (not a regression)
- [ ] When baseline tests pass (exit_code=0), `run_final_tests` still requires exit_code=0
- [ ] `baseline-test-output.txt` is written to `${context.run_dir}/` (not bare `.loops/tmp/`)
- [ ] Tests pass: `python -m pytest scripts/tests/test_builtin_loops.py -k general_task`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — add `check_baseline_tests` state, update `initial:` to point to it, add `compare_baseline` state

### Dependent Files (Callers/Importers)
- TBD — use grep: `grep -r "general-task" scripts/` to find orchestration callers

### Similar Patterns
- Other loop YAMLs under `scripts/little_loops/loops/` — check for existing shell capture patterns to reuse

### Tests
- `scripts/tests/test_builtin_loops.py` — add test verifying `check_baseline_tests` routes correctly for both exit_code=0 and exit_code=1 baselines

### Documentation
- N/A — internal loop enhancement; no public API changes

### Configuration
- N/A — reads `test_cmd` from `.ll/ll-config.json` via inline shell command in state action

## Impact

- **Priority**: P3 — Loop reliability improvement; failure mode produces misleading outcomes but does not block task completion in the normal case
- **Effort**: Small — One YAML file (new states + updated `initial:`); one new unit test; follows existing FSM shell/capture patterns
- **Risk**: Low — Additive change; `check_baseline_tests` routes to `define_done` on completion or error, so existing happy path is unchanged; no breaking changes
- **Breaking Change**: No

## Context

Observed in loop run `2026-06-20T035602-general-task` (audit-loop-run assessment):
- 18 × `run_final_tests` failures (exit_code=1) consumed 144/201 iterations
- All failures pre-dated the loop's work (introduced by commit `82b1248d`)
- Loop terminated via `summarize_partial` despite all DoD criteria being verified

## Status

**Open** | Created: 2026-06-20 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-20T14:26:48 - `baebe263-e6b7-4ad2-8dea-f55423552373.jsonl`
