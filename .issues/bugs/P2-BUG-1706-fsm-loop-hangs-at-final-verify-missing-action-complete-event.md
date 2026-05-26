---
id: BUG-1706
title: "FSM loop hangs at final_verify when action_complete event is never emitted"
type: BUG
status: open
priority: P2
captured_at: "2026-05-25T23:53:17Z"
discovered_date: "2026-05-25"
discovered_by: capture-issue
labels:
  - bug
  - ll-loop
  - fsm
  - captured
---

# BUG-1706: FSM loop hangs at final_verify when action_complete event is never emitted

## Summary

The `general-task` FSM loop enters `final_verify`, the LLM completes all work (36/36 DoD criteria verified, Final Verification section written), but never emits an `action_complete` event. The FSM stalls indefinitely — the 1800s LLM timeout expired 33+ minutes ago with no kill or retry triggered, leaving the process running but fully idle with completed work trapped inside.

## Current Behavior

1. Loop enters `final_verify` state (23:09:48 UTC)
2. LLM finishes all verification work by 23:13:54 UTC (all 36 DoD criteria re-verified, Final Verification section written to DoD file)
3. No `action_complete` event is emitted
4. FSM waits for `action_complete` → `count_final` transition that never fires
5. Process remains alive and idle 33+ minutes past the 1800s LLM timeout with no kill, retry, or alert

**Expected path:** `final_verify --next--> count_final --yes--> done` (terminal)

**Actual path:** `final_verify` → stalled forever

## Expected Behavior

When the LLM in `final_verify` finishes its task, it should emit `action_complete` so the FSM advances to `count_final` and then `done`. If that event is not emitted within the configured LLM timeout (1800s), the runner should either:
- Kill the idle process (and optionally emit a `timeout` event to trigger recovery), or
- Retry the state, or
- Alert the operator

## Motivation

Work is fully complete but the loop never reaches the terminal `done` state. The result: the operator must manually inspect and kill the process; log artifacts may remain unclosed; any downstream trigger on `done` (notifications, post-loop hooks) never fires. This is a silent failure — the loop appears alive until the operator notices it hasn't progressed.

## Steps to Reproduce

1. Run a `general-task` loop (or similar) with a `final_verify` state that uses `ll_structured` or similar LLM action
2. Have the LLM complete all verification work successfully
3. Observe that the LLM response does not include the `action_complete` event token/signal
4. Observe FSM stalls; wait for LLM timeout to expire; confirm process is not killed

## Root Cause

Two distinct gaps combine to produce this failure:

**Gap 1 — Missing `action_complete` emission (primary):**
- **File**: loop YAML / LLM prompt for `final_verify` state
- **Anchor**: `final_verify` state definition, LLM prompt text
- **Cause**: The LLM prompt for `final_verify` either does not instruct the model to emit `action_complete`, or the model fails to include it in its output. Without the signal, the FSM routing finds no matching event and idles.

**Gap 2 — No liveness enforcement after LLM timeout (secondary):**
- **File**: `scripts/little_loops/loop_runner.py` (or equivalent FSM executor)
- **Anchor**: LLM timeout handling / state execution loop
- **Cause**: The 1800s `llm_timeout` in loop config expired but the runner did not kill the process, retry the state, or fire a recovery transition. The timeout is tracked but not enforced with a kill/retry action.

## Proposed Solution

1. **Audit `final_verify` (and similar terminal-adjacent) state prompts** to ensure `action_complete` is explicitly required in the model's output format.
2. **Enforce LLM timeout kill/retry in the runner**: when a state's wall-clock time exceeds `llm_timeout`, the runner should kill the blocking subprocess and either retry the state (up to a configured max) or transition via a `timeout` event to a recovery/failure state.
3. **Add a liveness watchdog**: a lightweight background monitor that fires an alert or transition when a state has been idle longer than `llm_timeout * N`.

## Integration Map

### Files to Modify
- TBD — loop YAML for `general-task` (the `final_verify` state prompt)
- TBD — FSM runner / state executor (liveness/timeout enforcement)

### Dependent Files (Callers/Importers)
- TBD — use grep to find `llm_timeout` references in the runner

### Similar Patterns
- Other loops with terminal-adjacent states that rely on LLM-emitted completion signals
- `loops/general-task.yaml` (confirmed affected)

### Tests
- TBD — integration test simulating LLM that completes work but omits `action_complete`
- TBD — unit test for timeout-kill enforcement in the runner

### Documentation
- `docs/reference/API.md` — loop config `llm_timeout` semantics
- Loop authoring guide — note that terminal-adjacent states must explicitly prompt for `action_complete`

### Configuration
- Loop YAML: `llm_timeout` (1800s in the affected run)

## Implementation Steps

1. Reproduce: create a minimal loop with a `final_verify` state whose prompt omits `action_complete`; confirm hang
2. Fix the prompt: add explicit instruction to emit `action_complete` in `final_verify` (and audit peer states)
3. Fix the runner: enforce `llm_timeout` as a hard kill deadline with configurable retry or `timeout` transition
4. Add watchdog: background thread/process that pings idle states and fires `loop_timeout` event
5. Regression test both gaps

## Impact

- **Priority**: P2 — significant; work completes but the loop silently hangs; operator intervention required; downstream hooks never fire
- **Effort**: Medium — prompt fix is small; runner timeout enforcement is moderate; watchdog is optional follow-on
- **Risk**: Low/Medium — timeout enforcement changes runner behavior; needs care to not kill legitimately long-running states
- **Breaking Change**: No (fixing a hang is not a breaking change; timeout enforcement is additive behavior)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `ll-loop`, `fsm`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-05-25T23:53:17Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6beeb46c-ca56-4385-8e86-f1d1ac1a4edf.jsonl`

---

## Status

**Open** | Created: 2026-05-25 | Priority: P2
