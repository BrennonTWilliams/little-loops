# Continuation Prompt Template

This template is used by agents when generating handoff prompts for fresh session continuation.
The agent should fill in the bracketed sections with actual values.

---

# Session Continuation: [ISSUE-ID]

## Context
[2-3 sentence summary of what was being worked on, including the issue title and type]

## Completed Work
[List completed phases/steps with file:line references]
- [x] Phase 1: [Name] - completed at [file:line]
- [x] Phase 2: [Name] - completed at [file:line]

## Current State
- **Working on**: Phase [N]: [Name]
- **Last action**: [What was just completed before handoff]
- **Next action**: [Immediate next step to take]

## Key File References
- **Plan**: `thoughts/shared/plans/[YYYY-MM-DD]-[ISSUE-ID]-management.md`
- **Modified files**:
  - `[file:line]` - [brief description]
  - `[file:line]` - [brief description]
- **Test files**: `[test-file]`

## Resume Command
```bash
/ll:manage_issue [type] [action] [ISSUE-ID] --resume
```

Or continue manually from the plan.

## Critical Context
[Information that would be lost without this prompt - keep this focused and essential]

### Decisions Made
- [Decision 1: chose X over Y because...]
- [Decision 2: ...]

### Gotchas Discovered
- [Gotcha 1: watch out for...]
- [Gotcha 2: ...]

### Patterns Being Followed
- Following pattern from `[file:line]`
- Using convention established in `[file:line]`

---

## Template Usage Notes

This template is automatically populated by Claude when:
1. **PreCompact hook** triggers (context approaching limits)
2. **Proactive handoff** during manage_issue (agent detects low context)

The filled template is written to: `.claude/ll-continue-prompt.md`

### For Automation (ll-auto)
When automation detects `CONTEXT_HANDOFF: Ready for fresh session` in output:
1. Read `.claude/ll-continue-prompt.md`
2. Start new Claude session with that content as the prompt
3. Continue processing

### For Manual Sessions
User can:
1. Copy content from `.claude/ll-continue-prompt.md`
2. Start new Claude Code session
3. Paste as first prompt
4. Continue with fresh context
