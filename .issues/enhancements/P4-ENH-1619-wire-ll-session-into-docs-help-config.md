---
id: ENH-1619
type: ENH
priority: P4
status: done
discovered_date: 2026-05-22
completed_at: 2026-05-22T21:55:20Z
discovered_by: confidence-check
testable: false
relates_to:
- FEAT-1112
- ENH-1621
labels:
- enhancement
- wiring
- docs
confidence_score: 100
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1619: Wire ll-session into docs, help, and config references

## Summary

Mechanical follow-up to FEAT-1112 (Unified Session Store): now that `ll-session`, `SQLiteTransport`, and the `events.sqlite` config block have landed (commit `844d7edf`), update all documentation, help tables, skill allow-lists, and the doc-wiring test to reference the new CLI and transport. Carved out of FEAT-1112 so the core DB/CLI/transport implementation ships as a focused PR and the ~12 uniform wiring edits land separately without mixed concerns in review.

## Motivation

FEAT-1112's wiring pass enumerated ~28 change sites. Roughly half are functional (new modules, transport registration, config schema, entry-point registration) and half are mechanical reference updates (count increments, list additions, doc sections). Bundling both into one PR inflates the review surface and the breadth-driven implementation risk. Splitting the mechanical reference updates into this issue keeps each PR single-purpose.

## Current Behavior

- `ll-session` does not appear in `commands/help.md`, `.claude/CLAUDE.md` CLI Tools, `README.md` tool count, `CONTRIBUTING.md` package tree, or `docs/reference/CLI.md` / `docs/reference/API.md`
- `SQLiteTransport` / `events.sqlite` are absent from `docs/ARCHITECTURE.md`, `docs/reference/CONFIGURATION.md`, and `docs/reference/HOST_COMPATIBILITY.md`
- `skills/configure/areas.md` and `skills/init/SKILL.md` do not authorize `ll-session`
- `test_feat1504_doc_wiring.py` asserts `"Authorize all 24"` — will be stale once `areas.md` updates

## Expected Behavior

All documentation, help surfaces, skill allow-lists, and the doc-wiring test reference `ll-session` and `SQLiteTransport` consistently, matching the CLI and transport delivered by FEAT-1112.

## Acceptance Criteria

- `ll-session` row added to `commands/help.md` CLI TOOLS table
- `ll-session` entry added to `.claude/CLAUDE.md` CLI Tools section
- `README.md` tool count incremented `27` → `28` (both occurrences — README.md:46 `"27 typed CLI tools"` and README.md:166 `"27 CLI tools"`; the unrelated `"28 slash commands"` at README.md:163 must NOT be touched)
- `CONTRIBUTING.md` package tree adds `session.py` to the `cli/` listing (CONTRIBUTING.md:186–203)
- `docs/reference/CLI.md` adds `### ll-session` section documenting all three subcommands — `search --fts QUERY [--limit N]`, `recent --kind {tool,file,issue,loop,correction} [--limit N]`, and `backfill` (place after `### ll-logs` at CLI.md:1179)
- `docs/reference/API.md` adds an `ll-session` / `main_session` CLI reference (model on the `main_logs` entry, API.md:3361)
- `docs/ARCHITECTURE.md` adds `SQLiteTransport` to the EventBus component row (`API.md` line ref: `events.py` row, ARCHITECTURE.md:489) and the built-in transports prose (ARCHITECTURE.md:518), and `cli/session.py` to the module tree. (The "CLI Entry Points / Transports Wired" table at ARCHITECTURE.md:511 lists *loop runners* — `ll-loop`/`ll-parallel`/`ll-sprint` — and needs **no** new row: `ll-session` is a read-only query CLI, not a runner that calls `wire_transports()`.)
- `docs/reference/CONFIGURATION.md` adds a `"sqlite"` row to the "Currently shipped transports" table (CONFIGURATION.md:772–777) and an `events.sqlite` sub-section + example, modeled on the existing `events.socket`/`events.otel`/`events.webhook` sub-sections (CONFIGURATION.md:791+)
- `docs/reference/HOST_COMPATIBILITY.md` `## State directory` table (HOST_COMPATIBILITY.md:168–177) adds a `.ll/session.db` row
- `skills/configure/areas.md` increments `"Authorize all 24 ll- CLI tools"` → `25` (areas.md:823) and adds `ll-session` to the inline list
- `skills/init/SKILL.md` adds `"Bash(ll-session:*)"` to the single Bash allow-list JSON block (SKILL.md:502–521 — there is only **one** such block, not two)
- `test_feat1504_doc_wiring.py::test_authorize_all_count_is_24` assertion updated to `"Authorize all 25"` (test line 49; the inline failure message and `(includes ll-migrate-status)` comment also need updating, and the method renamed to `test_authorize_all_count_is_25`)
- Verification grep (see below) returns a hit for every wired surface

