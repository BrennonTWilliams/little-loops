---
id: BUG-1881
type: BUG
priority: P2
status: open
discovered_date: 2026-06-02
captured_at: '2026-06-02T23:39:38Z'
discovered_by: capture-issue
relates_to:
- EPIC-1707
- FEAT-1489
- ENH-1832
decision_needed: false
labels:
- bug
- captured
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
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

1. Create `hooks/adapters/claude-code/post-tool-use.sh` as a **blocking** shim mirroring `hooks/adapters/codex/post-tool-use.sh`. Do NOT use `&` — the Codex shim's own comment says backgrounding was intentionally avoided (single-row INSERT keeps p95 well under the 5s timeout). Do NOT set `LL_HOOK_HOST` — the Python dispatcher (`scripts/little_loops/hooks/__init__.py:main_hooks`) defaults to `"claude-code"` via `os.environ.get("LL_HOOK_HOST", "claude-code")`, so existing claude-code shims (`session-start.sh`, `precompact.sh`, `session-end.sh`) all omit it.

   Exact file content:
   ```bash
   #!/usr/bin/env bash
   #
   # Claude Code adapter for the PostToolUse hook intent (BUG-1881).
   #
   # Mirrors hooks/adapters/codex/post-tool-use.sh. LL_HOOK_HOST is not set
   # because the Python dispatcher defaults to "claude-code".
   # Backgrounding (&/disown) is intentionally avoided — a single-row INSERT
   # keeps p95 well below the 5 s timeout when analytics is enabled.
   #
   INPUT=$(cat)
   echo "$INPUT" | python -m little_loops.hooks post_tool_use
   exit $?
   ```

2. Add a PostToolUse hook entry to `hooks/hooks.json` `"PostToolUse"` array (after line 54, as the first entry before tool-specific matchers) with matcher `"*"`, timeout 5:
   ```json
   {
     "matcher": "*",
     "hooks": [
       {
         "type": "command",
         "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/post-tool-use.sh",
         "timeout": 5,
         "statusMessage": "Recording tool use..."
       }
     ]
   }
   ```

3. Confirm `analytics.enabled` is set in `.ll/ll-config.json` (see BUG-1882/ENH-1883) — without it, the handler runs but skips all writes (gated in `post_tool_use.py:handle()` via `feature_enabled(config, "analytics.enabled")`).

## Integration Map

