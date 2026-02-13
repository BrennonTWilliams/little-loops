# BUG-363: allowed-tools mismatch in scan commands - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P4-BUG-363-allowed-tools-mismatch-in-scan-commands.md`
- **Type**: bug
- **Priority**: P4
- **Action**: fix

## Current State Analysis

Both `scan_codebase.md` and `scan_product.md` declare only `Bash(git:*, gh:*)` in their `allowed-tools` frontmatter, but their command bodies invoke additional tools:

- `scan_codebase.md`: Uses `Task` (lines 68, 72, 104, 137) and `TodoWrite` (line 27)
- `scan_product.md`: Uses `Skill` (line 138) and `TodoWrite` (line 33)

### Patterns to Follow
- `analyze-workflows.md:3-11` lists all tools as bare names in YAML list format
- `manage_release.md:17-24` mixes `Bash(glob)` with bare tool names
- Both patterns are valid; we'll follow the mixed pattern (keep existing Bash glob, add bare tool names)

## Desired End State

Both commands have `allowed-tools` frontmatter that includes all tools actually used in their command bodies.

### How to Verify
- Inspect frontmatter of both files
- Confirm each tool used in body is listed in `allowed-tools`

## What We're NOT Doing

- Not auditing other commands for similar issues (tracked by BUG-365 and ENH-399)
- Not changing command body content
- Not addressing `Bash(date:*)` or `Bash(cat:*)` sub-patterns (those are bash commands covered by expanding to general `Bash` if needed, but the issue scope is Task/Skill/TodoWrite)

## Solution Approach

Add missing tool declarations to the `allowed-tools` YAML list in each file's frontmatter.

## Implementation Phases

### Phase 1: Update scan_codebase.md frontmatter

**File**: `commands/scan_codebase.md`
**Changes**: Add `Task` and `TodoWrite` to `allowed-tools` list

```yaml
allowed-tools:
  - Bash(git:*, gh:*)
  - Task
  - TodoWrite
```

### Phase 2: Update scan_product.md frontmatter

**File**: `commands/scan_product.md`
**Changes**: Add `Skill` and `TodoWrite` to `allowed-tools` list

```yaml
allowed-tools:
  - Bash(git:*, gh:*)
  - Skill
  - TodoWrite
```

## Success Criteria

- [x] `scan_codebase.md` allowed-tools includes `Task` and `TodoWrite`
- [x] `scan_product.md` allowed-tools includes `Skill` and `TodoWrite`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