## Verification

```bash
# Every surface below must reference ll-session after this issue lands:
grep -rln "ll-session" \
  commands/help.md \
  .claude/CLAUDE.md \
  README.md \
  CONTRIBUTING.md \
  docs/reference/CLI.md \
  docs/reference/API.md \
  skills/configure/areas.md \
  skills/init/SKILL.md

# SQLiteTransport doc surfaces:
grep -rln "SQLiteTransport\|events.sqlite\|session.db" \
  docs/ARCHITECTURE.md \
  docs/reference/CONFIGURATION.md \
  docs/reference/HOST_COMPATIBILITY.md

# Doc-wiring test must assert the new count:
grep -n "Authorize all 25" scripts/tests/test_feat1504_doc_wiring.py
```

## Scope Boundaries

- **In scope**: The ~12 mechanical reference edits enumerated below — count increments, help/CLI-table additions, doc sections, skill allow-list entries, and the `test_feat1504_doc_wiring.py` assertion update.
- **Out of scope**: All functional FEAT-1112 work — the `ll-session` CLI module, `SQLiteTransport` registration, the `events.sqlite` config schema, and entry-point registration. These **already landed** in commit `844d7edf` (`feat(session): add unified SQLite + FTS5 session store`); this issue only updates references to them.
- **Out of scope (deferred to ENH-1621)**: Any documentation that describes `ll-workflows` / `ll-history` as *DB-backed*. FEAT-1112 explicitly carved the migration of `analyze_workflows()` and `main_history()` to the session DB out to **ENH-1621** ("the schema cannot yet reconstruct their rich `IssueInfo` / message-text inputs"). Until ENH-1621 lands, those CLIs still consume JSONL. Therefore the following — originally listed in this issue — are **removed from scope** and belong to ENH-1621's doc-wiring: `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` data-source rewrite, `skills/update-docs/SKILL.md` inline-snippet annotation, and `commands/analyze-workflows.md` precondition change. Touching them now would document behavior that does not exist.
- **Out of scope**: New behavior or test coverage beyond updating the single stale assertion in `test_feat1504_doc_wiring.py`.

## Integration Map

### Files to Modify
- `commands/help.md` — add `ll-session` row to the CLI TOOLS table (help.md:239–267; table is roughly alphabetical — insert near `ll-logs`)
- `.claude/CLAUDE.md` — add `ll-session` bullet to the CLI Tools section (no `ll-session` mention currently)
- `README.md` — increment tool count `27` → `28` at README.md:46 and README.md:166 (leave `"28 slash commands"` at README.md:163 untouched)
- `CONTRIBUTING.md` — add `session.py` to `cli/` package tree (CONTRIBUTING.md:186–203)
- `docs/reference/CLI.md` — add `### ll-session` section after `### ll-logs` (CLI.md:1179)
- `docs/reference/API.md` — add `main_session` / `ll-session` CLI reference (model on `main_logs`, API.md:3361)
- `docs/ARCHITECTURE.md` — add `SQLiteTransport` to the EventBus component row (ARCHITECTURE.md:489) and built-in transports prose (ARCHITECTURE.md:518), and `cli/session.py` to the module tree. The CLI Entry Points table (ARCHITECTURE.md:511) needs **no** new row (see Acceptance Criteria note).
- `docs/reference/CONFIGURATION.md` — add `"sqlite"` row to the transports table (CONFIGURATION.md:772–777) + `events.sqlite` sub-section/example
- `docs/reference/HOST_COMPATIBILITY.md` — add `.ll/session.db` row to `## State directory` table (HOST_COMPATIBILITY.md:168–177)
- `skills/configure/areas.md` — increment count `24` → `25` and add `ll-session` to the inline list (areas.md:823)
- `skills/init/SKILL.md` — add `"Bash(ll-session:*)"` to the Bash allow-list block (SKILL.md:502–521 — single block; insert alphabetically near `Bash(ll-logs:*)`)

