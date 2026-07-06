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
(`cli/harness.py:main_harness()` at `:452`; pass/fail logic at `:197–252`,
`eval_result.verdict`), but only the process **exit code** is persisted — via the
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
- `_evaluate()` (`harness.py:197`) computes `passed`, prints `PASS`/`FAIL`, and
  returns an exit code; `eval_result.verdict` is not persisted.
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
- Call it from `main_harness()` after `_evaluate()` returns, reading `runner`
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

## Implementation Steps

1. Schema migration for `harness_events`; bump `SCHEMA_VERSION`.
2. Add `"harness"` to `_VALID_KINDS` and `_KIND_TABLE`.
3. Implement `record_harness_event()` in `session_store.py`; export.
4. Wire `main_harness()` (post-`_evaluate`) + the `--dsl` per-task path.
5. `history_reader.recent_harness_events()` + `harness_pass_rate()`.
6. CLI: `ll-session recent --kind harness`.
7. Tests: `TestRecordHarnessEvent`, `TestHarnessSchema`,
   `TestHarnessWiring`, graceful-degradation test.
8. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/API.md`,
   `docs/reference/CLI.md`.

## Sources

- `thoughts/history-db-expand-wiring.md` — §2 (loop/eval outcomes gap)
- EPIC-2457 review (2026-07-05) — item #2
- `scripts/little_loops/cli/harness.py:197-252` (`_evaluate`), `:452`
  (`main_harness` cli_event_context wrap)
- ENH-2459 — sibling structured-result table (`test_run_events`)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `docs/reference/CLI.md` | New `ll-session --kind` value |

## Status

**Open** | Created: 2026-07-05 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
