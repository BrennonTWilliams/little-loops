# BUG-104: ll_create_sprint examples show wrong command name - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-104-ll-create-sprint-examples-show-wrong-command-name.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The command file is named `ll_create_sprint.md`, making the actual invocation `/ll:ll_create_sprint`. However, the examples within the file show `/ll:create-sprint` which doesn't match.

### Key Discoveries
- Command file: `.claude/commands/ll_create_sprint.md`
- Lines 149, 152, 155 contain incorrect examples using `/ll:create-sprint`
- The issue recommends Option 1: Rename file to `create_sprint.md` (removes redundant `ll_` prefix)
- Multiple other issue files reference this command and will need updates

### Files Requiring Updates
1. `.claude/commands/ll_create_sprint.md` → rename to `create_sprint.md`
2. Update examples in the renamed file from `/ll:create-sprint` to `/ll:create_sprint`
3. Update references in related issue files:
   - `.issues/bugs/P2-BUG-105-ll-create-sprint-references-undefined-priority-argument.md`
   - `.issues/enhancements/P3-ENH-106-ll-create-sprint-uses-unsupported-template-syntax.md`
   - `.issues/enhancements/P3-ENH-107-add-sprints-configuration-to-config-schema.md`
   - `.issues/enhancements/P4-ENH-108-ll-create-sprint-use-claude-tools-instead-of-bash.md`

## Desired End State

- Command file renamed to `create_sprint.md`
- All examples use `/ll:create_sprint` (consistent with filename)
- Related issue files updated to reference the new command name
- No broken references remain

### How to Verify
- Command file exists at new path
- Examples in command file match the invocation pattern
- No references to old command name remain in active issue files

## What We're NOT Doing

- Not changing command functionality
- Not updating completed issue files (they're historical records)
- Not updating plan files (they're historical records)
- Not fixing BUG-105 (undefined --priority argument) - separate issue

## Problem Analysis

The root cause is a naming inconsistency: the file was named `ll_create_sprint.md` but examples used `/ll:create-sprint`. This creates user confusion and failed command invocations.

## Solution Approach

1. Rename the command file to remove the redundant `ll_` prefix
2. Update examples to use underscores (`create_sprint`) to match filename
3. Update references in active issue files for consistency

## Implementation Phases

### Phase 1: Rename Command File

#### Overview
Rename the command file using git mv to preserve history.

#### Changes Required

**File**: `.claude/commands/ll_create_sprint.md` → `.claude/commands/create_sprint.md`

```bash
git mv .claude/commands/ll_create_sprint.md .claude/commands/create_sprint.md
```

#### Success Criteria

**Automated Verification**:
- [ ] New file exists: `ls .claude/commands/create_sprint.md`
- [ ] Old file doesn't exist: `! ls .claude/commands/ll_create_sprint.md 2>/dev/null`

---

### Phase 2: Update Examples in Command File

#### Overview
Fix the three example lines to use `/ll:create_sprint` instead of `/ll:create-sprint`.

#### Changes Required

**File**: `.claude/commands/create_sprint.md`
**Lines**: 149, 152, 155

```markdown
# Before:
/ll:create-sprint sprint-1 --issues "BUG-001,BUG-002,FEAT-010" --description "Q1 fixes"
/ll:create-sprint q1-features --description "Q1 feature work"
/ll:create-sprint critical-fixes --priority P0

# After:
/ll:create_sprint sprint-1 --issues "BUG-001,BUG-002,FEAT-010" --description "Q1 fixes"
/ll:create_sprint q1-features --description "Q1 feature work"
/ll:create_sprint critical-fixes --priority P0
```

#### Success Criteria

**Automated Verification**:
- [ ] No occurrences of `/ll:create-sprint` in command file
- [ ] Three occurrences of `/ll:create_sprint` in examples section

---

### Phase 3: Update Related Issue Files

#### Overview
Update active issue files that reference the old command name.

#### Changes Required

**File**: `.issues/bugs/P2-BUG-105-ll-create-sprint-references-undefined-priority-argument.md`
- Update title references from `ll_create_sprint` to `create_sprint`
- Update `/ll:ll_create_sprint` to `/ll:create_sprint`

**File**: `.issues/enhancements/P3-ENH-106-ll-create-sprint-uses-unsupported-template-syntax.md`
- Update title references from `ll_create_sprint` to `create_sprint`
- Update `/ll:ll_create_sprint` to `/ll:create_sprint`

**File**: `.issues/enhancements/P3-ENH-107-add-sprints-configuration-to-config-schema.md`
- Update `/ll:ll_create_sprint` to `/ll:create_sprint`
- Update `ll_create_sprint.md` to `create_sprint.md`

**File**: `.issues/enhancements/P4-ENH-108-ll-create-sprint-use-claude-tools-instead-of-bash.md`
- Update title references from `ll_create_sprint` to `create_sprint`
- Update `/ll:ll_create_sprint` to `/ll:create_sprint`

#### Success Criteria

**Automated Verification**:
- [ ] No occurrences of `/ll:ll_create_sprint` in active issue files
- [ ] No occurrences of `ll_create_sprint.md` in active issue files

---

### Phase 4: Verify All Changes

#### Overview
Run verification to ensure no broken references remain.

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Grep for old patterns returns no results in active files

---

## Testing Strategy

### Verification Commands
```bash
# Verify file rename
ls -la .claude/commands/create_sprint.md

# Check no old file
ls .claude/commands/ll_create_sprint.md 2>&1 | grep -q "No such file"

# Check no old references in active issues
grep -r "ll_create_sprint" .issues/bugs/ .issues/features/ .issues/enhancements/ 2>/dev/null || echo "Clean"
grep -r "/ll:ll_create_sprint" .issues/bugs/ .issues/features/ .issues/enhancements/ 2>/dev/null || echo "Clean"
```

## References

- Original issue: `.issues/bugs/P2-BUG-104-ll-create-sprint-examples-show-wrong-command-name.md`
- Command file: `.claude/commands/ll_create_sprint.md` (to be renamed)
