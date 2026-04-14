---
parent: BUG-1105
priority: P2
type: BUG
size: Medium
confidence_score: 95
outcome_confidence: 87
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 22
---

# BUG-1107: FSM Executor 429 Detection, Retry, and Persistence

## Summary

Decomposed from BUG-1105: FSM Loops Silently Skip All Work on 429 Rate Limit Failures.

This child covers the core behavioral change: detect 429/rate-limit responses in the FSM executor's `before_route` interceptor, apply exponential backoff retry in-place, track retry counts in a new `_rate_limit_retries` dict, emit a `rate_limit_exhausted` event when retries are exhausted, and save/restore that dict in persistence so retry counts survive loop pause/resume.

## Current Behavior

- `executor.py`'s `before_route` interceptor does not inspect `ActionResult` for rate-limit signals
- 429-failed actions route via `on_error`/`on_no` identically to intentional skips
- `persistence.py` only saves/restores `_retry_counts`; a new parallel dict would be lost on resume

## Expected Behavior

- `before_route` detects 429/rate-limit patterns in `action_result.output` + `action_result.stderr`
- Applies exponential backoff sleep with jitter (`base * 2^n + uniform(0, base)` seconds, default base=30), polling `_shutdown_requested` every 100ms to remain cancellable; jitter desynchronizes wakeups across parallel worktrees to prevent thundering herd on shared API quota
- Returns `RouteDecision(route_ctx.state_name)` to retry the state in-place (do NOT use `"$current"`)
- Tracks retries per state in `_rate_limit_retries: dict[str, int]` (parallel to `_retry_counts`)
- When retries exhausted: emits a `rate_limit_exhausted` event and routes to `on_rate_limit_exhausted` (if configured) or falls back to `on_error`
- `persistence.py` saves and restores `_rate_limit_retries` in parallel with `_retry_counts`
- `__init__.py` re-exports the new `rate_limit_exhausted` event type constant

## Root Cause

See BUG-1105 for full root cause analysis.

## Key Implementation Details

