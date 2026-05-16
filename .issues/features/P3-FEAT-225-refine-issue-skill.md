---
discovered_date: 2026-02-05
discovered_by: capture_issue
---

# FEAT-225: Add /ll:refine-issue skill for interactive issue clarification

## Summary

Create a new `/ll:refine-issue` skill that accepts an Issue ID (e.g., FEAT-XXX), reads the issue file, and asks the user clarifying questions to refine the issue before implementation.

## Context

User request to add a workflow step between issue capture and implementation that helps ensure issues have sufficient detail and clarity through interactive Q&A.

## Current Behavior

Issues go directly from capture (`/ll:capture-issue`) or scanning (`/ll:scan-codebase`) to validation (`/ll:ready-issue`) and implementation (`/ll:manage-issue`). There's no dedicated interactive refinement step.

## Expected Behavior

The `/ll:refine-issue FEAT-225` skill would:

1. Accept an Issue ID as argument (e.g., `FEAT-225`, `BUG-071`)
2. Read and parse the issue file from `.issues/` directories
3. Analyze the issue content to identify:
   - Missing or vague requirements
   - Ambiguous acceptance criteria
   - Unclear scope boundaries
   - Missing technical context
4. Use `AskUserQuestion` to interactively gather clarifying information
5. Update the issue file with refined details
6. Optionally stage the changes for commit

## Proposed Solution

Create new skill directory at `skills/refine-issue/SKILL.md` with:

- **Input**: Issue ID (TYPE-NNN format)
- **Process**:
  1. Locate issue file across all `.issues/` subdirectories
  2. Parse frontmatter and content sections
  3. Generate targeted clarifying questions based on issue type and content gaps
  4. Collect answers via `AskUserQuestion`
  5. Update issue with refined information
- **Output**: Updated issue file with improved clarity

### Question Categories

The skill should generate questions tailored to:

- **BUGs**: Steps to reproduce? Error messages? Environment details?
- **FEATs**: User story? Acceptance criteria? Edge cases?
- **ENHs**: Current pain points? Success metrics? Scope boundaries?

## Impact

- **Priority**: P3
- **Effort**: Medium (new skill, similar patterns to existing skills)
- **Risk**: Low

## Related Key Documentation

_No documents linked. Run `/ll:align-issues` to discover relevant docs._

## Labels

`feature`, `captured`, `skills`, `workflow`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-05
- **Status**: Completed

### Changes Made
- `skills/refine-issue/SKILL.md`: Created new skill with full workflow for interactive issue refinement
- `thoughts/shared/plans/2026-02-05-FEAT-225-management.md`: Implementation plan

### Implementation Details
The skill provides:
- Issue location using standard search pattern
- Type-specific gap analysis (BUG/FEAT/ENH)
- Interactive Q&A via AskUserQuestion
- Issue file updates with Edit tool
- Optional git staging

### Verification Results
- Tests: PASS (2455 passed)
- Lint: PASS

---

## Status

**Completed** | Created: 2026-02-05 | Completed: 2026-02-05 | Priority: P3
