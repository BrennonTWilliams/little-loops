---
id: ENH-2493
title: Persist ll-harness / eval outcomes into history.db
type: ENH
priority: P3
discovered_date: 2026-07-05
captured_at: '2026-07-05T00:00:00Z'
discovered_by: capture-issue
parent: EPIC-2457
labels:
- enhancement
- history-db
- eval
- captured
learning_tests_required:
- sqlite3
confidence_score: 100
outcome_confidence: 43
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 0
size: Very Large
status: done
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

## Architectural Note — direct-write is primary (ARCHITECTURE-144 scope)

ARCHITECTURE-144 (`.ll/decisions.yaml`, ENH-2581) named this issue among those
"turned into event_type parser tasks over raw_events." That clause is scoped by a
later project decision (see `.ll/decisions.d/`): the parser reframe applies only
to fields sourced from the 5 JSONL-ingested `raw_events` kinds. `ll-harness` runs
appear as Bash `tool_events` **only when run inside a Claude session**;
out-of-session / CI / manual runs never touch the transcript, and the semantic
`verdict` / `exit_code` would have to be scraped from captured stdout. Therefore
**direct-write (`record_harness_event`) stays the primary producer** — it is the
only path that captures every run with structured fields. An optional
`_backfill_harness_events` parser over `tool_events` (keyed on the `ll-harness`
command basename) may be added later as *secondary enrichment*, not a replacement.
This is a documented, justified pattern deviation, mirroring ENH-2507.

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

### Codebase Research Findings — Anchor Refresh (2026-07-16)

_Added by `/ll:refine-issue` — corrects stale anchors verified against current `main` at refinement time:_

- **`SCHEMA_VERSION` is now 20, not 18.** Verified at `scripts/little_loops/session_store.py:207` — current value is `SCHEMA_VERSION = 20`. The existing Implementation Steps say "bump `SCHEMA_VERSION = 18 → 19`" but the next free slot when this issue lands is **20 → 21**. The earlier Scope Boundary note already flagged this; this subsection pins the precise landing version. The migration comment should be `# v21 (ENH-2493): harness_events — persisted ll-harness / eval outcomes …`.
- **Symbol name correction: `VALID_KINDS` (no underscore, tuple, not frozenset).** Verified at `session_store.py:209-222`:
  ```python
  VALID_KINDS: tuple[str, ...] = (
      "tool", "file", "issue", "loop", "correction", "message",
      "skill", "cli", "snapshot", "commit", "test_run", "usage",
  )
  ```
  Appending `"harness"` here automatically extends the `--kind` choices in `cli/session.py` — both `search` and `recent` subparsers bind to `list(VALID_KINDS)` (verified at `cli/session.py:102-106` and `:113-118`).
