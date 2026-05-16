---
id: ENH-1293
type: ENH
priority: P3
status: done
captured_at: "2026-04-26T15:55:17Z"
completed_at: 2026-04-26T16:23:48Z
discovered_date: 2026-04-26
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1293: Executor-level API resilience: transient server-error retry and sub-loop budget forwarding

## Summary

Two executor-level fixes that improve FSM loop resilience against API server errors and timeout budget overrun — without requiring per-loop YAML retry logic.

**Fix 1 — Transient server-error retry**: When a prompt/slash_command action fails with a server error ("The server had an error while processing your request", overload, 529), the executor should automatically retry with short-burst backoff (≤3 attempts, ~30s each) before propagating the exit code to FSM routing.

**Fix 2 — Sub-loop remaining-budget forwarding**: When spawning a child FSM via `_execute_sub_loop`, clamp the child's `timeout` to the parent's remaining wall-clock budget so the child terminates cleanly and the parent can route via `on_no`/`dequeue_next` rather than hitting the parent's hard timeout with no recourse.

## Current Behavior

**Fix 1**: `classify_failure` (in `issue_lifecycle.py`) does not recognize server-error strings like `"The server had an error while processing your request"` as transient — they fall through to `FailureType.REAL` (default). In `_execute_state`, only failures classified as `TRANSIENT` with `"rate limit"` or `"quota"` in the reason trigger the retry path (`_handle_rate_limit`). All other transient failures (server errors, overload) are routed as normal logic failures — `exit_code=1` → verdict `no` → FSM takes the failure path. In the observed incident (ENH-461), `confidence_check` returned `exit_code=1` with `"API Error: The server had an error..."` in its output; `autodev` treated this as a genuine below-threshold score and routed ENH-448 to `breakdown_issue`, causing premature decomposition.

**Fix 2**: `_execute_sub_loop` in `executor.py` constructs the child FSM with its own unmodified `timeout`. The parent's remaining budget is not forwarded. A slow sub-loop can legally consume the parent's entire remaining wall-clock budget. In the observed incident (ENH-460), `refine_issue` for BUG-452 ran for 29.5 min; combined with `wire_issue` and `confidence_check`, the full sub-loop consumed ~47 min and pushed the outer `autodev` loop past its 8h timeout before `implement_current` could run — despite BUG-452 having reached a perfect 100/100 readiness/outcome score.

## Expected Behavior

**Fix 1**: Server errors from the API (5xx, overload, `"server had an error"`, `529`) are classified as transient. The executor auto-retries the state up to `max_api_error_retries` times (default: 2) with a short flat backoff (default: 30s) before falling through to normal FSM routing. Retry/exhaustion events are emitted for observability. No loop YAML changes required.

**Fix 2**: Before constructing the child FSM, `_execute_sub_loop` computes the parent's remaining budget and clamps `child_fsm.timeout` to it. When the child times out against this clamped budget, it returns `terminated_by="timeout"`, and the parent routes via the sub-loop state's `on_no`/`on_failure` edge — draining the queue gracefully rather than crashing the outer loop's wall-clock deadline.

## Motivation

Both failures required per-loop YAML workarounds: ENH-461 proposed adding a `max_rate_limit_retries`-style guard specifically in `refine-to-ready-issue`; ENH-460 proposed bumping the `autodev` timeout from 8h to 12h. Executor-level fixes eliminate this boilerplate and protect all current and future loops automatically.

The ENH-448 premature decomposition represents a correctness failure: the issue was ready, but the loop was misdirected by a transient infrastructure event. BUG-452 represents a lost implementation opportunity: 47 min of refinement work discarded because budget tracking didn't cross loop boundaries.

## Proposed Solution

### Fix 1 — Transient server-error retry

**Step 1**: Extend `classify_failure` in `scripts/little_loops/issue_lifecycle.py` to recognize server-error patterns:
```python
server_error_patterns = [
    "the server had an error",
    "internal server error",
    "overloaded_error",
    "overloaded",
    "529",          # Anthropic overload code
    "api error",    # generic "API Error: ..." prefix from Claude Code
]
if any(pattern in error_lower for pattern in server_error_patterns):
    return (FailureType.TRANSIENT, "API server error")
```

