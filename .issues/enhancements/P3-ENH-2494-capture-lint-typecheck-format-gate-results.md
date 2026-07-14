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
decision_needed: false
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

**Scope covers the full gate family, not just the four core gates.** The same
`check_events` shape is the home for every other pass/fail CI gate the project
wraps under `python -m pytest` per the Testing & CI Policy — `ll-verify-docs`,
`ll-verify-skills`, `ll-verify-triggers`, `ll-verify-package-data`,
`ll-verify-design-tokens`, `ll-verify-skill-budget`, `ll-check-links`, and
`ll-deps validate`. They are all "did this gate stay green at this commit?"
signals that today vanish into CLI text. Because the `tool` column is free-form
TEXT, these need no new table — only additional producer call-sites and a wider
`tool` value domain. Ship the four core gates first, but design the table,
`recent_check_events()` filter, and `_VALID_KINDS` so the verify-*/check-links
family drops in without a second migration.

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

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store.py:102` — bump `SCHEMA_VERSION = 18` → `19`.
- `scripts/little_loops/session_store.py:104-130` — add `"check_run"` to `_VALID_KINDS` and `"check_run": "check_events"` to `_KIND_TABLE` (one line each).
- `scripts/little_loops/session_store.py` (in `_MIGRATIONS` list at 208-545, following the v18 entry at 521-544) — append v19 migration creating `check_events` + 2 indexes.
- `scripts/little_loops/session_store.py:1171` (next to `record_test_run_event()`) — add `record_check_event()` keyword-only API mirroring `record_test_run_event()`. Export via `__all__` (line 80).
- `scripts/little_loops/history_reader.py:138-162` (next to `RunEvent` dataclass) — add `CheckEvent` dataclass with `pass_rate` derived property.
- `scripts/little_loops/history_reader.py:562-598` (next to `recent_test_runs()`) — add `recent_check_events(tool=None, since=None, limit=50, db=DEFAULT_DB_PATH)`.
- `scripts/little_loops/history_reader.py:472-521` (alongside `summarize_skills()`) — add `check_pass_rate(tool, since=None)`.
- `scripts/little_loops/cli/session.py:88-106` — add `"check_run"` to `search --kind` choices list (line 91-103).
- `scripts/little_loops/cli/session.py:112-129` — add `"check_run"` to `recent --kind` choices list (line 114-129).
- `commands/check-code.md` (gates at lines 51-69 lint, 75-94 format, 99-117 types, 120-139 build) — replace inline shell with `ll-check-gates <mode>` per gate.
- `scripts/pyproject.toml` `[project.scripts]` section (around line 63-92) — register new `ll-check-gates` binary alongside the `ll-verify-*` family.
- `docs/ARCHITECTURE.md:614-633` — append v19 row to schema versions table.
- `docs/reference/API.md` — add `record_check_event` (around line 7025-7048) and `recent_check_events` (around line 6762-6774) sections.
- `docs/reference/CLI.md:2191-2299` — add `check_run` to `ll-session` `--kind` choices listing.
- `.claude/CLAUDE.md` § Testing & CI Policy — note that all four gate results are now recorded.

### Dependent Files (Callers / Importers)

- `scripts/little_loops/pytest_history_plugin.py:118-144` — the `LLHistoryPlugin._record()` model for `contextlib.suppress(Exception)`-wrapped best-effort writes; template for the new gate writer's caller-side guard.
- `scripts/little_loops/cli/docs.py:23, 119, 245, 321` — `main_verify_docs`, `main_verify_skill_budget`, `main_verify_skills`, `main_check_links` entry points wrapped in `cli_event_context()`. Each is a candidate call-site for adding `record_check_event()` after the result is known.
- `scripts/little_loops/cli/verify_triggers.py:583` — `main_verify_triggers`.
- `scripts/little_loops/cli/verify_package_data.py:241` — `main_verify_package_data`.
- `scripts/little_loops/cli/verify_design_tokens.py:206` — `main_verify_design_tokens`.
- `scripts/little_loops/cli/deps.py:74` — `main_deps validate` subcommand.

### Similar Patterns (template / pattern-finder findings)

- `scripts/little_loops/session_store.py:1171-1233` (`record_test_run_event()`) — **the EXACT template** to clone for `record_check_event()`. Same kwargs signature, same `_index()` FTS call (`session_store.py:705-718`), same `try/finally conn.close()` lifecycle, same `_index()` summary string.
- `scripts/little_loops/session_store.py:1041-1091` (`record_commit_event()`) — stricter best-effort pattern catching `sqlite3.Error` inside the function. Alternative template if the new writer needs harder guarantees than the test_run-side caller-only guard.
- `scripts/little_loops/history_reader.py:562-598` (`recent_test_runs()`) — **the EXACT template** for `recent_check_events()`. Uses `_connect_readonly()` (silent-failure) and `_row_to_dataclass()`; the new reader inherits silent-failure semantics for free.
- `scripts/little_loops/history_reader.py:472-521` (`summarize_skills()`) — template for `check_pass_rate(tool, since=None)`: GROUP BY aggregation with ISO-8601 lower bound on `ts`.

### Tests (existing model + new sites)

- `scripts/tests/test_session_store.py:3549-3620` (`class TestRecordTestRunEvent`) — **the EXACT class to clone** for `TestRecordCheckEvent` (round-trip + FTS + multi-row + `_bootstrap_schema_at(version)` upgrade assertion at line 3618).
- `scripts/tests/test_history_reader.py:1442-1522` — template for `recent_check_events` + `check_pass_rate` (lines 1442-1458) and the graceful-degradation test pattern (lines 1513-1522).
- `scripts/tests/test_ll_session.py:88-96` (`test_recent_subcommand_test_run_accepted`) — template for the `check_run` argparse choices test for both `recent --kind check_run` and `search --kind check_run`.
- `scripts/tests/test_ll_session.py:916-975` (`class TestSkillStatsAndNewKinds`) — `recent --kind check_run` row-output parity test.
- `scripts/tests/test_pytest_history_plugin.py:117` (`class TestSessionFinishWritesRow`) — best-effort producer test template; mirror as `test_checkcode_never_raises_on_broken_db` for the new gate writer.

## Proposed Solution

### Schema migration

Prefer a **new `check_events` table** over overloading `test_run_events` (keeps
pytest semantics — `passed`/`skipped` counts — clean):

```sql
CREATE TABLE IF NOT EXISTS check_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    tool TEXT NOT NULL,          -- "ruff" | "mypy" | "ruff-format" | "verify-docs" | "verify-skills" | "check-links" | "deps-validate" | ...
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against codebase patterns._

