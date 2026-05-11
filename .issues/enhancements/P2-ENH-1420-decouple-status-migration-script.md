---
id: ENH-1420
type: ENH
priority: P2
status: done
completed_at: 2026-05-10T22:12:31Z

confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
parent: ENH-1390
---

# ENH-1420: Decouple Issue Status — Migration Script

## Summary

One-time migration script that moves all files from `deferred/` and `completed/` into their type directories with correct `status:` frontmatter, and backfills `completed_at:` for ~140 older completed files that lack it. Must run after ENH-1418 and ENH-1419 (discovery and lifecycle tools must be updated before files are physically moved so no window exists where tools are broken).

## Parent Issue

Decomposed from ENH-1390: Decouple Issue Status from Directory Structure

## Current Behavior

Files for completed and deferred issues are stored in `.issues/completed/` and `.issues/deferred/` subdirectories. Approximately 140 older completed files lack the `completed_at:` frontmatter field. No tooling exists to move these files into the new directory-per-type layout that ENH-1390 establishes.

## Expected Behavior

Running the migration script moves all files from `.issues/completed/` and `.issues/deferred/` into their corresponding type directories (`.issues/bugs/`, `.issues/features/`, `.issues/enhancements/`, `.issues/epics/`) with `status: done` or `status: deferred` written into frontmatter, and `completed_at:` backfilled for files that were missing it. The `completed/` and `deferred/` directories are left empty or removed.

## Motivation

ENH-1390 decouples issue status from directory structure, requiring all ~1,346 issues currently in `completed/` and `deferred/` to move to type-based directories. Without this migration script the cutover cannot happen safely at scale. Manual migration of 1,346 files is error-prone; an automated script with dry-run mode is the only practical path.

## Proposed Solution

### Step 4 — Migration script

Write a one-time migration script (e.g., `scripts/little_loops/cli/migrate_issue_dirs.py` or as a subcommand of `ll-issues`) that:

1. **Scans** `deferred/` and `completed/` under `.issues/` (using `config.get_deferred_dir()` and `config.get_completed_dir()`)
2. **Backfills `completed_at:`** for completed files missing the field:
   - Use the existing git-log fallback logic already in `_parse_completion_date()` (lines 185–190 of `issue_history/parsing.py`) to derive completion dates from git history before the files are moved
   - Call `update_frontmatter(path, {"completed_at": derived_date})` for files missing the field
3. **Writes status frontmatter**:
   - `update_frontmatter(path, {"status": "done"})` for files in `completed/`
   - `update_frontmatter(path, {"status": "deferred"})` for files in `deferred/`
4. **Determines target type directory**:
   - Read `type:` from frontmatter (`BUG` → `bugs/`, `FEAT` → `features/`, `ENH` → `enhancements/`, `EPIC` → `epics/`)
   - Fall back to filename parsing if frontmatter type is missing
5. **Moves files** via `git mv` into the correct type directory
6. **Dry-run mode**: `--dry-run` flag prints all planned moves without executing them (strongly advised given 1,346 files at risk)
7. **Reports**: count of files moved, count of `completed_at:` backfills, list of any files that couldn't be typed (needs manual review)

### Post-migration cleanup

After migration is confirmed complete:
- Remove or archive the now-empty `deferred/` and `completed/` directories
- Remove git-log fallback tiers from `_parse_completion_date()` (they are no longer needed once all files carry `completed_at:`)
- Remove deprecated `get_completed_dir()` / `get_deferred_dir()` stubs from `config/core.py` (the deprecation warnings added in ENH-1417 can now become hard removals)

### Constraint from Sub-decision 2 (ENH-1390 decide-issue)

