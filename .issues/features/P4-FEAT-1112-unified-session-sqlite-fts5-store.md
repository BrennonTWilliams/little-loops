---
id: FEAT-1112
type: FEAT
priority: P4
status: done
discovered_date: 2026-04-15
completed_at: 2026-05-23T00:08:25Z
discovered_by: capture-issue
relates_to:
- FEAT-1113
- ENH-1114
- ENH-1619
- ENH-1621
labels:
- feature
- captured
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
implementation_order_risk: true
---

# FEAT-1112: Unified Session Store (SQLite + FTS5)

## Summary

Replace the scattered JSON/markdown stores behind `analyze-loop`, `analyze-history`, and `analyze-workflows` with a single per-project SQLite + FTS5 database that indexes tool events, file modifications, git operations, issue transitions, and user corrections.

## Motivation

Today little-loops persists session/loop/history state in multiple disconnected places: FSM loop state JSON, issue frontmatter, session JSONLs under `~/.claude/projects/`, and ad-hoc files under `.ll/`. Each `/ll:analyze-*` skill re-parses these from scratch, which is slow, expensive on context, and makes cross-cutting queries ("which loops failed on issues touching file X?") impractical.

Context-mode (github.com/mksglu/context-mode) uses a per-project SQLite + FTS5 database with BM25 ranking and Reciprocal Rank Fusion to answer queries like this in milliseconds, and makes compaction-time reconstruction of working state feasible.

## Current Behavior

- Loop runs: JSON under `.ll/loops/` per-run
- Issue history: markdown frontmatter + `ll-history` scrapes completed/ dir
- Workflow patterns: one-shot extraction via `ll-messages` + `ll-workflows`
- Analysis skills each re-parse their source data every invocation
- No cross-index between loops, issues, messages, and git operations

## Expected Behavior

- New per-project SQLite DB at `.ll/session.db` (gitignored) with FTS5 tables for:
  - `tool_events` (tool name, args hash, result size, timestamp, session id)
  - `file_events` (path, op, session id, issue id, git sha)
  - `issue_events` (issue id, transition, discovered_by, timestamp)
  - `loop_events` (loop name, state, transition, rate-limit retries)
  - `user_corrections` (captured from feedback memory + explicit markers)
- Ingestion via a lightweight daemon or SessionStart/PostToolUse hook that writes events as they happen
- New `ll-session` CLI wraps queries (`ll-session search`, `ll-session recent --kind=loop`)
- `/ll:analyze-loop`, `/ll:analyze-history`, `/ll:analyze-workflows` refactored to query the DB instead of re-parsing source files
- Schema documented in `docs/reference/`; migrations via a version column

## Use Case

**Who**: Little-loops operator or developer maintaining automation loops

**Context**: After running several `/ll:analyze-*` skills across multiple sessions, the operator needs to answer cross-cutting questions like "which loops failed on issues touching file X?" or "what were the user corrections from the last sprint?"

**Goal**: Query a single indexed database instead of re-parsing scattered JSON/markdown files for each analysis invocation

**Outcome**: Sub-second answers to cross-cutting queries via FTS5 full-text search with BM25 ranking, and compaction-time reconstruction of working state from indexed events

## Acceptance Criteria

- `.ll/session.db` created on first run; schema migration framework in place
- Backfill script populates from existing `.ll/loops/`, `.issues/completed/`, and session JSONLs
- At least two analyze-* skills migrated to query the DB
- `ll-session search --fts "<query>"` returns ranked results with file:line anchors
- `.gitignore` updated
- Unit tests for ingestion, migration, and query paths

## API/Interface

### New CLI: `ll-session`

```bash
ll-session search --fts "<query>"    # Full-text search with ranked results
ll-session recent --kind=<kind>      # Recent events filtered by kind (loop, issue, file, tool)
```

### Database Schema

SQLite database at `.ll/session.db` with FTS5 virtual tables:

