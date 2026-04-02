---
discovered_date: 2026-04-02
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 86
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
- **Anchor**: Lines 45-47 (INPUT parsing), line 50 (DETECTED_MODEL transcript slurp), and lines 123-127 (`get_transcript_baseline` — second transcript slurp)
- **Cause**: Three separate `echo "$INPUT" | jq` invocations re-serialize and re-parse potentially megabytes of JSON (file contents embedded in `tool_response`). The transcript slurp (`jq -s`) loads the entire growing JSONL file into memory on every call. These compound under the 5-second hook timeout, especially mid-session with many turns.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Second transcript slurp not addressed**: `get_transcript_baseline()` at lines 120-128 performs a second `jq -s` full-file slurp on the transcript, called at line 257 **inside the lock-held critical section**. This compounds with the model detection slurp at line 50 (which runs pre-lock). The proposed solution only caches model detection but does not cache the transcript baseline.
- **Pre-lock time budget**: Lines 45-47 (INPUT parsing) + line 50 (transcript slurp) + line 228 (`estimate_tokens` with jq at line 63 for Read) all execute before the 3-second lock acquisition at line 232. This leaves virtually no margin.
- **Post-lock time budget**: After lock acquisition, `get_transcript_baseline` at line 257 performs the second slurp, followed by 7 `jq` calls on small state JSON (lines 248-252, 279, 284). The baseline slurp is the dominant cost in this phase.
- **Total jq invocations per Read call**: 3 (INPUT parsing) + 1 (model detection slurp) + 1 (estimate_tokens for Read) + 5 (state field extraction) + 2 (breakdown extraction) + 1 (state build) + 1 (baseline slurp) + 1 (atomic_write validation) = **15 jq subprocesses** minimum per invocation.

## Error Messages

```
PostToolUse:Read hook error
```

Displayed in the Claude Code UI after Read tool calls when the hook exceeds its timeout.

## Proposed Solution

Five changes, all within `context-monitor.sh`:

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

### 5. Cache transcript baseline in state file (missing from original proposal)

_Added by `/ll:refine-issue` — based on codebase analysis:_

