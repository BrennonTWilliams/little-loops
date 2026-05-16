---
discovered_date: 2026-02-10
discovered_by: capture_issue
---

# BUG-326: manage_issue improve action inconsistent for documentation issues

## Summary

The `ll:manage_issue` command with `improve` action behaves inconsistently based on issue type:
- **Code fix issues** (e.g., ENH-2078): Implements, tests, and commits as expected
- **Documentation issues** (e.g., ENH-2079): Only verifies and asks confirmation question

For documentation-only issues, the command defaults to "verify and ask confirmation" mode instead of implementing directly. This breaks the automated workflow (ll-auto, ll-parallel) because the command exits with return code 0 but no actual changes were made.

## Context

**Direct mode**: User description: "The ll:manage_issue skill has inconsistent behavior for the improve action: Code fix (ENH-2078) implements, tests, commits; Documentation (ENH-2079) only verifies, asks question"

Identified from issue discovered in a development project using `ll-auto` automation. Documentation issues would pass ready_issue verification but then fail during implementation because manage_issue skipped the implementation phases and only performed verification.

## Current Behavior

When running `/ll:manage-issue enhancement improve ENH-2079` (a documentation issue):

1. The command may skip to verification phase without implementing
2. Exits with return code 0 (success) without making changes
3. ll-auto's `verify_work_was_done()` detects no meaningful changes
4. Issue is not marked complete, causing the automation to stall

The model interprets `improve` for documentation as a verification task rather than an implementation task, leading to:
- Skipping implementation phases
- Running verification only
- Asking confirmation questions (potentially via AskUserQuestion despite no --gates flag)

## Steps to Reproduce

1. Create a documentation-only enhancement issue (e.g., ENH-2079)
2. Run `/ll:manage-issue enhancement improve ENH-2079` (no --gates flag)
3. Observe that the command may skip implementation and only verify
4. Note return code 0 but no file changes were made
5. ll-auto's verify_work_was_done() returns False

## Actual Behavior

The `improve` action (line 660) is defined vaguely as "Improve/enhance" without explicit implementation requirements. For documentation issues, the model interprets this as a verification task rather than an implementation task, resulting in:
- Skipping Phase 3 (Implementation)
- Running only Phase 4 (Verification)
- Asking confirmation questions via AskUserQuestion despite no --gates flag

## Expected Behavior

The `improve` action should:
1. Always go through full implementation phases (Plan -> Implement -> Verify -> Complete)
2. Make actual changes to the files described in the issue
3. Not ask confirmation questions unless --gates flag is provided
4. Behave consistently regardless of issue type (code vs documentation vs tests)

## Root Cause

The `manage_issue.md` prompt (commands/manage_issue.md) lacks clear instructions for the `improve` action behavior. While `fix` and `implement` actions have clear implementation phases, `improve` is ambiguously defined as "Improve/enhance" without explicit implementation requirements.

The model interprets `improve` for documentation as a verification task rather than an implementation task. This ambiguity causes:
- Inconsistent behavior across issue types
- Prompt-level confusion leading to skipped implementation
- Potential fallback to `verify` action behavior

### Key Locations

- **Primary fix location**: `commands/manage_issue.md`
- Action definitions section (line ~660): `improve` - Improve/enhance
- Phase 4.5 skip condition (line ~503): Action is `verify` (verification-only mode)

## Proposed Solution

Update `commands/manage_issue.md` to:

1. **Replace the vague `improve` action definition** (line ~660) with explicit instructions:

```markdown
- `improve` - Improve/enhance existing functionality or documentation
  - **IMPORTANT**: Requires full implementation (Plan → Implement → Verify → Complete)
  - For documentation: Must edit/create files, not just verify content
  - For code: Follow same implementation process as fix/implement
  - Behaves identically to fix/implement actions across all issue types
```

2. **Add documentation-specific guidance** in Phase 3 (Implementation) section to prevent ambiguity:
   - Explicitly state that documentation improvements require editing files
   - Clarify that `improve documentation` means make changes, not verify correctness
   - Add example: "Improving docs.md means editing the file, not reviewing it"

3. **Reinforce automation-mode constraints** in the Default Behavior section:
   - Add explicit reminder that without --gates, no interactive prompts should occur
   - Ensure the prompt doesn't allow `improve` to fall back to `verify` behavior

### Implementation Steps

1. Read `commands/manage_issue.md` and locate the action definitions section (line ~660)
2. Replace the current `improve - Improve/enhance` definition with the full expanded version
3. Add documentation-specific guidance in Phase 3 (Implementation) instructions
4. Optionally: Strengthen the Default Behavior section with explicit reminder about improve requiring implementation
5. Test with a documentation-only issue to verify consistent behavior (no --gates, should implement directly)

## Integration Map

### Files to Modify
- `commands/manage_issue.md` - Primary fix location

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` - Uses get_category_action() to determine action (line 467)
- `scripts/little_loops/work_verification.py` - verify_work_was_done() detects no changes (lines 44-125)
- `scripts/little_loops/parallel/worker_pool.py` - Uses get_category_action() for parallel workers (line 352)

### Similar Patterns
- Note: Previous similar issues (ENH-304, BUG-302) referenced but not found in completed/ - may be from external project

### Tests
- `scripts/tests/test_issue_manager.py` - Contains tests for manage_issue workflow
- `scripts/tests/test_config.py` - Contains tests for get_category_action (lines 371-382)

### Documentation
- `docs/ARCHITECTURE.md` - Documents manage_issue lifecycle and automation flow
- `docs/API.md` - Documents manage_issue command templates

### Configuration
- `.claude/ll-config.json` - Issue categories with actions (enhancements.action = "improve")

## Impact

- **Priority**: P2
  - **Justification**: Breaks ll-auto/ll-parallel automation for documentation issues. Not P0/P1 because workarounds exist (manual implementation, using fix/implement actions instead), but automation is significantly degraded.

- **Effort**: Small
  - **Justification**: Prompt clarification only - no code changes required

- **Risk**: Very low
  - **Justification**: Prompt instruction change only - clarifying existing intent, not changing behavior

- **Affected workflows**: ll-auto, ll-parallel, ll-sprint
- **Issue types affected**: Documentation issues (and potentially test-only issues)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Documents manage_issue lifecycle and automation flow |
| architecture | docs/API.md | Documents manage_issue command templates |
| reference | commands/manage_issue.md | Primary file to fix - contains improve action definition |

## Labels

`bug`, `automation`, `prompt-engineering`, `documentation`, `captured`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P2

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-11
- **Status**: Completed

### Changes Made
- `commands/manage_issue.md`: Clarified `improve` action definition with explicit implementation requirements (line 660)
- `commands/manage_issue.md`: Added "Documentation Implementation Guidance" subsection after line 338
- `commands/manage_issue.md`: Added reminder note in Default Behavior section about improve requiring implementation

### Changes Summary
1. Replaced vague `improve - Improve/enhance` with multi-line definition including:
   - **IMPORTANT** marker requiring full implementation
   - Explicit documentation guidance (must edit/create files)
   - Clarification that it behaves identically to fix/implement

2. Added new "Documentation Implementation Guidance" subsection in Phase 3:
   - Explicitly states improve requires implementation, not verification
   - Clarifies "improve docs.md" means edit the file, not review it
   - Distinguishes improve from verify action

3. Strengthened Default Behavior section with reminder note:
   - improve requires full implementation (Plan → Implement → Verify → Complete)
   - Do not skip Implementation phase
   - improve means make changes to files, not just review

### Verification Results
- Tests: PASS
- Lint: PASS
- Types: PASS
- Integration: PASS
