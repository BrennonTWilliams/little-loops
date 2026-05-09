---
id: ENH-1390
type: ENH
priority: P2
status: open
captured_at: "2026-05-09T20:26:09Z"
discovered_date: "2026-05-09"
discovered_by: capture-issue
relates_to: [FEAT-1389, ENH-1391, ENH-1392, ENH-1393]
---

# ENH-1390: Decouple Issue Status from Directory Structure

## Summary

Remove `deferred/` and `completed/` as lifecycle-state directories. Encode status exclusively in issue frontmatter (`status:` field). Keep type directories (`features/`, `bugs/`, `enhancements/`) since type is stable and aids human navigation. This eliminates the fundamental mixing of *type* and *state* in the directory structure that breaks sync compatibility with all major platforms.

## Current Behavior

The `.issues/` directory mixes two orthogonal concerns:

- **Type directories** (stable): `features/`, `bugs/`, `enhancements/`
- **State directories** (volatile): `deferred/`, `completed/`

Moving an issue to `deferred/` or `completed/` requires a file rename/move, which: (a) breaks git blame/log continuity, (b) requires sync tools to detect moves rather than status field changes, and (c) is inconsistent with how every major platform represents state (GitHub open/closed, JIRA status field, ADO state field, Linear status field).

## Expected Behavior

- `deferred/` and `completed/` directories are removed as active-use state containers
- All issues live in their type directory (`features/`, `bugs/`, `enhancements/`, `epics/`) for their entire lifecycle
- Status is tracked exclusively via `status: open | in_progress | blocked | deferred | done | cancelled` in frontmatter
- `ll-issues list` supports `--status deferred` and `--status done` filters
- `ll-auto`, `ll-sprint`, and `ll-parallel` filter by `status: open` rather than directory inclusion
- Existing files in `deferred/` and `completed/` are migrated to their type directories with `status:` set appropriately

## Motivation

- **Git history**: A status change should be a frontmatter edit, not a file move. `git log --follow` can track renames but it's lossy and tooling-dependent.
- **Sync compatibility**: All platforms (GitHub, JIRA, ADO, Linear) represent status as a field, never as a file location. `ll-sync` currently has to detect directory moves to update remote status; with status in frontmatter it becomes a simple field diff.
- **Consistency**: The current model is internally inconsistent — issues start in a type directory, get moved to a state directory, and there's no single canonical location. "Where is issue 1073?" requires checking multiple directories.
- **EPIC support**: With the addition of EPIC type (FEAT-1389), epics need their own lifecycle (deferred epics should stay in `epics/`, not move to `deferred/`).

## Proposed Solution

1. Extend the `status:` frontmatter field with the full vocabulary: `open | in_progress | blocked | deferred | done | cancelled`
2. Update all tooling to filter by `status:` instead of directory:
   - `ll-auto` and `ll-sprint`: process issues where `status: open`
   - `ll-issues list`: default to showing `open` + `in_progress`; `--status all` shows everything
3. Migrate existing files: move all files from `deferred/` into their type directories with `status: deferred`; move `completed/` files with `status: done`
4. Keep `completed/` and `deferred/` as empty archived directories (or remove entirely) after migration
5. Update all documentation, skills, and commands that reference `deferred/` or `completed/` paths

## API/Interface

Extension to issue frontmatter `status:` field vocabulary:

```yaml
# Extended status enum (new values: in_progress, blocked, done, cancelled)
status: open | in_progress | blocked | deferred | done | cancelled
```

`ll-issues list` CLI argument:

```
ll-issues list [--status <open|in_progress|blocked|deferred|done|cancelled|all>]
# Default (no flag): shows open + in_progress
```

## Scope Boundaries

