---
id: FEAT-1323
priority: P5
size: Medium
confidence_score: 100
outcome_confidence: 60
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
completed_at: 2026-05-02T16:40:58Z
status: done
---

# FEAT-1323: Transport CLI Wiring Pass and Documentation

## Summary

Wire `wire_transports()` at all four CLI entry points, add teardown via `close_transports()`, update public exports, fix affected test fixtures, and write the four documentation updates. This is the wiring half of the FEAT-918 split and requires FEAT-1322 to be merged first.

## Current Behavior

None of the four CLI entry points (`run.py`, `lifecycle.py`, `parallel.py`, `sprint/run.py`) call `wire_transports()` or `close_transports()`. Any `events.transports` configuration in `.ll/ll-config.json` is silently ignored — events never flow through transports regardless of config.

Public-API exports for `wire_transports` and `EventsConfig` are **already in place** as part of FEAT-1322 (`scripts/little_loops/__init__.py:33,62` and `scripts/little_loops/config/__init__.py:37,68`); no further export work is required.

## Parent Issue

Decomposed from FEAT-918: Transport Protocol Foundation and JsonlTransport

## Context

FEAT-918 scored 11/11 on the size heuristic. The confidence check recommended splitting into two commits: (1) core module + refactor, (2) CLI wiring pass. This issue is part 2.

After FEAT-1322 ships: `Transport`, `JsonlTransport`, `wire_transports()`, `EventsConfig`, and `BRConfig.events` are all available. This issue hooks them up at the CLI layer and documents the complete feature.

## Expected Behavior

- `wire_transports(bus, config.events)` called after `wire_extensions()` at all four CLI entry points: `run.py`, `lifecycle.py`, `parallel.py`, `sprint/run.py`.
- `close_transports()` called in `run.py` `finally` block (before `lock_manager.release()`), in a new `lifecycle.py` `try/finally`, and in `ParallelOrchestrator._cleanup()`.
- All four documentation files updated to reflect the multi-transport model.

(`wire_transports` and `EventsConfig` are already exported as of FEAT-1322 — no export work in this issue.)

## Motivation

FEAT-1322 delivers the transport protocol and `JsonlTransport` implementation, but without CLI wiring the transport layer is inert: `events.transports` config entries are silently ignored, and all downstream transport features (FEAT-1314 WebhookTransport, FEAT-1312 OTelTransport, FEAT-1313 UnixSocketTransport) are blocked until entry-point wiring is in place. This issue closes the gap between "transport exists" and "transport runs."

## Proposed Solution

7. Wire transports at all four CLI entry points and add teardown:
   - `run.py:334` — `wire_transports(executor.event_bus, config.events)` after `wire_extensions`; `executor.close_transports()` inside `finally:` (line 343) before `lock_manager.release()` (line 344).
   - `lifecycle.py:266` — `wire_transports()` after `wire_extensions()`; wrap from line 261 through end of resume call in `try/finally` so `close_transports()` runs on exit/exception.
   - `parallel.py:229` — `wire_transports(event_bus, config.events)` after `wire_extensions` (line 228); teardown handled by orchestrator.
   - `sprint/run.py:403` — per-wave `wire_transports(event_bus, config.events)` after `wire_extensions` (line 403); teardown handled by orchestrator.
   - `orchestrator.py:_cleanup()` (lines 1301–1314) — `self._event_bus.close_transports()` after `merge_coordinator.shutdown()`.

