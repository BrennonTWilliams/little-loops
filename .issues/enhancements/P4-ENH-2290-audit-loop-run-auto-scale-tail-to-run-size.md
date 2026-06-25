---
id: ENH-2290
title: audit-loop-run should auto-scale --tail to run size instead of defaulting to 200
priority: P4
type: ENH
status: open
captured_at: '2026-06-25T13:53:17Z'
discovered_date: '2026-06-25'
discovered_by: audit-loop-run
labels:
- audit-loop-run
- skills
- diagnostics
---

# ENH-2290: audit-loop-run should auto-scale --tail to run size instead of defaulting to 200

## Motivation

`/ll:audit-loop-run` loads the event history with a default `--tail 200`
(Step 2: `ll-loop history <loop> [<run>] --json --tail <tail_arg_or_200>`).
For long runs this silently truncates the event stream, so Phase 1 fault-signal
analysis and the Step 5.5 shallow-iteration `TOOL_CALL_COUNT` operate on a
partial window without flagging that they did.

Concrete example: auditing run `2026-06-25T065113-rn-implement` (89 iterations,
795 total events, 8 issues processed) with the default tail surfaced only the
last ~2 issues' events. The audit's own `action_complete` count (36) was a
subset of the full run, and fault-signal coverage was incomplete. A second pass
with `--tail 1000` was required to reach ground truth.

## Proposed Behavior

In Step 2, before loading history, query the run's total event/iteration count
and scale the tail accordingly rather than hard-defaulting to 200:

- Read the run's iteration/event total (e.g. from the `loop_complete` event's
  `iterations`, or `ll-loop status`/`history` metadata).
- If the user did not pass an explicit `--tail`, set the effective tail to
  cover the whole run (e.g. `max(200, total_events)` or an "all events"
  sentinel), capped at a sane ceiling.
- When truncation does occur (explicit small `--tail` on a larger run), emit a
  one-line notice in the audit output, e.g.
  `ℹ️ Loaded last N of M events — fault analysis covers a partial window.`
  so the verdict is not read as full coverage (consistent with the skill's
  existing "No silent caps" principle for loops).

## Acceptance Criteria

1. With no explicit `--tail`, auditing a run with more than 200 events loads
   the full event stream (or an explicitly-stated, sufficient window).
2. When the loaded window is smaller than the run's total event count, the
   audit output includes a one-line truncation notice with the loaded vs total
   counts.
3. An explicit user-supplied `--tail` still takes precedence over the
   auto-scaled default.

## Impact

- **Priority**: P4 — Diagnostic-quality improvement to the audit skill; the
  workaround (pass a larger `--tail`) is trivial once the user knows to.
- **Effort**: Small — change the default-tail derivation in the skill's Step 2
  and add a truncation-notice line.
- **Risk**: Low — skill-doc change; no code or loop changes.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-25 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-06-25T13:53:17Z - `fe374318-c8a2-454a-82dd-24bd83653458.jsonl`
