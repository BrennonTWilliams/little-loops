# Manage Issue Templates

This file contains reference templates used by the manage-issue skill. These templates are loaded on demand when needed during issue management.

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
- Current behavior with function/class anchors (e.g. `in function foo()`, `near class Bar`)
- Data flow and integration points
- Any existing patterns being used

Return detailed analysis with specific anchor-based references (function/class names).
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

Return examples with anchor-based references (function/class names). For reusable code, explicitly note whether to reuse as-is, extend, or justify creating new.
```

### Research Findings Template

```markdown
## Research Findings

### Key Discoveries
- [Discovery 1 with function/class anchor]
- [Discovery 2 with function/class anchor]

### Current State
- [How the affected code currently works]
- [Integration points identified]

### Patterns to Follow
- [Convention 1 found in codebase]
- [Similar implementation with function/class anchor]

### Reusable Code
- [Utility/module with function/class anchor — reuse as-is / extend / justify new]
- [Shared abstraction with function/class anchor — how it applies]

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
- [Finding 1 with function/class anchor]
- [Finding 2 with function/class anchor]
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

- **Reusable existing code**: [list utilities/modules to leverage with anchor-based references (function/class names)]
- **Patterns to follow**: [established conventions this implementation must match]
- **New code justification**: [what's genuinely new and why existing code doesn't cover it]

## Implementation Phases

> **TDD Mode** (when `config.commands.tdd_mode` is `true`): Include "Phase 0: Write Tests (Red)" as the first implementation phase. This phase writes failing tests derived from the issue's acceptance criteria and the plan's success criteria. The tests must fail against the current codebase (Red). Subsequent phases then implement code to make these tests pass (Green).
> **Skip Phase 0** if issue frontmatter contains `testable: false` — omit this phase entirely from the plan in that case.

### Phase 0: Write Tests — Red *(TDD mode only, skip if `config.commands.tdd_mode` is `false` or `testable: false` in frontmatter)*

#### Overview
Write tests that encode the issue's acceptance criteria. These tests must FAIL against the current codebase.

#### Test Files
- [List specific test files to create/modify]
- [List test function names and what each asserts]

#### Red Validation
After writing tests, run: `{{config.project.test_cmd}} [test_files] -v`
- **Expected**: Non-zero exit code with `FAILED` markers (assertion failures)
- **Invalid**: `ERROR`, `ImportError`, `SyntaxError`, `ModuleNotFoundError` — fix test code before proceeding

#### Success Criteria

**Automated Verification**:
- [ ] Tests fail with assertion errors (not import/syntax errors): `{{config.project.test_cmd}} [test_files] -v` returns non-zero exit
- [ ] Test output contains `FAILED` (not `ERROR`/`ImportError`/`SyntaxError`)

---

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
- Related patterns: `[function/class anchor]`
- Similar implementation: `[function/class anchor]`
````

---

## Phase 2.3/2.5: Gate Logic

### Decision Gate (Phase 2.3)

```
READ decision_needed from issue YAML frontmatter

IF decision_needed is true:
  IF --force-implement flag is set:
    WARN: "⚠ Decision gate: decision_needed=true. Proceeding due to --force-implement."
    PROCEED to Phase 2.5
  ELSE:
    HALT with message:
    "✗ Decision gate: this issue has competing implementation options that require a decision.
     Run /ll:decide-issue [ISSUE_ID] to select an approach, then re-run manage-issue.
     Use --force-implement to bypass this gate."
    STOP (do not proceed to Phase 3)

ELSE (decision_needed is absent or false):
  PROCEED silently to Phase 2.5
```

### Confidence Gate (Phase 2.5)

```
READ confidence_score from issue YAML frontmatter

IF confidence_score is absent:
  IF --force-implement flag is set:
    WARN: "⚠ Confidence gate: no confidence_score found. Proceeding due to --force-implement."
    PROCEED to Phase 3
  ELSE:
    HALT with message:
    "✗ Confidence gate: no confidence_score on file.
     Run /ll:confidence-check [ID] to evaluate readiness, or use --force-implement to bypass."
    STOP (do not proceed to Phase 3)

ELSE IF confidence_score < config.commands.confidence_gate.readiness_threshold:
  IF --force-implement flag is set:
    WARN: "⚠ Confidence gate: score [SCORE]/100 is below threshold [THRESHOLD]. Proceeding due to --force-implement."
    PROCEED to Phase 3
  ELSE:
    HALT with message:
    "✗ Confidence gate: score [SCORE]/100 is below threshold [THRESHOLD].
     Run /ll:confidence-check [ID] to evaluate readiness, or use --force-implement to override."
    STOP (do not proceed to Phase 3)

ELSE:
  LOG: "✓ Confidence gate: score [SCORE]/100 meets threshold [THRESHOLD]."
  PROCEED to Phase 3
```

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

