---
id: FEAT-3404
title: Add ll_version history.db stamp and typed reader path (orchestration_runs/loop_runs)
type: FEAT
priority: P0
status: done
discovered_date: '2026-09-07'
completed_at: '2026-09-08T15:31:30Z'
parent: FEAT-3398
labels:
- path-a
- observability
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-3404: Add ll_version history.db stamp and typed reader path (orchestration_runs/loop_runs)

## Summary

Add a `ll_version TEXT` column to `orchestration_runs` and `loop_runs`, stamped
automatically by the writers from the installed `little_loops.__version__` (no
call-site changes required). Expose it through the typed reader path:
`recent_orchestration_runs()`/`aggregate_orchestration_runs()` and their
loop_runs counterparts in `history_reader/runs.py`, and the
`OrchestrationRun`/`LoopRun` dataclasses in `history_reader/models.py` — not
only via raw SQL.

## Parent Issue

Decomposed from FEAT-3398: Quality-regression detection with model/host/version
attribution. This is the first of two children — FEAT-3398's detection logic
(second child, FEAT-3405) needs this column to exist before it can read a
`ll_version` composition dimension.

## Current Behavior

`orchestration_runs` (`schema.py:540`) carries `driver`/`head_sha`/`branch` but no
version column. `usage_events.model` and `raw_events.host` are already
recoverable per-run via the `issue_sessions` join, but no persisted
little-loops-version stamp exists anywhere — `__version__`
(`scripts/little_loops/__init__.py:83`) lives only in the installed package,
never written to `history.db`. `record_orchestration_run()` and
`record_loop_run_summary()` (`session_store/writers.py:1287,1428`) accept no
model/host/version parameter.

## Expected Behavior

New `orchestration_runs`/`loop_runs` rows carry `ll_version` without any
orchestrator call-site change (the writer defaults it from
`little_loops.__version__` internally). Existing rows read back with `ll_version
IS NULL`. The value is visible through the typed reader path, matching the
`base_sha`/`base_dirty` precedent (ENH-2866).

## Motivation

FEAT-3398's attribution logic needs a per-run little-loops-version stamp to name
"version" as a candidate cause of a quality regression, the same way model and
host already are via existing joins. This column is the only piece of that
Dependencies gap that isn't already recoverable from existing tables.

The `loop_runs.ll_version` half has exactly one consumer: FEAT-3405's
retry-inflation series is bucketed by `(period, loop_name)` from `loop_runs`
(not by orchestrator), so version is the only attribution dimension available
there. If FEAT-3405 scopes retry inflation out, this half becomes
forward-looking only — still cheap, but call that out in the commit message.

## Use Case

**Who**: FEAT-3405's quality-regression attribution logic, and any maintainer
querying `history.db` directly.

**Context**: A maintainer investigating a quality-metric drop wants to check
whether a little-loops version bump coincided with it. Model and host are
already recoverable per-run via the `issue_sessions` join, but there is no
`ll_version` column to join against — the version a run executed under isn't
recorded anywhere.

**Goal**: Query `recent_orchestration_runs()` (or the raw table) for a given
period and see which `little_loops.__version__` was installed when each run
executed, without any producer code having to remember to pass it.

**Outcome**: `orchestration_runs.ll_version`/`loop_runs.ll_version` is
populated automatically by the writers and exposed through the typed reader
path, so FEAT-3405's `load_window_compositions()` can compute a per-window
version-share composition the same way it already does for model and host.

## Proposed Solution

### Schema (v48)

- **Append one v48 migration string** to the append-only `_MIGRATIONS` list
  (`schema.py:124-1330`) containing two statements:
  `ALTER TABLE orchestration_runs ADD COLUMN ll_version TEXT;` and
  `ALTER TABLE loop_runs ADD COLUMN ll_version TEXT;`. This is exactly how v38
  added `base_sha` (`schema.py:949`). **Do not edit** the v22/v23 `CREATE TABLE`
  strings at `schema.py:540`/`570` — those are frozen history; changing them
  breaks the checked-in manifest and diverges fresh DBs from upgraded ones.
- `record_orchestration_run()` / `record_loop_run_summary()`
  (`session_store/writers.py:1287,1428`) gain a keyword-only
  `ll_version: str | None = None` param, defaulting to `little_loops.__version__`
  inside the writer so no call site needs to change.
