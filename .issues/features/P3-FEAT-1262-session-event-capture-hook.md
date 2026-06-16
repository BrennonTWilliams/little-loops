---
id: FEAT-1262
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-22
discovered_by: issue-size-review
blocked_by:
- FEAT-1112
parent: FEAT-1159
relates_to:
- FEAT-1112
- FEAT-1156
- FEAT-1264
decision_needed: false
confidence_score: 95
outcome_confidence: 80
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 20
---

# FEAT-1262: Session Event Capture Hook (`session-capture.sh`)

## Summary

Implement `hooks/scripts/session-capture.sh` as a PostToolUse hook that continuously appends structured event records to `.ll/ll-session-events.jsonl` throughout the session, providing the data source for event-log-driven handoff snapshots.

## Parent Issue

Decomposed from FEAT-1159: Continuous Session Event Capture with PreCompact Guarantee and SessionStart Injection

## Current Behavior

The current handoff approach (`/ll:handoff`, `precompact-handoff.sh`) reconstructs session state at handoff time — from git diff, `ll-issues list`, and loop JSON. This is lossy: it cannot mechanically determine which tasks are pending vs completed, which files were net-modified, or what errors remain unresolved.

## Expected Behavior

A `session-capture.sh` PostToolUse hook fires on each tool invocation and appends one structured JSON event record to `.ll/ll-session-events.jsonl`. FEAT-1264's PreCompact snapshot builder reads this log to produce an accurate, structured handoff context for resuming sessions.

## Use Case

**Who**: Developer using ll-auto, ll-parallel, or an interactive session nearing context limits

**Context**: During a long automated session, context approaches the window limit and the PreCompact hook triggers

**Goal**: The handoff snapshot should accurately reflect which tasks completed, which files were net-modified, and which errors remain unresolved — without inferring state solely from git diffs

**Outcome**: FEAT-1264 reads `.ll/ll-session-events.jsonl` and produces a structured snapshot that a resuming session can act on directly

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
- Storage routing (JSONL vs SQLite vs other) is NOT this issue's concern — emit canonical event JSON to `.ll/ll-session-events.jsonl`; routing/fan-out is FEAT-918's Transport responsibility (FEAT-1112 subscribes via Transport sink)

## Proposed Solution

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

### Event Semantics (canonical — consumers MUST cite this section)

Producers and consumers of `.ll/ll-session-events.jsonl` share these semantic rules. Downstream consumers (FEAT-1264, FEAT-1112) reference these definitions instead of redefining them.

**Error-resolution heuristic**: an event with `type=error` for `subject=X` is considered "unresolved" if the most recent event for `subject=X` is itself a `type=error`. A subsequent `type=file` Write/Edit event touching the same subject is treated as likely-resolved. This is a heuristic — it can produce false positives (e.g., an unrelated edit) and false negatives (e.g., the bug persists). Consumers may surface confidence levels but should not invent stricter rules without coordinating an update here.

**Subject normalization**: file subjects are stored relative to the project root, no leading `./`; git subjects are the raw command args (truncated at 200 chars). Consumers compare subjects as raw strings — no canonicalization.

**Recency**: latest-event-wins for any state derived from the log (task status, error resolution, net file ops). Earlier events are evidence of motion, not truth.

### Registration: `hooks/hooks.json`

Add `session-capture.sh` to the PostToolUse array. Multiple PostToolUse hooks are supported.

### Tests: `TestSessionCapture`

Add to `scripts/tests/test_hooks_integration.py`, modeled after `TestPrecompactState` (line 2037):
- Hook produces a valid JSONL record for each captured event type
- Hook exits 0 even when jq is missing or stdin is malformed
- Concurrent invocations don't corrupt the JSONL file (lock acquisition verified)
- Unknown tool names produce no record (or a best-effort `type: unknown` record — decide during implementation)

## Integration Map

### Files to Modify
- `hooks/hooks.json` — add PostToolUse entry for `session-capture.sh`
- `scripts/tests/test_hooks_integration.py` — add `TestSessionCapture` class
- `config-schema.json` — add `session_capture` top-level property block with `enabled: boolean` (default false); required because `additionalProperties: false` at the schema root silently rejects `session_capture.enabled` in `.ll/ll-config.json` without this declaration [Wiring pass added by `/ll:wire-issue`]

### New Files
- `hooks/scripts/session-capture.sh`

### Dependent Files (Callers/Importers)
- FEAT-1264 (`precompact-handoff.sh`) — consumes `.ll/ll-session-events.jsonl`
- FEAT-1112 (SQLite Transport sink) — optional downstream consumer

