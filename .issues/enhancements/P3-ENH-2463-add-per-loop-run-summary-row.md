---
id: ENH-2463
title: Add per-loop-run summary row to history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-02
captured_at: "2026-07-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - loops
  - captured
decision_needed: true
---

# ENH-2463: Add per-loop-run summary row to history.db

## Summary

`loop_events` records per-transition FSM state (`loop_start`, `state_enter`, `route`, `loop_complete`, `retry_exhausted`, …) but no single row summarises a run. To answer "what was the iteration count, final state, and evaluator score of `rn-implement` last Tuesday?" requires replaying the entire `loop_events` stream for that run. Add a `loop_runs` table populated at run completion via a side-effect of `loop_complete` (or a new `loop_run_summary` event) carrying `(run_id, loop_name, started_at, ended_at, final_state, iterations, terminated_by, error, evaluator_score, diagnostics_path)`. Per `thoughts/history-db-expand-wiring.md` §3 ranked recommendation #6: *"one row per completed loop run (final state, iteration count, evaluator score if any, path to `.loops/diagnostics/*.md`), rather than only per-transition events — makes loop health queryable without replaying the whole event stream."*

## Motivation

Loop health is the project's most heavily-instrumented surface, yet it lacks a rollup query:

- **No "best/worst loop last week" without scanning JSONL** — `ll-loop history` exists but is event-stream oriented; users want a summary view.
- **No correlation with diagnostic artifacts** — `loop-specialist` writes `.loops/diagnostics/<loop>-<ts>.md`, but the link between that path and the run row is implicit.
- **No aggregate evaluator score trend** — `mr-baseline`-style comparisons need per-run scores surfaced without per-event reconstruction.
- **Existing close-neighbour fixes are insufficient**:
  - `BUG-2304` (done) fixed the missing `error` field on `loop_complete` events; that's per-transition, not per-run.
  - `ENH-2428` (done) added a `score_stall` evaluator; that's intra-loop, not a rollup.

`loop_runs` is the missing rollup.

## Current Behavior

