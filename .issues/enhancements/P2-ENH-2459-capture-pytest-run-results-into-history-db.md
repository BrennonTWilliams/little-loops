---
id: ENH-2459
title: Capture pytest run results into history.db as test_run_events
type: ENH
priority: P2
status: done
discovered_date: 2026-07-02
captured_at: "2026-07-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - testing
  - captured
---

# ENH-2459: Capture pytest run results into history.db as test_run_events

## Summary

`.ll/history.db` (schema v14) does not persist pytest results — pass/fail counts, duration, failing test names — even though `python -m pytest scripts/tests/` is the project's **only CI gate** per `.claude/CLAUDE.md` § Testing & CI Policy. Today, the run results exist only in the most recent stdout/stderr (transient) and in CI-equivalent local re-runs. Add a `test_run_events` table populated by a pytest wrapper carrying `(ts, started_at, ended_at, total, passed, failed, errored, skipped, duration_s, failing_test_names_json, env_label, head_sha)`; surface via `ll-session recent --kind test_run` and `ll-session search --fts "<test name fragment>" --kind test_run`. Per `thoughts/history-db-expand-wiring.md` §3 ranked recommendation #2: *"since `pytest` is this project's only CI gate, wrapping test runs (pass/fail counts, duration, failing test names) into a `test_run_events` table would let history correlate 'this issue's fix' with 'did the suite stay green,' and support trend/flake analysis."*

## Motivation

The current local-CI model leaves no trail:

- **No "was the suite green before this change" check** — pre-merge confidence relies on running the suite each time and visually parsing output. A historical record lets `ll-history` answer "did this branch's first run pass?" without re-running.
- **No flake detection** — "this test was intermittent on 2026-06-15 between 14:00 and 16:00" is invisible without a record.
- **No coverage-by-time analysis** — "duration crept from 30s to 90s over the last week" cannot be reconstructed.
- **No correlation with issues** — there's no automated "this issue's PR ran 5 tests, all green, landed in commit X."

The pytest `--junitxml` reporter already produces machine-readable run results; this enhancement is a thin wrapper that pipes `--junitxml` into `history.db`.

## Current Behavior

- `python -m pytest scripts/tests/` outputs human-readable text only.
- Pass/fail counts exist in stdout but are not persisted.
- Failing test names exist in stdout only.
- Duration exists in stdout only.
- No historical record — each run starts fresh.

## Expected Behavior

- `test_run_events` table exists in schema v15+ with columns: `id`, `ts` (start timestamp ISO 8601), `ended_at`, `total`, `passed`, `failed`, `errored`, `skipped`, `duration_s`, `failing_names_json`, `env_label` (`ci|local|worktree|...`), `head_sha`, `branch`, `command` (e.g. `python -m pytest scripts/tests/`).
- A pytest wrapper (`scripts/bin/pytest-wrapped` or a python entry-point `ll-pytest` invoking `pytest.main()` with a custom terminal reporter) writes a row at the start of a run and updates it on completion with the actual counts.
- `--junitxml` output is captured and used as the source of truth for counts and failing-test names.
- `ll-session recent --kind test_run` returns rows; `ll-session search --fts "<test fragment>" --kind test_run` returns matches against `failing_names_json`.
- Trend analysis: `ll-session recent --kind test_run --limit 50` reveals pass-rate and duration over time.
- Works under any pytest invocation that goes through the wrapper — no source rewrite of pytest.

## Proposed Solution

### Schema migration (append to `_MIGRATIONS` in `session_store.py`)

```sql
CREATE TABLE IF NOT EXISTS test_run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    ended_at TEXT,
    total INTEGER,
    passed INTEGER,
    failed INTEGER,
    errored INTEGER,
    skipped INTEGER,
    duration_s REAL,
    failing_names_json TEXT,
    env_label TEXT,
    head_sha TEXT,
    branch TEXT,
    command TEXT
);
CREATE INDEX IF NOT EXISTS idx_test_run_events_head_sha ON test_run_events(head_sha);
CREATE INDEX IF NOT EXISTS idx_test_run_events_branch ON test_run_events(branch);
CREATE INDEX IF NOT EXISTS idx_test_run_events_failed_count ON test_run_events(failed);
```

