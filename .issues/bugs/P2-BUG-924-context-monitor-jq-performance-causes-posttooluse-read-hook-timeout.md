---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# BUG-924: context-monitor.sh jq performance causes PostToolUse:Read hook timeout

## Summary

The `context-monitor.sh` PostToolUse hook (matcher: `*`) exceeds the 5-second hook timeout due to heavy `jq` processing. Two compounding bottlenecks cause this: (1) the full hook input JSON — which includes the complete `tool_response` (entire file contents for Read calls) — is parsed by `jq` three separate times via `echo "$INPUT" | jq`, and (2) the full transcript JSONL is slurped into memory on every tool call to detect the model. Together these easily exceed 5 seconds for mid-session Read calls of moderate files.

## Steps to Reproduce

1. Start a Claude Code session and work through several conversation turns (building up the transcript JSONL)
2. Read a moderate-to-large file (200+ lines)
3. Observe "PostToolUse:Read hook error" in the Claude Code UI

## Current Behavior

Three separate `echo "$INPUT" | jq` calls parse the full hook input (which contains the complete file contents for Read):
```bash
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""' ...)
TOOL_RESPONSE=$(echo "$INPUT" | jq -c '.tool_response // {}' ...)
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // ""' ...)
```

Then the entire transcript JSONL is slurped into memory:
```bash
DETECTED_MODEL=$(jq -rs 'map(select(.type == "assistant")) | last | .message.model // ""' "$TRANSCRIPT_PATH" ...)
```

Combined: ~1-2s for INPUT parsing (x3) + ~1-3s for transcript slurp + lock acquisition + state jq calls = exceeds 5s timeout. With `set -euo pipefail`, timeout signals cause immediate non-zero exit reported as "hook error."

## Expected Behavior

The hook completes well within the 5-second timeout for all tool calls, including Read calls on large files. INPUT should be parsed in a single `jq` pass, and the model should be cached in the state file after first detection rather than re-detected from the transcript on every call.

## Motivation

This bug causes visible "PostToolUse:Read hook error" messages in the Claude Code UI during normal usage. The error frequency increases as sessions grow longer (larger transcript) and is triggered by routine file reads. It degrades user trust in the hook system and may lead users to disable context monitoring entirely.

## Root Cause

- **File**: `hooks/scripts/context-monitor.sh`
- **Anchor**: Lines 45-47 (INPUT parsing) and line 50 (DETECTED_MODEL transcript slurp)
- **Cause**: Three separate `echo "$INPUT" | jq` invocations re-serialize and re-parse potentially megabytes of JSON (file contents embedded in `tool_response`). The transcript slurp (`jq -s`) loads the entire growing JSONL file into memory on every call. These compound under the 5-second hook timeout, especially mid-session with many turns.

## Error Messages

```
PostToolUse:Read hook error
```

Displayed in the Claude Code UI after Read tool calls when the hook exceeds its timeout.

## Proposed Solution

Four changes, all within `context-monitor.sh`:

### 1. Single-pass INPUT parsing (replace lines 45-47)
Replace three `echo "$INPUT" | jq` calls with one:
```bash
eval "$(echo "$INPUT" | jq -r '
  @sh "TOOL_NAME=\(.tool_name // "")",
  @sh "TRANSCRIPT_PATH=\(.transcript_path // "")"
' 2>/dev/null)" || { TOOL_NAME=""; TRANSCRIPT_PATH=""; }
```
Avoid extracting `tool_response` into a variable at all — pass `$INPUT` directly to `estimate_tokens` and extract `.tool_response` only within the specific tool case branches that need it.

### 2. Cache detected model in state file (replace line 50)
Read cached model from state; only detect from transcript on first call:
```bash
DETECTED_MODEL=$(echo "$STATE" | jq -r '.detected_model // ""')
if [ -z "$DETECTED_MODEL" ] && [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ]; then
    DETECTED_MODEL=$(tail -50 "$TRANSCRIPT_PATH" | jq -rs 'map(select(.type == "assistant")) | last | .message.model // ""' 2>/dev/null || echo "")
fi
```

### 3. Defer tool_response extraction into estimate_tokens
Pass raw `$INPUT` to `estimate_tokens` and extract `.tool_response` only within specific case branches (Read, Bash, Grep, Glob) that inspect response content.

### 4. Move transcript/model detection after lock acquisition
Move model detection inside `main()` after reading state, so the cached value can be checked first and the transcript skipped entirely.

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` — all changes in this single file

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — defines the PostToolUse hook entry (no changes needed)

### Similar Patterns
- N/A

### Tests
- Manual testing: simulate Read input via `echo '{"tool_name":"Read","tool_response":"test","transcript_path":""}' | bash hooks/scripts/context-monitor.sh`
- Verify state file updates: `cat .ll/ll-context-state.json`
- Run a Claude Code session and confirm no "PostToolUse:Read hook error" after Read calls

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Replace three `echo "$INPUT" | jq` calls with single-pass `eval`+`jq` extraction
2. Add model caching in state file; use `tail -50` for first-call transcript detection
3. Refactor `estimate_tokens` to accept raw `$INPUT` and extract `.tool_response` internally per-tool
4. Reorder `main()` to move model detection after lock/state-read
5. Test with simulated large Read input and verify completion under 5s

## Impact

- **Priority**: P2 - Causes visible errors in the UI during normal usage; worsens over session lifetime
- **Effort**: Small - All changes in a single shell script, well-understood bottlenecks
- **Risk**: Low - context-monitor.sh is a monitoring hook with no side effects on core functionality; changes are performance optimizations preserving existing behavior
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Hook system design and context monitoring architecture |

## Labels

`bug`, `hooks`, `performance`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-02 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2f1745da-4e21-4370-979f-bddf31a380b8.jsonl`

---

## Status

**Open** | Created: 2026-04-02 | Priority: P2
