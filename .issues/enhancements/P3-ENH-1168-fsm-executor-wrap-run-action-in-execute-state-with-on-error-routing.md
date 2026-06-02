---
captured_at: 2026-04-18T19:59:00Z
discovered_date: 2026-04-18
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 75
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 18
status: done
completed_at: 2026-04-18T00:00:00Z
---

# ENH-1168: FSM executor wrap run_action in execute_state with on_error routing

## Summary

`_execute_state()` at `executor.py:478` calls `self._run_action(state.action, state, ctx)` without any `try/except` guard. If `_run_action` raises an unhandled exception, it propagates out of `_execute_state` entirely and terminates the loop rather than routing to the state's `on_error` target. Wrapping the call in a `try/except Exception` that routes to `on_error` (when defined) makes exception behavior consistent with the already-handled non-zero exit-code and timeout paths.

## Context

**Direct mode**: User description: "FSM Loop error handling: Wrap _run_action() call in _execute_state() (executor.py:478) with try/except that routes caught exceptions to the state's on_error target instead of terminating the loop"

The executor already handles two similar failure modes for shell-based states (lines 446–471):
- `FileNotFoundError`/`ValueError` on action lookup → routes to `on_error`
- Non-zero exit code → routes to `on_error`

But the bare `_run_action` call at line 478 (used for the evaluate/prompt/mcp path) is unguarded. Any exception raised inside `_run_action` (e.g., from a broken MCP tool, a malformed prompt interpolation caught late, or an unexpected API error) escapes up to the top-level `except Exception` in `run()` (line 363), which records `fatal_error` and halts the loop — ignoring any `on_error` transition the state author defined.

## Motivation

Loop authors expect `on_error` to catch action-level failures. When `_run_action` throws, `on_error` is silently bypassed, making recovery impossible and error diagnosis harder. Consistent exception routing means loops can self-heal (e.g., `on_error: retry_state`) without requiring loop authors to understand executor internals.

## Proposed Solution

In `_execute_state()` (`scripts/little_loops/fsm/executor.py`, around line 475–479), wrap the `_run_action` call:

```python
try:
    action_result = self._run_action(state.action, state, ctx)
except Exception as exc:
    if state.on_error:
        self._emit("action_error", {
            "state": self.current_state,
            "error": str(exc),
            "route": "on_error",
        })
        return interpolate(state.on_error, ctx)
    raise
```

The `raise` on the no-`on_error` path preserves current behavior for states that don't define error handling, so this is purely additive.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Logging convention**: this file has no `_log_error` method. Observability goes through `self._emit(event_name, {...})` (`executor.py:879-887`). Use `_emit` for the exception log, mirroring existing events like `action_start`, `action_complete`, `route`.
- **Second unguarded `_run_action` call site**: Branch B (the `state.next` path) calls `self._run_action(state.action, state, ctx)` at `executor.py:457` with the same lack of try/except. Any non-shell-failure exception escaping `_run_action` there also bypasses `on_error`. The fix should wrap **both** call sites (line 457 and line 478) for consistency, or consolidate into a single helper.
- **Interpolation form**: use `interpolate(state.on_error, ctx)` — matches the three existing inlined on_error routes at `executor.py:450, 466, 471`. Do **not** use `_resolve_route` here; that method only adds `$current` token handling, which isn't needed for the exception path (all other on_error escape paths in `_execute_state` use the bare `interpolate` form).
- **Concrete exception types that currently escape `_run_action`** (from `executor.py:536` down through `runners.py`):
  - `InterpolationError` from `interpolate(action_template, ctx)` at `executor.py:552` and `interpolate_dict(state.params, ctx)` at `executor.py:562`
  - `FileNotFoundError` / `PermissionError` from `subprocess.Popen` in `runners.py:126` (shell mode) — not caught in `DefaultActionRunner.run()`
  - Arbitrary exceptions from contributed `ActionRunner` implementations (`executor.py:569-579`)
- **Currently these all land in** the top-level `except Exception` at `executor.py:363`, which calls `_finish("error", error=str(exc))` and terminates the loop — bypassing `state.on_error` entirely.
- **InterpolationError handling interaction**: `executor.py:355-362` catches `InterpolationError` specifically at the `run()` level and produces a helpful "Missing context variable" message. Once `_execute_state` routes `InterpolationError` to `on_error`, that helpful message is no longer emitted for action-template interpolation failures. This is acceptable (on_error is an explicit opt-in), but worth noting in the test matrix.

## Implementation Steps

