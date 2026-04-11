---
id: ENH-1020
type: ENH
priority: P3
status: backlog
discovered_date: 2026-04-10
discovered_by: capture-issue
---

# ENH-1020: Fix /ll:update to properly update little-loops in consumer projects

## Summary

`/ll:update` is designed for the little-loops source repo (version bumping `plugin.json`, updating `marketplace.json`), so when run in consumer projects it skips marketplace and plugin steps entirely and only attempts a package update — poorly. The skill needs to be split: consumer-facing update logic (upgrade pip package, refresh Claude Code plugin) should become the primary behavior, and source-repo-only steps (marketplace/plugin version bumping) should move to a separate internal command.

## Current Behavior

When `/ll:update` runs in a consumer repo:
- Prints "This is a consumer repo — skipping marketplace and plugin steps"
- `MARKETPLACE_RESULT="SKIP"`
- `PLUGIN_RESULT="SKIP"`
- Attempts package update but has a logic bug: detects `./scripts/` directory and assumes it's a dev install, then falls back to `pip install --upgrade little-loops` only after realizing the scripts dir isn't the package source
- Produces a confusing output with two SKIP results and no actionable guidance

## Expected Behavior

When `/ll:update` runs in any repo (consumer or source):
- Upgrades the installed `little-loops` pip package via `pip install --upgrade little-loops`
- Updates the `ll@little-loops` Claude Code plugin via `claude plugin update ll@little-loops`
- Reports current → new version for both
- Source-repo-only steps (bump `plugin.json` version, sync `marketplace.json`) live in a separate command (e.g., `commands/ll-publish.md` or similar) that is only relevant to maintainers

## Motivation

Every end-user of little-loops runs `/ll:update` in their own project, not in the source repo. The current skill is backwards: it optimizes for the maintainer workflow and degrades for the common case. Users see two SKIP lines and no clear path to actually getting updated. Moving source-repo steps out also simplifies the skill considerably and removes the confusing is-source-repo branching logic.

## Proposed Solution

1. **Rewrite `skills/update/SKILL.md`** to target consumer repos as the primary path:
   - Remove the is-source-repo detection guard entirely from the main update flow
   - Step A: `pip install --upgrade little-loops` (always)
   - Step B: `claude plugin update ll@little-loops` (always, same as existing Step 4 logic)
   - Remove Step 3 (marketplace update) and Step 4's plugin.json version check from this skill

2. **Create `commands/ll-publish.md`** (or similar internal command) with the source-repo-only operations:
   - Bump `plugin.json` version
   - Sync `marketplace.json` version
   - This command can guard with `if [ ! -f ".claude-plugin/plugin.json" ]; then echo "Not in little-loops source repo"; exit 1; fi`

3. **Fix the `./scripts/` dev-install detection bug** in the package update step:
   - Presence of `./scripts/` should not be used to infer a dev install — check for `pip show -e` or `pip list --format=json` for editable installs instead

## Integration Map

### Files to Modify
- `skills/update/SKILL.md` — rewrite to consumer-first logic, remove source-repo guards

### New Files
- `commands/ll-publish.md` (or `commands/ll-release-publish.md`) — extract marketplace + plugin.json version bump logic here

### Dependent Files (Callers/Importers)
- `skills/manage-release/SKILL.md` — may call or reference update steps; check for cross-references
- `commands/ll-update.md` — if a separate command wrapper exists

### Tests
- `scripts/tests/test_update_skill.py` — if tests exist for update behavior

### Documentation
- `docs/reference/API.md` — update any mention of `/ll:update` behavior
- `CLAUDE.md` — skill description under "Git & Release" section

### Configuration
- N/A

## Implementation Steps

1. Read full `skills/update/SKILL.md` to inventory all logic branches
2. Identify which steps belong to consumer path vs. source-repo path
3. Rewrite `skills/update/SKILL.md` with consumer-first logic (no is-source-repo gate)
4. Create new command file for source-repo publish operations
5. Fix `./scripts/` dev-install detection logic in the package step
6. Verify the new update skill works in a consumer test repo (`loop-viz` or similar)
7. Update any docs that reference `/ll:update` behavior

## Impact

- **Users affected**: All end-users of little-loops (every consumer project)
- **Risk**: Low — split is clean, no shared state between the two paths
- **Benefit**: `/ll:update` becomes a single useful command for the 99% case; maintainer publish workflow gets its own clear home

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/update/SKILL.md` | Primary file being changed |
| `docs/ARCHITECTURE.md` | Skills vs Commands distinction |
| `.claude/CLAUDE.md` | "Prefer Skills over Agents" guidance |

## Labels

`skill`, `update`, `consumer-ux`, `refactor`

## Status

> backlog

## Session Log
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1742fd85-5820-4a26-bdfa-11b23824f386.jsonl`
