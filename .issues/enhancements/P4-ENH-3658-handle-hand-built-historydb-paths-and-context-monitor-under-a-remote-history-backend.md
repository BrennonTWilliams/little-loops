---
id: ENH-3658
type: ENH
title: Handle hand-built history.db paths and context-monitor under a remote history
  backend
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T05:29:44Z'
decision_needed: false
reconcile_attempted: true
verify_verdict: VALID
confidence_score: 95
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3658: Handle hand-built history.db paths and context-monitor under a remote history backend

## Summary

Four sites build `<root>/.ll/history.db` by hand and test `is_file()` / `.exists()` instead of calling `resolve_history_db()`. Under `history.backend.provider: libsql` they silently act on a nonexistent local file. `hooks/scripts/context-monitor.sh` also silently drops its handoff and context-pressure rows under a remote backend. Split out of BUG-3652 (these are not `resolve_history_db()` callers, so its grep-based audit never sees them).

## Current Behavior

- `cli/artifact/serve.py:92`, `cli/artifact/dashboard.py:438`, `cli/doctor_trim.py:373`, `workflow_sequence/io.py:44` build the local path directly and treat a missing file as "no history".
- `hooks/scripts/context-monitor.sh`: `record_handoff_needed()` / `record_context_pressure()` swallow the `HistoryBackendNotLocal` raise with `>/dev/null 2>&1 || true`, so the rows never reach the remote store.

## Expected Behavior

Class (c)-shaped sites refuse or skip explicitly instead of silently reading a nonexistent file: `doctor_trim` calls `refuse_on_remote(db, "trim")`; the artifact and workflow-sequence sites skip with a stated reason on a `RemoteTarget`. Decide per site whether the `context-monitor.sh` rows should reach the remote store (route via the target-aware seam) or stay a documented silent drop.

## Motivation

These sites fail quietly rather than aborting, so they were missed by BUG-3652's `resolve_history_db()` grep audit; under a remote backend they read a nonexistent local file or drop rows without saying so.

## Proposed Solution

Classify each site as class (c) (needs a local file): resolve via `resolve_history_target`, then refuse (`refuse_on_remote`) or skip with a stated reason on a `RemoteTarget`. For `context-monitor.sh`, either route the two `record_*` calls through the target-aware seam or document the silent drop.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

**Conventions in force**
- Sites never inspect provider config themselves; they test the resolver's result type (`isinstance(..., RemoteTarget)`) — evidence: `worktree_utils.py:export_history_db_env`, `hooks/session_start.py`, `cli/session.py:_is_foreign_path`. Those inline skips are silent (the reason lives in a code comment); none logs a line.
- Refusals raise `HistoryUnsupported` naming the operation before any I/O, and the catcher owns exit code and message shape. Existing catchers disagree: `cli/backfill_worker.py:main` prints a prefixed line to stderr and returns 1; `cli/session.py:_main_migrate` logs via `logger.error` and returns 1; the mutating `ll-session` subcommands have no handler and let it propagate; `cli/doctor.py` `_*_data()` helpers never raise and return an `unsupported`/informational dict via `_remote_target()`. A contested convention — the implementer picks per site.
- Remote tests use a per-file `remote` fixture (`HranaStub` + libsql `ll-config.json` + `chdir` + cache clears; `delenv("LL_HISTORY_DB")` because the autouse `_isolate_history_db` sets it), assert no `Traceback`, no token leak and an unchanged `remote.requests` count for refusals, and pair each with a local twin (explicit local path / `LL_HISTORY_DB`). `_REJECTED` in `test_remote_operation_matrix.py` is a `(operation, callable)` list asserting `HistoryUnsupported`, `.operation`, `"libsql"` in the message, and no network call; every current `_REMOTE_REFUSALS` key has a row, though no meta-test enforces it.
- New user-facing doc strings are pinned in `test_wiring_reference_docs.py::DOC_STRINGS_PRESENT` as `(doc_path, string, issue_id)`; `docs/reference/` text must use end-user shapes (`test_docs_audience_gate.py`).

**Option A**: Route the two `context-monitor.sh` rows to the remote store by dropping the `resolve_history_db()` pre-resolve and passing the literal default-shaped `.ll/history.db` to the writers, as the in-process hooks do; the seam then resolves to the remote target under `telemetry_scope()`, and the shell `|| true` remains the fail-soft guard.

> **Selected:** Option A — sibling hooks already hand the writers a default-shaped path and rely on the seam; the drop is an artifact of the pre-resolve.

**Option B**: Keep the silent drop for `context-monitor.sh` and document it in `docs/reference/CONFIGURATION.md` (Remote history backend) as a known non-supported write.

**Recommended**: Option A — the seam already handles a default-shaped path for every sibling hook, so the drop is an accident of the pre-resolve rather than a capability gap; precedent exists (`hooks/post_tool_use.py`, `hooks/scripts/record-hook-event.sh`), so no spike is needed. Verify it under a `HranaStub` remote fixture (rows arrive) and with the stub stopped (hook exits 0, no stderr leak).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-29.

