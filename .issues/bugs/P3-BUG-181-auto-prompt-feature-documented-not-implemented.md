---
discovered_date: 2026-01-29
discovered_by: capture_issue
---

# BUG-181: Auto-prompt feature documented but not implemented

## Summary

The auto-prompt optimization feature is extensively documented across multiple files (config schema, command docs, agent definition, CHANGELOG, README) but the actual runtime implementation is completely missing. The feature appears functional on paper but does nothing.

## Context

Identified during investigation of the `/ll:toggle_autoprompt` command and related prompt optimization functionality. User asked "Is it a real feature? Does it work?" - the answer is it's designed but non-functional.

## Current Behavior

- Config schema defines `prompt_optimization` settings (enabled, mode, confirm, bypass_prefix, clarity_threshold)
- `commands/toggle_autoprompt.md` provides complete user documentation
- `agents/prompt-optimizer.md` defines the specialized agent for thorough mode
- CHANGELOG v1.0.0 lists it as an added feature
- README and docs/COMMANDS.md reference the command

**However:**
- No hook file exists at `hooks/prompts/optimize-prompt-hook.md`
- No `UserPromptSubmit` hook is registered in `hooks/hooks.json`
- No Python backend executes the toggle logic
- No script performs actual prompt optimization or clarity scoring
- Running `/ll:toggle_autoprompt` would change settings that nothing reads

## Expected Behavior

When enabled, the auto-prompt feature should:
1. Intercept user prompts via a `UserPromptSubmit` hook
2. Check if optimization is enabled in config
3. Skip optimization for bypass patterns (`*` prefix, `/` commands, `#` notes, `?` questions, short prompts)
4. In **quick mode**: Use project docs (CLAUDE.md, CONTRIBUTING.md, README.md) to enhance prompts
5. In **thorough mode**: Spawn the `prompt-optimizer` agent for deep codebase search
6. If `confirm` is ON: Show diff and wait for approval
7. If `confirm` is OFF: Auto-apply optimization

## Proposed Solution

Implement the missing components:

1. **Create `hooks/prompts/optimize-prompt-hook.md`** - The hook prompt that intercepts user submissions
2. **Register hook in `hooks/hooks.json`** - Add `UserPromptSubmit` event handler
3. **Implement hook logic** - Clarity scoring, bypass detection, mode switching
4. **Test the feature** - Verify quick mode, thorough mode, bypass patterns, and confirmation flow

Alternatively, if this feature is not planned for implementation:
- Remove from CHANGELOG
- Remove from README/docs
- Remove config schema section
- Remove command and agent files
- Document as "planned but not implemented" somewhere

## Impact

- **Priority**: P3 (the feature is advertised but doesn't work - misleading but not breaking)
- **Effort**: Medium (hook implementation, testing)
- **Risk**: Low (new functionality, no existing behavior to break)

## Files Involved

**Existing (documentation only):**
- `config-schema.json:334-368` - Config definition
- `commands/toggle_autoprompt.md` - Command docs
- `agents/prompt-optimizer.md` - Agent definition
- `CHANGELOG.md` - Lists as added feature
- `README.md` - Command table reference
- `docs/COMMANDS.md` - Command documentation

**Missing (implementation):**
- `hooks/prompts/optimize-prompt-hook.md` - Hook prompt file
- `hooks/hooks.json` - Hook registration
- Hook script/logic for execution

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Hook lifecycle and plugin structure |
| guidelines | CONTRIBUTING.md | Development patterns for hooks |

## Labels

`bug`, `documentation-mismatch`, `captured`

---

## Status

**Open** | Created: 2026-01-29 | Priority: P3
