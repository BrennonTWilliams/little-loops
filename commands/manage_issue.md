---
description: Autonomously manage issues - plan, implement, verify, and complete
arguments:
  - name: issue_type
    description: Type of issue (bug|feature|enhancement)
    required: true
  - name: action
    description: Action to perform (fix|implement|improve|verify|plan)
    required: true
  - name: issue_id
    description: Specific issue ID (e.g., BUG-004). If empty, finds highest priority.
    required: false
  - name: flags
    description: "Optional flags: --plan-only (stop after planning), --resume (continue from checkpoint), --quick (skip research), --auto (skip research + phase gates)"
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

### Workflow Settings
- **Phase gates**: `{{config.workflow.phase_gates.enabled}}` (skip with --auto)
- **Deep research**: `{{config.workflow.deep_research.enabled}}` (skip with --quick or --auto)
- **Research agents**: `{{config.workflow.deep_research.agents}}`

### Directory Structure

**IMPORTANT**: The `completed/` directory is a SIBLING to category directories, NOT a child:

```
{{config.issues.base_dir}}/
├── bugs/           # Active bugs (NEVER create completed/ here)
├── features/       # Active features (NEVER create completed/ here)
├── enhancements/   # Active enhancements (NEVER create completed/ here)
└── completed/      # ALL completed issues go here (sibling to categories)
```

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

## Phase 1.5: Deep Research (unless --quick or --auto)

Before creating an implementation plan, spawn parallel sub-agents to gather comprehensive context about the issue.

