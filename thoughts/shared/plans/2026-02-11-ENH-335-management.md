# ENH-335: Organize docs with command and skill groupings - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-335-organize-docs-with-command-and-skill-groupings.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

Four files list commands/skills/CLI tools in flat or partially-grouped tables:
- `README.md:448-518` - Commands in 5 groups (Setup, Code Quality, Issue Management, Documentation & Analysis, Git & Workflow, Session Management), but missing many newer commands
- `docs/ARCHITECTURE.md` - No command listing (just component tables)
- `.claude/CLAUDE.md:48-54` - Flat list of key commands only
- `commands/help.md:14-133` - Commands in 6 groups, missing many newer commands

## Desired End State

All four files reorganize commands/skills/CLI tools under 9 capability groupings from the issue.

## What We're NOT Doing

- Not changing command/skill names or moving files
- Not creating new documentation files
- Not changing help command logic
- Not modifying ARCHITECTURE.md beyond adding grouped command/skill reference (it's mostly diagrams)

## Implementation Phases

### Phase 1: Update `commands/help.md`

Reorganize the command reference output and quick reference table under the 9 groupings. Add all missing commands (manage_release, sync_issues, create_sprint, cleanup_worktrees, create_loop, loop-suggester, scan_product, refine_issue, configure, analyze-workflows).

### Phase 2: Update `README.md`

Reorganize the Commands section (lines 448-518) under the 9 groupings. Add missing commands. Update Skills section to note which grouping each skill belongs to.

### Phase 3: Update `.claude/CLAUDE.md`

Reorganize the Commands section to use grouped format.

### Phase 4: Update `docs/ARCHITECTURE.md`

ARCHITECTURE.md doesn't have a command listing to reorganize - skip or add minimal grouped reference if appropriate. Decision: skip (it's focused on system design, not user-facing command reference).

## Success Criteria
- [ ] All commands/skills/CLI tools appear in at least one grouping
- [ ] No commands are missing from help.md
- [ ] Consistent grouping names across all files
