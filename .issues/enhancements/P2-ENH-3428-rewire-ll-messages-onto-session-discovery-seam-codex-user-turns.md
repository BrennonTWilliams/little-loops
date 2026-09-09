---
id: ENH-3428
type: ENH
title: Rewire ll-messages onto the session-discovery seam (Codex user-turn support)
priority: P2
status: open
discovered_by: issue-size-review
discovered_date: '2026-09-09'
captured_at: '2026-09-09T21:54:30Z'
labels:
- multi-host
- observability
parent: ENH-3419
blocked_by:
- ENH-3427
blocks: []
relates_to:
- ENH-3420
- FEAT-3417
- ENH-3429
- ENH-3430
---

# ENH-3428: Rewire ll-messages onto the session-discovery seam (Codex user-turn support)

## Summary

Decomposed from ENH-3419 (score 8/11, Very Large). Rewires `user_messages.py`'s
`extract_user_messages`, `extract_commands`, and `extract_conversation_turns` — plus their sole
caller `cli/messages.py`'s `main_messages` — off the `project_folder: Path` glob and onto
`detect_sessions`/`iter_events`, and adds the Codex user-turn extraction. Depends on ENH-3427 for
`_resolve_host` and the `--host` flag already registered on `ll-messages`.

## Parent Issue

Decomposed from ENH-3419: Adopt the session-discovery seam in ll-logs, ll-messages, and
ll-ctx-stats (Codex observability).

## Current Behavior

`cli/messages.py`'s `main_messages` calls `get_project_folder(cwd)` (line 173) then
`extract_user_messages(project_folder, ...)` (192) and `extract_commands(project_folder, ...)`
(201-207). `user_messages.py`'s `extract_user_messages` (639) and `extract_commands` (722) take a
bare `project_folder: Path`, glob `*.jsonl`, and parse via `_parse_user_record`.
`extract_user_messages` defaults to `include_agent_sessions=True`. A third globbing function,
`extract_conversation_turns` (1028, glob at 1096), is called from `main_messages` for
`--sft-format` (`cli/messages.py:250`) with the same `project_folder`; only its `--reader db` mode
bypasses the glob.

## Proposed Solution

1. **Signature change**: `extract_user_messages`/`extract_commands`/`extract_conversation_turns`
   gain a `handles: list[SessionHandle]` entry point and iterate `iter_events(handle)`. The Claude
   branch keeps `_parse_user_record` byte-for-byte on `event.payload`.
2. **Codex user-turn mapping** (corrected against the 0.152.1 fixtures): neither committed fixture
   contains an `event_msg` of type `user_message`; the user's prompt lives in `response_item`
   events with `payload.type == "message"` and `payload.role == "user"`, text under
   `payload.content[].text` (`type: "input_text"`). Filter out two injected user-role messages:
   the host-injected `<environment_context>...</environment_context>` block and any
   `role == "developer"` message; also filter `<turn_aborted>` (match on the stripped text's
   opening tag, kept as a single named constant list).
3. **0.130.0 dedup path** (the common path on the real corpus — 399/400 of the newest local
   rollouts are 0.130.0): both a `response_item` role-`user` message and an `event_msg`
   `user_message` carry the same text per turn; the 0.130.0 payload's text is under **`message`**
   (not `text`). Dedup key = `payload.message` vs the joined `input_text` of the preceding
   `response_item`. Unknown `event_msg` types pass through untouched.
4. **Codex → `UserMessage` field mapping**: `content` = joined `input_text` texts; `timestamp` =
   envelope `timestamp` (same ISO-Z parse as Claude, file mtime fallback); `session_id` =
   `handle.session_id`; `uuid` = `payload.id` (`msg_…`); `cwd` = the `session_meta` payload's `cwd`
   if seen else `str(handle.cwd)`; `git_branch = None`; `is_sidechain = False`.
5. **`extract_commands` stays Claude-Code-only**: it parses Claude `tool_use` blocks for `Bash`
   (722-745); Codex handles yield no `CommandRecord`s. The Codex equivalent
   (`response_item.payload.type == "custom_tool_call"`, `name: "exec"`) is out of scope — a
   content-level mapping deferred to a follow-up.
6. **Two more Claude branches must move off the glob**: `extract_user_messages` with
   `include_response_context=True` (935) and `extract_conversation_turns`'s JSONL branch (976) —
   both take the file only for the mtime fallback; under handles,
   `all_records = [e.payload for e in iter_events(h)]`, pass `h.path`.
