---
id: ENH-3650
type: ENH
title: Introduce HistoryTarget through the history.db backend chokepoint (SQLite-only,
  no behavior change)
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T02:40:50Z'
blocks:
- FEAT-3535
verify_verdict: VALID
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3650: Introduce HistoryTarget through the history.db backend chokepoint (SQLite-only, no behavior change)

## Summary

Introduce a `HistoryTarget` type (`LocalTarget(path) | RemoteTarget(config)`) through the `little_loops.session_store.backend` chokepoint, with no behavior change. It is the SQLite-only prerequisite for FEAT-3535 (remote libSQL history backend): a remote store has no filesystem path, so the path-typed chokepoint must first become target-typed. After this lands, only `LocalTarget` is ever produced and `sqlite` behaves exactly as today.

## Current Behavior

The chokepoint is path-typed end to end: `Backend.connect(path: Path, *, check_same_thread)`, `connect_readonly(path)` and `ensure_schema(path)` take `Path`; `_resolve_once()` returns `Path`; `open_history`, `open_history_readonly` and `connect_readonly` return `sqlite3.Connection`. `BackendProvider` is `Literal["sqlite"]` and the entry points call `resolve_backend()` with no argument. `hooks/__init__.py::main_hooks` and `hooks/post_tool_use.py` hard-code `<root>/.ll/history.db`, and the session-start, post-commit and pytest-history-plugin modules read the history-path environment override independently.

## Expected Behavior

- `_resolve_once(target)` returns a `HistoryTarget`; with only the SQLite provider registered it is always a `LocalTarget` and resolution precedence is unchanged (`explicit path > LL_HISTORY_DB > history.db_path > DEFAULT_DB_PATH`).
- `Backend.connect`, `connect_readonly` and `ensure_schema` widen to accept `Path | HistoryTarget` (a `Path` is coerced to `LocalTarget` at the boundary), so no existing caller changes; `SqliteBackend` accepts only a local target and raises `HistoryUnsupported` for a `RemoteTarget`.
- The entry points select the backend from the target (`resolve_backend(target.provider)`) instead of the hard-coded default. Return annotations stay `sqlite3.Connection` in this issue; narrowing to `HistoryConnection` lands with FEAT-3535 when a second backend exists.
- The `schema.connect` and `ensure_db` seam accepts a target, so a later `RemoteTarget` either performs a supported operation or raises `HistoryUnsupported` before any mutation (fail-closed).
- Hook and plugin paths that open the history database resolve a target through the same seam instead of constructing the location themselves.

## Motivation

FEAT-3535 (remote libSQL history backend) needs a store target that is not a filesystem path. Landing the target type first, SQLite-only and with no behavior change, keeps that feature's own change surface small and lets this refactor be reviewed and reverted independently: the chokepoint has 100+ call sites and the hook paths hard-code the database location.

## Proposed Solution