**Step 2**: Add `_handle_api_error` to `FSMExecutor` in `executor.py` — short-burst only, no long-wait ladder:
```python
def _handle_api_error(self, state: StateConfig, state_name: str) -> tuple[bool, str | None]:
    record = self._api_error_retries.setdefault(state_name, {"retries": 0, "total_wait": 0.0})
    max_retries = getattr(state, "max_api_error_retries", None) or _DEFAULT_API_ERROR_RETRIES  # default 2
    backoff = getattr(state, "api_error_backoff_seconds", None) or _DEFAULT_API_ERROR_BACKOFF  # default 30
    if record["retries"] >= max_retries:
        self._api_error_retries.pop(state_name, None)
        self._emit("api_error_exhausted", {"state": state_name, "retries": record["retries"]})
        return False, None  # fall through to normal routing
    record["retries"] += 1
    slept = self._interruptible_sleep(backoff)
    record["total_wait"] += slept
    self._emit("api_error_retry", {"state": state_name, "attempt": record["retries"], "backoff": backoff})
    return True, state_name  # retry in place
```

**Step 3**: Wire into `_execute_state` beside the rate-limit branch:
```python
elif _failure_type == FailureType.TRANSIENT and "api server error" in _reason.lower():
    _handled, _target = self._handle_api_error(state, route_ctx.state_name)
    if _handled:
        return _target
    # exhausted — fall through to normal verdict routing
```

Also reset `_api_error_retries` on non-error outcomes alongside `_rate_limit_retries`.

### Fix 2 — Sub-loop remaining-budget forwarding

In `_execute_sub_loop` in `executor.py`, before constructing the child executor, clamp the child timeout:
```python
if self.fsm.timeout:
    elapsed_ms = _now_ms() - self.start_time_ms + self.elapsed_offset_ms
    remaining_s = max(1, (self.fsm.timeout * 1000 - elapsed_ms) // 1000)
    if child_fsm.timeout is None or child_fsm.timeout > remaining_s:
        child_fsm.timeout = remaining_s
```