### Tests
- `scripts/tests/test_feat1504_doc_wiring.py` — update the `test_authorize_all_count_is_24` assertion at test line 49 to `"Authorize all 25"`, update its inline failure message, and rename the method to `test_authorize_all_count_is_25` [existing test, will break — update required]

### Deferred to ENH-1621 (NOT modified by this issue)
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md`, `skills/update-docs/SKILL.md`, `commands/analyze-workflows.md` — these describe `ll-workflows`/`ll-history` data sources; their wording only changes once the DB migration (ENH-1621) lands. See Scope Boundaries.

## Implementation Steps

1. FEAT-1112 has landed (commit `844d7edf`) — `ll-session` CLI (`scripts/little_loops/cli/session.py`), `SQLiteTransport` (`scripts/little_loops/session_store.py:256`), the `events.sqlite` config block (`config-schema.json:1176–1188`, named `"sqlite"`), and the `ll-session` pyproject entry point all exist. No pre-check needed; proceed directly.
2. Apply help/CLI-tool reference edits: `commands/help.md`, `.claude/CLAUDE.md`, `README.md` count, `CONTRIBUTING.md` package tree.
3. Apply doc-reference edits: `docs/reference/CLI.md`, `API.md`, `ARCHITECTURE.md`, `CONFIGURATION.md`, `HOST_COMPATIBILITY.md`. (`WORKFLOW_ANALYSIS_GUIDE.md` is deferred to ENH-1621 — see Scope Boundaries.)
4. Apply skill allow-list edits: `skills/configure/areas.md`, `skills/init/SKILL.md`. (`skills/update-docs/SKILL.md` and `commands/analyze-workflows.md` are deferred to ENH-1621.)
5. Update the `test_feat1504_doc_wiring.py` assertion to `"Authorize all 25"` (and rename the method) in the same commit as the `areas.md` edit.
6. Run the Verification greps to confirm every surface references `ll-session`.

## Impact

- **Priority**: P4 — Non-blocking documentation/reference consistency follow-up
- **Effort**: Small — ~12 mechanical, uniform reference edits (3 originally-listed surfaces deferred to ENH-1621)
- **Risk**: Low — No functional code; all changes are docs/help/allow-list text
- **Breaking Change**: No

## Risks / Notes

- **No longer blocked.** FEAT-1112 landed in commit `844d7edf`; the `ll-session` CLI, `SQLiteTransport`, and `events.sqlite` config block all exist, so every reference this issue adds is now accurate. `blocked_by` has been cleared from the frontmatter. (FEAT-1112 is now `done`; ENH-1621 tracks the remaining DB-migration work for `ll-workflows`/`ll-history`, which does not affect ENH-1619 — see Scope Boundaries.)
- `test_feat1504_doc_wiring.py` will fail the moment `areas.md` is updated — bundle the assertion update in the same commit as the `areas.md` edit.
- Three surfaces originally listed here (`WORKFLOW_ANALYSIS_GUIDE.md`, `update-docs/SKILL.md`, `analyze-workflows.md`) were removed from scope: they describe `ll-workflows`/`ll-history` data sources, and FEAT-1112 deferred the DB migration of those CLIs to ENH-1621. Editing them now would document non-existent behavior.

## Codebase Research Findings

_Added by `/ll:refine-issue` — every surface verified against the working tree (commit `844d7edf`):_

- **FEAT-1112 functional deps confirmed present**: `cli/session.py` (entry point `ll-session = "little_loops.cli:main_session"`, `pyproject.toml:72`), `SQLiteTransport` (`session_store.py:256`), `"sqlite"` transport registered (`transport.py` registry + `wire_transports`), `events.sqlite`→`"sqlite"` config block (`config-schema.json:1176–1188`).
- **`ll-session` CLI surface** (`cli/session.py:23–65`): three subcommands — `search --fts QUERY [--limit N]`, `recent --kind {tool,file,issue,loop,correction} [--limit N]`, `backfill`; global `--db PATH` (default `.ll/session.db`). The original CLI.md AC named only `search`/`recent` — `backfill` was added.
- **Verified counts/anchors**: README.md:46 + :166 say `"27 ... CLI tools"` (→ 28); `"28 slash commands"` at README.md:163 is unrelated and must be left alone. `areas.md:823` says `"Authorize all 24"`. `test_feat1504_doc_wiring.py:49` asserts `"Authorize all 24"` in method `test_authorize_all_count_is_24`.
- **`skills/init/SKILL.md` correction**: the issue said "both Bash allow-list blocks" — there is only **one** block (`SKILL.md:502–521`).
- **`docs/ARCHITECTURE.md` correction**: the EventBus component row (:489), CLI Entry Points table (:511–516), and "Built-in transports" prose (:518) all exist (a `grep "built-in transport"` misses them — the prose uses capital "Built-in"). `SQLiteTransport` belongs in the :489 row and :518 prose; the :511 entry-points table lists *loop runners* only and needs no row for the read-only `ll-session` CLI.
- **Three ACs removed → ENH-1621**: `WORKFLOW_ANALYSIS_GUIDE.md`, `update-docs/SKILL.md`, and `analyze-workflows.md` describe `ll-workflows`/`ll-history` as JSONL-consuming today. FEAT-1112's management plan (`P4-FEAT-1112-...md:320`) explicitly defers migrating `analyze_workflows()`/`main_history()` to the DB to ENH-1621. ENH-1621 has no issue file yet — it exists only as a planned carve-out referenced in FEAT-1112.

## References

- Carved out of FEAT-1112 (Unified Session Store) during a confidence-check pass to reduce that issue's breadth-driven implementation risk.
- FEAT-1112 landed in commit `844d7edf` (`feat(session): add unified SQLite + FTS5 session store`).
- ENH-1621 (not yet filed) — owns the `ll-workflows`/`ll-history` DB migration and its three associated doc surfaces.

## Resolution

All ~12 mechanical reference edits applied. `ll-session` is now wired into `commands/help.md`, `.claude/CLAUDE.md`, `README.md` (count `27`→`28` at both occurrences), `CONTRIBUTING.md` package tree, `docs/reference/CLI.md` (`### ll-session` section), `docs/reference/API.md` (`main_session` entry), `skills/configure/areas.md` (count `24`→`25`), and `skills/init/SKILL.md` Bash allow-list. `SQLiteTransport` / `events.sqlite` / `.ll/session.db` are wired into `docs/ARCHITECTURE.md`, `docs/reference/CONFIGURATION.md`, and `docs/reference/HOST_COMPATIBILITY.md`.

