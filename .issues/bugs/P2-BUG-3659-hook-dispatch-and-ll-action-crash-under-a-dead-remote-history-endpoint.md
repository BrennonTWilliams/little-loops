---
id: BUG-3659
type: BUG
title: Hook dispatch and ll-action crash under a dead remote history endpoint
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T06:51:55Z'
---

# BUG-3659: Hook dispatch and ll-action crash under a dead remote history endpoint

## Summary

Under `history.backend.provider: libsql`, a dead or unreachable remote endpoint makes every hook dispatch crash after its handler has run, and makes `ll-action` exit before the skill runs. `record_hook_event` and `skill_event_context` catch only `sqlite3.Error`, but remote failures surface as `HistoryError` subclasses (`HranaUnavailable`, then `HistorySuppressed` for the 60 s unreachable window), which are not `sqlite3.Error`.

## Current Behavior

- `hooks/__init__.py:main_hooks` (`:234`) wraps every handler in `hook_event_context` when `analytics.enabled` and `analytics.capture.hooks` hold, with no outer guard. `hook_event_context` calls `record_hook_event` in its `finally`. Its connect and insert handlers (`session_store/writers.py:807`, `:836`) catch only `sqlite3.Error`, so a `HranaUnavailable` from `conn.execute` propagates out of the `with`. The handler already ran, but `result.stdout` (for example PreToolUse decision JSON) and `result.feedback` are never written, and the hook process exits with a traceback.
- For `UNREACHABLE_TTL_S` (60 s) after the first failure, `LibsqlConnection` raises `HistorySuppressed` on every telemetry `execute` before any network call, so every hook fire in that window crashes the same way.
- `skill_event_context`'s enter handler (`writers.py:733`) catches only `sqlite3.Error`, so the exception escapes before `yield`. `cli/action.py:232` (`ll-action`) never runs the skill. The exit-update handler (`:766`) has the same gap.
- Verified 2026-09-29 against `HranaStub` after `remote.stop()`: `hook_event_context` raised `HranaUnavailable` after the body ran; `skill_event_context` raised `HranaUnavailable` before the body ran.
- Why no test caught it: `test_remote_hooks.py::TestPostToolUse::test_a_dead_endpoint_never_fails_the_hook` (`:134`) calls `post_tool_use.handle()` directly, bypassing the dispatcher and `hook_event_context`.

## Steps to Reproduce

1. Configure `history.backend.provider: libsql` with a remote endpoint, and enable `analytics.enabled` and `analytics.capture.hooks`.
2. Make the endpoint unreachable (stop the remote, or point it at a closed port). The test route is `HranaStub` followed by `remote.stop()`.
3. Fire any hook through the dispatcher, for example `main_hooks` with a PreToolUse intent and stdin JSON. The handler runs, then the process exits with a `HranaUnavailable` traceback and its stdout decision JSON is never written.
4. Fire a second hook within 60 s. It crashes the same way, with `HistorySuppressed` and no network call.
5. Run `ll-action <skill>`. It exits with `HranaUnavailable` before the skill runs.

## Expected Behavior

A dead, slow or suppressed remote history endpoint never changes a hook's exit code, stdout or feedback, and never stops `ll-action` from running the skill. The telemetry row is skipped: `HistorySuppressed` is logged at debug with no traceback, and other `HistoryError`s are logged once as a warning.

## Motivation

Hooks run on every tool call. During any remote outage, every libsql user with hook telemetry enabled loses hook output, including PreToolUse permission decisions, for at least 60 s per outage. The fix is small and independent of the `resolve_history_db` caller audit (BUG-3652), so it should not wait behind that work.

## Proposed Solution

