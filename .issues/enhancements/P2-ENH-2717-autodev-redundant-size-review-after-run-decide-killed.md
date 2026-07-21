---
id: ENH-2717
type: ENH
title: "autodev run_decide → run_size_review path wastes a full size-review call when decide-issue is killed mid-turn"
priority: P2
status: open
captured_at: '2026-07-21T05:07:30Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
labels:
- autodev
- fsm
- token-cost
relates_to:
- ENH-2712
- BUG-2718
---

# ENH-2717: autodev run_decide → run_size_review path wastes a full size-review call when decide-issue is killed mid-turn

## Summary

During `ll-loop run autodev ENH-2712`, `run_decide` invoked `/ll:decide-issue ENH-2712 --auto`. The subprocess was still mid-turn — waiting on two parallel evidence-gathering subagents scoring Option A vs Option B — when `subprocess_utils.py`'s post-stream-close watchdog force-killed it (SIGKILL, exit -9) before it could produce a score or clear `decision_needed`. `run_decide`'s `on_error` routed to `recheck_after_decide`, which (correctly) still failed readiness, and fell through to `snap_and_size_review` → `run_size_review` — a full second LLM call (`/ll:issue-size-review --auto`, ~1m8s) that independently re-discovered the exact same unresolved `decision_needed: true` blocker before finally deferring via `mark_gate_blocked`.

## Current Behavior

`run_decide` (`scripts/little_loops/loops/autodev.yaml`, ~line 300) has `on_error: recheck_after_decide`. When `/ll:decide-issue --auto` is killed before completing (subprocess watchdog, crash, or any other on_error path), the FSM cannot distinguish "decide genuinely failed/was interrupted" from "decide ran to completion but scores are still low for unrelated reasons." Both cases fall through the same `recheck_after_decide` → `snap_and_size_review` → `run_size_review` path, which reruns `/ll:issue-size-review --auto` — a costly LLM call — even when the blocking cause (`decision_needed: true`, unchanged) is already fully known from `run_decide`'s failure.

## Expected Behavior

When `run_decide` fails to clear `decision_needed` (whether via `on_error` or via `recheck_after_decide` finding the flag still `true` post-run), the loop should short-circuit directly to `record_decision_unresolved` / `mark_gate_blocked` instead of routing through `snap_and_size_review` → `run_size_review`. Size-review adds no new information when the known blocker is an incomplete/failed decision — it's the same `decision_needed` check re-run against a fact that hasn't changed.

## Root Cause

Observed in `.loops/runs/autodev-20260720T235236/` / `.loops/.running/autodev-20260720T235236.log`:

- `[8/500] run_decide`: `/ll:decide-issue ENH-2712 --auto` started scoring Option A vs Option B via two parallel evidence-gathering subagents. Before it finished, the log shows: `Process 48056 did not exit within 30s after streams closed, killing` (`scripts/little_loops/subprocess_utils.py:511-518`), then `exit: -9`, then `-> recheck_after_decide` (the `on_error` route).
- `decision_needed` remained `true` on ENH-2712's frontmatter (decide never wrote a score).
- `recheck_after_decide` re-ran the readiness check (still failing) → `snap_and_size_review` → `[11/500] run_size_review`: `/ll:issue-size-review --auto` ran a full analysis and independently concluded: *"There's also an unresolved blocker: `decision_needed: true` ... hasn't been formally closed via `/ll:decide-issue`"* — the identical fact already known 3 states earlier — before the loop finally deferred ENH-2712 with `deferred_reason: low_readiness`.

**This issue is a mitigation, not the root-cause fix.** The actual reason `run_decide` failed to clear `decision_needed` is [[BUG-2718]]: `subprocess_utils.py`'s fixed 30s post-stream-close kill watchdog force-killed the `/ll:decide-issue --auto` process while it still had legitimate parallel subagent work in flight. This ENH stops the FSM from compounding that loss with a redundant `run_size_review` call regardless of *why* `run_decide` fails — but BUG-2718 is what should stop the kill (and the lost work) from happening in the first place. Implement both; this one is defense-in-depth for any `run_decide` failure mode, not a substitute for fixing the kill.

## Proposed Solution

In `autodev.yaml`, have `run_decide`'s `on_error` route to a state that checks whether `decision_needed` is still `true` and, if so, goes straight to `record_decision_unresolved` (bypassing `snap_and_size_review`/`run_size_review` entirely). If `decision_needed` was somehow cleared despite the error (unlikely but possible), fall back to the existing `recheck_after_decide` path so readiness is still re-evaluated normally.

## Implementation Steps

1. Add a `check_decision_after_decide_error` (or similar) state between `run_decide`'s `on_error` and `recheck_after_decide`, mirroring the existing `check-flag decision_needed` pattern used elsewhere in the file (`check_decision_at_dequeue`, `check_decision_after_refine`, `assert_decision_cleared`).
2. `on_yes` (decision_needed still true) → `record_decision_unresolved` directly.
3. `on_no`/`on_error` → fall through to existing `recheck_after_decide`.
4. Verify with a single-iteration run against an issue whose `decide-issue --auto` is forced to fail (or via `ll-loop simulate`/routing dry-run) that the redundant `run_size_review` state is skipped.

## Impact

- **Priority**: P2 — low risk, saves a full LLM call (~1m8s+ tokens) on every autodev run where `run_decide` fails without clearing `decision_needed`.
- **Effort**: Small — one new routing state plus a re-point of `run_decide`'s `on_error`.
- **Risk**: Low — read-only routing change to an already-defensive gate chain (`assert_decision_cleared`/`record_decision_unresolved` already exist for the analogous post-`recheck_after_decide` case).

## Session Log
- `/ll:capture-issue` - 2026-07-21T05:07:30Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/255186e7-f4f9-45b7-b959-38186bd122ed.jsonl`

---

## Status

**Open** | Created: 2026-07-21 | Priority: P2