When context is running low, write a continuation prompt to `$(pwd)/.ll/ll-continue-prompt.md` (absolute path anchored to the project root — **never** to `~/.ll/ll-continue-prompt.md`) using this template:

```markdown
# Session Continuation: [ISSUE-ID]

## Context
Implementing [issue title]. Reached end of context during [phase].

## Completed Work
- [x] Phase 1: [Name] - completed in [function/class anchor]
- [x] Phase 2: [Name] - completed in [function/class anchor]

## Current State
- Working on: Phase [N]: [Name]
- Last action: [What was just completed]
- Next action: [Immediate next step]

## Key File References
- Plan: `thoughts/shared/plans/[plan-file].md`
- Modified: `[function/class anchor]`, `[function/class anchor]`
- Tests: `[test-file]`

## Resume Command
/ll:manage-issue [type] [action] [ISSUE-ID] --resume

## Critical Context
- [Decision 1 made during implementation]
- [Gotcha discovered]
- [Pattern being followed from function/class anchor]
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
- `/ll:manage-issue` - [ISO timestamp] - `[path to current session JSONL]`
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
- Frontmatter: status set to done

================================================================================
```

---

## Arguments Reference

Full per-argument reference for `/ll:manage-issue`. The canonical machine-readable
schema lives in `SKILL.md`'s YAML frontmatter; this section is the human-readable
expansion.

- **issue_type** (required): Type of issue
  - `bug` - Search in bugs directory
  - `feature` - Search in features directory
  - `enhancement` - Search in enhancements directory
  - `epic` - Search in epics directory. Note: EPICs are coordination containers; manage-issue lists their child issues and redirects to `/ll:manage-issue` per child or `/ll:create-sprint` for grouped execution rather than implementing the EPIC directly.

- **action** (required): Action to perform
  - `fix` - Fix a bug
  - `implement` - Implement a feature
  - `improve` - Improve/enhance existing functionality or documentation
  - **IMPORTANT**: Requires full implementation (Plan → Implement → Verify → Complete)
  - For documentation: Must edit/create files, not just verify content
  - For code: Follow same implementation process as fix/implement
  - Behaves identically to fix/implement actions across all issue types
  - `verify` - Verify issue status only
  - `plan` - Create plan only (equivalent to --plan-only flag)
  - `defer` - Move issue to deferred/ (parked, not active or completed)
  - `undefer` - Move issue from deferred/ back to its active category directory

- **issue_id** (optional): Specific issue ID
  - If provided, work on that issue
  - If omitted, find highest priority

- **flags** (optional): Modify command behavior
  - `--plan-only` - Stop after creating the implementation plan
  - `--dry-run` - Alias for `--plan-only`
  - `--resume` - Resume from existing plan checkpoint
  - `--gates` - Enable phase gates for manual verification between phases
  - `--quick` - Skip deep research (Phase 1.5) and confidence check for faster planning
  - `--force-implement` - Bypass confidence gate (when `commands.confidence_gate.enabled` is true)

## Usage Examples

```bash
# Fix highest priority bug
/ll:manage-issue bug fix

# Implement specific feature
/ll:manage-issue feature implement FEAT-042

# Create plan only, don't implement
/ll:manage-issue feature implement FEAT-042 --plan-only

# Dry run (alias for --plan-only)
/ll:manage-issue enhancement improve ENH-100 --dry-run

# Quick mode: skip deep research for faster planning
/ll:manage-issue bug fix BUG-050 --quick

# Resume interrupted work from checkpoint
/ll:manage-issue bug fix BUG-123 --resume

# Defer an issue (park it for later)
/ll:manage-issue feature defer FEAT-441

# Undefer an issue (bring it back to active)
/ll:manage-issue feature undefer FEAT-441

# Enable phase gates for careful manual verification
/ll:manage-issue feature implement FEAT-042 --gates

# Just verify an issue (no implementation)
/ll:manage-issue bug verify BUG-123

# Bypass confidence gate for a specific issue
/ll:manage-issue enhancement improve ENH-100 --force-implement
```

**Display Note**: When reviewing an issue file during implementation, check for and display product impact fields if present in the frontmatter. These provide business context for prioritization decisions.
