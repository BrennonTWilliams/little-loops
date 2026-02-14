# BUG-404: `/ll:review-sprint` missing from README command tables and COMMANDS.md - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-404-review-sprint-missing-from-docs.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `review_sprint` command exists in `commands/review_sprint.md` but is absent from all documentation surfaces:

### Key Discoveries
- README.md lists 36 commands across 8 categories (line 84) — `review_sprint` missing
- `create_sprint` is documented in "Planning & Implementation" at README.md:120
- docs/COMMANDS.md has "Sprint Management" section (lines 135-153) with only `create_sprint`
- docs/COMMANDS.md Quick Reference table (lines 272-311) — `review_sprint` missing
- commands/help.md "PLANNING & IMPLEMENTATION" section (lines 72-85) — `review_sprint` missing
- commands/help.md Quick Reference Table (line 191) — `review_sprint` missing
- .claude/CLAUDE.md "Planning & Implementation" list (line 53) — `review_sprint` missing

### Patterns to Follow
- README table format: `| /ll:command [args] | Short description |`
- COMMANDS.md detailed section: h3 heading, description, Arguments, optional sections, Output
- COMMANDS.md Quick Reference: `| command_name | Short description |` (no `/ll:` prefix)
- help.md listing: indented description lines under command with args
- CLAUDE.md: backtick-separated command names in category lists

## Desired End State

`review_sprint` documented in all 4 files alongside `create_sprint` in sprint-related sections.

### How to Verify
- Search each file for `review_sprint` — should have entries
- Command count in README.md updated from 36 to 37
- All formatting matches existing patterns

## What We're NOT Doing

- Not modifying the `review_sprint` command implementation itself
- Not updating CHANGELOG.md (this is a doc bug fix, not a release)
- Not restructuring existing documentation sections

## Implementation Phases

### Phase 1: Update README.md

**File**: `README.md`

1. Line 84: Change "36 slash commands" to "37 slash commands"
2. Line 120-121: Add `review_sprint` row after `create_sprint` in Planning & Implementation table:
   ```markdown
   | `/ll:review-sprint [name]` | Review sprint health and suggest improvements |
   ```

### Phase 2: Update docs/COMMANDS.md

**File**: `docs/COMMANDS.md`

1. After line 153 (after `create_sprint` section's `---`): Add new detailed section:
   ```markdown
   ### `/ll:review-sprint`
   AI-guided sprint health check that analyzes a sprint's current state and suggests improvements.

   **Arguments:**
   - `sprint_name` (optional): Sprint name to review (e.g., "my-sprint"). If omitted, lists available sprints.

   **Trigger keywords:** "review sprint", "sprint health", "sprint review", "check sprint", "sprint suggestions", "optimize sprint"

   **Output:** Recommendations for removing stale issues, adding related backlog issues, and resolving dependency or contention problems.

   ---
   ```

2. After line 310 (`create_sprint` in Quick Reference): Add:
   ```markdown
   | `review_sprint` | Review sprint health and suggest improvements |
   ```

### Phase 3: Update commands/help.md

**File**: `commands/help.md`

1. After line 75 (after `create_sprint` entry): Add:
   ```
   /ll:review-sprint [sprint_name]
       AI-guided sprint health check and optimization
   ```

2. Line 191: Add `review_sprint` to Planning & Implementation quick reference list

### Phase 4: Update .claude/CLAUDE.md

**File**: `.claude/CLAUDE.md`

1. Line 53: Add `review_sprint` to Planning & Implementation list after `create_sprint`

### Success Criteria

- [ ] All 4 files contain `review_sprint` documentation
- [ ] README command count updated to 37
- [ ] Formatting matches existing patterns in each file
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