**Selected**: Option A

**Reasoning**: `hooks/post_tool_use.py` (`connect(cwd / ".ll" / "history.db")`), `user_prompt_submit.py`, `pre_compact.py` and `record-hook-event.sh` already pass a default-shaped path and reach the remote store through `_seam_target()`; `context-monitor.sh` (lines 58, 84) is the only hook that pre-resolves via `resolve_history_db()`, which raises `HistoryBackendNotLocal` before the writer runs. Removing the pre-resolve is a two-line change and the shell `|| true` (pinned by `test_python_failure_does_not_flip_exit_code`) stays the fail-soft guard. Option B leaves handoff/pressure telemetry silently lost under a remote backend and adds a documented gap that contradicts the sibling hooks.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 2/3 | 2/3 | 10/12 |
| Option B | 1/3 | 3/3 | 3/3 | 2/3 | 9/12 |

**Key evidence**:
Selected option: four in-process hooks plus `record-hook-event.sh` are precedent; the writers accept `Path | str`. Testing needs a `HranaStub` fixture around a shell hook, since no test runs `context-monitor.sh` under remote today.

Rejected option: needs only a doc string pinned in `test_wiring_reference_docs.py::DOC_STRINGS_PRESENT`, but institutionalises data loss that no other hook has.

## Scope Boundaries

- In scope: the four hand-built `.ll/history.db` paths and `hooks/scripts/context-monitor.sh`.
- Out of scope: `resolve_history_db()` callers (BUG-3652 for startup/write paths, ENH-3657 for readers).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact/serve.py` (two sites), `cli/artifact/dashboard.py`, `cli/doctor_trim.py`, `cli/loop/run.py`, `cli/doctor.py`, `hooks/scripts/context-monitor.sh`. `workflow_sequence/io.py` needs no change (correct JSONL degrade). A `session_store/backend.py` `_REMOTE_REFUSALS` `trim` entry is optional (generic refusal wording applies).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/serve.py:173` — second hand-built site in `_make_page_html_factory()` (`db_path=config.project_root / ".ll" / "history.db"` into `build_dashboard_html`); the first is `make_history_route()` at `:92`, whose `db_path.stat()` ETag key also reads the local file [Agent 1 finding, confirmed by grep]
- `scripts/little_loops/cli/loop/run.py:691` — hand-built `db_path=_config.project_root / ".ll" / "history.db"` in the `ll-loop run --serve` dashboard render (`build_dashboard_html(..., serve_context=serve_ctx)`); same `allow_missing` degrade, no `except` around it, so an uncaught raise here would abort `--serve` startup [Agent 1 + Agent 2 finding, confirmed by grep]
- `scripts/little_loops/cli/doctor.py:1836` — `main_doctor` call to `collect_trim_report(Path.cwd(), window_days=...)` needs a handler (or `collect_trim_report` must skip rather than raise) to keep `--trim` advisory; `main_doctor` runs inside `cli_event_context`, which re-raises with `exit_code = 1` [Agent 1 + Agent 2 finding]
- `hooks/scripts/context-monitor.sh:56-58` in `record_handoff_needed()` and `:82-84` in `record_context_pressure()` — the two `resolve_history_db(".ll/history.db")` pre-resolves to drop under Option A; also drop the now-unused `resolve_history_db` from the two `from little_loops.session_store import ...` lines [Agent 1 finding, confirmed by grep]

