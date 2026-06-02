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

## Steps to Reproduce

1. Configure and start an `autodev` loop run with multiple issues in `autodev-queue.txt`
2. Allow `implement_current` to begin processing an issue and reach a context limit mid-implementation
3. Observe: FSM emits `handoff_detected` → `handoff_spawned`; `ll-loop resume autodev` is spawned as a subprocess
4. Observe: `autodev-inflight` still contains the interrupted issue
5. Observe: The continuation run resumes at `dequeue_next` and reads the next item from `autodev-queue.txt` — the inflight issue is never re-queued and is silently skipped

## Current Behavior

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

## Motivation

Context-handoff is the primary mechanism for surviving long autodev runs that exceed a single context window. When it silently drops inflight issues:
- Partially-implemented issues accumulate: code changes are written but commits, docs, and `status=done` are never set
- The failure is invisible: no error, no log entry, no retry — discoverable only by manual diff of `autodev-inflight` vs `autodev-queue.txt`
- Compounds across runs: each handoff event in a multi-session sprint silently drops one more issue

## Proposed Solution

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

## Integration Map

### Files to Modify
- `loops/autodev.yaml` — add `on_resume` hook or `init` state guard with inflight-reconciliation logic

### Dependent Files (Callers/Importers)
- TBD — `grep -r "autodev-inflight" loops/` to find all states that read/write the inflight file

### Similar Patterns
- BUG-1226 (done): autodev in-flight state loss pattern — see its fix for consistency
- BUG-1759 (done): handoff forwarding — the fix is the layer this builds on

### Tests
- TBD — manual validation by running autodev with a forced context-limit trigger

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Locate the `on_resume` hook or `init` state entry point in `loops/autodev.yaml`
2. Add the inflight-reconciliation script: read `autodev-inflight`, check issue status via `ll-issues show`, prepend back to `autodev-queue.txt` if status is not `done`/`cancelled`
3. Validate: run autodev with a forced mid-implementation interrupt and confirm the inflight issue appears at the head of the queue in the continuation
4. Confirm no duplicate-processing regression: if the issue reaches `done` before handoff, reconciliation must be a no-op

## Impact

Low frequency (only triggered when `implement_current` is interrupted mid-run), but when it occurs the inflight issue is silently left in a partially-implemented state with no follow-up. Discoverable only by manual inspection of `autodev-inflight` vs `autodev-queue.txt` after a run.

- **Priority**: P3 — Low-frequency but silent data loss; no mechanism to detect or recover automatically
- **Effort**: Small — localized change to a single FSM hook or state guard
- **Risk**: Low — reconciliation is additive; if inflight is already `done`, it's a no-op
- **Breaking Change**: No

## Related

- BUG-1759 (done): ll-auto handoff forwarding to outer FSM — the fix made handoff detection work; this bug is the next layer (re-queue on resume)
- BUG-1226 (done): autodev drops breakdown result on timeout between `refine_current` and `copy_broke_down` — similar in-flight state loss pattern

---

**Open** | Created: 2026-06-02 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-02T13:18:33 - `1a1ea335-7acb-47eb-a0a7-9d25c099f34d.jsonl`
