---
id: BUG-3652
type: BUG
title: Audit resolve_history_db callers under a remote history backend
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T04:19:08Z'
---

# BUG-3652: Audit resolve_history_db callers under a remote history backend

## Summary

Under `history.backend.provider: libsql` (FEAT-3535), `resolve_history_db()` raises `HistoryBackendNotLocal` for the default location because a remote store has no local path. FEAT-3535 converted the event writers and hooks (which open through the target-aware `schema.connect` seam), but about 49 other call sites outside `session_store/` still call it. Nobody audited whether each sits inside a best-effort guard, so a remote-configured `ll-parallel`, `ll-sprint` or `ll-loop` run may fail at startup instead of degrading.

## Current Behavior

`resolve_history_db()` raises `HistoryBackendNotLocal` (a `HistoryUnsupported` subclass) when `history.backend` selects a remote provider and the path is default-shaped with `LL_HISTORY_DB` unset. Callers that do not catch it propagate the error. Call sites by file (counts from `grep "resolve_history_db("` outside `session_store/`): `cli/history.py` (8), `cli/harness.py` (5), `parallel/orchestrator.py` (4), `fsm/executor.py` (4), `parallel/worker_pool.py` (3), `cli/sprint/run.py` (3), `parallel/merge_coordinator.py` (2), `cli/loop/run.py` (2), `cli/logs.py` (2), `cli/doctor.py` (2, already remote-aware), and one each in `workspace.py`, `work_verification.py`, `user_messages.py`, `transport.py`, `runner_spec.py`, `mcp_server/tools.py`, `fsm/continuity.py`, `decisions.py`, `cli/parallel.py`, `cli/issues/set_status.py`, `cli/issues/research_triage.py`, `cli/ctx_stats.py`, `issue_history/workspace_quality.py`, `history_reader/_base.py`.

## Expected Behavior

Every caller either reaches the remote store correctly (a history read or write routed through `resolve_history_store` or the target-aware `schema.connect` seam), is guarded so a remote target degrades to "skip" for best-effort telemetry, or raises a clear `HistoryUnsupported` for an operation the remote store does not support. No `ll-*` startup path fails with an unhandled `HistoryBackendNotLocal`.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Audit each call site and classify it: (a) history read or write, so convert to `resolve_history_store` or pass the default-shaped path through the seam; (b) best-effort telemetry, so guard and skip on a remote target; (c) a local-file operation, so raise `HistoryUnsupported` naming the operation via `refuse_on_remote`. Add a test that drives `ll-parallel`, `ll-sprint` and `ll-loop` startup under the Hrana stub backend.

## Integration Map

### Files to Modify
- The call sites listed above.

### Dependent Files
- `scripts/little_loops/session_store/db.py` (`resolve_history_db`, `resolve_history_store`, `resolve_history_target`)
- `scripts/tests/hrana_stub.py` (test double)

### Tests
- New test module driving the three orchestrators under the remote stub; existing `test_remote_hooks.py` shows the fixture shape.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

**Caller classification** (path under `scripts/little_loops/`; guard = what already surrounds the `resolve_history_db()` evaluation; class per the Proposed Solution scheme):