- `tool_events` — tool name, args hash, result size, timestamp, session id, bytes_in, bytes_out, cache_hit
- `file_events` — path, op, session id, issue id, git sha
- `issue_events` — issue id, transition, discovered_by, timestamp
- `loop_events` — loop name, state, transition, rate-limit retries
- `user_corrections` — captured from feedback memory + explicit markers

Schema migrations managed via a version column. `bytes_in`, `bytes_out`, and `cache_hit` columns reserved in initial `tool_events` schema for FEAT-1160 (Context Window Analytics).

## Implementation Steps

1. Design and document the SQLite schema with FTS5 table definitions
2. Implement schema migration framework and `.ll/session.db` bootstrap on first run
3. Build ingestion pipeline via SessionStart hook, subscribing to event stream through FEAT-918 Transport sink
4. Implement `ll-session` CLI with `search` and `recent` subcommands
5. Write backfill script for existing `.ll/loops/`, `.issues/`, and session JSONLs
6. Migrate at least two `analyze-*` skills to query the DB instead of re-parsing source files
7. Add unit tests for ingestion, migration, and query paths
8. Update `.gitignore` and publish schema documentation

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete wiring for each step:_

- **Step 2 (schema bootstrap)**: Call from `scripts/little_loops/hooks/session_start.py:handle()` after config load (line ~115). `sqlite3` is stdlib in Python 3.11+; no new `pyproject.toml` dependency needed.
- **Step 3 (Transport sink)**: Add `SqliteTransport` implementing `Transport` Protocol (`send()` / `close()`) in `scripts/little_loops/session_store.py`. Register it in `scripts/little_loops/transport.py:wire_transports()` (line 570) following the `JsonlTransport` pattern at line 596. Model the class structure after `JsonlTransport` (line **78**). Note: `wire_transports` uses an explicit `if/elif` chain (not a factory pattern) — add an `elif name == "sqlite":` branch alongside the `if name == "jsonl":` block at lines 595–596. The `test_sqlite_registered_by_name` pattern to follow (`TestWireTransports`) calls `wire_transports(bus, config, log_dir=tmp_path)` then emits an event and verifies a file was written — it does not merely assert dict membership.
- **Step 4 (CLI wiring)**: 
  1. Create `scripts/little_loops/cli/session.py` with `_build_parser()`, `_parse_args()`, and `main_session() -> int` (model after `scripts/little_loops/cli/logs.py`). Important: in `logs.py`, `_parse_args()` takes **no `argv` parameter** — it calls `_build_parser().parse_args()` directly; `main_logs()` also calls `_build_parser().parse_args()` directly (not via `_parse_args()`), so it can hold a `parser` reference for `print_help()`. Follow this same pattern.
  2. Add `ll-session = "little_loops.cli:main_session"` to `scripts/pyproject.toml` `[project.scripts]` (insert after line 72)
  3. Add `from little_loops.cli.session import main_session` to `scripts/little_loops/cli/__init__.py` (after existing imports) and append `"main_session"` to `__all__`
  4. Use `scripts/little_loops/cli_args.py:add_config_arg()` for `--config` flag consistency
- **Step 6 (migration targets)**:
  - Target 1: `scripts/little_loops/cli/history.py:main_history()` (line 14) has **3 call sites** for `scan_completed_issues()` (lines 202, 216, 253 — for `summary`, `analyze`, and `export` subcommands respectively, all passing `issues_dir` as sole arg); all three must be routed post-backfill to `issue_events` table query. `scan_completed_issues` is defined in `scripts/little_loops/issue_history/parsing.py:289`.
  - Target 2: `scripts/little_loops/workflow_sequence/analysis.py:analyze_workflows()` (line 621) is the entry point for analyze-workflows; route to `tool_events` table query