- **Migration shape** is established at `session_store.py:521-544` (v18 ENH-2459): `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS × 3`, idempotent re-apply, applied inside a `BEGIN IMMEDIATE` transaction in `_apply_migrations()` (`session_store.py:609-645`). Bumping `SCHEMA_VERSION = 18` → `19` (line 102) and appending one string to `_MIGRATIONS` (line 208-545) is the only required step on the schema side.
- **`_VALID_KINDS` / `_KIND_TABLE` extension** is a one-line-each addition (lines 104-130). Once added, the `recent()` generic dispatcher (`session_store.py:1268-1289`) routes `kind="check_run"` to the new table without code change — `recent(db, kind="check_run")` works out of the box.
- **`record_check_event()` signature** should mirror `record_test_run_event()` (line 1171-1233) exactly: keyword-only params after `db_path`, single `INSERT INTO ...`, one `_index()` FTS call with concatenated summary string, `commit()` + `close()`. **Best-effort guard lives at the caller** — the same `contextlib.suppress(Exception)` wrapper the pytest plugin uses at `pytest_history_plugin.py:118-120`. Do not wrap the function itself in try/except.
- **CLI argparse choices** are duplicated in `cli/session.py`: `search --kind` (line 91-103) and `recent --kind` (line 114-129). Both `choices` lists must add `"check_run"` — a single line edit satisfies the read-side contract.
- **`history_reader.recent_check_events()`** mirrors `recent_test_runs()` (`history_reader.py:562-598`): `_connect_readonly()` (silent-failure) + `ORDER BY ts DESC, id DESC` + `_row_to_dataclass()`. `check_pass_rate(tool, since=None)` parallels `summarize_skills()` (`history_reader.py:472-521`): GROUP BY aggregation with ISO-8601 lower bound on `ts`.
- **Subprocess + JSON parse tolerance** for `ruff --output-format=json` and `mypy --output=json` has no existing pattern in this repo. The established precedent is `session_store._call_llm_for_summary()` (`session_store.py:1995-2093`): catches every failure mode (timeout, missing binary, non-zero exit, JSON parse error, empty stdout) and returns a sentinel. The new ruff/mypy wrapper should adopt the same envelope-and-best-effort design — fall back to exit-code-only when JSON is unavailable.
- **Producer architecture decision** (single recommended path, no real alternative):
  - **Recommended**: replace inline shell in `commands/check-code.md` with `ll-check-gates <mode>` (a new `cli/check_gates.py` analog to `cli/docs.py`). Centralizes parsing, counting, and recording; the issue's Proposed Solution already implies this path ("thin Python wrapper the skill invokes").
  - **Reject**: inline `python -c "from little_loops.session_store import record_check_event; ..."` after each gate in `commands/check-code.md` — invasive to the prompt body, brittle JSON parsing inside heredocs.