- **UPSERT is first-write-wins**: `ll_version=COALESCE(ll_version,
  excluded.ll_version)` — note the argument order is the *reverse* of the
  `base_sha` clause (`writers.py:1358-1360`). Rationale: because the writer
  always fills `ll_version` from `__version__`, `excluded.ll_version` is never
  NULL, so the `base_sha` order (`COALESCE(excluded.x, x)`) would degenerate to
  last-write-wins. The value we want is the version *at dequeue*; a terminal
  upsert that runs after a mid-run `pip install -e` upgrade must not overwrite
  it. `COALESCE(ll_version, excluded.ll_version)` keeps the existing stamp when
  present and fills it on the first write (or on pre-v48 rows that get a later
  upsert).
- Bump `SCHEMA_VERSION` 47 → 48.

### Typed reader path

- `history_reader/runs.py`: extend the `orchestration_runs` SELECT column list /
  `_ORCHESTRATION_GROUP_COLUMNS` map (currently `79,100-103`) and the
  `loop_runs` counterpart (`_LOOP_RUN_COLUMNS`, `recent_loop_runs()`,
  `_LOOP_RUN_GROUP_COLUMNS`, `aggregate_loop_runs()`, currently
  `328-332,335,388,394`) with `ll_version`.
- `history_reader/models.py`: add `ll_version` to the `OrchestrationRun`
  dataclass (currently `151`) and the `LoopRun` dataclass (currently
  `171-186`) — both are positionally/name-matched against their SELECT lists
  via `_row_to_dataclass`.

### Manifest and version-assertion updates

- Regenerate `session_store/schema_manifest.json` (recipe:
  `test_session_store_schema.py:2852-2865`) after the migration.
- Update every hardcoded `SCHEMA_VERSION == 47` assertion to 48:
  `test_session_store_schema.py` (e.g. lines 1884, 1929),
  `test_session_store_writers.py` (470,1153,1283,1540,1738),
  `test_assistant_messages.py:88` (`test_schema_version_is_12` — name already
  stale relative to its own assertion).

### Documentation

- `docs/guides/HISTORY_SESSION_GUIDE.md`: add a new row to the
  schema-version-history table (currently ending `v47 | ENH-3204 |
  credential_scope_events table`) and add `ll_version` to the
  `orchestration_runs` column enumeration (currently line 132).
- `docs/ARCHITECTURE.md`: matching new-version row in its schema-version-history
  table (currently rows ~659-680).
- `docs/reference/API.md`: update `record_orchestration_run()`
  (`9695-9713`), `record_loop_run_summary()` (`9755-9772`), `OrchestrationRun`
  (`8678-8713`), and `LoopRun` (`8717-8729`) blocks with the new
  `ll_version` field/param.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- `loop_runs` CREATE TABLE lives at `schema.py:570` (v23/ENH-2463), immediately below `orchestration_runs` at `schema.py:540`.
- `record_loop_run_summary()` writes via a plain `INSERT OR IGNORE` (`writers.py:1472-1476`) with no `ON CONFLICT`/COALESCE clause at all — the row is idempotent-by-insert on the `run_id` UNIQUE constraint, so unlike `record_orchestration_run()`'s COALESCE handling for `base_sha`/`base_dirty`, an `ll_version` param on this writer needs no merge logic; it is appended once to the INSERT column list and never re-written.
- `writers.py` never imports the top-level `little_loops` package at module scope (`little_loops/__init__.py` itself imports from `little_loops.session_store`, so a module-level `from little_loops import __version__` in `writers.py` would be circular). Both existing `from little_loops import __version__` call sites in the codebase (`init/tui.py:1203`, `init/cli.py:45`) are function-local; `writers.py`'s own `record_usage_event()` already imports `little_loops.pricing` function-locally for the same reason (`writers.py:1528`). The default-from-`__version__` logic in both writers must follow this function-local pattern.

## Program Design

### Types

- `OrchestrationRun` (`history_reader/models.py:151`): gains `ll_version: str
  | None`.
- `LoopRun` (`history_reader/models.py:171-186`): gains `ll_version: str |
  None`.

### Signatures

- `record_orchestration_run(*, ll_version: str | None = None) -> None`
- `record_loop_run_summary(*, ll_version: str | None = None) -> None`

Both gain this keyword-only param in `session_store/writers.py` (lines 1287 and 1428 respectively) alongside their existing params.

### Call Path

