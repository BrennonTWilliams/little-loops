---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# BUG-402: Commands reference $ARGUMENTS inconsistently

## Summary

Per `docs/claude-code/skills.md`, if a command doesn't contain `$ARGUMENTS` in its body, arguments are appended as `"ARGUMENTS: <value>"`. Some commands define `arguments:` in frontmatter but don't use `$ARGUMENTS` in the body, relying on implicit append behavior. This causes confusion when arguments have specific semantics (flags, IDs, paths) because the argument arrives as an unstructured appended string rather than being parsed at a well-defined location in the prompt.

## Current Behavior

Commands like `manage_issue`, `format_issue`, and others define `arguments:` in frontmatter:
```yaml
---
arguments: "issue_file_path"
---
```

But their body has no `$ARGUMENTS` placeholder. Claude Code appends the argument as `"ARGUMENTS: <value>"` at the end of the prompt, which may be ignored or misinterpreted depending on prompt structure.

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
- Commands in `commands/` that have `arguments:` frontmatter but no `$ARGUMENTS` in body

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
- **Effort**: Small-Medium - Requires reading each command's body to place $ARGUMENTS correctly
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

## Session Log
- `/ll:format_issue --all --auto` - 2026-02-13

## Status

**Open** | Created: 2026-02-12 | Priority: P4