Add `LocalTarget`/`RemoteTarget`/`HistoryTarget` in `session_store/backend.py`, retype the `Backend` protocol and `_resolve_once` to them, select the backend from the target in the three entry points, and make the shared `schema.connect`/`ensure_db` seam and the hook paths resolve through the same target. Only `LocalTarget` is produced until FEAT-3535 registers a second provider, so behavior is unchanged. Design source: FEAT-3535 Proposed Design, section 2.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/backend.py`: target types, protocol, `_resolve_once`, entry points.
- `scripts/little_loops/session_store/db.py`: `_resolve_db_path` and `resolve_history_db` carry the target.
- `scripts/little_loops/session_store/schema.py`: `connect` and `ensure_db` accept a target.
- Hook modules that build a literal `.ll/history.db` path (`hooks/__init__.py::main_hooks`, `post_tool_use`, `user_prompt_submit`, `pre_compact`, `subagent_start`, `subagent_stop`, `sweep_stale_refs`, `session_start`, plus `post_commit` and `pytest_history_plugin` for the environment override): audit, and edit only paths that bypass `_resolve_once`; several already wrap the path in `resolve_history_db`.

### Tests
- `scripts/tests/test_session_store_backend.py`, `test_history_store_chokepoint_gate.py`, `test_session_store_writers.py`, `test_session_store_lifecycle.py`.

## Program Design

### Types

- `LocalTarget`: frozen dataclass holding a filesystem `path: Path`
- `RemoteTarget`: frozen dataclass holding a `config: BackendConfig`
- `HistoryTarget`: type alias `LocalTarget | RemoteTarget`

### Signatures

- `_resolve_once(target: Path | str | HistoryTarget | None) -> HistoryTarget` — resolve precedence and return the typed target
- `Backend.connect(target: Path | HistoryTarget, *, check_same_thread: bool = True) -> sqlite3.Connection` — open a connection for the target; a `Path` is coerced to `LocalTarget`
- `resolve_backend(provider: str = "sqlite") -> Backend` — unchanged signature; entry points now pass `target.provider`

### Call Path

`open_history` -> `_resolve_once` -> `resolve_backend` -> `SqliteBackend.connect`

## Implementation Steps

1. Add `HistoryTarget`, `LocalTarget` and `RemoteTarget` (frozen dataclasses) beside `Backend` in `session_store/backend.py`.
2. Change `_resolve_once` to return a `HistoryTarget` and widen the `Backend` protocol methods to `Path | HistoryTarget` (coercing `Path` to `LocalTarget`); make `SqliteBackend` reject a `RemoteTarget`.
3. Route `open_history`, `open_history_readonly` and `connect_readonly` through `resolve_backend(target.provider)`; leave their return annotations unchanged.
4. Make the `schema.connect` and `ensure_db` seam target-aware.
5. Audit every hook module that builds a literal `.ll/history.db` path (`__init__`, `post_tool_use`, `user_prompt_submit`, `pre_compact`, `subagent_start`, `subagent_stop`, `sweep_stale_refs`, `session_start`) and the environment-override readers; edit only paths that do not already reach `_resolve_once` through `schema.connect`/`resolve_history_db`.
6. Update the affected tests (`test_session_store_backend.py`, `test_history_store_chokepoint_gate.py`, `test_session_store_writers.py`, `test_session_store_lifecycle.py`).

## Impact

- **Priority**: P4. A prerequisite for FEAT-3535 (also P4); nothing else depends on it.
- **Effort**: Medium. Touches the chokepoint, the connect seam, five hook or plugin readers and four test modules, but changes no behavior.
- **Risk**: Low to Medium. Wide call surface; the existing suite and the chokepoint gate are the regression net.
- **Breaking Change**: None.

## Scope Boundaries

- Out of scope: any remote provider, the Hrana client, `history.backend` config, the operation matrix and ingestion changes; all stay in FEAT-3535.
- Out of scope: migrating call sites that hold a plain `Path` to the target type one by one; they keep SQLite behavior through the target-aware seam.

## Acceptance Criteria

- [ ] `python -m pytest scripts/tests/` exits 0 with no test changes other than annotation and fixture updates for the new target type.
- [ ] `_resolve_once` returns a `LocalTarget` for every existing input shape, and `resolve_history_db()` returns the same `Path` as before for each.
- [ ] `SqliteBackend.connect` called with a `RemoteTarget` raises `HistoryUnsupported`.
- [ ] `test_history_store_chokepoint_gate.py` still passes and its `sqlite3.connect` allowlist does not grow.
- [ ] Every hook writer path that opens the history database (`main_hooks`, `post_tool_use`, `user_prompt_submit`, `pre_compact`, `subagent_start`, `subagent_stop`, `sweep_stale_refs`, `session_start`) reaches `_resolve_once`; a test monkeypatches `_resolve_once`, drives each path, and asserts it was called.

## Related

- FEAT-3535 (remote libSQL history backend; blocked by this issue). Design source: FEAT-3535 Proposed Design section 2.
- ENH-3525, ENH-3526 (chokepoint prerequisites, done).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-28_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 75/100 → MODERATE

### Concerns
- The hook audit (Step 5) has an unknown result: eight hook modules build a literal default-shaped path and several already wrap it in `resolve_history_db`. The test in the acceptance criteria settles which need edits.
- `schema.connect` and `ensure_db` accept `Path | str` today, so the seam must decide how a default-shaped path resolves to a target; that rule already exists in `db.py::_resolve_db_path` and should be reused, not reimplemented.

**Open** | Created: 2026-09-29 | Priority: P4


## Session Log
- `/ll:confidence-check` - 2026-09-29T02:44:29 - `82825f0f-e592-4590-85b9-5a65863337be.jsonl`