`manage-release.md` must compare full ISO timestamps (not date-only) against the previous tag's commit timestamp to avoid the BUG-942 off-by-one failure mode. Verify this before migration confirmation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Utility function signatures (confirmed):**
- `update_frontmatter(content: str, updates: dict[str, str | int]) -> str` at `scripts/little_loops/frontmatter.py` — takes a content string, not a path; call as `path.write_text(update_frontmatter(path.read_text("utf-8"), {...}), "utf-8")`
- `parse_frontmatter(content: str, *, coerce_types: bool = False) -> dict[str, Any]` at `scripts/little_loops/frontmatter.py` — returns `{}` when no frontmatter block exists
- `_parse_completion_date(content: str, file_path: Path, *, batch_dates: dict[str, date] | None = None, fm: dict[str, Any] | None = None) -> date | None` at `scripts/little_loops/issue_history/parsing.py` — returns `datetime.date`, not `datetime`; git-log fallback uses `git log --format=%as -1 -- <path>`
- `_is_git_tracked(file_path: Path) -> bool` at `scripts/little_loops/issue_lifecycle.py` — runs `git ls-files`; use before `git mv`

**Critical caveats discovered:**
- `_batch_completion_dates()` in `issue_history/parsing.py` is a **no-op stub returning `{}`** — batch mode unavailable; the migration script must call the per-file git-log subprocess directly (mirroring `_parse_completion_date()` tier 4)
- A large portion of `completed/` files have **no frontmatter block at all** — `update_frontmatter()` handles this correctly (prepends a new block), but test fixtures must cover this case
- Deferred files currently carry **`status: open`** in frontmatter (not blank) — the migration must overwrite with `status: deferred`
- Actual file counts: **~1,303 files** in `completed/`, **~49 files** in `deferred/` (plus 1 `.gitkeep`); the 1,346 total cited in Motivation combines both

**CLI registration pattern:**
- New standalone script: `scripts/little_loops/cli/migrate.py` exporting `main_migrate() -> int` (not a subcommand of `ll-issues`)
- Register in `scripts/pyproject.toml` under `[project.scripts]`: `ll-migrate = "little_loops.cli:main_migrate"`
- Import and re-export `main_migrate` in `scripts/little_loops/cli/__init__.py` (following pattern of `main_gitignore`, `main_deps`)
- Use `add_dry_run_arg(parser)` and `add_config_arg(parser)` from `scripts/little_loops/cli_args.py`
- Follow dry-run prefix pattern from `scripts/little_loops/cli/gitignore.py:main_gitignore()`: `[DRY RUN]` prefix on all action lines

## Files to Create / Modify

- `scripts/little_loops/cli/migrate_issue_dirs.py` (new) — migration script with dry-run mode
- `scripts/little_loops/issue_history/parsing.py` — remove git-log fallback tiers after migration (post-migration cleanup step, can be a follow-up commit)
- `scripts/little_loops/config/core.py` — remove `get_completed_dir()`/`get_deferred_dir()` stubs (post-migration cleanup)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/__init__.py` — import and re-export `main_migrate`; also update module docstring (lines 1–21) which lists all CLI tools
- `scripts/pyproject.toml` — add `ll-migrate = "little_loops.cli:main_migrate"` under `[project.scripts]`
- `.claude/CLAUDE.md` — CLI Tools section lists all `ll-*` tools; add `ll-migrate` entry [Agent 1/2 finding]
- `README.md` — "17 CLI tools" count and `### ll-*` tool sections; update count to 18 and add `### ll-migrate` section [Agent 2 finding]
- `commands/help.md` — "CLI TOOLS" section enumerates all tools; add `ll-migrate` [Agent 2 finding]
- `docs/reference/CLI.md` — per-tool sections; add `ll-migrate` section [Agent 2 finding]
- `skills/configure/areas.md` — "Authorize all 16 ll- CLI tools" string; update count to 17 and add `ll-migrate` to the list [Agent 2 finding]
- `scripts/tests/test_create_extension_wiring.py` — `test_readme_tool_count_is_17` (×2) and `test_configure_areas_count_is_16` hardcode current counts; update when README and `skills/configure/areas.md` are updated [Agent 2/3 finding]
- (Post-migration) `scripts/little_loops/issue_history/parsing.py` — remove git-log fallback tiers from `_parse_completion_date()`
- (Post-migration) `scripts/little_loops/config/core.py` — hard-remove `get_completed_dir()` and `get_deferred_dir()` stubs (lines 221–237)
- (Post-migration) `scripts/little_loops/issue_discovery/search.py` — update `get_all_issues()` to stop calling deprecated `get_completed_dir()`/`get_deferred_dir()`; **must happen before stub removal or breaks at runtime** [Agent 1/2 finding]
- (Post-migration) `config-schema.json` — `completed_dir`/`deferred_dir` keys (lines 106–111) marked `[DEPRECATED]`; remove after migration [Agent 2 finding]