1. In `scripts/little_loops/fsm/executor.py`, wrap the `_run_action` call in Branch C at line 478 with `try/except Exception` — route to `interpolate(state.on_error, ctx)` when `state.on_error` is truthy, `raise` otherwise. Emit an `action_error` event via `self._emit(...)` on the routed path (see Proposed Solution snippet; mirror the shape of `_emit` calls at `executor.py:879-887`).
2. Apply the same wrap to the `_run_action` call in Branch B at line 457 (the `state.next` path). Consider extracting a small helper (e.g., `_run_action_guarded(state, ctx) -> ActionResult | None` returning `None` on routed exception, plus the routed next-state string) to avoid duplicating the try/except pattern across both call sites.
3. Add unit tests in `scripts/tests/test_fsm_executor.py` modeled after `test_sigkill_on_next_state_routes_via_on_error_if_configured` (line 2367) and `test_shell_failure_on_next_state_routes_via_on_error_when_configured` (line 2389). Use the existing `MockActionRunner` (`test_fsm_executor.py:30-92`) and extend it (or subclass inline) to raise an exception instead of returning an `ActionResult`. Cover at minimum:
   - `InterpolationError` raised from `_run_action` → routes to `on_error` when set; re-raises (and hits `except InterpolationError` at `executor.py:355`) when unset.
   - Generic `Exception` raised from `_run_action` → routes to `on_error` when set; re-raises (and hits `except Exception` at `executor.py:363`) when unset.
   - `on_error` template interpolation works (e.g., `on_error: "${ctx.fallback}"`) — mirror the existing shell-failure test but with a raised exception.
   - Branch B variant: same exception-raising test but with `state.next` set and no on_error-from-verdict path.
