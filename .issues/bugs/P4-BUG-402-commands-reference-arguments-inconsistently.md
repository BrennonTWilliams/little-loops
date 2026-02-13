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

## Integration Map

### Files to Modify
- Commands in `commands/` that have `arguments:` frontmatter but no `$ARGUMENTS` in body

### Tests
- Invoke each affected command with an argument and verify it's handled correctly

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

## Labels

`bug`, `commands`, `configuration`, `ux`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4