No loop YAML changes needed. Existing `on_no`/`on_failure` edges on sub-loop states already handle child timeout gracefully (e.g., `autodev`'s `refine_current` → `on_failure: copy_broke_down`).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop`, `_execute_state`, add `_handle_api_error`, add `_api_error_retries` dict to `__init__`
- `scripts/little_loops/issue_lifecycle.py` — `classify_failure` server-error patterns

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/runners.py` — no changes, uses executor internals
- `scripts/little_loops/cli/loop/run.py` — no changes needed
- Any loop that calls `_execute_sub_loop` indirectly (autodev, refine-to-ready-issue, recursive-refine) benefits automatically

### Similar Patterns
- `_handle_rate_limit` in `executor.py` — `_handle_api_error` mirrors its shape but with flat backoff and no long-wait ladder
- `_retry_counts` / `_rate_limit_retries` dicts — `_api_error_retries` follows the same per-state-name keyed dict pattern

### Tests
- `scripts/tests/test_fsm_executor.py` (or equivalent) — add tests for:
  - Server-error output classified as TRANSIENT/"API server error"
  - `_handle_api_error` retries in place up to `max_api_error_retries`, then falls through
  - `_execute_sub_loop` clamps child timeout to parent remaining budget
  - Child timeout → parent routes via `on_no`

### Documentation
- N/A

### Configuration
- No new config fields required (defaults baked into executor constants). Optional: expose `max_api_error_retries` / `api_error_backoff_seconds` as FSM-level or state-level schema fields in `schema.py` if per-loop tunability is desired (out of scope for this issue).

## API/Interface

N/A — No public API changes. All modifications are internal to `FSMExecutor` and `classify_failure`; no schema fields, CLI arguments, or public module interfaces change.

## Implementation Steps

1. Add server-error patterns to `classify_failure` in `issue_lifecycle.py`
2. Add `_api_error_retries` dict to `FSMExecutor.__init__`, implement `_handle_api_error`
3. Wire `_handle_api_error` into `_execute_state` beside the rate-limit branch; reset on clean outcomes
4. Add remaining-budget clamping to `_execute_sub_loop`
5. Add tests for both behaviors; verify existing rate-limit tests still pass

## Impact

- **Priority**: P3 — reliability improvement; eliminates per-loop retry boilerplate; directly caused two failed loop runs
- **Effort**: Small — ~80 lines across 2 files; no schema changes required; additive changes only
- **Risk**: Low — both changes are additive; existing routing paths unchanged for non-error cases
- **Breaking Change**: No

## Scope Boundaries

- **Out of scope**: skill-level score caching (short-circuit `confidence_check` on cached frontmatter — separate ENH-461 item); `refine_issue` performance optimization (separate ENH-460 item); per-state `max_duration` kill-timeout (a larger feature); changes to any loop YAML files.
- Executor-level only. No loop YAML modifications.

## Success Metrics

- API server errors during prompt/slash_command states are retried automatically without FSM routing side-effects
- A sub-loop that would exceed the parent's remaining budget terminates with `terminated_by=timeout` and the parent routes via `on_no` — no parent wall-clock timeout needed
- Existing rate-limit retry behavior is unchanged

## Labels

`enhancement`, `loops`, `fsm`, `captured`

## Session Log
- `/ll:manage-issue` - 2026-04-26T16:23:48Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e72e6f55-689c-4446-a282-e790c6de43c5.jsonl`
- `/ll:ready-issue` - 2026-04-26T16:10:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e72e6f55-689c-4446-a282-e790c6de43c5.jsonl`
- `/ll:confidence-check` - 2026-04-26T16:10:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19d888fc-9d07-4112-a699-8e85e5e4b1a4.jsonl`
- `/ll:format-issue` - 2026-04-26T16:01:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/94484366-6d21-45f4-bb1a-79697c996675.jsonl`
- `/ll:capture-issue` - 2026-04-26T15:55:17Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ffdee53-56db-44d2-9808-6c86e33f5c0f.jsonl`

---

## Resolution

**Completed**: 2026-04-26

### Changes Made

**Fix 1 — Transient server-error retry** (`scripts/little_loops/issue_lifecycle.py`, `scripts/little_loops/fsm/executor.py`):
- Extended `classify_failure` to recognize server-error patterns (`"the server had an error"`, `"internal server error"`, `"overloaded_error"`, `"overloaded"`, `"529"`, `"api error"`) returning `(TRANSIENT, "API server error")`
- Added `_DEFAULT_API_ERROR_RETRIES = 2` and `_DEFAULT_API_ERROR_BACKOFF = 30` constants
- Added `_api_error_retries` per-state tracking dict to `FSMExecutor.__init__`
- Added `_handle_api_error` method (flat backoff, no long-wait tier, falls through on exhaustion)
- Wired into `_execute_state` as `elif` branch beside rate-limit handler; resets `_api_error_retries` in `else` on clean outcomes

**Fix 2 — Sub-loop remaining-budget forwarding** (`scripts/little_loops/fsm/executor.py`):
- Added budget clamping in `_execute_sub_loop` before `child_executor.run()`: computes parent elapsed time and clamps `child_fsm.timeout` to remaining budget (`max(1, remaining_s)`)

**Tests** (`scripts/tests/test_issue_lifecycle.py`, `scripts/tests/test_fsm_executor.py`):
- 4 new parametrize cases for server-error `classify_failure` patterns
- `TestAPIErrorRetries` class (7 tests): retry in-place, exhaustion fallthrough, events, counter reset, independence from rate-limit handler, 529 variant
- `TestSubLoopBudgetClamping` class (3 tests): clamping verified, no-timeout parent passthrough, child-timeout → parent `on_no` routing

## Status

**Completed** | Created: 2026-04-26 | Priority: P3