### Files to Modify
- `hooks/hooks.json` — add PostToolUse entry for the claude-code shim
- `hooks/adapters/claude-code/post-tool-use.sh` — new file (fire-and-forget shim)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/post_tool_use.py` — the handler being wired; `handle()` gates both `tool_events` and `file_events` INSERTs on `feature_enabled(config, "analytics.enabled")`
- `scripts/little_loops/hooks/__init__.py:main_hooks()` — dispatcher; reads `LL_HOOK_HOST` env (default `"claude-code"`) and routes `post_tool_use` intent to the handler
- `hooks/adapters/codex/post-tool-use.sh` — reference implementation to mirror (blocking, sets `LL_HOOK_HOST=codex`)

### Similar Patterns
- `hooks/adapters/codex/post-tool-use.sh` — reference blocking shim (comment says `&` intentionally avoided)
- `hooks/adapters/claude-code/session-start.sh` — claude-code shim pattern: no `LL_HOOK_HOST`, blocking `INPUT=$(cat); echo "$INPUT" | python -m little_loops.hooks <intent>; exit $?`
- `hooks/adapters/claude-code/precompact.sh` — same 3-line blocking pattern

### Tests
- Manual: after wiring, verify `tool_events` rows appear in `.ll/history.db` during a session
- `scripts/tests/test_hook_post_tool_use.py` — existing unit tests for the handler (path corrected from stale reference)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_claude_code_adapter.py` — new test file needed; no parallel to `TestCodexAdapterIntegration` (`test_codex_adapter.py`) exists for the claude-code adapter. Follow `TestCodexAdapterIntegration` pattern for these four tests:
  - `test_adapter_files_exist` — assert `hooks/adapters/claude-code/post-tool-use.sh` exists
  - `test_adapter_scripts_are_executable` — assert the new shim is `chmod +x`
  - `test_hooks_json_has_post_tool_use` — read real `hooks/hooks.json` and assert a `PostToolUse` `"*"` matcher entry invokes `post-tool-use.sh`
  - `test_post_tool_use_default_host_claude_code` — e2e subprocess test via sentinel file; assert `LL_HOOK_HOST` defaults to `"claude-code"` (unlike Codex, which explicitly sets it)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/claude-code/write-a-hook.md` — "The three concrete adapters" section lists adapter files explicitly (`precompact.sh, session-end.sh, session-start.sh`); add `post-tool-use.sh`
- `docs/reference/API.md` — `main_hooks` "Adapter integration" section lists Claude Code shims; add `post-tool-use.sh` to the enumeration
- `docs/reference/HOST_COMPATIBILITY.md` — `[^hot]` footnote describes only the Codex blocking shim and OpenCode fire-and-forget as the two wired implementations; update to note the Claude Code blocking shim as a third wired host
- `docs/development/TROUBLESHOOTING.md` — "Verify hook script is executable" chmod block lists existing adapter shims; add `chmod +x hooks/adapters/claude-code/post-tool-use.sh`

### Configuration
- `hooks/hooks.json` — the Claude Code hook registry

## Implementation Steps

1. Read `hooks/adapters/codex/post-tool-use.sh` to confirm the blocking shim pattern (no `&`, sets `LL_HOOK_HOST=codex`)
2. Create `hooks/adapters/claude-code/post-tool-use.sh` as a **blocking** shim following claude-code convention (no `LL_HOOK_HOST`, no `&`); use content from Proposed Solution step 1 above
3. Add the PostToolUse `"*"` matcher entry to `hooks/hooks.json` as the first item in the `"PostToolUse"` array (line 54), before the existing tool-specific matcher entries; use the JSON block from Proposed Solution step 2 above
4. Ensure `analytics.enabled: true` is in `.ll/ll-config.json` (ENH-1883 covers this — without it, the handler exits 0 without writing to SQLite)
5. Verify with `python3 -c "import sqlite3; c=sqlite3.connect('.ll/history.db'); print(c.execute('SELECT COUNT(*) FROM tool_events').fetchone())"` after a few tool calls in a new session; expected: non-zero row count

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/claude-code/write-a-hook.md` — add `post-tool-use.sh` to the "three concrete adapters" file list
7. Update `docs/reference/API.md` — add `post-tool-use.sh` to the claude-code adapter enumeration in the `main_hooks` section
8. Update `docs/reference/HOST_COMPATIBILITY.md` — update the `[^hot]` footnote to name Claude Code as the third wired host (blocking shim pattern)
9. Update `docs/development/TROUBLESHOOTING.md` — add `chmod +x hooks/adapters/claude-code/post-tool-use.sh` to the "Verify hook script is executable" block
10. Create `scripts/tests/test_claude_code_adapter.py` with `TestClaudeCodeAdapterIntegration` — mirror `TestCodexAdapterIntegration` pattern (file-exists, executable, `hooks/hooks.json` PostToolUse entry, e2e default-host sentinel test)

## Acceptance Criteria

- `hooks/adapters/claude-code/post-tool-use.sh` exists, is executable, and contains no `&` (blocking shim)
- `hooks/hooks.json` `"PostToolUse"` array contains an entry with `"matcher": "*"` invoking `hooks/adapters/claude-code/post-tool-use.sh`
- After a session with `analytics.enabled: true`, `SELECT COUNT(*) FROM tool_events` returns > 0
- Existing PostToolUse hook entries (`context-monitor.sh`, `issue-completion-log.sh`, etc.) still fire (new entry is additive, not replacing)
- `scripts/tests/test_hook_post_tool_use.py` passes

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
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3d256da0-1528-4797-a690-c3fc75d7e7f8.jsonl`
- `/ll:wire-issue` - 2026-06-02T23:56:34 - `fe86b63e-5425-48d6-8618-c201523662ec.jsonl`
- `/ll:refine-issue` - 2026-06-02T23:50:46 - `2a1abd26-d301-4d91-8b99-8cf96eaffa61.jsonl`
- `/ll:format-issue` - 2026-06-02T23:43:00 - `e58fe996-ddfe-46f4-a827-73b50b9ebde3.jsonl`

- `/ll:capture-issue` - 2026-06-02T23:39:38Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/65f77860-d771-4c40-9ba9-2bc9f9139bfe.jsonl`
