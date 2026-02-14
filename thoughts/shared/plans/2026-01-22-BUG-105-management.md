# BUG-105: create_sprint references undefined --priority argument - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-105-ll-create-sprint-references-undefined-priority-argument.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `/ll:create-sprint` command at `.claude/commands/create_sprint.md` contains three examples in the Examples section (lines 147-156):

1. Line 149: `/ll:create-sprint sprint-1 --issues "BUG-001,BUG-002,FEAT-010" --description "Q1 fixes"` - **Valid**
2. Line 152: `/ll:create-sprint q1-features --description "Q1 feature work"` - **Valid**
3. Line 155: `/ll:create-sprint critical-fixes --priority P0` - **Invalid - argument not defined**

### Key Discoveries
- The `--issues` and `--description` arguments are defined in frontmatter (lines 7-12)
- No `--priority` argument is defined in the frontmatter
- The `--priority` flag exists in the `ll-parallel` CLI tool (scripts/little_loops/cli.py:130) but NOT in the slash command
- The comment at line 154 says "Create sprint with all P0 bugs" suggesting automatic filtering, which the command does support via interactive selection (Option A: "Select by priority" at line 55)

## Desired End State

The Examples section should only show commands that use defined arguments.

### How to Verify
- All examples in the file use only arguments defined in frontmatter
- The file passes any linting/validation checks

## What We're NOT Doing

- Not implementing the `--priority` argument (that would be a feature enhancement, not a bug fix)
- Not modifying the interactive selection process (it already supports priority-based selection)
- Not refactoring the entire Examples section

## Problem Analysis

The example at line 155 references `--priority P0` which is not a defined argument. This misleads users who might try to use this syntax. The functionality for selecting issues by priority exists in the interactive mode (line 55: "Select by priority"), so users can achieve the same result by not providing the `--issues` argument and selecting interactively.

## Solution Approach

Remove the invalid example (lines 154-155) from the Examples section. The simpler approach preserves the valid examples while eliminating the misleading one.

## Implementation Phases

### Phase 1: Remove Invalid Example

#### Overview
Remove the invalid `--priority P0` example from the Examples section.

#### Changes Required

**File**: `.claude/commands/create_sprint.md`
**Changes**: Remove lines 154-155 (the comment and the invalid example)

Current content (lines 145-156):
```markdown
## Examples

```bash
# Create sprint with explicit issue list
/ll:create-sprint sprint-1 --issues "BUG-001,BUG-002,FEAT-010" --description "Q1 fixes"

# Create sprint interactively (select issues)
/ll:create-sprint q1-features --description "Q1 feature work"

# Create sprint with all P0 bugs
/ll:create-sprint critical-fixes --priority P0
```
```

After edit (lines 145-153):
```markdown
## Examples

```bash
# Create sprint with explicit issue list
/ll:create-sprint sprint-1 --issues "BUG-001,BUG-002,FEAT-010" --description "Q1 fixes"

# Create sprint interactively (select issues)
/ll:create-sprint q1-features --description "Q1 feature work"
```
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] No `--priority` appears in examples section

**Manual Verification**:
- [ ] The remaining examples only use `--issues` and `--description` arguments
- [ ] The file is syntactically valid markdown

---

## Testing Strategy

### Verification
- Grep the file for `--priority` to ensure it's no longer in the examples section
- Visually confirm the examples match defined arguments

## References

- Original issue: `.issues/bugs/P2-BUG-105-ll-create-sprint-references-undefined-priority-argument.md`
- Similar command argument patterns: `commands/manage_issue.md:1-18`
- Related completed bugs: `.issues/completed/P2-BUG-104-ll-create-sprint-examples-show-wrong-command-name.md`
