# BUG-110: COMMANDS.md missing create_sprint command - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-110-commands-md-missing-create-sprint-command.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `docs/COMMANDS.md` file documents all `/ll:` commands but is missing the `/ll:create-sprint` command. The command definition exists at `.claude/commands/create_sprint.md`.

### Key Discoveries
- Quick Reference table has 24 commands (lines 177-205) but excludes `create_sprint`
- The command creates sprint definitions with curated issue lists
- Command belongs logically with sprint/issue management commands

## Desired End State

The `/ll:create-sprint` command is fully documented in `docs/COMMANDS.md`:
1. Listed in the Quick Reference table
2. Has a full section with description, arguments, and usage

### How to Verify
- The command appears in the Quick Reference table
- A detailed section exists with arguments and description

## What We're NOT Doing

- Not modifying the command definition itself
- Not changing any Python code
- Not adding examples to the Common Workflows section (optional enhancement)

## Solution Approach

Add documentation for `/ll:create-sprint` in two places:
1. Add a new "Sprint Management" section after "Issue Management" (since sprints are related but distinct)
2. Add entry to Quick Reference table

## Implementation Phases

### Phase 1: Add Sprint Management Section

#### Overview
Add a new section documenting the `/ll:create-sprint` command.

#### Changes Required

**File**: `docs/COMMANDS.md`
**Location**: After line 98 (after `/ll:iterate-plan` section, before `## Auditing & Analysis`)

```markdown
---

## Sprint Management

### `/ll:create-sprint`
Create a sprint definition with a curated list of issues.

**Arguments:**
- `name` (required): Sprint name (e.g., "sprint-1", "q1-bug-fixes")
- `description` (optional): Description of the sprint's purpose
- `issues` (optional): Comma-separated list of issue IDs (e.g., "BUG-001,FEAT-010")

**Interactive Mode:** If issues are not provided, the command will help select issues interactively.

**Output:** Creates `.sprints/<name>.yaml` with issue list and execution options.
```

#### Success Criteria

**Automated Verification**:
- [ ] File is valid markdown (no syntax errors)

**Manual Verification**:
- [ ] Section appears in correct location
- [ ] Arguments match command definition

### Phase 2: Add Quick Reference Entry

#### Overview
Add `create_sprint` to the Quick Reference table.

#### Changes Required

**File**: `docs/COMMANDS.md`
**Location**: In Quick Reference table, after `create_loop` entry (line 204)

Add:
```markdown
| `create_sprint` | Create sprint with curated issue list |
```

#### Success Criteria

**Automated Verification**:
- [ ] File is valid markdown

**Manual Verification**:
- [ ] Entry appears in table
- [ ] Description is concise and accurate

## Testing Strategy

This is a documentation-only change. Verification is visual inspection.

## References

- Original issue: `.issues/bugs/P2-BUG-110-commands-md-missing-create-sprint-command.md`
- Command definition: `.claude/commands/create_sprint.md`
