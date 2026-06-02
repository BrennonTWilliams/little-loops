---
id: ENH-1846
title: Scaffold ll-history-context CLI (Option B) with tests and docs
type: ENH
priority: P3
status: done
parent: ENH-1708
depends_on:
- ENH-1782
- ENH-1717
blocked_by:
- ENH-1831
labels:
- enhancement
size: Medium
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-06-01 10:28:40+00:00
---

# ENH-1846: Scaffold ll-history-context CLI (Option B) with tests and docs

## Summary

Create the `ll-history-context <issue_id> [--file <path>]` CLI entry point that queries `.ll/history.db` for user corrections and FTS5 matches and renders a ready-to-inject `## Historical Context` markdown block. Includes registration, permission wiring, tests, and all Option B documentation touchpoints.

## Parent Issue
Decomposed from ENH-1708: Wire user_corrections + FTS5 Reads into refine-issue / ready-issue / confidence-check

## Motivation

ENH-1708 selected Option B (new `ll-history-context` CLI) as the implementation approach. This child creates the CLI module itself so it can be called by the three skills in the follow-on issue (ENH-1847). Without this CLI, ENH-1847 cannot be started.

## Scope

This child covers **Implementation Steps 5, 8, 9, 10** from ENH-1708:

- Step 5: Scaffold `scripts/little_loops/cli/history_context.py`; add `ll-history-context` entry point to `scripts/pyproject.toml`
- Step 8: Add `"Bash(ll-history-context:*)"` to `.claude/settings.local.json` `permissions.allow`
- Step 9: Update `scripts/little_loops/cli/__init__.py` — add import and `__all__` entry
- Step 10: Update all 7 Option B-only documentation files

Tests for the new CLI (`test_history_context_cli.py`) are included here (tests belong with the implementation they cover).

## Implementation Steps

### 1. Create `scripts/little_loops/cli/history_context.py`

Follow the pattern from `scripts/little_loops/cli/session.py` (`main_session()`):

```python
def main_history_context() -> int:
    """ll-history-context <issue_id> [--file <path>]"""
    ...
```

Startup sequence (mirrors `session.py`): call `configure_output()` then `logger = Logger(use_color=use_color_enabled())` before parsing args. Return `0` on success, `1` on error.

Behavior:
1. Parse `issue_id` (required) and optional `--file <path>` arguments
2. Call `find_user_corrections(topic=issue_id)` + `search(query=issue_title_keywords, kind="correction")` with dedup
3. If `--file <path>` provided, also call `recent_file_events(path=path, limit=5)`
4. Deduplicate across all result sets (by content hash or `(kind, anchor, content)`)
5. Cap at N=5 rows total
6. Render a `## Historical Context` markdown block and print to stdout
7. Return empty output (no section) if DB is missing, no matches, or all rows stale

**Critical: `search()` has no built-in stale filter.** Unlike `find_user_corrections()` and `recent_file_events()` (which apply `AND ts >= ?` in SQL), `search()` returns `SearchResult` objects at any age. The CLI must post-filter by comparing `result.ts` against `_stale_cutoff(STALE_DAYS_DEFAULT)` from `history_reader.py` before including rows in the output.

### 2. Register entry point in `scripts/pyproject.toml`

Add under `[project.scripts]`:
```toml
ll-history-context = "little_loops.cli:main_history_context"
```

This routes through `cli/__init__.py` (same pattern as `ll-session`, `ll-history`, `ll-ctx-stats`) — not direct module registration. The direct-module pattern (`"little_loops.cli.history_context:main"`) is used only for `ll-workflows`; don't mix patterns.

### 3. Update `scripts/little_loops/cli/__init__.py`

Add import and `__all__` entry matching the existing pattern used for `session.py`, `ctx_stats.py`, `history.py`.

### 4. Update `.claude/settings.local.json`

Add `"Bash(ll-history-context:*)"` to the `permissions.allow` array so interactive skill testing doesn't prompt for permission on every history query.

### 5. Add `scripts/tests/test_history_context_cli.py`

Follow patterns from `scripts/tests/test_ll_session.py` (`TestMainSession`):

Test classes to add:
- `TestArgumentParsing` — verify `--file` is optional, missing `issue_id` errors
- `TestHistoryContextWithMatches` — DB seeded with correction rows; assert `## Historical Context` in stdout
- `TestHistoryContextNoMatches` — DB present but empty; assert empty stdout
- `TestHistoryContextDBMissing` — no DB file; assert empty stdout, exit 0
- `TestHistoryContextStaleRows` — all rows older than 30 days; assert empty stdout
- `TestDeduplication` — same content from two queries; assert deduped in output

