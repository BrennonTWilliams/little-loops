---
description: Autonomously manage issues - plan, implement, verify, and complete
arguments:
  - name: issue_type
    description: Type of issue (bug|feature|enhancement)
    required: true
  - name: action
    description: Action to perform (fix|implement|improve|verify)
    required: true
  - name: issue_id
    description: Specific issue ID (e.g., BUG-004). If empty, finds highest priority.
    required: false
---

# Manage Issue

You are tasked with autonomously managing issues across the project. This command handles the full lifecycle: planning, implementation, verification, and completion.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`
- **Completed dir**: `{{config.issues.completed_dir}}`
- **Source dir**: `{{config.project.src_dir}}`
- **Test command**: `{{config.project.test_cmd}}`
- **Lint command**: `{{config.project.lint_cmd}}`
- **Custom verification**: `{{config.commands.custom_verification}}`

---

## Phase 1: Find Issue

If issue_id is provided, locate that specific issue. Otherwise, find the highest priority issue of the specified type.

```bash
ISSUE_TYPE="${issue_type}"
ISSUE_ID="${issue_id}"
ISSUE_DIR="{{config.issues.base_dir}}"

# Map issue_type to directory
case "$ISSUE_TYPE" in
    bug) SEARCH_DIR="$ISSUE_DIR/bugs" ;;
    feature) SEARCH_DIR="$ISSUE_DIR/features" ;;
    enhancement) SEARCH_DIR="$ISSUE_DIR/enhancements" ;;
esac

# Find issue file
# Use strict matching: ID must be bounded by delimiters (-, _, .) to avoid
# matching BUG-1 against BUG-10 or ENH-1 against issue-enh-01-...
if [ -n "$ISSUE_ID" ]; then
    ISSUE_FILE=$(find "$SEARCH_DIR" -maxdepth 1 -name "*.md" 2>/dev/null | grep -E "[-_]${ISSUE_ID}[-_.]" | head -1)
else
    # Find highest priority (P0 > P1 > P2 > ...)
    for P in P0 P1 P2 P3 P4 P5; do
        ISSUE_FILE=$(ls "$SEARCH_DIR"/$P-*.md 2>/dev/null | sort | head -1)
        if [ -n "$ISSUE_FILE" ]; then
            break
        fi
    done
fi
```

---

## Phase 2: Create Implementation Plan

After reading the issue, create a plan:

1. **Read the issue file** completely
2. **Extract referenced files** and line numbers
3. **Research the codebase** to understand affected components
4. **Design the solution** with specific changes
5. **Write plan** to `thoughts/shared/plans/YYYY-MM-DD-[ISSUE-ID]-management.md`

Plan template:
```markdown
# [ISSUE-ID]: [Title] - Management Plan

## Issue Reference
- **File**: [path to issue]
- **Type**: [bug|feature|enhancement]
- **Priority**: [P0-P5]
- **Action**: [action]

## Problem Analysis
[Root cause for bugs, or requirements for features]

## Solution Approach
[High-level strategy]

## Implementation Phases

### Phase 1: [Name]
**Files**: [list]
**Changes**: [summary]

### Phase 2: [Name]
...

## Verification Plan
[How to verify the fix/feature works]
```

---

## Phase 3: Implement

1. **Create todo list** with TodoWrite
2. **Follow the plan** phase by phase
3. **Make atomic changes** - focused and minimal
4. **Mark todos complete** as you finish

### Implementation Guidelines
- Follow existing code patterns
- Add/update tests for changed behavior
- Keep changes focused on the issue
- Include type hints for new code
- Add docstrings for public interfaces

---

## Phase 4: Verify

Run verification commands:

```bash
# Run tests
{{config.project.test_cmd}} tests/ -v

# Run linting
{{config.project.lint_cmd}} {{config.project.src_dir}}

# Run type checking (if configured)
{{config.project.type_cmd}} {{config.project.src_dir}}

# Run custom verification (if configured)
# {{config.commands.custom_verification}}
```

All checks must pass before proceeding.

---

## Phase 5: Complete Issue Lifecycle

### 1. Update Issue File

Add resolution section:
```markdown
---

## Resolution

- **Action**: [action]
- **Completed**: YYYY-MM-DD
- **Status**: Completed

### Changes Made
- [file]: [description]

### Verification Results
- Tests: PASS
- Lint: PASS
- Types: PASS
```

### 2. Commit Changes

```bash
git add [modified files]
git commit -m "[action]([component]): [description]

[issue_type] [ISSUE-ID]: [title]

- [change 1]
- [change 2]
"
```

### 3. Move to Completed

```bash
git mv "{{config.issues.base_dir}}/[type]/[file].md" \
       "{{config.issues.base_dir}}/{{config.issues.completed_dir}}/"
git commit -m "chore(issues): mark [ISSUE-ID] as completed"
```

---

## Final Report

Output in this format for machine parsing:

```
================================================================================
ISSUE MANAGED: {ISSUE_ID} - {action}
================================================================================

## METADATA
- Type: {issue_type}
- Priority: {priority}
- Title: {title}
- Action: {action}

## PLAN
- File: thoughts/shared/plans/{plan-file}.md

## FILES_CHANGED
- {file} [MODIFIED]
- {file} [CREATED]

## FILES_CREATED
- {file} - {purpose}

## COMMITS
- {hash}: {message}

## VERIFICATION
- tests: PASS
- lint: PASS
- types: PASS

## RESULT
- Status: COMPLETED
- Moved To: {{config.issues.base_dir}}/{{config.issues.completed_dir}}/{filename}.md

================================================================================
```

---

## Arguments

$ARGUMENTS

- **issue_type** (required): Type of issue
  - `bug` - Search in bugs directory
  - `feature` - Search in features directory
  - `enhancement` - Search in enhancements directory

- **action** (required): Action to perform
  - `fix` - Fix a bug
  - `implement` - Implement a feature
  - `improve` - Improve/enhance
  - `verify` - Verify issue status only

- **issue_id** (optional): Specific issue ID
  - If provided, work on that issue
  - If omitted, find highest priority

---

## Examples

```bash
# Fix highest priority bug
/ll:manage_issue bug fix

# Implement specific feature
/ll:manage_issue feature implement FEAT-042

# Improve highest priority enhancement
/ll:manage_issue enhancement improve

# Just verify an issue (no implementation)
/ll:manage_issue bug verify BUG-123
```
