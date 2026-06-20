---
id: ENH-2244
type: ENH
priority: P3
status: done
captured_at: '2026-06-20T00:00:00Z'
completed_at: '2026-06-20T17:32:18Z'
discovered_date: 2026-06-20
discovered_by: audit-loop-run
labels:
- enhancement
- fsm
- general-task
- reliability
confidence_score: 98
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 22
decision_needed: false
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
   `scripts/little_loops/loops/general-task.yaml`. Write the full test output to
   `baseline-test-output.txt` and write the exit code to `baseline-exit.txt` — both
   under `${context.run_dir}/` for cross-state communication via the filesystem
   (consistent with the existing pattern of `verify-output.txt`). No context capture
   needed:
   ```yaml
   check_baseline_tests:
     action: |
       CMD=$(python3 -c "import json,pathlib; p=pathlib.Path('.ll/ll-config.json'); cfg=json.loads(p.read_text()) if p.exists() else {}; print(cfg.get('project',{}).get('test_cmd','pytest'))")
       eval "$CMD" > "${context.run_dir}/baseline-test-output.txt" 2>&1
       echo $? > "${context.run_dir}/baseline-exit.txt"
     action_type: shell
     next: define_done
     on_error: define_done
   ```
2. Inline the baseline comparison in `run_final_tests` — no separate `compare_baseline`
   state. After running the test command, capture `$?` immediately (before any other
   command can overwrite it), read `baseline-exit.txt`, and exit 0 only if there is no
   regression (final_exit=0 OR final_exit=baseline_exit). The `shell_exit` fragment
   routes on the shell exit code, so the final line of the action determines routing:
   ```yaml
   run_final_tests:
     fragment: shell_exit
     timeout: 1800
     action: |
       if [ -n "${context.test_cmd}" ]; then
         CMD="${context.test_cmd}"
       else
         CMD=$(python3 -c "
       import json, pathlib
       p = pathlib.Path('.ll/ll-config.json')
       cfg = json.loads(p.read_text()) if p.exists() else {}
       raw = cfg.get('project', {}).get('test_cmd')
       print(raw if raw else 'pytest')
       ")
       fi
       eval "$CMD" > "${context.run_dir}/verify-output.txt" 2>&1
       FINAL_EXIT=$?
       BASELINE_EXIT=$(cat "${context.run_dir}/baseline-exit.txt" 2>/dev/null || echo "0")
       [ "$FINAL_EXIT" = "0" ] || [ "$FINAL_EXIT" = "$BASELINE_EXIT" ]
     on_yes: count_final
     on_no: continue_work
     on_error: diagnose
   ```
3. Update `initial: define_done` → `initial: check_baseline_tests`.
4. Add unit test in `scripts/tests/test_builtin_loops.py` verifying the new state
   routes correctly when baseline is exit_code=1.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-20.

Three open design decisions from the confidence-check were resolved by reading the actual
`general-task.yaml` and `lib/common.yaml`:

**Decision 1 — Artifact naming**: Canonical artifact names are `baseline-exit.txt`
(exit code only) and `baseline-test-output.txt` (full test stdout/stderr). The acceptance
criteria already used `baseline-exit.txt`; the implementation steps are now consistent
with it.

**Decision 2 — Exit-code capture**: Option (b) — inline comparison inside
`run_final_tests`, no `compare_baseline` state. The original `compare_baseline` action
used `FINAL=$?` which would capture the exit code of the preceding `grep` command, not
`run_final_tests`. The `shell_exit` fragment routes on the exit code of the entire action
block, so capturing `$?` immediately after `eval "$CMD"` and emitting the correct final
exit code from the last line is correct and requires no new FSM state.

**Decision 3 — Capture mechanism**: Use filesystem (`baseline-exit.txt`) for
cross-state communication, not `capture:` context variables. The loop already uses this
pattern (`verify-output.txt`), and shell states cannot reliably read captured context
values from earlier states in their action bodies.

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
- `scripts/little_loops/loops/general-task.yaml` — add `check_baseline_tests` state, update `initial:` to point to it, inline baseline comparison in `run_final_tests`

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

## Resolution

Implemented 2026-06-20. Added `check_baseline_tests` shell state that runs the project's test command before `define_done` and writes the exit code to `${context.run_dir}/baseline-exit.txt`. Updated `run_final_tests` to capture `FINAL_EXIT` immediately after `eval "$CMD"`, read `BASELINE_EXIT` from that file, and exit 0 only when there is no regression (`FINAL_EXIT=0 OR FINAL_EXIT=BASELINE_EXIT`). Added 7 unit tests in `TestGeneralTaskLoop` covering initial state, routing, artifact naming, and comparison logic.

## Status

**Done** | Created: 2026-06-20 | Completed: 2026-06-20 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-20_

**Readiness Score**: 94/100 → PROCEED
**Outcome Confidence**: 74/100 → below threshold

### Outcome Risk Factors
- **Artifact naming — open decision**: Three different names appear for the baseline artifact (`baseline-test-output.txt` in the `check_baseline_tests` action, `baseline-test-result` in `compare_baseline`, and `baseline-exit.txt` in acceptance criteria). Resolve before implementing: canonicalize to a single name and update all three locations.
- **Exit-code capture — open decision**: `compare_baseline` uses `FINAL=$?`, but `run_final_tests` uses the `shell_exit` fragment which routes on exit code without writing it to a file. `$?` in the compare state would capture the last command in that state's action, not `run_final_tests`. The implementation needs either: (a) modify `run_final_tests` to write its exit code to a file (`echo $? > ${context.run_dir}/final-exit.txt`) before exiting, or (b) inline the comparison in `run_final_tests` itself and remove `compare_baseline` entirely.
- **Capture mechanism — open decision**: `check_baseline_tests` sets `capture: baseline_test_result` (a context variable), but `compare_baseline` reads from a filesystem path via grep. Decide whether to pass the baseline exit code via context capture or via file, and apply consistently across both states.

## Session Log
- `/ll:ready-issue` - 2026-06-20T17:26:44 - `69a8917a-3f9a-40e3-bb44-c6f8400c3601.jsonl`
- `/ll:confidence-check` - 2026-06-20T17:30:00Z - `623044f8-c1bc-4550-8d79-b31acf4cd60c.jsonl`
- `/ll:decide-issue` - 2026-06-20T17:19:38 - `e77be12a-9cd4-4065-94f2-dff2780e327c.jsonl`
- `/ll:format-issue` - 2026-06-20T14:26:48 - `baebe263-e6b7-4ad2-8dea-f55423552373.jsonl`
- `/ll:confidence-check` - 2026-06-20T00:00:00Z - `baebe263-e6b7-4ad2-8dea-f55423552373.jsonl`
