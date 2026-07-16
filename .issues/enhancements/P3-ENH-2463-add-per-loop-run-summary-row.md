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
decision_needed: false
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

### Codebase Research Findings

_Added by `/ll:refine-issue` (gap-analysis pass, 2026-07-16) — anchor refresh against current code. The Integration Map line numbers above have drifted; use the current anchors below and the [Scope Boundary](#scope-boundary) note (SCHEMA_VERSION is now **20**, not 18/19)._

**Behavioral corrections (not just line drift):**

- ⚠ **Constant is `VALID_KINDS`, not `_VALID_KINDS`.** Every reference above/below (Integration Map, Proposed Solution, Implementation Steps 2) to `_VALID_KINDS` should read `VALID_KINDS` — a public name exported in `__all__` (`session_store.py:64`), defined as a tuple at `session_store.py:209`. The validation gate lives at `session_store.py:1473`.
- ⚠ **CLI `--kind` choices are now auto-derived — the "add `loop_run` to the `choices=[...]` list" step is a NO-OP.** `cli/session.py:103` and `:115` both use `choices=list(VALID_KINDS)` (imported at `cli/session.py:45`). Adding `"loop_run"` to `VALID_KINDS` automatically flows into both `search --kind` and `recent --kind`. This supersedes the Integration Map bullet for `cli/session.py:88-141` and the first bullet of Implementation Step 9. Only the `ll-loop runs` subcommand and `ll-loop history --summary` remain as real CLI work.

**Current authoritative anchors (replace the drifted line numbers above):**

| Symbol | Was cited | Current |
|--------|-----------|---------|
| `SCHEMA_VERSION` (value `20`) | `session_store.py:102` | `session_store.py:207` |
| `_MIGRATIONS` list | `session_store.py:208-545` | `session_store.py:333` |
| `VALID_KINDS` tuple | `session_store.py:104` (`_VALID_KINDS`) | `session_store.py:209` |
| `_KIND_TABLE` | `session_store.py:119` | `session_store.py:223` |
| `_LOOP_EVENT_TYPES` | `session_store.py:133` | `session_store.py:258` (`"loop_complete"` at `:262`) |
| `record_commit_event` (shape to copy) | `session_store.py:1041` | `session_store.py:1222` |
| `record_test_run_event` (shape to copy) | — | `session_store.py:1352` |
| `SQLiteTransport.send` `loop_complete` branch | `session_store.py:1353` | `session_store.py:1543` (`if event_type == "loop_complete"`) |
| `summarize_skills` (rollup model) | `history_reader.py:472` | `history_reader.py:497` |
| `recent_commit_events` (reader model) | `history_reader.py:524` | `history_reader.py:651` |
| `FSMExecutor._finish()` | `fsm/executor.py:2269` | `fsm/executor.py:2415` |
| `_emit("loop_complete", payload)` | `fsm/executor.py:2278` | `fsm/executor.py:2424` |
| archive-time `run_id` derivation | `fsm/persistence.py:494` | `fsm/persistence.py:518` |

The `record_test_run_event` at `session_store.py:1352` (v18/ENH-2459) is now the most-recent additive-writer precedent alongside `record_commit_event` — model `record_loop_run_summary` on either.

## Expected Behavior

- `loop_runs` table exists with columns: `id`, `run_id` (UNIQUE), `loop_name`, `started_at`, `ended_at`, `final_state`, `iterations`, `terminated_by`, `error`, `evaluator_score REAL`, `diagnostics_path`, `head_sha`, `branch`.
- A side-effect of `loop_complete` event processing (or a new writer at the same `_finish()` site) inserts a `loop_runs` row keyed by `run_id`.
- `ll-session recent --kind loop_run` returns rows; `ll-session search --fts "<loop_name>" --kind loop_run` returns matches.
- `ll-loop history --summary` (new flag, optionally) prints a table from `loop_runs` instead of (or in addition to) the event stream.
- Diagnostic artifact linkage: when `loop-specialist` writes a `.loops/diagnostics/<loop>-<ts>.md`, update the matching `loop_runs.diagnostics_path` column.
- _Known v1 coverage gap (per Gap Q + Gap R):_ runs that exit via handoff (`_handle_handoff()`) or force-archive (`PersistentExecutor.archive_run_only()` at `fsm/persistence.py:839-895`) do not call `_finish()` and therefore write no `loop_runs` row. Hard process kills — `SystemExit`, `KeyboardInterrupt` escaping configured handlers, and other `BaseException` paths — also skip `_finish()` (no `finally` block in `FSMExecutor.run()`). Reconciler follow-on issues (Decision G2 + G3) will close this gap.

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

> **Selected:** Option A1 — per the stated recommendation. Side-effect of existing `loop_complete` keeps the transport-layer fan-out pattern intact and lets JSONL backfill auto-populate `loop_runs`.

- **Option A1**: Side-effect of existing `loop_complete` event — modify `SQLiteTransport.send()` at `session_store.py:1353` to also write `loop_runs` when `event_type == "loop_complete"`. Pros: no new event type, no `_LOOP_EVENT_TYPES` change, single ingest path. Cons: conflates per-transition and per-run semantics in one branch.
- **Option A2**: New `loop_run_summary` event — emit from `fsm/executor.py:_finish()` at line 2278 alongside `loop_complete`; add `"loop_run_summary"` to `_LOOP_EVENT_TYPES` at `session_store.py:133`. Pros: clean separation; can be re-emitted on backfill without side effects. Cons: two emits per run; more code surface.
- **Recommendation**: Option A1. Matches the existing transport-layer "fan-out" pattern (one event → multiple table writes); the JSONL backfill reader at `_backfill_loops:1586` would automatically populate `loop_runs` from historical `loop_complete` events with no additional backfill code.

**Decision B — `evaluator_score` extraction**

> **Selected:** Option B1 — per the stated recommendation. Defer score extraction to a follow-on; `loop_runs.evaluator_score` is nullable.

- **Option B1**: Defer (start with `NULL`) — `loop_runs.evaluator_score` is nullable; document a follow-up issue. Cheapest; matches ENH-2476's nullable-final-score pattern. Cons: no aggregate-score trend until the follow-on lands.
- **Option B2**: New accumulator — add `self._evaluator_scores: list[float]` to `FSMExecutor.__init__`, updated inside `_evaluate()` when `state.evaluate.type == "output_numeric"` returns a numeric `details["value"]`. Pros: precise. Cons: invasive; one more mutable on the executor; risks drift between accumulator and event-stream-derived scores.
- **Option B3**: Post-hoc from `summary.json` — `persistence.py:archive_run()` already copies `run_dir/summary.json` to the archive (line 509); `_finish()` can read it before archiving. Pros: reuses an existing artifact; no executor change. Cons: depends on every loop writing `summary.json`, which is not yet universal.

**Decision C — `diagnostics_path` observation**

> **Selected:** Option C1 — per the stated recommendation. Best-effort glob at `_finish()` keeps v1 wiring trivial; `loop_runs.diagnostics_path` is nullable so C2/C3 follow-ons slot in cleanly.

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

---

**Pass-3 findings** (added by `/ll:refine-issue --auto`, 2026-07-16) — three behavioral refutations of the prior Gap K/Pass-2 claims and four new gaps surfaced by codebase-analyzer + pattern-finder against live source state. Implementation Steps 5 and 9, and Expected Behavior, are affected — see also the addenda appended there.

**Refutations of prior-pass claims:**

- ⚠ **Gap N — `_finish()` does NOT emit `loop_name`.** The Gap K claim that `_emit("loop_complete", payload)` propagates `loop_name` via `self.fsm.name` is **false**. Verified at `fsm/executor.py:2124-2132`: `_emit()` only adds `event` and `ts`. Only `loop_start` explicitly supplies `{"loop": self.fsm.name}` at `executor.py:389-393`. On the `loop_complete` path, `SQLiteTransport.send()` reads `event.get("loop_name", "")` and gets `""`. **Implication**: a transport-side fan-out cannot populate `loop_runs.loop_name`. The producer-side `record_loop_run_summary()` call from `_finish()` must receive `loop_name` as a direct arg from `self.fsm.name` (Decision D2). The transport-side write path becomes the backfill / historical-replay path only (see Gap P).
- ⚠ **Gap O — `_finish()` emits `final_state`; transport reads `outcome`.** At `session_store.py:1543-1544`, the `loop_complete` branch sets `state = event.get("outcome", state)`. The current `_finish()` payload uses the key `final_state` (per BUG-2304), so `final_state` does NOT reach `loop_events.state`. **Implication**: a transport-side fan-out keyed off `final_state` would silently write `None`. The producer-side `record_loop_run_summary()` call from `_finish()` with the local `final_state` is the correct wiring (matches Implementation Step 5's "with the locals" phrasing exactly).
- ⚠ **Gap P — JSONL backfill refutation.** The Pass-2 claim that "extending `SQLiteTransport.send()` would automatically make historical `.loops/.history/*/events.jsonl` replay populate `loop_runs`" is **false**. Current backfill paths: session JSONL → `raw_events` only via `_backfill_raw_events()` (`session_store.py:2700-2756`); loop backfill reads state JSON via `_backfill_loops()` (lines 1776-1807) and inserts synthetic `transition="backfill"` rows directly. `rebuild()` (lines 2838-2898) explicitly excludes `loop_events` from materialization (commented at lines 2818-2823). **Implication**: historical `.loops/.history/*/events.jsonl` archives will NOT populate `loop_runs` retroactively. Backfill is a separate follow-on (Decision F).

**New behavioral facts:**

- ⚠ **Gap Q — Handoff + force-archive paths skip `_finish()`.** `PersistentExecutor.archive_run_only()` at `fsm/persistence.py:839-895` writes final state and archives without calling `_finish()` and therefore emits no `loop_complete`. The handoff path (`_handle_handoff()`) similarly builds `ExecutionResult` directly. **Implication**: ~5–10% of runs (forced shutdowns, handoffs) will have no `loop_runs` row even with the producer-side wiring. Document as known v1 coverage gap; close via Decision G follow-on.
- ⚠ **Gap R — `_finish()` is not guaranteed for `BaseException` paths.** `FSMExecutor.run()` catches `except Exception` at `executor.py:729-738` but has no `finally` that guarantees `_finish()`. Hard process kills, `SystemExit`, `KeyboardInterrupt` escaping configured handlers, and other `BaseException` subclasses do NOT receive a guaranteed `_finish()` call. Smaller, separate coverage gap from Q; both should be documented.
- ⚠ **Gap S — `loop-specialist` filenames do NOT encode the FSM archive run_id.** The artifact filename is `.loops/diagnostics/<loop-name>-<UTC-ts>.md` per `agents/loop-specialist.md:75`. The FSM archive run_id is a different identifier (`<compact-ts>-<loop-name>`, e.g. `20260702T101530-rn-implement`). The agent→DB wiring cannot extract `run_id` from the artifact filename; the agent must receive `run_id` as a separate input. **Practical v1**: defer DB linkage (Option C3, "Skip on v1") until an upstream caller can supply `run_id`.
- ⚠ **Gap T — Line 991 staleness for the skill_events completion-UPDATE pattern.** Cited line 991 is `record_skill_event()`'s initial insert area. The actual completion `UPDATE` lives in `skill_event_context()` at `session_store.py:1164-1180`, which updates by numeric row `id` (not by `run_id`). For `update_loop_run_diagnostics(run_id, path)`, the equivalent is `UPDATE loop_runs SET diagnostics_path=? WHERE run_id=?` — the structural pattern is right; only the lookup key differs (textual UNIQUE `run_id` vs. numeric primary `id`).

**New decision points (Pass-3):**

**Decision D — `loop_name` propagation into `loop_runs` (see Gap N)**

> **Selected:** Option D2 — per the stated recommendation. `self.fsm.name` is already in scope at `_finish()`; direct arg-pass avoids touching the event contract.

**Option D1**: Modify `_finish()` payload to include `"loop": self.fsm.name` (mirror `loop_start` at `executor.py:389-393`). Fixes the transport-side `loop_name` gap once for all `loop_complete` consumers. Small event-shape change.

**Option D2**: Pass `loop_name` as a separate direct arg to `record_loop_run_summary()` from `_finish()` (bypass the event). Smallest blast radius; no event-shape change. Requires `_finish()` to import the writer.

**Option D3**: Drop `loop_name` from the row; use `run_id` only and cross-join to `loop_events` for loop_name on read. Simpler schema; costlier queries.

**Recommended**: Option D2. `self.fsm.name` is already in scope at `_finish()`; direct arg-pass is the smallest change and avoids touching the event contract.

**Decision E — `started_at` population (see Gap N)**

> **Selected:** Option E3 — per the stated recommendation. Pass `self.started_at` as a direct arg from `_finish()` (paired with D2); zero DB hit, zero event change.

**Option E1**: Add `started_at` to `_finish()` payload (mirror BUG-2304 shape). Explicit, in-band. Event-shape change.

**Option E2**: `record_loop_run_summary()` derives `started_at` via `SELECT MIN(ts) FROM loop_events WHERE loop_name=? AND transition='loop_start'`. No event change. Extra DB hit per write.

**Option E3**: `_finish()` passes `started_at` as a direct arg from `self.started_at` (set at `executor.py:339`). Zero DB hit, zero event change. Couples to D2.

**Recommended**: Option E3 (paired with D2 — both are direct-arg-pass from `_finish()`).

**Decision F — Backfill strategy for historical runs (see Gap P)**

> **Selected:** Option F2 — per the stated recommendation. One-shot migration scanning `.loops/.history/*/state.json`; idempotent via UNIQUE on `run_id`. Filed as a follow-on issue (not part of ENH-2463 v1).

**Option F1**: No backfill — `loop_runs` covers only post-migration runs.

**Option F2**: One-shot migration that scans `.loops/.history/*/state.json`, parses `started_at` / `iterations` / `final_state` per file, and calls `record_loop_run_summary()` per file. Idempotent via UNIQUE on `run_id`.

**Option F3**: Periodic reconciler that runs on each `ll-session backfill` invocation. Lifecycle / scheduling overhead.

**Recommended**: Option F2 as a follow-on issue, not part of ENH-2463 v1.

**Decision G — Reconciler for handoff / force-archive / hard-kill gaps (see Gaps Q + R)**

> **Selected:** Option G1 — per the stated recommendation. Document v1 coverage gap in Expected Behavior; G2 + G3 filed as follow-on issues.

**Option G1**: Accept the gap; document in Expected Behavior.

**Option G2**: Extend `PersistentExecutor.archive_run_only()` and `_handle_handoff()` to call `record_loop_run_summary()` directly. Closes most gaps. Requires the writer import in those paths.

**Option G3**: Periodic background scanner that reads `.loops/.history/*/state.json` and backfills missing rows. Covers all gaps. Scheduling overhead.

**Recommended**: G1 as the v1 known gap (documented in Expected Behavior addendum); G2 + G3 as follow-on issues.

**Pattern disambiguation — `record_commit_event` is the right model for `record_loop_run_summary`**

Among the two additive-writer precedents, `record_commit_event` (`session_store.py:1222-1272`) is the right model:

- Returns `bool` (`cursor.rowcount`-driven)
- Uses `INSERT OR IGNORE` on UNIQUE constraint
- Gates `_index()` on `cursor.rowcount` (avoids double-indexing)
- Has the `config: dict | None = None` forward-compat stub

`record_test_run_event` (`session_store.py:1352-1414`) is the wrong model:

- Returns `None` (no UNIQUE constraint)
- Plain INSERT (always indexes)
- No idempotency

Since `loop_runs.run_id` is UNIQUE, `record_commit_event` is the closer fit. **Note**: Gap M's mirror reference to `record_test_run_event` for the `_index(kind="loop_run", ref=run_id, anchor=loop_name)` row shape is still correct, but the surrounding INSERT pattern (UNIQUE-key idempotency, `cursor.rowcount` gating, `bool` return) should follow `record_commit_event`.

**Active `analytics.capture.*` gate pattern (for the future `loop_runs` config key)**

Currently `write_file_event` at `session_store.py:920-925` is the ONLY writer that actively honors the gate:

```python
if config is not None:
    from little_loops.config.features import AnalyticsCaptureConfig
    capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
    if not capture.file_events:
        return
```

`AnalyticsCaptureConfig` is at `config/features.py:528-558` with fields `skills`, `cli_commands`, `corrections`, `file_events`, `usage_events`, `correction_patterns`. For ENH-2463 v1, accept `config: dict | None = None` as a forward-compat stub (matching `record_commit_event`); adding `loop_runs: bool = True` to the dataclass + wiring the gate inside `record_loop_run_summary` is a clean follow-on (mirrors how `file_events` was added).

**Agent→DB ingestion precedent for `update_loop_run_diagnostics`**

The closest pattern for an external caller invoking a session-store writer is `record_head_commit()` in `scripts/little_loops/hooks/post_commit.py`. For the `loop-specialist` diagnostic-artifact step, the equivalent wiring is:

1. After writing `.loops/diagnostics/<loop-name>-<UTC-ts>.md`, invoke (via CLI or in-process call) `update_loop_run_diagnostics(run_id, artifact_path)`.
2. `run_id` is supplied to the agent as an input parameter (per Gap S — not derivable from the artifact filename).
3. Failure is best-effort (logged, not raised).

Per Decisions G/S, v1 should defer this wiring; it requires an upstream caller that knows the archive `run_id`.

**`ll-loop runs` subcommand registration mechanics**

The `known_subcommands` set at `cli/loop/__init__.py:54-86` must include `"runs"` so the implicit-`run` pre-parser (line 92) doesn't shadow it. Handler imports are at lines 25-41; dispatch is at lines 936-983. The `_list_archived_runs()` helper at `cli/loop/info.py:884-963` is the existing on-disk run-listing shape (currently reads `state.json` directly); `cmd_runs` for ENH-2463 sources its data from `recent_loop_runs()` instead — same rendering shape, different data source. Add `cmd_runs` to the `info.py` import group.

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

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot ("bump
`SCHEMA_VERSION = 18` → `19`"). At least ten other active EPIC-2457 siblings
(ENH-2464, ENH-2465, ENH-2492, ENH-2493, ENH-2494, ENH-2495, ENH-2496,
ENH-2497, ENH-2498, ENH-2511) independently make the same "18→19" claim in
their own Integration Maps — they cannot all be v19. Verified against current
code (`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **20**
(v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459 done,
v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done). At
implementation time, read the live `SCHEMA_VERSION` constant to determine the
actual next-available slot rather than trusting this issue's stale "19"
literal; each child lands its own migration at whatever version is open when
it is implemented (no coordinated release; per EPIC-2457's own "no shared
helper module is required" scope note).

## Wiring Pass Addendum (added by `/ll:wire-issue` on 2026-07-16)

This addendum captures every wiring touchpoint surfaced by the three parallel research agents (Caller Tracer, Side-Effect Tracer, Test Gap Finder) that is NOT already enumerated in the Integration Map and Implementation Steps above. Each item is verified against the live source as of 2026-07-16. Drift corrections are listed separately at the end. The session_log entry appended below records the source JSONL.

### Dependent Files (Callers / Importers)

_Wiring pass added by `/ll:wire-issue`:_

Direct importers and consumers of the changed code that are NOT already listed in the issue's `### Files to Modify`. These are adjacent touchpoints; not all require editing, but each one must be checked during implementation.

- `scripts/little_loops/cli/loop/__init__.py:25-41` — handler-imports group; add `cmd_runs` to the `from .info import ...` block alongside `cmd_history`, `cmd_list`, `cmd_show`.
- `scripts/little_loops/cli/loop/__init__.py:54-86` — `known_subcommands` set; MUST add `"runs"` so the implicit-`run` pre-parser at line 92 doesn't shadow it.
- `scripts/little_loops/cli/loop/__init__.py:100-118` — `epilog` example block; append a `ll-loop runs` example alongside existing `ll-loop history fix-types` reference.
- `scripts/little_loops/cli/loop/__init__.py:521-573` — `history_parser` argument block; add `--summary` flag here. Use `action="store_true"` boolean (NOT `--since`-style optional); in `cmd_history` use `getattr(args, "summary", False)` for defensive access matching existing flag-handling pattern at `cli/loop/info.py:966`.
- `scripts/little_loops/cli/session.py:1-23` — module docstring subcommand list at lines 8-10 (`tool, file, issue, loop, correction, message, skill, cli, snapshot, commit, test_run`); append `loop_run`. The docstring is hand-maintained; `VALID_KINDS` auto-derives argparse `choices=[...]` at lines 103 and 115, but does NOT auto-flow into the docstring.
- `scripts/little_loops/cli/loop/_helpers.py:145` — calls `archive_run_only` on forced interruption; Gap Q reconciler site (Decision G2 follow-on).
- `scripts/little_loops/cli/loop/_helpers.py:1458` — defines `_make_instance_id`; provides the invocation-time `run_id` source. (Note: line has drifted from the issue's claim of `:1239`; see Anchor Drift table.)
- `scripts/little_loops/cli/logs.py:1752-1783` — existing CLI-side interpretation of archived `loop_complete` events; will continue to work (reads `events.jsonl`, not `loop_runs`). No v1 change.
- `scripts/little_loops/fsm/executor.py:2457` — defines `_handle_handoff`; Gap R reconciler site (Decision G2 follow-on). The BaseException skip path (`executor.py:729-738` has `except Exception` but no `finally`) is documented as known v1 coverage gap.
- `scripts/little_loops/fsm/persistence.py:743` — treats `loop_complete` as archival event; no v1 change needed.
- `scripts/little_loops/session_store.py:1473-1474` — `kind` validation gate; adding `"loop_run"` to `VALID_KINDS` enables both write paths and the `_index()` FTS row.
- `scripts/little_loops/session_store.py:2824-2834` — `_REBUILD_TABLES` deliberately excludes `loop_events` and `loop_runs` (commented at lines 2818-2823). The new migration block should follow this same convention so a future `_REBUILD_TABLES` audit doesn't try to add `loop_runs` to it.
- `scripts/little_loops/session_store.py:2835` — `_REBUILD_SEARCH_KINDS` currently `("tool", "message", "skill", "correction", "usage")` only. v1 should NOT add `"loop_run"` here (the FTS row from `record_loop_run_summary` will not be touched by `rebuild()`, but operators who delete a `loop_runs` row manually accept stale-FTS responsibility — see Decision F2 follow-on).
- `scripts/little_loops/session_store.py:3309` — `export_history` table-name mapping. Must add `"loop_run": ("loop_runs", "ts")` for `ll-session export --tables loop_run` to work; otherwise the export silently skips the new table.
- `scripts/little_loops/cli/verify_kinds.py:30-47` — gate; `loop_runs` MUST be registered in `_KIND_TABLE` in lock-step with the migration's `CREATE TABLE`, or `ll-verify-kinds` exits 1.
- `scripts/little_loops/cli/verify_des_audit.py:97-164` — DES audit gate (only required if Decision A2). Walks `_emit(...)` call sites and fails on any emit whose type string is not in `DES_VARIANT_TYPES` (`scripts/little_loops/observability/schema.py:653`).
- `scripts/little_loops/observability/__init__.py:18-26` — DES registry exports; only matters if Decision A2.
- `scripts/little_loops/observability/schema.py:563-634` — `DES_VARIANTS` tuple; only A2 (would need a `LoopRunSummaryVariant`).
- `scripts/little_loops/observability/audit.py:53-189` — DES audit allow-list consumer; only A2.
- `scripts/little_loops/generate_schemas.py:391-402` — registers the generated `loop_complete` event schema; only A2.
- `scripts/little_loops/session_store.py:768-822` — `_split_sql_statements` migration splitter; the new migration block must follow the v17 multi-statement layout (`CREATE TABLE` + 3 named indexes) so the splitter handles it without modification.
- `scripts/little_loops/session_store.py:2962-2963` — `backfill()` dispatch; `_backfill_loops` writes synthetic `transition="backfill"` rows directly (no historical `loop_runs` materialization). Decision F2 follow-on will add a line here.
- `scripts/little_loops/hooks/session_start.py:150-171` — `--rebuild` flag logic compares `_last_rebuild_version < SCHEMA_VERSION`; after migration lands, an unrun `SessionStart` triggers a rebuild, but since `_REBUILD_TABLES` excludes `loop_runs`, the rebuild is a no-op for `loop_runs`. Document this for the Decision F2 follow-on.

### Files to Modify (additional entries not already in the Integration Map)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/cli/loop/__init__.py:25-41, 54-86, 100-118, 521-573` — sub-changes within the already-listed file (`cli/loop/__init__.py` at line 370). Add `cmd_runs` import, `"runs"` to `known_subcommands`, `epilog` example, `history_parser --summary` flag.
- `scripts/little_loops/cli/session.py:1-23` — module docstring subcommand list (hand-maintained; NOT auto-derived). Append `loop_run`.
- `scripts/little_loops/session_store.py:3309` — `export_history` table-name mapping. Add `"loop_run": ("loop_runs", "ts")`.
- `scripts/little_loops/session_store.py:2824-2834` — comment on new migration block matching the `_REBUILD_TABLES` deliberate-exclusion convention.
- `scripts/tests/test_session_store.py:90-106` — `test_all_tables_created` (verify the precise test name during impl). Add `"loop_runs"` to the table-name tuple.
- `scripts/tests/test_session_store.py:3410-3418` — `TestValidKindsCentralization` set-equality invariant. Adding `"loop_run"` to both `VALID_KINDS` and `_KIND_TABLE` keeps the test green; optionally add a new test pinning `"loop_run" in VALID_KINDS and _KIND_TABLE["loop_run"] == "loop_runs"`.
- `scripts/tests/test_session_store.py:4444-4456` — `_LOOP_EVENT_TYPES` membership test for `("loop_start", "loop_complete", "state_enter", "route")`. Decision A1 keeps `loop_complete` (no change); Decision A2 would require `"loop_run_summary"` in the set.

### Tests to Update / Add (additional entries not already in the Integration Map)

_Wiring pass added by `/ll:wire-issue`:_

Existing test files / classes that touch the affected code and should be checked during implementation (NOT covered by the issue's narrow test list):

- `scripts/tests/test_fsm_executor.py:1677-1697` — `test_loop_complete_event_details` asserts on `final_state`, `iterations`, `terminated_by` from `loop_complete` payload. Verify the producer-side `record_loop_run_summary()` call from `_finish()` doesn't change these shape assertions.
- `scripts/tests/test_fsm_executor.py:2310-2379` — `test_exception_during_execution_emits_error_in_loop_complete_event` and `test_normal_termination_omits_error_from_loop_complete_event`. Both go through `_finish()` and would hit the new writer call; ensure they pass.
- `scripts/tests/test_fsm_executor.py:2653-2686, 2775-2983, 8332-8481` — Multiple `loop_complete` assertions across `TestFSMExecutorBasic` and downstream test classes; spot-check during impl.
- `scripts/tests/test_fsm_persistence.py:867-887, 898, 931-949, 2107-2436` — `PersistentExecutor.archive_run_only()` lifecycle tests. Document Gap Q v1 known coverage gap in a new regression test that verifies an `archive_run_only()`-terminated run does NOT create a `loop_runs` row (the test pins the gap, doesn't fix it).
- `scripts/tests/test_session_store.py:347-388` — `TestSQLiteTransport.test_loop_complete_records_outcome_as_state` (line 372-377) is the only DIRECT test of the `loop_complete` transport branch at `session_store.py:1543`. Extend to cover the new `record_loop_run_summary()` fan-out (under Decision A1, this asserts `loop_runs` is NOT populated — the producer-side path owns it).
- `scripts/tests/test_session_store.py:4226-4283` — `TestRecordCommitEvent` is the precise model for `TestRecordLoopRun`: `test_roundtrip`, `test_dedupe_on_sha`, `test_fts_searchable_by_message_fragment`, `test_explicit_issue_id_not_overridden`.
- `scripts/tests/test_session_store.py:4347-4432` — `TestRecordTestRunEvent` is the secondary model for migration-shape.
- `scripts/tests/test_session_store.py:3758-3828` — `TestRecordIssueSnapshot` insert-then-update companion for idempotency.
- `scripts/tests/test_session_store.py:3957-4034` — `TestSkillEventContext` (NOT line 1164 of session_store.py as the Issue's Gap T quoted; the production skill_event_context is at `:1164-1180`) is the model for `update_loop_run_diagnostics`'s UPDATE pattern.
- `scripts/tests/test_session_store.py:3891-3911` — `_bootstrap_schema_at` helper; the new `TestSchemaV{N}LoopRuns` test must call `_bootstrap_schema_at(db, N-1)` (the prior version), per existing usages at lines 3924 and 3927.
- `scripts/tests/test_session_store.py:3914-3966` — `TestSchemaV15SkillCompletionColumns` is the exact template for `TestSchemaV{N}LoopRuns`.
- `scripts/tests/test_history_reader.py:1395-1546` — `TestNewEventReaders` template for `TestHistoryLoopRunsRead`; uses writer-then-reader integration tests.
- `scripts/tests/test_history_reader.py:1548` — `TestUsageEventReaders` (the most-recent reader test class to model after for `aggregate_loop_runs`).
- `scripts/tests/test_history_reader.py` — extend `test_readers_return_empty_on_missing_db` to cover `recent_loop_runs(db=missing)`, `aggregate_loop_runs(db=missing)`, `find_loop_run(run_id, db=missing)`.
- `scripts/tests/test_cli.py:2343-2364` — `test_history_command_with_tail` is the model for the new `--summary` flag test.
- `scripts/tests/test_verify_kinds.py:18-23` — `test_clean_state_returns_zero` is the hard gate; adding `CREATE TABLE loop_runs` without registering in `_KIND_TABLE` will break this test. Verify it passes after the migration lands.
- `scripts/tests/test_des_audit.py:52-68` — DES audit gate; only matters if Decision A2.
- `scripts/tests/test_verify_package_data.py` — affected if the docstring at `session_store.py:17-37` is not updated with the new function names.
- `scripts/tests/conftest.py:565-604` — `_guard_real_history_db` fixture intercepts `little_loops.session_store.sqlite3.connect` to prevent tests from touching the production `.ll/history.db`. Any new test that calls `record_loop_run_summary()` through `connect()` goes through this gate automatically — no extra wiring needed.

New test classes to add (NOT in the issue's test list):

- `TestRecordLoopRunEndToEnd` — in `test_fsm_executor.py`. Patch `record_loop_run_summary` to a mock, run a real `FSMExecutor`, assert the mock was called with `run_id` derived from `started_at`, `loop_name` from `fsm.name`, `final_state`, `iterations`, `terminated_by`. Covers Gap T-6 (Decision D2 + E3 acceptance).
- `TestLoopRunsRunsSubcommand` — in `test_cli.py` (or new `test_cli_loop_runs.py`). Mirror `test_history_command_with_tail` at `test_cli.py:2343-2364`. Covers `ll-loop runs --since` (Gap T-4).
- `TestHistorySummaryFlag` — in `test_cli.py`. Covers `ll-loop history --summary` (Gap T-5). Asserts `getattr(args, "summary", False)` is consumed correctly.
- `TestLoopRunsSchemaV{N}RegistrationLocks` — in `test_session_store.py`. Pins that `_KIND_TABLE["loop_run"] == "loop_runs"` AND `"loop_run" in VALID_KINDS`. Catches unilateral updates that would silently fail `test_verify_kinds.py:18-23`.
- `TestArchiveRunOnlyDoesNotPopulateLoopRuns` (Gap Q coverage) — in `test_fsm_persistence.py`. Pins the v1 known coverage gap as a regression test; documents that the follow-on (Decision G2) is the fix.
- `TestResumedRunHasSingleLoopRunsRow` (Gap H coverage) — in `test_fsm_persistence.py` or new file. Verifies the resume path produces a single `loop_runs` row, not multiple, leveraging the `INSERT OR IGNORE` UNIQUE-key idempotency.

### Documentation (additional entries not already in the Integration Map)

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/EVENT-SCHEMA.md:600-659` — `loop_complete` event schema and termination semantics; will continue to be valid (no event-shape change under Decision A1). Confirm A1 leaves this section accurate.
- `docs/reference/EVENT-SCHEMA.md:1020-1033` — SQLite transport loop event handling.
- `docs/reference/EVENT-SCHEMA.md:1096` — generated event-schema file listing (includes `loop_complete.json`); `ll-generate-schemas` will emit a new `loop_run.json` (note: `loop_run`, not `loop_runs`, matching the DES kind).
- `docs/reference/EVENT-SCHEMA.md:1201, 1245` — event-to-source mapping for `loop_complete`.
- `docs/reference/COMMANDS.md:771-781` — loop outcome + `loop_complete` diagnostics section; will need an addendum when the new `ll-loop runs` subcommand lands.
- `docs/guides/LOOPS_REFERENCE.md:3302` — loop-run command reference.
- `docs/guides/HISTORY_SESSION_GUIDE.md:51, 91-106, 510-514` — history schema section, version references, and analytics capture settings. Line 51 currently says `Current schema version: 18` (already stale; live is 20) — bump during implementation.
- `docs/reference/CONFIGURATION.md:509-520` — analytics capture configuration table; if the `analytics.capture.loop_runs` gate is added in v1, the doc table needs a new row.
- `docs/reference/HOST_COMPATIBILITY.md:312` — analytics capture reporting in `ll-doctor`; if the new capture key is added, this is the surface where it shows up.
- `docs/generalized-fsm-loop.md:1676` — example `loop_complete` event reference; A1 leaves this intact.
- `docs/observability/des-audit.md:27` — DES documentation table; only matters if Decision A2 (the table would gain a new row).
- `docs/reference/API.md:7275, 7279` — `Current schema version: **19**` and `# 19` (both stale; live is 20). Bump during implementation. (Already flagged in Agent 1's documentation research.)
- `docs/ARCHITECTURE.md:723, 748, 811` — three `v1–v20` callouts (NOT four as the issue claims at Implementation Step 11 line 632). The issue's `:632` claim is wrong; line 632 is the end of an FSMExecutor events row in the emitters table, not a version-range callout. Verified callouts at lines 723 (`mermaid` ensure_db callout), 748 (CLI transport-wiring table), 811 (see-also callout), all currently `v1–v20`. They need `v1–v{N+1}` after the migration lands. (`v1–v18` is from Issue's stale anchor claims.)
- `docs/reference/CLI.md:2427, 2435, 2509-2511` — `--kind` help text at lines 2427 and 2435 is hand-maintained (does NOT auto-track `VALID_KINDS` like `cli/session.py:103,115` does). Both lines need `loop_run` appended. Example block at lines 2509-2511 should gain a `ll-session recent --kind loop_run` example.

### Configuration (additional entries not already in the Integration Map)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/config-schema.json:1608-1680` — `analytics.capture` block has `additionalProperties: false` at line 1655. Adding `loop_runs: bool = True` to `AnalyticsCaptureConfig` requires a matching JSON-schema `loop_runs` boolean entry here. Only required if v1 activates the gate (the Issue's Gap L decision explicitly defers the gate to a follow-on; in that case no JSON-schema change is needed for v1).
- `scripts/little_loops/config/features.py:528-558` — `AnalyticsCaptureConfig` (already partially covered by Gap L). If v1 activates the gate, add `loop_runs: bool = True` with the `file_events` precedent at line 540.
- `scripts/little_loops/.ll/ll-config.json:78-86` — project's `analytics.capture` block currently declares `skills`, `cli_commands`, `corrections`, `file_events` only. For v1 forward-compat stub only, no change needed. If the gate is activated, add `"loop_runs": true` for discoverability.
- `scripts/little_loops/cli/verify_kinds.py:30-47` — gate. Already covered above in Dependent Files; included here for cross-reference because the lock-step registration is the constraint that drives every entry listed.

### Schema-side-effect additional entries

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/session_store.py:3309` — `export_history` table-name mapping. Add `"loop_run": ("loop_runs", "ts")` for `ll-session export --tables loop_run` to surface the new table; otherwise the export silently skips it.
- `scripts/little_loops/session_store.py:2824-2834` — `_REBUILD_TABLES` (deliberate-exclusion convention). The new v{N} migration block's leading comment should match this convention so a future audit doesn't attempt to materialise `loop_runs` from `raw_events`.
- `scripts/little_loops/session_store.py:2835` — `_REBUILD_SEARCH_KINDS`. v1 should NOT add `"loop_run"` here (see Dependent Files note); the FTS row written by `_index(kind="loop_run", ...)` will outlast a `rebuild()` until Decision F2 lands.

### Implementation Steps Wiring Phase (additional substeps)

_Wiring pass added by `/ll:wire-issue`:_

These touchpoints must be included in the implementation; they are NOT in the existing 12 Implementation Steps.

13. **`scripts/little_loops/cli/loop/__init__.py:521-573`** — Add `--summary` flag (boolean `action="store_true"`) to the `history_parser` argument block. In `cmd_history` at `cli/loop/info.py:966`, consume via `getattr(args, "summary", False)` (defensive access pattern matching the surrounding flags).
14. **`scripts/little_loops/cli/loop/__init__.py:25-41, 54-86, 100-118`** — Add `cmd_runs` to the handler-imports group; add `"runs"` to `known_subcommands` so line 92's implicit-`run` pre-parser doesn't shadow it; append `ll-loop runs` example to the `epilog` block at lines 100-118.
15. **`scripts/little_loops/cli/loop/info.py`** — Add `cmd_runs()` mirroring `cmd_history`'s `getattr(args, ...)` flag-handling pattern. Source data from `recent_loop_runs(since=...)`; on-disk fallback can mirror `_list_archived_runs()` at lines 884-963 if a v2 wants offline listing.
16. **`scripts/little_loops/cli/session.py:1-23`** — Append `loop_run` to the module docstring subcommand list at lines 8-10. NOTE: this list is hand-maintained; it does NOT auto-derive from `VALID_KINDS` the way argparse `choices=[...]` at lines 103 and 115 does.
17. **`scripts/little_loops/session_store.py:3309`** — Add `"loop_run": ("loop_runs", "ts")` to the `export_history` table-name mapping.
18. **`scripts/little_loops/session_store.py:2824-2834`** — Add a leading comment to the new migration block matching the `_REBUILD_TABLES` deliberate-exclusion convention (`loop_runs` is live-write-only; not materialised from `raw_events`).
19. **`scripts/tests/test_session_store.py:90-106`** — Add `"loop_runs"` to `_all_tables_created`'s table-name tuple.
20. **`scripts/tests/test_session_store.py:4444-4456`** — Verify the `_LOOP_EVENT_TYPES` membership test still passes (no code change under Decision A1). Add an explicit negative-case test ensuring `"loop_run_summary" not in _LOOP_EVENT_TYPES` so a future A2 pivot can't silently break the test.
21. **`scripts/tests/test_verify_kinds.py:18-23`** — Run `test_clean_state_returns_zero` after the migration lands; it must remain exit-0. If it fails, the `_KIND_TABLE` registration was missed.
22. **End-to-end wire-up test (Gap T-6)** — Add `TestRecordLoopRunEndToEnd` in `test_fsm_executor.py` that patches `record_loop_run_summary` to a mock, runs a real `FSMExecutor` through to `_finish()`, and asserts the mock was called with the archive-time `run_id` (derived from `self.started_at[:17]` + `self.fsm.name`), `loop_name=self.fsm.name`, `final_state`, `iterations`, `terminated_by`.
23. **CLI tests (Gaps T-4, T-5)** — Add `TestLoopRunsRunsSubcommand` and `TestHistorySummaryFlag` in `test_cli.py` (or new `test_cli_loop_runs.py`). Mirror `test_history_command_with_tail` at `test_cli.py:2343-2364`.
24. **Stale doc version refs** — Bump `docs/reference/API.md:7275, 7279` and `docs/guides/HISTORY_SESSION_GUIDE.md:51` to the current `SCHEMA_VERSION`. Bump `docs/ARCHITECTURE.md:723, 748, 811` (3 callouts, NOT 4) from `v1–v20` to `v1–v{N+1}`.
25. **`docs/reference/CLI.md:2427, 2435, 2509-2511`** — Append `loop_run` to the `--kind` help text at lines 2427 and 2435; add a `ll-session recent --kind loop_run` example to lines 2509-2511.
26. **`docs/reference/EVENT-SCHEMA.md:1096`** — Confirm `ll-generate-schemas` emits `loop_run.json` (not `loop_runs.json`) and the listing picks it up.
27. **Decision G2/G3 follow-on hooks** — Document (in the issue, not in code) the two reconciler sites that remain for v1: `cli/loop/_helpers.py:145` (forced-interrupt `archive_run_only`) and `fsm/executor.py:2457` (`_handle_handoff`). A new `loop_runs` row is missed for ~5-10% of runs until these are wired. Verification: file the follow-on issues; do not block v1.
28. **Decision F2 follow-on hooks** — Document that `_backfill_loops` at `session_store.py:2962-2963` and the migration in step 1 don't auto-populate `loop_runs` for pre-migration runs. A one-shot scan of `.loops/.history/*/state.json` is the chosen follow-on path. Verification: file the follow-on issue.

### Anchor Drift Corrections

_Wiring pass added by `/ll:wire-issue`:_

The Integration Map and Implementation Steps cite line numbers that have drifted since refine-issue was last run. Verified current positions:

| Symbol | Issue's cited line(s) | Verified current | Source |
|--------|-----------------------|------------------|--------|
| `SCHEMA_VERSION` constant | `:102`, claimed `18` or `19` | `session_store.py:207`, value `20` | Agent 2 + Scope Boundary note |
| `_MIGRATIONS` list | `:208-545` | `session_store.py:333` | Agent 2 |
| `VALID_KINDS` tuple | `:104` (as `_VALID_KINDS`) | `session_store.py:209` (public, in `__all__`) | Agent 2 |
| `_KIND_TABLE` | `:119` | `session_store.py:223` | Agent 2 |
| `_LOOP_EVENT_TYPES` | `:133` | `session_store.py:258` (`"loop_complete"` at `:262`) | Agent 2 |
| `record_commit_event` | `:1041`, `:1041-1091` | `session_store.py:1222-1272` | Agent 2 |
| `record_test_run_event` | (not cited) | `session_store.py:1352-1414` | Agent 2 |
| `record_skill_event` (initial insert area) | `:991` | `session_store.py:973+` (initial insert) | Agent 2 (Gap T refutation) |
| `skill_event_context` (completion UPDATE) | `:1164-1180` | `session_store.py:1164-1180` ✓ | Agent 3 |
| `_split_sql_statements` | (not cited by name) | `session_store.py:768`, used at `:822` | Agent 1 |
| `kind` validation gate | (not cited) | `session_store.py:1473-1474` | Agent 1 |
| `SQLiteTransport.send` `loop_complete` branch | `:1353`, `:1341-1376` | `session_store.py:1543` (with `outcome` key read at `:1543-1544`) | Agent 2 |
| `summarize_skills` | `:472` and `:472-598` | `history_reader.py:497-546` | Agent 2 |
| `recent_commit_events` | `:524` | `history_reader.py:651-686` | Agent 2 |
| `record_commit_event` author shape | `1222-1272` | `session_store.py:1222-1272` ✓ | Agent 3 |
| `_index` helper | `:705-718` | `session_store.py:890-903` | Agent 3 (DRIFT) |
| `_bootstrap_schema_at` test helper | `:3075-3095` | `test_session_store.py:3891-3911` | Agent 3 (DRIFT) |
| `_make_instance_id` | `cli/loop/_helpers.py:1239` | `cli/loop/_helpers.py:1458` | Agent 3 (DRIFT) |
| `archive_run()` | `fsm/persistence.py:494` | `fsm/persistence.py:487-537` (line `518` is the actual `run_id` derivation) | Agent 2 |
| `archive_run_only()` | `fsm/persistence.py:839-895` | `fsm/persistence.py:839-895` ✓ | Agents 1-3 |
| `FSMExecutor._finish()` | `fsm/executor.py:2269-2309` | `fsm/executor.py:2415` | Agent 2 |
| `_emit("loop_complete", payload)` | `fsm/executor.py:2278` | `fsm/executor.py:2424` | Agent 2 |
| `loop_start` (explicit `loop_name` injection) | (Gap K implied `:389-393`) | `fsm/executor.py:389-393` ✓ | Gap N |
| `_emit` (only adds `event` + `ts`) | (Gap K implied) | `fsm/executor.py:2124-2132` | Gap N refutation |
| `_handle_handoff()` | (not cited by line) | `fsm/executor.py:2457` | Agent 1 |
| `loop_complete` archival treatment | (not cited) | `fsm/persistence.py:743` | Agent 1 |
| `known_subcommands` set | `:54-86` | `cli/loop/__init__.py:54-86` ✓ | Agent 3 |
| `cli/session.py --kind` choices | `:88-141` | `cli/session.py:103, 115` (auto-derived via `list(VALID_KINDS)`) | Gap note |
| `cli/session.py` module docstring | (not cited) | `cli/session.py:1-23` (hand-maintained) | Agent 2 (line 8-10 specifically) |
| `_list_archived_runs()` | `:884-963` | `cli/loop/info.py:884-963` ✓ | Agent 1 |
| `cmd_history` flag pattern | (not cited) | `cli/loop/info.py:966` | Agent 2 |
| `history_parser` arg block | (not cited) | `cli/loop/__init__.py:521-573` | Agent 2 |
| `epilog` block | (not cited) | `cli/loop/__init__.py:100-118` | Agent 2 |
| `AnalyticsCaptureConfig` | `config/features.py:528-558` | matches | Agents 1-3 |
| `analytics.capture` block | `config-schema.json` not cited | `config-schema.json:1608-1680` (line 1655 `additionalProperties: false`) | Agent 2 |
| `ll-verify-kinds` gate | not cited by path | `cli/verify_kinds.py:30-47` | Agents 2 + 3 |
| `ll-verify-des-audit` (A2 only) | not cited by file | `cli/verify_des_audit.py:97-164`; observability at `schema.py:653` | Agent 2 |
| DES `LoopCompleteVariant` registration | not cited by file | `observability/schema.py:113-119` (`:115-117` per Agent 1) | Agent 1 |
| DES `DES_VARIANTS` | not cited by line | `observability/schema.py:563-634` | Agent 2 |
| DES audit allow-list | not cited by file | `observability/audit.py:53-189` (Agent 1 says `:27, 161-189`) | Agents 1 + 2 |
| `ll-generate-schemas` registration | not cited | `generate_schemas.py:391-402` | Agent 1 (A2 only) |
| `_backfill_loops` (no `loop_runs` materialisation) | not cited | `session_store.py:1776-1807` and dispatch at `:2962-2963` | Agent 2 |
| `rebuild()` excludes `loop_events` | not cited | `session_store.py:2818-2823` (comment); `_REBUILD_TABLES` at `:2824-2834` | Agent 2 |
| `_REBUILD_SEARCH_KINDS` (FTS rebuild filter) | not cited | `session_store.py:2835` | Agent 2 |
| `export_history` table-name mapping | not cited | `session_store.py:3309` | Agent 2 |
| `SessionStart --rebuild` trigger | not cited | `hooks/session_start.py:150-171` | Agent 2 |
| `loop_complete` archival scan in CLI logs | not cited | `cli/logs.py:1752-1783` (archived `events.jsonl`) | Agent 1 |
| `_guard_real_history_db` (conftest fixture) | not cited | `tests/conftest.py:565-604` | Agent 3 |
| `tests/test_session_store.py:_all_tables_created` | not cited | `test_session_store.py:90-106` | Agent 2 |
| `tests/test_session_store.py:TestValidKindsCentralization` | not cited | `test_session_store.py:3410-3418` (lines 3412, 3417) | Agent 2 |
| `tests/test_session_store.py:TestSQLiteTransport` | not cited | `test_session_store.py:347-388` (`:372-377` direct test of loop_complete branch) | Agent 3 |
| `tests/test_session_store.py:_LOOP_EVENT_TYPES` test | not cited | `test_session_store.py:4444-4456` (line 4454 membership check) | Agent 2 |
| `tests/test_verify_kinds.py:test_clean_state_returns_zero` | not cited | `test_verify_kinds.py:18-23` (and `:41` per Agent 3) | Agent 2 |
| `tests/test_des_audit.py` (A2 only) | not cited | `test_des_audit.py:52-68` | Agent 3 |
| `tests/test_verify_package_data.py` | not cited | exists; affected by docstring | Agent 3 |
| `tests/test_fsm_executor.py` `loop_complete` tests | not cited | `test_fsm_executor.py:1677-1697, 2310-2379, 2653-2686, 2775-2983, 8332-8481` | Agent 3 |
| `tests/test_fsm_persistence.py` `archive_run_only` tests | not cited | `test_fsm_persistence.py:867-887, 898, 931-949, 2107-2436` | Agent 3 |
| `tests/test_history_reader.py:TestNewEventReaders` template | not cited | `test_history_reader.py:1395-1546` | Agent 3 |
| `tests/test_history_reader.py:TestUsageEventReaders` template | not cited | `test_history_reader.py:1548` | Agent 3 |
| `tests/test_cli.py:2343-2364` (`test_history_command_with_tail` model) | not cited | `test_cli.py:2343-2364` | Agent 3 |
| `docs/observability/des-audit.md:27` (A2) | not cited | exists | Agent 1 |
| `docs/reference/EVENT-SCHEMA.md` references | not cited by line | `:600-659, 1020-1033, 1096, 1201, 1245` | Agent 1 + Agent 2 |
| `docs/reference/COMMANDS.md:771-781` | not cited | exists | Agent 1 |
| `docs/guides/LOOPS_REFERENCE.md:3302` | not cited | exists | Agent 1 |
| `docs/guides/HISTORY_SESSION_GUIDE.md:51, 91-106, 510-514` | not cited | exists; line 51 has stale version ref | Agents 1 + 2 |
| `docs/reference/CONFIGURATION.md:509-520` | not cited | exists | Agent 1 |
| `docs/reference/HOST_COMPATIBILITY.md:312` | not cited | exists | Agent 1 |
| `docs/generalized-fsm-loop.md:1676` | not cited | exists | Agent 1 |
| `docs/reference/API.md:7275, 7279` (stale version refs) | not cited | exists; both stale `19` | Agents 1 + 2 |
| `docs/ARCHITECTURE.md` version-range callouts | `:632, :678, :703, :749` (4 callouts claimed) | Verified `3 callouts at `:723, :748, :811` (line `:632` is NOT a callout — it's the end of an FSMExecutor events row) | Agent 2 |
| `docs/reference/CLI.md:2427, 2435, 2509-2511` | not cited | exist; help text is hand-maintained and out-of-date | Agent 2 |

Use the verified-current column when implementing. The drift is mostly +100 lines per major session-store expansion (v17→v18→v20 migrations each added ~30 lines).

---

The session-log entry appended below records the source JSONL for this wiring pass.

## Session Log
- `/ll:wire-issue` - 2026-07-16T20:45:15 - `f2e34338-c6b9-4184-87ae-f3c7166e82ab.jsonl`

- `/ll:decide-issue` - 2026-07-16T18:28:35 - `ed09a07d-067d-44ac-b1ad-ad826ab00704.jsonl`
- `/ll:refine-issue` - 2026-07-16T14:29:26 - `6a56187c-bd1e-41fd-bb6f-3e87d47a557a.jsonl`
- `/ll:refine-issue` - 2026-07-16T14:09:47 - `62d957fd-b2f2-451b-85fc-3f142b5e5e6b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-14T00:22:36 - `bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
- `/ll:refine-issue` - 2026-07-07T07:05:11 - `af395362-9221-4c5e-9038-fca90275d34a.jsonl`
- `/ll:refine-issue` - 2026-07-07T00:06:36 - `6c59385b-d02b-4ef9-8cb4-4a48daafa67d.jsonl`
- audit - 2026-07-06 - Fixed loop-specialist agent path in Sources (`agents/loop-specialist.md`, not `scripts/little_loops/agents/`). Note for implementer: schema is at v18 as of 2026-07-06, so the new migration lands as v19+; `_finish()` is at `fsm/executor.py:2269`.
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
