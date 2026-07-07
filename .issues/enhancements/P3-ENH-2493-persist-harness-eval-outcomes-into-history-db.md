---
id: ENH-2493
title: Persist ll-harness / eval outcomes into history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-05
captured_at: "2026-07-05T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - eval
  - captured
---

# ENH-2493: Persist ll-harness / eval outcomes into history.db

## Summary

`ll-harness` computes a real `PASS`/`FAIL` plus a semantic `verdict` per run
(`cli/harness.py:main_harness()` at `:450`; pass/fail logic in
`_evaluate_and_report()` at `:192`, `eval_result.verdict`), but only the process **exit code** is persisted — via the
generic `cli_event_context` wrap. The runner type (skill/cmd/mcp/prompt/dsl), the
target, whether the semantic criterion passed, and whether it timed out are all
discarded. So the DB can't answer "has this eval flapped between PASS and FAIL
over the last ten runs?" without re-running. Add a `harness_events` table (or
extend with a structured record call alongside the existing `cli_event_context`)
capturing the structured result so eval-score trends are queryable. This mirrors
what ENH-2459 did for pytest — turn an exit code into a structured, trend-able
signal.

## Motivation

- **Evals exist to be tracked over time, and currently aren't.** A harness that
  guards a feature is only useful as a trend; a single exit code with no history
  can't show regression or flake.
- **Runner/target discrimination is lost.** `cli_events` records
  `args="run skill format-issue …"` as an opaque string; there's no queryable
  `runner`/`target`/`semantic_passed` to group or filter on.
- **DSL eval tasks (`create-eval-from-issues --dsl`) have the same gap** — each
  `DslTask` produces a `RunnerResult` (`exit_code`, `timed_out`) that's evaluated
  and discarded.

## Current Behavior

- `main_harness()` wraps the run in `cli_event_context(DEFAULT_DB_PATH,
  "ll-harness", sys.argv[1:])` (`harness.py:452`); the `cli_events` row carries
  only `(binary, args, exit_code, duration_ms)`.
- `_evaluate_and_report()` (`harness.py:192`) computes `passed`, prints
  `PASS`/`FAIL`, and returns an exit code; `eval_result.verdict` is not persisted.
- No `--kind harness` in `ll-session`.

## Expected Behavior

- A `harness_events` table records one row per harness/eval run with
  `runner`, `target`, `exit_code`, `semantic_verdict`, `semantic_passed`,
  `timed_out`, `duration_ms`.
- `main_harness()` calls `record_harness_event(...)` before returning (inside the
  existing `cli_event_context`; best-effort guarded).