### Similar Patterns
- `hooks/scripts/precompact-state.sh` — follow same structure (stdin JSON, jq extraction, lock-safe JSONL append)
- `hooks/scripts/lib/common.sh` — provides `acquire_lock`, `release_lock`, `ll_feature_enabled`

### Tests
- `scripts/tests/test_hooks_integration.py` — `TestSessionCapture` class (modeled after `TestPrecompactState` at line 2037)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — add `test_session_capture_in_schema` to `class TestConfigSchema`, following the `test_analytics_in_schema` pattern (line 253); guards that `session_capture` is declared at the schema root so `additionalProperties: false` doesn't silently reject user config

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — add `session-capture` row to `## The Lifecycle at a Glance` table; update "Five hooks run after each tool call" count in `## PostToolUse`; add `session_capture.enabled` row to `## Configuration Reference` table
- `docs/reference/CONFIGURATION.md` — add `### session_capture` section following the `### analytics` pattern (documents `session_capture.enabled` boolean flag)
- `docs/ARCHITECTURE.md` — add `session-capture.sh` to PostToolUse hook flow section (parent EPIC FEAT-1159 line 117 explicitly calls this out as required)

### Configuration
- `hooks/hooks.json` — PostToolUse registration
- `config-schema.json` — declare `session_capture` property (same shape as `analytics` / `context_monitor` blocks: `type: object`, `additionalProperties: false`, `enabled: boolean, default: false`) [Wiring pass added by `/ll:wire-issue`]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**hooks.json entry format** (confirmed from existing entries): each PostToolUse hook is a separate top-level object in the array — not nested under an existing matcher. The new entry must be:
```json
{
  "matcher": "*",
  "hooks": [
    {
      "type": "command",
      "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-capture.sh",
      "timeout": 5,
      "statusMessage": "Capturing session event..."
    }
  ]
}
```

**Existing PostToolUse context files** (not modified, but relevant for FEAT-1116 porting note):
- `hooks/adapters/claude-code/post-tool-use.sh` — current catch-all PostToolUse adapter (dispatches to Python)
- `scripts/little_loops/hooks/post_tool_use.py` — Python PostToolUse handler (future porting target per Scope Boundary note)

**TestSessionCapture fixture path**: the `hook_script` fixture must return `Path(__file__).parent.parent.parent / "hooks/scripts/session-capture.sh"` (NOT the adapter path — `TestPrecompactState` tests the adapter at `hooks/adapters/claude-code/precompact.sh`, but `TestSessionCapture` tests the script directly since there is no PostToolUse adapter wrapping it).

**Additional test reference classes** in `test_hooks_integration.py`:
- `TestIssueCompletionLog` at line 1363 — also a direct-script test (no adapter) and a closer model than `TestPrecompactState` for JSONL-appending PostToolUse scripts
- `TestContextMonitor` at line 14 — concurrent access test model

## Implementation Steps

1. Create `hooks/scripts/session-capture.sh` following `precompact-state.sh` structure (stdin JSON, jq, common.sh)
2. Implement tool-name → event-type mapping (`file`, `task`, `git`, `error`) via case statement
3. Build event JSON record with `jq -n` and append using `acquire_lock` / `release_lock`
4. Register as PostToolUse entry in `hooks/hooks.json`
5. Add `TestSessionCapture` class to `scripts/tests/test_hooks_integration.py`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `config-schema.json` — add `session_capture` top-level object property with `enabled: boolean` (default false), matching the `analytics` and `context_monitor` block shapes; required before users can set `session_capture.enabled` in `.ll/ll-config.json` without silent rejection
7. Add `test_session_capture_in_schema` to `class TestConfigSchema` in `scripts/tests/test_config_schema.py` — pattern from `test_analytics_in_schema` (line 253): assert `session_capture` in schema properties, `type == "object"`, `additionalProperties is False`, `enabled` property with `type == "boolean"` and `default is False`
8. Update `docs/guides/BUILTIN_HOOKS_GUIDE.md` — add `session-capture` row to the lifecycle table, fix the "Five hooks run after each tool call" count, add `session_capture.enabled` row to the Configuration Reference table
9. Update `docs/reference/CONFIGURATION.md` — add `### session_capture` section following the `### analytics` pattern (document `enabled` boolean key)
10. Update `docs/ARCHITECTURE.md` — add `session-capture.sh` to the PostToolUse hook flow section (parent EPIC FEAT-1159 calls this out at line 117)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**JSONL append differs from `precompact-state.sh`**: `atomic_write_json` replaces a whole JSON file — do NOT use it for JSONL append. The correct pattern (confirmed from `context-monitor.sh` + `lib/common.sh`):
```bash
EVENTS_FILE=".ll/ll-session-events.jsonl"
EVENTS_LOCK="${EVENTS_FILE}.lock"
mkdir -p "$(dirname "$EVENTS_FILE")" 2>/dev/null || true
if acquire_lock "$EVENTS_LOCK" 3; then
    echo "$EVENT_JSON" >> "$EVENTS_FILE" 2>/dev/null || true
    release_lock "$EVENTS_LOCK"
else
    echo "$EVENT_JSON" >> "$EVENTS_FILE" 2>/dev/null || true  # best-effort on timeout
fi
```