### Files to Create
- `scripts/little_loops/cli/migrate.py` — main migration CLI with `main_migrate() -> int`
- `scripts/tests/test_issue_migration.py` — test suite for the migration script

### Utility Functions to Reuse
- `scripts/little_loops/frontmatter.py` — `parse_frontmatter()`, `update_frontmatter()`
- `scripts/little_loops/issue_lifecycle.py` — `_is_git_tracked()` (git mv guard) and git mv + fallback rename pattern from `skip_issue()`
- `scripts/little_loops/cli_args.py` — `add_dry_run_arg()`, `add_config_arg()`

### Similar Patterns to Follow
- `scripts/little_loops/cli/gitignore.py:main_gitignore()` — dry-run flag + `[DRY RUN]` prefix output pattern
- `scripts/little_loops/cli/deps.py:main_deps()` — scan + report with dry-run awareness
- `scripts/little_loops/issue_lifecycle.py:skip_issue()` — `_is_git_tracked()` → `git mv` → fallback rename

### Tests
- `scripts/tests/conftest.py` — `temp_project_dir`, `sample_config` fixtures to inherit
- `scripts/tests/test_issue_history_parsing.py:TestParseCompletionDate` — `subprocess.run` mocking pattern for git-log tests
- `scripts/tests/test_gitignore_cmd.py` — `sys.argv` patching + `assert_not_called()` dry-run assertion pattern

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_lifecycle.py` — `TestCommitIssueCompletion` / `TestUndeferIssue` — provides the `subprocess.run` `side_effect` dispatch pattern for mocking `git ls-files` and `git mv`; prefer this pattern over `test_issue_history_parsing.py` for the git-mv portions of the migration test [Agent 3 finding]
- `scripts/tests/test_frontmatter.py` — `TestParseFrontmatter.test_no_frontmatter` + `TestUpdateFrontmatter.test_update_creates_frontmatter` cover the no-frontmatter edge case (~50% of `completed/` files); ensure migration test fixtures include at least one file with no frontmatter block [Agent 3 finding]

_Tests to DELETE in post-migration cleanup (these exercise code paths that will be removed):_
- `scripts/tests/test_config.py` — `TestGetCompletedDir.test_get_completed_dir` (line 646) and `TestGetDeferredDir.test_get_deferred_dir` (line 659) — will error (not just fail) when the stubs are hard-removed [Agent 3 finding]
- `scripts/tests/test_issue_history_parsing.py` — `TestParseCompletionDate.test_git_log_fallback_when_no_date_field` (line 200), `test_git_log_fallback_returns_none_when_empty` (line 211), `test_git_log_fallback_returns_none_on_nonzero_exit` (line 220), `test_git_log_fallback_returns_none_on_oserror` (line 231) — test the fallback tiers that will be stripped [Agent 3 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_discovery/search.py` — `get_all_issues()` calls `config.get_completed_dir()` (line 84) and `config.get_deferred_dir()` (line 90) inside "Legacy completed/ and deferred/ sibling dirs" block; **runtime break if stubs are removed without updating this file first** [Agent 1/2 finding]
- `scripts/little_loops/config/features.py` — `IssuesConfig` dataclass has `completed_dir` and `deferred_dir` fields backing the deprecated stubs; fields become orphaned after method removal — remove in the same post-migration pass [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `##### get_completed_dir` and `##### get_deferred_dir` subsections with usage example at line 3681; remove when methods are removed in post-migration cleanup [Agent 2 finding]
- `docs/ARCHITECTURE.md` — Mermaid class diagram shows both methods as `[DEPRECATED]`; state machine diagram references `Move to completed/` directory transitions; update post-migration [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — line 783: "Check issue moved to `completed/` directory"; update post-migration [Agent 2 finding]
- `skills/manage-issue/SKILL.md` — directory tree (lines 42–51) shows `completed/` and `deferred/` as siblings; defer/undefer descriptions use directory language; update post-migration [Agent 2 finding]
- `skills/confidence-check/SKILL.md` — lines 185 and 298 reference checking `completed/`; update post-migration [Agent 2 finding]
- `skills/update-docs/SKILL.md` — line 80 instructs scanning `.issues/completed/`; update post-migration [Agent 2 finding]
- `skills/create-eval-from-issues/SKILL.md` — line 63 references `completed/` and `deferred/`; update post-migration [Agent 2 finding]
- `skills/audit-docs/SKILL.md` — lines 216/247 reference `grep` and `git mv` against `completed/`; update post-migration [Agent 2 finding]

## Implementation Steps

1. **Create `scripts/little_loops/cli/migrate.py`** with `main_migrate() -> int`:
   - Set up argparse with `add_dry_run_arg()` and `add_config_arg()` from `cli_args.py`
   - Scan `config.get_completed_dir()` and `config.get_deferred_dir()` for `.md` files
   - For each file: call `parse_frontmatter()`, check `completed_at` field, run git-log subprocess fallback if absent (`git log --format=%as -1 -- <path>`), call `update_frontmatter()` to write `status:` and backfill `completed_at:`
   - Determine target type dir from `type:` frontmatter field (or filename parse as fallback); run `_is_git_tracked()` then `git mv` with `Path.rename` fallback
   - Collect and print: moved count, backfilled count, untyped file paths for manual review
2. **Register in `scripts/pyproject.toml`**: add `ll-migrate = "little_loops.cli:main_migrate"` to `[project.scripts]`
3. **Register in `scripts/little_loops/cli/__init__.py`**: import `main_migrate` from `little_loops.cli.migrate`, add to `__all__`
4. **Write `scripts/tests/test_issue_migration.py`** using `tmp_path` fixture:
   - Fixtures: files in `completed/` (with/without frontmatter, with/without `completed_at:`) and `deferred/` (with `status: open`)
   - Mock `subprocess.run` for git-tracked check and git-log fallback (follow `test_issue_history_parsing.py:TestParseCompletionDate` pattern)
   - Assert `status:` and `completed_at:` fields written; assert files land in type dirs; assert dry-run makes no file changes
5. **Run migration**: `ll-migrate --dry-run` first to verify, then `ll-migrate` for production
6. **Post-migration cleanup** (follow-up commits): remove git-log fallback tiers from `_parse_completion_date()`, hard-remove `get_completed_dir()`/`get_deferred_dir()` stubs from `config/core.py`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Register `ll-migrate` in all doc locations**: update `.claude/CLAUDE.md` CLI Tools list, `commands/help.md` CLI TOOLS section, `docs/reference/CLI.md`, `README.md` (count 17 → 18, add `### ll-migrate` section), and `cli/__init__.py` module docstring
8. **Update count assertions**: `skills/configure/areas.md` "Authorize all 16" → 17 (add `ll-migrate`); update `scripts/tests/test_create_extension_wiring.py` — `test_readme_tool_count_is_17` (×2) → 18 and `test_configure_areas_count_is_16` → 17
9. **(Post-migration) Update `issue_discovery/search.py`** — remove calls to `config.get_completed_dir()` and `config.get_deferred_dir()` in `get_all_issues()` **before** removing the stubs from `config/core.py`; also remove orphaned `completed_dir`/`deferred_dir` fields from `config/features.py:IssuesConfig`
10. **(Post-migration) Delete 6 tests** that will error after code removal: `TestGetCompletedDir.test_get_completed_dir` + `TestGetDeferredDir.test_get_deferred_dir` in `test_config.py`; four `TestParseCompletionDate` git-log-fallback tests in `test_issue_history_parsing.py`
11. **(Post-migration) Remove deprecated schema keys**: delete `completed_dir`/`deferred_dir` entries (lines 106–111) from `config-schema.json`

## Tests to Add

- `scripts/tests/test_issue_migration.py` (new):
  - Fixture: `tmp_path` with files in `deferred/` and `completed/` subdirs, some with/without `completed_at:`
  - Assert all files land in type dirs with correct `status:` frontmatter
  - Assert `completed_at:` is backfilled for files that were missing it
  - Assert dry-run mode makes no changes but reports correctly
  - Assert files that can't be typed are reported, not dropped

## Acceptance Criteria

- 0 files lost from `deferred/` or `completed/` during migration
- All migrated files have `status: done` or `status: deferred` set correctly
- All completed files have `completed_at:` set (either pre-existing or backfilled)
- Dry-run mode works correctly
- `completed/` and `deferred/` directories are empty (or removed) post-migration
- `ll-auto`, `ll-sprint`, and `ll-parallel` process `status: open` issues correctly after migration

## Scope Boundaries

- **In scope**: Moving files from `completed/` and `deferred/` into type directories; backfilling `completed_at:` for completed files lacking it; post-migration cleanup of deprecated `get_completed_dir()`/`get_deferred_dir()` stubs and git-log fallback tiers
- **Out of scope**: Updating discovery tools or lifecycle commands (covered by ENH-1418, ENH-1419); modifying issue file content beyond frontmatter fields; handling non-issue files that may exist in those directories; making the script reusable for future migrations

## Impact

- **Priority**: P2 — Blocked on ENH-1418 and ENH-1419; capstone step for ENH-1390 but not independently urgent until those land
- **Effort**: Medium — New CLI script + test suite; clear requirements and reuses existing `update_frontmatter()` and `_parse_completion_date()` utilities
- **Risk**: High — 1,346 files at risk of data loss if logic is incorrect; dry-run mode is mandatory before production run
- **Breaking Change**: Yes — Files physically move; any code that hardcodes `.issues/completed/` or `.issues/deferred/` paths will break

## Labels

`migration`, `decouple-status`, `issue-management`

## Resolution

Implemented `ll-migrate` as `scripts/little_loops/cli/migrate.py`. Key decisions:
- Used direct string manipulation (`_set_fields`) instead of `update_frontmatter` to avoid yaml roundtrip issues (yaml.dump quotes ISO timestamps, parse_frontmatter doesn't strip quotes)
- `_set_fields` preserves existing frontmatter values verbatim, preventing datetime reformatting
- `git mv` preferred for tracked files (preserves history); fallback to `Path.rename` for untracked
- Registered in `pyproject.toml`, `cli/__init__.py`, and all 5 doc locations; updated 3 count assertions across wiring tests

## Session Log
- `/ll:manage-issue` - 2026-05-10T22:12:31Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-05-10T21:57:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62f22df3-03b1-4da2-a95b-bb95e7af9e65.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/59c0f1a4-24eb-4243-bf34-3449d41f1dfe.jsonl`
- `/ll:wire-issue` - 2026-05-10T21:52:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08f9118c-1ea4-48e8-b5b5-0eea815b1327.jsonl`
- `/ll:refine-issue` - 2026-05-10T21:46:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/525e757d-20a6-49b8-9440-f8e278d12be7.jsonl`
- `/ll:format-issue` - 2026-05-10T15:21:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/293739bc-9ebc-4dac-a29c-99529166ae17.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cc6049e-f9fc-4387-9af6-418507182087.jsonl`

---

**Done** | Created: 2026-05-10 | Completed: 2026-05-10 | Priority: P2
