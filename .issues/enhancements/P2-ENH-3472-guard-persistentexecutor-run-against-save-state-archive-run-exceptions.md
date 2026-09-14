---
id: ENH-3472
title: 'Guard PersistentExecutor.run() so a save_state/archive_run exception cannot discard an already-computed ExecutionResult'
type: ENH
priority: P2
status: open
discovered_date: '2026-09-13'
labels: []
parent: ENH-3468
---

## Summary

`PersistentExecutor.run()` (`fsm/persistence.py:1212`) wraps `FSMExecutor.run()` and, once that inner call returns a fully-formed `ExecutionResult`, calls `StatePersistence.save_state()` (`:502`) and `StatePersistence.archive_run()` (`:585`). Neither call is exception-guarded except inside the `terminated_by == "workdir_vanished"` branch (which only catches `OSError`). If either raises (e.g. disk full) outside that branch, the exception propagates out of `PersistentExecutor.run()` unhandled and discards the result — including the `events.jsonl`/`usage.jsonl` traces `archive_run()` was about to copy into `.loops/.history/`. This issue closes that gap: an already-computed result must survive a persistence-layer failure.

This child is independent of its siblings (ENH-3471, ENH-3473) — it does not touch `terminated_by` vocabulary or checkpoint artifacts, only the persistence call site's own exception safety.

## Current Behavior

`PersistentExecutor.run()` calls `StatePersistence.save_state()` and `StatePersistence.archive_run()` after `FSMExecutor.run()` returns; only the `terminated_by == "workdir_vanished"` branch is exception-guarded, and only against `OSError`. The `else` branch (`fsm/persistence.py:1279-1281`) has no exception handling at all — a `save_state()`/`archive_run()` failure (e.g. disk full) raises out of `PersistentExecutor.run()` uncaught, discarding the already-computed `ExecutionResult` along with the `events.jsonl`/`usage.jsonl` traces `archive_run()` was about to copy into `.loops/.history/`.

## Expected Behavior

A `save_state()`/`archive_run()` exception raised from the unguarded `else` branch is caught, logged, and does not propagate — `PersistentExecutor.run()` still returns the already-computed `ExecutionResult` to its caller, following the `except Exception  # noqa: BLE001` precedent cited in Design.

## Parent Issue

Decomposed from ENH-3468: Every loop iteration writes a checkpoint, never zero: salvage paid work and tag the best-effort attempt.

This child covers **Implementation Step 2** in full, including its dedicated wiring/test item.

## Design

This codebase's convention for guarding a risky I/O/persistence call that "must never fail the run" is a final broad `except Exception` carrying a `# noqa: BLE001` comment stating the rule, after narrower exception types where relevant:
- `fsm/persistence.py:904` (`promote_run_artifact()`, three-tier `except (ManifestError, DataValidationError)` / `except OSError` / `except Exception  # noqa: BLE001 - promotion must never fail the run`, each branch logging and returning `None`)
- `fsm/persistence.py:85` (`# noqa: BLE001 — additive enrichment; default on`)
- `session_store/db.py:579,609` (`cli_event_context`, documented at `:504-511`)
- `cli/harness.py:83,112,118,1200`; `learning_tests/gate.py:79`; `worktree_utils.py:847`; `skill_expander.py:163`; `parallel/worker_pool.py:1945,1970`; `cli/sprint/run.py:303`

This is the applicable precedent for guarding `save_state()`/`archive_run()` in `PersistentExecutor.run()`'s unguarded `else` branch — log and continue, do not re-raise.

## Program Design

### Signatures
- `PersistentExecutor.run(self, clear_previous: bool = True) -> ExecutionResult` (`scripts/little_loops/fsm/persistence.py:1212`) — wraps `FSMExecutor.run()` then calls `StatePersistence.save_state(self, state: LoopState) -> None` (`:502`) and `StatePersistence.archive_run(self, run_dir: Path | None = None) -> Path | None` (`:585`); the target of this change is the unguarded `else` branch at `:1279-1281`.
- `record_loop_run_summary(...)` (`scripts/little_loops/session_store/writers.py:1791`) — already writes its `loop_runs` row inside `_finish()`, which returns *before* the block this issue guards runs — so only the filesystem archive step (`state.json`/`events.jsonl` copy) is at risk here, not the DB row.

### Call Path
`PersistentExecutor.run()` → `run_foreground()` (`cli/loop/runner.py:476`, `try/finally` only, no `except`, `:467-489`) → `cmd_run()` (`cli/loop/run.py:659-673`, `try/finally` only) → `main_loop()` dispatch (`cli/loop/__init__.py:1088`, zero try/except) → `ll-loop` console-script boundary (`pyproject.toml:84`). Nothing intercepts a `save_state()`/`archive_run()` exception anywhere in this chain today — it surfaces as a raw traceback with default nonzero exit.

## Implementation Steps

1. Guard `PersistentExecutor.run()`'s `save_state()`/`archive_run()` calls (`fsm/persistence.py:1279-1281`) following the `except Exception  # noqa: BLE001` precedent above — log the failure and return the already-computed `ExecutionResult` rather than letting the exception propagate.
2. Add a test in `scripts/tests/test_fsm_persistence.py` covering this branch (no existing test does — `TestWorkdirVanished` in `test_fsm_executor.py` (:14155+) only exercises a raw `FSMExecutor`, never `PersistentExecutor`). Follow the file's own post-construction method-assign convention (see `test_drain_inbound_spoof_does_not_trigger_persistence_side_effects`, :960-968): set `executor.persistence.save_state = MagicMock(side_effect=RuntimeError("disk full"))` before calling `executor.run()`, and assert the result is still returned rather than an exception propagating.
3. `python -m pytest scripts/tests/test_fsm_persistence.py -v` passes.

## Tests

- `scripts/tests/test_fsm_persistence.py::test_run_saves_final_state` (:915) — closest existing structural template to extend from, though the new test targets the failure path rather than the happy path.
- Inline `side_effect=RuntimeError(...)` patching convention already used in `test_fsm_executor.py` (`test_survives_db_failure_during_summary` ~:3693-3699, a same-shape test ~:3780-3786, `test_survives_write_failure` :3888-3898) is the pattern to mirror for asserting the run still completes normally despite the injected failure.

## Scope Boundaries

- **In scope**: Guarding the `save_state()`/`archive_run()` calls in `PersistentExecutor.run()`'s unguarded `else` branch (`fsm/persistence.py:1279-1281`) with a broad catch-and-log per the precedent cited in Design; the accompanying regression test.
- **Out of scope**: `terminated_by` vocabulary changes (ENH-3471), checkpoint/best-effort artifacts (ENH-3473), the already-guarded `workdir_vanished`/`OSError` branch.

## Impact

- **Priority**: P2 - Matches frontmatter; scoped to one call site's exception safety, independent of siblings ENH-3471/ENH-3473
- **Effort**: Small - One guard clause plus one regression test, per Implementation Steps
- **Risk**: Low - Additive exception handling around an existing unguarded branch; behavior-preserving for the success path
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-13 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-09-14T19:18:27 - `e03a4d3e-6e32-492e-b751-6c3a912f41aa.jsonl`
- `/ll:issue-size-review` - 2026-09-13T19:16:25 - `bd6d1308-41a1-42e0-b1ba-67bcf198d91f.jsonl`