- `ll-session recent --kind harness` returns rows;
  `ll-session search --fts "<target>" --kind harness` matches.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS harness_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    runner TEXT,                 -- "skill" | "cmd" | "mcp" | "prompt" | "dsl"
    target TEXT,                 -- skill/cmd name, mcp tool, or task id
    exit_code INTEGER,
    semantic_verdict TEXT,       -- raw evaluator verdict, e.g. "yes"/"no"/score
    semantic_passed INTEGER,     -- 0/1 overall pass
    timed_out INTEGER,           -- 0/1
    duration_ms INTEGER,
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_harness_runner ON harness_events(runner);
CREATE INDEX IF NOT EXISTS idx_harness_target ON harness_events(target);
CREATE INDEX IF NOT EXISTS idx_harness_passed ON harness_events(semantic_passed);
```

Bump `SCHEMA_VERSION`. Add `"harness"` to `_VALID_KINDS` and
`"harness": "harness_events"` to `_KIND_TABLE`.

### Producer wiring

- Add `record_harness_event(db_path, *, ts, runner, target, exit_code,
  semantic_verdict=None, semantic_passed=None, timed_out=None,
  duration_ms=None, head_sha=None, branch=None)` to `session_store.py`,
  best-effort guarded, indexing `target` into `search_index` (`kind="harness"`).
- Call it from `main_harness()` after `_evaluate_and_report()` returns, reading `runner`
  from the parsed args, `semantic_passed`/`semantic_verdict` from `eval_result`,
  and `timed_out` from `RunnerResult`.
- For `--dsl` batch runs, emit one row per `DslTask`.

### Read API

- `history_reader.recent_harness_events(runner=None, target=None, since=None,
  limit=50)`.
- `history_reader.harness_pass_rate(target, since=None)` — flake/regression rollup.

### CLI surface

- `ll-session recent --kind harness`.

## Acceptance Criteria

- Schema migration lands; `harness_events` exists; `SCHEMA_VERSION` bumped.
- A `ll-harness run skill format-issue …` invocation writes one row with the
  correct `runner="skill"`, `target="format-issue"`, `semantic_passed`, and
  `exit_code`.
- A timing-out run records `timed_out=1`.
- A `--dsl` batch writes one row per task.
- Writes are best-effort: DB absent/locked does not change the harness exit code.
- `ll-session recent --kind harness` returns rows; FTS matches `target`.
- Tests cover: PASS run, FAIL run, timeout, DSL multi-row, graceful degradation.

### Codebase Research Findings — Proposed Solution anchors

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Where to wire the producer**: `cli/harness.py:450` `main_harness()` currently wraps the dispatch in `cli_event_context(...)` at `:452` (which UPDATEs `cli_events` with only `(exit_code, duration_ms)` — see `session_store.py:870-908` `cli_event_context`). Insert the structured `record_harness_event(...)` call alongside the existing wrap (inside the `with` block, just before each branch's return), not inside `cli_event_context` itself — that keeps the legacy `cli_events` row intact for backward compat.
- **Where `passed`/`verdict` are computed (today, only in process)**: `cli/harness.py:192-252` `_evaluate_and_report()` — `passed` flips at `:211` (exit-code mismatch) and `:218` (semantic verdict != "yes"); `eval_result.verdict` lives at `:216`. Each caller (`cmd_skill:300`, `cmd_cmd:334/346`, `cmd_mcp:377`, `cmd_prompt:399`) returns only the int exit code. Either (a) thread `passed`/`verdict` out via a tuple return or a small dataclass, or (b) attach attributes to a mutable holder (`args.__dict__["_semantic_verdict"] = eval_result.verdict`) before the `_evaluate_and_report` call returns.
- **`runner_label` construction sites** (per-branch): `cli/harness.py:284` (skill), `:305` (cmd), `:367` (mcp), `:383` (prompt), `:382-383` (truncated to 40 chars for prompt). For `dsl` (`cmd_dsl` at `:402-447`), `runner_label` is never built — only the integer `pass_count/total` aggregates N sub-runs. Emit one row per sub-run inside `cmd_dsl`'s loop at `:440` (`cmd_prompt(task_args)`), with `target` = the DslTask identifier and `runner` = `"dsl"`.
- **Best-effort pattern**: `session_store.py:1171-1233` `record_test_run_event()` itself raises; the swallow lives in the caller (`pytest_history_plugin.py:120-121` wraps in `contextlib.suppress(Exception)`). Mirror in the harness CLI by calling `record_harness_event(...)` inside `try: ... except Exception: pass` — or, simpler, wrap `_emit_harness_event(...)` once and `suppress(Exception)` the call site. This is what makes "DB absent/locked does not change the harness exit code" (AC) true.
- **FTS indexing**: `session_store.py:1218-1230` — `_index(db_path, kind="test_run", ref=head_sha or "", anchor=branch or "", ts=ts, content=summary_512_chars)`. Mirror for harness: `kind="harness"`, `ref=target`, `anchor=runner`, `content=` short summary like `f"runner={runner} target={target} verdict={semantic_verdict or 'n/a'} passed={bool(semantic_passed)}"` (clip to 512 chars). This makes `ll-session search --fts "<target>" --kind harness` work.
- **`git_utils` lookup**: use `scripts/little_loops/git_utils.py:get_head_sha()` / `get_current_branch()` (the same helpers that `record_commit_event` at `session_store.py:1067-1072` and `hooks/post_commit.py:record_head_commit` use). Wrap in `try/except` so a non-git working tree doesn't break the write (return `None` for both).

### Codebase Research Findings — Implementation Steps (concrete anchors)

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Schema migration** — append to `_MIGRATIONS: list[str]` at `session_store.py:521-544`. Use the exact shape `# v19 (ENH-2493): harness_events — persisted ll-harness / eval outcomes ...` followed by triple-quoted SQL with `CREATE TABLE IF NOT EXISTS harness_events (...)` + 3 `CREATE INDEX IF NOT EXISTS idx_harness_*` lines. Bump `SCHEMA_VERSION = 19` at line 102. `_apply_migrations` (line 609) iterates `version → len(_MIGRATIONS)` — appending is sufficient, no helper.
2. **Registers** — edit `_VALID_KINDS` (line 104) and `_KIND_TABLE` (line 119) in `session_store.py`. Update both `--kind` `choices` lists in `cli/session.py:91-106` (search) and `:113-129` (recent). Also update the module-level docstring at `cli/session.py:8-10`.
3. **`record_harness_event(...)`** — add to `session_store.py` after `record_test_run_event()` (line 1233). Kwarg-only signature matching the issue shape exactly, with `try/finally` over `connect(db_path)` → `INSERT INTO harness_events (...)` → `_index(db_path, kind="harness", ref=target or "", anchor=runner or "", ts=ts, content=summary_512)` → `conn.commit()`. Export in `__all__` (line 60).
4. **Wire in `cli/harness.py`** — at each branch return site (`cmd_skill:300`, `cmd_cmd:334/346`, `cmd_mcp:377`, `cmd_prompt:399`) and inside the `cmd_dsl` loop (`:440`), build kwargs from the parsed `args` + `result: RunnerResult` + the local `runner_label` / `passed` / `eval_result.verdict` and call `record_harness_event(DEFAULT_DB_PATH, ...)`. For DSL, emit inside the loop (per-task), not just once in the aggregate. Capture `head_sha` / `branch` via `git_utils.get_head_sha()` / `get_current_branch()` before the call.
5. **Read API** — add `HarnessEvent` dataclass to `history_reader.py` near line 161 (mirror `RunEvent` at `:138-162`). Add `recent_harness_events(runner=None, target=None, since=None, limit=50, db=DEFAULT_DB_PATH)` near line 598 (mirror `recent_test_runs()` at `:562-598`). Add `harness_pass_rate(target, since=None, db=DEFAULT_DB_PATH)` modeled on `summarize_skills()` at `:472-521` (uses `SUM(CASE WHEN semantic_passed = 1 THEN 1 ELSE 0 END) / COUNT(semantic_passed)` to ignore NULL rows).
6. **CLI** — `ll-session recent --kind harness` works automatically once `_KIND_TABLE` is updated (dispatched via `session_store.recent()` at line 1241). No new subparser needed unless `harness_pass_rate` becomes a separate command (then mirror `cli/session.py:253-263` `skill-stats` parser + `:503-522` handler).
7. **Tests** — add `TestRecordHarnessEvent` to `scripts/tests/test_session_store.py` near line 3619 (mirror `TestRecordTestRunEvent`). Include `test_v18_db_upgrades_gains_harness_events` using `_bootstrap_schema_at(db, 18)`. Add CLI test `test_recent_kind_harness_outputs_row` + `test_search_kind_harness_filters` to `scripts/tests/test_ll_session.py`. Add reader tests to `scripts/tests/test_history_reader.py` mirroring `test_recent_test_runs_and_pass_rate` (`:1442-1460`) and the empty-DB graceful-degradation test (`:1505-1522`). Add `TestHarnessEventPersistence` to `scripts/tests/test_cli_harness.py` covering PASS/FAIL/timeout/DSL/graceful-degradation.
8. **Docs** — add v19 row to `docs/ARCHITECTURE.md` schema-versions table at `:612-635`. Add `recent_harness_events` / `harness_pass_rate` blocks to `docs/reference/API.md:6723-6767` and `record_harness_event` block to `:6980-7048`. Update `--kind` flag tables in `docs/reference/CLI.md:2245, 2253` and add example at `:2280-2282`.
9. **Run the gate** — `python -m pytest scripts/tests/test_session_store.py scripts/tests/test_history_reader.py scripts/tests/test_ll_session.py scripts/tests/test_cli_harness.py -v` (per the project's CI policy: `python -m pytest scripts/tests/` *is* CI). Verify `harness_events` appears in `sqlite_master` after `ensure_db(db)` in the upgrade test.

## Implementation Steps

1. Schema migration for `harness_events`; bump `SCHEMA_VERSION`.
2. Add `"harness"` to `_VALID_KINDS` and `_KIND_TABLE`.
3. Implement `record_harness_event()` in `session_store.py`; export.
4. Wire `main_harness()` (post-`_evaluate_and_report`) + the `--dsl` per-task path.
5. `history_reader.recent_harness_events()` + `harness_pass_rate()`.
6. CLI: `ll-session recent --kind harness`.
7. Tests: `TestRecordHarnessEvent`, `TestHarnessSchema`,
   `TestHarnessWiring`, graceful-degradation test.
8. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/API.md`,
   `docs/reference/CLI.md`.

## Sources

- `thoughts/history-db-expand-wiring.md` — §2 (loop/eval outcomes gap)
- EPIC-2457 review (2026-07-05) — item #2
- `scripts/little_loops/cli/harness.py:192` (`_evaluate_and_report`), `:450`
  (`main_harness`; `cli_event_context` wrap at `:452`)
- ENH-2459 — sibling structured-result table (`test_run_events`)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `docs/reference/CLI.md` | New `ll-session --kind` value |

## Integration Map

### Files to Modify

**Schema & registers (`scripts/little_loops/session_store.py`)**
- Line 102 — `SCHEMA_VERSION = 18` → bump to `19`.
- Lines 104–118 — `_VALID_KINDS` frozenset: add `"harness"`.
- Lines 119–130 — `_KIND_TABLE` dict: add `"harness": "harness_events"`.
- Lines 521–544 (v18 migration slot) — append v19 `harness_events` table + 3 indexes (mirroring the v18 `test_run_events` block shape). `_apply_migrations` (line 609) is append-only; no helper function needed.
- Lines 60–87 (`__all__`) + module docstring top-of-file — export `record_harness_event` and reference it in the Public API list.

**Producer (`scripts/little_loops/cli/harness.py`)**
- Line 22 — imports: add `record_harness_event` from `little_loops.session_store`.
- Line 192 — `_evaluate_and_report()`: capture `passed` and `eval_result.verdict` so the caller can persist them (today both flow only into the print/return path).
- Lines 277–354 — `cmd_skill/cmd_cmd/cmd_mcp/cmd_prompt`: extract a `runner_label` (already built at 284/305/367/383) + structured fields into a small helper before returning; that helper calls `record_harness_event(...)` under `contextlib.suppress(Exception)`.
- Lines 402–447 — `cmd_dsl()`: emit one row per `DslTask` after each `cmd_prompt(task_args)` call (line 440), not just the aggregate.
- Line 450 — `main_harness()`: keep the existing `cli_event_context(...)` wrap at `:452` (don't disturb the legacy `cli_events` row); layer the structured write alongside.

**Read API (`scripts/little_loops/history_reader.py`)**
- Lines 124–162 — declare `@dataclass HarnessEvent` mirroring `RunEvent` field shape.
- Lines 562–598 — model `recent_harness_events(runner=None, target=None, since=None, limit=50, db=DEFAULT_DB_PATH)` after `recent_test_runs()` (parameterized WHERE, `ORDER BY ts DESC, id DESC LIMIT ?`, `_connect_readonly` swallow).
- `summarize_skills()` (lines 472–521) is the closest existing `SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) / total` rollup pattern — model `harness_pass_rate(target, since)` after it.
- Lines 1–42 — module docstring Public API list.

**CLI (`scripts/little_loops/cli/session.py`)**
- Lines 91–106 + 113–129 — append `"harness"` to both `--kind` `choices` lists (search and recent parsers). Module docstring (line 8–10) needs `"harness"` added to the kind list paragraph.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py` — re-exports `main_harness`; no change required (entry point already wired at `pyproject.toml:54`).
- `scripts/tests/test_cli_harness.py:1-100` — existing `FakeRunner` / `_make_completed` / `_make_namespace` / `_llm_verdict` helpers provide the wire-up surface for new `TestHarnessEventPersistence` tests.
- `scripts/little_loops/fsm/evaluators.py:49-58` — defines `EvaluationResult` (fields: `verdict`, `details`) used by `evaluate_llm_structured` at line 915 and consumed at `harness.py:215`.
- `scripts/little_loops/git_utils.py` — `get_head_sha()` / `get_current_branch()` available for populating `head_sha` / `branch` columns (used analogously in `record_commit_event` at `session_store.py:1067-1072`).

