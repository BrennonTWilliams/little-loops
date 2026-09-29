---
id: BUG-3652
type: BUG
title: Audit resolve_history_db callers under a remote history backend
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T04:19:08Z'
verify_verdict: VALID
confidence_score: 95
outcome_confidence: 56
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
size: Large
---

# BUG-3652: Audit resolve_history_db callers under a remote history backend

## Summary

Under `history.backend.provider: libsql` (FEAT-3535), `resolve_history_db()` raises `HistoryBackendNotLocal` for the default location because a remote store has no local path. FEAT-3535 converted the event writers and hooks (which open through the target-aware `schema.connect` seam), but about 49 other call sites outside `session_store/` still call it. Nobody audited whether each sits inside a best-effort guard, so a remote-configured `ll-parallel`, `ll-sprint` or `ll-loop` run may fail at startup instead of degrading.

## Current Behavior

`resolve_history_db()` raises `HistoryBackendNotLocal` (a `HistoryUnsupported` subclass) when `history.backend` selects a remote provider and the path is default-shaped with `LL_HISTORY_DB` unset. Callers that do not catch it propagate the error. Call sites by file (counts from `grep "resolve_history_db("` outside `session_store/`): `cli/history.py` (8), `cli/harness.py` (5), `parallel/orchestrator.py` (4), `fsm/executor.py` (4), `parallel/worker_pool.py` (3), `cli/sprint/run.py` (3), `parallel/merge_coordinator.py` (2), `cli/loop/run.py` (2), `cli/logs.py` (2), `cli/doctor.py` (2, already remote-aware), and one each in `workspace.py`, `work_verification.py`, `user_messages.py`, `transport.py`, `runner_spec.py`, `mcp_server/tools.py`, `fsm/continuity.py`, `decisions.py`, `cli/parallel.py`, `cli/issues/set_status.py`, `cli/issues/research_triage.py`, `cli/ctx_stats.py`, `issue_history/workspace_quality.py`, `history_reader/_base.py`.

## Expected Behavior

Every caller either reaches the remote store correctly (a history read or write routed through `resolve_history_store` or the target-aware `schema.connect` seam), is guarded so a remote target degrades to "skip" for best-effort telemetry, or raises a clear `HistoryUnsupported` for an operation the remote store does not support. No `ll-*` startup path fails with an unhandled `HistoryBackendNotLocal`.

## Motivation

FEAT-3535 made `history.backend.provider: libsql` a supported configuration, but only the event writers and hooks were converted. Two main orchestrator startup paths (`cli/parallel.py:main_parallel`, `cli/sprint/run.py:_cmd_sprint_run`) and the shared `transport.py:wire_transports` sqlite branch still pre-resolve through `resolve_history_db()`, so a remote-configured user hits an unhandled `HistoryBackendNotLocal` before any work starts. Best-effort telemetry should never gate `ll-parallel` or `ll-sprint`; leaving the callers unaudited also means `ll-issues set-status` can change a status file and then raise. Loop YAMLs that gate on `ll-history summary`, `ll-parallel` or `ll-sprint run` (`loops/lib/cli.yaml`, `loops/sprint-build-and-validate.yaml`) flip to failure under a remote backend for the same reason.

## Proposed Solution

Audit each call site and classify it: (a) history read or write, so convert to `resolve_history_store` or pass the default-shaped path through the seam; (b) best-effort telemetry, so guard and skip on a remote target; (c) a local-file operation, so raise `HistoryUnsupported` naming the operation via `refuse_on_remote`. Add a test that drives `ll-parallel`, `ll-sprint` and `ll-loop` startup under the Hrana stub backend.

## Integration Map

### Files to Modify
- The call sites listed above.