### Dependent Files (Callers/Importers)
- Callers of the modified functions: `cmd_serve` (→ `make_history_route`, `_make_page_html_factory`), `cmd_dashboard`, `main_doctor` (→ `collect_trim_report`), `ll-loop run --serve`; `hooks/scripts/context-monitor.sh` calls the `record_*` writers.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/serve.py:212-213` — `cmd_serve` calls `make_history_route(config)` and `_make_page_html_factory(...)`; the route only catches `ValueError` (→ HTTP 413), so a `HistoryUnsupported` from `build_snapshot_db` propagates out of the handler [Agent 1 + Agent 2 finding]
- `scripts/little_loops/cli/artifact/dashboard.py:459` — `cmd_dashboard` calls `build_dashboard_html`; `build_dashboard_html` (`:294`) calls `build_history_payload(allow_missing=serve_context is not None)`, which raises `ValueError("history database not found: …")` when the file is absent [Agent 1 + Agent 2 finding]
- `scripts/little_loops/workflow_sequence/analysis.py:658` in `analyze_workflows()` — sole caller of `_load_messages_from_db`; passes `db_path` from its own param (default `None`); `workflow_sequence/__init__.py:243` (`analyze` CLI) passes no `db_path`, so no source path reaches `io.py:44` today [Agent 1 finding]
- `scripts/little_loops/cli/logs.py:997,1002` in `_cmd_dead_skills()` and `:1535,1539` in `_cmd_stats()` — further hand-built `<project>/.ll/history.db` sites feeding `_aggregate_skill_stats` (`--project` override paths; `:1556` logs "No history.db found"); these are **reader CLIs owned by ENH-3657**, not this issue — record only to prevent double-fixing [Agent 1 finding, confirmed by grep]
- `scripts/little_loops/hooks/adapters/`, `.claude-plugin/plugin.json` — no `context-monitor.sh` reference; `hooks/hooks.json:137-138` is its only registration (PostToolUse, matcher `*`, `timeout: 5`), so no host-mirror or manifest edit is needed [Agent 1 + Agent 2 finding]

### Similar Patterns
- Inline `isinstance(<store>, RemoteTarget)` skips in `worktree_utils.py:export_history_db_env`, `hooks/session_start.py`, `cli/session.py`; `cli/doctor.py:_remote_target()`.

### Tests
- `scripts/tests/test_remote_doctor.py`, `test_remote_operation_matrix.py` (`_REJECTED`), `test_remote_hooks.py` (fixture shape).

_Wiring pass added by `/ll:wire-issue`:_

**Existing tests that pin current behavior — must stay green (local path unchanged):**
- `scripts/tests/test_feat3304_artifact_dashboard.py` — `TestServeModeBuildDashboardHtml::test_missing_db_with_serve_context_renders_empty_snapshot_instead_of_failing` (empty-snapshot degrade), `test_missing_db_without_serve_context_raises` and `TestBuildHistoryPayload::test_allow_missing_false_raises_on_missing_db` (both `match="history database not found"`), `test_allow_missing_true_returns_empty_payload_without_creating_file`; keep the remote check at the call sites (`make_history_route`, `_make_page_html_factory`, `run.py`) or keyed on `RemoteTarget`, not on "any non-file" [Agent 3 finding]
- `scripts/tests/test_feat3304_artifact_dashboard.py` — `TestMissingDatabase::test_missing_history_db_exits_1` (exit 1, no output file — a remote refusal that also returns 1 stays green) and `test_cmd_dashboard_delegates_to_build_dashboard_html_with_no_serve_context` (pins exact `build_dashboard_html` kwargs; breaks if `cmd_dashboard`'s call signature changes) [Agent 3 finding]
- `scripts/tests/test_feat3323_sse_bridge.py` — `TestHistoryRoute::test_never_migrates_or_creates_missing_db` (HTTP 200, empty gzip payload, no `history.db` created; local config so it stays green) and `TestCmdServeHistoryGate::test_history_enabled_passes_route_and_factory` (breaks if the remote check moves into `cmd_serve` and drops `routes`/`page_html_factory`) [Agent 3 finding]
- `scripts/tests/test_cli_doctor_trim.py` — `TestAbsentTelemetry::test_missing_db_scores_nothing_as_trim` / `test_db_without_skill_events_table_scores_nothing_as_trim` (local `usage_available is False`; the remote branch must be purely additive) and `TestExitCodeIsolation::test_trim_findings_do_not_affect_exit_code` (`main_doctor(["--trim"]) == main_doctor([])` — the advisory-exit-code pin any `main_doctor` handler must keep green) [Agent 2 + Agent 3 finding]
- `scripts/tests/test_workflow_sequence_analyzer.py` — `test_db_source_falls_back_to_jsonl_when_empty` (silent JSONL fallback for a missing db; breaks if `_load_messages_from_db` starts raising or logging) [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py` — `TestContextMonitor::test_writes_lifecycle_row_on_threshold_crossing`, `test_writes_pressure_row_every_call`, `test_pressure_row_records_threshold_crossing`, `test_python_failure_does_not_flip_exit_code` (`|| true` guard) and `test_pressure_write_survives_broken_history_db`; all set `LL_HISTORY_DB`, so they resolve local and stay green after dropping the pre-resolve; `timeout=6` per run [Agent 2 + Agent 3 finding]
- `scripts/tests/test_pre_compact.py::TestContextMonitorContract::test_check_compaction_reads_compacted_at` — greps `context-monitor.sh` for `check_compaction` and `.compacted_at`; both must survive the shell edit [Agent 2 + Agent 3 finding]
- `scripts/tests/test_portability_gate.py` — scans `hooks/**/*.sh`; any new shell syntax in `context-monitor.sh` runs through it [Agent 2 finding]

