---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# BUG-402: Commands reference $ARGUMENTS inconsistently

## Summary

Per `docs/claude-code/skills.md`, if a command doesn't contain `$ARGUMENTS` in its body, arguments are appended as `"ARGUMENTS: <value>"`. Some commands define `arguments:` in frontmatter but don't use `$ARGUMENTS` in the body, relying on implicit append behavior. This causes confusion when arguments have specific semantics (flags, IDs, paths) because the argument arrives as an unstructured appended string rather than being parsed at a well-defined location in the prompt.

## Current Behavior

Six commands define `arguments:` in frontmatter but have no `$ARGUMENTS` placeholder in their body:

1. `commands/configure.md` — accepts `area` and `flags` arguments
2. `commands/create_sprint.md` — accepts `name`, `description`, and `issues` arguments
3. `commands/handoff.md` — accepts `context` and `flags` arguments
4. `commands/resume.md` — accepts `prompt_file` argument
5. `commands/sync_issues.md` — accepts `action` and `issue_id` arguments
6. `commands/toggle_autoprompt.md` — accepts `setting` argument

Claude Code appends arguments as `"ARGUMENTS: <value>"` at the end of the prompt, which may be ignored or misinterpreted depending on prompt structure.

**Note**: Previously affected commands (`manage_issue`, `format_issue`, etc.) have since been fixed.

## Expected Behavior

Commands that accept arguments should include an explicit `$ARGUMENTS` reference in their body where the argument value should be inserted:

```markdown
## Input

Process the issue at: $ARGUMENTS
```

This ensures arguments are placed at a semantically appropriate location in the prompt rather than appended as an afterthought.

## Motivation

This bug would:
- Ensure consistent and reliable argument handling across all commands that accept arguments
- Business value: Improves command UX by placing arguments at semantically appropriate locations in prompts
- Technical debt: Eliminates reliance on implicit append behavior that can cause arguments to be ignored or misinterpreted

## Root Cause

- **File**: Multiple command files in `commands/`
- **Anchor**: `in frontmatter and body`
- **Cause**: Commands define `arguments:` in frontmatter but omit `$ARGUMENTS` in their body, relying on Claude Code's implicit behavior of appending `"ARGUMENTS: <value>"` at the end of the prompt rather than placing the argument at a well-defined location

## Integration Map

### Files to Modify
- `commands/configure.md`
- `commands/create_sprint.md`
- `commands/handoff.md`
- `commands/resume.md`
- `commands/sync_issues.md`
- `commands/toggle_autoprompt.md`

### Tests
- N/A — command markdown frontmatter standardization; verified by invoking affected commands with arguments

### Documentation
- `docs/COMMANDS.md` — document $ARGUMENTS convention if not already covered

## Implementation Steps

1. Grep command files for `arguments:` in frontmatter
2. For each, check if `$ARGUMENTS` appears in the body
3. For commands missing `$ARGUMENTS`:
   a. Determine where the argument should be used in the prompt
   b. Add `$ARGUMENTS` at the appropriate location
   c. Add a fallback instruction for when no argument is provided (e.g., "If no argument provided, ask the user")
4. Test representative commands with and without arguments

## Impact

- **Priority**: P4 - Correctness issue, but implicit append usually works
- **Effort**: Small - 6 remaining commands need $ARGUMENTS placement (21 others already fixed)
- **Risk**: Low - Improving argument handling, unlikely to break existing usage
- **Breaking Change**: No

## Blocked By

- ENH-399: Add allowed-tools to commands — modifies same command files, should complete first
- ENH-400: Migrate oversized commands to skill directories — restructures command files

## Blocks

- ENH-398: Skill frontmatter missing allowed-tools — BUG-402 argument fix should land first
- ENH-401: Add argument-hint to commands — depends on $ARGUMENTS placement being resolved

## Labels

`bug`, `commands`, `configuration`, `ux`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `commands/configure.md`: Added `## Arguments` section with `$ARGUMENTS` placeholder
- `commands/create_sprint.md`: Added `## Arguments` section with `$ARGUMENTS` placeholder
- `commands/handoff.md`: Added `## Arguments` section with `$ARGUMENTS` placeholder
- `commands/resume.md`: Added `## Arguments` section with `$ARGUMENTS` placeholder
- `commands/sync_issues.md`: Added `$ARGUMENTS` to existing `## Arguments` section
- `commands/toggle_autoprompt.md`: Added `## Arguments` section with `$ARGUMENTS` placeholder

### Verification Results
- Tests: PASS (2728 passed)
- Lint: PASS
- Types: PASS
- Integration: PASS

## Session Log
- `/ll:format-issue --all --auto` - 2026-02-13
- `/ll:manage-issue` - 2026-02-13T01:47:24Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-worker-bug-402-20260213-014724/613343a6-7a6e-4f0f-ab97-376e6544996d.jsonl`

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-13 | Priority: P4