_Wiring pass added by `/ll:wire-issue`:_
- `skills/improve-claude-md/SKILL.md` — inline `python3 -c` block calls `resolve_history_db()` then `detect_recurring_feedback(db, ...)`; a real class-(a) caller the table omits, raises under a remote backend in `Step CT-0: Get Evolution Trigger Candidates` [Agent 1 + 2 finding, confirmed at `:206-209`]. Editing a skill trips the mirror gates (`ll-adapt --host <gemini|kimi-code|qwen> --apply`)
- `scripts/little_loops/session_store/backend.py` — `_REMOTE_REFUSALS` needs one entry per new operation name passed to `refuse_on_remote(db, "<op>")` for class-(c) sites, else the message falls back to the generic "local-file operation" text, in `refuse_on_remote` [Agent 2 finding]
- `scripts/little_loops/decisions.py:596` — `generate_from_completed()` resolves then branches on `db_path.exists()` to pick `scan_completed_issues_from_db` vs the issues-dir scan; under remote the natural degrade is the issues-dir scan (the reader layer cannot take a `RemoteTarget`), in `generate_from_completed()` [Agent 2 finding]
- `scripts/little_loops/issue_history/parsing.py` — `issue_events_ever_recorded()` and `scan_completed_issues_from_db()` gate on `db_path.exists()` and coerce with `Path(db)`; only relevant if a class-(a) site is routed to the remote store rather than refused [Agent 2 finding]
- `scripts/little_loops/issue_history/evolution.py:39` — `_open_db()` gates on `db_path.exists()`, backs `detect_recurring_feedback()` which the `improve-claude-md` skill calls with the resolved path, in `_open_db()` [Agent 2 finding]

