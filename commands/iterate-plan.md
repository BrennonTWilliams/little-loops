---
description: Iterate on existing implementation plans with thorough research and updates
argument-hint: "[plan-path]"
allowed-tools:
  - Read
  - Edit
  - Task
  - Bash(ls:*)
arguments:
  - name: plan_path
    description: Path to existing plan file to iterate on
    required: false
---

# Iterate Plan

You are tasked with iterating on an existing implementation plan, updating it based on new research or changed requirements.

## Process

### 1. Find Plan File

```bash
PLAN_PATH="${plan_path}"

if [ -z "$PLAN_PATH" ]; then
    # Find most recent plan
    PLAN_PATH=$(ls -t thoughts/shared/plans/*.md 2>/dev/null | head -1)
fi

if [ -z "$PLAN_PATH" ]; then
    echo "No plan file found. Use /ll:manage-issue to create one."
    exit 1
fi

echo "Iterating on: $PLAN_PATH"
```

### 2. Review Current Plan

Read the existing plan and identify:
- Completed phases
- Pending phases
- Blockers or issues encountered
- Assumptions that need validation

### 3. Research Updates

**Only spawn research tasks if the changes require new technical understanding.**

For pending phases, first assess what research is needed:
1. **Re-read affected files** - Has code changed since plan was created?
2. **Validate approach** - Is the planned approach still best?
3. **Check dependencies** - Are required changes still needed?
4. **Test assumptions** - Were any assumptions incorrect?

If the user's feedback requires understanding new code patterns or validating assumptions, **spawn parallel sub-tasks for research**:

Use the right agent for each type of research:
- **codebase-locator** - To find relevant files and directories
- **codebase-analyzer** - To understand implementation details
- **codebase-pattern-finder** - To find similar patterns to model after

**Sub-task Guidelines:**
- Only spawn if truly needed - don't research for simple changes
- Spawn multiple tasks in parallel for efficiency
- Each task should be focused on a specific area
- Provide detailed instructions including directories to focus on
- Request specific file:line references in responses
- Wait for all tasks to complete before synthesizing
- Verify sub-task results - if something seems off, spawn follow-up tasks

### 4. Present Understanding and Approach

Before making changes, confirm your understanding with the user:

```markdown
Based on your feedback, I understand you want to:
- [Change 1 with specific detail]
- [Change 2 with specific detail]

My research found:
- [Relevant code pattern or constraint]
- [Important discovery that affects the change]

I plan to update the plan by:
1. [Specific modification to make]
2. [Another modification]

Does this align with your intent? (y/n)
```

**Get user confirmation before proceeding to edits.**

### 5. Update Plan

**Make focused, precise edits** to the existing plan:
- Use the Edit tool for surgical changes
- Maintain existing structure unless explicitly changing it
- Keep all file:line references accurate

Modify the plan file with:
- Status updates for completed phases
- Revised approach for problematic areas
- New discoveries or considerations
- Updated file references if code moved

**When updating success criteria**, maintain two categories:

1. **Automated Verification** (can be run by execution agents):
   - Commands that can be run: `make test`, `npm run lint`, etc.
   - Specific files that should exist
   - Code compilation/type checking

2. **Manual Verification** (requires human testing):
   - UI/UX functionality
   - Performance under real conditions
   - Edge cases that are hard to automate

**Success Criteria Format Example**:
```markdown
#### Success Criteria

**Automated Verification** (commands that can be run):
- [ ] `pytest tests/` passes
- [ ] `ruff check .` passes
- [ ] `mypy src/` passes

**Manual Verification** (requires human judgment):
- [ ] Feature behaves correctly when tested via CLI
- [ ] Error messages are clear and actionable
- [ ] No regressions in related functionality
```

Add an iteration section:
```markdown
---

## Iteration Log

### Iteration 1 (YYYY-MM-DD)
- **Reason**: [Why iteration was needed]
- **Changes**:
  - Updated Phase 2 approach due to [discovery]
  - Added new Phase 4 for [additional requirement]
  - Removed Phase 3 (already completed elsewhere)
- **Blockers Resolved**: [What was blocking and how resolved]
```

### 6. Validate Updated Plan

Check that the updated plan:
- [ ] References files that exist
- [ ] Accounts for code changes since original plan
- [ ] Has clear, actionable phases
- [ ] Includes verification steps
- [ ] Addresses any discovered blockers

### 7. Output Summary

```markdown
# Plan Iteration Summary

## Plan File
`{plan_path}`

## Status Before Iteration
- Phases complete: X/Y
- Blockers: [list]
- Issues: [list]

## Changes Made
1. [Change 1]
2. [Change 2]

## Status After Iteration
- Phases complete: X/Y
- Next phase: [phase name]
- Ready for implementation: Yes/No

## Next Steps
- [Recommended next action]
```

---

## Arguments

$ARGUMENTS

- **plan_path** (optional): Path to plan file
  - If provided, iterate on that specific plan
  - If omitted, find most recent plan in `thoughts/shared/plans/`

---

## Examples

```bash
# Iterate on most recent plan
/ll:iterate-plan

# Iterate on specific plan
/ll:iterate-plan thoughts/shared/plans/2024-01-15-BUG-042-management.md
```

---

## Integration

Use this when:
- `/ll:manage-issue` was interrupted
- Requirements changed mid-implementation
- Blockers were encountered
- Codebase changed since plan creation

After iterating:
- Continue with implementation
- Or create new issue if scope changed significantly

---

## Important Guidelines

1. **Be Skeptical**:
   - Don't blindly accept change requests that seem problematic
   - Question vague feedback - ask for clarification
   - Verify technical feasibility with code research
   - Point out potential conflicts with existing plan phases

2. **Be Surgical**:
   - Make precise edits, not wholesale rewrites
   - Preserve good content that doesn't need changing
   - Only research what's necessary for the specific changes
   - Don't over-engineer the updates

3. **Be Thorough**:
   - Read the entire existing plan before making changes
   - Research code patterns if changes require new technical understanding
   - Ensure updated sections maintain quality standards
   - Verify success criteria are still measurable

4. **No Open Questions**:
   - If the requested change raises questions, ASK
   - Research or get clarification immediately
   - Do NOT update the plan with unresolved questions
   - Every change must be complete and actionable
