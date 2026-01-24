# ENH-138: Add Sprint Name Validation - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-138-create-sprint-name-validation.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The `/ll:create_sprint` command at `commands/create_sprint.md:59-62` documents naming conventions but doesn't enforce them:

```markdown
**Validate sprint name:**
- Must be non-empty
- Should use lowercase letters, numbers, and hyphens only
- Suggest format: `sprint-N`, `q1-features`, `bug-fixes-week-1`
```

### Key Discoveries
- Sprint names are used directly in file paths: `{sprints_dir}/{name}.yaml` (`sprint.py:124`)
- No validation occurs between CLI input and file creation
- Invalid names can cause issues: spaces, special chars, path traversal (`../`), empty names
- Issue IDs are normalized (`.strip().upper()`) but sprint names are not (`cli.py:207`)
- The codebase has established patterns for validation via AskUserQuestion (`create_sprint.md:113-131`)

## Desired End State

Sprint names are validated before file creation with:
1. Non-empty check
2. Pattern validation: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` (lowercase, numbers, hyphens, no leading/trailing hyphens)
3. No consecutive hyphens
4. Clear error messages with auto-suggested corrections
5. User can accept suggestion, enter different name, or use original anyway

### How to Verify
- Invalid names are caught and reported
- Suggested corrections are offered
- User can proceed with corrected name or choose alternative

## What We're NOT Doing

- Not adding validation to the Python `ll-sprint` CLI tool (separate issue if needed)
- Not changing existing sprint files
- Not adding validation to other commands

## Problem Analysis

Invalid sprint names pass through unchecked because lines 59-62 only document expectations without enforcement logic. When invalid names reach `Sprint.save()`, they create files that may:
- Have spaces in filenames (problematic for CLI usage)
- Cause path traversal if containing `../`
- Create hidden files if empty (results in `.yaml`)
- Be case-inconsistent with documented conventions

## Solution Approach

Add validation logic immediately after the existing documentation at lines 59-62, using the AskUserQuestion pattern established at lines 113-131 for the overwrite flow.

## Implementation Phases

### Phase 1: Add Validation Logic

#### Overview
Insert validation rules and correction flow after the existing name documentation.

#### Changes Required

**File**: `commands/create_sprint.md`
**Location**: After line 62 (after the current "Suggest format" line)

Add the following validation logic block:

```markdown
**Validation rules:**
1. Must be non-empty
2. Must match pattern: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` (or single char `^[a-z0-9]$`)
3. No consecutive hyphens (`--`)
4. No leading or trailing hyphens

**If name is invalid**, auto-generate a suggested correction:
- Convert to lowercase
- Replace spaces and underscores with hyphens
- Remove invalid characters
- Collapse consecutive hyphens to single hyphen
- Trim leading/trailing hyphens

**Example corrections:**

| Input | Issue | Suggestion |
|-------|-------|------------|
| `Sprint 1` | Uppercase and space | `sprint-1` |
| `--test--` | Leading/trailing hyphens | `test` |
| `Q1_bugs` | Uppercase and underscore | `q1-bugs` |
| `my..sprint` | Invalid characters | `my-sprint` |
| `` (empty) | Empty name | Prompt user to provide name |

**If validation fails**, use AskUserQuestion:

```yaml
questions:
  - question: "Sprint name '${SPRINT_NAME}' is invalid: ${REASON}. How would you like to proceed?"
    header: "Fix name"
    multiSelect: false
    options:
      - label: "Use '${SUGGESTED_NAME}' (Recommended)"
        description: "Auto-corrected name following conventions"
      - label: "Enter different name"
        description: "Provide your own valid name"
      - label: "Use original anyway"
        description: "May cause issues with ll-sprint CLI"
```

**Based on user response:**
- **"Use '${SUGGESTED_NAME}'"**: Update `SPRINT_NAME` to the suggested value and continue
- **"Enter different name"**: Prompt for new name and re-validate
- **"Use original anyway"**: Continue with original name (warn about potential issues)
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Running `/ll:create_sprint "Sprint 1"` triggers validation and offers `sprint-1` as correction
- [ ] Running `/ll:create_sprint "--test--"` triggers validation and offers `test` as correction
- [ ] Running `/ll:create_sprint "valid-name"` proceeds without validation prompt
- [ ] Choosing "Enter different name" allows re-entry and re-validation

---

## Testing Strategy

### Manual Tests
- Test with various invalid inputs:
  - Uppercase: `Sprint-1` → should suggest `sprint-1`
  - Spaces: `my sprint` → should suggest `my-sprint`
  - Underscores: `q1_bugs` → should suggest `q1-bugs`
  - Leading/trailing hyphens: `--test--` → should suggest `test`
  - Consecutive hyphens: `test--name` → should suggest `test-name`
  - Empty string → should prompt for name
- Test valid inputs pass through without prompts:
  - `sprint-1`, `q1-features`, `bugfix`, `a`, `1`

## References

- Original issue: `.issues/enhancements/P4-ENH-138-create-sprint-name-validation.md`
- Target file: `commands/create_sprint.md:59-62`
- Similar pattern: `commands/create_sprint.md:113-131` (overwrite confirmation flow)
- Sprint file usage: `scripts/little_loops/sprint.py:124` (path construction)
