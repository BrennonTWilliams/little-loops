# BUG-317: README command tables missing 4 of 34 commands - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P2-BUG-317-readme-command-tables-missing-4-commands.md
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

README.md has 6 command category tables (lines 390-454) listing 30 commands, but claims 34 slash commands exist. Four commands are missing from the tables while being present in `docs/COMMANDS.md` and `commands/`.

### Key Discoveries
- Issue Management table: lines 413-426 (12 commands) — missing `tradeoff_review_issues`
- Git & Workflow table: lines 440-445 (4 commands) — missing `open_pr`, `manage_release`, `loop-suggester`
- All 4 commands have proper command files in `commands/` and entries in `docs/COMMANDS.md`

## Desired End State

All 34 commands appear in the README command tables. Count matches stated "34 slash commands".

### How to Verify
- `grep -cE '^\| .*/ll:' README.md` should return 34
- Each missing command appears in its appropriate category table

## What We're NOT Doing

- Not reorganizing categories or creating new sections — keep it simple
- Not changing docs/COMMANDS.md (already correct)
- Not updating command counts (already says 34)

## Solution Approach

Add 4 table rows to existing category tables in README.md:
1. `/ll:tradeoff-review-issues` → Issue Management (after `create_sprint`)
2. `/ll:open-pr [target_branch]` → Git & Workflow (after `commit`)
3. `/ll:manage-release [action] [version]` → Git & Workflow (after `open_pr`)
4. `/ll:loop-suggester [file]` → Git & Workflow (after `create_loop`)

## Implementation Phases

### Phase 1: Add missing commands to README tables

**File**: `README.md`

**Change 1**: Add `tradeoff_review_issues` to Issue Management table after line 426 (`create_sprint`)

```markdown
| `/ll:tradeoff-review-issues` | Evaluate issues for utility vs complexity |
```

**Change 2**: Add `open_pr` and `manage_release` to Git & Workflow table after line 442 (`commit`)

```markdown
| `/ll:open-pr [target_branch]` | Open pull request for current branch |
| `/ll:manage-release [action] [version]` | Manage releases, tags, and changelogs |
```

**Change 3**: Add `loop-suggester` to Git & Workflow table after line 445 (`create_loop`)

```markdown
| `/ll:loop-suggester [file]` | Suggest FSM loops from message history |
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -cE '^\| .*/ll:' README.md` returns 34
- [ ] All 4 missing commands appear in output of `grep '/ll:open-pr\|/ll:manage-release\|/ll:loop-suggester\|/ll:tradeoff_review' README.md`

## References

- Original issue: `.issues/bugs/P2-BUG-317-readme-command-tables-missing-4-commands.md`
- Command reference: `docs/COMMANDS.md`
- Command files: `commands/open_pr.md`, `commands/manage_release.md`, `commands/loop-suggester.md`, `commands/tradeoff_review_issues.md`
