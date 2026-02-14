# ENH-135: Fix /ll:create-sprint Command Issues - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-135-create-sprint-command-audit-fixes.md`
- **Type**: Enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The `/ll:create-sprint` command has several consistency issues identified during an audit:

### Key Discoveries
1. **File location**: Command at `.claude/commands/create_sprint.md` while 26 other commands are in `commands/` directory
2. **Missing frontmatter**: No `allowed-tools` specification (pattern comparison shows many commands include this)
3. **Variable syntax**: Uses `${name}`, `${description:-}` in bash code blocks - this is actually correct per codebase patterns found in `commands/manage_issue.md:59-61`, `commands/ready_issue.md:30`
4. **Glob syntax issue**: Line 76 uses `.issues/**/*-{issue_id}-*.md` which is incorrect - should show literal substitution
5. **`max_iterations` field**: Present in template but NOT in `config-schema.json` (confirmed via grep)
6. **Missing config**: `.claude/ll-config.json` lacks `sprints` section (schema exists at lines 527-556)
7. **No directory creation**: Command creates files at `.sprints/` but doesn't ensure directory exists first

## Desired End State

A consistent, well-documented command file at `commands/create_sprint.md` with:
- Proper frontmatter matching codebase conventions
- Correct placeholder/variable syntax
- Proper glob pattern examples
- Schema-compliant YAML template
- Directory creation step
- Project config includes `sprints` section

### How to Verify
- Command file exists at `commands/create_sprint.md` (not in `.claude/commands/`)
- Frontmatter includes `allowed-tools` (or explicit comment that none needed)
- Glob examples use correct syntax with literal substitution
- YAML template matches schema (no `max_iterations` since not in schema)
- `.claude/ll-config.json` has `sprints` section with defaults
- Directory creation step is present before file write

## What We're NOT Doing

- Not adding `max_iterations` to the schema - removing from template instead (simpler)
- Not changing the overall command logic or workflow
- Not modifying the `ll-sprint` CLI tool behavior
- Not updating other commands for consistency (separate issue if needed)

## Problem Analysis

These are documentation/consistency issues that make the command harder to maintain and potentially confusing for users. The fixes are straightforward and low-risk.

## Solution Approach

Make targeted edits to the command file and config, following patterns established in other commands (especially `manage_issue.md`, `create_loop.md`, `init.md`).

## Implementation Phases

### Phase 1: Move Command File

#### Overview
Move the command file from `.claude/commands/create_sprint.md` to `commands/create_sprint.md` using git mv.

#### Changes Required

```bash
git mv .claude/commands/create_sprint.md commands/create_sprint.md
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists at `commands/create_sprint.md`
- [ ] File does NOT exist at `.claude/commands/create_sprint.md`
- [ ] `git status` shows rename

---

### Phase 2: Update Command Frontmatter

#### Overview
Add `allowed-tools` to frontmatter. Based on the command's needs (file operations with Write/Glob, no bash commands needed), we'll add the tools explicitly.

#### Changes Required

**File**: `commands/create_sprint.md`
**Changes**: Update frontmatter to include `allowed-tools`

```yaml
---
description: Create a sprint definition with a curated list of issues
allowed-tools:
  - Bash(mkdir:*)
arguments:
  - name: name
    description: Sprint name (e.g., "sprint-1", "q1-bug-fixes")
    required: true
  - name: description
    description: Optional description of the sprint's purpose
    required: false
  - name: issues
    description: Comma-separated list of issue IDs to include (e.g., "BUG-001,FEAT-010")
    required: false
---
```

#### Success Criteria

**Automated Verification**:
- [ ] Frontmatter contains `allowed-tools` section
- [ ] `Bash(mkdir:*)` is listed (for directory creation)

---

### Phase 3: Fix Glob Pattern Syntax

#### Overview
Update line 76-77 to show correct glob pattern usage with literal substitution example.

#### Changes Required

**File**: `commands/create_sprint.md`
**Changes**: Replace incorrect brace syntax with clear example

From:
```markdown
For each issue ID in the list, use the Glob tool to verify it exists:
- Pattern: `.issues/**/*-{issue_id}-*.md`
- Example: For issue `BUG-001`, use pattern `.issues/**/*-BUG-001-*.md`
```

To:
```markdown
For each issue ID in the list, use the Glob tool to verify it exists:
- Pattern: `.issues/**/*-[ISSUE-ID]-*.md` (substitute the actual ID)
- Example: For issue `BUG-001`, use pattern `.issues/**/*-BUG-001-*.md`
```

#### Success Criteria

**Automated Verification**:
- [ ] Line no longer contains `{issue_id}` brace syntax
- [ ] Pattern shows `[ISSUE-ID]` placeholder notation

---

### Phase 4: Update YAML Template (Remove `max_iterations`)

#### Overview
Remove `max_iterations` from the YAML template since it's not in the schema, and add a directory creation step.

#### Changes Required

**File**: `commands/create_sprint.md`
**Changes**:

1. Add directory creation step before file write (lines ~84-86):

```markdown
### 4. Create Sprint Directory (if needed)