- `loop_events` carries `(ts, loop_name, state, transition, retries, ...)` rows per transition.
- `loop_complete` events carry `(final_state, iterations, terminated_by, error)` (after BUG-2304).
- `.loops/diagnostics/<loop>-<ts>.md` exists if `loop-specialist` ran, but isn't DB-linked.
- `ll-loop history` prints the event stream; `ll-loop promote-baseline` operates on baselines; neither surfaces a per-run summary.
- `ll-session search --fts "<loop_name>"` returns transition rows, not summary rows.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/session_store.py:208-545` — append v19 entry to `_MIGRATIONS` AND manually bump `SCHEMA_VERSION = 18` → `SCHEMA_VERSION = 19` at line 102 (the constant is **separate** from `len(_MIGRATIONS)` and is not auto-derived — both edits are required)
- `scripts/little_loops/session_store.py:17-37` (module docstring public API list) — add `record_loop_run_summary()` and `update_loop_run_diagnostics()` to the enumerated public functions (the docstring is the rendered public-API surface)
- `scripts/little_loops/session_store.py:104-130` — add `"loop_run"` to `_VALID_KINDS` and `"loop_run": "loop_runs"` to `_KIND_TABLE` (paired registry; both must move together)
- `scripts/little_loops/session_store.py:133-145` — add `"loop_run"` to `_LOOP_EVENT_TYPES` if emitting a new `loop_run_summary` event (not needed if piggy-backing on `loop_complete`)
- `scripts/little_loops/session_store.py:1341-1376` (`SQLiteTransport.send`) — extend the `loop_complete` branch (or add a new branch) to upsert into `loop_runs` (idempotent via `INSERT OR IGNORE` on the `run_id` UNIQUE constraint, mirroring `record_commit_event` at lines 1041-1091)
- `scripts/little_loops/session_store.py` (new function `record_loop_run_summary`) — model on `record_commit_event` pattern; INSERT OR IGNORE + conditional `_index()` call only when `cursor.rowcount` is truthy
- `scripts/little_loops/session_store.py` (new function `update_loop_run_diagnostics`) — single UPDATE by `run_id`, mirrors `skill_events` completion-UPDATE at line 991
- `scripts/little_loops/fsm/executor.py:2269-2309` (`_finish()`) — after `_emit("loop_complete", payload)` at line 2278, populate `loop_runs` columns from locals (`self.started_at` set at line 339; `self.fsm.context.get("run_dir", "")` for the run-id source)
- `scripts/little_loops/history_reader.py:472-598` — add `recent_loop_runs()`, `find_loop_run()`, `aggregate_loop_runs()` (model: `recent_commit_events` at line 524, `summarize_skills` at line 472 for the GROUP BY rollup)
- `scripts/little_loops/cli/session.py:88-141` — add `"loop_run"` to the `choices=[...]` list for both `search_parser.add_argument("--kind", ...)` and `recent_parser.add_argument("--kind", ...)`
- `agents/loop-specialist.md:73-76` — append instruction to call `update_loop_run_diagnostics(run_id, path)` after writing the diagnostic artifact (matches agent→DB ingestion pattern used by `record_correction`)

### Existing abstractions to reuse
- `_bootstrap_schema_at(db, N)` — `scripts/tests/test_session_store.py:3075-3095` — shared helper for "old DB upgrades cleanly" migration tests
- `_index(conn, content, kind, ref, anchor, ts)` — `session_store.py:705-718` — single FTS5 row inserter; call only when the row was actually inserted (avoid double-indexing)
- `_connect_readonly(db_path)` — `history_reader.py:235-249` — opens `mode=ro` + `PRAGMA query_only = ON`; degrades gracefully to `None` on failure
- `_row_to_dataclass(row, dataclass)` — `history_reader.py:252+` — map sqlite3.Row → typed dataclass; pair with new `LoopRun` dataclass

### Tests to update / add
- `scripts/tests/test_session_store.py:49, 1858, 2883` — bump `assert SCHEMA_VERSION == 18` → `== 19` (or change to `== SCHEMA_VERSION` so they don't keep breaking)
- `scripts/tests/test_session_store.py` — add `TestSchemaV19LoopRuns` class (model: `TestSchemaV15SkillCompletionColumns` at line 3098)
- `scripts/tests/test_session_store.py` — add `TestRecordLoopRunSummary` (model: `TestRecordCommitEvent`); cover normal completion, error termination, idempotent re-insert via UNIQUE
- `scripts/tests/test_history_reader.py` — add `TestHistoryLoopRunsRead` for `recent_loop_runs()`, `find_loop_run()`, `aggregate_loop_runs()`

### Documentation
- `docs/ARCHITECTURE.md` — schema versions table (around line 612) — add v19 row referencing ENH-2463
- `docs/reference/API.md:6527` (`## little_loops.history_reader`) — document `recent_loop_runs`, `find_loop_run`, `aggregate_loop_runs`
- `docs/reference/API.md:6970` (`## little_loops.session_store`) — document `record_loop_run_summary`, `update_loop_run_diagnostics`
- `docs/reference/CLI.md` — new flags (`ll-session recent --kind loop_run`, `ll-loop history --summary`, `ll-loop runs --since`)
- `docs/reference/schemas/loop_run.json` (new) — regenerate via `ll-generate-schemas` after schema lands

### Configuration
- `.ll/ll-config.json` — `analytics.capture.loop_runs` flag (defaults to `true` per "permissive default" pattern at `session_store.py:738`); gate the transport-layer write

## Expected Behavior