**New tests to write (no existing coverage):**
- `scripts/tests/test_remote_hooks.py` (or a new `test_remote_context_monitor.py`) — `context-monitor.sh` run as a subprocess under the `remote` fixture (`LL_HISTORY_URL`/`LL_HISTORY_AUTH_TOKEN` set, `LL_HISTORY_DB` deleted, cwd `tmp_path`): assert the lifecycle and pressure rows arrive in `remote.db`, no local `.ll/history.db` is created, and a stopped stub with low `telemetry_timeout_ms` leaves exit 0 (2 with `LL_HANDOFF_THRESHOLD=1`) and empty stderr; pair with a `LL_HISTORY_DB` local twin (closest pattern: `test_hooks_integration.py::TestContextMonitor::test_writes_lifecycle_row_on_threshold_crossing` + `test_remote_hooks.py::TestPostToolUse::test_a_dead_endpoint_never_fails_the_hook`) [Agent 3 finding]
- `scripts/tests/test_remote_doctor.py` — `main_doctor(["--trim"])` under `remote`: exit code equals `main_doctor([])`, no `Traceback`, no `TOKEN` in output; needs the two autouse canned-hint fixtures from `test_cli_doctor_trim.py` (`_canned_model_hints`, `_canned_code_query`); local twin in `test_cli_doctor_trim.py` [Agent 3 finding]
- `scripts/tests/test_feat3323_sse_bridge.py` — `TestHistoryRoute` sibling under a libsql config: reason surfaced, `len(remote.requests)` unchanged, no `history.db` created, plus `--db`/local twin; `_make_page_html_factory` has no direct test today — follow the direct-call style of `test_missing_db_with_serve_context_renders_empty_snapshot_instead_of_failing` [Agent 3 finding]
- `scripts/tests/test_feat3304_artifact_dashboard.py` — `cmd_dashboard` under `remote` via the `_run` helper: exit 1, message names `libsql` (not "history database not found"), no `Traceback`; `--db` override twin still runs locally [Agent 3 finding]
- `scripts/tests/test_remote_operation_matrix.py::_REJECTED` — add `("trim", lambda: refuse_on_remote(Path(".ll/history.db"), "trim"))`; no meta-test enforces the key set, so the row is manual; ENH-3657 edits the same list — merge, don't overwrite [Agent 3 finding]
- `cli/loop/run.py` `--serve` dashboard render — no test drives it (`build_dashboard_html`/`ServeContext` appear only in test_feat3304/3323/3504 and test_enh3558_escape_ingest); closest pattern is the patched-`build_dashboard_html` spy at `test_feat3304_artifact_dashboard.py::test_cmd_dashboard_delegates_to_build_dashboard_html_with_no_serve_context` [Agent 3 finding]
- `scripts/tests/test_history_target_hook_audit.py::_PATHS` — optional `context_monitor` entry; its helpers are in-process, so a shell hook needs a `subprocess` wrapper or a direct `record_session_lifecycle_event(root/".ll"/"history.db", ...)` call [Agent 2 + Agent 3 finding]

### Documentation
- `docs/reference/CONFIGURATION.md` (Remote history backend), `docs/reference/CLI.md`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:723-739` in `Remote history backend` — "Not supported remotely" bullet lists `rebuild`, `backfill`, `prune`, `compact`, `recompress`, `VACUUM`, `ATTACH`, snapshot export but not `--trim` / `ll-artifact dashboard` / `serve`; the "Never stalls a hook" bullet (`telemetry_timeout_ms`, 60s unreachable marker, "not buffered or replayed") is what covers Option A's remote writes; `:984` (snapshot-export policy "for `ll-artifact dashboard`") and `:1801` (`events.bridge.history`) may need a remote note; keep the strings pinned by `test_wiring_reference_docs.py::DOC_STRINGS_PRESENT` (`history.backend.provider`, `history.backend.project_id`, `Remote history backend`) [Agent 2 finding]
- `docs/reference/CLI.md:502-541` in `Context residency (--trim)` — says absent telemetry renders entries `keep`/not scored and `--trim` "never affects `ll-doctor`'s exit code"; add the remote outcome; `:5468-5503` in `ll-artifact dashboard` lists "a missing history database" as an exit-1 cause — add the remote refusal; `:5385-5386` subcommand table rows for `dashboard`/`serve` [Agent 2 finding]
- `docs/reference/API.md:10528` (`record_session_lifecycle_event` / `record_context_pressure_event`), `docs/ARCHITECTURE.md:703,808`, `docs/guides/HISTORY_SESSION_GUIDE.md:144,148` — assert the writers "never raise"; under a remote backend `HistorySuppressed`/`HranaUnavailable` are not `sqlite3.Error`, so the shell `|| true` is the guard — reword only if Option A ships [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md:681` — "edit … lines 53-109" of `context-monitor.sh`; a shell edit can shift those line numbers; `test_wiring_guides_and_meta.py:165` pins the `hooks/scripts/context-monitor.sh` reference — keep it [Agent 2 finding]
- New user-facing sentences must be end-user shaped (`test_docs_audience_gate.py` forbids `scripts/tests`, `this repo`, `scripts/little_loops/`) and pinned in `test_wiring_reference_docs.py::DOC_STRINGS_PRESENT` as `(doc_path, string, "ENH-3658")` [Agent 2 finding]
- `site/` copies are generated from `docs/` — not hand-edited [Agent 2 finding]

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- No config-schema change: `history.backend.*` keys (`config-schema.json`, `CONFIGURATION.md:620-625`) are unchanged; `telemetry_timeout_ms` (default 1500) and the hook `timeout: 5` in `hooks/hooks.json:138` bound Option A's latency [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

