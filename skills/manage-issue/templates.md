# Manage Issue Templates

This file contains reference templates used by the manage_issue skill. These templates are loaded on demand when needed during issue management.

---

## Phase 1.5: Deep Research Agent Prompts

### Codebase Locator Prompt

```
Find all files related to [ISSUE-ID]: [issue title]

Search for:
- Files mentioned in the issue description
- Related components and dependencies
- Test files that cover affected code

Return file paths with brief descriptions of relevance.
```

### Codebase Analyzer Prompt

```
Analyze the code paths related to [ISSUE-ID]: [issue title]

For the files found, explain:
- Current behavior with file:line references
- Data flow and integration points
- Any existing patterns being used

Return detailed analysis with specific file:line references.
```

### Codebase Pattern Finder Prompt

```
Find similar implementations for [ISSUE-ID]: [issue title]

Search for:
- Similar fixes/features in the codebase
- Established conventions for this type of change
- Test patterns to model after
- Existing utility functions, helpers, and shared modules that could be reused or extended instead of writing new code
- Similar logic elsewhere that suggests consolidation rather than duplication

Return examples with file:line references. For reusable code, explicitly note whether to reuse as-is, extend, or justify creating new.
```

### Research Findings Template

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

### Reusable Code
- [Utility/module at file:line — reuse as-is / extend / justify new]
- [Shared abstraction at file:line — how it applies]

### Potential Concerns
- [Any complexity or risk identified]
```

---

## Enhanced Plan Template

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

## Code Reuse & Integration

- **Reusable existing code**: [list utilities/modules to leverage with file:line refs]
- **Patterns to follow**: [established conventions this implementation must match]
- **New code justification**: [what's genuinely new and why existing code doesn't cover it]

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

> **Phase Gate**: After automated verification passes, pause for manual verification confirmation (requires `--gates` flag).

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

## Phase 3: Implementation Templates

### Resume Status Display Format

```
Resuming [ISSUE-ID] from Phase [N]

Previously completed:
- [x] Phase 1: [Name]
- [x] Phase 2: [Name]

Starting from:
- [ ] Phase 3: [Name]

Verifying previous work is still valid...
```

### Phase Gate Pause Message Format

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

### Mismatch Detection Format

```
MISMATCH DETECTED in Phase [N]

Expected: [What the plan says]
Found: [Actual situation]
Impact: [Why this matters for implementation]
```

### Incomplete Status Report Format

```
INCOMPLETE: Mismatch in Phase [N]
Expected: [plan details]
Found: [actual situation]
Reason: Cannot safely proceed without human guidance
```

---

## Session Continuation (Handoff) Template

When context is running low, write a continuation prompt to `.claude/ll-continue-prompt.md` using this template:

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

---

## Phase 4.5: Integration Review Templates

### Integration Report Template

Produce a structured report after the integration review:

```
INTEGRATION REVIEW: [ISSUE-ID]

| Check              | Status    | Details                                    |
|--------------------|-----------|--------------------------------------------|
| Duplication        | PASS/WARN | [Details or "No duplication detected"]     |
| Shared module use  | PASS/WARN | [Details or "Properly uses shared code"]   |
| Pattern conformance| PASS/WARN | [Details or "Follows project patterns"]    |
| Integration points | PASS/WARN | [Details or "Well-integrated"]             |

Overall: PASS / WARN (with actionable findings)
```

### Handling Warnings

- **PASS**: Proceed to Phase 5
- **WARN**: Document findings in the plan file's iteration log. If warnings are minor (naming differences, style preferences), proceed. If warnings indicate significant duplication or missed reuse opportunities, fix before proceeding.

---

## Phase 5: Completion Templates

### Session Log Entry Format

```markdown
## Session Log
- `/ll:manage_issue` - [ISO timestamp] - `[path to current session JSONL]`
```

To find the current session JSONL path: look in `~/.claude/projects/` for the directory matching the current project (path encoded with dashes), then find the most recently modified `.jsonl` file (excluding files starting with `agent-`).

If the `## Session Log` section already exists, append the new entry below the header. If it doesn't exist, add it before the `---` / `## Status` footer.

### Resolution Section Template

Add this resolution section to the issue file:

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
- Run: PASS
- Integration: PASS
```

---

## Final Report Template

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
{if product_impact exists:}
## PRODUCT IMPACT
- Goal Alignment: {goal_alignment}
- Persona Impact: {persona_impact}
- Business Value: {business_value}
- User Benefit: {user_benefit}
{endif}

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
- run: PASS
- integration: PASS

## RESULT
- Status: COMPLETED
- Moved To: {{config.issues.base_dir}}/{{config.issues.completed_dir}}/{filename}.md

================================================================================
```

**Display Note**: When reviewing an issue file during implementation, check for and display product impact fields if present in the frontmatter. These provide business context for prioritization decisions.