7. **`extract_conversation_turns`'s JSONL branch** takes `handles` and iterates `iter_events`, with
   the same `include_agent_sessions` → `include_agents` mapping and the mtime-based `since`
   pre-filter re-expressed on `handle.updated_at`; the `--reader db` branch is untouched;
   `_extract_turn_pairs` stays Claude-shaped (Codex handles yield no windows here).
8. **No-sessions stderr**: change the wording to `"No sessions found for: <cwd>"` (no test asserts
   the old string); exit code stays 1.

## Files to Modify

- `scripts/little_loops/user_messages.py` (`extract_user_messages` 639, `extract_commands` 722,
  `extract_conversation_turns` 1028, `_extract_messages_with_context`, `_extract_turn_pairs`)
- `scripts/little_loops/cli/messages.py` (`main_messages` 173, 192, 201-207, 250)
- `docs/reference/API.md:3424-3629,5461-5462` — signature/docstring updates for
  `extract_user_messages`, `get_project_folder`, `get_sessions_folder`
- `docs/reference/CLI.md` — `### ll-messages` section (Claude-Code-only framing → host-generic +
  `--host` documented)
- `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md`,
  `docs/guides/EXAMPLES_MINING_GUIDE.md` — remove/qualify Claude-Code-only framing for ll-messages
- `scripts/little_loops/cli/__init__.py` module docstring line 18
- `scripts/little_loops/loops/lib/cli.yaml:86-94` (`ll_messages` fragment description — stays
  unpinned per decision, description updated to "session logs of every registered host (narrow
  with `--host`)")

### Tests

- `scripts/tests/test_user_messages.py` — Codex content tests: user-turn extraction from
  `response_item` role `user`; `<environment_context>`/`developer`/`<turn_aborted>` excluded;
  0.130.0 `user_message` dedup when present; `include_agent_sessions=True` regression through the
  new path; a `handles` builder helper.
- `scripts/tests/test_cli.py` — `TestMainMessagesIntegration` (~651) and
  `TestMainMessagesAdditionalCoverage` (~1815): re-patch `little_loops.cli.messages.detect_sessions`
  (not `get_project_folder`) to return a fixed `[SessionHandle(...)]`.
- `scripts/tests/test_cli_messages.py` — same re-patch (currently patches `_PROJECT_FOLDER_PATH`,
  line 54).
- Existing Claude Code tests in all files above pass unmodified except where they patch
  `get_project_folder` directly.

## Acceptance Criteria

- `ll-messages` (user messages, commands, and `--sft-format --reader auto|jsonl` conversation
  turns) obtains sessions via `detect_sessions`/`iter_events` and never calls
  `get_project_folder`/`get_sessions_folder` for session enumeration.
- `ll-messages --host codex` yields the user's typed prompts from `response_item` role-`user`
  messages, excludes `<environment_context>`/`<turn_aborted>`/`developer`-role messages, and
  `extract_commands` yields no records for Codex handles.
- `ll-messages --host codex` on a 0.130.0-shaped session (both `response_item` and `event_msg`
  present for the same turn) yields each prompt once.
- `ll-messages --host codex` records carry `session_id == handle.session_id`,
  `uuid == payload.id`, `cwd` from `session_meta`, `git_branch is None`, `is_sidechain is False`.
- With no flag and no `LL_HOOK_HOST`, a workspace containing both a Claude Code and a Codex
  session shows both; `--host codex`/`--host claude-code` narrows to one.
- `ll-messages` with no sessions for the target still exits 1, now with `"No sessions found for:
  <cwd>"` on stderr.
- Claude Code output for every existing test in `test_user_messages.py` is unchanged;
  `include_agent_sessions=True` still includes `agent-*` sessions.
- `docs/reference/CLI.md` and the three guides no longer frame `ll-messages` as Claude-Code-only.

## Dependencies

Blocked by ENH-3427 (host-resolution seam). Independent of ENH-3429/ENH-3430 (disjoint files —
touches `user_messages.py`/`cli/messages.py` only).

## Status

**Open** | Created: 2026-09-09 | Priority: P2


## Session Log
- `/ll:issue-size-review` - 2026-09-09T21:57:08 - `0ecdfd2a-1186-4e76-ae8e-586f75aad086.jsonl`
