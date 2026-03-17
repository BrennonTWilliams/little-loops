---
discovered_date: 2026-03-17
discovered_by: session
---

# ENH-793: general-task loop — add plan state and per-step execution constraints

## Summary

The `general-task` built-in loop executed entire tasks in a single Claude session, preventing
the handoff threshold from ever firing and making progress unrecoverable if context was exhausted.
Added a `plan` state for upfront decomposition and constrained `execute`/`continue_work` to one
step per iteration.

## Context

During a `ll-loop run general-task` session with `--handoff-threshold 35`, a docs-review task
completed in 2 iterations (11 min 39 s for the `execute` state). The handoff threshold was never
reached because the agent finished everything in one shot before context dropped to 35%.

Root cause: the original `execute` state used `${context.input}` verbatim as its action — Claude
received the full task and naturally attempted to complete all of it in one response session.

## Original Behavior

```yaml
initial: execute

states:
  execute:
    action: "${context.input}"   # raw task, no constraints
    action_type: prompt
    next: check_done
```

- Entire task attempted in one iteration
- Handoff threshold effectively unreachable for moderate-sized tasks
- `continue_work` said "be thorough and finish completely" — same unbounded behavior

## New Behavior

```
[1/N] plan      → creates /tmp/ll-general-task-plan.md checklist
[2/N] execute   → completes FIRST unchecked step only, marks [x]
[3/N] check_done → no → continue_work
[4/N] continue_work → completes NEXT unchecked step only
...
[N/N] check_done → yes → done
```

- `plan` state: decomposes task into numbered steps, writes to `/tmp/ll-general-task-plan.md`
- `execute` / `continue_work`: explicitly instructed to complete one unchecked step, update
  the plan file, and stop
- Each step gets its own Claude session — handoff threshold becomes meaningful

## Changes Made

- `.loops/general-task.yaml`:
  - Changed `initial` from `execute` → `plan`
  - Added `plan` state with decomposition prompt
  - Rewrote `execute` action to read plan file and complete one step
  - Rewrote `continue_work` action (same one-step constraint as `execute`)

## Tradeoffs

- Adds 1 extra iteration (the plan state) before work begins
- Plan file at `/tmp/` is lost on machine restart; for long-running tasks use a project-relative
  path like `.ll-scratch/general-task-plan.md`
- Relies on Claude correctly maintaining the checklist — a shell validation step could be added
  after each execute if drift becomes a problem

## Labels

`enhancement`, `loops`, `general-task`, `handoff`, `batch-behavior`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-03-17
- **Status**: Completed

### Changes Made

- `.loops/general-task.yaml`: Added `plan` initial state; constrained `execute` and `continue_work`
  to one step per iteration via explicit plan-file instructions.

---

## Status

**Completed** | Created: 2026-03-17 | Completed: 2026-03-17 | Priority: P4
