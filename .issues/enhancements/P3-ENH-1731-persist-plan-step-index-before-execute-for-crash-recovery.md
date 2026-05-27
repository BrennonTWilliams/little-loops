---
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
labels:
- loops
- general-task
- resilience
- crash-recovery
confidence_score: 80
---

# ENH-1731: Persist plan step index before execute for crash recovery

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

## Impact

- **Priority**: P3 — Improves robustness for an edge case (SIGKILL/OOM during execute); not blocking for normal operation
- **Effort**: Low — Small shell snippet added to existing states; no new dependencies
- **Risk**: Low — Additive change; doesn't alter existing routing or evaluation logic

## Labels

- loops
- general-task
- resilience
- crash-recovery
