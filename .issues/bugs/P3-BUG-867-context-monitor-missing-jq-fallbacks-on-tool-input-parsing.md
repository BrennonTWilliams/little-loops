---
id: BUG-867
discovered_date: 2026-03-23
discovered_by: capture-issue
---

# BUG-867: context-monitor.sh missing jq fallbacks on tool input parsing

## Summary

Lines 45-46 of `context-monitor.sh` call `jq` without `|| echo` fallbacks. With `set -euo pipefail` active, if `jq` receives malformed or empty stdin (e.g., a hook runner that passes no input), the script exits with `jq`'s non-zero exit code rather than degrading gracefully. Line 47 (`TRANSCRIPT_PATH`) already uses the correct `2>/dev/null || echo ""` pattern, making this an inconsistency rather than an unknown need.

## Current Behavior

```bash
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')       # no fallback — exits on jq error
TOOL_RESPONSE=$(echo "$INPUT" | jq -c '.tool_response // {}') # no fallback — exits on jq error
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // ""' 2>/dev/null || echo "") # correct
```

If `INPUT` is empty or malformed JSON, lines 45-46 cause the script to exit with jq's error code, which Claude Code's hook runner reports as a hook error.

## Expected Behavior

All three variable assignments should use the same defensive pattern. Malformed input should result in empty/default values and a graceful `exit 0` (the existing `[ -z "$TOOL_NAME" ]` guard at line ~212 already handles the empty case).

## Motivation

This is a latent crash path that becomes more likely in edge cases: automation contexts where hook input may be truncated, future Claude Code versions changing hook input format, or testing/debugging where the script is invoked directly. Fixing it makes the hook robust to unexpected inputs and consistent with the pattern already used on line 47.

## Steps to Reproduce

1. Run: `echo "" | bash hooks/scripts/context-monitor.sh`
2. Observe: non-zero exit from jq rather than clean exit 0

## Root Cause

- **File**: `hooks/scripts/context-monitor.sh`
- **Anchor**: top-level input parsing block (lines 44-48)
- **Cause**: Lines 45-46 were written without `|| echo` fallbacks. Line 47 was added later (or by a different author) with the correct pattern, creating inconsistency.

## Proposed Solution

Apply the same defensive pattern from line 47 to lines 45-46:

```bash
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")
TOOL_RESPONSE=$(echo "$INPUT" | jq -c '.tool_response // {}' 2>/dev/null || echo '{}')
```

No other changes needed — the existing `[ -z "$TOOL_NAME" ] && exit 0` guard handles the empty-TOOL_NAME case.

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` — lines 45-46, add `2>/dev/null || echo` fallbacks

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — registers context-monitor.sh as PostToolUse hook; no changes needed

### Similar Patterns
- `hooks/scripts/user-prompt-check.sh` — audit for same pattern (may have same gap)
- `hooks/scripts/session-start.sh` — uses jq; check for similar missing fallbacks

### Tests
- Manual: `echo "" | bash hooks/scripts/context-monitor.sh` should exit 0 after fix

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `2>/dev/null || echo ""` to line 45 (`TOOL_NAME`)
2. Add `2>/dev/null || echo '{}'` to line 46 (`TOOL_RESPONSE`)
3. Audit `user-prompt-check.sh` and `session-start.sh` for the same gap
4. Verify: `echo "" | bash hooks/scripts/context-monitor.sh` exits 0

## Impact

- **Priority**: P3 — Latent crash, not currently triggered in normal use; low-friction fix
- **Effort**: Small — 2-line change
- **Risk**: Low — purely additive; no behavior change on valid input
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`hooks`, `context-monitor`, `robustness`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/520e79f8-0528-4c6d-92c0-e09d2d2aa372.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P3