- **In scope**: Extending `status:` frontmatter enum; updating issue discovery in `issue_manager.py`, `ll-auto`, `ll-sprint`, `ll-parallel` to filter by `status:` field; migrating existing files from `deferred/` and `completed/`; updating `ll-issues list` with `--status` filter; updating docs, skills, and commands referencing state directories
- **Out of scope**: Changing type directories (`features/`, `bugs/`, `enhancements/`) or their role; redesigning `ll-sync` protocol beyond status field mapping; building a status visualization UI; changing issue filename format or ID scheme

## Success Metrics

- **Migration**: 0 files lost from `deferred/` or `completed/` during migration; all migrated files have correct `status:` set (`deferred` or `done`)
- **Discovery**: `ll-auto`, `ll-sprint`, and `ll-parallel` process `status: open` issues and skip `status: deferred` / `status: done` issues
- **Sync**: `ll-sync` maps `status: done` → remote closed and `status: open` → remote open without directory checks
- **Regression**: All existing tests pass; no issue discovery regressions across tools

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — filter by `status:` field, not directory
- `scripts/little_loops/cli/issues.py` — `list` command status filtering
- `scripts/little_loops/parallel/` — worktree/parallel runner issue discovery
- `skills/capture-issue/SKILL.md` — remove `deferred/` reopen flow (replace with status field update)
- `scripts/little_loops/cli/sync.py` — status mapping from field instead of directory
- `docs/ARCHITECTURE.md`, `docs/reference/API.md` — update directory structure docs
- `config-schema.json` — add `status` enum to issue schema

### Migration Script Needed
- One-time script to move files from `deferred/` and `completed/` into type directories with correct `status:` frontmatter

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "completed\|deferred" scripts/little_loops/ --include="*.py"`
- `scripts/little_loops/cli/auto.py` — issue selection loop (filters by directory today)
- `scripts/little_loops/cli/sprint.py` — issue set execution (directory-based exclusion)

### Similar Patterns
- `ll-issues path` and `ll-issues show` — may use directory-based lookups; check for consistency
- Any skill referencing `config.issues.completed_dir` or `config.issues.deferred_dir` config keys

### Tests
- TBD - `scripts/tests/` — update tests that assert on `deferred/` or `completed/` directory paths
- Add integration tests for `status:` filtering in `issue_manager.py` and `ll-issues list`
- Add migration script test with fixture files in `deferred/` and `completed/`

### Documentation
- `docs/ARCHITECTURE.md` — remove state directories from directory structure diagram
- `docs/reference/API.md` — update `status` field documentation and valid values
- `skills/format-issue/SKILL.md`, `skills/ready-issue/SKILL.md` — remove references to `completed_dir`/`deferred_dir`

### Configuration
- `config-schema.json` — extend `status` enum; deprecate or remove `completed_dir` and `deferred_dir` keys
- `.ll/ll-config.json` — `issues.completed_dir` and `issues.deferred_dir` settings become obsolete post-migration

## Implementation Steps

1. Extend `status:` enum in schema and validation: `open | in_progress | blocked | deferred | done | cancelled`
2. Update `issue_manager.py` issue discovery to filter on `status: open` instead of excluding `deferred/` and `completed/` directories
3. Update `ll-issues list` to support `--status <value>` filter; default view shows open/in_progress
4. Write and run migration script for existing `deferred/` and `completed/` files
5. Update `capture-issue` skill: "reopen completed issue" becomes a `status:` field update, not a file move
6. Update `ll-sync` to read `status:` field for open/closed mapping
7. Remove `deferred/` and `completed/` from ARCHITECTURE.md and other docs
8. Update tests that assert on directory paths

## Impact

- **Priority**: P2 — prerequisite for meaningful `ll-sync` and EPIC support
- **Effort**: Medium — code changes are straightforward; migration of ~60 existing files is the main risk
- **Risk**: Medium — touches all tooling that does issue discovery; comprehensive test coverage needed before migration

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover relevant docs._

## Labels

`issue-model`, `sync-compatibility`, `migration`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-09T20:39:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf87852d-ec5b-4a4d-959f-57a040534f19.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:26:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e536be3e-1c62-4dcb-81f6-419c8b29e71f.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P2
