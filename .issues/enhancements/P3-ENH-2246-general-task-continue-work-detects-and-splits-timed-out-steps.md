---
id: ENH-2246
type: ENH
priority: P3
status: done
captured_at: '2026-06-20T00:00:00Z'
completed_at: '2026-06-20T18:17:22Z'
discovered_date: 2026-06-20
discovered_by: audit-loop-run
labels:
- enhancement
- general-task
- fsm
confidence_score: 90
outcome_confidence: 79
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 15
score_change_surface: 22
---

# ENH-2246: continue_work should detect do_work timeout (exit_code=124) and split the step

## Motivation

When `do_work` exhausts retries due to timeouts (exit_code=124), `continue_work` currently appends a remediation step targeting an unmet DoD criterion. That remediation step will also time out — creating a permanent stall from which the loop cannot recover without human intervention. Splitting the oversized step is the correct recovery action, but the prompt has no signal to distinguish a timeout failure from a correctness failure.

## Summary

When `do_work` exhausts its `max_retries: 2` due to timeouts (exit_code=124), the loop
routes to `continue_work` via `on_retry_exhausted`. Currently, `continue_work`'s prompt
has no awareness that the previous step timed out — it treats a timeout the same as any
other failure and appends a generic remediation step. The right response to a timeout is
to **split the step** into two or more smaller steps, not to append another remediation
step that will likely time out too.

In the `2026-06-20T035602` general-task run, `do_work` timed out 3 times (exit_code=124
at 900s). In each case, `continue_work` was reached via `on_retry_exhausted`, but the
prompt had no signal that the step was too large for the timeout window.

## Current Behavior

`continue_work` prompt text: "Find the first unchecked DoD criterion... append a new
remediation step." This is appropriate for a correctness failure but wrong for a timeout —
a timed-out step is too large, not incorrect.

`do_work` captures `work_result` which includes `exit_code`. The `continue_work` prompt
references `${captured.work_result.output}` but not `${captured.work_result.exit_code}`.

## Expected Behavior

`continue_work` checks `${captured.work_result.exit_code}`:
- If 124 (timeout): prompt instructs the agent to **split the timed-out step** into
  2–3 smaller independently-completable steps and insert them before the next unchecked step.
- Otherwise: current remediation behaviour (append a step targeting the first unmet DoD criterion).

## Implementation Steps

1. Update `continue_work.action` in `scripts/little_loops/loops/general-task.yaml` to
   include a timeout-detection branch:
   ```
   LAST_EXIT_CODE=$(cat "${context.run_dir}/last-exit-code.txt" 2>/dev/null || echo "0")
   if [ "$LAST_EXIT_CODE" = "124" ]; then
     echo "TIMEOUT_DETECTED"
   fi
   ```
2. Write `do_work`'s exit code to `${context.run_dir}/last-exit-code.txt` via the
   shell runner after each action_complete (or add a `capture_exit_code: true` option
   to the FSM config).
3. Update the `continue_work` prompt body with a conditional instruction:
   ```
   The previous do_work exited with code 124 (timeout). This means the step was too
   large to complete within ${context.work_timeout}s. Split the timed-out step from
   current-step.txt into 2-3 smaller steps in plan.md. Do NOT append a remediation
   step for a DoD criterion — the step was sound but oversized.
   ```
4. No schema changes needed; this is a YAML prompt update only.

## Acceptance Criteria

- [ ] When `do_work` times out (exit_code=124) and routes to `continue_work`, the
  `continue_work` prompt detects the timeout and instructs step-splitting rather than
  DoD-criterion remediation
- [ ] When `do_work` fails for other reasons (exit_code≠0, ≠124), `continue_work`
  behaves as today (appends a remediation step)
- [ ] `last-exit-code.txt` is written to `${context.run_dir}/` (not bare `.loops/tmp/`)
- [ ] Unit test verifying timeout-split branch in `scripts/tests/test_builtin_loops.py`

## Scope Boundaries

- No FSM executor or YAML schema changes — prompt update only
- No changes to timeout values or `max_retries` configuration
- `do_work` action body is unchanged; only adds exit-code capture to a sidecar file
- Does not handle partial-timeout cases (e.g., timeout on retry 1 but success on retry 2)
- Scoped to `general-task.yaml` only; other loops with `do_work` states are out of scope

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — update `continue_work` prompt body; add exit-code capture to `do_work` post-action shell

### Dependent Files (Callers/Importers)
- N/A — YAML loop file invoked by `ll-loop run general-task`

### Similar Patterns
- Other loops with `do_work` + `continue_work` pairing may benefit from the same timeout-detection pattern in a follow-up

### Tests
- `scripts/tests/test_builtin_loops.py` — add test for timeout-split branch (exit_code=124 routes to split, not DoD remediation)

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — Loop stalls permanently on oversized steps, but only affects runs where every retry times out; manually splitting steps is an acceptable workaround
- **Effort**: Small — YAML prompt update and a one-line exit-code capture; no Python changes, no schema changes
- **Risk**: Low — Additive change; non-timeout failure paths are entirely unchanged
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-20 | Priority: P3

## Context

Observed in loop run `2026-06-20T035602-general-task` (audit-loop-run assessment):
- 3 × `do_work` exit_code=124 (15-minute timeout exhausted), all routes to `continue_work`
- `continue_work` had no signal to split rather than append


## Resolution

- Added `capture_work_exit` shell state that writes `${context.run_dir}/last-exit-code.txt` with the do_work exit code
- Changed `do_work.on_retry_exhausted` to route through `capture_work_exit` before `continue_work`
- Updated `continue_work` prompt to reference `${captured.work_result.exit_code:default=0}` and branch on exit code 124 (split step) vs other failures (DoD remediation)
- Added 10 unit tests in `TestGeneralTaskLoop` covering all acceptance criteria

## Session Log
- `/ll:ready-issue` - 2026-06-20T18:07:28 - `33967be3-0f13-4771-a0c5-e16f36d02d59.jsonl`
- `/ll:format-issue` - 2026-06-20T14:25:58 - `bee582da-5285-4690-892c-a09d1cfe4553.jsonl`
- `/ll:manage-issue` - 2026-06-20T18:17:22 - implementation complete