**Backend seam (constraints, not a route)**
- Detection lives once in `session_store/db.py:resolve_history_target()`: it yields a `RemoteTarget` only when the provider is non-sqlite, the path is default-shaped (`None`, or any `<x>/.ll/history.db` — absolute paths included, via `_is_default_shaped`), and `LL_HISTORY_DB` is unset. An explicit non-default path (e.g. a `--db` override) or `LL_HISTORY_DB` stays a `LocalTarget`, so a remote check must never fire on an override.
- `resolve_history_store()` returns `Path | RemoteTarget`; `resolve_history_db()` raises `HistoryBackendNotLocal` on a remote target.
- `session_store/backend.py:refuse_on_remote(db, operation)` raises `HistoryUnsupported` (with `.operation` set) and does no I/O. Its `_REMOTE_REFUSALS` dict has no `trim` key; an unlisted operation falls back to the generic "local-file operation" reason, so a `trim` entry is only needed for a specific reason text, not for the refusal to work. The only current callers are inside `session_store/` (`lifecycle.py`, `queries.py`); no `cli/` module calls it.
- `refuse_on_remote` resolves with no `root=`, so it reads backend config from cwd.

**Per-site ground truth (scope corrections to the issue text)**
- `cli/artifact/serve.py` has **two** hand-built sites, not one: `make_history_route()` (`db_path = config.project_root / ".ll" / "history.db"`, no `--db` override) and `_make_page_html_factory()` (same path fed to `build_dashboard_html` inside a `ServeContext`). Both call through `build_history_payload(..., allow_missing=True)`, which returns an empty gzip payload with `source_version=None` when the file is missing — so under remote today the `/history` route and the served page silently show an empty snapshot with HTTP 200. `make_history_route` takes only `config` (no `Logger`); a stated reason must fit the handler's payload/status contract.
- `cli/loop/run.py` (`build_dashboard_html(db_path=_config.project_root / ".ll" / "history.db", ..., serve_context=serve_ctx)`, ~line 691) is a **fifth hand-built site** the issue does not list; it uses the same `allow_missing` degradation via `serve_context`.
- `cli/artifact/dashboard.py:cmd_dashboard()` builds the path only when `--db` is absent; a missing file logs a "history database not found" error and returns 1 — a misleading message under remote. The function body is wrapped in a broad `except Exception` that logs and returns 1. `build_snapshot_db()` (`session_store/queries.py`) already calls `refuse_on_remote(db, "snapshot_export")`, but is unreachable because the `is_file()` check runs first.
- `cli/doctor_trim.py:collect_trim_report()` has a `db_path` override param; when `None` it builds the default path and hands it to `_usage_counts()`, which returns `(None, 0)` on a missing file. `TrimReport.usage_available=False` renders as "no usage telemetry — verdicts skipped", indistinguishable from a fresh install. Its only non-test caller is `cli/doctor.py:main_doctor` (`collect_trim_report(Path.cwd(), window_days=args.trim_window_days)`, never passing `db_path`) with **no try/except**, and `--trim` is documented as advisory (never affects `ll-doctor`'s exit code). A raising `refuse_on_remote(db, "trim")` therefore propagates out of `main_doctor` through `cli_event_context` unless a handler is added — the issue's `refuse_on_remote` prescription and the advisory contract pull in opposite directions (see Proposed Solution).
- `workflow_sequence/io.py:_load_messages_from_db()` does **not** build the path: it receives `db_path` and tests `db_path.exists()`. Its sole caller is `workflow_sequence/analysis.py:analyze_workflows(..., db_path=None)`, which falls back to the JSONL messages file when the result is empty. The CLI (`workflow_sequence/__init__.py`, `analyze`) passes no `db_path`; the only in-repo `db_path=` callers are tests. So the remote failure mode is already a *correct* silent degrade to JSONL; the hand-built default-path construction is in the caller's caller, not `io.py:44`.

**`context-monitor.sh`**
- `record_handoff_needed()` and `record_context_pressure()` pass `resolve_history_db(".ll/history.db")` as the writer's first argument, so `HistoryBackendNotLocal` raises **before** the writer runs; `>/dev/null 2>&1 || true` (and the `&& record_* || true` call sites) swallow it. No row is written and nothing is logged.
- The blocker is the pre-resolve, not the writers: `record_session_lifecycle_event()` and `record_context_pressure_event()` (`session_store/writers.py`) accept `Path | str` and open through `_connect_telemetry()` → `schema.connect()` → `_seam_target()`, which resolves a default-shaped path to the remote target inside `remote_telemetry.telemetry_scope()`. `hooks/post_tool_use.py`, `hooks/user_prompt_submit.py`, `hooks/pre_compact.py` and `hooks/sweep_stale_refs.py` already hand the writers a literal default-shaped path and rely on that seam (`test_history_target_hook_audit.py` pins it for those paths); `hooks/scripts/record-hook-event.sh` → `ll-session record-hook-event` is an existing shell-to-remote route.
- The writers catch only `sqlite3.Error`, not `HistoryError` (`HistorySuppressed`, `HranaUnavailable`); their docstrings promise "never raises" but a remote failure would propagate to the `|| true`. Under BUG-3652's writer-level fail-soft plan the `record_*` writers keep propagating and "their call sites own the guard" — here the shell `|| true` is that guard.
- `session_store/__init__.py` exports `resolve_history_db` but not `resolve_history_store`/`resolve_history_target`/`RemoteTarget`; shell snippets needing them must import from `session_store.db` / `session_store.targets`.
- No `hooks/scripts/*.sh` file branches on the backend; remote handling elsewhere lives entirely in Python. `test_history_target_hook_audit.py::_PATHS` has no `context-monitor.sh` entry, and no test runs that script under a remote backend (`test_hooks_integration.py` runs it locally via `LL_HISTORY_DB`, including `test_python_failure_does_not_flip_exit_code`, which pins the `|| true` guarantee).

**Overlap with sibling issues**
- BUG-3652 explicitly routes the hand-built paths and `context-monitor.sh` here and allowlists them in its planned meta-test. ENH-3657 (reader CLIs) also plans `_REMOTE_REFUSALS` entries and `_REJECTED` rows — both this issue and ENH-3657 edit the same dict and list in `session_store/backend.py` / `test_remote_operation_matrix.py`; whichever lands second must merge rather than overwrite. Ordering is not a hard dependency (independent keys).

## Program Design

### Types
- `HistoryTarget = LocalTarget | RemoteTarget` — frozen dataclasses in `session_store/targets.py`; `RemoteTarget.config: BackendConfig`, `RemoteTarget.provider` is `config.provider`.
- `HistoryUnsupported(HistoryError)` — carries `operation: str | None`; `HistoryBackendNotLocal` subclasses it.
- `TrimReport.usage_available: bool` — the existing "telemetry absent" flag in `cli/doctor_trim.py`; no new field is forced by this change.

### Signatures
- `resolve_history_store(path: Path | str | HistoryTarget | None = None, *, root: Path | None = None) -> Path | RemoteTarget` — the resolver the four sites test the result type of.
- `resolve_history_target(path: Path | str | HistoryTarget | None = None, *, root: Path | None = None) -> HistoryTarget` — the typed resolver; a default-shaped path with `LL_HISTORY_DB` unset resolves remote.
- `refuse_on_remote(db: Path | str | HistoryTarget | None, operation: str) -> None` — raises `HistoryUnsupported` on a `RemoteTarget`, no I/O.
- `make_history_route(config: BRConfig) -> Callable[[http.server.BaseHTTPRequestHandler], None]` — site 1a, hand-built `db_path` at construction.
- `cmd_dashboard(args: argparse.Namespace, logger: Logger) -> int` — site 2, `--db` override bypasses the hand-built path.
- `collect_trim_report(root: Path | None = None, *, window_days: int = _DEFAULT_WINDOW_DAYS, rarely_threshold: int = _DEFAULT_RARELY_THRESHOLD, db_path: Path | None = None) -> TrimReport` — site 3, `db_path` override.
- `analyze_workflows(..., db_path: Path | None = None)` — the caller of `_load_messages_from_db(db_path: Path) -> list[dict[str, Any]]`; site 4, path arrives from the caller.
- `record_session_lifecycle_event(db_path: Path | str, *, session_id, event, detail=None, head_sha=None, branch=None, ts=None) -> bool` — `context-monitor.sh` writer.
- `record_context_pressure_event(db_path: Path | str, *, session_id, used_pct, used_tokens_est, threshold_crossed=False, crossed_level=None, head_sha=None, branch=None, ts=None) -> bool` — `context-monitor.sh` writer.

### Call Path
`main_doctor` -> `collect_trim_report` -> `_usage_counts` -> `connect_readonly` (local file only)

`cmd_serve` -> `make_history_route` / `_make_page_html_factory` -> `build_history_payload(allow_missing=True)` -> `build_snapshot_db` -> `refuse_on_remote(db, "snapshot_export")` (reached only when the `is_file()` gate passes)

`cmd_dashboard` -> `db_path.is_file()` gate -> `build_history_payload` -> `build_snapshot_db`

`analyze_workflows` -> `_load_messages_from_db` -> `connect` (skipped when `db_path.exists()` is false; falls back to the JSONL messages file)

`context-monitor.sh` `record_handoff_needed` / `record_context_pressure` -> `resolve_history_db` (raises `HistoryBackendNotLocal`, swallowed by `|| true`) — the writers -> `_connect_telemetry` -> `schema.connect` -> `_seam_target` are never reached under remote

### Decision Rules
- A site acts as remote only when `resolve_history_store(<default-shaped path>)` returns a `RemoteTarget`; an explicit override (`--db`, `db_path=`, `LL_HISTORY_DB`) is `LocalTarget` and must behave exactly as today.
- Per-site outcome class: **refuse** (raise/exit non-zero naming the operation) for `cmd_dashboard` (a `--db`-less run has nothing to render); **skip with a stated reason** for the advisory/degrading sites (`collect_trim_report`, the `serve` route and page factory, the `loop run` dashboard render). `_load_messages_from_db` needs no site change if the JSONL fallback is judged sufficient — a stated reason would need a logger or stderr channel the function lacks.
- `doctor --trim` is advisory and excluded from `ll-doctor`'s exit code; whichever outcome `collect_trim_report` takes must not change that exit code and must not surface a traceback.

## Implementation Steps

1. Handle a `RemoteTarget` at each hand-built default path via `resolve_history_store` (an explicit `--db` / `db_path=` / `LL_HISTORY_DB` stays local and unchanged): **refuse** in `cmd_dashboard` (`refuse_on_remote(db, "snapshot_export")` naming `libsql`, exit 1, not "history database not found"); **skip with a stated reason** in `collect_trim_report` (keeps `--trim` advisory — `main_doctor` exit code unchanged, no traceback), `serve.py`'s `make_history_route()` and `_make_page_html_factory()` (reason must fit the route's payload/status contract), and `cli/loop/run.py`'s `--serve` dashboard render. `workflow_sequence/io.py:_load_messages_from_db` needs no change (its silent JSONL fallback is already a correct degrade). (Per Codebase Research Findings: five sites, not four; `refuse_on_remote` for `trim` is not usable at `collect_trim_report` without a handler.)
2. In `hooks/scripts/context-monitor.sh`, implement **Option A** (selected, see Decision Rationale): drop both `resolve_history_db(".ll/history.db")` pre-resolves in `record_handoff_needed()` / `record_context_pressure()`, pass the literal `.ll/history.db` to the writers so the seam routes to the remote target, drop the unused `resolve_history_db` import, and keep `>/dev/null 2>&1 || true`.
3. Add remote-stub tests and local twins (see Tests); run `python -m pytest scripts/tests/` with `ruff check` and `mypy` clean.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- Scope is five-plus sites, not four: `serve.py` contributes two (`make_history_route`, `_make_page_html_factory`), `cli/loop/run.py`'s `build_dashboard_html` call is a fifth, and `workflow_sequence/io.py:_load_messages_from_db` is a consumer of a caller-supplied path (already a correct degrade to JSONL). Step 1's "four hand-built paths" should be read against the Integration Map findings.
- Outcome: under a libsql backend, no site reports "not found" or renders an empty-as-if-fresh result for a default-shaped path; each names the remote backend as the reason. Check: a remote-fixture test per site asserts the reason text and that a `--db`/`db_path` override still takes the local path.
- Outcome: `ll-doctor --trim` under remote leaves `ll-doctor`'s exit code unchanged and raises no traceback (`main_doctor` has no handler around `collect_trim_report`). Check: a `test_remote_doctor.py`-style test plus the local twin in `test_cli_doctor_trim.py`.
- Outcome: the `context-monitor.sh` decision is recorded (Option A/B under Proposed Solution). Check: under Option A, a `HranaStub` fixture sees the lifecycle/pressure rows arrive and a stopped stub leaves the hook exiting 0 with no stderr; `test_hooks_integration.py::test_python_failure_does_not_flip_exit_code` keeps passing.
- Outcome: a `trim` operation is registered wherever the rejected-operation set is enumerated (`_REJECTED` row) if the refuse route is chosen; a specific `_REMOTE_REFUSALS` reason is optional since the generic wording applies. Coordinate with ENH-3657, which edits the same dict and list.
- Outcome: any new user-facing sentence in `docs/reference/CONFIGURATION.md` / `CLI.md` is pinned in `test_wiring_reference_docs.py::DOC_STRINGS_PRESENT` and passes `test_docs_audience_gate.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/loop/run.py` — handle a `RemoteTarget` at the `build_dashboard_html(db_path=..., serve_context=serve_ctx)` call (~`:691`); it has no `except`, so a raise aborts `ll-loop run --serve`
- Update `scripts/little_loops/cli/artifact/serve.py` — both `make_history_route()` (`:92`, incl. the `db_path.stat()` ETag key) and `_make_page_html_factory()` (`:173`); the route catches only `ValueError`, so a stated reason must fit its payload/status contract
- Update `scripts/little_loops/cli/doctor.py` `main_doctor` (`:1836`) — add a handler around `collect_trim_report` (or skip inside it) so `--trim` stays advisory and leaves the exit code unchanged
- Update `hooks/scripts/context-monitor.sh` — drop both `resolve_history_db(".ll/history.db")` pre-resolves (`:58`, `:84`) and the unused import on `:56`/`:82`; keep `>/dev/null 2>&1 || true`, keep `check_compaction` / `.compacted_at`, avoid non-portable shell syntax
- Add `("trim", ...)` row to `scripts/tests/test_remote_operation_matrix.py::_REJECTED` if the refuse route is used; merge with ENH-3657's edits to `_REJECTED` and `_REMOTE_REFUSALS`
- Add remote-fixture tests + local twins: `context-monitor.sh` subprocess under `remote` (rows arrive; stopped stub exits 0 with empty stderr), `main_doctor(["--trim"])`, `cmd_dashboard`, `TestHistoryRoute` sibling, `_make_page_html_factory`, `run.py --serve` render
- Update `docs/reference/CLI.md` (`--trim`, `ll-artifact dashboard`) and the "Remote history backend" reference section (site refusals only — not a `context-monitor.sh` drop note, which Option A rejects) with end-user wording; pin new strings in `test_wiring_reference_docs.py::DOC_STRINGS_PRESENT`
- Do not touch `scripts/little_loops/cli/logs.py` (`_cmd_dead_skills`, `_cmd_stats` hand-built paths) — owned by ENH-3657