`get_transcript_baseline()` at lines 120-128 performs a second full `jq -s` slurp of the transcript JSONL. The state file already stores `transcript_baseline_tokens` (written at line 295) but this value is **never read back as a cache** — `get_transcript_baseline` always re-slurps the file. Fix:
```bash
TRANSCRIPT_BASELINE=$(echo "$STATE" | jq -r '.transcript_baseline_tokens // 0')
if [ "$TRANSCRIPT_BASELINE" -le 0 ] 2>/dev/null && [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ]; then
    TRANSCRIPT_BASELINE=$(tail -50 "$TRANSCRIPT_PATH" | jq -s '...' 2>/dev/null || echo 0)
fi
```
This mirrors the model caching pattern proposed in fix #2 and eliminates the second slurp on all but the first call.

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` — all changes in this single file

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — defines the PostToolUse hook entry; timeout `5` at line 49, matcher `*` at line 44 (no changes needed)
- `hooks/scripts/lib/common.sh` — shared utilities (`acquire_lock`, `release_lock`, `atomic_write_json`, `ll_config_value`, `ll_feature_enabled`); no changes needed but relevant for understanding locking and config reads
- `hooks/scripts/precompact-state.sh` — reads `ll-context-state.json` for compaction snapshots; must remain compatible with any state schema changes

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `hooks/scripts/issue-completion-log.sh:16-29` — lighter hook that uses early-exit guard after extracting `tool_name`, avoiding unnecessary jq calls; same `echo "$INPUT" | jq -r` pattern
- `hooks/scripts/check-duplicate-issue-id.sh:31-32` — same INPUT parsing pattern, two fields only
- The proposed `eval "$(... | jq -r '@sh ...')"` pattern is **not used anywhere** in the codebase — this is a novel pattern that should be tested carefully
- `hooks/scripts/context-monitor.sh:288-295` — existing single-pass `jq --argjson` state update pattern; the state-write side already follows best practice

### Tests
- **Existing test file**: `scripts/tests/test_hooks_integration.py` — integration tests for context-monitor.sh with `subprocess.run`, tmp_path fixtures, JSONL transcript fixtures, and concurrent ThreadPoolExecutor tests
- Manual testing: simulate Read input via `echo '{"tool_name":"Read","tool_response":"test","transcript_path":""}' | bash hooks/scripts/context-monitor.sh`
- Verify state file updates: `cat .ll/ll-context-state.json`
- Run a Claude Code session and confirm no "PostToolUse:Read hook error" after Read calls
- **Suggested new tests**: Add a performance-oriented test that passes a large tool_response (1000+ lines) and asserts completion within 5 seconds, following the existing pattern at `test_hooks_integration.py:52-64`

### Documentation
- `docs/ARCHITECTURE.md` — hook system design and context monitoring architecture
- `docs/claude-code/hooks-reference.md` — hook system reference including timeouts
- `docs/development/TROUBLESHOOTING.md` — mentions hook timeouts and context monitor issues

### Configuration
- `.ll/ll-config.json` — `context_monitor` section (enabled, threshold, state_file, estimate_weights)
- `config-schema.json` — schema defining the `context_monitor` configuration object

### Related Completed Issues (same subsystem)
- `P3-BUG-869` — lock timeout tuning for this same hook (leaves 1s margin before hook timeout)
- `P3-BUG-867` — jq fallback handling in the same INPUT parsing code
- `P3-ENH-810` — added the JSONL transcript hybrid (introduced the transcript slurp)
- `P3-FEAT-812` — added model detection from transcript (introduced `DETECTED_MODEL` slurp)
- `P2-BUG-329` — `estimate_tokens` logic bug (token estimate never decreases after compaction)

## Implementation Steps

1. **Single-pass INPUT parsing** (lines 45-47): Replace three `echo "$INPUT" | jq` calls with single-pass `eval`+`jq` extraction. Note: the `eval "$(... | jq -r '@sh ...')"` pattern is novel to this codebase — test shell quoting edge cases.
2. **Cache model in state file** (line 50): Read cached model from `$STATE`; only detect from transcript on first call using `tail -50` instead of `jq -rs` full slurp.
3. **Defer tool_response extraction** (line 46): Pass raw `$INPUT` to `estimate_tokens`; extract `.tool_response` only within tool-specific branches (Read at line 63, Bash at lines 79-80, Grep at line 73, Glob at line 88).
4. **Move model detection after lock/state-read** (line 50 → after line 238): Move model detection inside `main()` after `read_state`, so the cached value in state can be checked first.
5. **Cache transcript baseline** (lines 256-258): Read `transcript_baseline_tokens` from `$STATE` first (already written at line 295 but never read back). Only call `get_transcript_baseline()` when the cached value is 0 or missing. Use `tail -50` instead of `jq -s` for the fallback slurp.
6. **Test**: Run existing tests at `scripts/tests/test_hooks_integration.py`; add a performance test with large tool_response (1000+ lines) asserting completion under 5s.

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

## Verification Notes

**Verified: 2026-04-02 | Verdict: VALID**

All claims confirmed against current codebase:

- **Lines 45-47**: Three separate `echo "$INPUT" | jq` calls confirmed at exact lines
- **Line 50**: Full `jq -rs` transcript slurp confirmed
- **Lines 120-128**: `get_transcript_baseline()` second slurp confirmed; value written to state at line 295 (`.transcript_baseline_tokens`) but never read back as cache
- **Line 257**: Transcript baseline call inside lock-held critical section confirmed
- **hooks.json**: Timeout `5` at line 49, matcher `*` at line 44 confirmed
- **15 jq subprocesses per Read call**: Count verified (3 INPUT + 1 model slurp + 1 estimate_tokens + 5 state extraction + 2 breakdown + 1 state build + 1 baseline slurp + 1 atomic_write validation)
- **Similar patterns**: `issue-completion-log.sh:16-29` and `check-duplicate-issue-id.sh:31-32` confirmed
- **Test file**: `scripts/tests/test_hooks_integration.py:52-64` confirmed with subprocess/ThreadPoolExecutor pattern
- **All referenced files exist**: context-monitor.sh, hooks.json, lib/common.sh, precompact-state.sh, all docs, all 5 completed issues
- **Integration map**: All dependent files, documentation, and config references verified

## Session Log
- `/ll:ready-issue` - 2026-04-02T22:19:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ce45c89-4ad8-4c6d-b8ea-43d33fdd3374.jsonl`
- `/ll:verify-issues` - 2026-04-02T22:15:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/290105ed-73d3-4d92-b9c4-5473c65fa704.jsonl`
- `/ll:confidence-check` - 2026-04-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/290105ed-73d3-4d92-b9c4-5473c65fa704.jsonl`
- `/ll:refine-issue` - 2026-04-02T22:11:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/290105ed-73d3-4d92-b9c4-5473c65fa704.jsonl`
- `/ll:format-issue` - 2026-04-02T22:05:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/290105ed-73d3-4d92-b9c4-5473c65fa704.jsonl`
- `/ll:capture-issue` - 2026-04-02 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2f1745da-4e21-4370-979f-bddf31a380b8.jsonl`

- `/ll:manage-issue` - 2026-04-02T22:30:00Z - `fix BUG-924`

---

## Resolution

**Fixed** — Reduced jq subprocess invocations from ~15 to ~5 per hook call through 5 optimizations:

1. **Single-pass INPUT parsing**: 3 `echo "$INPUT" | jq` calls → 1 `jq @tsv` call
2. **Deferred tool_response extraction**: `estimate_tokens` now reads `.tool_response` directly from raw `$INPUT` only in branches that need it; Read counts lines in jq (avoids full file content in bash var); Bash combines 2 jq calls into 1
3. **Cached model detection**: `detected_model` stored in state file; transcript only read on first call via `tail -50` (not full `jq -s` slurp)
4. **Consolidated state extraction**: 7 individual `jq -r` calls → 1 multi-field jq call
5. **Cached transcript baseline**: `transcript_baseline_tokens` from state reused; `get_transcript_baseline()` uses `tail -50` instead of full slurp; only called when cache is 0

---

## Status

**Completed** | Created: 2026-04-02 | Resolved: 2026-04-02 | Priority: P2
