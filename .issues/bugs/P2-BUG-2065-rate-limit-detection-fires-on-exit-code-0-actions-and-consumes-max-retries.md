---
id: BUG-2065
type: bug
priority: P2
status: done
title: Rate-limit detection fires on exit_code=0 actions and consumes max_retries
  budget
discovered_date: 2026-06-10
discovered_by: capture-issue
captured_at: '2026-06-10T00:39:57Z'
completed_at: '2026-06-10T01:26:09Z'
affects:
- scripts/little_loops/fsm/executor.py
- scripts/little_loops/issue_lifecycle.py
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-2065: Rate-limit detection fires on exit_code=0 actions and consumes max_retries budget

## Summary

Two related defects in the FSM executor's rate-limit/retry interaction cause successful action results to be discarded and the `max_retries` budget to be consumed by infrastructure pauses rather than real action failures.

Observed in the `rlhf-animated-svg` audit (run `2026-06-09T220055`): `review_critique` reached `retry_exhausted → failed` despite the action completing with exit_code=0 and `REPLAN_NEEDED` correctly present in the output. 29.5 minutes of accumulated runtime, 2 scoring cycles, the best artifact, and an optimization summary were all discarded.

## Steps to Reproduce

1. Define a loop state with `max_retries: 3` and `on_error: self` (or a `route:` table that maps `error` back to itself).
2. Run the loop via `ll-loop run <loop-name>` where the action exits 0 but its stdout/stderr contains the substring `"rate limit"` (e.g., the Claude CLI prints a rate-limit recovery message during a successful run).
3. Observe: `executor.py` intercepts the successful result and routes back to the same state rather than proceeding normally; the valid action output is discarded.
4. Repeat until `max_retries` is exhausted — the state transitions to `retry_exhausted → failed` despite every action having succeeded (exit_code=0).

**Concrete reproducer (Bug 2):** Run a state where `_handle_rate_limit` returns an in-place target. Check `_retry_counts` after N rate-limit pauses — the count equals N, consuming the `max_retries` budget before any true action failure occurs.

## Root Cause

### Bug 1: Rate-limit detection ignores exit_code (primary)

`executor.py` ~line 977 passes the combined action output through `classify_failure` with no exit-code guard:

```python
if action_result is not None:
    _combined = (action_result.output or "") + "\n" + (action_result.stderr or "")
    _failure_type, _reason = classify_failure(_combined, action_result.exit_code)
    if _failure_type == FailureType.TRANSIENT and (
        "rate limit" in _reason.lower() or "quota" in _reason.lower()
    ):
        _handled, _target = self._handle_rate_limit(state, route_ctx.state_name)
        if _handled:
            return _target   # discards successful result, retries in-place
```

`classify_failure` in `issue_lifecycle.py:54` accepts `returncode` but the docstring notes it is "available for future use" — no exit-code check is performed. If the claude CLI prints its own rate-limit recovery messages during a successful run (exit_code=0, success marker in output), the executor classifies the output as TRANSIENT/rate-limit, discards the good result, and retries in-place.

### Bug 2: Rate-limit in-place retries count against max_retries (secondary)

`_handle_rate_limit()` returns `state_name` for in-place retries. The main loop's retry-counting block (`executor.py` ~line 342) increments `_retry_counts` for ANY consecutive same-state re-entry regardless of cause:

```python
if self.current_state == self._prev_state:
    self._retry_counts[self.current_state] = (
        self._retry_counts.get(self.current_state, 0) + 1
    )
```

Rate-limit pauses are infrastructure delays, not action failures, but they burn the `max_retries` budget identically to real errors.

## Current Behavior

- A state with `max_retries: 3` and `on_error: self` reaches `retry_exhausted` after 4 rate-limit-triggered same-state re-entries, even if every action succeeded.
- Any action whose output contains "rate limit" text (e.g., a claude CLI progress message) is retried regardless of exit code, discarding a valid result.

## Expected Behavior

- Actions that exit with code 0 are never intercepted by the rate-limit handler, regardless of output content.
- Rate-limit-driven in-place retries do not consume `max_retries` budget; only true action failures (non-zero exit codes) count.

## Proposed Solution

**Fix 1** — guard the transient interceptor on exit code (`executor.py` ~line 977):

```python
if action_result is not None:
    _combined = (action_result.output or "") + "\n" + (action_result.stderr or "")
    _failure_type, _reason = classify_failure(_combined, action_result.exit_code)
    if action_result.exit_code != 0 and _failure_type == FailureType.TRANSIENT and (
        "rate limit" in _reason.lower() or "quota" in _reason.lower()
    ):
        ...
    elif action_result.exit_code != 0 and _failure_type == FailureType.TRANSIENT and "api server error" in _reason.lower():
        ...
    else:
        # reset counters (covers exit_code=0 path, cleaning up stale state)
        ...
```

**Fix 2** — track rate-limit in-flight transitions to exempt them from `_retry_counts`:

```python
# __init__: self._rate_limit_in_flight: set[str] = set()
# After _handle_rate_limit returns in-place target:
#   self._rate_limit_in_flight.add(state_name)
# In retry-counting block:
if self.current_state == self._prev_state:
    if self.current_state not in self._rate_limit_in_flight:
        self._retry_counts[self.current_state] = (
            self._retry_counts.get(self.current_state, 0) + 1
        )
    self._rate_limit_in_flight.discard(self.current_state)
```

## Implementation Steps

1. Add `exit_code != 0` guard to the rate-limit and api-server-error interceptor branches in `_route_next_state` (`executor.py`).
2. Add `self._rate_limit_in_flight: set[str] = set()` to `FSMExecutor.__init__`.
3. After `_handle_rate_limit` returns an in-place target, mark the state in `_rate_limit_in_flight`.
4. In the retry-counting block, skip increment if the state is in `_rate_limit_in_flight`; discard after consuming.
5. Add tests:
   - `test_rate_limit_skipped_when_exit_code_zero` — exit_code=0 with "rate limit" in output routes normally (no retry).
   - `test_rate_limit_retry_does_not_consume_max_retries` — N rate-limit retries followed by action-error retries: only action-error retries count against `max_retries`.

## Related

- BUG-1105 (done): FSM loops silently skipping work on rate-limit — the fix for that issue added rate-limit retry logic; this bug is the inverse (retry logic too aggressive).
- Audit: `audit-rlhf-animated-svg-2026-06-09.md` — Proposal 2.

## Impact

- **Priority**: P2 — Causes silent loss of long-running successful work; loops that completed successfully are discarded and marked failed, with no recovery path.
- **Effort**: Small — Two targeted guards in `executor.py` (~5 lines each) plus two new test cases; no new behavior added.
- **Risk**: Low — Guards are narrowly scoped (exit_code check + set membership check); they only prevent false positives and add no code paths that didn't exist before.
- **Breaking Change**: No

## Labels

`bug`, `fsm`, `rate-limit`, `executor`

## Status

**Open** | Created: 2026-06-10 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-06-10T01:03:01 - `206b4f70-88ba-48b0-b242-51d5e51f39d4.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a35aa6aa-87b6-4195-9999-42a59f417280.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7629637a-6cfe-473e-b481-fe1a913607f6.jsonl`
- `/ll:format-issue` - 2026-06-10T00:43:55 - `90b6c2b3-9e72-43e6-b0cd-271e91d5ea62.jsonl`
- `/ll:capture-issue` - 2026-06-10T00:39:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5aa504ea-5921-488d-9ecf-3b2ac6ff0d2a.jsonl`
