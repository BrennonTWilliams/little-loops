---
id: BUG-1870
title: autodev inflight issue not re-queued after context handoff spawns continuation
type: BUG
status: open
priority: P3
captured_at: '2026-06-02T04:00:00Z'
discovered_date: '2026-06-02'
discovered_by: audit-loop-run
source_loop: autodev
source_state: implement_current
labels:
- bug
- autodev
- handoff
- fsm
---

# BUG-1870: autodev inflight issue not re-queued after context handoff spawns continuation

## Summary

When `implement_current` hits a context limit mid-implementation and the FSM emits `handoff_detected` + `handoff_spawned`, the in-flight issue recorded in `autodev-inflight` is **not re-queued** in `autodev-queue.txt`. The spawned continuation (`ll-loop resume autodev`) resumes from `dequeue_next`, which reads only from `autodev-queue.txt` — so the inflight issue is silently skipped for the rest of the run.

## Observed Behavior

In run `2026-06-02T022609`:
- `implement_current` for ENH-1868 hit a context limit at iter 16 (03:48 UTC)
- `handoff_spawned` fired with PID 162 (`ll-loop resume autodev`)
- `autodev-inflight` = `ENH-1869`; `autodev-queue.txt` = `ENH-1776\nENH-1777`
- Continuation resumed at `refine_current iter=19`, processing ENH-1776 next
- ENH-1869 has partial implementation (code changes made in ENH-1868's session) but docs, commit, and `status=done` are pending — and no further processing will occur

## Root Cause

`implement_current` writes the inflight issue to `autodev-inflight` (set earlier by `dequeue_next`). The handoff mechanism correctly spawns the continuation, but neither the FSM definition nor the resume logic checks `autodev-inflight` to see whether the last processed issue reached a clean terminal state.

## Expected Behavior

On `handoff_spawned`, if `autodev-inflight` contains an issue whose `status` is not `done`/`cancelled`, that issue should be prepended back to `autodev-queue.txt` so the continuation can process it.

## Proposed Fix

Add a pre-resume step (either in the FSM's `on_resume` hook or in the `init` state guard on resume) that reconciles `autodev-inflight`:

```bash
INFLIGHT=$(cat "${context.run_dir}/autodev-inflight" 2>/dev/null | tr -d '[:space:]')
if [ -n "$INFLIGHT" ]; then
  STATUS=$(ll-issues show "$INFLIGHT" --json \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','open'))" 2>/dev/null || echo "open")
  if [ "$STATUS" != "done" ] && [ "$STATUS" != "cancelled" ]; then
    # Re-queue at the head so it's processed before any remaining queue items
    echo "$INFLIGHT" | cat - "${context.run_dir}/autodev-queue.txt" \
      > "${context.run_dir}/autodev-queue.tmp" \
      && mv "${context.run_dir}/autodev-queue.tmp" "${context.run_dir}/autodev-queue.txt"
  fi
fi
```

## Impact

Low frequency (only triggered when `implement_current` is interrupted mid-run), but when it occurs the inflight issue is silently left in a partially-implemented state with no follow-up. Discoverable only by manual inspection of `autodev-inflight` vs `autodev-queue.txt` after a run.

## Related

- BUG-1759 (done): ll-auto handoff forwarding to outer FSM — the fix made handoff detection work; this bug is the next layer (re-queue on resume)
- BUG-1226 (done): autodev drops breakdown result on timeout between `refine_current` and `copy_broke_down` — similar in-flight state loss pattern
