---
id: BUG-3659
type: BUG
title: Hook dispatch and ll-action crash under a dead remote history endpoint
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T06:51:55Z'
completed_at: '2026-09-29T15:57:28Z'
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- Anchor drift: `main_hooks` is defined at `scripts/little_loops/hooks/__init__.py:198`; the `hook_event_context` wrap is at `:238-249` (the `:234` citation above now lands on the `LLHookEvent(...)` close paren). `result` is bound inside the `with` body at `:248`, so an exception from the wrap's `__exit__` (the `record_hook_event` call in `hook_event_context`'s `finally`, `writers.py:891-903`) arrives after `result` is bound, while a handler exception arrives with `result` unbound. That difference is what lets a guard swallow only telemetry failures.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/writers.py:hook_event_context` (`finally`, `:891-903`) — `record_hook_event` runs in an unguarded `finally`. If it raises while the handler's own exception propagates, the new exception replaces it (handler's survives only as `__context__`). A guard placed only in `main_hooks` cannot tell the two apart; guard the `finally` call itself (or check `result` is bound) so the handler's exception keeps propagating. [Agent 2 finding]
- `scripts/little_loops/session_store/writers.py:skill_event_context` — the exit `finally` has an unguarded `conn.close()`, and `resolve_history_store` plus the config gate sit in an unguarded prefix before the enter `try`. Widening the enter/exit-update handlers does not cover these. [Agent 2 finding]
- `scripts/little_loops/hooks/__init__.py` module docstring (`:44`, "The wrap is best-effort and never alters the handler's exit code or exception propagation") and `scripts/little_loops/hooks/post_tool_use.py:12` ("the `__init__.main_hooks` dispatcher has no try/except") — in-code prose that goes stale once `main_hooks` gains a guard. [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/action.py:232`: `ll-action`, the only `skill_event_context` caller. No edit needed.
- `hook_event_context` has one caller, `main_hooks`. Every intent in `_dispatch_table()` is affected.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/session.py:1215` (`record-hook-event` branch) and `hooks/scripts/record-hook-event.sh:57` — second `record_hook_event` caller. Already wrapped in `except Exception` and `|| true`, so it stays safe; no edit, but it inherits the widened handler. [Agent 1 finding]
- `scripts/little_loops/hooks/__main__.py:6` — `raise SystemExit(main_hooks())`, the only `main_hooks` entry point. Reached via every adapter shim: `hooks/adapters/claude-code/*.sh` (`pre-tool-use.sh` uses exit 2 as the block signal), `scripts/little_loops/hooks/adapters/{codex,gemini,kimi,qwen}/*.sh`, `hooks/hooks.json`, and `hooks/adapters/opencode/index.ts:spawnIntent` (throws on exit 2 in `session.created` and on any non-0/2 exit in `session.compacted`, so today's crash exit 1 surfaces there as a thrown error). [Agent 1, Agent 2 findings]
- `scripts/little_loops/loops/migrate-sdk-version.yaml` and `scripts/little_loops/loops/assumption-firewall.yaml` — shell out to `ll-action invoke explore-api` with `check=False` and ignore its exit code; an `ll-action` that exits before the skill runs silently skips the learning-test record. Fixed by this issue, no edit needed. [Agent 2 finding]
- `scripts/little_loops/cli/advise.py` — additional `cmd_invoke` consumer. [Agent 1 finding]
- `scripts/little_loops/session_store/backend.py:56` defines `HistoryError`; `writers.py:36-38` already imports `HistoryError` and `HistorySuppressed` and `writers.py:21` imports `sqlite3`. No new import and no circular-import risk for `_DEGRADE_ERRORS`. [Agent 1 finding]
- Not covered by `_DEGRADE_ERRORS`: `hrana.normalize_url` raises a plain `ValueError` for a malformed `history.backend.url`, and it escapes the connect handler on the `_connect_telemetry` route. Out of scope for this bug, but the `main_hooks` defense-in-depth guard is what protects hooks from it. [Agent 2 finding]
- Sibling writers with the same `except sqlite3.Error`-only gap, for BUG-3652 (do not change here): `record_session_lifecycle_event`, `record_context_pressure_event`, `write_advisor_consult`, `write_research_triage`, `write_credential_scope`, `record_subagent_run_start`, `record_subagent_run_stop`, `reconcile_stale_subagent_runs`. Hook-called writers with no guard at all: `record_correction` and `record_skill_event` (`hooks/user_prompt_submit.py`), `write_file_event` (`hooks/post_tool_use.py`). [Agent 2 finding]

### Similar Patterns
- `writers.py:cli_event_context` already catches `Exception` on enter and exit, and debug-logs `HistorySuppressed`. That is the template.

### Tests
- `scripts/tests/test_remote_hooks.py`: new dispatcher-level and `ll-action` dead-endpoint cases.
- `scripts/tests/test_remote_ingestion_telemetry.py::TestBestEffortNeverAborts`: covers only `cli_event_context` today; pattern reference.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_intents.py::TestHooksMainModule::test_record_hook_event_in_dispatch` — template for the in-process `main_hooks` test (writes `{"analytics": {"enabled": true, "capture": {"hooks": true}}}`, stubs `_dispatch_table`, sets `sys.argv` and `sys.stdin`, `monkeypatch.chdir(tmp_path)`). A stub handler can return `LLHookResult(exit_code=N, stdout=..., feedback=...)`. Also the happy-path regression guard for the `main_hooks` restructure. [Agent 3 finding]
- `scripts/tests/test_hook_usage_stop.py::test_dispatcher_does_not_open_hook_telemetry` — pins the `intent != "usage_stop"` short-circuit ahead of `_hooks_telemetry_enabled`; keep it intact when restructuring `main_hooks`. [Agent 3 finding]
- `scripts/tests/test_remote_hooks.py::remote` fixture (`:28`) — writes only `history.backend` to `ll-config.json`, so `_hooks_telemetry_enabled` returns False against it. New `main_hooks` cases must add `analytics.enabled` and `analytics.capture.hooks` (plus `telemetry_timeout_ms` to keep a dead endpoint fast), then call `db_mod.clear_backend_config_cache()`. Model on `TestPostToolUse::test_writes_the_tool_event_to_the_remote_store`. [Agent 3 finding]
- `scripts/tests/test_remote_hooks.py` — suppression-window case: with the stub already stopped, `remote.requests` cannot grow, so "no stub request" is unassertable. Force `HistorySuppressed` with `remote_telemetry.mark_unreachable(remote.url)` (marker is per `.ll/` dir, so tests do not bleed), or use a live stub with `remote.delay` for a real first failure as in `test_a_failure_writes_an_unreachable_marker_and_later_writes_skip`. [Agent 3 finding]
- `scripts/tests/test_remote_hooks.py` (or `test_session_store_writers.py`) — direct `record_hook_event` / `skill_event_context` cases against a stopped stub with `caplog` at DEBUG: `HistorySuppressed` yields a DEBUG record with falsy `exc_info`; other `HistoryError`s yield one WARNING; assert `TOKEN` absent from messages. No existing test asserts on `exc_info` or the debug/warning split, so `record.exc_info` must be read directly. Cover the `skill_event_context` exit-update handler by stopping the stub or calling `mark_unreachable` inside the body. [Agent 3 finding]
- `scripts/tests/test_action.py::TestCmdInvokeStreamJson` — pattern for the `ll-action` case: `_make_namespace(...)`, `patch("little_loops.subprocess_utils.run_claude_command", return_value=_make_completed(N))`, assert the mock was called and `cmd_invoke(args)` returns N. The `remote` fixture lives in `test_remote_hooks.py`, so the new case belongs there or must import it. [Agent 3 finding]
- Local-twin regression guards that must keep passing (they rely on `sqlite3.Error` staying in `_DEGRADE_ERRORS`): `scripts/tests/test_session_store_writers.py::TestRecordHookEvent::test_best_effort_on_unopenable_db`, `TestHookEventContext::test_best_effort_on_unopenable_db`, `TestHookEventContext::test_raise_path_records_exit_code_one_and_propagates`, `TestSkillEventContext::test_best_effort_on_unopenable_db`, and `scripts/tests/test_action.py` `test_best_effort_on_unopenable_db` (verdict and review-event classes). [Agent 1, Agent 3 findings]
- `scripts/tests/test_history_target_hook_audit.py::test_hook_path_reaches_resolve_once[main_hooks]` — drives `hook_event_context` under a `_resolve_once` spy; confirm the restructure keeps it reaching the resolver once. [Agent 3 finding]
- No existing test breaks: nothing asserts the `sqlite3.Error`-only handling or the log strings `record_hook_event: connect failed`, `record_hook_event: insert failed`, `skill_event_context: insert failed`, `skill_event_context: update failed`. [Agent 1, Agent 3 findings]
- New coverage gaps: no dispatcher-level test against a libsql store; no `capsys` assertion on `main_hooks` output; no `hook_events` or `skill_events` row asserted in a remote stub; no test that a non-`sqlite3.Error` from the connect or execute path is swallowed. [Agent 3 finding]

### Documentation
- None required. Optionally, add to `docs/reference/CONFIGURATION.md` § `Remote history backend` that hook telemetry skips silently while the endpoint is unreachable.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` § `record_hook_event` — "Best-effort: a missing/locked database logs and returns rather than raising"; add unreachable remote endpoint. [Agent 2 finding]
- `docs/reference/API.md` § `hook_event_context` and § `skill_event_context` — best-effort sentences ("never alters the wrapped hook's exit code or exception propagation", "never blocks the wrapped skill body"); add a clause for remote errors. § `cli_event_context` is the wording template. [Agent 2 finding]
- `docs/reference/API.md` `HistoryError` / `translate_sqlite_errors` section (~`:9987-9990`) — "a best-effort writer that used to catch `sqlite3.Error` catches `HistoryError` instead"; mention `_DEGRADE_ERRORS` as the shared tuple. [Agent 1, Agent 2 findings]
- `docs/reference/CONFIGURATION.md:738` § `Remote history backend`, "Never stalls a hook" bullet — describes the 60 s `.ll/libsql-<hash>.unreachable.lock` marker and "Dropped telemetry is not buffered or replayed"; the optional sentence belongs here. [Agent 1, Agent 2 findings]
- No edit needed: `docs/guides/BUILTIN_HOOKS_GUIDE.md` (shim section is about the bash shim), `docs/ARCHITECTURE.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/HOST_COMPATIBILITY.md`. [Agent 2 finding]

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Guard the `record_hook_event` call in `hook_event_context`'s `finally` (or check in `main_hooks` that `result` is bound) so a telemetry failure cannot replace a propagating handler exception; `writers.py:hook_event_context`
- Guard `skill_event_context`'s unguarded prefix (`resolve_history_store`, config gate) and exit-`finally` `conn.close()` in `writers.py`, not only the enter and exit-update handlers
- Update the `hooks/__init__.py` module docstring and `hooks/post_tool_use.py:12` ("dispatcher has no try/except") to match the new guard
- Update `docs/reference/API.md` § `record_hook_event`, `hook_event_context`, `skill_event_context`, and the `HistoryError` best-effort paragraph; add the optional sentence to `docs/reference/CONFIGURATION.md:738`
- New tests in `scripts/tests/test_remote_hooks.py`: extend the `remote` fixture config with `analytics.enabled` and `analytics.capture.hooks`, force the suppression window with `remote_telemetry.mark_unreachable(remote.url)`, and assert on `caplog` record level and `exc_info` directly
- Keep `test_hook_usage_stop.py::test_dispatcher_does_not_open_hook_telemetry` and `test_hook_intents.py::test_record_hook_event_in_dispatch` green when restructuring `main_hooks`

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

## Resolution

Fixed 2026-09-29. Added `_DEGRADE_ERRORS`/`_log_degraded` in `session_store/writers.py`; `record_hook_event` and `skill_event_context` (setup, enter, exit-update, close) now degrade on remote `HistoryError`s (debug for `HistorySuppressed`, one warning otherwise). `hook_event_context` guards its `record_hook_event` call so it cannot replace a handler exception, and `main_hooks` swallows a wrap failure once the handler has finished. Tests: `test_remote_hooks.py::TestDeadEndpointDegrades`. Full suite: 27539 passed.

## Status

**Open** | Created: 2026-09-29 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-29T15:57:28 - `0aeb51ea-248a-4c27-a531-ab2676055a68.jsonl`
- `/ll:ready-issue` - 2026-09-29T15:48:58 - `db4cb08b-d09f-47f5-b858-0d644403de90.jsonl`
- `/ll:confidence-check` - 2026-09-29T15:46:03 - `b9f63681-22db-44ce-ad41-11a9e55eecc2.jsonl`
- `/ll:verify-issues` - 2026-09-29T15:44:48 - `940ad7ce-416b-4a9d-93ee-b729c7bab54f.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-29T15:43:04 - `b286ef2e-43a0-42ba-b50e-dd67b7f3b73e.jsonl`
- `/ll:verify-issues` - 2026-09-29T15:42:12 - `0e078dec-faf0-4ff3-87ed-dcbdd276697c.jsonl`
- `/ll:wire-issue` - 2026-09-29T15:40:24 - `f3f502cb-ad8a-484f-9e72-65b0f5fb4d73.jsonl`
- `/ll:refine-issue` - 2026-09-29T15:34:43 - `6038439a-4a88-4017-a873-b730adce0fef.jsonl`
- `/ll:format-issue` - 2026-09-29T15:33:38 - `9a90bf56-499f-485e-aa0b-df712bf8e9cd.jsonl`
- `/ll:capture-issue` - 2026-09-29T06:52:01 - `5f8d5762-5341-43fe-88c8-0e9ad90d90b3.jsonl`
