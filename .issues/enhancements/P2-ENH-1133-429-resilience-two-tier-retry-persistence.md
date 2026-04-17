---
id: ENH-1133
type: ENH
priority: P2
status: open
discovered_date: 2026-04-16
parent: ENH-1131
related: [ENH-1131, ENH-1132, ENH-1134, ENH-1135, BUG-1107, BUG-1108, BUG-1109]
---

# ENH-1133: 429 Resilience — Two-Tier Retry Logic & Persistence

## Summary

Refactor the FSM executor's rate-limit detection block to implement two-tier retry (short burst → long-wait ladder → exhaustion route), upgrade `LoopState` persistence to store dict-of-record retry state and storm counter, and add a migration path for legacy state files. Depends on ENH-1132 (schema/config foundation).

## Parent Issue

Decomposed from ENH-1131: Multi-Hour 429 Resilience with Shared Circuit Breaker and Wall-Clock Budget

## Motivation

Current handling (3 retries, ~3.5min total) fails on real outages. The fix adds a long-wait tier that sleeps 5min → 15min → 30min → 1h in a budget-bounded loop before giving up. Persistence must be upgraded so the two-tier state and storm counter survive process restarts (today, storm count silently resets to 0 on resume).

## Current Behavior

- `executor.py:481-541`: 3 in-place retries, exponential backoff (30s base), jittered
- On exhaustion: routes to `on_rate_limit_exhausted` or `on_error`
- `_consecutive_rate_limit_exhaustions` (`executor.py:172-173`): in-memory only, lost on resume
- `rate_limit_retries` (`persistence.py:104`): `dict[str, int]` — per-state attempt count only

## Expected Behavior

### 1. Two-tier retry logic (`executor.py:481-541`)

Refactor to track a per-state record:
```python
{
    "short_retries": int,       # attempts in burst tier
    "long_retries": int,        # attempts in long-wait tier
    "total_wait_seconds": float,
    "first_seen_at": float      # epoch timestamp
}
```

On short-tier exhaustion (after `max_rate_limit_retries` attempts), instead of routing to `on_rate_limit_exhausted`, enter **long-wait tier**:
- Use `rate_limit_long_wait_ladder` from `StateConfig` (falls back to global `commands.rate_limits.long_wait_ladder`)
- Advance ladder index on each long-wait exhaustion, capping at the last value
- Only route to `on_rate_limit_exhausted` once `total_wait_seconds >= rate_limit_max_wait_seconds`

The existing `rate_limit_exhausted` event payload should be extended with `short_retries`, `long_retries`, `total_wait_seconds` fields so observers can distinguish tiers.

Post-exhaustion routing still returns `state.on_rate_limit_exhausted or state.on_error` directly (preserving current bypass-of-`_route()` behavior).

### 2. Sleep-loop replacement

During long-wait sleeps, replace direct `time.sleep` calls at `executor.py:527-534` with the same interruptible pattern (100ms tick, check `_shutdown_requested`). The heartbeat emit wrapping will be added in ENH-1135; this issue just ensures the interruptible loop is in place with a `total_wait_seconds` accumulator.

### 3. Persistence: dict-of-record (`persistence.py:104`)

Upgrade `rate_limit_retries` from `dict[str, int]` to `dict[str, dict]`. Update:
- `LoopState` dataclass field type (line 104)
- `to_dict` serialization (line 128)
- `from_dict` deserialization (line 156) — **include migration**: detect `int` values and coerce to `{"short_retries": int, "long_retries": 0, "total_wait_seconds": 0, "first_seen_at": None}`
- `save` path (line 433)
- `restore` path (line 501)

### 4. Persistence: storm counter (`persistence.py`)

Add `consecutive_rate_limit_exhaustions: int = 0` to `LoopState`. Update `to_dict`, `from_dict`, `save`, and `restore` so storm state survives resume.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py` — lines 481-541: two-tier state machine; lines 527-534: interruptible long-wait loop with accumulator; event payload extension near lines 506-513
- `scripts/little_loops/fsm/persistence.py` — lines 104, 128, 156, 433, 501: dict-of-record + storm counter
- `scripts/little_loops/cli/loop/lifecycle.py` — resume path via `PersistentExecutor.resume()` must restore new dict-of-record and storm counter

### Depends On

- ENH-1132 — `StateConfig` new fields must exist before executor can read them

### Tests

- `scripts/tests/test_fsm_executor.py:4303+` — extend `TestRateLimitRetries` / `TestRateLimitStorm`:
  - Use `patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0)` to skip sleeps
  - Two-tier ladder transitions: verify long-tier entered after short-tier exhausted
  - Budget enforcement: `total_wait_seconds >= max_wait_seconds` triggers exhaust route
  - Short-circuit on `_shutdown_requested` during long-wait sleep
- `scripts/tests/test_fsm_persistence.py:1737,1787,1815` — update `TestRateLimitRetriesPersistence` (3 tests assert `rate_limit_retries == {"execute": 2}`) to new dict-of-record shape
- `scripts/tests/test_fsm_persistence.py` — add migration test: load hand-crafted legacy `dict[str, int]` state file, assert successful coercion to record shape
- `scripts/tests/test_fsm_persistence.py` — add `consecutive_rate_limit_exhaustions` serialization round-trip test

### Similar Patterns to Model After

- `executor.py:324-329,527-534` — existing interruptible sleep idiom
- `executor.py:49-58` — existing default constants (follow pattern for new defaults)
- `persistence.py:200-207` — atomic JSON write with `mkstemp + os.replace`

## Acceptance Criteria

- Short-tier exhaustion enters long-wait tier (does not immediately route to `on_rate_limit_exhausted`)
- Long-wait tier uses `rate_limit_long_wait_ladder`; advances index, caps at last value
- Wall-clock budget (`rate_limit_max_wait_seconds`) enforced; per-state override respected
- `_shutdown_requested` exits long-wait sleep promptly
- `rate_limit_exhausted` payload includes `short_retries`, `long_retries`, `total_wait_seconds`
- `LoopState` persists dict-of-record retry state and storm counter; restored correctly on resume
- Legacy `dict[str, int]` state files migrate cleanly
- Existing `TestRateLimitRetriesPersistence` tests updated and passing; new migration test passes

## Session Log
- `/ll:issue-size-review` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86c5c7e4-236c-46a0-acd9-2124269e76f0.jsonl`

---

## Status
- [ ] Open
