---
id: ENH-2494
title: Capture lint/typecheck/format gate results into history.db
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
  - ci
  - captured
---

# ENH-2494: Capture lint/typecheck/format gate results into history.db

## Summary

ENH-2459 gave the DB `test_run_events` for pytest — but the project's CI gate per
`.claude/CLAUDE.md` § Testing & CI Policy is really **pytest + `ruff check` +
`mypy` + `ruff format --check`**. The three non-pytest gates leave no structured
record: their pass/fail counts, error counts, and offending files vanish into CLI
text. Generalize the existing `test_run_events` machinery to a `check_events`
table (or add a `tool` discriminator + a `check_run` kind) so all four gates are
captured uniformly and "when did type-checking start failing, and on which
files?" becomes a query. The write-point is the `/ll:check-code` skill's command
runs (there is no `ll-check-code` binary today — it is skill-driven).

## Motivation

- **Three of four CI gates are unobservable.** Only pytest is captured; ruff and
  mypy regressions can't be traced historically or correlated with the commit
  that introduced them (`commit_events`, ENH-2458).
- **Cheap, high-symmetry extension.** `record_test_run_event()` already models
  `(total, passed, failed, errored, skipped, failing_names, command, head_sha,
  branch)` and FTS-indexes failing names. Lint/type results map onto the same
  shape (error count + offending file/rule names).
- **Enables a green-across-all-gates join.** Combined with `test_run_events` and
  `orchestration_runs` (ENH-2492), the DB can answer "did this automated fix pass
  every gate?" without re-running anything.

## Current Behavior

- `python -m pytest` results land in `test_run_events` (ENH-2459).
- `ruff check`, `mypy`, `ruff format --check` produce only CLI output; nothing
  persists. The `/ll:check-code` skill runs them ad hoc.
- No `--kind check_run` in `ll-session`.

## Expected Behavior

- A `check_events` table records one row per gate run with
  `tool` (`ruff` / `mypy` / `ruff-format`), pass/fail, error count, and a
  JSON list of offending files/rules (FTS-indexed like `failing_names`).
- The `/ll:check-code` command runs write a row per tool (best-effort guarded).
- `ll-session recent --kind check_run` returns rows;
  `ll-session search --fts "<file_or_rule>" --kind check_run` matches.

## Proposed Solution

### Schema migration

Prefer a **new `check_events` table** over overloading `test_run_events` (keeps
pytest semantics — `passed`/`skipped` counts — clean):

```sql
CREATE TABLE IF NOT EXISTS check_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    tool TEXT NOT NULL,          -- "ruff" | "mypy" | "ruff-format"
    passed INTEGER,              -- 0/1 overall
    error_count INTEGER,
    offenders TEXT,              -- JSON array of "path:rule" strings
    duration_s REAL,
    command TEXT,
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_check_events_tool ON check_events(tool);
CREATE INDEX IF NOT EXISTS idx_check_events_passed ON check_events(passed);
```

Bump `SCHEMA_VERSION`. Add `"check_run"` to `_VALID_KINDS` and
`"check_run": "check_events"` to `_KIND_TABLE`.

### Producer wiring

- Add `record_check_event(db_path, *, ts, tool, passed, error_count=0,
  offenders=None, duration_s=None, command=None, head_sha=None, branch=None)` to
  `session_store.py`, modeled on `record_test_run_event()` (idempotent-free
  append; FTS-index `offenders`). Best-effort guarded.
- Wire the `/ll:check-code` command's gate invocations to call it per tool. Since
  the gates run as shell commands from the skill body, the cleanest write-point is
  a thin Python wrapper the skill invokes (e.g. `ll-check-code` mini-CLI or a
  `record` shim) that parses ruff/mypy output into `(error_count, offenders)`.
  - `ruff check --output-format json` and `mypy --output json`-style parsing give
    structured offender lists; fall back to exit-code-only when JSON is
    unavailable.

### Read API

- `history_reader.recent_check_events(tool=None, since=None, limit=50)`.
- `history_reader.check_pass_rate(tool, since=None)`.

### CLI surface

- `ll-session recent --kind check_run`.

## Acceptance Criteria

- Schema migration lands; `check_events` exists; `SCHEMA_VERSION` bumped.
- Running the `/ll:check-code` gates writes one row per tool with correct
  `passed` and `error_count`; a mypy failure lists offending files in `offenders`.
- Writes are best-effort: DB absent/locked never changes gate exit status.
- `ll-session recent --kind check_run` returns rows; FTS matches an offender path.
- Tests cover: clean run (all pass), ruff failure with offenders, mypy failure,
  format-check failure, graceful degradation.

## Implementation Steps

1. Schema migration for `check_events`; bump `SCHEMA_VERSION`.
2. Add `"check_run"` to `_VALID_KINDS` and `_KIND_TABLE`.
3. Implement `record_check_event()` in `session_store.py` (mirror
   `record_test_run_event`); export.
4. Add a Python write-point the `/ll:check-code` skill invokes per tool
   (parse ruff/mypy JSON output → `error_count` + `offenders`).
5. `history_reader.recent_check_events()` + `check_pass_rate()`.
6. CLI: `ll-session recent --kind check_run`.
7. Tests: `TestRecordCheckEvent`, `TestCheckSchema`, per-tool parse tests,
   graceful degradation.
8. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/API.md`,
   `docs/reference/CLI.md`; note in `.claude/CLAUDE.md` § Testing & CI Policy that
   gate results are now recorded.

## Sources

- `thoughts/history-db-expand-wiring.md` — §2 (test/gate results gap)
- EPIC-2457 review (2026-07-05) — item #3
- ENH-2459 / `record_test_run_event()` (`session_store.py:1171`) — the shape to
  generalize
- `.claude/CLAUDE.md` § Testing & CI Policy — the four-gate definition
- `skills/check-code/` (`/ll:check-code`) — gate invocation site

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `.claude/CLAUDE.md` | Testing & CI Policy (single local gate) |

## Status

**Open** | Created: 2026-07-05 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
