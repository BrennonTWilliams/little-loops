---
id: BUG-3567
type: BUG
title: Autodev rate-limit exits bypass finalize_done and summary.json
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:12Z'
parent: EPIC-3565
completed_at: '2026-09-24T19:41:21Z'
---

# BUG-3567: Autodev rate-limit exits bypass finalize_done and summary.json

## Summary

Twelve autodev skill states declared `on_rate_limit_exhausted` targeting the bare `done`
terminal, and `check_decide_rate_limited.on_yes` did the same. The `done` terminal has no
action. `finalize_done` is the state that writes `summary.json`, promotes staged → passed,
and detects abandoned in-flight work. A 429-exhausted run therefore ended "successfully" with
no summary, no closure accounting, and the unprocessed queue silently dropped. The `done`
state's own comment still claimed it emitted the summary.

## Current Behavior

Before the fix, rate-limit exhaustion ended at `done` with no `summary.json`. Staged issues
were never checked for closure, and the remaining queue was unreported.

## Expected Behavior

Every exit goes through `finalize_done`. A rate-limit stop is reported as an interrupted run,
with its stop reason and pending queue.

## Steps to Reproduce

1. Run autodev on a multi-issue queue until a skill state exhausts its 429 retry budget (pre-fix, commit `958bf1f90`)
2. Observe the run end at `done` with no `summary.json` in the run dir, and the remaining `autodev-queue.txt` entries unreported

## Motivation

Rate-limit exhaustion is a common way for long autodev runs to end. Those runs left no summary and no record of unprocessed work.

## Proposed Solution

Route every rate-limit exit through a stop-reason stamp into `finalize_done`. Implemented; see Resolution.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `finalize_rate_limited`, `finalize_done`, `init`, `done`

### Dependent Files (Callers/Importers)
- N/A — loop-internal routing

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop`
- `scripts/tests/test_autodev_decision_gate.py`
- `scripts/tests/test_fsm_topology.py` — autodev state count (87)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `finalize_rate_limited` → `finalize_done`
2. Retarget all `on_rate_limit_exhausted` sites and `check_decide_rate_limited.on_yes`
3. Add `stop_reason`/`pending` to `summary.json`, plus the `rate_limited` verdict
4. Tests: no edge to `done` except `finalize_done`; finalize output under a rate-limit stop

## Impact

- **Priority**: P2 — interrupted runs were indistinguishable from clean ones
- **Effort**: Small
- **Risk**: Low. Verdict consumers (`ll-loop audit`, evidence archiving) copy `summary.json`
  and do not enumerate verdict values.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: the `on_rate_limit_exhausted` edges, `check_decide_rate_limited`, and the `done` terminal
- **Cause**: rate-limit exits treated "stop gracefully" as "reach the terminal", bypassing finalization

## Resolution

- New state `finalize_rate_limited` stamps `autodev-stop-reason` (`rate_limit`) and routes
  to `finalize_done`. All 12 `on_rate_limit_exhausted` sites and
  `check_decide_rate_limited.on_yes` now target it.
- `finalize_done` reads the stop reason and counts `autodev-queue.txt` as pending. On a stop
  it prints a `Stopped early` line with the pending IDs. `summary.json` gains `stop_reason`
  and `pending`, and a rate-limit stop reports `verdict: rate_limited` (exit 0 → `done`, not
  `phantom` → `failed`). An in-flight issue is still counted as abandoned.
- `init` clears `autodev-stop-reason`. The stale comment on `done` was corrected.
- Tests: `test_rate_limit_exits_route_through_finalize` (only `finalize_done` may reach
  `done`) and `test_finalize_done_reports_rate_limited_stop_with_pending` in
  `test_builtin_loops.py`, plus retargeted route assertions there and in
  `test_autodev_decision_gate.py`.
- The YAML landed in commit `9a5d0f523`. The retargeted `test_builtin_loops.py` assertions
  were uncommitted in the working tree at capture time. `test_fsm_topology.py`'s autodev state
  count must be 87 (it was reverted on disk to 84 by a concurrent session).

## Acceptance Criteria

- [x] No autodev state routes to `done` except `finalize_done`
- [x] Rate-limit stop writes `summary.json` with `verdict: rate_limited`, `stop_reason`, `pending`
- [ ] `test_fsm_topology.py::TestAutodevSmoke::test_autodev_topology` expects 87 states (committed)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-24T19:42:30 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