Bump `SCHEMA_VERSION`. Add `"test_run"` to `_VALID_KINDS` and `"test_run": "test_run_events"` to `_KIND_TABLE`.

### Producer wiring

- **Approach A (preferred)**: Author `scripts/pyproject.toml` `pytest-wrapped = "little_loops.testing.pytest_plugin:main"` entry-point as a `pytest` plugin (`pytest_configure` hook) that registers an `pytest_terminal_summary` callback writing to `.ll/history.db` on each test session.
- **Approach B (fallback)**: A shell wrapper `scripts/bin/pytest-wrapped` that runs `python -m pytest --junitxml=/tmp/ll-junit.xml ...` then parses the JUnit XML into `record_test_run_event()`. Adoptable via `PATH` re-order for the worker's `ll-auto`/`ll-parallel` runs.
- Best-effort: `record_test_run_event` is wrapped in `contextlib.suppress(Exception)` per the EPIC-1707 graceful-degradation contract — test results never block the run.

### Env label inference

- Detect CI by env vars: `CI=true`, `GITHUB_ACTIONS=true`, `JENKINS_URL`, `LL_AUTO_RUN=true`.
- Detect worktree by checking `.git` parent path for `..worktree..`.
- Default: `local`.

### Read API

Add `recent_test_runs(branch=None, head_sha=None, limit=50)` to `history_reader.py`. Returns `list[TestRunEvent]` with all fields plus a derived `pass_rate` for convenience.

## Acceptance Criteria

- `test_run_events` table exists in `.ll/history.db` after migration.
- A pytest invocation via the wrapper plugin writes a `test_run_events` row with pass/fail counts and duration that match the `--junitxml` summary.
- A failing test (deliberately introduced) records the failing test's node ID in `failing_names_json`.
- `ll-session recent --kind test_run` returns the row.
- `ll-session search --fts "<failing test name fragment>" --kind test_run` returns matches.
- Multiple runs in sequence produce non-overlapping rows with monotonically increasing `ts`.
- CI env vars populate `env_label` correctly.
- The wrapper's pytest run is not blocked when `.ll/history.db` is absent/locked.
- Documented in `docs/ARCHITECTURE.md` schema-versions table and `docs/reference/CONFIGURATION.md` analytics gates.

## Implementation Steps