8. (wiring) ~~Update `scripts/little_loops/config/__init__.py` — add `EventsConfig`~~ — **already done in FEAT-1322** (`scripts/little_loops/config/__init__.py:37,68`).
9. (wiring) ~~Update `scripts/little_loops/__init__.py` — add `wire_transports`~~ — **already done in FEAT-1322** (`scripts/little_loops/__init__.py:33,62`).
10. (wiring) Fix `test_cli_loop_lifecycle.py` `TestCmdResumeCircuitWiring` fixtures (`test_cmd_resume_wires_circuit_when_enabled` at line 1032, `test_cmd_resume_passes_none_when_disabled` at line 1068) — set `mock_config.events = MagicMock(transports=[])` after the existing `mock_config.extensions = {}` (line 1050 / line 1084), and add `patch("little_loops.transport.wire_transports")` alongside the existing `patch("little_loops.extension.wire_extensions")` (lines 1057 / 1091). Patch at module-of-definition (`little_loops.transport.wire_transports`), matching the convention used for `wire_extensions`.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/run.py:334` — `wire_transports()` after `wire_extensions`; `close_transports()` in `finally` before `lock_manager.release()`
- `scripts/little_loops/cli/loop/lifecycle.py:266` — `wire_transports()` after `wire_extensions()`; add `try/finally` wrapper (lines 261–279) for teardown
- `scripts/little_loops/cli/parallel.py:229` — `wire_transports(event_bus, config.events)` after `wire_extensions` (line 228)
- `scripts/little_loops/cli/sprint/run.py:403` — per-wave `wire_transports(event_bus, config.events)` after `wire_extensions` (line 403)
- `scripts/little_loops/parallel/orchestrator.py:_cleanup()` — `self._event_bus.close_transports()` inside `_cleanup()` (lines 1301–1314) after `merge_coordinator.shutdown(wait=True, timeout=30)` at line 1310 and before the `if not self._shutdown_requested:` guard at line 1313 — flush regardless of interrupt state.
- ~~`scripts/little_loops/config/__init__.py`~~ — already exports `EventsConfig` (FEAT-1322 — line 37 import, line 68 `__all__`).
- ~~`scripts/little_loops/__init__.py`~~ — already exports `wire_transports` (FEAT-1322 — line 33 import, line 62 `__all__`).

### Tests

- `scripts/tests/test_orchestrator.py` — add `_cleanup()` test asserting `close_transports()` is called via injected mock `EventBus`; cover `_event_bus=None` guard
- `scripts/tests/test_cli_loop_lifecycle.py` — assert `wire_transports` called in `cmd_resume`; assert `close_transports()` runs in new `finally`; fix `TestCmdResumeCircuitWiring` fixtures at lines 1032 and 1068

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_worktree.py` — `TestCmdRunWithWorktree.test_worktree_atexit_registration` and `test_worktree_path_name_format` will break: add `patch("little_loops.transport.wire_transports")` and `mock_cfg.return_value.events = MagicMock(transports=[])` alongside existing `BRConfig` patch [Agent 3 finding]
- `scripts/tests/test_cli_loop_queue.py` — `TestQueueRetryOnRace` already patches `wire_extensions`; add parallel `patch("little_loops.transport.wire_transports")` to prevent failure when `wire_transports` is wired into `cmd_run` [Agent 3 finding]
- `scripts/tests/test_cli_loop_lifecycle.py:TestCmdResume`, `TestCmdResumeBackground`, `TestCmdResumeExitCodes` — call `cmd_resume` with real `BRConfig`; verify `config.events.transports` resolves safely from real project config, or add `patch("little_loops.transport.wire_transports")` to these classes [Agent 3 finding]
- `scripts/tests/test_sprint_integration.py` — multi-wave tests using `MockOrchestrator`: `wire_transports` call in `_cmd_sprint_run` runs before the mock is active; add `patch("little_loops.transport.wire_transports")` to multi-wave test setup [Agent 3 finding]
- `scripts/tests/test_cli_e2e.py` — `TestParallelExecution.test_ll_parallel_dry_run`: calls `main_parallel` without patching `wire_transports`; add `patch("little_loops.transport.wire_transports")` alongside existing mocks [Agent 3 finding]
- `scripts/tests/test_cli_loop_queue.py` or `test_cli_loop_lifecycle.py` — **new test**: assert `wire_transports(executor.event_bus, config.events)` called in `cmd_run` (`run.py`); follow `TestCmdResumeCircuitWiring` patch pattern [Agent 3 finding]
- `scripts/tests/test_cli_e2e.py` or new `test_cli_parallel.py` — **new test**: assert `wire_transports(event_bus, config.events)` called in `main_parallel` (`parallel.py`) [Agent 3 finding]
- `scripts/tests/test_sprint_integration.py` — **new test**: assert `wire_transports(event_bus, config.events)` called per-wave in `_cmd_sprint_run` (`sprint/run.py`) [Agent 3 finding]

### Documentation

- `docs/reference/API.md` — document `Transport` Protocol and `EventBus.add_transport()` / `close_transports()`
- `docs/ARCHITECTURE.md` — note the multi-transport fan-out model (foundation only; webhook/OTel/socket listed when they land)
- `docs/reference/CONFIGURATION.md` — add `events.transports` block after `extensions` (line 608)
- `docs/reference/EVENT-SCHEMA.md` — annotate the `loop_resume` bypass fix in the transport-behavior section (net-new section required)

