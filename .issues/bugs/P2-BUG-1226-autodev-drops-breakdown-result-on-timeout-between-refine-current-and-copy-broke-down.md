---
discovered_date: 2026-04-21
discovered_by: analyze-loop
source_loop: autodev
source_state: copy_broke_down
---

# BUG-1226: autodev drops breakdown result on timeout between refine_current and copy_broke_down

## Summary

When the `autodev` loop's 8-hour wall-clock timeout fires in the narrow window between a
`refine_current` sub-loop completing and the `copy_broke_down` state starting, the breakdown
result is silently discarded. The sub-loop correctly wrote `1` to
`.loops/tmp/recursive-refine-broke-down`, but the parent loop timed out before
`copy_broke_down` could copy that flag into `.loops/tmp/autodev-broke-down`. As a result,
`check_broke_down` never ran, child detection never ran, and the issue (`FEAT-1201`) was
left off both the passed and skipped lists — effectively lost from the session.

## Loop Context

- **Loop**: `autodev`
- **State**: `copy_broke_down` (never executed)
- **Signal type**: timeout before routing completes
- **Occurrences**: 1 (observed 2026-04-21 session)
- **Last observed**: `2026-04-21T09:10:36+00:00`

## Root Cause

The sub-loop (`refine-to-ready-issue`) for `FEAT-1201` exhausted its two refine attempts
without passing `check_readiness`, hit the `check_refine_limit` → `breakdown_issue` path,
ran `/ll:issue-size-review FEAT-1201 --auto` (117s), and wrote the `recursive-refine-broke-down`
flag. The sub-loop then completed normally (`terminated_by: terminal`). The parent `autodev`
loop issued a `route from=refine_current to=copy_broke_down` at 09:10:36.552491 — but the
8-hour timeout fired at 09:10:36.552553, 62 µs later, before the state could enter.

## History Excerpt

Events leading to this signal:

```json
[
  {"event": "state_enter",    "ts": "2026-04-21T09:08:39.526042+00:00", "state": "breakdown_issue", "iteration": 15},
  {"event": "action_complete","ts": "2026-04-21T09:10:36.547092+00:00", "exit_code": 0, "duration_ms": 117005, "is_prompt": true},
  {"event": "route",          "ts": "2026-04-21T09:10:36.547319+00:00", "from": "breakdown_issue", "to": "write_broke_down"},
  {"event": "state_enter",    "ts": "2026-04-21T09:10:36.547572+00:00", "state": "write_broke_down", "iteration": 16},
  {"event": "action_complete","ts": "2026-04-21T09:10:36.551770+00:00", "exit_code": 0, "duration_ms": 3, "is_prompt": false},
  {"event": "route",          "ts": "2026-04-21T09:10:36.551959+00:00", "from": "write_broke_down", "to": "done"},
  {"event": "loop_complete",  "ts": "2026-04-21T09:10:36.552034+00:00", "final_state": "done", "iterations": 16, "terminated_by": "terminal", "depth": 1},
  {"event": "route",          "ts": "2026-04-21T09:10:36.552491+00:00", "from": "refine_current", "to": "copy_broke_down"},
  {"event": "loop_complete",  "ts": "2026-04-21T09:10:36.552553+00:00", "final_state": "copy_broke_down", "iterations": 236, "terminated_by": "timeout"}
]
```

## Expected Behavior

When the loop times out while `final_state` is `copy_broke_down` (i.e. the state was
targeted but never executed), the executor should either:

1. **Execute the pending state before honoring the timeout** when the timeout fires
   between a sub-loop return and the next shell action (a safe, fast-path guarantee
   for non-prompt states like `copy_broke_down`).
2. **Or emit a resume hint** in `loop_complete` that names the interrupted issue ID so
   a subsequent `ll-loop run autodev` with the same input can skip already-processed
   issues and retry the one that was mid-flight.

At minimum, the `done` state's summary should flag that `FEAT-1201` was neither passed
nor skipped, so the user knows to re-queue it.

## Proposed Fix

Two-part fix: a scoped executor change (closes the race) plus a lightweight
autodev-local signal (covers timeouts outside the race window). Full resume
support was considered and rejected as premature — the autodev queue state
(baseline IDs, broke-down flag, pre-ids) is not yet designed for durability.

### Part 1 — Flush one pending non-prompt state on timeout (executor)

In `scripts/little_loops/fsm/executor.py` around the timeout check at the top
of the run loop (`executor.py:237-240`), when the timeout fires *and* a `route`
event was just emitted to a non-terminal state whose action is `shell` (not
`slash_command`, not a sub-loop), execute that one state before finishing with
`terminated_by: "timeout"`. Single-step only — no cascade; if the flushed
state routes to another non-prompt state, honor the timeout there.

Why bounded to shell actions: `copy_broke_down` and similar handshake states
run in ~5 ms, so running one after timeout detection is safe. Slash commands
and sub-loops can take minutes and would violate the timeout budget.

### Part 2 — Record mid-flight issue for the done summary (autodev.yaml)

- `dequeue_next` writes the popped issue ID to `.loops/tmp/autodev-inflight`.
- `enqueue_or_skip` and `enqueue_children` clear that file when the issue is
  resolved or decomposed.
- `done` checks `autodev-inflight`; if non-empty it prints a warning alongside
  the passed/skipped lists naming the interrupted issue.

This catches timeouts Part 1 cannot — e.g. timeout fires while a sub-loop's
slash command is running — so the user always knows which issue to re-queue.

### Rejected — persistent resume

Storing dequeued-but-not-finished state so `ll-loop run autodev` can prepend
it automatically would require snapshotting queue state, baseline IDs, and
handshake flags, plus defining stale-resume semantics. Not justified for a
race that's been observed once; revisit if timeouts become common.

## Acceptance Criteria

- [ ] Executor flushes a single pending shell-action state when a timeout fires between `route` and `state_enter`; repro test covers the `refine_current → copy_broke_down` case
- [ ] Flush is bounded: only one state, only `shell` action_type, no cascade into further non-prompt states
- [ ] `dequeue_next` writes `.loops/tmp/autodev-inflight`; `enqueue_or_skip` and `enqueue_children` clear it
- [ ] `done` state emits a warning listing the mid-flight issue ID when `autodev-inflight` is non-empty
- [ ] Running `autodev` against an issue that hits the timeout mid-`refine_current` no longer silently drops the breakdown result — either the flag is flushed (Part 1) or the summary names the issue (Part 2)

## Labels

`bug`, `loops`, `autodev`, `captured`

## Status

**Open** | Created: 2026-04-21 | Priority: P2