- **`__all__` lines 61-93** (32 exports — confirmed). Add `"record_harness_event"` to this list before implementation.
- **`_KIND_TABLE` lines 223-236.** Add `"harness": "harness_events"` here.
- **`record_test_run_event()` is at lines 1352-1414, not 1171-1233.** Earlier anchors in this issue (line 128, 130, 131) are off by ~180 lines because subsequent migrations (v19 raw_events/ENH-2581, v20 usage_events/ENH-2461) and other additions grew the file. Place `record_harness_event()` directly after `record_test_run_event()` at line 1414, before the next public symbol.
- **No `harness_events` reference anywhere yet.** Confirmed: `grep -rn "harness_events\|record_harness" scripts/little_loops/` returns zero matches.
- **`git_utils.py` does NOT exist** — the prior Integration Map (`scripts/little_loops/git_utils.py:get_head_sha()` / `get_current_branch()`) is a stale anchor. The actual file is `scripts/little_loops/git_operations.py` and neither helper exists there. The canonical helper is `_git_output(*args) -> str | None` at `scripts/little_loops/pytest_history_plugin.py:61-74`. **Recommended path**: replicate the 14-line `_git_output` helper locally in `cli/harness.py` (private), or factor it into a new `scripts/little_loops/git_utils.py` if more than one consumer needs it (post-MVP; keep scope small for v21).
- **`recent_test_runs()` is at `history_reader.py:689-725`, not 562-598** (file grew by ~125 lines since the original anchors). Mirror `recent_harness_events()` immediately after it.
- **`RunEvent` dataclass is at `history_reader.py:138-161`** (anchor close, prior estimates held). Place `HarnessEvent` dataclass right after.
- **`history_reader.py` has no `__all__`** — prior Integration Map guess ("Lines 1-42 — module docstring Public API list") was about the docstring, not an `__all__` list. Update only the module docstring Public API list.
- **`summarize_skills()` is at `history_reader.py:497-546`** and returns `list[dict]`, not a dataclass. `harness_pass_rate(target, since)` can either return `list[dict]` (consistent) or a typed `@dataclass` (cleaner). Recommend `dict` for v1 to mirror existing pattern.
- **`cli_event_context` does NOT swallow `sqlite3.Error` (pre-existing issue).** Per `session_store.py:1054-1091`, the existing `__exit__` does `conn.commit()` without a `try/except`, so a missing/locked DB raises into the wrapped harness CLI body. The newer `skill_event_context` (`session_store.py:1108-1195`) wraps in `try/except sqlite3.Error` per EPIC-1707. **The harness call site MUST wrap `record_harness_event(...)` in `contextlib.suppress(Exception)`** (mirroring `pytest_history_plugin.py:118-121`) so that "DB absent/locked does not change the harness exit code" (Acceptance Criterion) holds. This is a hard requirement — `cli_event_context` cannot be relied on for graceful degradation.
- **DSL per-task vs aggregate row linkage**: The current Implementation Step says "emit one row per DslTask" but does not specify how per-task rows link back to the aggregate row. **`cmd_prompt` only returns an `int rc`** (verified at `harness.py:380-399`); `RunnerResult` (`harness.py:25-33`) is local to `cmd_skill/cmd_cmd/cmd_cmd/cmd_mcp/cmd_prompt` and not returned. Two viable strategies:

  **Option A** — Aggregate-first then per-task: write the aggregate `harness_event` row first to capture `lastrowid`, then collect per-task results in memory inside the `for task_file in task_files:` loop, then write each per-task row with `parent_id=<lastrowid>`. Matches `record_commit_event`'s `INSERT OR IGNORE` idempotency model (per-task insert is straightforward once you have the parent id).

  **Option B** — Collect-then-bulk-write: append each per-task outcome to a list inside the loop, write the aggregate row at the end, then write all per-task rows with `parent_id` populated. Two passes over DB but no transient FK-style ordering issue.

  **Recommended**: Option A — single pass, parent_id known immediately, matches `record_commit_event` precedent. The aggregate row uses `parent_id=NULL` and `target=str(path)` (the file or directory); per-task rows use `target=task_file.name`, `runner="dsl-task"` (distinct from aggregate's `runner="dsl"`), `parent_id=aggregate_row.lastrowid`. Schema must include a nullable `parent_id INTEGER` column (FK would be overkill for SQLite — leave as plain column with no constraint, matching `record_commit_event`'s `parent_sha` precedent).

  This decision adds **a `parent_id` column to the proposed schema** (not in the original SQL block above). Trade-off: simple, queryable (`SELECT * FROM harness_events WHERE parent_id IS NOT NULL` for per-task rows); cost is one extra nullable column.

- **Schema column extensions for richer `EvaluationResult.details` capture** (per `fsm/evaluators.py:48-58` and `evaluate_llm_structured`): the proposed SQL has only `semantic_verdict` + `semantic_passed`, but `EvaluationResult.details` includes `confidence`, `confident`, `reason`, `evidence`, `evidence_coerced`, `llm_model`, `llm_latency_ms`, `llm_prompt` (truncated 500 chars), `llm_raw_output` (truncated 500 chars). Add these columns to make `--semantic` eval runs fully queryable:
  ```sql
  semantic_prompt TEXT,            -- args.semantic (input to evaluate_llm_structured)
  semantic_confidence REAL,        -- eval_result.details["confidence"]
  semantic_reason TEXT,            -- eval_result.details["reason"]
  semantic_evidence TEXT,          -- eval_result.details["evidence"]
  semantic_model TEXT,             -- eval_result.details["llm_model"]
  ```
  All nullable; `_evaluate_and_report()` has access to all of them at `:215` (only when `args.semantic is not None`).

- **`_evaluate_and_report()` does NOT return `passed`/`eval_result` to callers** (verified at `harness.py:192-252`): both are locals, and all `cmd_*` runners return only the int exit code. Two threading strategies:
  - **(a)** Change `_evaluate_and_report` signature to return `(rc, EvalReport)` where `EvalReport` is a small dataclass with `passed: bool`, `verdict: str | None`, `eval_result: EvaluationResult | None`. Each caller `cmd_skill/cmd_cmd/cmd_mcp/cmd_prompt` writes a `harness_event` row using the dataclass fields.
  - **(b)** Attach fields to the mutable `args: argparse.Namespace` inside `_evaluate_and_report` (`args.__dict__["_harness_eval"] = EvalReport(...)`) before the final `return rc`. Hackier but smaller diff.
  **Recommended**: (a) — explicit, type-safe, no global mutation. Add a tiny `@dataclass EvalReport` near `RunnerResult` at `harness.py:25-33` with three fields (`passed: bool`, `verdict: str | None`, `eval_result: EvaluationResult | None`).