- **`tool` domain is intentionally free-form** (TEXT column, no enum constraint). The `verify-docs` / `verify-skills` / `verify-skill-budget` / `verify-triggers` / `verify-package-data` / `verify-design-tokens` / `check-links` / `deps-validate` family shares the same column with no schema change — Acceptance Criterion #6 ("tool accepts a verify-*/check-links value … with no second migration") is satisfiable from the existing table design.
- **Test scaffolding is fully derivable**: `TestRecordTestRunEvent` (`test_session_store.py:3549-3620`) plus `TestReadResultsAndEdges` (`test_history_reader.py:1442-1522`) plus `test_recent_subcommand_test_run_accepted` (`test_ll_session.py:88-96`) cover all three families (writer, reader, CLI) — Implementation Step 7 has complete precedent in-tree.

## Acceptance Criteria

- Schema migration lands; `check_events` exists; `SCHEMA_VERSION` bumped.
- Running the `/ll:check-code` gates writes one row per tool with correct
  `passed` and `error_count`; a mypy failure lists offending files in `offenders`.
- Writes are best-effort: DB absent/locked never changes gate exit status.
- `ll-session recent --kind check_run` returns rows; FTS matches an offender path.
- Tests cover: clean run (all pass), ruff failure with offenders, mypy failure,
  format-check failure, graceful degradation.
- `tool` accepts a verify-*/check-links value (e.g. `verify-docs`) and the read
  API filters on it — proving the family generalizes with no second migration.

## Implementation Steps

1. Schema migration for `check_events`; bump `SCHEMA_VERSION`.
2. Add `"check_run"` to `_VALID_KINDS` and `_KIND_TABLE`.
3. Implement `record_check_event()` in `session_store.py` (mirror
   `record_test_run_event`); export.
4. Add a Python write-point the `/ll:check-code` skill invokes per tool
   (parse ruff/mypy JSON output → `error_count` + `offenders`). Keep the
   parse/record shim tool-agnostic so verify-*/check-links call-sites reuse it.
5. `history_reader.recent_check_events()` + `check_pass_rate()`.
6. CLI: `ll-session recent --kind check_run`.
7. Tests: `TestRecordCheckEvent`, `TestCheckSchema`, per-tool parse tests,
   graceful degradation.
8. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/API.md`,
   `docs/reference/CLI.md`; note in `.claude/CLAUDE.md` § Testing & CI Policy that
   gate results are now recorded.

### Codebase Research Findings

_Added by `/ll:refine-issue` — anchor references verified against `main`:_

- **Step 1** — append SQL string to `_MIGRATIONS` after the v18 entry at `scripts/little_loops/session_store.py:521-544`; bump `SCHEMA_VERSION = 18` → `19` at `session_store.py:102`. The migration block uses `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` (idempotent on re-apply), per the v18 precedent.
- **Step 2** — append `"check_run"` to `_VALID_KINDS` (`session_store.py:104-118`) and `"check_run": "check_events"` to `_KIND_TABLE` (`session_store.py:119-130`). No `recent()` change needed at line 1268 — the dispatcher is data-driven from the map.
- **Step 3** — place `record_check_event()` next to `record_test_run_event()` at `scripts/little_loops/session_store.py:1171`. Mirror the kwargs signature exactly (keyword-only after `db_path`); index a concatenated summary string via `_index()` (`session_store.py:705-718`); idempotent-free append (no `INSERT OR IGNORE`); propagate sqlite errors and rely on the caller's `contextlib.suppress(Exception)` guard. Export via `__all__` (line 80).
- **Step 4** — add `scripts/little_loops/cli/check_gates.py` (new file, analogous to `cli/docs.py`) exporting `main_check_gates`. Register in `scripts/pyproject.toml` `[project.scripts]` (sibling of `ll-verify-docs` at line 63). Subprocesses each gate with `--output-format=json` (ruff) or `--output=json` (mypy) or exit-code-only (`ruff format --check`), parses into `(tool, passed, error_count, offenders)`, then calls `record_check_event()`. Rewrite the four gate blocks in `commands/check-code.md` (lines 51-69 lint, 75-94 format, 99-117 types, 120-139 build) to invoke `ll-check-gates <mode>` instead of raw shell. Each call is best-effort guarded with the `pytest_history_plugin.py:118-120` `contextlib.suppress(Exception)` pattern.
- **Step 5** — add `CheckEvent` dataclass next to `RunEvent` (`scripts/little_loops/history_reader.py:138-162`). Add `recent_check_events(tool=None, since=None, limit=50, db=DEFAULT_DB_PATH)` next to `recent_test_runs()` at line 562. Add `check_pass_rate(tool, since=None)` next to `summarize_skills()` at line 472.
- **Step 6** — add `"check_run"` to BOTH `search --kind` choices (`cli/session.py:91-103`) AND `recent --kind` choices (`cli/session.py:114-129`). The two `choices` lists are duplicated and both must be updated.
- **Step 7** — clone `TestRecordTestRunEvent` (`scripts/tests/test_session_store.py:3549-3620`) → `TestRecordCheckEvent`; add `TestCheckSchema` covering `_bootstrap_schema_at(18)` followed by `ensure_db()` and asserting `check_events` table exists. Clone `TestReadResultsAndEdges` (`scripts/tests/test_history_reader.py:1442-1522`) → add tests for `recent_check_events` + `check_pass_rate` + missing-DB graceful-degradation. Add `test_check_run_kind_in_argparse` next to `test_recent_subcommand_test_run_accepted` at `scripts/tests/test_ll_session.py:88-96`. Add `test_checkcode_never_raises_on_broken_db` mirroring `class TestSessionFinishWritesRow` at `scripts/tests/test_pytest_history_plugin.py:117`.
- **Step 8** — append v19 row to schema versions table at `docs/ARCHITECTURE.md:614-633`. Mirror API docs for `record_check_event` (after `record_test_run_event` at `docs/reference/API.md:7025-7048`) and `recent_check_events` (after `recent_test_runs` at `docs/reference/API.md:6762-6774`). Update `docs/reference/CLI.md:2191-2299` `--kind` choices listing. Update `.claude/CLAUDE.md` § Testing & CI Policy to note gate results are now recorded.

## Sources

- `thoughts/history-db-expand-wiring.md` — §2 (test/gate results gap)
- EPIC-2457 review (2026-07-05) — item #3
- ENH-2459 / `record_test_run_event()` (`session_store.py:1171`) — the shape to
  generalize
- `.claude/CLAUDE.md` § Testing & CI Policy — the four-gate definition
- `skills/ll-check-code/` (`/ll:check-code`) — gate invocation site

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `.claude/CLAUDE.md` | Testing & CI Policy (single local gate) |

## Status

**Open** | Created: 2026-07-05 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot ("bump
`SCHEMA_VERSION = 18` → `19`"). At least ten other active EPIC-2457 siblings
(ENH-2463, ENH-2464, ENH-2465, ENH-2492, ENH-2493, ENH-2495, ENH-2496,
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

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-14T00:23:48 - `bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
- `/ll:refine-issue` - 2026-07-07T00:50:28 - `9bf8990b-8daf-440e-9ca6-abe848329070.jsonl`
- audit - 2026-07-06 - Corrected skill path in Sources: the skill directory is `skills/ll-check-code/`, not `skills/check-code/`. Confirmed no `ll-check-code` console script exists in `scripts/pyproject.toml` (the "skill-driven, no binary" premise holds).
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