- **Detection patterns**: reuse `classify_failure()` from `scripts/little_loops/issue_lifecycle.py:47` — actual signature is `classify_failure(error_output: str, returncode: int) -> tuple[FailureType, str]`; quota patterns at lines 59-75: `["429", "rate limit", "too many requests", "quota exceeded", "resource exhausted", "resourceexhausted", "out of extra usage", "usage limit", "api limit"]`; pass combined `output + stderr` as `error_output` and `action_result.exit_code` as `returncode`
- **Interceptor hook**: `executor.py:455-461` — `before_route` receives `RouteContext` (`executor.py:53-63`) with `action_result: ActionResult | None`; `ActionResult` fields are `output: str`, `stderr: str`, `exit_code: int`, `duration_ms: int` (`types.py:57-71`)
- **Do NOT use `"$current"`** in `RouteDecision` — bypassed by `before_route` return path; use `route_ctx.state_name`
- **Interruptible sleep model**: `executor.py:299-305` — polls `_shutdown_requested` every 100ms using `min(0.1, remaining)` chunks; apply identical pattern for backoff sleeps inside `_execute_state`
- **Backoff formula with jitter**: `sleep_seconds = base * (2 ** attempt) + random.uniform(0, base)` where `base = _DEFAULT_RATE_LIMIT_BACKOFF_BASE` (module-level constant, default `30`). At base=30 this yields 30-60s / 60-120s / 120-180s per attempt. Jitter is critical when `ll-parallel` runs multiple worktrees concurrently — without it all loops backoff identically and produce a thundering herd that immediately re-triggers the 429. BUG-1108 will replace `_DEFAULT_RATE_LIMIT_BACKOFF_BASE` with a read from `route_ctx.state.rate_limit_backoff_base_seconds`.
- **`_retry_counts` pattern to mirror**: declared `executor.py:142-148`, incremented `executor.py:200-206`, exhaustion check `executor.py:229-252`; `_rate_limit_retries` must be incremented INSIDE `_execute_state` (NOT via the main-loop `_prev_state` mechanism, which would also incorrectly increment `_retry_counts`)
- **Persistence `LoopState` dataclass**: add `rate_limit_retries: dict[str, int] = field(default_factory=dict)` at `persistence.py:103` (parallel to `retry_counts`); update `to_dict` to serialize only when non-empty, `from_dict` to deserialize with `data.get("rate_limit_retries", {})` — see `retry_counts` pattern at `persistence.py:122-123, 150`
- **Persistence save/restore**: `persistence.py:426` — add `rate_limit_retries=dict(self._executor._rate_limit_retries)`; `persistence.py:493` — add `self._executor._rate_limit_retries = dict(state.rate_limit_retries)`
- **Event emission**: events use `self._emit("event_name", data_dict)` at `executor.py:811-819` — no EventType enum; plain string name `"rate_limit_exhausted"` follows existing pattern (e.g., `"retry_exhausted"` at `executor.py:241-248`)
- **Routing lookup (stub for BUG-1108)**: `on_rate_limit_exhausted` is NOT yet a `StateConfig` field until BUG-1108 runs (which adds it to `_known_on_keys` at `schema.py:305-338`). Stub as `target = route_ctx.state.extra_routes.get("rate_limit_exhausted") or route_ctx.state.on_error` — this works today because unknown `on_*` keys land in `extra_routes`; BUG-1108 will promote it to a first-class field
- **`generate_schemas.py` is owned by BUG-1108** — that issue adds the `"rate_limit_exhausted"` entry to `SCHEMA_DEFINITIONS` and updates the count; do not touch here

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — add `_rate_limit_retries: dict[str, int] = {}` in `__init__` (line 142 area); add 429-detection + backoff + exhaustion logic inside `_execute_state` **before** the `for interceptor in self._interceptors:` loop (line 455) — placing it before ensures a rate-limit in-place retry returns early without dispatching to registered interceptors
- `scripts/little_loops/fsm/persistence.py` — add `rate_limit_retries` field to `LoopState` dataclass (line 103); update `to_dict` (line 122), `from_dict` (line 150), `_save_state` (line 426), `resume` (line 493)
- `scripts/little_loops/fsm/__init__.py` — re-export new event type constant

### Dependent Files (Do NOT need modification here)
- `scripts/little_loops/issue_lifecycle.py:47` — `classify_failure()` reused read-only; import `FailureType` from here
- `scripts/little_loops/fsm/types.py:57-71` — `ActionResult` fields `output`, `stderr` already present
- `scripts/little_loops/fsm/schema.py:296-337` — `extra_routes` mechanism handles the stub `on_rate_limit_exhausted` routing until BUG-1108 adds the first-class field
- `scripts/little_loops/generate_schemas.py` — **owned by BUG-1108**: adds `"rate_limit_exhausted"` to schema registry at lines 78-290

### Tests
- `scripts/tests/test_fsm_executor.py:3206-3376` — `TestPerStateRetryLimits`: model new tests on this class for `_rate_limit_retries` increment, exhaustion, and event emission
- `scripts/tests/test_fsm_executor.py:3979-4161` — `TestInterceptorDispatch`: model `before_route` interaction tests here
- `scripts/tests/test_fsm_persistence.py:1152-1182` — model resume/restore tests for `rate_limit_retries` on this pattern
- `scripts/tests/test_issue_lifecycle.py:748-798` — existing `classify_failure` tests show parametrized rate-limit string coverage

### Documentation
- `docs/reference/EVENT-SCHEMA.md` — may need updating to document new `rate_limit_exhausted` event
- `docs/reference/schemas/` — `generate_schemas.py` run will produce `rate_limit_exhausted.json`

## Implementation Steps

