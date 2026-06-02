---
id: BUG-1881
type: BUG
priority: P2
status: open
discovered_date: 2026-06-02
captured_at: "2026-06-02T23:39:38Z"
discovered_by: capture-issue
relates_to: [EPIC-1707, FEAT-1489, ENH-1832]
labels:
  - bug
  - captured
---

# BUG-1881: `post_tool_use.py` Python handler not wired in Claude Code `hooks/hooks.json`

## Summary

`hooks/hooks.json` (the Claude Code adapter) has no PostToolUse entry that invokes `python -m little_loops.hooks post_tool_use`. The Codex adapter (`hooks/adapters/codex/hooks.json`) and the OpenCode adapter (`hooks/adapters/opencode/index.ts`) both wire the handler correctly. As a result, `tool_events` and `file_events` always have 0 rows on the Claude Code host — the primary development host for this project.

## Current Behavior

`hooks/hooks.json` PostToolUse section contains only shell script entries:
- `context-monitor.sh`
- `issue-completion-log.sh`
- `check-duplicate-issue-id-post.sh`
- `issue-auto-commit.sh`

None invoke `python -m little_loops.hooks post_tool_use`. The `post_tool_use.py` Python handler — which writes `tool_events` and `file_events` rows to `history.db` — is never called on Claude Code.

## Expected Behavior

A PostToolUse entry matching `"*"` should call `bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/post-tool-use.sh`, analogous to the Codex shim `hooks/adapters/codex/post-tool-use.sh`. The Python handler runs and writes `tool_events` rows (with `bytes_in`, `bytes_out`, `cache_hit`) and `file_events` rows for Read/Write/Edit tool calls.

## Motivation

FEAT-1489 was marked done after wiring Codex and OpenCode, but Claude Code was missed. EPIC-1707's goal of a queryable context layer is blocked for the primary host — `file_events` data (recently touched files) and `tool_events` data (cache hit rates, bytes per tool call) are completely absent. `ll-ctx-stats` reports no analytic rows and falls back to the static `.ll/ll-context-state.json` as the expected normal case, which defeats the purpose.

## Proposed Solution

1. Create `hooks/adapters/claude-code/post-tool-use.sh` as a fire-and-forget shim mirroring the Codex pattern:
   ```bash
   #!/usr/bin/env bash
   INPUT=$(cat)
   echo "$INPUT" | python -m little_loops.hooks post_tool_use &
   ```
2. Add a PostToolUse hook entry to `hooks/hooks.json` (matcher `"*"`, timeout 5, fire-and-forget) calling the new shim.
3. Confirm `analytics.enabled` is set in `.ll/ll-config.json` (see BUG-1882/ENH-1883) — without it, the handler runs but skips all writes.

## Integration Map

### Files to Modify
- `hooks/hooks.json` — add PostToolUse entry for the claude-code shim
- `hooks/adapters/claude-code/post-tool-use.sh` — new file (fire-and-forget shim)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/post_tool_use.py` — the handler being wired
- `hooks/adapters/codex/post-tool-use.sh` — reference implementation to mirror

### Similar Patterns
- `hooks/adapters/codex/post-tool-use.sh` — identical fire-and-forget pattern
- `hooks/adapters/claude-code/session-start.sh` — blocking shim pattern for reference

### Tests
- Manual: after wiring, verify `tool_events` rows appear in `.ll/history.db` during a session
- `scripts/tests/hooks/test_post_tool_use.py` — existing unit tests for the handler

### Documentation
- N/A - no documentation changes needed

### Configuration
- `hooks/hooks.json` — the Claude Code hook registry

## Implementation Steps

1. Read `hooks/adapters/codex/post-tool-use.sh` to confirm shim pattern
2. Create `hooks/adapters/claude-code/post-tool-use.sh` as fire-and-forget (non-blocking `&`)
3. Add PostToolUse `"*"` matcher entry to `hooks/hooks.json` calling the new shim (timeout 5s)
4. Verify with `python3 -c "import sqlite3; c=sqlite3.connect('.ll/history.db'); print(c.execute('SELECT COUNT(*) FROM tool_events').fetchone())"` after a few tool calls

## Impact

- **Priority**: P2 — renders `tool_events` and `file_events` always empty on Claude Code; blocks EPIC-1707 consumer work from having data to read
- **Effort**: Small — one 4-line shell script, one JSON entry
- **Risk**: Low — fire-and-forget; can't block the session
- **Breaking Change**: No

## Steps to Reproduce

1. Use Claude Code with this project
2. Run `python3 -c "import sqlite3; c=sqlite3.connect('.ll/history.db'); print(c.execute('SELECT COUNT(*) FROM tool_events').fetchone())"`
3. Observe: `(0,)` despite many tool calls in the session

## Root Cause

- **File**: `hooks/hooks.json`
- **Anchor**: `"PostToolUse"` section
- **Cause**: FEAT-1489 wired the Python `post_tool_use` handler for Codex (`hooks/adapters/codex/hooks.json`) and OpenCode (`hooks/adapters/opencode/index.ts`), but the Claude Code `hooks/hooks.json` was not updated as part of that work.

## Labels

`bug`, `hooks`, `history-db`, `captured`

## Status

**Open** | Created: 2026-06-02 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-06-02T23:43:00 - `e58fe996-ddfe-46f4-a827-73b50b9ebde3.jsonl`

- `/ll:capture-issue` - 2026-06-02T23:39:38Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/65f77860-d771-4c40-9ba9-2bc9f9139bfe.jsonl`
