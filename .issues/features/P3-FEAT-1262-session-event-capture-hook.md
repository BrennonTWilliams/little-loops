---
id: FEAT-1262
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-22
discovered_by: issue-size-review
blocked_by: [FEAT-1116, FEAT-1112]
parent: FEAT-1159
related: [FEAT-1112, FEAT-1156, FEAT-1264]
---

# FEAT-1262: Session Event Capture Hook (`session-capture.sh`)

## Summary

Implement `hooks/scripts/session-capture.sh` as a PostToolUse hook that continuously appends structured event records to `.ll/ll-session-events.jsonl` throughout the session, providing the data source for event-log-driven handoff snapshots.

## Parent Issue

Decomposed from FEAT-1159: Continuous Session Event Capture with PreCompact Guarantee and SessionStart Injection

## Motivation

The current handoff approach (`/ll:handoff`, `precompact-handoff.sh`) reconstructs state at the moment of handoff — from git diff, ll-issues list, and loop JSON. This is lossy: it cannot mechanically compute which tasks are pending vs completed, which files were net-modified, or what errors remain unresolved. Continuous event capture records state as it happens, giving the PreCompact snapshot builder (FEAT-1264) a complete, structured history to work from.

## Acceptance Criteria

- `hooks/scripts/session-capture.sh` exists and is executable
- Hook fires PostToolUse and appends one JSON event record per invocation to `.ll/ll-session-events.jsonl`
- Event schema: `{"ts": "ISO8601", "type": "file|task|git|error|decision|plan", "op": "...", "subject": "...", "status": ""}`
- Captured event types:
  - **file**: Read, Write, Edit, Glob, Grep — `op` = tool name, `subject` = filename
  - **task**: TodoWrite, TaskCreate, TaskUpdate — `op` = tool name, `subject` + `status` from JSON payload
  - **git**: any Bash invocation containing `git` — `op` = git subcommand, `subject` = args
  - **error**: Bash non-zero exit — `op` = "bash_error", `subject` = command (truncated), `status` = exit code
- Hook is failure-safe: errors must not block tool execution (exit 0 on all failure paths)
- Hook adds no noticeable latency for high-frequency tool calls (jq extraction + one append)
- `hooks/hooks.json` registers the script as a PostToolUse entry
- `TestSessionCapture` class added to `scripts/tests/test_hooks_integration.py`
- If FEAT-1112 (session store) is available, writes to its store instead of flat JSONL; otherwise falls back to JSONL

## Implementation

### New File: `hooks/scripts/session-capture.sh`

Follow `precompact-state.sh` structure:
- Read stdin JSON, extract `tool_name` and `tool_input` via jq
- Source `hooks/scripts/lib/common.sh`
- Check `ll_feature_enabled` guard
- Map tool name → event type using a case statement
- Build event JSON record with `jq -n`
- Append to `.ll/ll-session-events.jsonl` using `acquire_lock` / `release_lock` from `lib/common.sh`
- All error paths exit 0 (capture failures must not interrupt tool execution)

### Event Schema

```json
{"ts": "2026-04-22T20:00:00Z", "type": "file", "op": "Write", "subject": "scripts/foo.py", "status": ""}
{"ts": "2026-04-22T20:01:00Z", "type": "git", "op": "commit", "subject": "-m 'fix: ...'", "status": ""}
{"ts": "2026-04-22T20:02:00Z", "type": "error", "op": "bash_error", "subject": "pytest ...", "status": "1"}
```

### Registration: `hooks/hooks.json`

Add `session-capture.sh` to the PostToolUse array. Multiple PostToolUse hooks are supported.

### Tests: `TestSessionCapture`

Add to `scripts/tests/test_hooks_integration.py`, modeled after `TestPrecompactState` (line 1468):
- Hook produces a valid JSONL record for each captured event type
- Hook exits 0 even when jq is missing or stdin is malformed
- Concurrent invocations don't corrupt the JSONL file (lock acquisition verified)
- Unknown tool names produce no record (or a best-effort `type: unknown` record — decide during implementation)

## Files to Modify

- `hooks/hooks.json` — add PostToolUse entry for `session-capture.sh`
- `scripts/tests/test_hooks_integration.py` — add `TestSessionCapture` class

## New Files

- `hooks/scripts/session-capture.sh`

## Scope Boundary

This issue owns only the capture side: writing `.ll/ll-session-events.jsonl`. It does NOT modify `precompact-handoff.sh` (FEAT-1264 owns that integration) and does NOT implement the SessionStart injector (FEAT-1263).

FEAT-1116 risk: `session-capture.sh` is a PostToolUse shell script in the layer FEAT-1116 is migrating to Python core handlers. Implement as specified here for unblocked delivery; plan a follow-up to migrate to the FEAT-1116 adapter pattern.

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- `hooks/scripts/session-capture.sh` does not exist ✓
- No PostToolUse event capture entry in `hooks/hooks.json` for session events ✓
- Feature not yet implemented ✓

## References

- Parent: FEAT-1159
- Consumer of this output: FEAT-1264 (precompact-handoff.sh event-log integration)
- Session store integration: FEAT-1112 (optional; JSONL fallback always available)
- Hook utilities: `hooks/scripts/lib/common.sh` (`acquire_lock`, `release_lock`, `ll_feature_enabled`, `ll_config_value`)


## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers event *capture* only — detecting tool calls and writing structured event records. It must NOT own storage routing logic. The `if FEAT-1112 available, write to SQLite; else write to JSONL` conditional currently in scope should be deferred to FEAT-918's Transport abstraction layer. FEAT-1262's shell hook should emit a standard event JSON record and exit; where that event is stored or streamed is FEAT-918's concern. Related: FEAT-918 (Transport Protocol owns fan-out), FEAT-1112 (SQLite store is one Transport sink).

## Session Log
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T17:22:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/83033e3d-e46b-42e3-9b93-f788f6f5fee1.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
