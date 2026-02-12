---
discovered_date: 2026-02-12
discovered_by: hooks-reference-audit
supersedes: P4-BUG-361 (dead code finding was a symptom, not the root cause)
---

# BUG-361: user-prompt-check.sh exit 2 erases user prompt instead of enhancing it

## Summary

`hooks/scripts/user-prompt-check.sh` uses `exit 2` to inject prompt optimization content into the conversation. Per the hooks reference, exit 2 on `UserPromptSubmit` **blocks prompt processing and erases the prompt**. The script intends to enhance the user's prompt but instead destroys it.

The previously filed BUG-361 identified the dead `exit 0` on line 103 as a trivial dead-code issue. That was a symptom — the real bug is that `exit 2` on line 101 erases the user's original input.

## Location

- **File**: `hooks/scripts/user-prompt-check.sh:98-103`

## Steps to Reproduce

1. Enable prompt optimization in `.claude/ll-config.json` (`prompt_optimization.enabled: true`)
2. Submit a normal prompt (>10 chars, no bypass prefix) in Claude Code
3. `user-prompt-check.sh` fires, builds hook content, writes to stderr, and exits with code 2
4. Observe: user's original prompt is erased from context

## Current Behavior

```bash
# Output to stderr with exit 2 to ensure it reaches Claude
# Reference: https://github.com/anthropics/claude-code/issues/11224
echo "$HOOK_CONTENT" >&2
exit 2

exit 0  # dead code — never reached
```

When prompt optimization triggers:
1. The optimization template is written to stderr
2. `exit 2` fires — Claude Code **blocks the prompt and erases it from context**
3. stderr content is shown to Claude as an error, but the user's original prompt is gone

## Actual Behavior

The user's original prompt is destroyed. The optimization template content reaches Claude as an error message via stderr, but Claude has no access to the original prompt it was meant to enhance.

## Expected Behavior

Per the hooks reference, `UserPromptSubmit` on exit 0:
> "any non-JSON text written to stdout is added as context"

```bash
# Output to stdout with exit 0 — added as context alongside the user's prompt
echo "$HOOK_CONTENT"
exit 0
```

Alternatively, use JSON with `additionalContext` for more structured control:
```bash
jq -n --arg ctx "$HOOK_CONTENT" '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":$ctx}}'
exit 0
```

## Root Cause

- **File**: `hooks/scripts/user-prompt-check.sh`
- **Anchor**: lines 98-101 (the final output block)
- **Cause**: The script uses `exit 2` + stderr to deliver hook content, but for `UserPromptSubmit`, exit 2 means "block and erase the prompt." The correct approach is `exit 0` + stdout, which adds content as context alongside the user's prompt.

## Proposed Solution

Change the output mechanism from stderr+exit 2 to stdout+exit 0:

```bash
# Output to stdout with exit 0 — added as context alongside the user's prompt
echo "$HOOK_CONTENT"
exit 0
```

Remove the dead `exit 0` on line 103. The fix is two changes in `user-prompt-check.sh`:
1. Replace `echo "$HOOK_CONTENT" >&2` with `echo "$HOOK_CONTENT"` (stdout instead of stderr)
2. Replace `exit 2` with `exit 0`
3. Remove dead `exit 0` on line 103

## Reference

- `docs/claude-code/hooks-reference.md` — "Exit code 2 behavior per event" table: `UserPromptSubmit — Yes [can block] — Blocks prompt processing and erases the prompt`
- `docs/claude-code/hooks-reference.md` — "UserPromptSubmit decision control": plain text stdout on exit 0 is added as context

## Impact

- **Priority**: P2 (prompt optimization actively destroys user input when it fires)
- **Effort**: Small — change output target from stderr to stdout, change exit code from 2 to 0
- **Risk**: Low — straightforward fix with clear reference documentation

## Labels

`bug`, `hooks`, `user-prompt-check`, `data-loss`

## Resolution

- **Action**: fix
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `hooks/scripts/user-prompt-check.sh`: Changed output from stderr+exit 2 to stdout+exit 0, removed dead code
- `scripts/tests/test_hooks_integration.py`: Updated test assertion to expect only exit code 0

### Verification Results
- Tests: PASS (30/30)
- Lint: PASS

## Session Log
- `/ll:manage_issue` - 2026-02-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c3052a7-a34f-494d-9545-a1135642648a.jsonl`

---

## Status

**Completed** | Updated: 2026-02-12 | Priority: P2