_Wiring pass added by `/ll:wire-issue`:_
- ~~`docs/reference/CONFIGURATION.md`~~ — `events.transports` section already added by FEAT-1322 (verified at line 745); no new content needed — mark as done [Agent 2 finding]
- `docs/reference/API.md` — transport section already written by FEAT-1322 (`## little_loops.transport` describes `wire_transports`, `Transport`, `close_transports`); after wiring, verify the forward-looking "Called by CLI entry points" claim is now accurate [Agent 2 finding]
- `docs/ARCHITECTURE.md` — specifically the CLI entry point table in `## Extension Architecture & Event Flow` (line ~494) lists `wire_extensions` for all four entry points but not `wire_transports`; add a transport wiring column or note below the table [Agent 2 finding]

### Codebase Research Notes (from FEAT-918)

- **`run.py` `try/finally` ordering** — `try:` at line 276; `finally:` at line 343; `lock_manager.release(fsm.name)` at line 344. `executor.close_transports()` MUST come before `lock_manager.release()` so transports flush while the loop is still locked.
- **`lifecycle.py:cmd_resume` lacks `try/finally`** — Lines 211–280 are a flat sequence. Wrapping lines 261–279 is required so transports flush on exception/`KeyboardInterrupt`.
- **`orchestrator.py`** — `self._event_bus = event_bus` at line 88; `_cleanup()` at lines 1301–1314. Add unconditional `self._event_bus.close_transports()` — flush even on interrupt.
- **`TestCmdResumeCircuitWiring` latent break** — `mock_config.events` is not set on the `MagicMock`; after `wire_transports` is added to `cmd_resume`, these tests will fail on iteration unless patched.

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current codebase (post-FEAT-1322):_

- **Exports already complete (FEAT-1322)** — `scripts/little_loops/__init__.py:33` imports `wire_transports` from `little_loops.transport` (alongside `JsonlTransport`, `Transport`); listed in `__all__` at line 62. `scripts/little_loops/config/__init__.py:37` imports `EventsConfig` from `little_loops.config.features`; listed in `__all__` at line 68. Original Proposed Solution steps 8 and 9 are no-ops; remove from acceptance criteria.
- **`PersistentExecutor.close_transports()` proxy exists** — `scripts/little_loops/fsm/persistence.py:398-400` already provides `def close_transports(self) -> None: self.event_bus.close_transports()`. Use `executor.close_transports()` in `run.py` and `lifecycle.py` (loop entries that own a `PersistentExecutor`); use `event_bus.close_transports()` directly in `parallel.py` / `sprint/run.py` / `orchestrator._cleanup()` (which use a standalone `EventBus`).
- **`EventBus.close_transports()` exception isolation** — `scripts/little_loops/events.py:109-114` wraps each transport's `close()` in a `try/except` that logs but swallows. Implementers do not need to add their own exception handling around `close_transports()` calls in entry points.
- **`wire_transports` signature** — `scripts/little_loops/transport.py:72` takes `(bus, config, log_dir)`. Callers in this issue pass `(executor.event_bus, config.events)` or `(event_bus, config.events)` — confirm whether `log_dir` is required or has a default before wiring (FEAT-1322 contract).
- **Test patch convention** — `TestCmdResumeCircuitWiring` patches `wire_extensions` at `"little_loops.extension.wire_extensions"` (module of definition, not import site — `test_cli_loop_lifecycle.py:1057,1091`). Patch `wire_transports` at `"little_loops.transport.wire_transports"` to match.
- **`lifecycle.py` already has `atexit.register(_cleanup_pid)`** — but no `try/finally` around the resume call. The new `try/finally` for `executor.close_transports()` is independent of the atexit cleanup; the atexit handles PID file removal only.
- **Sprint per-wave teardown** — `sprint/run.py` already has a wave-level `try/except/finally` (lines 299–524). Per-wave `event_bus.close_transports()` is delegated to `orchestrator._cleanup()` since the `event_bus` is passed into the orchestrator constructor and torn down in its `finally` block (line 176–177 of `orchestrator.py`); no additional teardown call needed in `sprint/run.py` itself.
- **Pre-existing transport-layer tests** — `scripts/tests/test_transport.py` already covers `EventBus.close_transports()` (line 136) and `wire_transports()` (line 158) in isolation. The new tests in this issue cover only the CLI/integration layer.
- **`_cleanup()` insertion point** — `merge_coordinator.shutdown(wait=True, timeout=30)` is at `orchestrator.py:1310`; the next statement is `if not self._shutdown_requested:` at line 1313. Insert `self._event_bus.close_transports()` between them so transports flush regardless of `_shutdown_requested` state.

