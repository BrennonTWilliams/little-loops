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

## Reference

- `docs/claude-code/hooks-reference.md` — "Exit code 2 behavior per event" table: `UserPromptSubmit — Yes [can block] — Blocks prompt processing and erases the prompt`
- `docs/claude-code/hooks-reference.md` — "UserPromptSubmit decision control": plain text stdout on exit 0 is added as context

## Impact

- **Priority**: P2 (prompt optimization actively destroys user input when it fires)
- **Effort**: Small — change output target from stderr to stdout, change exit code from 2 to 0
- **Risk**: Low — straightforward fix with clear reference documentation

## Labels

`bug`, `hooks`, `user-prompt-check`, `data-loss`

---

## Status

**Open** | Updated: 2026-02-12 | Priority: P2
