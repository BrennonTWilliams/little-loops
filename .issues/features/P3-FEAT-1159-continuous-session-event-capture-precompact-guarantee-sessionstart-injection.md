---
id: FEAT-1159
type: FEAT
priority: P3
status: deferred
discovered_date: 2026-04-18
discovered_by: capture-issue
blocked_by:
- FEAT-1112
- FEAT-1116
- FEAT-1156
- FEAT-1157
- FEAT-1158
relates_to:
- FEAT-1112
- FEAT-1113
---

# FEAT-1159: Continuous Session Event Capture with PreCompact Guarantee and SessionStart Injection

## Summary

Extend the context-monitor system beyond its current threshold-reminder model to include: (1) continuous structured capture of tool events (file ops, git, tasks, decisions, errors) throughout the session via PostToolUse into a structured store; (2) a PreCompact hook that automatically writes a handoff snapshot if `/ll:handoff` has not already run; (3) a SessionStart hook that authoritatively injects the snapshot back into context on resume, without requiring user action.

Inspired by analysis of the context-mode plugin (github.com/mksglu/context-mode), which demonstrates that continuous event capture + deterministic PreCompact trigger + authoritative SessionStart injection is architecturally superior to point-in-time model summarization.

## Current Behavior

- `context-monitor.sh` (PostToolUse) estimates token usage and emits a reminder message at threshold, asking Claude to run `/ll:handoff`
- `/ll:handoff` is a model-invoked skill that produces a natural-language summary of what Claude remembers doing
- The resulting `ll-continue-prompt.md` file is read manually via `/ll:resume` on the next session
- No structured event capture occurs during the session — state reconstruction depends entirely on the model's in-context memory at the moment of handoff
- In headless mode (ll-loop, ll-auto), handoff is semi-automatic via FSM signal detection, but still requires Claude to invoke `/ll:handoff` and emit `CONTEXT_HANDOFF: Ready for fresh session`

## Expected Behavior

### 1. Continuous event capture (PostToolUse)
A PostToolUse hook records structured events throughout the session into `.ll/ll-session-events.json` (or the SQLite store from FEAT-1112 if available). Captured event types:
- **File ops**: Read, Write, Edit, Glob, Grep — filename + operation type
- **Task state**: TodoWrite, TaskCreate, TaskUpdate — with subject + status JSON
- **Git ops**: any git subcommand invoked via Bash
- **Errors**: Bash failures (non-zero exit) and detected error patterns
- **Decisions**: User preference expressions from conversation context
- **Plan mode**: EnterPlanMode / ExitPlanMode / plan approval events

### 2. PreCompact guarantee
A PreCompact hook fires when Claude Code is about to compact. It checks if `ll-continue-prompt.md` was already written since `threshold_crossed_at` (idempotency). If not, it reads the session event log and builds a priority-tiered snapshot (≤2KB) directly — no model involvement, no reminder, no risk of being ignored.

### 3. Authoritative SessionStart injection
On session resume (SessionStart with `source = "compact"` or explicit `/ll:resume`), the snapshot is injected as `additionalContext` at the system-prompt level — not as a file Claude is asked to read, but as a structured brief with a `<continue_from>` directive. This suppresses the most common post-compaction failure: Claude asking the user to re-explain what they were doing.

## Motivation

The current reminder-based approach has three failure modes context-mode's architecture avoids:

1. **The model may not act on the reminder** — if Claude is mid-task, degraded, or the reminder fires at an inopportune moment (BUG-982), handoff is silently missed
2. **Point-in-time summarization is lossy** — the model reconstructs state from its context window at threshold-crossing time; it cannot mechanically compute which tasks are pending vs completed, which files were net-modified, or what errors remain unresolved
3. **SessionStart is passive** — `ll-continue-prompt.md` is a file Claude can read; it is not an authoritative directive that tells Claude exactly what state it was in and what to continue

The event-capture approach captures data continuously as it happens, makes PreCompact deterministic rather than probabilistic, and makes context restoration authoritative rather than advisory.

## Use Case

A user is running an interactive Claude Code session working through a multi-file refactor. Their context hits 85% and they don't notice the reminder (or Claude is mid-tool-call when it fires). Context compacts. Without this feature: Claude asks "what were we working on?" With this feature: Claude receives a structured brief — last 10 files touched, 2 pending tasks, 1 unresolved error, last user request — and continues without interruption.