1. In `session_store/writers.py`, add a module constant `_DEGRADE_ERRORS = (sqlite3.Error, HistoryError)`. BUG-3652 reuses it for the remaining fail-soft writers.
2. `record_hook_event` (connect and insert handlers) and `skill_event_context` (enter and exit-update handlers) catch `_DEGRADE_ERRORS`. Log `HistorySuppressed` at debug with no traceback and other errors as a warning, mirroring `cli_event_context`'s `(logger.debug if isinstance(exc, HistorySuppressed) else logger.warning)` shape.
3. Defense in depth in `main_hooks`: an exception raised by the telemetry wrap itself (not by the handler) must not stop `result.stdout` and `result.feedback` from being written or change the exit code. The handler's own exceptions keep propagating as today.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/writers.py`: add `_DEGRADE_ERRORS`; widen `record_hook_event` (connect and insert handlers) and `skill_event_context` (enter and exit-update handlers).
- `scripts/little_loops/hooks/__init__.py`: `main_hooks`, the `hook_event_context` wrap.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/action.py:232`: `ll-action`, the only `skill_event_context` caller. No edit needed.
- `hook_event_context` has one caller, `main_hooks`. Every intent in `_dispatch_table()` is affected.

### Similar Patterns
- `writers.py:cli_event_context` already catches `Exception` on enter and exit, and debug-logs `HistorySuppressed`. That is the template.

### Tests
- `scripts/tests/test_remote_hooks.py`: new dispatcher-level and `ll-action` dead-endpoint cases.
- `scripts/tests/test_remote_ingestion_telemetry.py::TestBestEffortNeverAborts`: covers only `cli_event_context` today; pattern reference.

### Documentation
- None required. Optionally, add to `docs/reference/CONFIGURATION.md` § `Remote history backend` that hook telemetry skips silently while the endpoint is unreachable.

### Configuration
- N/A

## Program Design

### Types

- `_DEGRADE_ERRORS: tuple[type[Exception], ...]` — `(sqlite3.Error, HistoryError)`, module constant in `session_store/writers.py`

### Signatures

- `record_hook_event(...) -> None` — connect and insert handlers catch `_DEGRADE_ERRORS`; `HistorySuppressed` logs at debug, other errors at warning
- `skill_event_context(...) -> Iterator[...]` — enter and exit-update handlers catch `_DEGRADE_ERRORS`, same logging split
- `main_hooks() -> int` — a failure raised by the `hook_event_context` wrap itself is swallowed after `result` is bound; the handler's own exceptions still propagate

### Call Path

`main_hooks` -> `hook_event_context` -> `record_hook_event` -> `_connect_telemetry`

`cmd_invoke` -> `skill_event_context` -> `_connect_telemetry`

## Implementation Steps

1. Add `_DEGRADE_ERRORS` and widen the four handlers.
2. Restructure the `main_hooks` wrap so the recorded telemetry failure is swallowed after `result` is bound.
3. Tests (new cases in `test_remote_hooks.py`, reusing its `remote` fixture):
   - Drive `main_hooks` through the dispatcher (argv intent plus stdin JSON) with analytics and hook capture enabled and a stopped stub. Assert the handler's stdout reaches stdout, the exit code is the handler's, and stderr has no `Traceback` and no token sentinel.
   - Fire a second hook inside the 60 s `HistorySuppressed` window with the same assertions.
   - `ll-action` against a stopped stub runs the skill (mock the runner) and returns its exit code.
   - Local-store twin: a hook row is still written on the happy path.

## Impact

- **Priority**: P2. It affects only opt-in remote-backend users with hook telemetry on, but it breaks every hook during an outage.
- **Effort**: Small.
- **Risk**: Low. The change only widens exception handlers and guards telemetry.

## Root Cause

- **File**: `scripts/little_loops/session_store/writers.py`
- **Anchor**: `in function record_hook_event()` and `in function skill_event_context()`
- **Cause**: FEAT-3535 routed these writers through `_connect_telemetry`, which can return a remote `LibsqlConnection`, but their best-effort handlers still catch only `sqlite3.Error`. `HistoryError` subclasses `Exception` directly, not `sqlite3.Error`.

## Acceptance Criteria

- [ ] `main_hooks` under a stopped stub (analytics and hook capture on) writes the handler's stdout and feedback, returns the handler's exit code, and prints no `Traceback`.
- [ ] Same result for a second fire inside the unreachable window (`HistorySuppressed`), which sends no stub request.
- [ ] `ll-action` under a stopped stub runs the skill and returns its exit code.
- [ ] `_DEGRADE_ERRORS` exists in `writers.py` and is used by `record_hook_event` and `skill_event_context`.
- [ ] Local SQLite behavior is unchanged; `python -m pytest scripts/tests/` passes.

## Related

- BUG-3652: found during its pre-implementation review. Land this issue first; BUG-3652 then widens the remaining fail-soft writers using `_DEGRADE_ERRORS`.
- FEAT-3535: remote libSQL history backend.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-29T15:34:43 - `6038439a-4a88-4017-a873-b730adce0fef.jsonl`
- `/ll:format-issue` - 2026-09-29T15:33:38 - `9a90bf56-499f-485e-aa0b-df712bf8e9cd.jsonl`
- `/ll:capture-issue` - 2026-09-29T06:52:01 - `5f8d5762-5341-43fe-88c8-0e9ad90d90b3.jsonl`
