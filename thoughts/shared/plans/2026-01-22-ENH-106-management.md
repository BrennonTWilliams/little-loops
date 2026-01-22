# ENH-106: create_sprint uses unsupported template syntax - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-106-ll-create-sprint-uses-unsupported-template-syntax.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The `/ll:create_sprint` command uses Handlebars-style `{{config...}}` template syntax that Claude Code does not support. The values are not substituted at runtime, causing Claude to attempt commands with literal template strings.

### Key Discoveries
- Template syntax appears on 4 lines: 22, 23, 62, 74 in `.claude/commands/create_sprint.md`
- Line 22: `{{config.issues.base_dir}}` in configuration display
- Line 23: `{{config.issues.categories}}` in configuration display
- Line 62: `{{config.issues.base_dir}}` embedded in `find` bash command
- Line 74: `{{config.issues.base_dir}}` embedded in `find` bash command within loop

### Working Pattern (from handoff.md:18-23)
```markdown
## Configuration

Read settings from `.claude/ll-config.json` under `continuation`:
- `include_todos`: Include todo list state in deep mode (default: true)
```

This pattern instructs Claude to read the config file explicitly and documents the expected keys with defaults.

## Desired End State

The `create_sprint.md` command will:
1. Instruct Claude to read `.claude/ll-config.json` for project settings
2. Document expected config keys with their defaults
3. Use hardcoded default values (`.issues`) in bash examples
4. Work correctly without template substitution

### How to Verify
- Read the updated file and confirm no `{{config...}}` syntax remains
- The file still conveys the same information about configuration
- Bash examples use `.issues` as the hardcoded default path

## What We're NOT Doing

- Not fixing template syntax in other command files (separate issues needed)
- Not changing the behavior or functionality of the command
- Not adding new features or refactoring the command structure

## Problem Analysis

The root cause is that Claude Code's command system passes markdown files to Claude as prompts, but does not perform any template variable substitution. The `{{config...}}` syntax was designed to reference configuration values but was never actually implemented as a feature.

## Solution Approach

Follow the pattern established in `handoff.md` - use prose instructions telling Claude to read the config file, combined with hardcoded default values in bash examples.

## Implementation Phases

### Phase 1: Update Configuration Section

#### Overview
Replace template syntax in lines 21-24 with prose instructions.

#### Changes Required

**File**: `.claude/commands/create_sprint.md`
**Lines**: 19-24

**Before:**
```markdown
## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`
- **Sprints directory**: `.sprints/`
```

**After:**
```markdown
## Configuration

Read settings from `.claude/ll-config.json` under `issues`:
- `base_dir`: Issues directory (default: `.issues`)
- `categories`: Issue categories (default: `bugs`, `features`, `enhancements`)
- **Sprints directory**: `.sprints/`
```

#### Success Criteria

**Automated Verification**:
- [ ] No `{{config.issues.base_dir}}` on line 22
- [ ] No `{{config.issues.categories}}` on line 23

---

### Phase 2: Update Bash Examples

#### Overview
Replace template variables in bash code blocks with hardcoded default values.

#### Changes Required

**File**: `.claude/commands/create_sprint.md`
**Line**: 62

**Before:**
```bash
   find {{config.issues.base_dir}} -name "*.md" -not -path "*/completed/*" | sort
```

**After:**
```bash
   find .issues -name "*.md" -not -path "*/completed/*" | sort
```

**Line**: 74

**Before:**
```bash
  if ! find {{config.issues.base_dir}} -name "*-${issue_id}-*.md" | grep -q .; then
```

**After:**
```bash
  if ! find .issues -name "*-${issue_id}-*.md" | grep -q .; then
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c "{{config" .claude/commands/create_sprint.md` returns 0
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Manual Verification
- Read the updated file to confirm readability and correctness
- Verify the intent is preserved and instructions are clear

## References

- Original issue: `.issues/enhancements/P3-ENH-106-ll-create-sprint-uses-unsupported-template-syntax.md`
- Similar working pattern: `commands/handoff.md:18-23`
- Related completed issue: `.issues/completed/P3-ENH-071-capture-issue-hardcoded-config-values.md`
