---
id: FEAT-1323
priority: P5
size: Medium
---

# FEAT-1323: Transport CLI Wiring Pass and Documentation

## Summary

Wire `wire_transports()` at all four CLI entry points, add teardown via `close_transports()`, update public exports, fix affected test fixtures, and write the four documentation updates. This is the wiring half of the FEAT-918 split and requires FEAT-1322 to be merged first.

## Parent Issue

Decomposed from FEAT-918: Transport Protocol Foundation and JsonlTransport

## Context

FEAT-918 scored 11/11 on the size heuristic. The confidence check recommended splitting into two commits: (1) core module + refactor, (2) CLI wiring pass. This issue is part 2.

After FEAT-1322 ships: `Transport`, `JsonlTransport`, `wire_transports()`, `EventsConfig`, and `BRConfig.events` are all available. This issue hooks them up at the CLI layer and documents the complete feature.

## Expected Behavior

- `wire_transports(bus, config.events)` called after `wire_extensions()` at all four CLI entry points: `run.py`, `lifecycle.py`, `parallel.py`, `sprint/run.py`.
- `close_transports()` called in `run.py` `finally` block (before `lock_manager.release()`), in a new `lifecycle.py` `try/finally`, and in `ParallelOrchestrator._cleanup()`.
- `wire_transports` and `EventsConfig` exported from `scripts/little_loops/__init__.py` and `config/__init__.py`.
- All four documentation files updated to reflect the multi-transport model.

## Proposed Solution

7. Wire transports at all four CLI entry points and add teardown:
   - `run.py:334` — `wire_transports(executor.event_bus, config.events)` after `wire_extensions`; `executor.close_transports()` inside `finally:` (line 343) before `lock_manager.release()` (line 344).
   - `lifecycle.py:266` — `wire_transports()` after `wire_extensions()`; wrap from line 261 through end of resume call in `try/finally` so `close_transports()` runs on exit/exception.
   - `parallel.py:229` — `wire_transports(event_bus, config.events)` after `wire_extensions` (line 228); teardown handled by orchestrator.
   - `sprint/run.py:403` — per-wave `wire_transports(event_bus, config.events)` after `wire_extensions` (line 403); teardown handled by orchestrator.
   - `orchestrator.py:_cleanup()` (lines 1301–1314) — `self._event_bus.close_transports()` after `merge_coordinator.shutdown()`.