DB path injection: pass `--db str(db)` in the patched `sys.argv` (same as `test_ll_session.py`).

**Seeding pattern by test class:**
- `TestHistoryContextWithMatches`, `TestHistoryContextStaleRows`, `TestDeduplication`: seed via `record_correction(db, session_id, content, source)` from `little_loops.session_store` (or raw `INSERT INTO user_corrections`). `SQLiteTransport.send()` does NOT write to `user_corrections` — it only writes loop/issue events to `search_index` and event tables.
- `TestHistoryContextNoMatches`, `TestHistoryContextDBMissing`: use `ensure_db(db)` for schema-only (no rows) or omit DB creation entirely.
- Stale rows: insert with `ts = (datetime.now(UTC) - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")` via raw INSERT.

Pattern reference: `scripts/tests/test_history_reader.py:TestStaleRowFiltering._insert_old_correction()`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `README.md` — change both `"29 typed CLI tools"` (line 46) and `"29 CLI tools"` (line 162) to `"30 ..."`. Do NOT add a `### ll-history-context` section.
8. Update `skills/configure/areas.md` — change `"Authorize all 26 ll- CLI tools"` to `"Authorize all 27 ll- CLI tools"` and add `ll-history-context` to the tool enumeration in that label's description string.
9. Update `scripts/tests/test_create_extension_wiring.py` — change `"Authorize all 26"` to `"Authorize all 27"` in both `TestConfigureAreasWiring.test_count_updated_to_17()` and `TestFeat1229LlActionWiring.test_configure_areas_count_is_17()`.
10. Add `scripts/tests/test_enh1846_doc_wiring.py` — follow the `TestFeat1229LlActionWiring` class pattern; assert `ll-history-context` is present in `CLI.md`, `help.md`, `CLAUDE.md`, `init/SKILL.md`, and `configure/areas.md`.
11. Update `scripts/little_loops/cli/__init__.py` module-level docstring — in addition to the import line and `__all__` entry (Step 3), add `- ll-history-context: <description>` to the module-level CLI catalog docstring at lines 1–32.

### 6. Update documentation (7 Option B-only files)

- `docs/reference/API.md` — add `### main_history_context` subsection after `### main_session`
- `docs/reference/CLI.md` — add `### ll-history-context` section with `<issue_id>` and `--file <path>` args and output format
- `docs/ARCHITECTURE.md` — add `history_context.py` line in `cli/` directory tree alongside `session.py`
- `.claude/CLAUDE.md` — add `ll-history-context` bullet under `## CLI Tools` alongside `ll-session`
- `CONTRIBUTING.md` — add `history_context.py` tree entry in `cli/` section
- `commands/help.md` — add `ll-history-context` line to CLI Tools listing block
- `skills/init/SKILL.md` — add `"Bash(ll-history-context:*)"` to the generated `permissions.allow` template array

## Acceptance Criteria

- `ll-history-context ENH-1708` runs without error and returns a `## Historical Context` block when the DB has matching corrections
- `ll-history-context ENH-9999` returns empty output (no error) when no matches exist
- `ll-history-context ENH-1708` when DB file is missing returns empty output with exit code 0
- Output is capped at 5 rows even when more matches exist
- All test classes pass: matches present, no matches, DB missing, DB empty, stale rows, deduplication
- All 7 documentation files updated with `ll-history-context` entries

## Integration Map

### New Files
- `scripts/little_loops/cli/history_context.py` — new CLI module
- `scripts/tests/test_history_context_cli.py` — new test file

### Files to Modify
- `scripts/pyproject.toml` — add entry point
- `scripts/little_loops/cli/__init__.py` — add import + `__all__`
- `.claude/settings.local.json` — add permission
- `docs/reference/API.md` — add `main_history_context` section
- `docs/reference/CLI.md` — add `ll-history-context` section
- `docs/ARCHITECTURE.md` — add directory tree entry
- `.claude/CLAUDE.md` — add CLI Tools bullet
- `CONTRIBUTING.md` — add tree entry
- `commands/help.md` — add CLI listing line
- `skills/init/SKILL.md` — add to permissions template

### Reference (Read-Only)
- `scripts/little_loops/history_reader.py` — `find_user_corrections()`, `recent_file_events()`, `search()`
- `scripts/little_loops/cli/session.py` — template for CLI structure
- `scripts/tests/test_ll_session.py` — template for test structure

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — lines 46 and 162 both state `"29 typed CLI tools"` / `"29 CLI tools"` — must be incremented to 30. Guard test `TestReadmeIsHeroPage.test_readme_has_no_ll_cli_sections()` enforces no `### ll-*` sections in README, so only the count string changes, no new section. [Agent 2 finding]

### Registration / Manifest Files