`record_orchestration_run()`/`record_loop_run_summary()` (defaults `ll_version` from `little_loops.__version__` when the caller passes none) -> UPSERT `COALESCE(ll_version, excluded.ll_version)` (first-write-wins; `loop_runs` is plain `INSERT OR IGNORE`, no merge clause) -> `recent_orchestration_runs()`/`aggregate_orchestration_runs()` and `recent_loop_runs()`/`aggregate_loop_runs()` (`history_reader/runs.py`) -> `OrchestrationRun`/`LoopRun` dataclasses (`history_reader/models.py`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- `_row_to_dataclass()` (`history_reader/_base.py:87-91`) maps rows to dataclasses by **name intersection** (`{f.name for f in dc.__dataclass_fields__.values()}` against `row.keys()`), not by position — a column can be added to the SELECT list and the dataclass field independently, in any order, as long as both exist and the field carries a default (as `base_sha`/`base_dirty`/`failure_terminal` already do).
- `aggregate_orchestration_runs()`/`aggregate_loop_runs()` (`history_reader/runs.py:129,394`) never touch `OrchestrationRun`/`LoopRun` — they resolve a `group_by` literal through `_ORCHESTRATION_GROUP_COLUMNS`/`_LOOP_RUN_GROUP_COLUMNS` and return plain `dict`s. `_ORCHESTRATION_GROUP_COLUMNS` (`runs.py:79`) is the map FEAT-3405 needs `"ll_version": "ll_version"` added to if its version-share composition intends to group by this column, same as `driver`/`issue_id`/`status` today.

### Decision Rules

N/A — no new decision logic.

## Tests

- `TestOrchestrationRunLlVersion`-style class in `test_session_store_writers.py`,
  modeled on `TestOrchestrationRunBaseStamp` (1364-1519) but with a method set
  adapted to first-write-wins and the always-filled default:
  early-upsert-stamps-`__version__`-without-caller-passing-it,
  terminal-upsert-under-a-different-explicit-`ll_version`-does-not-overwrite
  (the mid-run-upgrade case; pass `ll_version="9.9.9"` on the second call and
  assert the first value survives), explicit-`ll_version`-on-first-write-is-
  honored. There is deliberately **no** "unstamped write leaves NULL" method —
  the public API cannot produce a NULL on a new row; NULL-on-old-rows is covered
  by the schema upgrade test below.
- `TestSchemaV38BaseShaColumns`-style class in `test_session_store_schema.py`
  (template: 1902-1967) for the new columns: column-presence via `PRAGMA
  table_info`, negative check that an unrelated table did not gain the column,
  upgrade-from-old-version test (bootstrap at v47, `ensure_db()`, assert old
  rows survive with NULL `ll_version`).
- Verify via:
  `python -m pytest scripts/tests/test_session_store_writers.py scripts/tests/test_session_store_schema.py scripts/tests/test_history_reader_runs.py -v`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- The typed-reader-level tests for `recent_orchestration_runs()`/`aggregate_orchestration_runs()`/`recent_loop_runs()`/`aggregate_loop_runs()`/`find_loop_run()` currently live in `test_history_reader_events.py::TestNewEventReaders` (e.g. `test_recent_orchestration_runs_filters:450`, `test_aggregate_orchestration_runs:485`, `test_recent_loop_runs_filters:528`, `test_aggregate_loop_runs:596`) — `test_history_reader_runs.py` only covers `read_base_sha`/`read_base_dirty` (`TestReadBaseSha:17`, `TestReadBaseDirty:88`). The verify command above should also include `scripts/tests/test_history_reader_events.py` or the new `ll_version` reader-path assertions won't be exercised.
- `TestLoopRuns` (`test_session_store_writers.py:1520-1657`) is the natural home for a `loop_runs` `ll_version` writer test, but there is no `base_sha`/`base_dirty`-style COALESCE precedent to mirror within it — `LoopRun`'s only existing optional field is `failure_terminal` (`models.py:186`), and even that field's coverage lives on the reader side (`test_history_reader_events.py::test_find_loop_run_exposes_failure_terminal:578`), not in `TestLoopRuns` itself. Since `record_loop_run_summary()` uses a plain `INSERT OR IGNORE` with no UPSERT, the new test method here only needs to assert "recorded on insert," not a COALESCE-preservation variant.
- No exhaustive column/field-set assertion exists for `orchestration_runs`/`loop_runs`/`OrchestrationRun`/`LoopRun` (`fields(...)`, `asdict(...)`, or `cols == {...}`) that would break from an added column — all existing `cols == {...}` checks in `test_session_store_schema.py` target other tables, and the two `orchestration_runs`/`loop_runs`-specific column checks are subset/negative (`{"base_sha","base_dirty"} <= cols`, and an absence check on `loop_runs`), both unaffected. `_row_to_dataclass()` (`history_reader/_base.py:87-91`) builds dataclass kwargs by name from `row.keys()`, so field order in `models.py` doesn't matter and no positional-construction risk exists (`OrchestrationRun(`/`LoopRun(` are never called positionally anywhere in the repo).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store_schema.py` — `SCHEMA_VERSION == 47` appears in **21** assertions, not just the 2 cited above (`1884`, `1929`): also `650, 664, 716, 812, 1034, 1075, 1413, 1453, 1497, 1547, 1622, 1682, 1751, 1816, 1984, 2542, 2624, 2724, 2786` (confirmed via direct grep) — all 21 need bumping to 48, or the schema-upgrade test suite fails on the version bump alone.
- `scripts/little_loops/session_store/queries.py:147-160` (`_SHAREABLE_COLUMNS["loop_runs"]`, version-locked via `_SHAREABLE_ALLOWLIST_VERSION`) and `scripts/little_loops/cli/loop/evidence.py:42-53` (`_LOOP_RUN_ALLOWLIST`) are hand-maintained `loop_runs` column allowlists (ENH-075 shareable dashboard export; FEAT-3182 evidence bundle) that do **not** auto-include new columns. `ll_version` stays excluded from `ll-artifact dashboard --mode shareable` and `ll-loop evidence` output — this is out of scope for this issue, not a missed touchpoint. A future issue extending either allowlist to include `ll_version` must bump `_SHAREABLE_ALLOWLIST_VERSION` in the same commit (enforced by `test_feat3304_artifact_dashboard.py::TestAllowlistVersionLockstep`).

## Note on superseded call-site threading

An earlier draft of FEAT-3398 considered threading `model`/`host`/`ll_version`
params through every `record_orchestration_run` production call site
(`issue_manager.py:767,2309`, `parallel/orchestrator.py:1223`,
`parallel/worker_pool.py:1703`, `cli/sprint/run.py:736,928`,
`fsm/executor.py:4293`). That plan is **not needed**: the writer defaults
`ll_version` internally, so those call sites are unaffected. The
`test_sprint.py:3159-3176` AST check (asserting every
`record_orchestration_run(driver="ll-sprint")` call carries required stamps)
stays passing since the new kwarg is optional.

## Impact

- **Priority**: P0 — blocks FEAT-3405's version-attribution dimension.
- **Effort**: Small — a one-column schema migration following an established
  precedent (ENH-2866 `base_sha`/`base_dirty`), plus reader-path plumbing.
- **Risk**: Low — read-only/additive; the main risk is a missed reader-path
  update leaving the column unreadable (not corrupted).
- **Breaking Change**: No.

## Acceptance Criteria

- `ll_version` is recorded on new `orchestration_runs`/`loop_runs` rows without
  any orchestrator call-site change; existing rows read back with NULL.
- `ll_version` is readable through the typed reader path —
  `recent_orchestration_runs()`/`aggregate_orchestration_runs()`/
  `OrchestrationRun` and their `loop_runs` counterparts — not only via raw SQL.
- UPSERT is first-write-wins: a later `record_orchestration_run()` upsert for
  the same `(run_id, issue_id)` under a different `ll_version` (explicit or
  defaulted) does not overwrite the value recorded at dequeue
  (`COALESCE(ll_version, excluded.ll_version)`).
- The migration is an appended v48 `ALTER TABLE` pair; the v22/v23
  `CREATE TABLE` strings are unchanged.
- `schema_manifest.json` matches the live schema; all `SCHEMA_VERSION == 47`
  assertions updated to 48.

## Resolution

- **Action**: implement
- **Completed**: 2026-09-08
- **Status**: Completed

### Changes Made
- `scripts/little_loops/session_store/schema.py` — v48 migration: `ALTER TABLE orchestration_runs ADD COLUMN ll_version TEXT;` / `ALTER TABLE loop_runs ADD COLUMN ll_version TEXT;`; `SCHEMA_VERSION` 47 → 48.
- `scripts/little_loops/session_store/writers.py` — `record_orchestration_run()`/`record_loop_run_summary()` gain a keyword-only `ll_version: str | None = None`, defaulted from `little_loops.__version__` via a function-local import (avoids the `writers.py` ↔ package `__init__.py` circular import). `orchestration_runs` UPSERT uses `ll_version=COALESCE(ll_version, excluded.ll_version)` (first-write-wins); `loop_runs` is a plain `INSERT OR IGNORE` with `ll_version` appended to the column list.
- `scripts/little_loops/history_reader/runs.py` — `ll_version` added to the `recent_orchestration_runs()` SELECT column list and the shared `_LOOP_RUN_COLUMNS` string.
- `scripts/little_loops/history_reader/models.py` — `ll_version: str | None = None` added to `OrchestrationRun` and `LoopRun`.
- `scripts/little_loops/session_store/schema_manifest.json` — regenerated for v48.
- Tests: `TestSchemaV48LlVersionColumns` (schema), `TestOrchestrationRunLlVersion` + `TestLoopRuns` additions (writers), reader-path assertions in `TestNewEventReaders` (events). All 27 `SCHEMA_VERSION == 47` assertions across `test_session_store_writers.py`/`test_session_store_schema.py`/`test_assistant_messages.py` bumped to 48; the `TestPriorityRegexCompletenessAllowlist` line-number allowlist in `test_issue_parser.py` updated for the resulting line shift in `writers.py`.
- Docs: `docs/reference/API.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/ARCHITECTURE.md` updated for the new column and signature params (also closed pre-existing drift in `API.md`'s `OrchestrationRun`/`LoopRun`/`record_loop_run_summary` blocks, which were missing `base_sha`/`base_dirty`/`failure_terminal`).

### Verification Results
- Tests: PASS (23382 passed, 43 skipped; 2 pre-existing unrelated failures on `main` — `test_host_runner.py::TestAC8BaselineCoverage` and `test_verify_evidence.py::TestRepoGate` — confirmed via `git stash` before this work started)
- Lint: PASS (`ruff check` clean on all touched files)
- Types: PASS (`mypy` clean on all touched source files)

### Acceptance Criteria Met
- [x] `ll_version` recorded on new rows without any orchestrator call-site change; existing rows read back NULL (schema-upgrade test)
- [x] `ll_version` readable through the typed reader path (`recent_orchestration_runs()`/`aggregate_orchestration_runs()`/`OrchestrationRun` and `loop_runs` counterparts)
- [x] UPSERT is first-write-wins via `COALESCE(ll_version, excluded.ll_version)`
- [x] v48 migration is an appended `ALTER TABLE` pair; v22/v23 `CREATE TABLE` strings unchanged
- [x] `schema_manifest.json` regenerated; all `SCHEMA_VERSION == 47` assertions updated to 48

## Status

**Open** | Created: 2026-09-07 | Priority: P0

## Session Log
- `/ll:manage-issue` - 2026-09-08T15:31:02 - `97cb2296-7f17-462e-a48c-36a01c338aeb.jsonl`
- `/ll:ready-issue` - 2026-09-08T15:04:03 - `84f1950c-16d3-4d7c-acb2-65d034748e03.jsonl`
- `/ll:confidence-check` - 2026-09-08T14:54:19 - `8322c870-f979-4103-842d-3ba90b32e30b.jsonl`
- `/ll:confidence-check` - 2026-09-08T04:24:30 - `34c68e63-9bdf-4f65-a533-7869136a3414.jsonl`
- `/ll:verify-issues` - 2026-09-08T04:21:41 - `cfa0d01b-9598-41c5-a254-7549b3c32bba.jsonl`
- `/ll:wire-issue` - 2026-09-08T04:17:48 - `c539b25a-7dc7-4833-af11-0f45b8d423ee.jsonl`
- `/ll:refine-issue` - 2026-09-08T04:05:59 - `3bc6d0ac-e755-4e64-bbf5-b3ba1b256912.jsonl`
- `/ll:format-issue` - 2026-09-08T03:48:53 - `2c3dcc18-94f9-46a0-aa50-9e1b85813520.jsonl`
- `/ll:issue-size-review` - 2026-09-08T03:38:19 - `2c3dcc18-94f9-46a0-aa50-9e1b85813520.jsonl`