## Impact

- **Priority**: P4 - these sites fail quietly (no startup abort), so impact is low.
- **Effort**: Small - four sites plus one hook script.
- **Risk**: Low - local behavior unchanged.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] `cmd_dashboard`, `collect_trim_report`, both `serve.py` sites (`make_history_route`, `_make_page_html_factory`) and the `cli/loop/run.py` `--serve` render resolve through `resolve_history_store` and handle a `RemoteTarget` explicitly (refuse or skip, naming the remote backend); no site reports "not found" or renders an empty-as-if-fresh result. `--db` / `db_path=` / `LL_HISTORY_DB` overrides still take the local path.
- [ ] `ll-doctor --trim` under remote leaves `ll-doctor`'s exit code unchanged and raises no traceback.
- [ ] `context-monitor.sh` (Option A) no longer pre-resolves; under a remote stub the lifecycle and pressure rows arrive, and with the stub stopped the hook exits 0 with empty stderr.
- [ ] Remote-stub tests cover each site with local twins; local behavior unchanged; `python -m pytest scripts/tests/` passes.

## Related

- BUG-3652 (caller audit that surfaced these).
- FEAT-3535 (remote libSQL history backend).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P4

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-29_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Concerns
- Summary, Effort ("four sites") and the Codebase Research Findings disagree on scope: five hand-built sites (serve.py ×2, dashboard.py, doctor_trim.py, run.py) plus the hook; Integration Map and Acceptance Criteria are the authoritative list.
- `collect_trim_report` skip mechanism is left as "handler in `main_doctor` or skip inside `collect_trim_report`" — pick one before coding (Decision Rules favor skip-with-reason to keep `--trim` advisory).
- The `serve.py` "stated reason" must fit the route's payload/status contract (`make_history_route` catches only `ValueError` → 413, takes no Logger); the concrete response shape is not specified.
- Refusal/catcher conventions are explicitly contested across the repo; per-site choice is left to the implementer.