### Dependent Files
- `scripts/little_loops/session_store/db.py` (`resolve_history_db`, `resolve_history_store`, `resolve_history_target`)
- `scripts/tests/hrana_stub.py` (test double)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/lifecycle.py:752` — `cmd_resume()` calls `wire_transports(executor.event_bus, config.events)`, reaching the same unguarded `"sqlite"` branch as `main_parallel`/`_cmd_sprint_run`/`cmd_run`. No edit at this site: fixing `wire_transports` in `transport.py` covers it; it is the fifth `wire_transports` caller and the resume path needs its own remote-stub assertion, in `cmd_resume()` [Agent 1 finding]
- `scripts/little_loops/preparation_policy.py:1004` — `_set_status_checked()` calls `apply_status_transition(...)` in-process; inherits the `HistoryBackendNotLocal` raise (after the status file has been written). No edit here: fix inside `apply_status_transition` [Agent 2 finding]
- `scripts/little_loops/mcp_server/tools.py:367` — `_tool_issue_set_status()` calls `apply_status_transition(...)`; same propagation, converted to `is_error` by `call_tool` only after the file changed. No edit here [Agent 2 finding]
- `scripts/little_loops/cli/issues/decisions.py:390` — `cmd_decisions()` (the `generate` subcommand) is the only caller of `generate_from_completed()`; no edit here, but its exit-code/traceback behavior changes with the `decisions.py:596` fix [Agent 2 finding]
- `scripts/little_loops/cli/messages.py:281` — `main_messages()` is the only caller of `user_messages.extract_conversation_turns()` (site `user_messages.py:1198`); inherits whatever that site does [Agent 2 finding]
- `scripts/little_loops/cli/artifact/serve.py:92`, `scripts/little_loops/cli/artifact/dashboard.py:438`, `scripts/little_loops/cli/doctor_trim.py:373`, `scripts/little_loops/workflow_sequence/io.py:44` — not `resolve_history_db()` callers: they build `<root>/.ll/history.db` by hand and test `is_file()`/`.exists()`, so under a remote provider they silently act on a nonexistent local file (class (c)-shaped). Advisory; decide whether they are in scope for this audit or a follow-up [Agent 2 finding]
- `scripts/little_loops/loops/lib/cli.yaml:66` (`ll-history summary`), `scripts/little_loops/loops/lib/cli.yaml:120` (`ll-parallel`), `scripts/little_loops/loops/sprint-build-and-validate.yaml:156` (`ll-sprint run`) — gate consumers with no `|| true`, whose exit code flips to failure under a remote backend until the startup and `summary` sites are fixed. `evaluation-quality.yaml:46` and `backlog-flow-optimizer.yaml:35` already degrade via `|| echo "(no history available)"` [Agent 2 finding]
- `hooks/scripts/context-monitor.sh` — `record_handoff_needed()`/`record_context_pressure()` already swallow the raise with `>/dev/null 2>&1 || true` (silent drop, no exit-code change); no edit needed unless the rows should reach the remote store [Agent 2 finding]

### Tests
- New test module driving the three orchestrators under the remote stub; existing `test_remote_hooks.py` shows the fixture shape.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_worker_pool.py` — `test_dequeue_stamp_written_as_running_row()` (`:4531`) and `test_dequeue_stamp_normalizes_failed_rev_parse_to_null()` (`:4553`) each `patch.object(worker_pool_module, "resolve_history_db", ...)`; they raise `AttributeError` if `worker_pool.py` stops importing that name at module level. Keep the name or update both patches [Agent 3 finding, confirmed at `:4546`, `:4568`]
- `scripts/tests/test_set_status_cli.py` — `TestSetStatusHistoryDbErrorHandling::test_sqlite_error_is_caught_and_logged()` (`:1289`) pins exit 0 plus the `"failed to record issue_events"` log; `test_unrelated_exception_propagates()` (`:1329`) pins that a `ValueError` still propagates. Widening the guard to `HistoryError` keeps both valid; widening to `Exception` breaks the second [Agent 3 finding]
- `scripts/tests/test_libsql_backend.py` — `TestConfigResolution::test_resolve_history_db_raises_for_the_remote_target()` (`:137`) and `test_ensure_db_refuses_a_remote_target_before_any_mutation()` (`:322`) pin the `HistoryBackendNotLocal` contract; must stay green — the fix is at call sites, not in `resolve_history_db()` [Agent 3 finding]
- `scripts/tests/test_transport.py` — `test_sqlite_branch_ignores_log_dir_and_honors_ll_history_db()` asserts `resolve_history_db() == redirected`, and its docstring names the `SQLiteTransport(resolve_history_db())` fallback shape; update if `wire_transports` moves to `resolve_history_store` [Agent 3 finding]
- `scripts/tests/test_parallel_cli.py` — `TestParallelEnvVarSideEffects` drives `main_parallel()` in-process (only `ParallelOrchestrator` and `subprocess.run` patched) so `cli/parallel.py:327` runs for real; template for the `ll-parallel` startup-under-remote test [Agent 3 finding]
- `scripts/tests/test_cli_sprint.py` — `_run()` helper (~`:810`) patches `cli.sprint.run.*` and leaves `:566` unpatched; `scripts/tests/test_sprint_integration.py::test_sprint_wires_transports_per_wave()` (`:509`) uses a real project plus `MockOrchestrator`; templates for the `ll-sprint run` test [Agent 3 finding]
- `scripts/tests/test_ll_loop_execution.py` — `TestLoopExecution::test_executes_loop_to_terminal_state()` (`:97`) drives `main_loop()` with a mocked `Popen`; `scripts/tests/test_cli_loop_worktree.py` (`:914+`) drives `cmd_run(worktree=True)`; templates for the `ll-loop run` test [Agent 3 finding]
- `scripts/tests/test_fsm_continuity.py` — every case passes `db=tmp_path/"history.db"` (an explicit local target), so the default-`None` remote path of `summarize_completed_state()` is untested; add a remote case [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — `test_prepatch_runs_before_tamper_guard_and_tamper_wins_the_route()` (`:14798`) patches `prepatch_check.run_prepatch_check` and sets `LL_HISTORY_DB`; extend or sibling-test `_check_prepatch_check()` under remote (`:2017`) [Agent 3 finding]
- `scripts/tests/test_remote_doctor.py` — the only existing remote-aware *caller* test (`cli/doctor.py:_schema_drift_data`) and a second `remote` fixture variant (`_write(root, backend, extra)` config helper); there is no shared `remote` fixture in `conftest.py`, so the new module defines its own copy [Agent 3 finding]
- `scripts/tests/test_remote_operation_matrix.py` — `TestRejectedOperations` (`_REJECTED` list) asserts `ei.value.operation == operation` and that the stub saw no request; add rows for any new `refuse_on_remote` operation names [Agent 2 + 3 finding]
- `scripts/tests/test_history_store_chokepoint_gate.py` — `test_no_raw_sqlite_connect_outside_chokepoint_and_allowlist()` and `test_allowlist_entries_still_exist_and_still_have_raw_connects()` are the AST + allowlist + drift-check template for a new meta-test enumerating `resolve_history_db()` callers and pinning each classification; `scripts/tests/test_usage_selection_chokepoint_gate.py` is the `(rel_path, enclosing_function)`-keyed variant. Most sites import locally (`from little_loops.session_store import resolve_history_db`), so the detector must also match `ast.ImportFrom` [Agent 3 finding]
- `scripts/tests/test_improve_claude_md_skill.py` — covers `skills/improve-claude-md/SKILL.md`; re-run after editing the CT-0 block [Agent 2 finding]
- `scripts/tests/test_ll_issues_research_triage.py` (`:112-174`) and `scripts/tests/test_feat3182_evidence_bundle.py` (`:494-599`) call `resolve_history_db()` directly to read rows back; local-target only, unaffected, but they are the local twins if the site is converted [Agent 3 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:2957` — `AutoManager` § says `db_path` and `SQLiteTransport.__init__` resolve "via `resolve_history_db()`"; the constructor actually calls `resolve_history_store`, so the sentence is already stale and should be corrected with the audit in `AutoManager` [Agent 2 finding, confirmed at `:2957`, `:2959`]
- `docs/reference/API.md:5184` — `main_ctx_stats` § "the DB path resolves via `resolve_history_db()`"; update if the site gains a remote branch, in `main_ctx_stats` [Agent 2 finding]
- `docs/reference/API.md:13427` — `generate_from_completed` § says it reads `<project_root>/.ll/history.db` "when present, otherwise scans the issues directory"; add the remote behavior, in `generate_from_completed` [Agent 2 finding]
- `docs/reference/API.md:9946` — `Backend chokepoint: little_loops.session_store.backend` § calls the module the "SQLite-only prerequisite for a future remote provider" and its import list omits `HistoryBackendNotLocal`, `RemoteTarget`, `refuse_on_remote`, `resolve_history_store`, `resolve_history_target`, in `Backend chokepoint` [Agent 2 finding]
- `docs/ARCHITECTURE.md:758` — paragraph describing `session_store.backend` as the "SQLite-only chokepoint FEAT-3524's remote provider will register"; stale after FEAT-3535, in the `history.db` chokepoint paragraph [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:736` — `Remote history backend` § "Not supported remotely" bullet lists only `rebuild`, full `backfill`, `prune`, `compact`, `recompress`, `VACUUM`, `ATTACH`, snapshot export; add every command this audit ends up refusing or degrading (class (a)/(c)), in `Remote history backend` [Agent 2 finding]
- `docs/reference/CLI.md:4381` — the "Under a remote history backend…" paragraph exists only in the `ll-session` section; add a matching note to the `ll-history`, `ll-parallel`, `ll-sprint`, `ll-loop`, `ll-harness`, `ll-logs`, `ll-ctx-stats`, `ll-issues set-status`/`research-triage` sections for whatever behavior lands, in `ll-session` [Agent 2 finding]
- Gates: `scripts/tests/test_wiring_reference_docs.py` pins `history.backend.provider`, `Remote history backend` and `ll-session migrate`; `scripts/tests/test_docs_audience_gate.py` forbids `scripts/tests/`/`scripts/little_loops/` paths in `docs/guides`, `docs/reference` and `skills/` — cite `little_loops.<module>` in prose [Agent 2 finding]

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

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

**Additional conventions in force (gap-analysis pass — gate, CLI-boundary and test-shape rules):**
- No gate enumerates `resolve_history_db()` callers today. The AST gates share one shape: walk `_SRC_ROOT.rglob("*.py")` with `ast.walk`, match `ast.Call` nodes only, compare against a module-level `_ALLOWLIST` of reasoned entries, and pair it with a drift test that asserts stale or fully-migrated entries are empty ("remove these entries"). Evidence: `scripts/tests/test_history_store_chokepoint_gate.py`, `scripts/tests/test_host_resolution_chokepoint_gate.py`, `scripts/tests/test_usage_selection_chokepoint_gate.py`.
- Allowlist keys come in two shapes, and the gates disagree: path-only → reason (`test_history_store_chokepoint_gate.py`, `test_host_resolution_chokepoint_gate.py`) versus `(rel_path, enclosing_function)` → reason with an `id(node) → func` owner map (`test_usage_selection_chokepoint_gate.py:_enclosing_functions`). Per-function classification (a)/(b)/(c) needs the second shape. Only the usage gate lacks a drift test. The host and usage gates also carry detector self-tests (`test_gate_detects_a_stray_site`).
- No existing gate inspects `ast.ImportFrom`; a function-local `from x import name` is caught only because `ast.walk` descends into nested bodies and the call is matched by `Name.id`. The classification gate can rely on that and need not add `ImportFrom` matching, unless a site aliases the import.
- No gate scans `skills/` or `hooks/scripts/`. The two non-Python callers (`skills/improve-claude-md/SKILL.md` CT-0 block, `hooks/scripts/context-monitor.sh`) sit in `python -c`/heredoc text and are outside every gate; the nearest audit is behavioral (`scripts/tests/test_history_target_hook_audit.py`, a `_resolve_once` spy over 9 hook paths).
- CLI boundaries turn `HistoryError` into a clean exit 1 by writing `<prefix>: <exc>` to stderr with no traceback. Two styles exist and disagree: `Logger.error` with `except HistoryError` (`cli/session.py:_main_migrate`) versus bare `print(..., file=sys.stderr)` with the narrower `except HistoryUnsupported` (`cli/backfill_worker.py:main`). `cli/session.py:main_session` has no handler. Every other `except HistoryError` site degrades silently (`cli/logs.py`, `cli/ctx_stats.py`, `cli/history.py:807`, `history_reader/_base.py`) rather than exiting.
- The refusal text is `"{operation} is not supported under history.backend provider 'libsql': {why}"` (`refuse_on_remote`, `session_store/backend.py`); `resolve_history_db` itself raises `"history.backend provider {p!r} has no local database path"` with `operation="resolve_history_db"` (`session_store/db.py`). Refusal tests assert exit code, operation name plus `"libsql"` in stderr, `"Traceback" not in err`, and zero requests seen by the stub (`test_remote_hooks.py::TestBackfillWorker`, `test_remote_operation_matrix.py::TestRejectedOperations`).
- "Skip on remote" is inlined as `isinstance(<store>, RemoteTarget)` with function-local imports at 5 sites outside `session_store/` (`cli/session.py` ×2, `worktree_utils.py:export_history_db_env`, `hooks/session_start.py` ×2, `cli/doctor.py:_remote_target`); `RemoteTarget` is imported from `session_store.targets` at most sites but from `session_store.backend` at `cli/session.py:462`. Adding a fourth-plus inline check is consistent with the codebase; introducing a shared predicate would be a new convention.
- Test fixtures re-declare per file (no `remote` in `conftest.py`). The shared recipe is `HranaStub(token=TOKEN).start()`, env `LL_HISTORY_AUTH_TOKEN`/`LL_HISTORY_URL`, `delenv("LL_HISTORY_DB")`, config with `url_env` and `project_id`, `chdir(tmp_path)`, `clear_verification_cache()` + `clear_backend_config_cache()` (plus `remote_telemetry.reset_for_tests()` in three fixtures) before and after, then `migrate_remote`. `TOKEN = "sentinel-token-DO-NOT-LEAK"` is asserted absent from output. CLIs are driven via `monkeypatch.setattr(sys, "argv", [...])` then `main_x()`, or by passing an argv list to `main([...])`.
- Docs convention for per-CLI remote behavior: a bold lead-in ("**Under a remote history backend** …") plus a comma-separated list of refused operations, stating they are refused "before any network call" and that reads still work (`docs/reference/CLI.md` `ll-session` section; `docs/reference/CONFIGURATION.md` `Remote history backend` bullets, which carry no issue IDs). No CLI other than `ll-session` has such a paragraph today.

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
   > ⚠ Superseded — table omits the `skills/improve-claude-md/SKILL.md` CT-0 call
2. `ll-parallel` and `ll-sprint run` start under the Hrana stub with `LL_HISTORY_DB` unset and reach their first phase; the two unguarded startup sites and the `wire_transports` sqlite branch no longer raise. `ll-loop run` (with and without `--worktree`, and a state using `prepatch_check`/`session_mode: continue`) completes without a `HistoryBackendNotLocal`.
3. Best-effort (b) sites degrade to skip on `HistoryError`, including `apply_status_transition` (the status file must not change and then raise); reader (a) commands either reach the remote store or raise a clear `HistoryUnsupported` naming the operation — none surfaces a bare `HistoryBackendNotLocal` traceback.
4. Coverage: a new remote-stub test module in the `test_remote_*.py` family drives the three orchestrators' startup using the `remote` fixture shape (including the `LL_HISTORY_DB` delenv) plus a dead-endpoint case asserting startup still succeeds; a local-provider twin proves behavior is unchanged. Existing tests that patch `resolve_history_db` by name (`test_worker_pool.py`, `test_transport.py`, `test_cli_harness.py`) keep passing or are updated with the change.
5. `python -m pytest scripts/tests/` passes with the default local store; `ruff check` and `mypy` clean on touched files (scope `ruff format` to changed files).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `skills/improve-claude-md/SKILL.md` — classify the `Step CT-0` `resolve_history_db()` call and guard or degrade it under remote (keep the block short: SKILL.md is capped at 500 lines); then run `ll-adapt --host <gemini|kimi-code|qwen> --apply` to clear the mirror gates and re-run `scripts/tests/test_improve_claude_md_skill.py`
- Update `scripts/little_loops/session_store/backend.py` — add a `_REMOTE_REFUSALS` entry for each new `refuse_on_remote(db, "<op>")` operation name, and add matching rows to `_REJECTED` in `scripts/tests/test_remote_operation_matrix.py::TestRejectedOperations`
- Update `scripts/little_loops/decisions.py` `generate_from_completed()` — on a `RemoteTarget`, fall back to the issues-directory scan instead of `resolve_history_db(...).exists()`; `cli/issues/decisions.py:cmd_decisions` and the `test_decisions.py`/`test_cli_decisions.py` cases (`generate_from_completed` at ~`:944-975`, ~`:1399-1435`) need a remote twin
- Update `scripts/little_loops/transport.py` `wire_transports()` — this single fix also covers `cli/loop/lifecycle.py:cmd_resume`, `cli/loop/run.py:cmd_run`, `cli/parallel.py` and `cli/sprint/run.py`; add a `cmd_resume` assertion to the remote-stub startup tests rather than editing `lifecycle.py`
- Update `scripts/little_loops/cli/issues/set_status.py` `apply_status_transition()` — widen the guard to include `HistoryError` (not `Exception`, to keep `test_unrelated_exception_propagates` valid); `preparation_policy._set_status_checked` and `mcp_server.tools._tool_issue_set_status` inherit the fix
- Update `scripts/tests/test_worker_pool.py` — keep a module-level `resolve_history_db` name in `parallel/worker_pool.py` or update the two `patch.object(worker_pool_module, "resolve_history_db", ...)` sites (`:4546`, `:4568`)
- Update `scripts/tests/test_transport.py::test_sqlite_branch_ignores_log_dir_and_honors_ll_history_db` — adapt if `wire_transports` stops calling `resolve_history_db()`
- Add a caller-classification meta-test modeled on `scripts/tests/test_history_store_chokepoint_gate.py` (AST walk of `scripts/little_loops/` keyed by `(rel_path, enclosing_function)` with a drift check), matching `ast.ImportFrom` as well as calls; extend it or add a sibling assertion for the `skills/` and `hooks/scripts/` shell callers
- Add `scripts/tests/test_fsm_continuity.py` and `scripts/tests/test_fsm_executor.py` remote cases — `summarize_completed_state()` with `db=None`, and `_check_prepatch_check()` under a `prepatch_check` policy
- Update docs — `docs/reference/API.md` (`AutoManager`, `main_ctx_stats`, `generate_from_completed`, `Backend chokepoint`), `docs/ARCHITECTURE.md:758`, `docs/reference/CONFIGURATION.md` `Remote history backend`, `docs/reference/CLI.md` per-CLI remote notes; keep `test_wiring_reference_docs.py` and `test_docs_audience_gate.py` green
- Decide scope for the hand-built `.ll/history.db` paths in `cli/artifact/serve.py`, `cli/artifact/dashboard.py`, `cli/doctor_trim.py` and `workflow_sequence/io.py` (advisory; class (c)-shaped, not `resolve_history_db()` callers)

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


## Verification Notes

Verdict at time of check: **CLAIMS_OUTDATED** (correction below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Integration Map (Dependent Files): `cli/messages.py:280` -> `:281`. The `extract_conversation_turns()` call is at line 281 (import at :276); :280 is the closing bracket of the preceding `formatter = {...}[...]` expression.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-29_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 56/100 → LOW

### Concerns
- Class (a) reader sites (`cli/history.py`, `cli/harness.py`, `cli/logs.py`, `decisions.py`, `user_messages.py`) have no per-site verdict yet: "reach the remote store or raise `HistoryUnsupported`" is left to implementer judgement, and the reader layer coerces with `Path(db)`, so routing to remote is not a call-site-only change.
- Scope of the hand-built `.ll/history.db` paths (`cli/artifact/serve.py`, `dashboard.py`, `doctor_trim.py`, `workflow_sequence/io.py`) is undecided (advisory).
- Guard style disagrees across the codebase (narrow tuple in `set_status.py` vs broad `Exception` elsewhere); the issue picks `HistoryError`, which is consistent with the Decision Rules.

### Outcome Risk Factors
- Broad enumeration across ~45 call sites plus docs/tests, with moderate per-site depth on the reader layer and `wire_transports`/`apply_status_transition` (shared by 3-5 callers each).
- Broad blast radius: `wire_transports` feeds 5 callers and `apply_status_transition` feeds the CLI, MCP tool and `preparation_policy`; mitigate by landing the two startup fixes and the `HistoryError` guard first, then the classification meta-test, with reader sites defaulting to a named `refuse_on_remote` refusal.

## Session Log
- `/ll:confidence-check` - 2026-09-29T05:15:44 - `bf65814b-8af2-43a0-8fe0-ec16e1b4857f.jsonl`
- `/ll:verify-issues` - 2026-09-29T05:14:12 - `ae0846b5-655f-4247-a75a-7ca807ba2469.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-29T05:12:10 - `a5edb1e1-9d75-4b79-af5e-93bf4804228c.jsonl`
- `/ll:verify-issues` - 2026-09-29T05:07:48 - `1bca72e1-aabf-43e5-89dc-106f3cd4dbd4.jsonl`
- `/ll:verify-issues` - 2026-09-29T05:06:02 - `4f909cde-90d0-4dc3-a3b6-39c01e60c85b.jsonl`
- `/ll:verify-issues` - 2026-09-29T05:05:13 - `ae1f9ace-139a-4564-bae7-910f1fa96a3f.jsonl`
- `/ll:wire-issue` - 2026-09-29T05:02:56 - `691a1ba6-9149-45d1-a9b7-21fe49d19962.jsonl`
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