## Proposed Solution

Three-component architecture following context-mode's model, adapted for the little-loops shell/Python stack:

**Component 1: Event capture hook** (`hooks/scripts/session-capture.sh`)
- Fires PostToolUse, appends a JSON event record to `.ll/ll-session-events.jsonl`
- Minimal overhead: one jq extraction + one append per tool call
- Event schema: `{"ts": "ISO8601", "type": "file|task|git|error|decision|plan", "op": "...", "subject": "...", "status": "..."}`
- Uses `acquire_lock` from `lib/common.sh` for safe concurrent writes

**Component 2: PreCompact snapshot builder** (`hooks/scripts/precompact-handoff.sh`)
- Reads `.ll/ll-session-events.jsonl`, groups by type, builds tiered markdown snapshot
- Idempotency: skips if `ll-continue-prompt.md` mtime > `threshold_crossed_at` epoch
- Priority tiers dropped LIFO if total exceeds 2KB
- Writes atomically to `.ll/ll-continue-prompt.md`

**Component 3: SessionStart injector** (`hooks/scripts/session-start-inject.sh`)
- Fires on SessionStart, reads `ll-continue-prompt.md` if it exists and is fresh
- Outputs `additionalContext` JSON with a `<continue_from>` directive and pending task list
- Marks the prompt as consumed to prevent re-injection in the same session

## Acceptance Criteria

- Session capture hook writes events for file ops, task transitions, git ops, and errors without noticeable latency impact
- PreCompact hook produces `ll-continue-prompt.md` ≤2KB even when event log is large (priority-tier dropping verified with synthetic large inputs)
- PreCompact hook is idempotent: skips write if prompt already fresh from manual `/ll:handoff`
- SessionStart hook injects snapshot as `additionalContext` on compact resume without user action
- Injected context includes pending tasks, last-modified files, unresolved errors, and a `<continue_from>` directive
- Existing `/ll:handoff` + `/ll:resume` manual flow continues to work unchanged
- Integration tests cover all three components

## Integration Map

### Files to Modify
- `hooks/hooks.json` — register `session-capture.sh` (PostToolUse), `precompact-handoff.sh` (PreCompact), `session-start-inject.sh` (SessionStart)
- `hooks/scripts/context-monitor.sh` — no functional change; idempotency in precompact hook reads `threshold_crossed_at` written here

### New Files
- `hooks/scripts/session-capture.sh` — PostToolUse event capture
- `hooks/scripts/precompact-handoff.sh` — PreCompact snapshot builder (supersedes the deferred FEAT-1113 scope)
- `hooks/scripts/session-start-inject.sh` — SessionStart injector

### Dependent Files (Callers/Importers)

See "Consumers of ll-continue-prompt.md" below.

### Similar Patterns

- `hooks/scripts/context-monitor.sh` — existing PostToolUse hook for threshold detection; session-capture.sh follows the same event-filter + append pattern

### Reusable Utilities (hooks/scripts/lib/common.sh)
- `acquire_lock` / `release_lock` / `atomic_write_json` — all state writes must use these
- `ll_config_value` / `ll_feature_enabled` — feature flag guards

### Consumers of ll-continue-prompt.md (must remain compatible)
- `commands/resume.md` — reads `ll-continue-prompt.md`; structured schema validated here
- `scripts/little_loops/subprocess_utils.py:read_continuation_prompt` — reads file for ll-auto/ll-parallel
- `hooks/scripts/context-monitor.sh` — reads mtime for idempotency check

### Tests
- `scripts/tests/test_hooks_integration.py` — add `TestSessionCapture`, `TestPrecompactHandoff`, `TestSessionStartInject` classes
- `scripts/tests/test_subprocess_utils.py:TestReadContinuationPrompt` — verify schema compatibility with new snapshot format

### Documentation
- `docs/guides/SESSION_HANDOFF.md` — update to describe automatic capture + PreCompact guarantee
- `docs/ARCHITECTURE.md` — add session capture to PreCompact and SessionStart sections

### Configuration
- `config-schema.json` — add top-level `session_capture` section if opt-in feature flag needed
- `templates/*.json` — add `"session_capture": {"enabled": true}` if opt-in

