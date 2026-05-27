---
title: Split general-task execute state into granular sub-states to limit per-action duration
type: ENH
priority: P3
effort: Medium
impact: High
risk: Medium
status: open
captured_at: '2026-05-27T00:00:00Z'
discovered_date: 2026-05-27
discovered_by: audit-loop-run
labels:
- loops
- general-task
- decomposition
- resilience
confidence_score: 75
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

## Integration Map

| File | Change |
|------|--------|
| `loops/general-task.yaml` | Replace `execute` state with `select_step`, `do_work`, `verify_step`, `mark_done`; update `continue_work` to route into `do_work` instead of old `execute`; update initial routing (`plan → select_step` instead of `plan → execute`) |
| `scripts/tests/` | Add test for the split-state routing (select_step → do_work → verify_step → mark_done → check_done); test verify_step on_no → continue_work → do_work loop |
| `docs/guides/LOOPS_GUIDE.md` | Optional: update general-task documentation if it documents the internal state machine |

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