**Skip this phase if**:
- `--quick` flag is specified (fast mode, skip research)
- `--auto` flag is specified (automation mode, skip research + phase gates)
- Action is `verify` (verification doesn't need deep research)

### 1. Spawn Research Tasks in Parallel

Use the Task tool to spawn these agents concurrently:

1. **codebase-locator** - Find all files related to the issue
   ```
   Find all files related to [ISSUE-ID]: [issue title]

   Search for:
   - Files mentioned in the issue description
   - Related components and dependencies
   - Test files that cover affected code

   Return file paths with brief descriptions of relevance.
   ```

2. **codebase-analyzer** - Understand the current implementation
   ```
   Analyze the code paths related to [ISSUE-ID]: [issue title]

   For the files found, explain:
   - Current behavior with file:line references
   - Data flow and integration points
   - Any existing patterns being used

   Return detailed analysis with specific file:line references.
   ```

3. **codebase-pattern-finder** - Find similar patterns to follow
   ```
   Find similar implementations for [ISSUE-ID]: [issue title]

   Search for:
   - Similar fixes/features in the codebase
   - Established conventions for this type of change
   - Test patterns to model after

   Return examples with file:line references.
   ```

### 2. Wait for All Tasks

**CRITICAL**: Wait for ALL sub-agent tasks to complete before proceeding to planning.

### 3. Synthesize Research Findings

Compile research into structured findings:

```markdown
## Research Findings

### Key Discoveries
- [Discovery 1 with file:line reference]
- [Discovery 2 with file:line reference]

### Current State
- [How the affected code currently works]
- [Integration points identified]

### Patterns to Follow
- [Convention 1 found in codebase]
- [Similar implementation at file:line]

### Potential Concerns
- [Any complexity or risk identified]
```

---

## Phase 2: Create Implementation Plan

After reading the issue and completing research, create a comprehensive plan.

**If `--plan-only` flag is set**: Stop after writing the plan (do not implement).

### No Open Questions Rule

**CRITICAL**: Before writing the plan, resolve ALL open questions:

1. **Unclear Requirements** → Ask for clarification or research further
2. **Technical Uncertainty** → Spawn additional research tasks
3. **Design Decisions** → Present options to user, get explicit approval

**The plan must be complete and actionable with no unresolved questions.**

In `--auto` mode: If questions arise that cannot be resolved, mark the issue as `NOT_READY` rather than proceeding with assumptions.

### Plan Creation Steps

1. **Read the issue file** completely
2. **Incorporate research findings** from Phase 1.5
3. **Resolve any remaining questions** before proceeding
4. **Design the solution** with specific changes
5. **Write plan** to `thoughts/shared/plans/YYYY-MM-DD-[ISSUE-ID]-management.md`

### Enhanced Plan Template

Write the plan using this structure (sections are recommended, skip if not applicable):

````markdown
# [ISSUE-ID]: [Title] - Implementation Plan

## Issue Reference
- **File**: [path to issue]
- **Type**: [bug|feature|enhancement]
- **Priority**: [P0-P5]
- **Action**: [action]

## Current State Analysis

[What exists now based on research findings]

### Key Discoveries
- [Finding 1 with file:line reference]
- [Finding 2 with file:line reference]
- [Pattern discovered in codebase]

## Desired End State

[Specification of what should exist after implementation]

### How to Verify
- [Specific verification method]
- [Expected behavior after change]

## What We're NOT Doing

[Explicitly list out-of-scope items to prevent scope creep]
- Not changing [X] - reason
- Not refactoring [Y] - deferred to separate issue
- Deferring [Z] to future enhancement

## Problem Analysis

[Root cause for bugs, or requirements analysis for features]

## Solution Approach

[High-level strategy based on research findings and patterns discovered]

## Implementation Phases

### Phase 1: [Descriptive Name]

#### Overview
[What this phase accomplishes]

#### Changes Required

**File**: `path/to/file.ext`
**Changes**: [Summary of changes]

```[language]
// Specific code to add/modify
```

#### Success Criteria

**Automated Verification** (commands that can be run):
- [ ] Tests pass: `{{config.project.test_cmd}}`
- [ ] Lint passes: `{{config.project.lint_cmd}}`
- [ ] Types pass: `{{config.project.type_cmd}}`
- [ ] [Add specific test commands, e.g., `pytest tests/test_feature.py -k test_specific`]

**Manual Verification** (requires human judgment):
- [ ] [Describe specific behavior to verify in UI/CLI]
- [ ] [Describe edge case to test manually]
- [ ] [Describe expected user experience outcome]

> **Phase Gate**: After automated verification passes, pause for manual verification confirmation (skipped with `--auto` flag).

**Success Criteria Guidelines**:
- **Automated**: Any verification that can be executed by running a command (tests, linting, type checking, build, specific test cases)
- **Manual**: Verification requiring human judgment (UI/UX behavior, performance perception, edge case handling, user acceptance)
- Each phase MUST have at least one automated criterion
- Manual criteria should be specific and testable, not vague ("works correctly" → "clicking Save button persists data and shows confirmation toast")

---

### Phase 2: [Descriptive Name]

[Continue with same structure...]

## Testing Strategy

### Unit Tests
- [What to test]
- [Key edge cases]

### Integration Tests
- [End-to-end scenarios]

## References

- Original issue: `{{config.issues.base_dir}}/[type]/[filename].md`
- Related patterns: `[file:line]`
- Similar implementation: `[file:line]`
````

---

## Phase 3: Implement

### Resuming Work (--resume flag)

If `--resume` flag is specified:

1. **Locate existing plan** matching the issue ID pattern
2. **Scan for progress** - look for `[x]` checkmarks in success criteria
3. **Present resume status**:
   ```
   Resuming [ISSUE-ID] from Phase [N]

   Previously completed:
   - [x] Phase 1: [Name]
   - [x] Phase 2: [Name]

   Starting from:
   - [ ] Phase 3: [Name]

   Verifying previous work is still valid...
   ```
4. **Verify previous work** (only if something seems off)
5. **Continue from first unchecked item**

### Implementation Process

1. **Create todo list** with TodoWrite
2. **Follow the plan** phase by phase
3. **Make atomic changes** - focused and minimal
4. **Mark todos complete** as you finish
5. **Update checkboxes in plan** as you complete each section

### Context Monitoring & Proactive Handoff

**IMPORTANT**: Monitor context usage throughout implementation. When context is running low:

1. **Detect low context** - If you notice context approaching limits (conversation getting long, many files read), find a natural stopping point at a phase boundary.

2. **Generate handoff** - Before context exhaustion, write a continuation prompt to `.claude/ll-continue-prompt.md`:

```markdown
# Session Continuation: [ISSUE-ID]

## Context
Implementing [issue title]. Reached end of context during [phase].

## Completed Work
- [x] Phase 1: [Name] - completed at [file:line]
- [x] Phase 2: [Name] - completed at [file:line]

## Current State
- Working on: Phase [N]: [Name]
- Last action: [What was just completed]
- Next action: [Immediate next step]

## Key File References
- Plan: `thoughts/shared/plans/[plan-file].md`
- Modified: `[file:line]`, `[file:line]`
- Tests: `[test-file]`

## Resume Command
/ll:manage_issue [type] [action] [ISSUE-ID] --resume

## Critical Context
- [Decision 1 made during implementation]
- [Gotcha discovered]
- [Pattern being followed from file:line]
```

3. **Signal handoff** - Output a clear message:
```
CONTEXT_HANDOFF: Ready for fresh session
Continuation prompt written to: .claude/ll-continue-prompt.md
To continue: Start new session with content from that file
```

4. **Stop cleanly** - Do not attempt further work after signaling handoff.

This ensures work can continue with fresh context quality rather than degraded post-compaction context.

### Implementation Guidelines
- Follow existing code patterns
- Add/update tests for changed behavior
- Keep changes focused on the issue
- Include type hints for new code
- Add docstrings for public interfaces

### Phase Gate Protocol (unless --auto)

After completing each implementation phase:

1. **Run automated verification**
   - Execute all automated success criteria from the plan
   - Fix any failures before proceeding

2. **Present pause message**:
   ```
   Phase [N] Complete - Ready for Manual Verification

   Automated verification passed:
   - [x] Tests pass: {{config.project.test_cmd}}
   - [x] Lint passes: {{config.project.lint_cmd}}
   - [x] Types pass: {{config.project.type_cmd}}

   Please perform the manual verification steps from the plan:
   - [ ] [Manual check 1]
   - [ ] [Manual check 2]

   Reply "continue" to proceed to Phase [N+1], or describe any issues found.
   ```

3. **Wait for human confirmation**
   - Do NOT proceed until confirmation received
   - If issues found, address them before continuing

### Auto Mode Behavior

When `--auto` flag is set:
- Skip all phase gate pauses
- Execute all phases sequentially
- Report all results in final output
- If critical errors occur, mark as INCOMPLETE

### Mismatch Handling Protocol

When reality diverges from the plan during implementation:

1. **Detect mismatch**
   - File doesn't exist where expected
   - Code structure differs from plan
   - Dependencies changed since planning

2. **Present issue clearly**:
   ```
   MISMATCH DETECTED in Phase [N]

   Expected: [What the plan says]
   Found: [Actual situation]
   Impact: [Why this matters for implementation]

   ```

   Use the AskUserQuestion tool with single-select:
   - Question: "How should I handle this mismatch?"
   - Options:
     - "Adapt" - Adapt implementation to actual code structure
     - "Update plan" - Update plan to reflect reality, then continue
     - "Stop" - Stop and re-research before proceeding

3. **In auto mode**:
   - Attempt Option A if the mismatch is minor
   - If significant mismatch, mark as `INCOMPLETE` and report:
     ```
     INCOMPLETE: Mismatch in Phase [N]
     Expected: [plan details]
     Found: [actual situation]
     Reason: Cannot safely proceed without human guidance
     ```

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

**CRITICAL**: Move to `{{config.issues.base_dir}}/{{config.issues.completed_dir}}/` - this is a SIBLING directory to bugs/features/enhancements, NOT a subdirectory within them.

```bash
# ✅ CORRECT: Move to sibling completed/ directory
git mv "{{config.issues.base_dir}}/[type]/[file].md" \
       "{{config.issues.base_dir}}/{{config.issues.completed_dir}}/"
git commit -m "chore(issues): mark [ISSUE-ID] as completed"

# ❌ WRONG - NEVER do this (creates nested directory):
# git mv "{{config.issues.base_dir}}/bugs/P1-BUG-001.md" "{{config.issues.base_dir}}/bugs/completed/"
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
  - `plan` - Create plan only (equivalent to --plan-only flag)

- **issue_id** (optional): Specific issue ID
  - If provided, work on that issue
  - If omitted, find highest priority

- **flags** (optional): Modify command behavior
  - `--plan-only` - Stop after creating the implementation plan
  - `--resume` - Resume from existing plan checkpoint
  - `--quick` - Skip deep research phase (faster, less thorough)
  - `--auto` - Skip research + phase gates (for automation scripts)

---

## Examples

```bash
# Fix highest priority bug (with deep research + phase gates)
/ll:manage_issue bug fix

# Implement specific feature
/ll:manage_issue feature implement FEAT-042

# Quick fix without deep research
/ll:manage_issue bug fix BUG-123 --quick

# Create plan only, don't implement
/ll:manage_issue feature implement FEAT-042 --plan-only

# Resume interrupted work from checkpoint
/ll:manage_issue bug fix BUG-123 --resume

# Full automation mode (for ll-auto/ll-parallel scripts)
/ll:manage_issue enhancement improve ENH-001 --auto

# Just verify an issue (no implementation)
/ll:manage_issue bug verify BUG-123
```
