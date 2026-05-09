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
- `/ll:capture-issue` - 2026-05-09T20:26:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e536be3e-1c62-4dcb-81f6-419c8b29e71f.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P2