**jq extraction — use single batched `@tsv` pass** (from `context-monitor.sh`; avoids re-parsing large stdin 3× per invocation):
```bash
INPUT=$(cat)
if ! command -v jq &>/dev/null; then exit 0; fi
IFS=$'\t' read -r TOOL_NAME BASH_CMD BASH_EXIT <<< "$(echo "$INPUT" | jq -r '[
    (.tool_name // ""),
    (.tool_input.command // ""),
    (.tool_response.exit_code // "" | tostring)
] | @tsv' 2>/dev/null || echo -e "\t\t")"
```

**`tool_input` field paths per event type**:
- `file` events: `subject` = `.tool_input.file_path // .tool_input.path // ""`
- `task` events: `subject` = `.tool_input.content // .tool_input.id // ""`; `status` = `.tool_input.status // ""`
- `git` events: `subject` = `.tool_input.command` (strip leading `git ` prefix, truncate at 200 chars)
- `error` events: `subject` = `.tool_input.command` (truncated at 200 chars); `status` = `.tool_response.exit_code | tostring`

**Feature flag**: follow `context-monitor.sh` pattern — call `ll_resolve_config` then guard with `ll_feature_enabled "session_capture.enabled"` (key not yet in config-schema.json; add alongside implementation).

**Exit code**: PostToolUse hooks exit `0` (confirmed from `issue-completion-log.sh`). Only PreCompact uses exit `2`. All success and error paths in `session-capture.sh` must exit `0`.

## Impact

- **Priority**: P3 — Enables structured event-log-driven handoffs; current text-based handoff still works without it
- **Effort**: Small — Shell script + JSON appender + hook registration + tests; pattern follows `precompact-state.sh` exactly
- **Risk**: Low — Failure-safe (exit 0 on all error paths); capture failures cannot block tool execution
- **Breaking Change**: No

## Scope Boundary

This issue owns only the capture side: writing `.ll/ll-session-events.jsonl`. It does NOT:
- Modify `precompact-handoff.sh` (FEAT-1264 owns that integration)
- Implement the SessionStart injector (FEAT-1263)
- Own storage routing logic — the shell hook emits a standard event JSON record and exits; where that event is stored or streamed is FEAT-918's Transport concern (FEAT-1112 is one Transport sink)

**FEAT-1116 migration note**: `session-capture.sh` is a PostToolUse shell script in the layer FEAT-1116 is migrating to Python core handlers. Implement as specified here for unblocked delivery; once FEAT-1116's PostToolUse migration scaffolding lands, port the event-capture logic to a Python intent handler (e.g., `scripts/little_loops/hooks/post_tool_use_capture.py`) and replace `session-capture.sh` with a thin Claude Code adapter. Keep the shell script logic minimal — event parsing, JSONL append, and failure-safe exit — so the Python port is straightforward.

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

## Labels

`hook`, `session`, `automation`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-06-16T23:30:00Z - `6bc84bfa-fc14-45b4-b36b-142a14cd7862.jsonl`
- `/ll:wire-issue` - 2026-06-16T23:04:16 - `db7f74a5-4414-4c6c-b58d-b13028a4c420.jsonl`
- `/ll:refine-issue` - 2026-06-16T22:56:38 - `a0890b90-9ac3-4ede-9e12-de710c5778d0.jsonl`
- `/ll:format-issue` - 2026-06-16T22:50:22 - `57330cc2-76ee-48f3-90e7-303e4ad55708.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-11T21:32:14 - `521f9c4d-aa09-4ad1-88fe-93826dacaa4a.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:01 - `4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T17:22:36 - `83033e3d-e46b-42e3-9b93-f788f6f5fee1.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`

## Blocks

- FEAT-1264
