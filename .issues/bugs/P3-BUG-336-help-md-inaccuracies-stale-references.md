---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# BUG-336: help.md contains multiple stale and missing references

## Summary

The `/ll:help` command output (`commands/help.md`) has several inaccuracies: a missing skill listing, a reference to a nonexistent CLI tool, a missing CLI tool reference, and a command listed as plugin-level that actually lives in user-level config.

## Current Behavior

1. **`confidence-check` skill not listed** — The skill was added in commit `6167da2` but never added to `help.md`. All other 6 skills are referenced.
2. ~~**`ll-sync` CLI referenced but doesn't exist**~~ — **INVALID**: `ll-sync` entry point DOES exist in `pyproject.toml` line 53 (`ll-sync = "little_loops.cli:main_sync"`). This item is not a bug.
3. **`ll-messages` CLI not referenced** — This CLI tool is a prerequisite for `/ll:analyze-workflows` but isn't mentioned in help.md.
4. **`analyze_log` listed as plugin command** — `help.md` line 86 lists `/ll:analyze_log` but it lives in `.claude/commands/analyze_log.md` (user-level), not in the plugin `commands/` directory.

## Expected Behavior

1. `confidence-check` should be listed in help.md (e.g., under Planning & Implementation alongside `ready_issue`)
2. ~~Remove the `ll-sync` CLI reference~~ — N/A, `ll-sync` entry point exists
3. Add `ll-messages` as a referenced CLI tool (under Meta-Analysis near `analyze-workflows`)
4. Either move `analyze_log` into the plugin `commands/` directory or remove it from `help.md`

## Steps to Reproduce

1. Run `/ll:help` to view command reference
2. Check for `confidence-check` skill — not listed anywhere
3. Check for `ll-messages` CLI reference — not listed
4. Note `analyze_log` is listed as plugin command but lives in `.claude/commands/`

## Actual Behavior

`help.md` contains 3 inaccuracies: a missing skill reference, a missing CLI tool reference, and a command listed under the wrong scope.

## Proposed Solution

Edit `commands/help.md` to fix all four references. For item 4, the simplest fix is moving `analyze_log.md` from `.claude/commands/` into the plugin `commands/` directory.

### Implementation Steps

1. Add `confidence-check` skill reference to help.md
2. ~~Remove `ll-sync` reference~~ — N/A, already exists
3. Add `ll-messages` CLI reference under Meta-Analysis
4. Move `analyze_log.md` to plugin commands dir or remove from help

## Impact

- **Scope**: Documentation accuracy
- **Severity**: Low — users may be confused by stale references but functionality works

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Lists CLI tools and command categories |
| guidelines | CONTRIBUTING.md | Development setup references |

## Labels

`bug`, `documentation`, `captured`

---

## Status

**Completed** | Created: 2026-02-11 | Completed: 2026-02-11 | Priority: P3

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-11
- **Status**: Completed

### Changes Made
- `commands/help.md`: Added `confidence-check` skill to Issue Refinement skills list
- `commands/help.md`: Added `ll-messages` CLI to Meta-Analysis CLI list
- `commands/help.md`: Removed `analyze_log` (user-level command, not plugin command)
- `commands/help.md`: Moved `product-analyzer` skill from orphaned position to `scan_product`

### Verification Results
- Tests: N/A (documentation only)
- Lint: N/A
- Types: N/A