- **Test class anchors (verified)**: `TestRecordTestRunEvent` at `scripts/tests/test_session_store.py:4362`; `_bootstrap_schema_at(db, version)` helper at `scripts/tests/test_session_store.py:3891`; `TestNewEventReaders` at `scripts/tests/test_history_reader.py:1395`; `test_recent_test_runs_and_pass_rate` at `scripts/tests/test_history_reader.py:1459`; `TestSkillStatsAndNewKinds` at `scripts/tests/test_ll_session.py:1040`; `TestHarnessEventPersistence` does not exist yet (create new in `test_cli_harness.py` after `TestCmdDsl` ends ~line 940+). Shared helpers in `test_cli_harness.py:25-75` (`FakeRunner`, `_make_completed`, `_make_namespace`, `_llm_verdict`) are reusable for new tests.
- **`LlLoop` row pattern mirrors `record_test_run_event` exactly**: `connect(db_path)` → `INSERT` → `_index(conn, kind="harness", ref=target or "", anchor=runner or "", content=<summary>[:512], ts=ts)` → `conn.commit()` → `finally: conn.close()`. The recorder raises; the caller wraps in `contextlib.suppress(Exception)`. This matches the AC's "best-effort, DB absent/locked does not change exit code" guarantee.

### Codebase Research Findings — Anchor Refresh (2026-07-22)

_Added by `/ll:refine-issue` — corrects further anchor drift verified against current `main`; the 2026-07-16 pass is now itself stale on line numbers (schema grew by 10 versions and several symbols moved files/lines in the intervening week). Grep confirms `harness_events`/`record_harness_event` still have zero references anywhere — the issue remains unimplemented._

