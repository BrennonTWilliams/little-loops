---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
---

# BUG-966: `--skill` session filter not applied to `commands` list in `ll-messages`

## Summary

In `ll-messages`, the `--skill` flag is intended to narrow output to sessions where the given skill pattern appears. The filter correctly restricts the `messages` list to matching sessions, but the `commands` list (from `extract_commands`) is combined with `messages` after the filter without applying the same session scope. As a result, `--skill` produces a `combined` output that includes commands from all sessions, not just the skill-matching ones.

## Location

- **File**: `scripts/little_loops/cli/messages.py`
- **Line(s)**: 189–197, 221–222 (at scan commit: 96d74cda)
- **Anchor**: `in function main_messages`, skill filter block
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/cli/messages.py#L189-L197)
- **Code**:
```python
# Lines 189–197: messages filtered to matching sessions
if args.skill:
    matching_sessions = {
        msg["session"] for msg in messages
        if args.skill.lower() in msg.get("content", "").lower()
    }
    messages = [m for m in messages if m["session"] in matching_sessions]
    # commands not filtered here

# Lines 221–222: commands combined without session filter
combined = messages + commands  # commands still contains all sessions
```

## Current Behavior

Running `ll-messages --skill /ll:manage-issue` returns messages from sessions where that skill appears, but the `combined` output also includes commands from sessions that never used the skill.

## Expected Behavior

When `--skill` is specified, both `messages` and `commands` should be restricted to sessions where the skill pattern appears. The `combined` output should contain only entries from matching sessions.

## Motivation

The `--skill` filter is used by workflow analysis tools (e.g., `ll-workflows`) to isolate activity for a particular command. Leaking commands from non-matching sessions pollutes the analysis and produces incorrect session-correlation results.

## Steps to Reproduce

1. Have a Claude Code log directory with multiple sessions, at least one using `/ll:manage-issue` and others that don't.
2. Run `ll-messages --skill /ll:manage-issue --output json`.
3. Observe: the output includes commands (slash-command invocations) from sessions that never used `/ll:manage-issue`.

## Root Cause

- **File**: `scripts/little_loops/cli/messages.py`
- **Anchor**: `in function main_messages`
- **Cause**: The session filter at lines 189–197 builds `matching_sessions` from the `messages` list and filters `messages` in-place. The `commands` list is computed separately via `extract_commands` and is combined with `messages` at lines 221–225 without applying `matching_sessions` as a filter.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Exact filter block at `messages.py:189–197` (uses compiled regex, not `.lower()` string match):
```python
if args.skill:
    import re
    skill_pattern = re.compile(rf"<command-name>/ll:{re.escape(args.skill)}</command-name>")
    matching_sessions = {
        msg.session_id for msg in messages if skill_pattern.search(msg.content)
    }
    messages = [msg for msg in messages if msg.session_id in matching_sessions]
    # commands list (populated at lines 181–187) is never filtered here
```

`combined` assembled at `messages.py:221–225`:
```python
combined: list[UserMessage | CommandRecord] = []
combined.extend(messages)   # already filtered to matching sessions
combined.extend(commands)   # never filtered — all sessions present
combined.sort(key=lambda x: x.timestamp, reverse=True)
```

`--since` and `--exclude-agents` are correctly applied to both lists at extraction time (passed as args to both `extract_user_messages` and `extract_commands`). `--skill` is the only post-extraction filter, and it operates only on `messages`.

## Proposed Solution

After filtering `messages`, apply the same `matching_sessions` set to `commands`. **Important**: `CommandRecord` is a dataclass — use attribute access `c.session_id`, not `c.get("session")`:

```python
if args.skill:
    import re
    skill_pattern = re.compile(rf"<command-name>/ll:{re.escape(args.skill)}</command-name>")
    matching_sessions = {
        msg.session_id for msg in messages if skill_pattern.search(msg.content)
    }
    messages = [msg for msg in messages if msg.session_id in matching_sessions]
    commands = [c for c in commands if c.session_id in matching_sessions]
```

`CommandRecord.session_id` is confirmed populated at `user_messages.py:592` from `record.get("sessionId", "")`. The `to_dict()` serialization at `user_messages.py:131` outputs it as `"session_id"` (not `"session"`).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/messages.py` — `main_messages` skill filter block (lines 189–197)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/workflow_sequence/__init__.py:60` — `ll-workflows` entry point; downstream consumer that processes `ll-messages` output JSONL files (does not call `ll-messages` directly — user runs `ll-messages` first, then pipes to `ll-workflows`)
- `scripts/little_loops/user_messages.py:466` — `extract_commands()` definition; confirmed `CommandRecord.session_id` field populated at line 592

### Similar Patterns
- `messages.py:189–197` — `--since` filter applied symmetrically to both lists at extraction time (passed to both `extract_user_messages` and `extract_commands`) — reference for how symmetric filtering should work
- `messages.py:200–202` — `--exclude-agents` applied symmetrically at extraction time

### Tests
- `scripts/tests/test_cli.py:1821` — `TestMainMessagesAdditionalCoverage.test_skill_filter_narrows_to_matching_sessions` — extend to also mock `extract_commands` returning a `CommandRecord` with non-matching `session_id`, then assert it's excluded from `_save_combined` args
- `scripts/tests/test_user_messages.py:1079` — `TestExtractCommands` — `temp_project_folder` fixture and `_write_jsonl` helper available here for reference

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `scripts/little_loops/cli/messages.py:189–197`, add one line after `messages = [...]`:
   ```python
   commands = [c for c in commands if c.session_id in matching_sessions]
   ```
2. In `scripts/tests/test_cli.py:1821` (`test_skill_filter_narrows_to_matching_sessions`):
   - Add a `with patch("little_loops.user_messages.extract_commands") as mock_cmds:` block
   - Return one `CommandRecord` with `session_id="sess-other"` (non-matching) from the mock
   - Add assertion: `assert not any(item.session_id == "sess-other" for item in saved_items)`
3. Run `python -m pytest scripts/tests/test_cli.py::TestMainMessagesAdditionalCoverage::test_skill_filter_narrows_to_matching_sessions -v` to verify

## Impact

- **Priority**: P3 — Correctness bug in a filtering feature; affects workflow analysis accuracy
- **Effort**: Small — One additional list comprehension in an existing block
- **Risk**: Low — The change only restricts data; cannot break callers that expect broader output since the feature's contract is to restrict
- **Breaking Change**: No (fixing incorrect behavior)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `cli`, `messages`, `captured`

## Session Log
- `/ll:refine-issue` - 2026-04-06T17:45:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e865744b-5f95-469a-aa99-0a969bc7ec79.jsonl`
- `/ll:format-issue` - 2026-04-06T17:43:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8ca7e8b3-b4f4-4de0-9e63-9207ac71f450.jsonl`
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`
- `/ll:confidence-check` - 2026-04-06T18:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4488fe91-5adc-4748-9bdd-d954babb961d.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P3