### Similar Patterns
- **`session_store.py:1171-1233`** — `record_test_run_event()` is the canonical sibling (kwargs shape, `_index(..., kind="test_run", ...)` call, `connect()` → `INSERT` → `commit` in `try/finally`). `pytest_history_plugin.py:81-148` is the consumer pattern.
- **`session_store.py:1041-1091`** — `record_commit_event()` is the alternative shape if `harness_events` needs `INSERT OR IGNORE` dedup on a natural key (it currently doesn't — each CLI invocation is a distinct row, no dedupe key yet).
- **`history_reader.py:472-521`** — `summarize_skills()` is the existing percent-rollup template for `harness_pass_rate(target, since)`.

### Tests
- `scripts/tests/test_session_store.py:3549-3619` — `TestRecordTestRunEvent` class (round-trip, FTS, multi-row, schema-upgrade). Mirror as `TestRecordHarnessEvent`.
- `scripts/tests/test_session_store.py:3075-3095` — `_bootstrap_schema_at(db, version)` helper for upgrade-path test (`_bootstrap_schema_at(db, 18)` + assert `harness_events` in `sqlite_master` after `ensure_db(db)`).
- `scripts/tests/test_history_reader.py:1442-1460` — `test_recent_test_runs_and_pass_rate` round-trip; mirror for `recent_harness_events` + `harness_pass_rate`.
- `scripts/tests/test_history_reader.py:1505-1522` — empty/missing-DB graceful-degradation test pattern.
- `scripts/tests/test_ll_session.py:962-975` — `test_recent_kind_test_run_outputs_row`; mirror as `test_recent_kind_harness_outputs_row`.
- `scripts/tests/test_ll_session.py:977-989` — `test_search_kind_commit_filters`; mirror for `test_search_kind_harness_filters`.
- `scripts/tests/test_cli_harness.py` — new `TestHarnessEventPersistence` class (PASS run, FAIL run, timeout, DSL multi-row, graceful degradation: DB absent/locked unchanged harness exit code).

### Documentation
- `docs/ARCHITECTURE.md:612-635` — `history.db` schema-versions table; append v19 row (`harness_events`) next to v18 `test_run_events`.
- `docs/reference/API.md:6723-6767` — module-reference blocks for `recent_test_runs` and friends; add `recent_harness_events` + `harness_pass_rate`.
- `docs/reference/API.md:6980-7048` — `record_test_run_event` reference doc; add `record_harness_event`.
- `docs/reference/CLI.md:2245, 2253` — `--kind {...,harness}` flag tables for both `search` and `recent`; lines 2280–2282 example block needs a `--kind harness` snippet.

### Configuration
- `config-schema.json:1577-1611` — `analytics.capture` block. `additionalProperties: false`, so adding `"harness_events": true` toggle (analogous to `corrections` / `file_events`) needs both schema and consumer wiring; not strictly required to ship — keep parity with ENH-2459 which does not gate `test_run_events`.

## Status

**Open** | Created: 2026-07-05 | Priority: P3

## Session Log
- `/ll:refine-issue` - 2026-07-07T00:41:19 - `b56869a4-8510-44e9-9ae9-aea10bc8d02d.jsonl`
- audit - 2026-07-06 - Corrected function reference: pass/fail logic lives in `_evaluate_and_report()` at `harness.py:192` (there is no `_evaluate()` at `:197`); `main_harness` is at `:450` with the `cli_event_context` wrap at `:452`.
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