- **`SCHEMA_VERSION` is now 30, not 20/21.** Verified at `session_store.py:222`. The landing slot at implementation time will be whatever is open then — continue to read the live constant rather than trusting any literal in this issue (per the existing "Scope Boundary" note below, which remains correct in spirit).
- **`VALID_KINDS` has grown to 18 entries** (`session_store.py:224-243`): `tool, file, issue, loop, correction, message, skill, cli, snapshot, commit, test_run, usage, orchestration_run, loop_run, learning_test, session_lifecycle, subagent_run, hook_event`. Still a plain tuple (confirms the 2026-07-16 correction); `_KIND_TABLE` dict starts at line 244 (was 209-236 → 223-236 in earlier passes).
- **`record_test_run_event()` moved again — now at `session_store.py:1727`** (was 1352-1414, was 1171-1233 before that). The file keeps growing; re-check the live line before placing `record_harness_event()` — do not trust any specific line number from prior refine passes, place it directly after whatever `record_test_run_event()`'s current end is.
- **`_EXPORT_TABLE_MAP` / `_EXPORT_DEFAULT_TABLES` are now at `session_store.py:4419` / `:4436`** (was 3304-3329). Same append pattern still applies (`"harness_event": ("harness_events", "ts")`).
- **`_REBUILD_TABLES` is now at `session_store.py:3926-3937`**, not 2818-2823 — and its current contents are `tool_events, message_events, assistant_messages, skill_events, sessions, user_corrections, summary_nodes, summary_spans, usage_events`. Note `test_run_events` and `commit_events` are **not** in this tuple either (they're direct-write like `harness_events` will be) — the "extend the comment" wiring step (Wiring Phase #10) should target this literal list, and `harness_events` does not need to be added to it (only mentioned in the explanatory comment, if one exists nearby — none currently does inline).
- **`TestRunEventVariant` is at `observability/schema.py:502`; `DES_VARIANTS` tuple starts at `:571` and includes `TestRunEventVariant` at `:634`** (was 501-507 / ~626 in the prior pass — moved but not drastically). Add `HarnessEventVariant` near `TestRunEventVariant` and register it adjacent to it in the tuple.
- **`RunEvent` dataclass is at `history_reader.py:163`** (was 138-161/138-162 — close). **`summarize_skills()` is at `:608`** (was 472-521/497-546). **`recent_test_runs()` is at `:1350`** (was 562-598/689-725). Re-verify exact line at implementation time; the module continues to grow ~100+ lines per week across sibling EPIC-2457 issues landing in parallel.
- **`RunnerResult`/`RunnerType` now live in `scripts/little_loops/runner_spec.py`** (`RunnerType` at `:43`, `RunnerResult` at `:55` — a frozen dataclass with `stdout`, `stderr`, `exit_code`, `timed_out`, `error`), imported into `cli/harness.py:17`. This corrects the prior pass's claim that `RunnerResult` is "local to `harness.py:25-33`" — it is now a shared module-level type, not local. `DslTask` (harness-specific, not shared) is still local at `cli/harness.py:28`. This doesn't change the wiring approach (both `(a)` return-dataclass and `(b)` mutable-namespace threading strategies from the 2026-07-16 pass remain valid), but implementers should import any new `EvalReport`-style dataclass alongside `RunnerResult`/`ActionSpec` in `runner_spec.py` if it's meant to be reused outside `harness.py`, or keep it harness-local if not.
- **`_evaluate_and_report()` is now at `cli/harness.py:183-240`** (function body re-verified: `passed`/`exit_code_display`/`semantic_display` are still locals; `eval_result.verdict` at `:206`; still returns only `int`). **`cmd_dsl()` is now at `:339-383`**, and per-task dispatch is `rc = cmd_prompt(task_args)` at `:376` (was `:440` in the earlier pass) — this is the loop iteration site where a per-task `record_harness_event(..., runner="dsl-task", parent_id=<aggregate id>)` call would go. **`main_harness()` is now at `:387-407`**, with the `cli_event_context(...)` wrap at `:389` (was `:450`/`:452`).
- **`TestRecordTestRunEvent` is now at `scripts/tests/test_session_store.py:4566`; `_bootstrap_schema_at()` is at `:4095`** (was 4362 / 3891 in the prior pass).
- **Net effect**: no structural finding from the 2026-07-16 pass is invalidated (the threading strategy, `contextlib.suppress(Exception)` requirement, `parent_id` DSL design, and semantic-column additions all still apply as designed) — only line-number anchors moved. Re-verify every anchor against live `main` immediately before implementing rather than trusting any specific line number cited anywhere in this issue, including this refresh.

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and MUST be included in the implementation alongside Steps 1–8:_

9. **`_EXPORT_TABLE_MAP` + `_EXPORT_DEFAULT_TABLES`** — at `session_store.py:3304-3329`, append `"harness_event": ("harness_events", "ts")` and `"harness_event"`. Without this, `ll-session export --tables harness_event` fails silently (table not in map). Mirror `test_run_event` precedent at lines 3313–3314.
10. **`_REBUILD_TABLES` exclusion comment** — at `session_store.py:2818-2823`, extend the comment to enumerate `harness_events` as direct-write-only. No code change (rebuild already skips it correctly), but the comment prevents future contributors from mistakenly adding it to the rebuild list.
11. **DES variant registration** — in `scripts/little_loops/observability/schema.py`, add `HarnessEventVariant` (type `Literal["harness_event"]`) after `TestRunEventVariant` at lines 506–507, and register it in the `DES_VARIANTS` tuple around line 626. **Mandatory** — without this, `ll-verify-des-audit` flags un-covered emit sites. Add a counterpart assertion in `scripts/tests/test_des_schema.py`.
12. **`export --tables` help text** — at `cli/session.py:228-230`, append `, harness_event` to the hardcoded `"Choices: session, issue_event, ..."` string (kept in sync with `_EXPORT_TABLE_MAP`).
13. **Mermaid diagram `v1–v20` → `v1–v21`** — at `docs/ARCHITECTURE.md:723, 748`, bump schema-version ranges to include v21.
14. **API doc import snippets** — at `docs/reference/API.md:6837-6850` and `:7287`, add `recent_harness_events` / `harness_pass_rate` / `record_harness_event` to the rendered `from little_loops.X import (...)` blocks.
15. **CLI doc `--kind` tables** — at `docs/reference/CLI.md:2427, 2435, 2509-2514`, append `,harness` to the static `--kind {tool,file,...}` choice tables and add a `--kind harness` example snippet.
16. **`scripts/tests/test_des_schema.py`** — add a counterpart assertion verifying `HarnessEventVariant` coverage (mirroring existing variant registration checks).

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
- **Lines 3304–3329** — `_EXPORT_TABLE_MAP` and `_EXPORT_DEFAULT_TABLES`: append `"harness_event": ("harness_events", "ts")` and `"harness_event"` (mirror `test_run_event`/`commit_event` precedent at 3313–3314). Without this, `ll-session export --tables harness_event` will fail. `[Agent 1 + Agent 2]`
- **Lines 2818–2823** — `_REBUILD_TABLES` exclusion-comment block: extend to enumerate `harness_events` alongside `cli_events/file_events/test_run_events/...` so future schema-doc readers know `harness_events` is direct-write-only. No code change (rebuild skips it correctly today). `[Agent 2]`

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
- **Lines 228–230** — `export --tables` help text hardcodes `"Choices: session, issue_event, ..."`; append `, harness_event` so the help string stays in sync with `_EXPORT_TABLE_MAP`. `[Agent 2]`

**DES audit / observability (NEW for this issue)**
- **Lines 506–507 of `scripts/little_loops/observability/schema.py`** — add a `HarnessEventVariant` (type `Literal["harness_event"]`) mirroring `TestRunEventVariant` (lines 501–505) and `CommitEventVariant` (lines 494–498).
- **Line ~626 of `observability/schema.py`** — register the new variant in the `DES_VARIANTS` tuple (after `TestRunEventVariant`).
- **`scripts/tests/test_des_schema.py`** — add a counterpart assertion verifying `HarnessEventVariant` is registered (mirroring existing variant coverage). Without this, `ll-verify-des-audit` will flag un-covered emit sites. `[Agent 1 + Agent 2]`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py` — re-exports `main_harness`; no change required (entry point already wired at `pyproject.toml:54`).
- `scripts/tests/test_cli_harness.py:1-100` — existing `FakeRunner` / `_make_completed` / `_make_namespace` / `_llm_verdict` helpers provide the wire-up surface for new `TestHarnessEventPersistence` tests.
- `scripts/little_loops/fsm/evaluators.py:49-58` — defines `EvaluationResult` (fields: `verdict`, `details`) used by `evaluate_llm_structured` at line 915 and consumed at `harness.py:215`.
- `scripts/little_loops/git_utils.py` — `get_head_sha()` / `get_current_branch()` available for populating `head_sha` / `branch` columns (used analogously in `record_commit_event` at `session_store.py:1067-1072`).
- `scripts/little_loops/cli/verify_kinds.py:38-47` — `_run()` scans every `CREATE TABLE` in `_MIGRATIONS` and asserts each appears in `_KIND_TABLE` or `_KINDLESS_TABLES`. Adding `harness_events` to `_MIGRATIONS` without `_KIND_TABLE` registration **fails the gate**. `[Agent 1]`
- `scripts/little_loops/hooks/session_start.py:161-172` — auto-rebuild path (`_last_rebuild_version < SCHEMA_VERSION`) fires on next session start once `SCHEMA_VERSION` is bumped; the JSONL-derived cache tables will rebuild automatically. No code change required. `[Agent 1]`
- `scripts/little_loops/cli/logs.py:1495-1736` — `_EvalInvocation` / `EvalFixture` reconstruction path (`ll-logs eval-export`) does NOT consult `harness_events` today; it builds fixtures from JSONL alone. Unaffected by this issue (candidate follow-on only). `[Agent 1]`
- `scripts/little_loops/cli/loop/_helpers.py:1926, 1930, 2101` — references `harness_pass_rate` / `harness_pass` for the **A/B comparator** (different semantics). Unrelated to the new `history_reader.harness_pass_rate()`. **Naming collision risk** — see "Notable Risks" below. `[Agent 1]`
- `scripts/little_loops/ab_writer.py:30, 39, 146, 174, 194, 221, 265` — defines `ABResults.harness_pass_rate` (float 0-1 fraction). The new `history_reader.harness_pass_rate(target, since)` shares the name with different semantics. Scoped to different modules — no import conflict — but downstream callers must distinguish. `[Agent 1]`
- `scripts/little_loops/cli/migrate.py`, `cli/migrate_status.py`, `cli/migrate_labels.py`, `cli/migrate_relationships.py` — one-shot issue-file migrations only; do not touch `_MIGRATIONS` / `VALID_KINDS` / `_KIND_TABLE`. No update. `[Agent 1]`
- `scripts/little_loops/init/writers.py:50, 70` — `Bash(ll-harness:*)` allow-list and CLI docstring mention; descriptive prose only, not a wiring constraint. Optional prose update ("eval outcomes persisted to history.db") only. `[Agent 1]`

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

_Wiring pass added by `/ll:wire-issue` — additional tests identified that the issue does not enumerate:_
- **`TestHarnessSchema.test_harness_event_indexes_exist`** (new in `scripts/tests/test_session_store.py`) — mirror `test_session_id_index_exists_and_is_used` at `:4049`. Asserts `idx_harness_runner`, `idx_harness_target`, `idx_harness_passed` exist in `sqlite_master`. `[Agent 3]`
- **`TestHarnessSchema.test_harness_kind_registered_in_both_tables`** — direct integrity assertion: `"harness" in VALID_KINDS` and `_KIND_TABLE["harness"] == "harness_events"`. Closes gap left by `test_verify_kinds.py`'s scan-only approach. `[Agent 3]`
- **`TestRecordHarnessEvent.test_semantic_columns_round_trip`** — write/read cycle for `semantic_prompt`, `semantic_confidence`, `semantic_reason`, `semantic_evidence`, `semantic_model` (mirror `test_roundtrip`). `[Agent 3]`
- **`TestRecordHarnessEvent.test_parent_id_round_trip`** — self-FK nullable column accepts arbitrary int (or `NULL`). `[Agent 3]`
- **`TestRecordHarnessEvent.test_harness_target_fts_searchable`** — verify `_index()` writes `kind="harness"` row to FTS5 when `record_harness_event` is called; mirror `test_record_skill_event_fts_indexed` at `:1641`. `[Agent 3]`
- **`TestRecordHarnessEvent.test_semantic_passed_mapping`** — `@pytest.mark.parametrize(("verdict", "passed"), [("yes", 1), ("no", 0), ("blocked", 0), ("partial", 0), ("error", 0)])`; mirror `test_semantic_non_yes_fails` at `:612`. `[Agent 3]`
- **`TestHarnessEventPersistence.test_dsl_aggregate_and_per_task_rows_with_parent_id`** — assert DSL batch writes 1 aggregate row (`runner="dsl"`, `parent_id IS NULL`) + N per-task rows (`runner="dsl-task"`, `parent_id = aggregate.id`). No existing precedent; new assertion. `[Agent 3]`
- **`TestHarnessEventPersistence.test_main_harness_succeeds_when_db_unopenable`** — set `LL_HISTORY_DB=/nonexistent/path.db` and assert exit code unchanged (PASS still exits 0). Mirrors `cli_event_context`'s missing `try/except` (verified `session_store.py:1054-1091`) — `record_harness_event` MUST be wrapped in `contextlib.suppress(Exception)` at the call site. `[Agent 3]`
- **`TestNewHarnessReaders.test_recent_harness_events_filters`** (`scripts/tests/test_history_reader.py`) — assert `runner=`, `target=`, `since=` filters independently and combined. Mirror `test_recent_commit_events_filters` at `:1438`. `[Agent 3]`
- **`TestNewHarnessReaders.test_harness_pass_rate_returns_none_when_no_semantic_results`** — division-by-zero guard when all rows have `semantic_passed IS NULL`. Mirror `summarize_skills`'s `(... if completions else None)` at `:533-545`. `[Agent 3]`
- **`TestNewHarnessReaders.test_readers_return_empty_on_missing_db`** — both `recent_harness_events` and `harness_pass_rate` return `[]` / `None` for missing DB. Mirror the existing test at `:1530`. `[Agent 3]`
- **`scripts/tests/test_verify_kinds.py`** — `test_clean_state_returns_zero` will pass once `_KIND_TABLE` is updated; no test code change needed but the implementation must satisfy the data-driven invariant. `[Agent 1]`

### Documentation
- `docs/ARCHITECTURE.md:612-635` — `history.db` schema-versions table; append v19 row (`harness_events`) next to v18 `test_run_events`.
- `docs/reference/API.md:6723-6767` — module-reference blocks for `recent_test_runs` and friends; add `recent_harness_events` + `harness_pass_rate`.
- `docs/reference/API.md:6980-7048` — `record_test_run_event` reference doc; add `record_harness_event`.
- `docs/reference/CLI.md:2245, 2253` — `--kind {...,harness}` flag tables for both `search` and `recent`; lines 2280–2282 example block needs a `--kind harness` snippet.

_Wiring pass added by `/ll:wire-issue` — additional documentation coupling:_
- **`docs/ARCHITECTURE.md:723, 748`** — mermaid diagrams reference `(v1–v20)` ranges (in `ensure_db() — bootstrap schema` and components table); bump to `(v1–v21)`. Schema-versions table line range has grown: current row block sits near `:657-678` (not the older `:612-635` anchor). `[Agent 2]`
- **`docs/reference/API.md:6837-6850`** — Python import snippet `from little_loops.history_reader import (...)` lists all readers; append `HarnessEvent`, `recent_harness_events`, `harness_pass_rate`. `[Agent 2]`
- **`docs/reference/API.md:7287`** — `session_store` import snippet — append `record_harness_event`. `[Agent 2]`
- **`docs/reference/API.md:4102-4103`** — `--kind {tool,file,...,usage}` choice list (CLI doc snippet, distinct from the live argparse choices); append `,harness`. `[Agent 2]`
- **`docs/reference/CLI.md:2427, 2435, 2509-2514`** — fixed `--kind {tool,file,...}` table at `:2427` is stale (missing `snapshot`, `usage`); mirror the live `VALID_KINDS` by appending `,harness` (and consider fixing the existing drift). `:2435` is the `recent --kind` table; needs same append. `:2509-2514` is the `recent --kind` example block; needs `--kind harness` example. `[Agent 2]`
- **`scripts/little_loops/cli/session.py:8-10`** (module docstring) — the prose list at the top of `cli/session.py` enumerates kinds; append `"harness"`. Already noted in the existing map but confirmed critical (the docs string is rendered in `--help`). `[Agent 1+2]`

### Configuration
- `config-schema.json:1577-1611` — `analytics.capture` block. `additionalProperties: false`, so adding `"harness_events": true` toggle (analogous to `corrections` / `file_events`) needs both schema and consumer wiring; not strictly required to ship — keep parity with ENH-2459 which does not gate `test_run_events`.

## Status

**Decomposed** | Created: 2026-07-05 | Priority: P3

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-22
- **Reason**: Very Large (score 11/11) — file count, section complexity,
  multiple concerns, dependency mentions, and word count all triggered.
  Qualitative-skip guard did not apply (`score_complexity=0`, guard requires
  both ambiguity and complexity ≥18). Split along clear module boundaries:
  foundational schema/recorder, the risky producer signature-refactor, and
  the read/CLI surface.

### Decomposed Into
- ENH-2739: harness_events schema, kind registration, and
  record_harness_event() recorder
- ENH-2740: Wire ll-harness producer to write harness_events (signature
  refactor + DSL per-task rows) — blocked_by: ENH-2739
- ENH-2741: harness_events read API, ll-session CLI wiring, and docs —
  blocked_by: ENH-2739

---

## Notable Risks (added by `/ll:wire-issue`)

_These risks surfaced during the wiring analysis and should be addressed before or during implementation:_

1. **Naming collision: `harness_pass_rate`.** The new `history_reader.harness_pass_rate(target, since)` (eval-flip rollup across DB history) shares its name with `scripts/little_loops/ab_writer.py:146` `ABResults.harness_pass_rate` (float 0–1 fraction from the A/B blind comparator). They are scoped to different modules, so no Python import collision — but downstream consumers of `cli/loop/_helpers.py:1926-1930` (which currently uses the A/B variant) MUST distinguish. **Recommendation**: keep both names; add a docstring paragraph at the top of `history_reader.harness_pass_rate` clarifying the eval-history semantics vs. the A/B semantics. The `specs/harness-optimize-rubric.md:280,316` and `specs/harness-optimize-rubric-check.py:853` references use the A/B context — unrelated to this issue, but worth a comment so future readers don't conflate them. `[Agent 1]`

2. **`cli_event_context` does NOT swallow `sqlite3.Error`.** Verified at `session_store.py:1054-1091` — the existing wrap commits without `try/except`, so a missing/locked DB raises into the harness CLI body. The newer `skill_event_context` (`session_store.py:1108-1195`) wraps in `try/except sqlite3.Error` per EPIC-1707. **The harness call site MUST wrap `record_harness_event(...)` in `contextlib.suppress(Exception)`** (mirroring `pytest_history_plugin.py:118-121`). This is a hard requirement — `cli_event_context` cannot be relied on for graceful degradation. Add a `TestHarnessEventPersistence.test_main_harness_succeeds_when_db_unopenable` test that pins this contract. `[Agent 1 + Agent 2]`

3. **DES audit Phase 1 regex does NOT match direct DB inserts.** `observability/audit.py:55-67` scans for `self._emit(...)` / `event_bus.emit(...)` calls; `record_harness_event(...)` is a direct DB insert, not an event-bus emit. The DES audit gate will NOT flag the new producer unless the `HarnessEventVariant` is explicitly registered in `observability/schema.py` `DES_VARIANTS`. Skipping step 11 of the Wiring Phase lets the new producer ship undetected by the audit gate. `[Agent 2]`

4. **`RunnerResult` re-export identity contract must not be disturbed.** `scripts/tests/test_runner_spec.py:49-54` (`TestRunnerResultReexport.test_runner_result_importable_from_harness`) pins `HarnessRunnerResult is RunnerResult` via `from little_loops.cli.harness import RunnerResult as HarnessRunnerResult`; `docs/reference/API.md:8521-8523` documents this as an unchanged-shape guarantee. The issue's own "Recommended: (a)" threading strategy proposes adding a new `EvalReport`-shaped dataclass "near `RunnerResult`... in `runner_spec.py`" — that's fine, but implementers must NOT fold new fields into `RunnerResult` itself or touch its re-export at `cli/harness.py:17`/`:20-24` (`__all__`) while doing so. Re-run `test_runner_spec.py::TestRunnerResultReexport` after implementation as a cheap regression check. Separately confirmed unaffected: `cli/action.py:68,90-98,127-136` and `cli/queue.py:46,58-77,230-243` call `run_action()`/`ActionSpec` directly (bypassing `harness.py`'s `_evaluate_and_report()`), consuming only `RunnerResult`'s existing fields — no coupling to add there. `[Wiring pass 2026-07-22]`

5. **18 `test_cli_harness.py` assertion sites break if `cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt` change return signature (int → tuple/dataclass) under Option (a).** Every listed test asserts `result == <int>` directly against these functions' return values and must change to `result.rc == <int>` (or equivalent unpacking) in lockstep with the signature change — NOT enumerated by the issue's original Implementation Steps:
   - `TestCmdSkill`: `test_skill_pass_no_criteria:199`, `test_skill_exit_code_pass:233`, `test_skill_exit_code_fail:245`, `test_skill_timeout_returns_2:261`, `test_skill_binary_not_found_returns_2:273`
   - `TestCmdCmd`: `test_cmd_captures_stdout:333`, `test_cmd_exit_code_pass:345`, `test_cmd_exit_code_fail:355`, `test_cmd_no_criteria_always_pass:367`, `test_cmd_timeout_returns_2:382`, `test_cmd_json_output:393`, `test_semantic_...pass:607`, `test_semantic_non_yes_fails:633` (parametrized 3x), `test_both_criteria_must_pass:657`
   - `TestCmdMcp`: `test_mcp_calls_tool:420`, `test_mcp_tool_error_exit_code:461`, `test_mcp_exit_code_criterion_fail:473`
   - `TestCmdPrompt`: `test_prompt_sends_request:502`
   - `cmd_dsl`'s internal call site (`harness.py:376`, `rc = cmd_prompt(task_args)`) also needs an unpacking update if `cmd_prompt`'s signature changes, since `cmd_dsl` consumes it directly; its own aggregate test assertions at `test_cli_harness.py:863,879,898` need the same treatment.
   - **Confirmed safe**: all PASS/FAIL `capsys.readouterr().out` substring assertions (e.g. `:200-201`, `:246-247`, `:334`, `:356-357`, `:608-609`, `:634-635`) check printed output, not the return value — unaffected by the signature change. `main_harness()`'s own tests (`test_main_harness_cmd_pass:682` etc., JSON-shape assertions at `:749-751`) are also unaffected since `main_harness()` itself is not changing shape. `[Wiring pass 2026-07-22]`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot ("bump
`SCHEMA_VERSION = 18` → `19`"). At least ten other active EPIC-2457 siblings
(ENH-2463, ENH-2464, ENH-2465, ENH-2492, ENH-2494, ENH-2495, ENH-2496,
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

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The Implementation Steps
instruct editing both `search_parser` and `recent_parser` `choices=[...]`
lists in `cli/session.py`. This premise is stale: both argparse subparsers
derive `choices=list(VALID_KINDS)` from the single source of truth at
`session_store.py` lines 104–118, so adding the new kind only to
`_VALID_KINDS` propagates to both subparsers. No duplicate `choices=[...]`
edit is required.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The proposed
`history_reader.harness_pass_rate(target, since)` collides in name with
`ABResults.harness_pass_rate` at `scripts/little_loops/ab_writer.py:146`
(float 0–1 fraction from the A/B comparator). The two are distinct symbols
in distinct modules, but downstream consumers of
`cli/loop/_helpers.py:1926-1930` (currently using the A/B variant) must
disambiguate. **The implementer should rename this issue's reader to
`history_reader.harness_eval_pass_rate(target, since)`** to remove the
ambiguity at the source rather than relying on the import path to
distinguish.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-22_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 43/100 → LOW

### Outcome Risk Factors
- Deep per-site complexity: Option (a) (recommended) changes `_evaluate_and_report()`'s return signature from `int` to a small dataclass — a genuine contract change that cascades to all 4 production callers (`cmd_skill`, `cmd_cmd`, `cmd_mcp`, `cmd_prompt`) plus `cmd_dsl`'s internal call to `cmd_prompt`, and breaks 18 existing test assertions across 4 test classes in `test_cli_harness.py` (enumerated in "Notable Risks" #5). Mitigation: the issue already enumerates every break site by file:line — budget time for the mechanical test-assertion updates rather than treating them as a surprise.
- Broad enumeration across N sites: the change touches 6+ distinct modules (`session_store.py`, `cli/harness.py`, `history_reader.py`, `cli/session.py`, `observability/schema.py`, plus 3 docs files and 5 test files) each with multiple precise edit points. Thoroughly documented, but the sheer site count raises the chance of a missed touchpoint on first pass — re-run the full gate (`python -m pytest scripts/tests/test_session_store.py scripts/tests/test_history_reader.py scripts/tests/test_ll_session.py scripts/tests/test_cli_harness.py scripts/tests/test_des_schema.py scripts/tests/test_verify_kinds.py -v`) rather than a narrow subset.

## Session Log
- `/ll:issue-size-review` - 2026-07-22T00:00:00Z - `5a7a2fd0-cba1-488a-89c7-36283dba4691.jsonl`
- `/ll:confidence-check` - 2026-07-22T00:00:00Z - `39bf2b90-4817-45f9-93b1-056dd83e238d.jsonl`
- `/ll:wire-issue` - 2026-07-22T19:52:31 - `51f70f6c-67d7-417d-af1b-2df06f09cee6.jsonl`
- `/ll:refine-issue` - 2026-07-22T19:48:04 - `2c7778a3-67ca-4e33-bfd3-e2dc60d47737.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-17T18:48:07 - `ff04da3c-210f-4c14-9967-762b390ae67c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-17T13:57:02 - `ff04da3c-210f-4c14-9967-762b390ae67c.jsonl`
- `/ll:wire-issue` - 2026-07-16T21:46:25 - `4035a88c-b8a6-4625-98d9-33f0bbb7d51e.jsonl`
- `/ll:wire-issue` - 2026-07-16T00:00:00Z - `<this-session>`
- `/ll:refine-issue` - 2026-07-16T15:04:04 - `74755637-ff93-4bca-bf37-d7f6bf2012f5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-14T00:23:47 - `bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
- `/ll:refine-issue` - 2026-07-07T00:41:19 - `b56869a4-8510-44e9-9ae9-aea10bc8d02d.jsonl`
- audit - 2026-07-06 - Corrected function reference: pass/fail logic lives in `_evaluate_and_report()` at `harness.py:192` (there is no `_evaluate()` at `:197`); `main_harness` is at `:450` with the `cli_event_context` wrap at `:452`.
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
