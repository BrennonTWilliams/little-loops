---
id: ENH-2494
title: Capture lint/typecheck/format gate results into history.db
type: ENH
priority: P3
status: cancelled
discovered_date: 2026-07-05
captured_at: '2026-07-05T00:00:00Z'
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

## Architectural Note — direct-write is primary (ARCHITECTURE-144 scope)

ARCHITECTURE-144 (`.ll/decisions.yaml`, ENH-2581) named this issue among those
"turned into event_type parser tasks over raw_events." That clause is scoped by a
later project decision (see `.ll/decisions.d/`): the parser reframe applies only
to fields sourced from the 5 JSONL-ingested `raw_events` kinds. The gate commands
(`ruff`, `mypy`, `ruff format`, the `ll-verify-*` family) appear as Bash
`tool_events` **only when run inside a Claude session**; runs from a terminal, a
pre-commit hook, or `/ll:check-code` outside a session never touch the transcript,
and error counts / offending files would have to be scraped from captured stdout
per-tool. Therefore **direct-write (`record_check_event`) stays the primary
producer**. An optional `_backfill_check_events` parser over `tool_events` (keyed
on command basename) may be added later as *secondary enrichment*, not a
replacement. This is a documented, justified pattern deviation, mirroring
ENH-2507.

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

### Wiring Pass Additions (`/ll:wire-issue` 2026-07-16)

_Wiring pass added by `/ll:wire-issue`:_

**Additional Files to Modify (not in the original Integration Map):**

- `scripts/little_loops/session_store.py:3304-3329` — both `_EXPORT_TABLE_MAP` AND `_EXPORT_DEFAULT_TABLES` need `"check_run_event"` (NOT `"check_run"`) added. The original Integration Map listed `_VALID_KINDS` / `_KIND_TABLE` but missed the parallel export-map pair that `ll-session export` reads. Mirrors the ENH-2461 finding at `.issues/enhancements/P3-ENH-2461-...md:378` which caught the same pair-miss post-merge.
- `scripts/little_loops/observability/schema.py:502-505` + line 626 (`DES_VARIANTS` tuple) — register new `CheckEventVariant` (`type: Literal["check_event"] = "check_event"`) per the precedent at `TestRunEventVariant`. The DES registry comment claims "every variant corresponds to a `record_*` writer site" — without this entry the registry becomes inaccurate.
- `commands/check-code.md:5` (frontmatter `allowed-tools`) — extend the whitelist from `Bash(ruff:*, mypy:*, python:*, ...)` to also include `Bash(ll-check-gates:*)`. Without this the model falls back to inline shell on permission denials.
- `commands/help.md:299` — add `ll-check-gates <mode>` bullet to the commands listing.
- `scripts/little_loops/worktree_utils.py:465-481` (`verify_epic_branch_before_merge`) — best-effort `record_check_event()` call after each `subprocess.run` of `test_cmd`/`lint_cmd` per worktree. Fills the "did this worktree pass lint/typecheck at merge time?" query.
- `scripts/little_loops/parallel/orchestrator.py:1308-1345` — verify-gate integration path; propagates per-worktree `record_check_event()` calls from `worktree_utils.verify_epic_branch_before_merge()`.
- `docs/guides/HISTORY_SESSION_GUIDE.md:41, 72, 96, 170` — schema versions table ends at v20; `--kind` enumeration ends at `usage`; "What Gets Recorded" table needs v21 row + `check_run` kind entry + `check_events` row.
- `CHANGELOG.md` — add entry under NEXT concrete version section (per user pref: no `[Unreleased]`; promote to `## [X.Y.Z] - DATE` during release prep).
- `commands/find-dead-code.md:30-37` — runs direct `ruff check --select F401` and `--select F841`. **Optional**: extend to invoke `ll-check-gates ruff` so the dead-code search's ruff invocations are also captured.

