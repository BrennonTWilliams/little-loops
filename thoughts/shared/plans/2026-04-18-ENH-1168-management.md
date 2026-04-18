# ENH-1168 Implementation Plan

**Issue**: `.issues/enhancements/P3-ENH-1168-fsm-executor-wrap-run-action-in-execute-state-with-on-error-routing.md`
**Confidence**: 100/100
**TDD**: Enabled

## Goal

Make `_run_action` exceptions in `_execute_state` route to `state.on_error` (when defined) instead of escaping to the top-level handler and terminating the loop. Apply to both Branch B (`state.next` path, line 457) and Branch C (evaluated path, line 478).

## Design

Add a small guarded helper to avoid duplicating try/except:

```python
def _run_action_or_route(
    self, state: StateConfig, ctx: InterpolationContext
) -> tuple[ActionResult | None, str | None]:
    """Run the state action. Return (result, routed_target).

    routed_target is a non-None next-state name only if an exception was raised
    and state.on_error is set. Otherwise result is the ActionResult and routed_target
    is None. Re-raises when no on_error is configured.
    """
    try:
        return self._run_action(state.action, state, ctx), None
    except Exception as exc:
        if state.on_error:
            self._emit(
                "action_error",
                {
                    "state": self.current_state,
                    "error": str(exc),
                    "route": "on_error",
                },
            )
            return None, interpolate(state.on_error, ctx)
        raise
```

Call sites:

- **Branch B (line 457)**: Replace `result = self._run_action(...)` with the helper. If `routed_target` is not None, short-circuit `return routed_target` (skip the shell-exit-code handling that follows).
- **Branch C (line 478)**: Replace `action_result = self._run_action(...)` with the helper. If `routed_target` is not None, short-circuit `return routed_target` (skip evaluation and route interceptors).

## Phase 0: Write Tests (Red)

New test class `TestActionExceptionRouting` in `scripts/tests/test_fsm_executor.py` (placed near line 2041 after `TestSignalHandling`):

1. `test_exception_in_branch_c_routes_to_on_error` — state with `on_error`; runner raises `RuntimeError`; assert `final_state` equals on_error target.
2. `test_exception_in_branch_c_without_on_error_reraises` — no `on_error`; runner raises; assert `terminated_by == "error"` (parity with existing test at line 1884).
3. `test_exception_in_branch_b_routes_to_on_error_not_next` — state with `next` and `on_error`; runner raises; assert route is `on_error` target, not `next`.
4. `test_action_error_event_emitted_on_routed_path` — capture events; runner raises; assert `action_error` event with payload `{state, error, route: "on_error"}`.
5. `test_interpolation_error_routes_to_on_error_when_set` — action `"${missing}"` with `on_error`; assert routes to `on_error` (friendly `--context` message NOT emitted).
6. `test_on_error_template_interpolated` — `on_error: "${context.fallback}"` with `context.fallback: "recover"`; runner raises; assert final state resolves to `recover`.

Use an inline `RaisingRunner` modeled on `FailingRunner` at line 1898.

## Phase 1: Implementation

1. Add `_run_action_or_route` helper in `executor.py`.
2. Update Branch B (line 457) and Branch C (line 478) to use it.
3. Inline the event name string `"action_error"` (skip named constant per issue step 12; mirrors other non-rate-limit events).

## Phase 2: Schema Registration

1. `scripts/little_loops/generate_schemas.py`:
   - Add `"action_error"` entry to `SCHEMA_DEFINITIONS` in the FSM Executor section (follows `action_start` / `action_complete` pattern). Payload: `state: str`, `error: str`, `route: str`. Required: `["state", "error", "route"]`.
   - Bump count `22` → `23` in docstrings at lines 1, 78 (comment), and 345.
   - Update comment `"FSM Executor (14 types)"` → `"FSM Executor (15 types)"`.

2. `scripts/tests/test_generate_schemas.py`:
   - Bump `== 22` → `== 23` at lines 19, 57, 64, 174.
   - Add `"action_error"` to `expected` set at lines 22–45.

3. Regenerate: `ll-generate-schemas` → creates `docs/reference/schemas/action_error.json`.

## Phase 3: Fix Pre-Existing Test

`scripts/tests/test_ll_loop_errors.py:306` — remove `on_error: failed` from inline YAML to preserve the friendly `--context` UX (option (a) per wiring recommendation).

## Phase 4: Docs

1. `docs/reference/EVENT-SCHEMA.md` — add `### action_error` section under FSM Executor.
2. `docs/generalized-fsm-loop.md:451` — expand `on_error` precedence to include raised Python exceptions.
3. `docs/ARCHITECTURE.md`, `docs/reference/API.md`, `docs/guides/LOOPS_GUIDE.md` — update error-routing descriptions to note action exceptions are now catchable.

## Phase 5: Verification

- `python -m pytest scripts/tests/` — all pass
- `python -m mypy scripts/little_loops/` — no errors
- `ruff check scripts/` — clean
- `ll-generate-schemas` — regenerates cleanly (schema file committed)

## Success Criteria

- [ ] All 6 new tests pass (Green after implementation)
- [ ] Existing exception-during-execution test still passes
- [ ] `TestInterpolationErrorHandling` friendly-message test still passes
- [ ] Schema count bumped to 23 across generate_schemas.py and test_generate_schemas.py
- [ ] `action_error.json` regenerated
- [ ] `test_missing_context_input_clear_error` updated and passes
- [ ] mypy + ruff clean
- [ ] Full suite passes