## Use Case

A developer adds a `JsonlTransport` entry to `events.transports` in `.ll/ll-config.json` and runs `ll-auto`. They expect loop events to be streamed through the configured transport during the run and for the transport to be cleanly shut down when the run completes (including on `KeyboardInterrupt`). Without this wiring, the `events.transports` config is ignored and events never reach the transport layer regardless of what is configured.

## Acceptance Criteria

- [x] `wire_transports()` called at `run.py:334`, `lifecycle.py:266`, `parallel.py:229`, `sprint/run.py:403`
- [x] `close_transports()` called in `run.py:343 finally` (before lock release), new `lifecycle.py finally`, and `orchestrator._cleanup()`
- [x] `EventsConfig` exported from `config/__init__.py` and available in `__all__` *(already done by FEAT-1322 — verified at `scripts/little_loops/config/__init__.py:37,68`)*
- [x] `wire_transports` exported from `scripts/little_loops/__init__.py` *(already done by FEAT-1322 — verified at `scripts/little_loops/__init__.py:33,62`)*
- [x] `TestCmdResumeCircuitWiring` fixtures fixed — tests pass with `wire_transports` active in `cmd_resume`
- [x] `test_orchestrator.py` covers `_cleanup()` calling `close_transports()` and `_event_bus=None` guard
- [x] All four documentation files updated (`CONFIGURATION.md` already done by FEAT-1322; `API.md`, `ARCHITECTURE.md`, `EVENT-SCHEMA.md` updated here)
- [x] All existing tests pass

## Resolution

Wired `wire_transports()` at all four CLI entry points and added matching teardown via `close_transports()`:

- `cli/loop/run.py:cmd_run` — `wire_transports()` after `wire_extensions()`; `executor.close_transports()` runs in `finally` before `lock_manager.release()` (executor sentinel `None` handles failures before construction).
- `cli/loop/lifecycle.py:cmd_resume` — `wire_transports()` after `wire_extensions()`; `executor.resume()` wrapped in `try/finally` so `executor.close_transports()` runs on exit/exception (including `KeyboardInterrupt`).
- `cli/parallel.py:main_parallel` — `wire_transports()` after `wire_extensions()`; teardown delegated to `ParallelOrchestrator._cleanup()`.
- `cli/sprint/run.py:_cmd_sprint_run` — per-wave `wire_transports()` after `wire_extensions()`; teardown delegated to per-wave `ParallelOrchestrator._cleanup()`.
- `parallel/orchestrator.py:_cleanup` — added `self._event_bus.close_transports()` after `merge_coordinator.shutdown()`, gated on `self._event_bus is not None`, so transports flush regardless of `_shutdown_requested`.

Test coverage:
- Fixed `TestCmdResumeCircuitWiring` (lifecycle), added `MagicMock(transports=[])` + `patch("little_loops.transport.wire_transports")` to `TestCmdRunWorktree` and `TestQueueRetryOnRace`.
- Added `TestCmdRunTransportWiring` (3 tests), `TestCmdResumeTransportWiring` (3 tests), `test_cleanup_calls_close_transports_on_event_bus`, `test_cleanup_safe_when_event_bus_is_none`, `test_ll_parallel_wires_transports`, `test_sprint_wires_transports_per_wave`.

Documentation:
- `docs/ARCHITECTURE.md` — extended the CLI entry-point table with a "Transports Wired" column and added a paragraph on the additive multi-transport fan-out model.
- `docs/reference/EVENT-SCHEMA.md` — added a "Transport behavior" subsection under `loop_resume` documenting the previous bypass and the FEAT-1323 fix.
- `docs/reference/API.md` and `docs/reference/CONFIGURATION.md` — already complete (FEAT-1322); the forward-looking "Called by CLI entry points" claim in `API.md` is now factual.

Verification: full pytest suite passes (5548 passed; 3 pre-existing failures on `main` are unrelated — marketplace version sync and a builtin-loop YAML check). `ruff check` and `ruff format --check` pass on all modified files; `mypy` clean on all modified source files.

