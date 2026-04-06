---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
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
- **Cause**: The session filter at lines 189–197 builds `matching_sessions` from the `messages` list and filters `messages` in-place. The `commands` list is computed separately via `extract_commands` and is combined with `messages` at lines 221–222 without applying `matching_sessions` as a filter.

## Proposed Solution

After filtering `messages`, apply the same `matching_sessions` set to `commands`:

```python
if args.skill:
    matching_sessions = {
        msg["session"] for msg in messages
        if args.skill.lower() in msg.get("content", "").lower()
    }
    messages = [m for m in messages if m["session"] in matching_sessions]
    commands = [c for c in commands if c.get("session") in matching_sessions]
```

Verify that `commands` entries carry a `"session"` key (check `extract_commands` output shape) before applying the filter.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/messages.py` — `main_messages` skill filter block

### Dependent Files (Callers/Importers)
- `scripts/little_loops/ll_workflows.py` — calls `ll-messages` output for workflow analysis

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_cli.py` — `test_skill_filter_narrows_to_matching_sessions` — extend to assert commands list is also filtered

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Confirm `commands` entries include a `"session"` field by inspecting `extract_commands` return value
2. Apply `matching_sessions` filter to `commands` in the `--skill` block
3. Update `test_skill_filter_narrows_to_matching_sessions` to assert commands from non-matching sessions are excluded

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
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P3