1. Schema migration for `test_run_events`; bump `SCHEMA_VERSION`.
2. Add `"test_run"` to `_VALID_KINDS` and `_KIND_TABLE`.
3. Implement `record_test_run_event()` in `session_store.py` accepting `pytest.TerminalReport`-shaped fields.
4. Author `scripts/little_loops/testing/pytest_plugin.py` registering `pytest_terminal_summary` + `pytest_runtest_logreport` hooks.
5. Register the entry-point in `scripts/pyproject.toml` under `[project.entry-points.pytest11]` so any `pytest` invocation picks it up automatically.
6. Document the opt-out: `PYTEST_DISABLE_PLUGIN_LL_HISTORY=1` for users who don't want test-event capture.
7. Add `recent_test_runs()` to `history_reader.py`.
8. Add CLI flags: `ll-session recent --kind test_run`.
9. Tests: `TestRecordTestRunEvent`, `TestSchemaV15` (or higher), `TestPytestPluginWritesRow`, `TestBackfillTestRunsStub`.
10. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/CLI.md` `--kind test_run`, `.claude/CLAUDE.md` notes the new gateway for "is CI green?" lookups.

## Integration Map

_Wiring pass added by `/ll:wire-issue` on 2026-07-16 — comprehensive touchpoint audit for the shipped implementation (schema v18)._

### Files to Modify

- `scripts/little_loops/pytest_history_plugin.py` — shipped as `pytest_history_plugin.py` (not `testing/pytest_plugin.py`); registers `pytest_sessionfinish` + `pytest_runtest_logreport` hooks (not `pytest_terminal_summary`)
- `scripts/little_loops/session_store.py` — schema v18 migration (test_run_events table + 3 indexes), `"test_run"` in `_VALID_KINDS`, `_KIND_TABLE["test_run"] = "test_run_events"`, `_EXPORT_TABLE_MAP["test_run_event"] = ("test_run_events", "ts")`, `test_run_event` in `_EXPORT_DEFAULT_TABLES`, `test_run_events` exclusion from `_REBUILD_TABLES`, `record_test_run_event()` in `__all__`
- `scripts/little_loops/history_reader.py` — `RunEvent` dataclass + `recent_test_runs()` (filter by `branch`/`head_sha`, derive `pass_rate`)
- `scripts/little_loops/observability/schema.py` — `TestRunEventVariant` registered in `DES_VARIANTS` (required for `ll-verify-des-audit` F5 adoption gate)
- `scripts/little_loops/cli/session.py` — argparse derives `search --kind` and `recent --kind` choices from `VALID_KINDS` (adding `"test_run"` automatically expands both surfaces)
- `scripts/pyproject.toml` — `[project.entry-points.pytest11]` table registering `ll_history = "little_loops.pytest_history_plugin"`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/pytest_history_plugin.py` — `from little_loops.session_store import record_test_run_event, resolve_history_db` (the plugin's own consumer)
- `scripts/little_loops/cli/session.py` — `main_session()` dispatches `--kind test_run` to `recent()` and `search()` (via `_KIND_TABLE` lookup)
- `scripts/little_loops/cli/verify_des_audit.py` — transitive: walks source tree for emit sites; `test_run_event` must remain registered in `DES_VARIANT_TYPES`
- `scripts/little_loops/cli/verify_kinds.py` — transitive: validates `_MIGRATIONS` ↔ `_KIND_TABLE` consistency for every `CREATE TABLE`
- `scripts/tests/conftest.py` (lines 91–93) — cites `pytest_history_plugin.py:147-150` and `test_pytest_history_plugin.py:62-71` as the proven-correct xdist-worker-detection idiom

### Registration / Manifest Files

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/pyproject.toml` — `[project.entry-points.pytest11]` with `ll_history` entry-point (lines 101–104)
- `scripts/little_loops/observability/schema.py` — `TestRunEventVariant` registered in `DES_VARIANTS` tuple (line 626)
- `scripts/little_loops/session_store.py` — `_KIND_TABLE["test_run"] = "test_run_events"` (line 234); `__all__` exports `record_test_run_event` (line 86); `_EXPORT_TABLE_MAP` + `_EXPORT_DEFAULT_TABLES` + `_REBUILD_TABLES` exclusions
- `.claude-plugin/plugin.json` — does NOT directly reference `test_run` (entry-point manifest is `pyproject.toml`, not plugin.json)

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Existing shipped coverage:**
- `scripts/tests/test_pytest_history_plugin.py` — `TestCaptureGating` (xdist, opt-out env), `TestOutcomeCounting` (per-phase tally), `TestSessionFinishWritesRow` (DB write), `TestEnvLabel` (CI/worktree/local)
- `scripts/tests/test_session_store.py::TestRecordTestRunEvent` (lines 4362–4432) — round-trip, FTS searchable, multi-row distinct, v14→v18 upgrade
- `scripts/tests/test_session_store.py::TestSchemaV14::test_v14_db_upgrades_gains_test_run_events` — schema upgrade smoke
- `scripts/tests/test_history_reader.py::test_recent_test_runs_and_pass_rate` — newest-first ordering, `pass_rate` derivation, `head_sha` filter, empty-DB path
- `scripts/tests/test_ll_session.py::test_recent_subcommand_test_run_accepted` + `test_recent_kind_test_run_outputs_row` — CLI end-to-end

**Test gaps identified (not yet implemented):**
- `TestSchemaV18TestRunEvents` — column set + 3 indexes (idx_test_run_events_head_sha/branch/failed_count) via `PRAGMA table_info` + `sqlite_master`, following `TestSchemaV20UsageEvents` convention
- xdist `-n auto` integration test asserting exactly one DB row under sharded run
- `pytest_configure(config)` with `PYTEST_DISABLE_PLUGIN_LL_HISTORY=1` set + `.ll/` present → `register.assert_not_called()`
- `failing_names[:100]` truncation when >100 reports logged
- `command[:500]` truncation when argv >500 chars
- `export_history()` with `tables=["test_run_event"]` yields rows with `type="test_run_event"`
- `ll-session search --fts "<node_id>" --kind test_run` end-to-end CLI (only arg-parser currently covered)
- `[project.entry-points.pytest11] ll_history` discoverability via `entry_points(group="pytest11")`
- `record_test_run_event` `config` kwarg accepted-and-ignored behavior
- Positive env-var tests for `GITHUB_ACTIONS=true` and `JENKINS_URL` (currently only `CI` and `LL_AUTO_RUN` set positively)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/ARCHITECTURE.md` — schema v18 row + plugin description (line 676)
- `docs/reference/API.md` — `RunEvent`, `recent_test_runs()`, `record_test_run_event()` API reference (lines 7065–7389)
- `docs/reference/CLI.md` — `search --kind` / `recent --kind` / `export --tables` choices + example
- `docs/guides/HISTORY_SESSION_GUIDE.md` — query examples, schema table, v18/ENH-2459 row
- `docs/observability/des-audit.md` — `TestRunEventVariant` registry entry (line 76)

**Documentation gaps (not yet mentioned):**
- `commands/run-tests.md` — user-facing command for running the test suite; does NOT mention automatic history capture, `PYTEST_DISABLE_PLUGIN_LL_HISTORY` opt-out, or `ll_history` entry-point

### Configuration

_Wiring pass added by `/ll:wire-issue`:_

- `.ll/ll-config.json` — no test-run-specific keys (capture controls are env vars: `PYTEST_DISABLE_PLUGIN_LL_HISTORY`, `LL_HISTORY_DB`)
- `config-schema.json` — no `test_runs` capture flag added (the `config` kwarg on `record_test_run_event` is documented as a forward-compatibility stub for a future `analytics.capture.test_runs` flag)

## Sources

- `thoughts/history-db-expand-wiring.md` — findings report, recommendations §2 row 2 ("Test run results") and §3 ranked recommendation #2
- `.claude/CLAUDE.md` § Testing & CI Policy — "single enforced, cost-free gate is the local test suite: `python -m pytest scripts/tests/`"
- `scripts/little_loops/session_store.py:_MIGRATIONS` — schema migration pattern
- `scripts/little_loops/hooks/post_tool_use.py::handle()` — `contextlib.suppress(Exception)` graceful-degradation precedent

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/CONFIGURATION.md` | `analytics.enabled` flag gates this write path |
| `.claude/CLAUDE.md` | "single enforced gate is the local test suite" — this enhancement makes that suite's history queryable |
| pytest docs | `--junitxml` schema; `pytest_terminal_summary` plugin hook |

## Status

**Done** | Created: 2026-07-02 | Completed: 2026-07-03 | Priority: P2

Implemented as schema v18: `test_run_events` table + head_sha/branch/failed indexes;
`"test_run"` added to `_VALID_KINDS`/`_KIND_TABLE` and the export map. Approach A shipped:
`little_loops/pytest_history_plugin.py` registered under `[project.entry-points.pytest11]`
(`ll_history`) in scripts/pyproject.toml — counts outcomes via `pytest_runtest_logreport`
(call-phase pass/fail/skip; setup/teardown failures as errors) and writes one row in
`pytest_sessionfinish` wrapped in `contextlib.suppress(Exception)`. Guard rails: opt-out via
`PYTEST_DISABLE_PLUGIN_LL_HISTORY=1` (or `-p no:ll_history`); only activates when cwd has
`.ll/` or `LL_HISTORY_DB` is set (never creates a DB in unrelated projects); xdist-aware
(controller-only, so `-n auto` yields exactly one row). No JUnit XML needed — the report hooks
are the source of truth. env_label: ci (CI/GITHUB_ACTIONS/JENKINS_URL/LL_AUTO_RUN) / worktree
(`.git` is a file) / local; head_sha+branch via best-effort git subprocess. Note: the new
entry point activates after the next `pip install -e "./scripts[dev]"`. Read side:
`history_reader.recent_test_runs()` with derived `pass_rate`; CLI: `ll-session recent --kind
test_run`, `search --fts "<test name>" --kind test_run` (failing node IDs are FTS-indexed).
Tests: scripts/tests/test_pytest_history_plugin.py, `TestRecordTestRunEvent` in
test_session_store.py, reader/CLI tests.

## Session Log
- `/ll:wire-issue` - 2026-07-16T22:32:30 - `e1bd59a2-e0c5-4fc0-822b-b3df1645480c.jsonl`
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