- `loop_runs` table exists with columns: `id`, `run_id` (UNIQUE), `loop_name`, `started_at`, `ended_at`, `final_state`, `iterations`, `terminated_by`, `error`, `evaluator_score REAL`, `diagnostics_path`, `head_sha`, `branch`.
- A side-effect of `loop_complete` event processing (or a new writer at the same `_finish()` site) inserts a `loop_runs` row keyed by `run_id`.
- `ll-session recent --kind loop_run` returns rows; `ll-session search --fts "<loop_name>" --kind loop_run` returns matches.
- `ll-loop history --summary` (new flag, optionally) prints a table from `loop_runs` instead of (or in addition to) the event stream.
- Diagnostic artifact linkage: when `loop-specialist` writes a `.loops/diagnostics/<loop>-<ts>.md`, update the matching `loop_runs.diagnostics_path` column.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS loop_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,         -- e.g. "rn-implement-20260702T101530"
    loop_name TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    final_state TEXT,
    iterations INTEGER,
    terminated_by TEXT,
    error TEXT,
    evaluator_score REAL,
    diagnostics_path TEXT,
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_loop_runs_loop_name ON loop_runs(loop_name);
CREATE INDEX IF NOT EXISTS idx_loop_runs_terminated_by ON loop_runs(terminated_by);
CREATE INDEX IF NOT EXISTS idx_loop_runs_evaluator_score ON loop_runs(evaluator_score);
```

Bump `SCHEMA_VERSION`. Add `"loop_run"` to `_VALID_KINDS` and `"loop_run": "loop_runs"` to `_KIND_TABLE`.

### Producer wiring

- In `scripts/little_loops/fsm/executor.py::_finish()` (where `loop_complete` is emitted per BUG-2304), after the existing `_emit("loop_complete", payload)` call, write a `loop_runs` row keyed by `run_id`:
  - `run_id` is the run's timestamped identifier (already used in `.loops/runs/<loop-name>-<timestamp>/events.jsonl`).
  - Populate `final_state`, `iterations`, `terminated_by`, `error` from the existing `_finish()` locals.
  - `started_at` is the run's first `loop_start` event ts (`loop_events` is the source; query for `ts ORDER BY ts ASC LIMIT 1 WHERE loop_name=? AND run_id=?`).
  - `evaluator_score`: if the loop ran an `output_numeric` evaluator with a numeric score, capture it. Defer deeper score-extraction work to follow-on; start with `NULL`.
- Hook into the FSM event ingest path (`scripts/little_loops/session_store.py`) so ingested `loop_complete` JSONL events also upsert into `loop_runs` (idempotent on `run_id`).
- Update `loop-specialist` (`agents/loop-specialist.md`) artifact write to also call `update_loop_run_diagnostics(run_id, diagnostics_path)` when it writes `.loops/diagnostics/<loop>-<ts>.md`.

### Read API

Add to `history_reader.py`:
- `recent_loop_runs(loop_name=None, since=None, limit=50)` — list summaries.
- `find_loop_run(run_id)` — single record by id.
- `aggregate_loop_runs(group_by: Literal["loop_name","terminated_by"], since=None)` — pass-rate / iteration-count rollups.

### CLI surface

- `ll-session recent --kind loop_run` — new `--kind` option.
- `ll-loop history --summary` — render from `loop_runs` instead of events.
- `ll-loop runs --since YYYY-MM-DD` — new subcommand listing recent runs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The proposed solution is sound, but the research surfaced three decision points that an implementer should resolve before writing code. Each has multiple viable options:

**Decision A — Producer wiring (one row per run)**
- **Option A1**: Side-effect of existing `loop_complete` event — modify `SQLiteTransport.send()` at `session_store.py:1353` to also write `loop_runs` when `event_type == "loop_complete"`. Pros: no new event type, no `_LOOP_EVENT_TYPES` change, single ingest path. Cons: conflates per-transition and per-run semantics in one branch.
- **Option A2**: New `loop_run_summary` event — emit from `fsm/executor.py:_finish()` at line 2278 alongside `loop_complete`; add `"loop_run_summary"` to `_LOOP_EVENT_TYPES` at `session_store.py:133`. Pros: clean separation; can be re-emitted on backfill without side effects. Cons: two emits per run; more code surface.
- **Recommendation**: Option A1. Matches the existing transport-layer "fan-out" pattern (one event → multiple table writes); the JSONL backfill reader at `_backfill_loops:1586` would automatically populate `loop_runs` from historical `loop_complete` events with no additional backfill code.

**Decision B — `evaluator_score` extraction**
- **Option B1**: Defer (start with `NULL`) — `loop_runs.evaluator_score` is nullable; document a follow-up issue. Cheapest; matches ENH-2476's nullable-final-score pattern. Cons: no aggregate-score trend until the follow-on lands.
- **Option B2**: New accumulator — add `self._evaluator_scores: list[float]` to `FSMExecutor.__init__`, updated inside `_evaluate()` when `state.evaluate.type == "output_numeric"` returns a numeric `details["value"]`. Pros: precise. Cons: invasive; one more mutable on the executor; risks drift between accumulator and event-stream-derived scores.
- **Option B3**: Post-hoc from `summary.json` — `persistence.py:archive_run()` already copies `run_dir/summary.json` to the archive (line 509); `_finish()` can read it before archiving. Pros: reuses an existing artifact; no executor change. Cons: depends on every loop writing `summary.json`, which is not yet universal.

**Decision C — `diagnostics_path` observation**
- **Option C1**: Best-effort glob at `_finish()` — after `_emit("loop_complete", ...)`, glob `.loops/diagnostics/<loop-name>-*` and record the newest match. Pros: zero new wiring; works retroactively. Cons: racy (agent may still be writing); assumes the agent already finished.
- **Option C2**: Sub-agent-stop hook — emit a `diagnostic_written` event from a hook watching the `.loops/diagnostics/` directory; route to `loop_runs.diagnostics_path` via `SQLiteTransport`. Pros: clean; mirrors the existing `record_correction` agent→DB ingestion pattern. Cons: requires hook plumbing.
- **Option C3**: Skip on v1 — make `diagnostics_path` nullable; document a follow-up. Pros: ships the row + read API immediately. Cons: the headline use case ("link the run row to the diagnostic artifact") is incomplete until the hook lands.
- **Recommendation**: Option A1 + C1 + B1 for the v1 migration (cheapest path; all three fields are nullable so the follow-on work slots in cleanly), with follow-on issues filed for B2/C2 if evaluator-score trend or reliable diagnostic linking are blocking.

**Two parallel `run_id` conventions exist in the codebase — pick the archive one for `loop_runs.run_id`**:
- **Invocation-time `instance_id`** (e.g. `rn-implement-20260702T101530`) — generated by `_make_instance_id(loop_name)` at `cli/loop/_helpers.py:1239`; flows into `fsm.context["run_dir"]` at `cli/loop/run.py:178`. Available at `_finish()` via `Path(self.fsm.context["run_dir"]).name`.
- **Archive-time `run_id`** (e.g. `20260702T101530-rn-implement`) — derived at `fsm/persistence.py:494` via `state.started_at.replace(":", "").replace(".", "").replace("+", "")[:17]` then `f"{run_id}-{self.loop_name}"`. This is the value that ends up in `.loops/.history/<run_id>-<loop-name>/` and is queryable indefinitely.
- **Canonical choice**: Use the archive-time convention so `loop_runs.run_id` JOINs cleanly to on-disk archives. Derive it from `self.started_at` at `_finish()` time using the same string-mangling as `persistence.py:494`.

**Implementation pattern to follow** (close parallel from ENH-2458):
- Migration v17 (`session_store.py:521-544`) for `test_run_events` is the most-recent additive-table precedent. Same UNIQUE-key idempotency, same `_index()` FTS call, same `recent_*` reader pattern.
- `record_commit_event` at `session_store.py:1041-1091` is the exact shape for `record_loop_run_summary` (UNIQUE + `INSERT OR IGNORE` + conditional `_index()`).
- `_bootstrap_schema_at(db, 18)` at `test_session_store.py:3075` plus a `TestSchemaV19LoopRuns` class mirroring `TestSchemaV15SkillCompletionColumns:3098` is the migration-test recipe.

**Phase 2 — additional gaps surfaced by the codebase-analyzer + pattern-finder passes:**

**Gap F — Public API docstring update at `session_store.py:17-37`**: The module-level docstring at lines 17-37 enumerates every public function (currently lists `record_commit_event`, `record_test_run_event`, etc.). `record_loop_run_summary()` and `update_loop_run_diagnostics()` must be appended there or the rendered public-API surface will omit them. (Verified: this docstring is the one referenced by `docs/reference/API.md:6970`.)

**Gap G — DES observability schema decision**: `scripts/little_loops/observability/schema.py` is the source for the DES (Discrete Event Schema) and feeds `ll-verify-des-audit`. If Decision A1 is taken (piggy-back on `loop_complete`, no new event type), no DES entry is needed — the existing `loop_complete` schema entry covers the new `loop_runs` write as a side-effect. If Decision A2 is taken (new `loop_run_summary` event), a new DES entry is required AND `ll-verify-des-audit` must pass. Recommendation reinforces A1.

**Gap H — Resume-path semantics for `loop_runs.run_id`**: When a run resumes (`cli/loop/lifecycle.py:503-504` re-injects `run_dir`), `self.started_at` is preserved across segments. The archive-time `run_id` derivation (`state.started_at.replace(":","").replace(".","").replace("+","")[:17] + "-" + self.fsm.name`) therefore produces the **same `run_id` for the resumed run** as for the original segment. The UNIQUE constraint + `INSERT OR IGNORE` pattern correctly absorbs the duplicate. No special handling needed; this is a feature, not a bug — a resumed-then-completed run is one logical run.

**Gap I — Schema versions table callout sites in ARCHITECTURE.md**: The schema versions table at `docs/ARCHITECTURE.md:614-633` has multiple other callouts referencing the version range. From the codebase-locator: line 632 (table footer), line 678 (`SS->DB: ensure_db() — bootstrap schema (v1–v18)`), line 703 (`ensure_db() ... Bootstrap schema (v1–v18 migrations)`), line 749 ("full schema-version table (v1–v18)"). All four must be bumped to `v1–v19` or `v18` → `v19` when v19 lands, otherwise the docs drift from the schema. The new table row goes at line 633 (appended).

**Gap J — `_split_sql_statements` helper**: The `_bootstrap_schema_at(db, N)` helper at `test_session_store.py:3075-3095` calls `_split_sql_statements(script)` from `session_store.py` to parse the triple-quoted migration string into individual statements. The new v19 SQL block should follow the same multi-statement layout (CREATE TABLE + 3 CREATE INDEX) that v17 and v18 use, so the splitter handles it without modification.

**Gap K — `loop_name` injection at `_emit`**: The codebase-analyzer confirmed that `_emit("loop_complete", payload)` in `executor.py:_finish()` propagates `loop_name` through the transport (the executor's `_emit` method reads `self.fsm.name`). So the new branch in `SQLiteTransport.send` at line 1353 already has access to `loop_name` via `event.get("loop_name", "")` — no separate wiring required.

**Gap L — Public API parity with `record_*` family**: `record_loop_run_summary()` should accept a `config: dict | None = None` parameter (forward-compat stub matching `record_commit_event` and `record_test_run_event`) so the `analytics.capture.loop_runs` gate can be honored without API churn later.

**Gap M — FTS5 `kind` discriminator**: When calling `_index()` from `record_loop_run_summary()`, use `kind="loop_run"` (must match the new `_VALID_KINDS` entry) and `ref=run_id` / `anchor=loop_name` — mirroring `record_test_run_event` (`kind="test_run"`, `ref=head_sha`, `anchor=branch`).

## Acceptance Criteria

- Schema migration lands; `loop_runs` table exists with `SCHEMA_VERSION` bumped.
- A run of `ll-loop run oracles/generator-evaluator` produces one `loop_runs` row at completion, with correct `final_state`, `iterations`, `terminated_by`, `error` (per BUG-2304 fix).
- The `started_at` column matches the run's actual `loop_start` ts (within 1 second).
- An interrupted run (`Ctrl-C`) still writes a `loop_runs` row with `terminated_by="error"` and a populated `error`.
- `ll-session recent --kind loop_run` returns rows; FTS search matches `loop_name`.
- Diagnostic-path update: when `loop-specialist` writes its artifact, the matching `loop_runs.diagnostics_path` is updated.
- Tests cover: normal completion, error termination, evaluator-score field (even if `NULL`), diagnostic-path linkage.

## Implementation Steps

1. **Schema migration** — append a v19 SQL block to `_MIGRATIONS` at `scripts/little_loops/session_store.py:208-545` (after the v18 entry at line 544). **Also manually bump `SCHEMA_VERSION = 18` → `SCHEMA_VERSION = 19` at line 102** — the constant is a separate module attribute and is NOT auto-derived from `len(_MIGRATIONS)` (verified by codebase-analyzer). Follow the v17 (`test_run_events`) precedent at lines 521-544 for the SQL shape: `CREATE TABLE` + 3 named indexes (`loop_name`, `terminated_by`, `started_at`).
2. **Registry updates** — add `"loop_run"` to `_VALID_KINDS` (`session_store.py:104`) and `"loop_run": "loop_runs"` to `_KIND_TABLE` (`session_store.py:119`). Both move together; the validation gate at line 1278 enforces this pairing. Also add `record_loop_run_summary()` and `update_loop_run_diagnostics()` to the public API docstring enumeration at `session_store.py:17-37` (the docstring is the rendered public-API surface referenced by `docs/reference/API.md:6970`).
3. **`record_loop_run_summary()`** — new function in `session_store.py`, modeled on `record_commit_event` at line 1041. Signature: `(db_path, run_id, loop_name, started_at, ended_at, final_state, iterations, terminated_by, error, evaluator_score=None, diagnostics_path=None, config: dict | None = None) -> bool`. Uses `INSERT OR IGNORE` on the `run_id` UNIQUE constraint; calls `_index()` only when `cursor.rowcount` is truthy (with `kind="loop_run"`, `ref=run_id`, `anchor=loop_name`); exports the function for re-use by `SQLiteTransport`. The `config` parameter is a forward-compat stub matching `record_commit_event` / `record_test_run_event` so the `analytics.capture.loop_runs` gate can be honored later without API churn.
4. **`update_loop_run_diagnostics()`** — new function in `session_store.py`, single `UPDATE loop_runs SET diagnostics_path=? WHERE run_id=?` per the `skill_events` completion-UPDATE pattern at line 991. Simple-by-primary-key (no return value).
5. **Wire `_finish()`** — at `fsm/executor.py:2278`, immediately after `_emit("loop_complete", payload)`, compute the archive-time `run_id` via `self.started_at.replace(":", "").replace(".", "").replace("+", "")[:17] + "-" + self.fsm.name` (mirrors `fsm/persistence.py:494`); then call `record_loop_run_summary(...)` with the locals. Make the call best-effort (try/except, log warning) — `_finish()` must never fail because the sink is unhappy.
6. **Wire JSONL ingest** — at `session_store.py:1353` (the `event_type == "loop_complete"` branch in `SQLiteTransport.send`), call `record_loop_run_summary()` with the event-payload fields. This is the backfill path — historical JSONL replays from `.loops/.history/*/events.jsonl` will populate `loop_runs` on next `ll-session backfill`.
7. **Update `loop-specialist` agent** — at `agents/loop-specialist.md:73-76`, append a bullet after the artifact-write step: "After writing the diagnostic artifact, call `update_loop_run_diagnostics(run_id, "<artifact-path>")` to link the artifact to the run row in `history.db`." Run-id is extracted from the artifact filename.
8. **Extend `history_reader`** — add three functions to `scripts/little_loops/history_reader.py`, modeled on `recent_commit_events` (line 524) and `summarize_skills` (line 472):
   - `recent_loop_runs(*, loop_name=None, since=None, limit=50)` → `list[LoopRun]`
   - `find_loop_run(run_id)` → `LoopRun | None`
   - `aggregate_loop_runs(group_by: Literal["loop_name","terminated_by"], since=None)` → `list[dict]` (pass-rate + iteration-count rollups)
   Add `LoopRun` dataclass.
9. **CLI surface** — three changes:
   - `scripts/little_loops/cli/session.py:91-130` — add `"loop_run"` to the `choices=[...]` list for both `search_parser.add_argument("--kind", ...)` and `recent_parser.add_argument("--kind", ...)`.
   - `scripts/little_loops/cli/loop/__init__.py:13` — register a new `runs` subcommand that calls `recent_loop_runs(since=...)` and renders a table.
   - `scripts/little_loops/cli/loop/info.py` — add `--summary` flag to the `history` subcommand; when set, source rows from `loop_runs` via `recent_loop_runs()` instead of the event stream.
10. **Tests** — add four test classes:
    - `TestSchemaV19LoopRuns` in `test_session_store.py` — uses `_bootstrap_schema_at(db, 18)` (helper at line 3075) + `ensure_db()`; asserts v19 columns + indexes exist; verifies pre-v19 rows survive the upgrade with NULL completion columns.
    - `TestRecordLoopRun` in `test_session_store.py` — covers normal completion, error termination, idempotent re-insert via UNIQUE; mirrors `TestRecordCommitEvent`.
    - `TestLoopSpecialistUpdatesDiagnostics` in `test_session_store.py` (or new file) — exercises `update_loop_run_diagnostics()`; verifies the row's `diagnostics_path` column updates while other fields remain untouched.
    - `TestHistoryLoopRunsRead` in `test_history_reader.py` — exercises `recent_loop_runs()`, `find_loop_run()`, `aggregate_loop_runs()`.
    - Also bump the three `assert SCHEMA_VERSION == 18` assertions at `test_session_store.py:49, 1858, 2883` to `== SCHEMA_VERSION` (or `== 19`) so they survive future migrations.
11. **Documentation** — five files:
    - `docs/ARCHITECTURE.md` — schema versions table (around line 614-633); add v19 row referencing ENH-2463. **Also bump the four version-range callouts** at lines 632, 678, 703, 749 (each currently says "v1–v18" — change to "v1–v19") so the prose matches the table.
    - `docs/reference/API.md:6527` (`## little_loops.history_reader`) — document `recent_loop_runs`, `find_loop_run`, `aggregate_loop_runs`, `LoopRun`.
    - `docs/reference/API.md:6970` (`## little_loops.session_store`) — document `record_loop_run_summary`, `update_loop_run_diagnostics`.
    - `docs/reference/CLI.md` — new flags (`ll-session recent --kind loop_run`, `ll-loop history --summary`, `ll-loop runs --since`).
    - Run `ll-generate-schemas` to emit `docs/reference/schemas/loop_run.json`.
    - **DES audit pass** (only if Decision A2 is taken): if a new `loop_run_summary` event type is emitted, add a corresponding entry to `scripts/little_loops/observability/schema.py` and verify `ll-verify-des-audit` passes. Decision A1 (recommended) piggy-backs on the existing `loop_complete` event, so this step is skipped.
12. **Verification** — run `python -m pytest scripts/tests/test_session_store.py scripts/tests/test_history_reader.py -v`; expect green. Then run a real `ll-loop run oracles/generator-evaluator` end-to-end and confirm the matching `loop_runs` row appears in `ll-session recent --kind loop_run`.

## Sources

- `thoughts/history-db-expand-wiring.md` — recommendations §2 row 3 ("Loop run final outcomes / evaluator scores"), §3 ranked recommendation #6
- `.issues/bugs/P2-BUG-2304-loop-complete-event-omits-error-field.md` — `loop_complete` `error` field reference
- `.issues/enhancements/P3-ENH-2428-score-plateau-early-stop-for-generator-evaluator.md` — sibling evaluator work
- `scripts/little_loops/fsm/executor.py::_finish()` — emit site for `loop_complete`
- `agents/loop-specialist.md` — diagnostic artifact writer

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` module references |
| `docs/reference/CLI.md` | New `ll-session`, `ll-loop` flags |
| `docs/guides/LOOPS_GUIDE.md` | Loops debugging section |

## Status

**Open** | Created: 2026-07-02 | Priority: P3

## Session Log
- `/ll:refine-issue` - 2026-07-07T07:05:11 - `af395362-9221-4c5e-9038-fca90275d34a.jsonl`
- `/ll:refine-issue` - 2026-07-07T00:06:36 - `6c59385b-d02b-4ef9-8cb4-4a48daafa67d.jsonl`
- audit - 2026-07-06 - Fixed loop-specialist agent path in Sources (`agents/loop-specialist.md`, not `scripts/little_loops/agents/`). Note for implementer: schema is at v18 as of 2026-07-06, so the new migration lands as v19+; `_finish()` is at `fsm/executor.py:2269`.
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
