---
discovered_date: 2026-02-18
discovered_by: capture-issue
---

# FEAT-441: Support Deferred Issues Folder

## Summary

Add a `.issues/deferred/` folder as a holding ground for issues that are intentionally set aside — not ready for active work but not closed. Deferred issues must not be counted in Open/Active Issues or Completed Issues by any CLI tool or skill that aggregates issue counts.

## Current Behavior

Issues can only exist in three active directories (`bugs/`, `features/`, `enhancements/`) or `completed/`. There is no intermediate state for issues that are intentionally set aside. Users who want to "park" an issue must either close it (falsely implying resolution) or leave it in the active backlog, where it pollutes sprint planning, prioritization runs, and issue counts.

## Expected Behavior

A `.issues/deferred/` directory serves as a holding ground for parked issues. All CLI tools, skills, and count-reporting commands treat `deferred/` as non-active (same pattern as `completed/`): skipped by `ll-auto`, `ll-sprint`, `ll-parallel`, and all issue enumeration. Users can move issues to deferred via `manage-issue defer [ID]` and restore them via `manage-issue undefer [ID]`.

## Motivation

Currently, there is no way to "park" an issue without either closing it (implying it's resolved) or leaving it in an active folder (implying it's ready to work on). A deferred state lets users set aside low-priority, blocked, or uncertain issues without polluting the active backlog or losing the context they've captured.

## Use Case

A user discovers a potential improvement but cannot work on it until a dependency ships. They want to keep the issue for reference without it appearing in sprint planning, prioritization runs, or active issue counts. They run `/ll:manage-issue defer FEAT-441` and the issue moves to `.issues/deferred/` where it's ignored by `ll-auto`, `ll-sprint`, `ll-parallel`, and all count-reporting tools.

## Acceptance Criteria

- [ ] `.issues/deferred/` directory is created (with `.gitkeep`) as part of this feature
- [ ] `ll-auto`, `ll-sprint`, `ll-parallel` skip issues in `deferred/` by default
- [ ] All skill/command issue enumeration excludes `deferred/` (same pattern as `completed/`)
- [ ] `manage-issue defer [ID]` moves an issue from its active directory to `deferred/`
- [ ] `manage-issue undefer [ID]` moves an issue from `deferred/` back to its original category directory
- [ ] `capture-issue` duplicate detection optionally surfaces deferred issues as candidates for un-deferral
- [ ] `ll-history`, `ll-next-id`, and count-reporting tools exclude deferred from active counts
- [ ] Documentation updated in `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`, `README.md`

## Proposed Solution

1. Create `.issues/deferred/` as a recognized issue directory (alongside `bugs/`, `features/`, `enhancements/`, `completed/`).
2. Update all CLI tools and skills that enumerate active issues to exclude `deferred/` (same pattern used to exclude `completed/`).
3. Add a `defer` action to `manage-issue` (and optionally `ll-auto`/`ll-sprint`) to move an issue into `deferred/`.
4. Add an `undefer` action to move an issue back to its original category directory.
5. Update count-reporting commands (`ll-history`, `capture-issue` duplicate scan, `prioritize-issues`, etc.) to exclude the deferred folder.
6. Document the deferred state in `docs/ARCHITECTURE.md` and `CONTRIBUTING.md`.

## Implementation Steps

1. Create `.issues/deferred/` directory (add a `.gitkeep`).
2. Update `config-schema.json` to document `deferred` as a recognized folder alongside `completed`.
3. Audit all places that enumerate issue dirs in `scripts/little_loops/` — add `deferred` to the exclusion list wherever `completed` is excluded.
4. Add `defer` / `undefer` actions to the `manage-issue` skill.
5. Update `ll-auto` and `ll-sprint` to skip deferred issues.
6. Update `capture-issue` duplicate detection to skip deferred folder (or optionally surface deferred as a candidate for un-deferral).
7. Update `ll-history`, `ll-next-id`, and any other count-reporting tools.
8. Add tests for new behavior.
9. Update documentation.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — exclude deferred from active issue enumeration
- `scripts/little_loops/cli.py` / CLI entry points — add defer/undefer subcommands
- `scripts/little_loops/sprint_manager.py` — skip deferred issues
- `scripts/little_loops/orchestrator.py` — skip deferred issues
- `skills/capture-issue/SKILL.md` — update duplicate scan logic
- `skills/manage-issue/SKILL.md` — add defer/undefer actions
- `config-schema.json` — document deferred dir
- `docs/ARCHITECTURE.md` — document issue lifecycle states
- `CONTRIBUTING.md` — document deferred folder

### Dependent Files (Callers/Importers)
- TBD - use grep to find all places that enumerate `.issues/` subdirectories

### Similar Patterns
- `completed/` exclusion logic throughout codebase

### Tests
- `scripts/tests/` — add tests for defer/undefer actions and exclusion behavior

### Documentation
- `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`, `README.md`

### Configuration
- `config-schema.json` — add `deferred_dir` field (default: `deferred`)

## API/Interface

```python
# Issue lifecycle: open -> deferred -> open (undefer) | open -> completed
# New CLI usage:
#   ll-auto --exclude-deferred  (default behavior)
#   manage-issue defer FEAT-441
#   manage-issue undefer FEAT-441
```

## Impact

- **Priority**: P3 — Reduces backlog noise; no blocking impact on current work
- **Effort**: Medium — Touches multiple CLI tools, skills, and documentation
- **Risk**: Low — Additive change; deferred folder is simply excluded like completed
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Issue lifecycle and directory structure |
| `CONTRIBUTING.md` | Development guidelines |
| `.claude/CLAUDE.md` | Issue file format and directory layout |

## Labels

`feature`, `issue-management`, `cli`, `backlog`

---

## Verification Notes

_Verified: 2026-02-22_

**Integration Map file paths corrected:**

Three paths listed under "Files to Modify" do not exist at the stated locations:

| Listed Path | Actual Path |
|-------------|-------------|
| `scripts/little_loops/cli.py` | `scripts/little_loops/cli/` (package directory — entry points are `cli/auto.py`, `cli/sprint.py`, `cli/parallel.py`, etc.) |
| `scripts/little_loops/sprint_manager.py` | `scripts/little_loops/sprint.py` (core sprint logic) + `scripts/little_loops/cli/sprint.py` (CLI entry point) |
| `scripts/little_loops/orchestrator.py` | `scripts/little_loops/parallel/orchestrator.py` |

All other referenced files exist at their stated paths.

## Session Log
- `/ll:capture-issue` - 2026-02-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/28564d89-65ed-40b1-b496-7da3bcf0a373.jsonl`
- `/ll:verify-issues` - 2026-02-22 - verification pass
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`

---

## Status

**Open** | Created: 2026-02-18 | Priority: P3