**Additional Loop YAMLs that run gates (per AC #6 free-form-tool spirit, not required for AC #1-5):**

- `scripts/little_loops/loops/auto-refine-and-implement.yaml:340-457` — `verify` state runs `test_cmd` + `lint_cmd` per worktree. Best-effort `record_check_event()` call after each gate gives per-tool breakdown (the existing `verify_verdict` field added by ENH-2601 is a single-state aggregate).
- `scripts/little_loops/loops/evaluation-quality.yaml:49-54` — runs `ruff check scripts/` and writes to `${context.run_dir}/eval-lint-results.txt`. Wire `record_check_event(tool="ruff", ...)` to also persist the same result into `history.db`.
- `scripts/little_loops/loops/oracles/code-run-gate.yaml:54, 63, 134-150, 194-220, 275-290` — defines `test_cmd` and `lint_cmd` as explicit oracle gate states. Wire `record_check_event()` per gate invocation.

**Additional Dependent Files (sibling templates + new call-sites):**

- `scripts/little_loops/hooks/post_commit.py:50, 73` — sibling commit-event writer; confirms the pattern of `_post_commit_*` hook-side writers that may need a sibling `_post_check_*` hook if gate recording is later wired into hook lifecycle (not required for this issue).
- `scripts/little_loops/cli/verify_decisions.py:88` — `main_verify_decisions` entry point wrapped in `cli_event_context()`. Per AC #6 ("`tool` accepts a verify-*/check-links value"), this is a required `record_check_event(tool="verify-decisions", ...)` writer call site.
- `scripts/little_loops/cli/verify_des_audit.py:106` — `main_verify_des_audit` (DES variant registration check). Per AC #6.
- `scripts/little_loops/cli/verify_kinds.py:52` — `main_verify_kinds`. Per AC #6. **CRITICAL**: this is the gate that silently catches a missing `check_events` table registration (test_verify_kinds.py:18-23). Adding `record_check_event(tool="verify-kinds", ...)` here closes the loop.

**Additional Documentation references (file:line):**

- `docs/development/TESTING.md:1008-1010` — gate summary block. Append: "All four gate results are persisted to `.ll/history.db` (`check_events` table) by `ll-check-gates`."
- `docs/development/TROUBLESHOOTING.md:82-88, 946-948` — references mypy install + pytest gate; cross-reference `ll-session recent --kind check_run` for triage.
- `docs/development/MERGE-COORDINATOR.md:156-163` — partial-failure and merge verification gates; append note that per-worktree gate results now land in `check_events`.
- `docs/reference/API.md:7275, 7279` — `SCHEMA_VERSION` literal ("Current schema version: **19**") needs bump to **21** in both sites (live is 20; new migration is 21).
- `docs/ARCHITECTURE.md:723, 748` — sequence diagram bootstrap label "v1–v20" appears twice; both need bump to "v1–v21".
- `docs/reference/CLI.md:2845` — generated CLI reference mentions CI/gate; append `check_run` to the `--kind` choices listing.
- `CONTRIBUTING.md:407` — documents `python -m pytest scripts/tests/` as project CI; cross-reference `check_events` table.
- `specs/harness-optimize-rubric.md:400` — references pytest CI gate; worth a note that gate results are now persisted.

**Additional Tests to add (precedents not in the issue's Tests subsection):**

- `scripts/tests/test_cli_docs.py:17-192` (`TestMainVerifyDocs`), 195-355 (`TestMainCheckLinks`), 358-492 (`TestMainVerifySkillBudget`), 495-588 (`TestMainVerifySkills`) — canonical analog for new `scripts/tests/test_check_gates.py`. Clone all four `TestMain*` classes; they use the triple-mock pattern (`patch("sys.argv", [...])` + `patch("little_loops.X.run_gate", ...)` + `patch("builtins.print")`).
- `scripts/tests/test_cli_harness.py:42-44` (`_make_completed()`) — canonical "subprocess.run returns CompletedProcess" helper. Reuse for `TestCheckGatesSubprocessWrappers` to mock ruff/mypy/ruff-format subprocess invocations.
- `scripts/tests/test_cli_harness.py:223-273` — representative subprocess mock patterns: `test_skill_exit_code_pass` (clean exit), `test_skill_timeout_returns_2` (TimeoutExpired), `test_skill_binary_not_found_returns_2` (FileNotFoundError).
- `scripts/tests/test_action.py:365-421` (`TestCmdCapabilities`) — closest pattern for parsing subprocess stdout as JSON via `json.loads(capsys.readouterr().out)`. Adopt for `TestCheckGatesRuffJsonParse` + `TestCheckGatesMypyJsonParse`.
- `scripts/tests/test_verify_kinds.py:18-23` (`test_clean_state_returns_zero`) — gate that silently catches missing `check_events` registration. The negative-control test at lines 25-33 (`test_mystery_events_caught`) would fire on a regression.
- `scripts/tests/test_session_store.py:3221-3243` (`TestSchemaV20UsageEvents.test_usage_events_columns`) — `PRAGMA table_info` + column-set assertion pattern. Clone → `TestCheckSchemaV21.test_check_events_columns`.
- `scripts/tests/test_session_store.py:3674-3685` (`TestSchemaV13.test_retirement_fingerprint_index_exists`) — index existence assertion pattern. Clone → `TestCheckSchemaV21.test_check_events_indexes_exist`.
- `scripts/tests/test_session_store.py:4049-4070` (`TestSchemaV16IssueSessionId.test_session_id_index_exists_and_is_used`) — `EXPLAIN QUERY PLAN` pattern for behavioral validation of the new indexes.

**Tests that will break — none.** Verified via Grep: no test asserts `len(VALID_KINDS)`, `len(_KIND_TABLE)`, or `len(_MIGRATIONS)`. `test_every_valid_kind_has_a_kind_table_entry` (line 3412-3413) uses set equality — adding `"check_run"` to both sides keeps it balanced. `SCHEMA_VERSION` literals at lines 3658, 3699, 3952, etc. reference the constant (not its numeric value) and silently update to 21.

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

### Wiring Phase (added by `/ll:wire-issue` 2026-07-16)

_These touchpoints were identified by wiring analysis and must be included in the implementation. They are not duplicates of the eight steps above — they are wiring-side couplings the original Integration Map missed._

9. **Add `check_run_event` to the export-map pair** at `scripts/little_loops/session_store.py:3304-3329` — both `_EXPORT_TABLE_MAP` AND `_EXPORT_DEFAULT_TABLES` need the new entry (NOT `_KIND_TABLE`). Without this, `ll-session export` skips the new table until the user passes `--tables check_run_event` explicitly. Mirrors the ENH-2461 finding at line 378.

10. **Register `CheckEventVariant` in the DES registry** at `scripts/little_loops/observability/schema.py:502-505` (variant dataclass) and line 626 (`DES_VARIANTS` tuple). Follow the `TestRunEventVariant` precedent. Without this, `ll-verify-des-audit` does not recognize `record_check_event` as a registered event type.

11. **Wire per-worktree verify-gate recording** in `scripts/little_loops/worktree_utils.py:465-481` (`verify_epic_branch_before_merge`) — add best-effort `record_check_event()` calls after each `subprocess.run` of `test_cmd`/`lint_cmd`. Then propagate through `scripts/little_loops/parallel/orchestrator.py:1308-1345` (`_verify_epic_branch_before_merge`) — the orchestrator just calls the worktree helper, so the wiring lives at one site.

12. **Add `ll-check-gates` to the commands/help bullet list** at `commands/help.md:299`. The help command enumerates CLI binaries; a new binary must be added there.

13. **Extend `commands/check-code.md` `allowed-tools` whitelist** at line 5 to include `Bash(ll-check-gates:*)`. Without this, the model falls back to inline shell on permission denials when rewriting the gate blocks.

14. **Update additional doc surfaces** not in Step 8:
    - `docs/reference/API.md:7275, 7279` — bump SCHEMA_VERSION literal from "19" to "21" in both sites.
    - `docs/ARCHITECTURE.md:723, 748` — bump sequence diagram "v1–v20" to "v1–v21" in both places.
    - `docs/guides/HISTORY_SESSION_GUIDE.md:41, 72, 96, 170` — schema versions table, `--kind` enumeration, "What Gets Recorded" table all need v21 row + `check_run` + `check_events`.
    - `docs/development/TESTING.md:1008-1010` — append note that all four gates now land in `check_events`.
    - `docs/development/MERGE-COORDINATOR.md:156-163` — note per-worktree gate recording.
    - `CHANGELOG.md` — entry under NEXT concrete version section (no `[Unreleased]` per project pref).

15. **Wire loop YAML per-worktree verify states** (optional AC #6 spirit):
    - `scripts/little_loops/loops/auto-refine-and-implement.yaml:340-457` — `verify` state.
    - `scripts/little_loops/loops/evaluation-quality.yaml:49-54` — `ruff check scripts/` capture.
    - `scripts/little_loops/loops/oracles/code-run-gate.yaml:54, 63, 134-150, 194-220, 275-290` — explicit test+lint oracle gates.

16. **Add `record_check_event()` calls inside the verify-* CLI entry points** per AC #6 ("`tool` accepts a verify-*/check-links value"):
    - `scripts/little_loops/cli/verify_decisions.py:88` — `main_verify_decisions` (tool="verify-decisions").
    - `scripts/little_loops/cli/verify_des_audit.py:106` — `main_verify_des_audit` (tool="verify-des-audit").
    - `scripts/little_loops/cli/verify_kinds.py:52` — `main_verify_kinds` (tool="verify-kinds"). **Critical**: this is the gate that silently catches missing `check_events` registration in the table-vs-kind consistency check.
    Each call wrapped in `contextlib.suppress(Exception)` per the `pytest_history_plugin.py:118-120` template.

17. **Add `commands/find-dead-code.md:30-37` to the gate-recording surface** (optional): replace the two direct `ruff check --select F401` / `--select F841` invocations with `ll-check-gates ruff` so the dead-code search's ruff invocations are captured.

### Anchor Drift Audit (re-verified at /ll:refine-issue 2026-07-16)

_Added by `/ll:refine-issue` — line numbers from the prior refine pass (2026-07-07) have drifted downstream due to v19 (`raw_events`) and v20 (`usage_events`) landing. Read the live source rather than trusting these literals — the slot to bump is no longer `SCHEMA_VERSION = 18 → 19`, the pattern templates are at different line numbers, and one symbol name is wrong._

| Anchor (issue text) | Verified live location | Drift | Notes |
|---|---|---|---|
| `session_store.py:102` (`SCHEMA_VERSION = 18`) | `session_store.py:207` (`SCHEMA_VERSION = 20`) | +105 lines | **Symbol correct, value stale**. Live `SCHEMA_VERSION = 20`; new migration is **v21**, not v19. See Scope Boundary (lines 250–264) for the multi-claimant note — ten sibling EPIC-2457 issues all reference `18 → 19`; live next-available slot is 21. |
| `session_store.py:104-130` (`_VALID_KINDS` + `_KIND_TABLE`) | `session_store.py:209-222` (`VALID_KINDS`); `session_store.py:223-236` (`_KIND_TABLE`) | +105 lines | **Symbol name wrong**. Live export is `VALID_KINDS` (no leading underscore) at line 209. Only `_KIND_TABLE` is module-private (line 223). Adding `"check_run"` to `VALID_KINDS` automatically propagates to the CLI `choices=list(VALID_KINDS)` lists in `cli/session.py` (lines 99–110 and 112–130) — no separate CLI edit needed beyond ensuring the constant itself is updated. |
| `session_store.py:705-718` (`_index()` FTS call) | `session_store.py:890-903` | +185 lines | Function body unchanged: still takes `(conn, *, content, kind, ref, anchor, ts)` and writes one row to `search_index`. The 512-char truncation happens at the call site (e.g. line 1403–1406 for test_run), not inside `_index()`. |
| `session_store.py:1041-1091` (`record_commit_event()`) | `session_store.py:1222-1272` | +181 lines | Body structurally unchanged: `INSERT OR IGNORE` on `commit_sha UNIQUE`, conditional `_index()` only when `cursor.rowcount`, returns `bool`. **It is not "stricter best-effort" per se** — it is structurally different from `record_test_run_event()` because the same commit_sha can be reported multiple times across hooks and `_backfill_commit_events()` (line 1275). |
| `session_store.py:1171-1233` (`record_test_run_event()`) | `session_store.py:1352-1414` | +181 lines | Body structurally unchanged: keyword-only after `db_path`, plain `INSERT` (no `OR IGNORE`), single `_index()` FTS call. **The function body does NOT wrap itself in try/except** — SQLite errors propagate. Best-effort comes from caller-side `contextlib.suppress(Exception)` (e.g. `pytest_history_plugin.py:120`). |
| `session_store.py:705-718` and `_call_llm_for_summary()` (line 1995-2093) | `_call_llm_for_summary()` envelope parser at `session_store.py:2312-2347` | +252 lines | The canonical "subprocess + JSON parse with graceful degradation" template. Catches `json.JSONDecodeError`, falls back to last-non-empty JSONL line, returns sentinel on every failure. Adopt this envelope for `ll-check-gates` ruff/mypy JSON parsing. |
| `history_reader.py:138-162` (`RunEvent` dataclass) | `history_reader.py:138-161` | matches | Correct (within 1 line). Place `CheckEvent` directly after this. |
| `history_reader.py:472-521` (`summarize_skills()`) | `history_reader.py:497-546` | +25 lines | `_connect_readonly()` is the silent-failure open. ISO-8601 lower bound on `ts` confirmed. |
| `history_reader.py:562-598` (`recent_test_runs()`) | `history_reader.py:689` | +127 lines | Function body unchanged: `_connect_readonly()` → `SELECT * ... ORDER BY ts DESC, id DESC LIMIT ?` → `_row_to_dataclass()`. |
| `cli/session.py:91-103` and `cli/session.py:114-129` | `cli/session.py:99-110` (`search_parser`); `cli/session.py:112-130` (`recent_parser`) | +8 lines | Both subparsers use `choices=list(VALID_KINDS)` — derived from the constant, so updating `VALID_KINDS` in `session_store.py` automatically extends both argparse lists. **Do not hand-edit either `choices` literal** — it will be replaced on the next `VALID_KINDS` update. |
| `cli/session.py:1181` (export in `__all__`) | `cli/session.py` — `__all__` line not yet verified | not verified | Low risk — the issue references the `__all__` line in `session_store.py` (line 80) where `record_commit_event` and `record_test_run_event` are exported. New `record_check_event` must be added there too. |
| `cli/docs.py:23, 119, 245, 321` (`cli_event_context` wraps) | `cli/docs.py:23, 119, 245, 321` — and `cli_event_context()` is defined at `session_store.py:1054-1091` | partial | The four wraps are at the cited `cli/docs.py` lines. `cli_event_context()` itself has drifted to `session_store.py:1054-1091` (was 1181). |
| `commands/check-code.md:51-69, 75-94, 99-117, 120-139` (gates) | `commands/check-code.md` frontmatter `allowed-tools` whitelists `Bash(ruff:*, mypy:*, python:*, npm:*, cargo:*, go:*, dotnet:*, mvn:*, ./gradlew:*, make:*)` — direct binary invocation | matches | When rewriting the four gate blocks to call `ll-check-gates <mode>`, the `allowed-tools` whitelist must be extended to `Bash(ll-check-gates:*)`. Otherwise the model will fall back to inline shell on permission denials. |
| `pyproject.toml:63-92` (`[project.scripts]`) | `pyproject.toml:51-95` | matches | Add `ll-check-gates = "little_loops.cli:main_check_gates"` near line 89 (sibling of `ll-verify-design-tokens`). Also re-export `main_check_gates` from `cli/__init__.py` (the import statement lives at line 86 and the export at line 126). |
| `docs/ARCHITECTURE.md:614-633` (schema versions table) | `docs/ARCHITECTURE.md:676` (v18 entry); note at line 2467 about test_run tables | +62 lines | Add the new entry for `check_events` next to the v18 row. |
| `docs/reference/API.md:7025-7048` (`record_test_run_event`); `:6762-6774` (`recent_test_runs`); `:7280` (`VALID_KINDS`) | `docs/reference/API.md:7366` (`record_test_run_event`); `:7065` (`recent_test_runs`); `:7280` (`VALID_KINDS`) | mixed | `recent_test_runs` is at line 7065 (issue says 6762-6774, drift −297); `record_test_run_event` is at line 7366 (issue says 7025-7048, drift −341). `VALID_KINDS` at line 7280 matches. |
| `docs/reference/CLI.md:2191-2299` | `docs/reference/CLI.md:2427, 2435` (`--kind` choices); `:2501` (`--tables`); `:2511` (example) | +236 lines | Choices list documented at 2427 and 2435. Append `check_run` to both listings. |
| `test_session_store.py:3549-3620` (`TestRecordTestRunEvent`) | `test_session_store.py:4362-4432` | +813 lines | Class body unchanged in shape: `test_roundtrip` + `test_failing_names_fts_searchable` + `test_multiple_runs_are_distinct_rows` + `test_v14_db_upgrades_gains_test_run_events`. Clone → `TestRecordCheckEvent` here. The `_bootstrap_schema_at(db, version)` helper at `test_session_store.py:3891-3911` is the upgrade test scaffold. |
| `test_history_reader.py:1442-1522` (`TestReadResultsAndEdges`) | `test_history_reader.py:1442-1458` (graceful degradation); `recent_test_runs_and_pass_rate` at line 1459 | matches | Both blocks live in this range. Use the graceful-degradation test (lines 1513–1522) as the missing-DB pattern. |
| `test_ll_session.py:88-96` (`test_recent_subcommand_test_run_accepted`) | `test_ll_session.py:88-96` | matches | `choices=list(VALID_KINDS)`-derived. Add `test_check_run_kind_in_argparse` here. |
| `test_pytest_history_plugin.py:117` (`TestSessionFinishWritesRow`) | `test_pytest_history_plugin.py:116` | matches | Use this class as the best-effort contract template for `test_checkcode_never_raises_on_broken_db`. |

### Additional Patterns Discovered (not in prior refine pass)

_Added by `/ll:refine-issue` — surfaced during the 2026-07-16 re-verification:_

- **`recent()` dispatcher is purely data-driven** (`session_store.py:1462-1484`): `if kind not in VALID_KINDS: raise ValueError(...); table = _KIND_TABLE[kind]; conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,))`. Once both `VALID_KINDS` and `_KIND_TABLE` are extended, `recent(db, kind="check_run")` works without any code change to `recent()` itself. **Step 2 of Implementation Steps is the ONLY place the dispatcher needs to be touched.**
- **`fts_phrase()` at `session_store.py:1422-1431`** wraps queries in escaped double-quotes (BUG-2651) so hyphenated file paths (e.g. `scripts/little_loops/foo.py`) match literally rather than being parsed as FTS5 column filters. The new `recent_check_events()` should accept the same query phrasing — or document that hyphenated offenders must be quoted at the CLI.
- **`skill_event_context()` at `session_store.py:1108-1181`** is a stronger envelope-and-best-effort template than the bare `pytest_history_plugin` `contextlib.suppress(Exception)` pattern. Documented as the "graceful degradation" contract per EPIC-1707. Use this if the gate-recording path needs harder guarantees than caller-only suppression (e.g. an `ll-check-gates` subprocess that writes inside a critical section).
- **`_call_llm_for_summary()` envelope parser at `session_store.py:2312-2347`** is the canonical subprocess + JSON-parse pattern: catches `json.JSONDecodeError`, falls back to last-non-empty JSONL line, returns a sentinel on every failure (timeout, missing binary, non-zero exit, empty stdout, JSON parse error). The `ll-check-gates <mode>` wrapper should adopt this envelope for `ruff --output-format=json` and `mypy --output=json` parsing.
- **ruff `--output-format=json` shape**: top-level JSON array of violation objects; each carries `code` (e.g. `E501`, `F401`), `message`, `filename`, `location.row/column`, `end_location.row/column`, `fix` (nullable), `noqa_rule` (nullable). Mapping: `error_count = len(parsed_array)`; `offenders = [f"{item['filename']}:{item['code']}" for item in parsed_array]`; `passed = exit_code == 0`.
- **mypy `--output=json` shape**: top-level JSON object keyed by `{file_path: [diagnostics...]}`, with `errors` summary list as a sibling key. Each diagnostic carries `file`, `line`, `column`, `severity` (`error`/`warning`/`note`), `message`, `code` (e.g. `union-attr`, `arg-type`, nullable), `hint` (nullable), `note_id` (nullable). Exit code 0 = clean; 1 = type errors found; 2 = mypy crashed/invalid config. Mapping: `error_count = sum(len(v) for v in diagnostics_per_file.values() if severity == "error")`; `offenders = [f"{diag['file']}:{diag['code']}" for diag in error_diagnostics]`; `passed = exit_code == 0`.
- **`ruff format --check`** does NOT emit JSON — exit-code-only mode. Mapping: `passed = exit_code == 0`; `error_count = 0 or 1` based on stdout "would reformat:" list (parse whitespace-split filenames).
- **`commands/check-code.md` `allowed-tools` whitelist** at the frontmatter whitelists `Bash(ruff:*, mypy:*, python:*, npm:*, cargo:*, go:*, dotnet:*, mvn:*, ./gradlew:*, make:*)` — direct binary invocation by the model. When rewriting gate blocks to call `ll-check-gates <mode>`, also extend the whitelist to `Bash(ll-check-gates:*)` so the model can invoke the wrapper.
- **Producer call-site coverage for the verify-* family**: `scripts/little_loops/cli/docs.py:15, 111, 237, 313` (`main_verify_docs`, `main_verify_skill_budget`, `main_verify_skills`, `main_check_links`), `scripts/little_loops/cli/verify_design_tokens.py:206`, `scripts/little_loops/cli/verify_package_data.py:241`, `scripts/little_loops/cli/verify_triggers.py:583`, `scripts/little_loops/cli/verify_decisions.py:88`, `scripts/little_loops/cli/verify_kinds.py:52`, `scripts/little_loops/cli/verify_des_audit.py:106`. Each is wrapped in `cli_event_context(DEFAULT_DB_PATH, "ll-verify-…", sys.argv[1:])`. Adding `record_check_event()` calls inside these wraps (after the result is known) satisfies the "free-form `tool` column accepts verify-*/check-links values" Acceptance Criterion #6 without a second migration.

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

**Cancelled** | Created: 2026-07-05 | Priority: P3

**Won't Do** (2026-07-20): Closed by user request without implementation.

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

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The Implementation Steps
instruct editing both `search_parser` and `recent_parser` `choices=[...]`
lists in `cli/session.py`. This premise is stale: both argparse subparsers
derive `choices=list(VALID_KINDS)` from the single source of truth at
`session_store.py` lines 104–118, so adding `"check_run"` only to
`_VALID_KINDS` propagates to both subparsers. No duplicate `choices=[...]`
edit is required.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-17T13:57:02 - `ff04da3c-210f-4c14-9967-762b390ae67c.jsonl`
- `/ll:wire-issue` - 2026-07-16T21:57:01 - `dc84b178-4ea7-48fc-aee7-d87810974053.jsonl`
- `/ll:refine-issue` - 2026-07-16T15:11:17 - `5e36f3af-c830-4cfb-9bdd-a2ad95303a4c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-14T00:23:48 - `bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
- `/ll:refine-issue` - 2026-07-07T00:50:28 - `9bf8990b-8daf-440e-9ca6-abe848329070.jsonl`
- audit - 2026-07-06 - Corrected skill path in Sources: the skill directory is `skills/ll-check-code/`, not `skills/check-code/`. Confirmed no `ll-check-code` console script exists in `scripts/pyproject.toml` (the "skill-driven, no binary" premise holds).
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