1. **`executor.py` — declare `_rate_limit_retries`**: In `FSMExecutor.__init__` alongside `_retry_counts` (line 142), add `self._rate_limit_retries: dict[str, int] = {}`
2. **`executor.py` — add 429 detection in `_execute_state`**: Insert the block **before** the `for interceptor in self._interceptors:` loop at line 455 (not within it) — so a rate-limit in-place retry returns early without dispatching to registered interceptors. Check `action_result` via `classify_failure()`; if rate-limited, increment `_rate_limit_retries[state_name]`, compute `sleep_seconds = _DEFAULT_RATE_LIMIT_BACKOFF_BASE * (2 ** attempt) + random.uniform(0, _DEFAULT_RATE_LIMIT_BACKOFF_BASE)` and apply interruptible sleep using `executor.py:299-305` pattern, then check exhaustion
3. **`executor.py` — exhaustion path**: When `_rate_limit_retries[state_name] > max_rate_limit_retries` (hardcode `3` as a module-level constant `_DEFAULT_RATE_LIMIT_RETRIES = 3` and `30` as `_DEFAULT_RATE_LIMIT_BACKOFF_BASE = 30`; BUG-1108 will replace these reads with `route_ctx.state.max_rate_limit_retries` and `route_ctx.state.rate_limit_backoff_base_seconds` after the `StateConfig` fields land), emit `self._emit("rate_limit_exhausted", {...})`, look up `route_ctx.state.extra_routes.get("rate_limit_exhausted") or route_ctx.state.on_error`, return `RouteDecision(target)` or call `self._finish("error")` if neither is set
4. **`executor.py` — in-place retry path**: When under limit, return `RouteDecision(route_ctx.state_name)` from within the interceptor dispatch to retry without going through the normal routing
5. **`persistence.py` — `LoopState` field**: Add `rate_limit_retries: dict[str, int] = field(default_factory=dict)` to `LoopState` dataclass; update `to_dict` and `from_dict` following the `retry_counts` pattern
6. **`persistence.py` — save/restore**: Add `rate_limit_retries=dict(self._executor._rate_limit_retries)` at line 426 and `self._executor._rate_limit_retries = dict(state.rate_limit_retries)` at line 493
7. **`__init__.py` — export**: Add the new event type constant to `__all__`

## Files to Modify

- `scripts/little_loops/fsm/executor.py` — `_rate_limit_retries` declaration, 429 detection + backoff + exhaustion in `_execute_state`
- `scripts/little_loops/fsm/persistence.py` — `LoopState.rate_limit_retries` field; save (`line 426`) and restore (`line 493`)
- `scripts/little_loops/fsm/__init__.py` — re-export new event type constant

## Acceptance Criteria

- [ ] `before_route` detects rate-limit patterns in `ActionResult.output` + `ActionResult.stderr`
- [ ] Exponential backoff with jitter (`base * 2^n + uniform(0, base)`) applied; sleep is cancellable via `_shutdown_requested`
- [ ] Jitter desynchronizes wakeup times across parallel worktrees (thundering herd prevention)
- [ ] `_rate_limit_retries` dict tracks per-state retry counts (parallel to `_retry_counts`)
- [ ] `rate_limit_exhausted` event emitted when retries exhausted
- [ ] Routes to `on_rate_limit_exhausted` if present on state config, otherwise `on_error`
- [ ] `persistence.py` saves and restores `_rate_limit_retries`
- [ ] `__init__.py` exports the new event type constant
- [ ] Non-429 failures are unaffected

## Dependencies

- Depends on BUG-1108 for `StateConfig.max_rate_limit_retries` and `on_rate_limit_exhausted` fields (stub with defaults during implementation if needed)

## Session Log
- `/ll:refine-issue` - 2026-04-14T16:00:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dd35ea7b-b89a-4d9f-9b21-2d82d177c6c6.jsonl`
- `/ll:issue-size-review` - 2026-04-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4abdbd46-1b62-4801-9d00-a2569583afde.jsonl`
- `/ll:confidence-check` - 2026-04-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a94e7ca3-0764-413e-b1a0-589250334b95.jsonl`
- `/ll:confidence-check` - 2026-04-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/848b5fee-42e8-4aa7-8e5d-15811fe3db56.jsonl`

---

## Status

**Open** | Created: 2026-04-14 | Priority: P2