## Implementation Steps

1. Wire `wire_transports()` at all four CLI entry points (`run.py`, `lifecycle.py`, `parallel.py`, `sprint/run.py`).
2. Add teardown: `close_transports()` in `run.py` `finally`, new `lifecycle.py` `try/finally`, and `orchestrator._cleanup()`.
3. ~~Update `config/__init__.py` and `__init__.py` exports.~~ — already done in FEAT-1322; skip.
4. Fix `TestCmdResumeCircuitWiring` fixtures in `test_cli_loop_lifecycle.py`.
5. Add `test_orchestrator.py` `_cleanup` test.
6. Assert `wire_transports` and `close_transports` called correctly in `test_cli_loop_lifecycle.py`.
7. Write all four documentation updates.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Fix additional tests at risk of breaking when `wire_transports` is wired in: add `patch("little_loops.transport.wire_transports")` + `events = MagicMock(transports=[])` to `TestCmdRunWithWorktree` (`test_cli_loop_worktree.py`), `TestQueueRetryOnRace` (`test_cli_loop_queue.py`), multi-wave tests in `test_sprint_integration.py`, and `test_ll_parallel_dry_run` (`test_cli_e2e.py`)
9. Audit `TestCmdResume`, `TestCmdResumeBackground`, and `TestCmdResumeExitCodes` in `test_cli_loop_lifecycle.py` — they use real `BRConfig`; if `config.events.transports` does not resolve safely add `patch("little_loops.transport.wire_transports")` to each
10. Write new transport wiring assertion tests for `cmd_run` (`run.py`), `main_parallel` (`parallel.py`), and `_cmd_sprint_run` (`sprint/run.py`) — follow `TestCmdResumeCircuitWiring` patch pattern at `"little_loops.transport.wire_transports"`
11. Before writing `CONFIGURATION.md` and `API.md` doc updates: verify both sections are already written by FEAT-1322 (confirmed); update acceptance criterion "all four documentation files updated" to reflect `CONFIGURATION.md` is already done

## Impact

- **Priority**: P5
- **Effort**: Small–Medium
- **Risk**: Low — purely additive wiring; lifecycle.py `try/finally` is the only structural change
- **Breaking Change**: No
- **Depends On**: FEAT-1322 (must be merged first)
- **Blocks**: FEAT-1314 (WebhookTransport), FEAT-1312 (OTelTransport), FEAT-1313 (UnixSocketTransport)

## Labels

`feature`, `cli`, `wiring`, `transports`, `documentation`

## Status

**Completed** | Created: 2026-05-02 | Completed: 2026-05-02 | Priority: P5

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-02_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 60/100 → MODERATE

### Outcome Risk Factors
- Wide file surface (14 files: 5 source, 7 test, 3 docs) — each change is 1-2 lines but coordinating across this many files creates opportunity for missed patches
- `lifecycle.py` `try/finally` wrap is the most structurally complex change; the other 4 source files are single-line additions but this one restructures the control flow
- 7 test files require patch additions (`wire_transports` mock); if any are missed, tests fail immediately — the full list is identified in the integration map but implementation must be meticulous

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-02T16:41:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/83d74176-84ac-4ea2-9c73-06de95bcdbd2.jsonl`
- `/ll:manage-issue` - 2026-05-02T16:40:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/83d74176-84ac-4ea2-9c73-06de95bcdbd2.jsonl`
- `/ll:ready-issue` - 2026-05-02T16:30:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d73397d4-b2be-454b-b88f-b82e927e6265.jsonl`
- `/ll:confidence-check` - 2026-05-02T17:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/456c0106-3520-4939-a7be-d96adc064527.jsonl`
- `/ll:wire-issue` - 2026-05-02T16:25:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6ab09e3a-7876-4093-acb8-51d064a572a3.jsonl`
- `/ll:refine-issue` - 2026-05-02T16:19:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/60c38c7d-c3d4-476f-947b-a6dac8e2f4ba.jsonl`
- `/ll:format-issue` - 2026-05-02T15:23:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a3eefc16-896f-481d-8558-b7c6d43c3bbd.jsonl`
- `/ll:issue-size-review` - 2026-05-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19344c8e-9db2-4d37-b7f7-d6bf19e299d8.jsonl`