| Site | Class | Guard today | Under remote today |
|---|---|---|---|
| `cli/parallel.py:main_parallel` (`:327`) | (b) | none | **startup abort** |
| `cli/sprint/run.py:_cmd_sprint_run` (`:566`) | (b) | none, before big `try` | **startup abort** |
| `cli/sprint/run.py:_cmd_sprint_run` (`:660`, `:807`) | (b) | big `try` / `except Exception` → exit 1 | sprint fails at first wave |
| `transport.py:wire_transports` (`:2031`) | (b) | none | abort whenever `"sqlite"` in `events.transports` |
| `parallel/orchestrator.py` (`:486`, `:785`, `:811`, `:1224`), `parallel/worker_pool.py` (`:460`, `:925`, `:1741`), `parallel/merge_coordinator.py` (`:1115`, `:1196`), `cli/loop/run.py` (`:533`, `:595`) | (b) | `with suppress(Exception)` around resolve + write | silently skips the write |
| `fsm/executor.py` (`:2689`, `:4681`, `:4708`), `runner_spec.py:_run_cmd` (`:326`) | (b) | `try/except Exception: pass` | silently skips |
| `fsm/executor.py:_check_prepatch_check` (`:2017`) | (a) read | none; outer `run()` `except Exception` | loop ends `error` when a `prepatch_check` policy applies |
| `fsm/continuity.py:summarize_completed_state` (`:52`) | (a) read+write | none; caller `except Exception: return None` | continuity summary dropped |
| `work_verification.py:_run_non_fsm_prepatch_check` (`:280`) | (a) | resolve unguarded, write guarded; returns early when `prepatch_check.enabled` is false (default) | raise only when enabled |
| `cli/issues/set_status.py:apply_status_transition` (`:183`) | (b) | `except (sqlite3.Error, ImportError, OSError)` — misses `HistoryError`; raised after the frontmatter `atomic_write` | `ll-issues set-status` and MCP `issue_set_status` raise after the status file already changed |
| `cli/issues/research_triage.py` (`:122`) | (b) | none (resolve is outside `write_research_triage`'s own guard) | `ll-issues research-triage` raises |
| `cli/history.py:main_history` (`:592`, `:628`, `:731`, `:755`, `:780`, `:797`, plus `summary` and `analyze` sites not in the issue's list) | (a) reads | none | user-invoked reads raise; readers take `Path`, not `HistoryTarget` |
| `cli/harness.py` (`:245`, `:1089`, `:1994`, `:2027`, `:3613`) | (a) reads | none | user-invoked reads raise |
| `cli/logs.py` (`:1721`, `:1965`), `cli/ctx_stats.py` (`:1074`), `decisions.py` (`:596`), `user_messages.py` (`:1198`), `mcp_server/tools.py:_tool_history_search` (`:172`) | (a) reads | none (MCP `call_tool` converts to `is_error`) | raise |
| `cli/doctor.py:_schema_drift_data` (`:716`) | (c) | already remote-aware (`_remote_target()` early return) | reports "not applicable" |
| `hooks/scripts/context-monitor.sh` (2 calls) | (b) | `>/dev/null 2>&1 \|\| true` | silently skips |

**Already remote-capable (do not touch)**: `SQLiteTransport.__init__` (`session_store/writers.py`, uses `resolve_history_store` and catches `HistoryError`), `cli_event_context`, `worktree_utils.export_history_db_env`, `hooks/session_start.py`, `cli/session.py`, `cli/auto.py`/`issue_manager.py` (pass `DEFAULT_DB_PATH` to `SQLiteTransport`, never call `resolve_history_db`).

**Contracts a change must preserve**
- `resolve_history_store()` returns a plain `Path` for a local store, byte-identical to `resolve_history_db()`; local behavior must not change.
- The reader layer (`history_reader.*`, `issue_history.parsing.*`, `decisions.generate_from_completed`) coerces with `Path(db)` / calls `.exists()`; `Path(RemoteTarget)` raises `TypeError`, and an *absolute* default-shaped path is treated as local verbatim by `_resolve_once` (BUG-3181) — only a relative default or the `schema.connect` seam re-resolves it. Routing a reader through the remote store is therefore not a call-site-only change.
- `refuse_on_remote` has no caller outside `session_store/` today; its message table `_REMOTE_REFUSALS` is keyed by operation name and falls back to a generic "local-file operation" text for unknown names.
- Writers catch only `sqlite3.Error` (not `HistoryError`); the FEAT-3535 Dependent Files note already flags the `except sqlite3.*` sites as needing best-effort review.

**Tests that couple to the current shape**: `test_worker_pool.py` patches `worker_pool_module.resolve_history_db`; `test_transport.py::test_sqlite_registered_by_name` pins the `wire_transports` sqlite branch against `resolve_history_db()`; `test_worktree_utils.py` shells out to it; `test_cli_harness.py` (18 refs) and `test_session_store_db.py` (25 refs) reference it by name. There is no test that drives `ll-parallel`/`ll-sprint`/`ll-loop` under `HranaStub` and no meta-test that enumerates `resolve_history_db()` callers (closest: `test_history_target_hook_audit.py`, a runtime `_resolve_once` spy).

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

**Conventions in force** (evidence, not templates):
- Three-way resolver split — a caller either needs a filesystem path (fails closed under remote) or "the store" (stays remote-capable): `session_store/db.py` (`resolve_history_db` / `resolve_history_target` / `resolve_history_store`).
- Where remote has no equivalent, code skips silently on an `isinstance(<store>, RemoteTarget)` check rather than raising: `worktree_utils.py:export_history_db_env`, `hooks/session_start.py`, `session_store/lifecycle.py:_watermark_key`, `cli/session.py:_is_foreign_path`. The check is written inline at ≥6 sites; the only helper is doctor's private `_remote_target()` — no shared `is_remote()` helper exists.
- Local-file-only maintenance operations call `refuse_on_remote(db, "<operation>")` first (`session_store/lifecycle.py`, `session_store/queries.py`); CLI boundaries catch `HistoryUnsupported`/`HistoryError` and return 1 without a traceback (`cli/backfill_worker.py:main`, `cli/session.py:_main_migrate`).
- Best-effort telemetry guards are written inline at each site in three shapes — `suppress(Exception)` (`parallel/*`, `cli/loop/run.py`), `try/except Exception: pass` (`fsm/executor.py`, `runner_spec.py`), narrow tuples (`set_status.py`). Contested: the narrow tuple disagrees with the broad-`Exception` convention used everywhere else for the same role.
- Contested: `SQLiteTransport`'s default is `DEFAULT_DB_PATH` (remote-capable) yet `transport.py`, `cli/parallel.py` and `cli/sprint/run.py` pass `resolve_history_db()`; `cli/harness.py` deliberately "resolves once" so reader and writer agree (BUG-3181).
- Remote tests are ordinary unmarked unit tests; each module defines its own `remote(tmp_path, monkeypatch)` fixture (`test_remote_hooks.py::remote`) that must `delenv("LL_HISTORY_DB")` (the autouse `_isolate_history_db` in `conftest.py` sets it), write `.ll/ll-config.json` with `history.backend.provider: libsql`, `chdir(tmp_path)`, clear the backend-config/verification caches, and run `migrate_remote`. Dead-endpoint tests call `remote.stop()` and assert exit 0 (`test_remote_ingestion_telemetry.py::TestBestEffortNeverAborts`). Local regression twins live in the same file (`test_remote_operation_matrix.py::test_local_sqlite_still_runs_the_same_operations`).

## Program Design

### Types
- `HistoryTarget = LocalTarget | RemoteTarget` — `session_store/targets.py`; the typed value `resolve_history_target()` returns.
- `HistoryBackendNotLocal(HistoryUnsupported)` — `session_store/backend.py`; raised (never caught) by `resolve_history_db()` and `schema._local_db_path()`.

### Signatures
- `resolve_history_db(path: Path | str | HistoryTarget | None = None, *, root: Path | None = None) -> Path` — raises `HistoryBackendNotLocal` for a remote target.
- `resolve_history_store(path: Path | str | HistoryTarget | None = None, *, root: Path | None = None) -> Path | RemoteTarget` — never raises for remote; local result equals `resolve_history_db()`.
- `resolve_history_target(path, *, root) -> HistoryTarget` — the typed resolver both of the above wrap.
- `refuse_on_remote(db: Path | str | HistoryTarget | None, operation: str) -> None` — raises `HistoryUnsupported(operation=...)` only for a `RemoteTarget`.
- `SQLiteTransport(db_path: Path | str = DEFAULT_DB_PATH)` — resolves through `resolve_history_store` and disables itself on `HistoryError`.
- `wire_transports(...)` in `transport.py` — the shared `"sqlite"` branch that `main_parallel`, `_cmd_sprint_run` and `cmd_run` reach.

### Call Path
`main_parallel` -> `SQLiteTransport(resolve_history_db())` -> `resolve_history_target` -> `HistoryBackendNotLocal`

`_cmd_sprint_run` -> `resolve_history_db` -> `resolve_history_target` -> `HistoryBackendNotLocal`

`apply_status_transition` -> `resolve_history_db` -> `record_issue_snapshot` (guard `except (sqlite3.Error, ImportError, OSError)` misses `HistoryError`)

### Decision Rules
- Classification of each caller: **(b)** if the resolve feeds a `record_*` writer or `SQLiteTransport` and the surrounding operation's outcome does not depend on the write; **(a)** if the resolved path is read back to produce output or a verdict; **(c)** if the operation needs a local file (`.exists()`, filesystem manifest read). Guard for **(b)** must degrade to "skip" on `HistoryError` (superclass of `HistoryBackendNotLocal`, `HistoryUnavailable`, `HistorySuppressed`), not only on `sqlite3.Error`.
- Escape hatch / invariant: an explicit non-default path or `LL_HISTORY_DB` is always a `LocalTarget`; no guard may change behavior there.

## Implementation Steps

1. Every non-`session_store/` caller is classified (a)/(b)/(c) — the Integration Map caller table is the starting inventory (45 real calls + 2 in `context-monitor.sh`, not 49; three of the issue's listed files only mention the name in docstrings). Verification: a grep for `resolve_history_db(` outside `session_store/` matches the table.
2. `ll-parallel` and `ll-sprint run` start under the Hrana stub with `LL_HISTORY_DB` unset and reach their first phase; the two unguarded startup sites and the `wire_transports` sqlite branch no longer raise. `ll-loop run` (with and without `--worktree`, and a state using `prepatch_check`/`session_mode: continue`) completes without a `HistoryBackendNotLocal`.
3. Best-effort (b) sites degrade to skip on `HistoryError`, including `apply_status_transition` (the status file must not change and then raise); reader (a) commands either reach the remote store or raise a clear `HistoryUnsupported` naming the operation — none surfaces a bare `HistoryBackendNotLocal` traceback.
4. Coverage: a new remote-stub test module in the `test_remote_*.py` family drives the three orchestrators' startup using the `remote` fixture shape (including the `LL_HISTORY_DB` delenv) plus a dead-endpoint case asserting startup still succeeds; a local-provider twin proves behavior is unchanged. Existing tests that patch `resolve_history_db` by name (`test_worker_pool.py`, `test_transport.py`, `test_cli_harness.py`) keep passing or are updated with the change.
5. `python -m pytest scripts/tests/` passes with the default local store; `ruff check` and `mypy` clean on touched files (scope `ruff format` to changed files).

## Impact

- **Priority**: P3. Affects only opt-in remote-backend users, but a startup failure in a main orchestrator is severe for them.
- **Effort**: Medium.
- **Risk**: Low; local SQLite behavior must stay byte-identical (`resolve_history_store` returns a plain `Path` for a local store).

## Steps to Reproduce

1. Configure `history.backend.provider: libsql` with a reachable endpoint (or the `tests/hrana_stub.py` double).
2. Run `ll-parallel`, `ll-sprint run` or `ll-loop run` with `LL_HISTORY_DB` unset.
3. Observe whether startup fails at a `resolve_history_db()` call.

## Acceptance Criteria

- [ ] Every non-`session_store/` caller of `resolve_history_db()` is classified and either routed, guarded or refused with a named `HistoryUnsupported`.
- [ ] `ll-parallel`, `ll-sprint` and `ll-loop` start under a remote (Hrana stub) backend without an unhandled `HistoryBackendNotLocal`.
- [ ] With the default local store, `python -m pytest scripts/tests/` passes unchanged.

## Related

- FEAT-3535 (remote libSQL history backend); see its Deviations and Resolution sections.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-29T04:50:06 - `d770577e-1f76-4a53-b5c3-a8661dec6288.jsonl`
- `/ll:capture-issue` - 2026-09-29T04:19:18 - `4d45d755-73ff-4de3-8bd1-bb8e866143f2.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **File**: `scripts/little_loops/session_store/db.py`
- **Anchor**: `in function resolve_history_db()`
- **Cause**: `resolve_history_db()` narrows `resolve_history_target()` to a `Path` and raises `HistoryBackendNotLocal(operation="resolve_history_db")` for a `RemoteTarget`; it never returns a fabricated path. The event writers (`record_*`), `SQLiteTransport.__init__`, `cli_event_context` and the hooks already accept a default-shaped path and resolve inside the seam (`schema.connect` → `_resolve_once(..., reresolve_absolute=True)`), so the raise only fires where a caller *pre-resolves* through `resolve_history_db()` first. `HistoryBackendNotLocal` subclasses `HistoryUnsupported` → `HistoryError` → `Exception` — it is not a `sqlite3.Error`, `OSError` or `ImportError`, so narrow `except` tuples miss it. No `except HistoryBackendNotLocal` exists anywhere in the repo (searched repo-wide).
- **Real-call count**: 45 real calls under `scripts/little_loops/` outside `session_store/` (+2 in `hooks/scripts/context-monitor.sh`). The issue's "about 49" includes docstring/comment mentions in `workspace.py`, `issue_history/workspace_quality.py` and `history_reader/_base.py` (deliberate non-use) and `cli/doctor.py`'s second mention — those are not callers.
- **Startup-reachable and unguarded** (the ones that fail the Acceptance Criteria): `cli/parallel.py:main_parallel` (`SQLiteTransport(resolve_history_db())` at `:327`, runs on default config because `events.transports` defaults to `[]`, before `ParallelOrchestrator` is built) and `cli/sprint/run.py:_cmd_sprint_run` (`history_db = resolve_history_db()` at `:566`, before the big `try`, on every non-dry-run sprint). The two further `SQLiteTransport(resolve_history_db())` sites in `_cmd_sprint_run` (`:660`, `:807`) sit inside the big `try`, whose `except Exception` converts the raise into sprint exit 1 rather than a skip. `transport.py:wire_transports` (`:2031`, `"sqlite"` branch) is unguarded whenever `"sqlite"` is configured and is reached from `main_parallel`, `_cmd_sprint_run`, `cli/loop/run.py:cmd_run` and the loop resume path.
- **`ll-loop run` startup is not itself broken** by a pre-resolve: its `resolve_history_db()` sites (`cli/loop/run.py:533`, `:595`) are inside `with suppress(Exception)` and gated on `--worktree`/exit hook. The loop-run failure modes are mid-run: `fsm/executor.py:_check_prepatch_check` (`:2017`, unguarded resolve feeding `read_base_sha`; the raise is caught only by `run()`'s outer `except Exception` → `_finish("error")`) and `fsm/continuity.py:summarize_completed_state` (`:52`; caller swallows via `except Exception: return None`).