### Outcome Risk Factors
- Broad enumeration across 6 code sites (plus a shell hook, 6+ test files and 4 doc files), each with a slightly different outcome class (refuse vs skip).
- Coverage gaps: no test drives `context-monitor.sh` under a remote backend, `_make_page_html_factory` has no direct test, and the `ll-loop run --serve` render has none — the new remote-stub tests are the only safety net.
- Shell-hook change is validated only through a `HranaStub` subprocess fixture that does not exist yet; hook `timeout: 5` bounds remote-write latency.

## Session Log
- `/ll:decide-issue` - 2026-09-29T06:52:11 - `b6e8b863-de04-439b-86a0-163f69ae4ae5.jsonl`
- `/ll:confidence-check` - 2026-09-29T06:37:24 - `8bc00e90-4fb4-4186-b015-6ae8b54ba73f.jsonl`
- `/ll:verify-issues` - 2026-09-29T06:35:53 - `8072da21-2d78-4f2f-ada0-f03b231f5125.jsonl`
- `/ll:reconcile-issue` - 2026-09-29T06:34:15 - `877ea6e8-6250-465b-b992-d2e8d8b06ce5.jsonl`
- `/ll:verify-issues` - 2026-09-29T06:33:17 - `ff97b32f-aa84-46a2-9a7d-af053e342cd2.jsonl`
- `/ll:wire-issue` - 2026-09-29T06:31:23 - `7b6ba26a-d87e-4453-a694-b6e659ef24db.jsonl`
- `/ll:decide-issue` - 2026-09-29T06:23:36 - `bbc97752-9916-4650-a701-f5939b2c2ee3.jsonl`
- `/ll:refine-issue` - 2026-09-29T06:21:46 - `37d0b17a-7e47-4ff9-92ea-b1a095fee341.jsonl`