Ensure the sprints directory exists:

```bash
mkdir -p .sprints
```

### 5. Create Sprint YAML File
```

2. Update YAML template to remove `max_iterations` and renumber to section 5:

From:
```yaml
options:
  mode: auto  # auto (sequential) or parallel
  max_iterations: 100
  timeout: 3600
  max_workers: 4  # for parallel mode
```

To:
```yaml
options:
  mode: auto  # auto (sequential) or parallel
  timeout: 3600
  max_workers: 4  # for parallel mode
```

3. Update fields documentation to remove `max_iterations`:

From:
```markdown
- `options`: Execution defaults (optional)
  - `mode`: "auto" for sequential, "parallel" for concurrent
  - `max_iterations`: Max Claude iterations per issue
  - `timeout`: Per-issue timeout in seconds
  - `max_workers`: Worker count for parallel mode
```

To:
```markdown
- `options`: Execution defaults (optional)
  - `mode`: "auto" for sequential, "parallel" for concurrent
  - `timeout`: Per-issue timeout in seconds
  - `max_workers`: Worker count for parallel mode
```

#### Success Criteria

**Automated Verification**:
- [ ] YAML template does not contain `max_iterations`
- [ ] Fields documentation does not mention `max_iterations`
- [ ] Directory creation step exists before YAML file creation

---

### Phase 5: Add `sprints` Config to ll-config.json

#### Overview
Add the `sprints` configuration section to `.claude/ll-config.json` with defaults matching the schema.

#### Changes Required

**File**: `.claude/ll-config.json`
**Changes**: Add `sprints` section

```json
{
  "$schema": "...",
  "project": { ... },
  "issues": { ... },
  "scan": { ... },
  "context_monitor": { ... },
  "documents": { ... },
  "sprints": {
    "sprints_dir": ".sprints",
    "default_mode": "auto",
    "default_timeout": 3600,
    "default_max_workers": 4
  }
}
```

#### Success Criteria

**Automated Verification**:
- [ ] `.claude/ll-config.json` contains `sprints` section
- [ ] JSON is valid (no syntax errors)
- [ ] All four fields present: `sprints_dir`, `default_mode`, `default_timeout`, `default_max_workers`

---

### Phase 6: Update Config References in Command

#### Overview
Update the command to use `{{config.sprints.*}}` template syntax consistent with other commands.

#### Changes Required

**File**: `commands/create_sprint.md`
**Changes**: Add Configuration section similar to other commands

Update lines 19-31 to be more explicit about config usage:

```markdown
## Configuration

This command uses project configuration from `.claude/ll-config.json`:

**Issues settings** (under `issues`):
- `base_dir`: Issues directory - `{{config.issues.base_dir}}`

**Sprints settings** (under `sprints`):
- `sprints_dir`: Directory for sprint definitions - `{{config.sprints.sprints_dir}}`
- `default_mode`: Default execution mode - `{{config.sprints.default_mode}}`
- `default_timeout`: Default timeout per issue - `{{config.sprints.default_timeout}}`
- `default_max_workers`: Default worker count - `{{config.sprints.default_max_workers}}`
```

#### Success Criteria

**Automated Verification**:
- [ ] Configuration section uses `{{config.*}}` syntax
- [ ] References match actual config structure

---

## Testing Strategy

### Manual Verification
- Run `/ll:create-sprint test-sprint` to verify command loads correctly
- Check that directory creation works (`mkdir -p .sprints`)
- Verify YAML output matches expected structure

### Validation
- Verify JSON syntax in `ll-config.json` with a JSON linter
- Check frontmatter YAML syntax is valid

## References

- Original issue: `.issues/enhancements/P3-ENH-135-create-sprint-command-audit-fixes.md`
- Pattern reference: `commands/manage_issue.md` (frontmatter, config refs)
- Pattern reference: `commands/create_loop.md:1-5` (allowed-tools with Bash)
- Pattern reference: `commands/init.md:875-878` (mkdir -p pattern)
- Schema: `config-schema.json:527-556` (sprints section)