The `test_feat1504_doc_wiring.py` assertion was updated to `"Authorize all 25"` and the method renamed to `test_authorize_all_count_is_25`. Two additional stale-count tests not enumerated in the issue (`test_ll_logs_wiring.py` and `test_create_extension_wiring.py`) were also updated — they asserted the same `"Authorize all 24"` / `"27 typed CLI tools"` strings and would otherwise break.

All verification greps return a hit for every wired surface; the full test suite passes (one unrelated pre-existing failure in `test_feat1287_doc_wiring.py` stems from a separate uncommitted `.claude/CLAUDE.md` change removing `(30 skills)`, not from this issue).

## Status

**Done** | Created: 2026-05-22 | Completed: 2026-05-22 | Priority: P4


## Session Log
- `/ll:manage-issue` - 2026-05-22T21:55:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2364d2da-6768-4e03-8b14-140e0435729f.jsonl`
- `/ll:confidence-check` - 2026-05-22T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b53de0d3-d850-43b9-9010-e17567340a8a.jsonl`
- `/ll:refine-issue` - 2026-05-22T21:31:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7f9c4451-bae8-485f-b744-89f4f1009dca.jsonl`
- `/ll:format-issue` - 2026-05-22T21:02:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/df79ad24-cc3b-462e-9fab-b112d3d4bad4.jsonl`