## Implementation Steps

1. **Design and validate event schema** — define the JSONL event record shape; verify it covers all state that `/ll:handoff` currently produces via model summarization
2. **Implement `session-capture.sh`** — PostToolUse hook with minimal overhead; test that high-frequency tool calls don't introduce latency
3. **Implement `precompact-handoff.sh`** — reads event log, builds tiered snapshot, idempotency guard; write size-pressure tests before implementing trim logic
4. **Implement `session-start-inject.sh`** — SessionStart hook outputting `additionalContext` JSON; test with synthetic snapshot files
5. **Register all three hooks in `hooks/hooks.json`**
6. **Write integration tests** for all three components including idempotency, size-cap, and schema compatibility
7. **Update docs and config schema**

## Impact

- **Priority**: P3 — significant UX improvement for interactive sessions; headless mode already handles handoff automatically
- **Effort**: Large — three new hook scripts, new event store format, SessionStart output protocol, full test coverage
- **Risk**: Medium — PostToolUse fires on every tool call; `session-capture.sh` must be fast and failure-safe (errors must not block tool execution)
- **Breaking Change**: No — all existing handoff/resume flows remain unchanged

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Three conflicts resolved by the blocking dependencies added above:

1. **precompact-handoff.sh ownership** (conflict with FEAT-1156): Do NOT implement `hooks/scripts/precompact-handoff.sh` as a new file in this issue. FEAT-1156 owns and delivers that script. Remove it from this issue's "New Files" list; FEAT-1159 should consume the script from FEAT-1156's deliverable, not re-implement it. FEAT-1159's Component 2 scope should be scoped to the *integration wiring* of the existing script (e.g., reading from the event log produced by Component 1).

2. **TestPrecompactHandoff ownership** (conflict with FEAT-1157): Do NOT create a `TestPrecompactHandoff` class in `test_hooks_integration.py` as part of this issue. FEAT-1157 owns that class. FEAT-1159's test scope is `TestSessionCapture` and `TestSessionStartInject` only.

3. **Docs/config overlap** (conflict with FEAT-1158): `docs/guides/SESSION_HANDOFF.md`, `docs/ARCHITECTURE.md`, and any `config-schema.json` additions for the PreCompact hook belong to FEAT-1158's docs phase. FEAT-1159's documentation step should build on FEAT-1158's existing edits and add only the session-capture–specific sections, not re-edit the same PreCompact trigger documentation.

4. **Hook architecture** (conflict with FEAT-1116): All three new hook scripts (`session-capture.sh`, `precompact-handoff.sh`, `session-start-inject.sh`) are proposed as shell scripts in `hooks/scripts/` using `lib/common.sh`. FEAT-1116 is migrating this layer to Python core handlers with per-host adapters. Implement the shell-script MVP as described for unblocked delivery, but plan a follow-up issue to migrate to the FEAT-1116 adapter pattern once its PreCompact and SessionStart scaffolding is available.

## Labels

`feature`, `hooks`, `session-management`, `captured`

## Session Log
- `/ll:format-issue` - 2026-06-16T23:25:00 - `0f3c4d3d-bfb8-4be3-873f-42ff99dd9160.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-22T20:04:15 - `82d256a6-9a99-40f5-8866-377a208de262.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-19T01:16:14 - `9c7ed14d-9621-459d-9f93-384968b2e6f6.jsonl`
- `/ll:capture-issue` - 2026-04-18T00:00:00Z - `ffa52965-8df7-4476-a2af-96e098002a6a.jsonl`

---

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-22
- **Reason**: Issue too large; three components decomposed into focused child issues

### Decomposed Into

- FEAT-1262: Session Event Capture Hook (`session-capture.sh`) — Component 1 (PostToolUse event log)
- FEAT-1263: SessionStart Context Injector (`session-start-inject.sh`) — Component 3 (authoritative injection)
- FEAT-1264: PreCompact Handoff — Event Log Integration — Component 2 wiring (enhances FEAT-1156 to read from FEAT-1262's event log)

FEAT-1156/1157/1158 (children of FEAT-1113) remain the active delivery for the basic precompact snapshot. FEAT-1262/1263/1264 extend that foundation with continuous capture and authoritative injection.

**Deferred** | Created: 2026-04-18 | Priority: P3
