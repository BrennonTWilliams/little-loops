# ENH-1293: Executor-level API resilience — Plan

**Date**: 2026-04-26
**Issue**: ENH-1293 — Transient server-error retry + sub-loop budget forwarding

## Research Findings

### Key Files
- `scripts/little_loops/issue_lifecycle.py` — `classify_failure` (line 53), `FailureType` enum (line 42)
- `scripts/little_loops/fsm/executor.py` — `_handle_rate_limit` (line 972), `_execute_state` rate-limit branch (line 536), `_execute_sub_loop` (line 391), `__init__` tracking dicts (line 177-201)
- `scripts/tests/test_issue_lifecycle.py` — `TestClassifyFailure` (line 746)
- `scripts/tests/test_fsm_executor.py` — `TestRateLimitRetries` (line 4584), `MockActionRunner` (line 29)

### Current TRANSIENT Routing Gap
`_execute_state` at line 541 only triggers `_handle_rate_limit` when the reason contains "rate limit" or "quota". Other `TRANSIENT` subtypes (network, timeout, resource, server-error) fall through to the `else` branch which resets tracking and proceeds to normal routing. Server errors hit `exit_code=1 → verdict="no" → FSM failure path`.

### Sub-loop Budget Gap
`_execute_sub_loop` constructs the child executor with the child FSM's own unmodified `timeout`. The parent's `self.start_time_ms` + `self.elapsed_offset_ms` + `_now_ms()` provide the elapsed budget.

## Implementation Plan

### Phase 1: `issue_lifecycle.py` — Server-error patterns

Add a new pattern group before the default return (after resource_patterns at line 129):
```python
server_error_patterns = [
    "the server had an error",
    "internal server error",
    "overloaded_error",
    "overloaded",
    "529",
    "api error",
]
if any(pattern in error_lower for pattern in server_error_patterns):
    return (FailureType.TRANSIENT, "API server error")
```

### Phase 2: `executor.py` — Constants

After line 73 (after `LLM_ACTION_TYPES`), add:
```python
_DEFAULT_API_ERROR_RETRIES: int = 2
_DEFAULT_API_ERROR_BACKOFF: int = 30
```

### Phase 3: `executor.py` — `__init__` tracking dict

After line 201 (`_consecutive_rate_limit_exhaustions`), add:
```python
self._api_error_retries: dict[str, dict[str, Any]] = {}
```

### Phase 4: `executor.py` — `_handle_api_error` method

Add after `_exhaust_rate_limit` (after line 1145). Flat backoff, no long-wait ladder, falls through on exhaustion.

### Phase 5: `executor.py` — Wire into `_execute_state`

Add `elif` branch for API server error between rate-limit `if` and `else`. Reset `_api_error_retries` in `else`.

### Phase 6: `executor.py` — Sub-loop budget clamping

In `_execute_sub_loop`, after `child_executor._depth = depth` (line 434), before `child_result = child_executor.run()`:
```python
if self.fsm.timeout:
    elapsed_ms = _now_ms() - self.start_time_ms + self.elapsed_offset_ms
    remaining_s = max(1, int((self.fsm.timeout * 1000 - elapsed_ms) // 1000))
    if child_fsm.timeout is None or child_fsm.timeout > remaining_s:
        child_fsm.timeout = remaining_s
```

### Phase 7: Tests

In `test_issue_lifecycle.py`: Add server-error parametrize cases.
In `test_fsm_executor.py`: Add `TestAPIErrorRetries` class mirroring `TestRateLimitRetries` structure.

## Success Criteria
- [x] `classify_failure("API Error: The server had an error", 1)` → `(TRANSIENT, "API server error")`
- [x] API server error retried in-place up to 2× then falls through
- [x] Sub-loop `child_fsm.timeout` clamped to parent remaining budget
- [x] Existing rate-limit tests still pass