_Wiring pass added by `/ll:wire-issue`:_
- `skills/configure/areas.md` — `## Area: allowed-tools` section currently reads `"Authorize all 26 ll- CLI tools"` — increment to 27 and add `ll-history-context` to the enumerated list [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py` — `TestConfigureAreasWiring.test_count_updated_to_17()` and `TestFeat1229LlActionWiring.test_configure_areas_count_is_17()` both assert `"Authorize all 26"` — update both to `"Authorize all 27"` [update needed — Agent 2 finding]
- `scripts/tests/test_enh1846_doc_wiring.py` (new) — add presence test asserting `ll-history-context` appears in `docs/reference/CLI.md`, `commands/help.md`, `.claude/CLAUDE.md`, `skills/init/SKILL.md`, and `skills/configure/areas.md`; follow existing pattern in `test_create_extension_wiring.py` (e.g. `TestFeat1229LlActionWiring`) [new test needed — Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — exact signatures and behavioral notes:_

**`history_reader.py` function signatures:**
- `find_user_corrections(topic: str, *, limit: int = 10, include_stale: bool = False, db: Path | str = DEFAULT_DB_PATH) -> list[UserCorrection]` — built-in 30-day stale filter via SQL; returns `[]` on missing DB (never raises)
- `recent_file_events(path: str, *, limit: int = 10, include_stale: bool = False, db: Path | str = DEFAULT_DB_PATH) -> list[FileEvent]` — same built-in stale filter; returns `[]` on error
- `search(query: str, *, kind: str | None = None, limit: int = 10, db: Path | str = DEFAULT_DB_PATH) -> list[SearchResult]` — **no built-in stale filter**; each `SearchResult` has a `ts: str` field; caller must post-filter; returns `[]` on FTS5 error or missing DB
- `STALE_DAYS_DEFAULT = 30` and `_stale_cutoff(days: int) -> str` are importable for the post-filter

**Test seeding helpers:**
- `record_correction(db_path, session_id, content, source)` in `scripts/little_loops/session_store.py` — writes to `user_corrections` AND indexes in `search_index` (preferred for round-trip tests)
- `ensure_db(db)` in `scripts/little_loops/session_store.py` — creates schema with no rows (use for empty-DB/missing-DB test classes)
- `connect(db)` in `scripts/little_loops/session_store.py` — for raw INSERT of stale rows with explicit `ts` values

**`session.py` startup sequence to replicate:**
```python
configure_output()
logger = Logger(use_color=use_color_enabled())
```
Both are from `scripts/little_loops/cli/output.py`.

## Notes

- This child must be completed before ENH-1847 (skill wiring) begins — the skills call `ll-history-context` which must be installed first
- Strictly sequential with ENH-1847; if implementing both in one session, consider keeping as one issue (ENH-1708 parent) to avoid tracking overhead

## Session Log
- `/ll:ready-issue` - 2026-06-01T10:18:16 - `cf38a300-936b-4182-8d3c-653c9bc6200b.jsonl`
- `/ll:wire-issue` - 2026-06-01T10:14:13 - `544e27c1-c5b2-4c59-bc53-6f190e1ade51.jsonl`
- `/ll:refine-issue` - 2026-06-01T10:09:29 - `59bcb2ef-0812-43b3-b6ca-f20662a97853.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `d911bade-69cf-42d7-8c1a-fd493d2859d8.jsonl`
- `/ll:manage-issue` - 2026-06-01T10:28:40Z - `9bda050f-155e-4eb1-aea6-1bce4cf98225.jsonl`

## Resolution

Implemented `ll-history-context <issue_id> [--file <path>]` CLI entry point (ENH-1846 Option B):

- Created `scripts/little_loops/cli/history_context.py` — queries user corrections + FTS5 search with dedup and stale-filtering; caps at 5 rows; renders `## Historical Context` block
- Registered `ll-history-context` entry point in `scripts/pyproject.toml`
- Updated `scripts/little_loops/cli/__init__.py` — import, `__all__`, docstring
- Added `"Bash(ll-history-context:*)"` to `.claude/settings.local.json`
- Added 18 tests across 6 classes in `scripts/tests/test_history_context_cli.py` (all pass)
- Added wiring tests in `scripts/tests/test_enh1846_doc_wiring.py` (all pass)
- Updated all 7 Option B documentation touchpoints (CLI.md, API.md, ARCHITECTURE.md, CLAUDE.md, CONTRIBUTING.md, help.md, init/SKILL.md)
- Updated README.md (29→30 CLI tools), configure/areas.md (26→27 tools), test_create_extension_wiring.py count assertions

---

**Done** | Created: 2026-06-01 | Priority: P3