- **Step 7 (test patterns)**: Model `test_session_store.py` after `scripts/tests/test_transport.py` (Protocol isinstance checks, exception isolation, tmp_path fixtures). Model `test_ll_session.py` after `scripts/tests/test_ll_logs.py` (`sys.argv` patching + `_parse_args()` + `capsys`).
- **Step 5 (path correction)**: Loop state lives at `.loops/` (not `.ll/loops/`). `StatePersistence` defaults to `Path(".loops")` in `scripts/little_loops/fsm/persistence.py:219`. Backfill sources are: `.loops/.running/` (active runs), `.loops/.history/` (archived runs), `.issues/` (completed issue frontmatter), and `~/.claude/projects/<hash>/*.jsonl` (session JSONL). Same correction applies to "Current Behavior" (line referencing `.ll/loops/`) and Acceptance Criteria (`.ll/loops/`).
- **Step 8**: Add `.ll/session.db` to `.gitignore` (already excludes `.ll/*.lock`, `.ll/ll-context-state.json`, `.ll/ll-sync-state.json`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

> **Scope split (2026-05-22, confidence-check):** The mechanical documentation, help-table, and skill allow-list reference updates have been carved out into **ENH-1619** ("Wire ll-session into docs, help, and config references"), which is `blocked_by: FEAT-1112`. The steps below retain only the **functional** wiring (transport registry, package re-export, config schema, CLI entry-point registration, functional tests). Steps that moved to ENH-1619 are marked `→ ENH-1619`.

9. Add `"sqlite"` key to `_TRANSPORT_REGISTRY` in `scripts/little_loops/transport.py`; update module docstring to list `SQLiteTransport` among built-in implementations
10. Add `SQLiteTransport` re-export to `scripts/little_loops/__init__.py` imports + `__all__` (follow `JsonlTransport` pattern)
11. Add `SqliteEventsConfig` dataclass + `sqlite` field to `EventsConfig.from_dict()` in `scripts/little_loops/config/features.py`; extend `config-schema.json` `events` object with `"sqlite"` property block
12. _→ ENH-1619_ — CLI registration chain docs: `commands/help.md`, `CONTRIBUTING.md`, `README.md`, `.claude/CLAUDE.md`
13. _→ ENH-1619_ — Skill registration: `skills/configure/areas.md`, `skills/init/SKILL.md`
14. Add `test_sqlite_registered_by_name` to `test_transport.py::TestWireTransports`; update `test_hook_session_start.py` after `handle()` gains DB bootstrap call. _(`test_feat1504_doc_wiring.py` count-assertion update → ENH-1619.)_
15. _→ ENH-1619_ — `docs/reference/CLI.md` `### ll-session` section
16. _→ ENH-1619_ — `docs/ARCHITECTURE.md` SQLiteTransport rows + directory tree entry
17. _→ ENH-1619_ — `docs/reference/CONFIGURATION.md` `"sqlite"` transport row + example
18. _→ ENH-1619_ — `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` data-source description
19. Update `scripts/tests/test_cli.py` — add `TestMainSessionIntegration`; adapt `TestMainHistoryIntegration` for DB-backed mocking; update `test_config_schema.py` for `events.sqlite` assertion

### Functional Wiring Verification

After implementing the steps above, this grep must return a hit for every functional registration site:

```bash
grep -rln "main_session\|ll-session\|SQLiteTransport\|\"sqlite\"" \
  scripts/pyproject.toml \
  scripts/little_loops/cli/__init__.py \
  scripts/little_loops/transport.py \
  scripts/little_loops/__init__.py \
  scripts/little_loops/config/features.py \
  config-schema.json
```

Documentation/help/allow-list reference sites are verified separately by **ENH-1619**.

## Integration Map

### Files to Modify
- `scripts/little_loops/hooks/session_start.py` — ingestion entry point
- `scripts/little_loops/session_store.py` — new SQLite/FTS5 module
- `scripts/little_loops/cli/session.py` — new CLI entry point
- `scripts/little_loops/cli/history.py` — migrate `main_history()` to DB queries (migration target #1)
- `scripts/little_loops/workflow_sequence/analysis.py` — migrate `analyze_workflows()` to DB queries (migration target #2)
- `scripts/pyproject.toml` — add `ll-session` entry point

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/transport.py` — add `"sqlite"` key to `_TRANSPORT_REGISTRY` (line ~562) and update module docstring to list `SQLiteTransport` among built-in implementations
- `scripts/little_loops/__init__.py` — add `SQLiteTransport` to package-level re-exports and `__all__` (following existing `JsonlTransport`/`UnixSocketTransport`/`OTelTransport`/`WebhookTransport` pattern)
- `scripts/little_loops/config/features.py` — add `SqliteEventsConfig` dataclass + `sqlite: SqliteEventsConfig` field to `EventsConfig.from_dict()` for optional DB path override
- `config-schema.json` — add `"sqlite"` property block inside the `events` object (required; the object uses `"additionalProperties": false`)
- `skills/configure/areas.md` — increment `"Authorize all 24 ll- CLI tools"` count to `25` and add `ll-session` to the inline tool list
- `skills/init/SKILL.md` — add `"Bash(ll-session:*)"` and narrative description to both Bash allow-list JSON blocks (~lines 502–523 and ~583–619)
- `commands/help.md` — add `ll-session` row to the CLI TOOLS table
- `skills/update-docs/SKILL.md` — inline Python snippet (~line 93) directly calls `scan_completed_issues(Path('.issues/completed'))`; update or annotate when `history.py` migrates to DB-backed queries [Agent 2 finding]
- `commands/analyze-workflows.md` — data-availability precondition changes from "JSONL message file present" to "session.db populated"; update description if a precondition note is documented [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/transport.py:570` — `wire_transports()` is where the new SQLiteTransport sink must be registered (same pattern as `JsonlTransport` and `UnixSocketTransport`)
- `scripts/little_loops/hooks/session_start.py:handle()` — must call DB bootstrap/migration on first run (after config load, before stdout emit)
- `scripts/little_loops/cli/__init__.py:42+` — needs `from little_loops.cli.session import main_session` import and `"main_session"` in `__all__`
- `scripts/little_loops/cli/history.py:main_history()` — calls `scan_completed_issues()` from `issue_history.parsing:289`; this is migration target #1 (post-backfill, route to `issue_events` table)
- `scripts/little_loops/workflow_sequence/analysis.py:621` — `analyze_workflows()` is the entry point for analyze-workflows skill; migration target #2 (route to `tool_events` table)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py:351` — calls `wire_transports()` in `cmd_run()`; will begin instantiating `SQLiteTransport` once `"sqlite"` is registered in `_TRANSPORT_REGISTRY` and user config
- `scripts/little_loops/cli/loop/lifecycle.py:415` — calls `wire_transports()` in `cmd_resume()`
- `scripts/little_loops/cli/parallel.py:235` — calls `wire_transports()` in `ParallelOrchestrator` setup
- `scripts/little_loops/cli/sprint/run.py:426` — calls `wire_transports()` in `_cmd_sprint_run()` per-wave block

### Similar Patterns
- `scripts/little_loops/transport.py:61` — `Transport` Protocol with `send(event)` / `close()` — new `SQLiteTransport` must satisfy this interface
- `scripts/little_loops/transport.py:570` — `wire_transports(bus, config, base)` — extend this function to instantiate `SQLiteTransport` from `EventsConfig`
- `scripts/little_loops/transport.py:85` — `JsonlTransport` — simplest concrete sink implementation; model `SQLiteTransport.__init__()` / `send()` / `close()` after this class
- `scripts/little_loops/cli/logs.py` + `scripts/pyproject.toml:50-76` — pattern for registering a new CLI: create `scripts/little_loops/cli/session.py`, add `ll-session = "little_loops.cli:main_session"` to `[project.scripts]`, import via `cli/__init__.py`
- `scripts/tests/test_transport.py` — test patterns for new `SQLiteTransport` unit tests
- `scripts/tests/test_ll_logs.py` — CLI test patterns (argparse, subcommand dispatch, tmp_path fixtures) to model `test_ll_session.py` after

### Tests
- `scripts/tests/test_session_store.py` — new test file
- `scripts/tests/test_ll_session.py` — new test file

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_transport.py` — add `TestWireTransports::test_sqlite_registered_by_name` to cover new `_TRANSPORT_REGISTRY` entry; model after existing `test_jsonl_registered_by_name` pattern [existing, add test]
- `scripts/tests/test_hook_session_start.py` — update `TestSessionStartConfigLoad` and `TestSessionStartContextStateCleanup` for DB bootstrap call added to `handle()`; verify `result.feedback` substring assertions don't pick up new bootstrap output [existing, update]
- `scripts/tests/test_feat1504_doc_wiring.py` — `TestConfigureAreasWiring.test_authorize_all_count_is_24` will break immediately when `areas.md` is updated; change assertion from `"Authorize all 24"` to `"Authorize all 25"` [existing, will break — update required]
- `scripts/tests/test_hook_intents.py` — verify `test_dispatch_session_start_happy_path` subprocess exit-code test still passes after bootstrap call is added to `handle()` (bootstrap must be best-effort/no-op if `.ll/` dir absent) [existing, may break]

_Wiring pass 2 added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — extend schema-validation test to assert `"sqlite"` key exists in `events` properties after `config-schema.json` is updated [existing, will break — update]
- `scripts/tests/test_cli.py` → `TestMainHistoryIntegration` — all three `scan_completed_issues` mock patches (`summary`, `analyze`, `export` subcommands) will stop covering the actual data path once `main_history()` migrates to DB queries; update mock strategy [existing, update required]
- `scripts/tests/test_cli.py` → add `TestMainSessionIntegration` class — `test_main_session_importable` plus subcommand dispatch tests; follow `TestMainHistoryIntegration` pattern [new test class to write]

### Documentation
- `docs/reference/session-store.md` — schema documentation
- `docs/reference/API.md` — add `ll-session` CLI reference

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — CLI Tools section: add `ll-session` entry (listed alongside `ll-history`, `ll-workflows`, `ll-logs`)
- `README.md` — increment `"27 CLI tools"` to `"28 CLI tools"` (two occurrences: ~lines 46 and 166)
- `CONTRIBUTING.md` — package structure tree (~line 188–203): add `session.py` to explicit `cli/` file listing
- `docs/reference/CLI.md` — add `### ll-session` section documenting `search --fts "<query>"` and `recent --kind=<kind>` subcommands (following `### ll-history` and `### ll-workflows` pattern)

_Wiring pass 2 added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — add `SQLiteTransport` to EventBus component row (line 489), CLI Entry Points table (lines 511–516), built-in transports prose (line 518), and `cli/session.py` to module directory tree (~line 233) [Agent 1 + 2 finding]
- `docs/reference/CONFIGURATION.md` — add `"sqlite"` row to "Currently shipped transports" table (`### events.transports`) and `events.sqlite` sub-object example block [Agent 2 finding]
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` — `## CLI Deep Dive: ll-workflows` section describes JSONL input model; update data-source description when `analyze_workflows()` migrates to `tool_events` DB query [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — `## State directory` table has no row for `.ll/session.db`; add entry after schema ships [Agent 2 finding]

### Configuration
- `.gitignore` — add `.ll/session.db`
- `.ll/ll-config.json` — optional DB path override

## Impact

- **Priority**: P4 — Important architectural improvement but non-blocking; existing analyze-* skills continue to work unchanged
- **Effort**: Large — New database module, schema design, ingestion pipeline, CLI, backfill script, and multiple skill migrations
- **Risk**: Medium — Introduces new persistent state (`.ll/session.db`) but all data is local and gitignored; no breaking changes to existing interfaces
- **Breaking Change**: No

## Risks / Notes

- Runtime selection: match context-mode's pattern — `bun:sqlite` on Bun, `node:sqlite` on Node ≥22.13, fallback to stdlib `sqlite3` in Python (we're Python-first, so this is simpler for us)
- Privacy: all local, no telemetry — consistent with ll defaults
- This is the larger bet in the context-mode cluster; consider `/ll:iterate-plan` before implementation

## References

- Inspiration: context-mode SQLite FTS5 session database
- Depends on / unblocks: FEAT-1113 (PreCompact auto-handoff), ENH-1114 (intent filtering)

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): `ll-logs` (FEAT-1002) is a downstream consumer that ships in Phase 1 reading JSONL directly from `~/.claude/projects/`. Once this store lands, a follow-up refactor will migrate `ll-logs` internals to query the SQLite database while preserving its CLI interface. Plan the schema to accommodate the fields ll-logs currently extracts from JSONL (see FEAT-1002 for field list).

## Verification Notes

**Verdict**: VALID — Re-verified 2026-05-22

- FEAT-918 is now `status: done` — block is naturally satisfied, no need to restore `blocked_by: [FEAT-918]` to frontmatter
- No `.ll/session.db` exists — feature not yet implemented ✓
- No `ll-session` CLI entry point in `pyproject.toml` ✓
- Previous verification (2026-05-17) recommended restoring `blocked_by: [FEAT-918]`, but this is no longer applicable since FEAT-918 is done

**Verdict**: NEEDS_UPDATE — Re-verified 2026-05-17

- `blocked_by: [FEAT-918]` was confirmed in frontmatter at 2026-04-26 verification, but the field is **no longer present** in the current frontmatter.
- FEAT-918 is now `done` — block is resolved. No action needed.
- The Scope Boundary prose still correctly states FEAT-1112 subscribes to FEAT-918's Transport sink.

**Verdict**: VALID — Verified 2026-04-26

- Frontmatter `blocked_by: [FEAT-918]` is accurate — FEAT-1002 reference already cleared ✓
- FEAT-918 (cross-process event streaming) is still open — block is real ✓
- No `.ll/session.db` exists — feature not implemented ✓
- No `ll-session` CLI entry point in `scripts/pyproject.toml` ✓

## Status

**Done** | Created: 2026-04-15 | Completed: 2026-05-23 | Priority: P4

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-22 (updated after ENH-1619 wiring carve-out)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 75/100 → MODERATE (was 62/100 before carve-out)

_Scope change: ~15 mechanical documentation/help/allow-list reference edits moved to ENH-1619 (`blocked_by: FEAT-1112`). This narrows FEAT-1112 to functional implementation + functional wiring, raising Complexity 9→14 and Change Surface 10→18._

### Outcome Risk Factors
- **tests are co-deliverables** — test_session_store.py and test_ll_session.py do not exist yet; implement tests first before wiring the new modules so DB ingestion logic ships with coverage from the start.
- **4 wire_transports callers will silently pick up SQLiteTransport** once `"sqlite"` is added to `_TRANSPORT_REGISTRY` and user config. Verify each call site (run.py:351, lifecycle.py:415, parallel.py:235, sprint/run.py:426) doesn't have error-handling assumptions that break under DB I/O failure; SQLiteTransport init must be best-effort or guarded by config flag.

## Implementation Note

_Added 2026-05-22 by `/ll:manage-issue features fix FEAT-1112`._

**Shipped (functional core + functional wiring + tests):**
- `scripts/little_loops/session_store.py` — SQLite + FTS5 schema, migration
  framework (`meta.schema_version`), `ensure_db()` / `connect()`,
  `SQLiteTransport` (best-effort EventBus sink), `search()` / `recent()`,
  `backfill()`. `tool_events` reserves `bytes_in`/`bytes_out`/`cache_hit` for
  FEAT-1160.
- `scripts/little_loops/cli/session.py` — `ll-session` CLI (`search --fts`,
  `recent --kind`, `backfill`).
- Functional wiring: `transport.py` registry + `wire_transports` branch,
  `__init__.py` re-export, `cli/__init__.py`, `config/features.py`
  (`SqliteEventsConfig`), `config-schema.json` (`events.sqlite`),
  `pyproject.toml` entry point, `session_start.py` bootstrap, `.gitignore`.
- Tests: `test_session_store.py`, `test_ll_session.py`,
  `test_transport.py::test_sqlite_registered_by_name`, `test_config_schema.py`.

**Completed via ENH-1621 (2026-05-22):** Step 6 / Acceptance Criterion 3 —
`main_history()` (summary subcommand) and `analyze_workflows()` now query the
session DB. See commit `3fb84970`. All acceptance criteria satisfied; FEAT-1112
closed 2026-05-23.

## Session Log
- `/ll:ready-issue` - 2026-05-22T21:07:28 - `2364d2da-6768-4e03-8b14-140e0435729f.jsonl`
- `/ll:confidence-check` - 2026-05-22T15:53:00 - `eb381959-43ce-4717-9896-81af7b2515ab.jsonl`
- `/ll:wire-issue` - 2026-05-22T20:25:37 - `dc75907b-1654-4afe-bf6b-17ff1d6e640c.jsonl`
- `/ll:refine-issue` - 2026-05-22T20:19:08 - `087da16e-8a6a-49c2-a0f5-b53a540fc58f.jsonl`
- `/ll:confidence-check` - 2026-05-22T00:00:00 - `b727c899-131c-4c1f-9603-f77124583f18.jsonl`
- `/ll:wire-issue` - 2026-05-22T20:04:52 - `7cc0d272-eceb-4768-b649-752fa3de3905.jsonl`
- `/ll:refine-issue` - 2026-05-22T19:58:39 - `d6c016c0-757a-4c25-9fb0-6b6bf3c10291.jsonl`
- `/ll:format-issue` - 2026-05-22T19:19:40 - `cbe9c704-5a55-4b97-bd03-bbd831363406.jsonl`
- `/ll:verify-issues` - 2026-05-22T16:11:37 - `d87b546d-fad7-425c-a8f4-8246f0ea8de8.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-22T16:01:45 - `bd1623c9-b064-4a18-a889-d90953167101.jsonl`
- `/ll:verify-issues` - 2026-05-18T04:53:51 - `2807bd8b-4e79-4b76-994d-e6f6cae14245.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:01 - `4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T19:43:56 - `b0a12d96-c315-4bf8-b507-7ba3c926702a.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T17:22:36 - `83033e3d-e46b-42e3-9b93-f788f6f5fee1.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:17 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-22T20:04:15 - `82d256a6-9a99-40f5-8866-377a208de262.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-19T01:16:14 - `9c7ed14d-9621-459d-9f93-384968b2e6f6.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Three scope clarifications from a 2026-05-01 cross-issue audit:

1. **Event capture is FEAT-1262's job, not this one's.** Drop "Ingestion via a lightweight daemon or SessionStart/PostToolUse hook" framing where it implies installing a parallel hook. This issue subscribes to FEAT-1262's event log via FEAT-918's Transport sink — no new PostToolUse hook is added by FEAT-1112.
2. **PreCompact summary reconstruction is FEAT-1264's MVP.** FEAT-1264 (JSONL/jq) is the MVP path for PreCompact handoff snapshots; FEAT-1112's SQLite-backed reconstruction is a future replacement that swaps in via the same stable snapshot-builder API. Don't ship parallel summary builders.
3. **SessionStart slot is shared.** FEAT-1112 owns SessionStart *ingestion* only; FEAT-1263 owns SessionStart *context injection*. `hooks/hooks.json` supports multiple SessionStart entries — the two are co-existing consumers, not competitors for the slot.

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-22): FEAT-1160 (Context Window Analytics) extends the `tool_events` table with per-tool byte columns (`bytes_in INTEGER`, `bytes_out INTEGER`, `cache_hit BOOLEAN`). Reserve these columns in FEAT-1112's initial `tool_events` schema so FEAT-1160 doesn't require a follow-up migration pass after the initial schema ships.

## Blocks

- FEAT-948
- FEAT-1156
- FEAT-1157
- FEAT-1158
- FEAT-1262
- ENH-1114
- FEAT-1160
- ENH-1619
