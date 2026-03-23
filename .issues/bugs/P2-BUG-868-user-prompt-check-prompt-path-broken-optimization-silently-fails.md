---
discovered_date: 2026-03-23
discovered_by: capture-issue
---

# BUG-868: user-prompt-check.sh prompt path broken — optimization silently fails

## Summary

`user-prompt-check.sh` constructs the hook prompt file path using `${CLAUDE_PLUGIN_ROOT}/prompts/optimize-prompt-hook.md`, but the actual file lives at `${CLAUDE_PLUGIN_ROOT}/hooks/prompts/optimize-prompt-hook.md`. Since `CLAUDE_PLUGIN_ROOT` is always set during hook execution, the fallback (`$SCRIPT_DIR/..`) never fires, causing prompt optimization to silently fail on every user prompt.

## Steps to Reproduce

1. Install the little-loops plugin in any project
2. Submit a user prompt longer than 10 characters
3. Observe: no prompt enhancement is injected; hook exits 0 without error

## Current Behavior

The script sets `HOOK_PROMPT_FILE="${CLAUDE_PLUGIN_ROOT:-$SCRIPT_DIR/..}/prompts/optimize-prompt-hook.md"`. When `CLAUDE_PLUGIN_ROOT` is set (always during hook execution), this resolves to `$CLAUDE_PLUGIN_ROOT/prompts/optimize-prompt-hook.md` — a path that does not exist. The `[ ! -f "$HOOK_PROMPT_FILE" ]` guard fires, logs a debug message, and exits 0. Optimization is silently dropped on every prompt.

## Expected Behavior

The path should resolve to `hooks/prompts/optimize-prompt-hook.md` relative to the plugin root (where the file actually lives). Prompt optimization should inject the template content into context on every qualifying user prompt.

## Root Cause

- **File**: `hooks/scripts/user-prompt-check.sh`
- **Anchor**: `HOOK_PROMPT_FILE` assignment (~line 81)
- **Cause**: `${CLAUDE_PLUGIN_ROOT:-$SCRIPT_DIR/..}` is intended to fall back to `$SCRIPT_DIR/..` (which resolves to `hooks/`) when `CLAUDE_PLUGIN_ROOT` is unset. But `CLAUDE_PLUGIN_ROOT` is always set during hook execution — it is required by the hook command itself. The primary branch path is missing the `hooks/` component: `$CLAUDE_PLUGIN_ROOT/prompts/` should be `$CLAUDE_PLUGIN_ROOT/hooks/prompts/`.

## Motivation

Prompt optimization is a core plugin feature that has been silently non-functional for all users since deployment. Every user prompt passes through this hook but receives no enhancement. The fix is a single line — high value for minimal effort.

## Proposed Solution

Remove the `CLAUDE_PLUGIN_ROOT` branch and always resolve relative to `$SCRIPT_DIR`:

```bash
# Before:
HOOK_PROMPT_FILE="${CLAUDE_PLUGIN_ROOT:-$SCRIPT_DIR/..}/prompts/optimize-prompt-hook.md"

# After (always correct, no env var ambiguity):
HOOK_PROMPT_FILE="${SCRIPT_DIR}/../prompts/optimize-prompt-hook.md"
```

This matches how other scripts in `hooks/scripts/` resolve sibling paths and is unambiguous regardless of whether `CLAUDE_PLUGIN_ROOT` is set.

## Integration Map

### Files to Modify
- `hooks/scripts/user-prompt-check.sh` — fix `HOOK_PROMPT_FILE` assignment

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — registers this script as the `UserPromptSubmit` handler

### Similar Patterns
- Other scripts in `hooks/scripts/` that reference `$SCRIPT_DIR` or `$CLAUDE_PLUGIN_ROOT` — verify path patterns are consistent

### Tests
- TBD — add test that path resolves to an existing file

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Fix `HOOK_PROMPT_FILE` assignment in `user-prompt-check.sh`
2. Verify the resolved path exists: `ls "${SCRIPT_DIR}/../prompts/optimize-prompt-hook.md"`
3. Test by submitting a prompt and confirming optimization template content appears in context

## Impact

- **Priority**: P2 - Core prompt optimization feature completely non-functional for all users since deployment
- **Effort**: Small - Single line change
- **Risk**: Low - Isolated path assignment; no logic changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`hooks`, `bug`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e087610-8d6c-49f4-bacd-b3c561cb7252.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P2