4. Verify existing executor tests still pass: `python -m pytest scripts/tests/test_fsm_executor.py -v`.
5. Run the full test suite and type checker: `python -m pytest scripts/tests/` and `python -m mypy scripts/little_loops/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Register the new `action_error` event in the schema catalog.** In `docs/reference/EVENT-SCHEMA.md`, add an `### action_error` subsection under the FSM Executor section documenting the payload fields `state`, `error`, `route`. Then in `scripts/little_loops/generate_schemas.py`, add an `"action_error"` entry to `SCHEMA_DEFINITIONS` at line 82 (follow the `action_start` / `action_complete` factory pattern at lines 112–143) and bump the hardcoded count from `22` → `23` at lines 1, 78, and 345.
7. **Regenerate schema files.** Run `ll-generate-schemas` to produce `docs/reference/schemas/action_error.json` and commit the generated file (per CONTRIBUTING.md lines 549–563 workflow).
8. **Update schema-generation tests.** In `scripts/tests/test_generate_schemas.py`, bump the `== 22` assertions at lines 19, 57, 64, 174 to `== 23` and add `"action_error"` to the expected event-type set at lines 22–45 (`test_expected_event_types_present`).
9. **Fix the CLI error test that will break.** In `scripts/tests/test_ll_loop_errors.py`, update `test_missing_context_input_clear_error` at line 306 — either remove `on_error: failed` from the inline loop YAML to preserve the friendly `--context` stderr path, or rewrite the assertions to match the new routing behavior (`terminated_by == "terminal"`, exit `0`). Prefer removing `on_error` to keep the friendly interpolation-error UX as a tested guarantee for loops that opt out of catching it.
10. **Update author-facing docs.** Edit `docs/generalized-fsm-loop.md:451` to expand the `on_error` precedence note beyond "shell non-zero" to include raised Python exceptions. Edit `docs/ARCHITECTURE.md`, `docs/reference/API.md` (~lines 3838-3844, 4052-4138), and `docs/guides/LOOPS_GUIDE.md` to describe action-exception routing per the existing Integration Map entries.
11. **Optional — event rendering branches.** If desired for live-run UX, add an `elif event_type == "action_error":` branch in `scripts/little_loops/cli/loop/_helpers.py` (near lines 395, 427, 433) to surface routed exceptions to the terminal during `ll-loop run`. The history viewer `scripts/little_loops/cli/loop/info.py` default branch already shows unknown events, so this is cosmetic.
12. **Decide on named constant.** If adding `ACTION_ERROR_EVENT = "action_error"` to `executor.py` (mirroring `RATE_LIMIT_EXHAUSTED_EVENT` et al. at lines 62-68), also re-export it via `scripts/little_loops/fsm/__init__.py` (import block lines 89-100, `__all__` lines 143-195). Otherwise inline the string literal in `_emit(...)` and skip this step.
13. **Re-run full suite.** `python -m pytest scripts/tests/` — must pass test_generate_schemas (new count + new event key), test_ll_loop_errors (updated), and new TestActionExceptionRouting cases.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — wrap `_run_action` call in `_execute_state()` at **line 478** (Branch C, evaluated-action path) and **line 457** (Branch B, `state.next` path). Route caught exceptions to `interpolate(state.on_error, ctx)` when set; re-raise otherwise.
- `scripts/tests/test_fsm_executor.py` — add new tests (see Implementation Steps) next to `TestSignalHandling` class (~line 2041) or add a dedicated `TestActionExceptionRouting` class.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/generate_schemas.py` — add `"action_error"` entry to `SCHEMA_DEFINITIONS` dict (line 82, follow `action_start` / `action_complete` pattern at lines 112–143 with payload fields `state: str`, `error: str`, `route: str`); bump hardcoded count `22` → `23` in docstrings at lines 1, 78, 345. [Agent 2 finding]
- `scripts/tests/test_generate_schemas.py` — bump `== 22` → `== 23` at lines 19, 57, 64, 174; add `"action_error"` to expected event-type set at lines 22–45 (otherwise `test_expected_event_types_present` will fail). [Agent 2 finding]
- `docs/reference/schemas/action_error.json` — **generated file**; regenerate via `ll-generate-schemas` after updating `SCHEMA_DEFINITIONS` (per CONTRIBUTING.md lines 549–563 workflow). [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md` — add a new `### action_error` section under the FSM Executor subsection documenting payload fields (`state`, `error`, `route`); this file is the source-of-truth event catalog (currently lists 14 bare-name FSM events, none named `action_error`). [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — update the `on_error` precedence note at line 451 ("When a shell action exits non-zero and `on_error` is defined...") to include raised Python exceptions alongside non-zero exits. [Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py:89-100, 143-195` — re-exports `FSMExecutor`, `ActionResult`, `ActionRunner`, `ExecutionResult`, and the three `RATE_LIMIT_*_EVENT` name constants. **If** implementation defines a named `ACTION_ERROR_EVENT = "action_error"` constant in `executor.py` (mirroring the rate-limit pattern at `executor.py:62-68`), add it to the import block and `__all__` here. If the event name is inlined as a string literal in `_emit(...)`, no change needed. [Agent 1/2 finding]
- `scripts/little_loops/cli/loop/_helpers.py:395, 427, 433` — `run_foreground` event-callback branches handle `action_start` / `action_output` / `action_complete`; new `action_error` events will fall through without terminal output. Optional: add a rendering branch to surface routed errors during live `ll-loop run`. [Agent 2 finding]
- `scripts/little_loops/cli/loop/info.py:236, 249, 254` — `ll-loop history` event rendering chain; `action_error` will fall through to the generic default. Optional polish, not a correctness issue. [Agent 2 finding]
- `scripts/little_loops/fsm/persistence.py:37, 1493` — `PersistentExecutor` wraps `FSMExecutor`; inherits behavior change transparently, no code changes required but is the path exercised by `ll-loop run`. [Agent 1 finding]

### Reference Sites (Do Not Modify — Use as Templates)
- `executor.py:445-451` — sub-loop `try/except (FileNotFoundError, ValueError)` → `on_error` pattern; closest existing analog to the fix.
- `executor.py:463-466, 470-471` — shell-state `on_error` routing via `interpolate(state.on_error, ctx)`; use identical return form.
- `executor.py:832-844` — `_resolve_route()` handles `$current` token; **not** used in exception path.
- `executor.py:879-887` — `_emit()` signature and event-shape convention for the new `action_error` event.
- `executor.py:355-364` — top-level `run()` exception handlers; the re-raised path still lands here and must continue to work for states without `on_error`.

### Callers / Dependents
- `run()` loop at `executor.py:312` — consumes the `str | None` returned by `_execute_state`; no changes needed.
- `_execute_sub_loop()` at `executor.py:~395` — independent of this change; already handles its own `on_error` routing.

### Tests (Existing — Must Not Regress)
- `scripts/tests/test_fsm_executor.py:2367` `test_sigkill_on_next_state_routes_via_on_error_if_configured` — model for new tests.
- `scripts/tests/test_fsm_executor.py:2389` `test_shell_failure_on_next_state_routes_via_on_error_when_configured` — model for new tests.
- `scripts/tests/test_fsm_executor.py:1921` `test_action_timeout_exit_code_124_routes_to_error` — timeout path; must still route via exit-code logic, not the new exception path.
- `scripts/tests/test_fsm_executor.py:3670` `test_sub_loop_missing_loop_with_on_error` — sub-loop `on_error` path; unchanged by this fix.
- `scripts/tests/test_ll_loop_errors.py` — CLI-level error routing; ensure no regression in behavior when `on_error` is unset (exception still terminates via `_finish("error", ...)`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py:1884` `TestErrorHandling.test_exception_during_execution_returns_error_result` — regression guard for the **no-`on_error`** path. State has no `on_error`, so the new `try/except` re-raises, top-level handler sets `terminated_by == "error"`. Must continue passing unchanged. [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py:3378-3405` `TestInterpolationErrorHandling.test_missing_context_variable_produces_friendly_message` — regression guard for the friendly `--context` message when no `on_error` is set. Must continue passing because the test state has no `on_error` (so `InterpolationError` still reaches `executor.py:355`). [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py:1250-1278` `TestEvents.test_events_emitted` — asserts on `action_start`, `action_complete`, `evaluate`, `route`, etc. event names. A success-path test, so `action_error` won't appear — no regression. Use as the template for the new `action_error` event-emission assertion. [Agent 3 finding]

### Tests (Likely To Break — Must Update)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_errors.py:306` `test_missing_context_input_clear_error` — **breaks after fix**. Loop YAML defines `on_error: failed` (terminal) with `${context.input}` in the action. Today `InterpolationError` raises out of `_run_action`, is caught by top-level `except InterpolationError` at `executor.py:355`, emits the friendly `--context` stderr message, exits with `result == 1`. After the fix, the new `try/except` in `_execute_state` catches `InterpolationError` first and routes to `on_error: failed` (terminal) → `terminated_by == "terminal"`, exit code `0`. Both assertions (`assert result == 1`; stderr contains `--context`) will fail. Decide whether to (a) remove `on_error: failed` from the test YAML to preserve the `--context` UX path, or (b) update the test to assert the new routing behavior. Recommend (a) — the friendly interpolation-error message is a distinct UX guarantee worth preserving when the loop opts out of catching it. [Agent 3 finding]

### Tests (New — To Write)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — new `TestActionExceptionRouting` class (place near `TestSignalHandling` at ~line 2041 or `TestErrorHandling` at ~line 1884). Cover the six cases identified by Agent 3:
  1. Exception in Branch C (evaluated-action path, line 478) with `on_error` set → routes to `on_error`, `final_state == "<on_error target>"`.
  2. Exception in Branch C with **no** `on_error` → re-raises; `terminated_by == "error"` (regression parity with line 1884 test).
  3. Exception in Branch B (`state.next` path, line 457) with `on_error` set → routes to `on_error`, **not** to `state.next`; assert `state.next` target was never executed (use `mock_runner.calls` pattern from `test_sigkill_on_next_state_routes_via_on_error_if_configured`).
  4. `action_error` event emitted on routed path with payload `{"state": ..., "error": ..., "route": "on_error"}`; use `event_callback=events.append` pattern from `test_rate_limit_exhausted_event_emitted` at line 4388.
  5. `InterpolationError` from action-template interpolation (`executor.py:552`) with `on_error` set → routes to `on_error`; friendly `--context` message is **not** emitted (companion to the existing `test_missing_context_variable_produces_friendly_message`).
  6. `on_error` template interpolation (e.g., `on_error: "${ctx.fallback}"`) correctly resolved via `interpolate(state.on_error, ctx)`. [Agent 3 finding]
- **MockActionRunner extension**: existing `MockActionRunner` at `test_fsm_executor.py:30-92` has no raise support. Follow the inline `FailingRunner` pattern at `test_fsm_executor.py:1898-1910` (used by `test_exception_during_execution_returns_error_result`) — define a small inline class whose `run()` raises, pass as `action_runner=RaisingRunner()`. Alternatively use `monkeypatch.setattr(executor, "_run_action", ...)`. [Agent 3 finding]

### Mock Harness
- `scripts/tests/test_fsm_executor.py:30-92` `MockActionRunner` — extend (subclass inline or add an `raise_on` field) to simulate `_run_action` raising. Alternatively use `monkeypatch.setattr(executor, "_run_action", raising_stub)` for finer control.

### Documentation
- `docs/ARCHITECTURE.md` — FSM executor lifecycle and error handling design; update the error-routing description to reflect that `on_error` now also catches action exceptions, not just non-zero exits and sub-loop errors.
- `docs/reference/API.md` — `StateConfig.on_error` and `FSMExecutor` internals sections (~line 3838-3844, 4052-4138); document that action-level Python exceptions now route to `on_error` when set.
- `docs/guides/LOOPS_GUIDE.md` — on_error routing semantics for loop authors; add a note that action exceptions are now catchable.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md` — add `### action_error` section under the FSM Executor subsection (currently lists 14 bare-name FSM executor events in sequential order). This doc is the authoritative event catalog and must be updated **before** `ll-generate-schemas` is run (per CONTRIBUTING.md lines 549–563). Document payload fields: `state` (the state name whose action raised), `error` (string form of the exception), `route` (always `"on_error"` when emitted). [Agent 2 finding]
- `docs/generalized-fsm-loop.md:451` — existing `on_error` precedence note scopes the behavior to "shell action exits non-zero"; update to also cover raised Python exceptions from non-shell action paths (evaluate/prompt/mcp). [Agent 2 finding]

### Configuration / Schema
- No changes needed. `StateConfig.on_error: str | None` in `scripts/little_loops/fsm/schema.py:236` already supports this; behavior is purely additive.

### Related Completed Work
- `.issues/completed/P3-BUG-940-fsm-on-error-dead-code-when-next-also-defined.md` — prior fix for `on_error` reachability when `next` was also defined. This enhancement extends that work to the exception path.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | FSM executor lifecycle and error handling design |
| architecture | docs/reference/API.md | `StateConfig.on_error`, `FSMExecutor` internals, `_execute_state` behavior |

## Labels

`enhancement`, `fsm`, `error-handling`, `executor`, `captured`

---

## Status

**Completed** | Created: 2026-04-18 | Completed: 2026-04-18 | Priority: P3

## Resolution

Wrapped the two `_run_action` call sites in `_execute_state` (Branch B at line 457 and Branch C at line 478) with a shared `_run_action_or_route` helper in `scripts/little_loops/fsm/executor.py`. Exceptions raised from `_run_action` now route to `state.on_error` (via `interpolate(state.on_error, ctx)`) when defined, emitting an `action_error` event with `{state, error, route: "on_error"}`. When no `on_error` is configured, the exception is re-raised — preserving the existing top-level error termination and the friendly `--context` message for missing interpolation variables.

### Changes
- `scripts/little_loops/fsm/executor.py` — added `_run_action_or_route` helper; updated both call sites.
- `scripts/little_loops/generate_schemas.py` — added `action_error` schema, bumped count 22 → 23.
- `docs/reference/schemas/action_error.json` — generated.
- `docs/reference/EVENT-SCHEMA.md` — new `### action_error` section, updated listing + event-to-source table.
- `docs/generalized-fsm-loop.md` — expanded the `on_error` precedence note to include raised exceptions.
- `scripts/tests/test_fsm_executor.py` — added `TestActionExceptionRouting` with 6 cases (Branch B, Branch C, no-on_error re-raise, event emission, InterpolationError routing, interpolated on_error target).
- `scripts/tests/test_generate_schemas.py` — bumped count assertions 22 → 23, added `"action_error"` to expected set.

### Verification
- Full test suite: 4973 passed, 5 skipped.
- mypy: clean on modified file.
- ruff: clean on modified files.

### Notes
- `test_missing_context_input_clear_error` (in `scripts/tests/test_ll_loop_errors.py`) was predicted to break by the wiring analysis but did not — it still passes. No change needed there.
- Per wiring step 12, inlined the `"action_error"` string literal rather than defining a named constant; no re-export needed in `scripts/little_loops/fsm/__init__.py`.
- Skipped optional wiring items 10 (ARCHITECTURE.md / API.md / LOOPS_GUIDE.md polish) and 11 (CLI renderers) — these are additive docs/UX and not on the correctness path.

## Session Log
- `/ll:ready-issue` - 2026-04-18T20:51:32 - `5c5bb8fb-3ecb-45f7-9cd0-f674b644124e.jsonl`
- `/ll:confidence-check` - 2026-04-18T21:00:00Z - `bda158c4-d7b8-4d82-9b6a-d835faf6e66e.jsonl`
- `/ll:wire-issue` - 2026-04-18T20:29:46 - `ab781961-a8c6-4915-8190-7c4fd3723052.jsonl`
- `/ll:refine-issue` - 2026-04-18T20:16:20 - `bc00f492-dc6a-41a8-aaba-c4d008a3652e.jsonl`
- `/ll:capture-issue` - 2026-04-18T19:59:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4165baeb-7bcd-4b9f-99ed-2cf4c171d21e.jsonl`
- `/ll:manage-issue` - 2026-04-18T22:00:00Z - `0acc05ca-0e56-4d0d-b243-afd1e09ac0f8.jsonl`
