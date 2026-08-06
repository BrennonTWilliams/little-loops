---
id: BUG-3085
type: BUG
title: Learning gate's 900s subprocess timeout preempts the configured 86400s queue-wait
  budget
priority: P3
status: open
captured_at: '2026-08-06T16:17:02Z'
discovered_date: 2026-08-06
discovered_by: capture-issue
labels:
- learning-gate
- fsm-concurrency
- config
relates_to:
- BUG-3083
- ENH-3073
---

# BUG-3085: Learning gate's 900s subprocess timeout preempts the configured 86400s queue-wait budget

## Summary

The in-progress ENH-3073 follow-up in `learning_tests/gate.py` (currently
uncommitted in the working tree) adds `--queue` to the
`ll-loop run ready-to-implement-gate` invocation, plus
`_QUEUE_WAIT_TIMEOUT_SECONDS = 900` as a `subprocess.run(timeout=...)` bound.

The child's own queue-wait budget is `loops.queue_wait_timeout_seconds`, which
defaults to **86400** (`config-schema.json:969-973`) and is read at
`cli/loop/run.py:401`. The outer 900s bound therefore always wins by nearly two
orders of magnitude: the configured value can never take effect, and the child
is SIGKILLed mid-queue rather than timing out cleanly on its own terms.

Because this repo is `local-editable` for every little-loops project on this
machine, the uncommitted change is already live everywhere.

## Steps to Reproduce

1. Hold a repo-root scope lock for >15 minutes (e.g. a long
   `refine-to-ready-issue` run — see BUG-3083).
2. Run `ll-auto --only <ID>` on an issue with `learning_tests_required`.
3. The gate subprocess queues, waits 900s, and is killed by
   `subprocess.run`'s timeout — never reaching its own 86400s budget.
   `ll-auto` reports `impl_failed`.

## Root Cause

Two independent timeout budgets govern the same wait, and the caller's is
unconditionally the smaller:

- `scripts/little_loops/learning_tests/gate.py` — `_QUEUE_WAIT_TIMEOUT_SECONDS = 900`,
  passed as `subprocess.run(..., timeout=...)`.
- `scripts/little_loops/cli/loop/run.py:401` — `_budget = _config.loops.queue_wait_timeout_seconds`,
  default 86400.

`subprocess.run`'s timeout path calls `Popen.kill()` (SIGKILL on POSIX), so the
child's `atexit` cleanup for its `.queue` entry and `.pid` file does not run.

## Current Behavior

- `loops.queue_wait_timeout_seconds` is dead config for this call path.
- The queued child dies by SIGKILL, orphaning its `.loops/.queue/<uuid>.json`
  entry and `.loops/.running/<instance>.pid`.

## Expected Behavior

One authoritative budget for the queue wait. The caller either adopts the
configured value or explicitly passes its own bound down to the child so both
layers agree, and the child exits its wait gracefully.

## Proposed Solution

Preferred: pass the intent down rather than racing it from outside.

1. If `ll-loop run` accepts a queue-timeout flag, pass it explicitly so the
   child's budget *is* the caller's budget. Grep the current `ll-loop run`
   argument surface before adding one — the flag may already exist.
2. If it does not, add `--queue-timeout SECONDS` to `ll-loop run` overriding
   `_budget` at run.py:401.
3. Keep an outer `subprocess.run(timeout=...)` only as a backstop, set
   comfortably *above* the child's budget (e.g. child budget + slack), so it
   fires only when the child is genuinely wedged — not as the normal exit path.
4. Decide the right default wait for the ll-auto call path deliberately. 900s is
   defensible for a foreground `ll-auto`; 86400s clearly is not. If 900s is the
   intended policy, set it as the child's budget rather than as an external kill.

Note: the orphaned `.queue` entry is self-healing — `read_queue_entries()`
prunes dead-PID entries (`cli/loop/_helpers.py:206-217`, BUG-1360) — so orphan
starvation is not a live risk. Do not over-engineer that part.

## Impact

Low severity but it makes a documented config knob inert and hides the real
tuning surface. Worth fixing before the ENH-3073 work is committed, since the
current shape bakes in a hardcoded constant that silently overrides user config.

## Integration Map

| File | Anchor | Change |
|------|--------|--------|
| `scripts/little_loops/learning_tests/gate.py` | `run_learning_gate_for_issue`, targets branch | Reconcile the two budgets |
| `scripts/little_loops/cli/loop/run.py` | `cmd_run`, ~line 401 | Optional `--queue-timeout` |
| `scripts/little_loops/config-schema.json` | `loops.queue_wait_timeout_seconds` | Reconsider the 86400 default |
| `scripts/tests/test_learning_tests_gate.py` | — | Assert the effective budget |

## Implementation Steps

1. Grep the `ll-loop run` arg surface for an existing queue-timeout flag.
2. Wire the caller's intended budget into the child.
3. Reduce the outer `subprocess.run` timeout to a backstop above that budget.
4. Test that the configured value is what actually governs the wait.

## Status

open


## Session Log
- `/ll:capture-issue` - 2026-08-06T16:20:22 - `ee676905-966c-42aa-ac9d-d7d4aaeea91d.jsonl`