8. (wiring) Update `scripts/little_loops/config/__init__.py` — add `EventsConfig` to `from little_loops.config.features import (...)` tuple and `__all__` list.
9. (wiring) Update `scripts/little_loops/__init__.py` — add `wire_transports` to exports alongside `wire_extensions` (line 55).
10. (wiring) Fix `test_cli_loop_lifecycle.py` `TestCmdResumeCircuitWiring` fixtures (lines 1032, 1068) — add `mock_config.events = MagicMock(transports=[])` or patch `wire_transports` alongside `wire_extensions`.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/run.py:334` — `wire_transports()` after `wire_extensions`; `close_transports()` in `finally` before `lock_manager.release()`
- `scripts/little_loops/cli/loop/lifecycle.py:266` — `wire_transports()` after `wire_extensions()`; add `try/finally` wrapper (lines 261–279) for teardown
- `scripts/little_loops/cli/parallel.py:229` — `wire_transports(event_bus, config.events)` after `wire_extensions` (line 228)
- `scripts/little_loops/cli/sprint/run.py:403` — per-wave `wire_transports(event_bus, config.events)` after `wire_extensions` (line 403)
- `scripts/little_loops/parallel/orchestrator.py:_cleanup()` — `self._event_bus.close_transports()` inside `_cleanup()` at lines 1301–1314 after `merge_coordinator.shutdown()`
- `scripts/little_loops/config/__init__.py` — add `EventsConfig` to import tuple and `__all__`
- `scripts/little_loops/__init__.py` — add `wire_transports` to exports (line 55)

### Tests

- `scripts/tests/test_orchestrator.py` — add `_cleanup()` test asserting `close_transports()` is called via injected mock `EventBus`; cover `_event_bus=None` guard
- `scripts/tests/test_cli_loop_lifecycle.py` — assert `wire_transports` called in `cmd_resume`; assert `close_transports()` runs in new `finally`; fix `TestCmdResumeCircuitWiring` fixtures at lines 1032 and 1068

### Documentation

- `docs/reference/API.md` — document `Transport` Protocol and `EventBus.add_transport()` / `close_transports()`
- `docs/ARCHITECTURE.md` — note the multi-transport fan-out model (foundation only; webhook/OTel/socket listed when they land)
- `docs/reference/CONFIGURATION.md` — add `events.transports` block after `extensions` (line 608)
- `docs/reference/EVENT-SCHEMA.md` — annotate the `loop_resume` bypass fix in the transport-behavior section

### Codebase Research Notes (from FEAT-918)

- **`run.py` `try/finally` ordering** — `try:` at line 276; `finally:` at line 343; `lock_manager.release(fsm.name)` at line 344. `executor.close_transports()` MUST come before `lock_manager.release()` so transports flush while the loop is still locked.
- **`lifecycle.py:cmd_resume` lacks `try/finally`** — Lines 211–280 are a flat sequence. Wrapping lines 261–279 is required so transports flush on exception/`KeyboardInterrupt`.
- **`orchestrator.py`** — `self._event_bus = event_bus` at line 88; `_cleanup()` at lines 1301–1314. Add unconditional `self._event_bus.close_transports()` — flush even on interrupt.
- **`TestCmdResumeCircuitWiring` latent break** — `mock_config.events` is not set on the `MagicMock`; after `wire_transports` is added to `cmd_resume`, these tests will fail on iteration unless patched.

## Acceptance Criteria

- [ ] `wire_transports()` called at `run.py:334`, `lifecycle.py:266`, `parallel.py:229`, `sprint/run.py:403`
- [ ] `close_transports()` called in `run.py:343 finally` (before lock release), new `lifecycle.py finally`, and `orchestrator._cleanup()`
- [ ] `EventsConfig` exported from `config/__init__.py` and available in `__all__`
- [ ] `wire_transports` exported from `scripts/little_loops/__init__.py`
- [ ] `TestCmdResumeCircuitWiring` fixtures fixed — tests pass with `wire_transports` active in `cmd_resume`
- [ ] `test_orchestrator.py` covers `_cleanup()` calling `close_transports()` and `_event_bus=None` guard
- [ ] All four documentation files updated
- [ ] All existing tests pass

## Implementation Steps

1. Wire `wire_transports()` at all four CLI entry points (`run.py`, `lifecycle.py`, `parallel.py`, `sprint/run.py`).
2. Add teardown: `close_transports()` in `run.py` `finally`, new `lifecycle.py` `try/finally`, and `orchestrator._cleanup()`.
3. Update `config/__init__.py` and `__init__.py` exports.
4. Fix `TestCmdResumeCircuitWiring` fixtures in `test_cli_loop_lifecycle.py`.
5. Add `test_orchestrator.py` `_cleanup` test.
6. Assert `wire_transports` and `close_transports` called correctly in `test_cli_loop_lifecycle.py`.
7. Write all four documentation updates.

## Impact

- **Priority**: P5
- **Effort**: Small–Medium
- **Risk**: Low — purely additive wiring; lifecycle.py `try/finally` is the only structural change
- **Breaking Change**: No
- **Depends On**: FEAT-1322 (must be merged first)
- **Blocks**: FEAT-1314 (WebhookTransport), FEAT-1312 (OTelTransport), FEAT-1313 (UnixSocketTransport)

## Status

**Open** | Created: 2026-05-02 | Priority: P5

## Session Log
- `/ll:issue-size-review` - 2026-05-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19344c8e-9db2-4d37-b7f7-d6bf19e299d8.jsonl`
