---
id: ENH-1420
type: ENH
priority: P2
status: open
parent_issue: ENH-1390
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

## Files to Create / Modify

- `scripts/little_loops/cli/migrate_issue_dirs.py` (new) — migration script with dry-run mode
- `scripts/little_loops/issue_history/parsing.py` — remove git-log fallback tiers after migration (post-migration cleanup step, can be a follow-up commit)
- `scripts/little_loops/config/core.py` — remove `get_completed_dir()`/`get_deferred_dir()` stubs (post-migration cleanup)

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

## Session Log
- `/ll:format-issue` - 2026-05-10T15:21:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/293739bc-9ebc-4dac-a29c-99529166ae17.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cc6049e-f9fc-4387-9af6-418507182087.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2
