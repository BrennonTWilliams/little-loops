---
description: Iterate on existing implementation plans with thorough research and updates
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
    echo "No plan file found. Use /ll:manage_issue to create one."
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

For pending phases:
1. **Re-read affected files** - Has code changed since plan was created?
2. **Validate approach** - Is the planned approach still best?
3. **Check dependencies** - Are required changes still needed?
4. **Test assumptions** - Were any assumptions incorrect?

### 4. Update Plan

Modify the plan file with:
- Status updates for completed phases
- Revised approach for problematic areas
- New discoveries or considerations
- Updated file references if code moved

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

### 5. Validate Updated Plan

Check that the updated plan:
- [ ] References files that exist
- [ ] Accounts for code changes since original plan
- [ ] Has clear, actionable phases
- [ ] Includes verification steps
- [ ] Addresses any discovered blockers

### 6. Output Summary

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
/ll:iterate_plan

# Iterate on specific plan
/ll:iterate_plan thoughts/shared/plans/2024-01-15-BUG-042-management.md
```

---

## Integration

Use this when:
- `/ll:manage_issue` was interrupted
- Requirements changed mid-implementation
- Blockers were encountered
- Codebase changed since plan creation

After iterating:
- Continue with implementation
- Or create new issue if scope changed significantly
