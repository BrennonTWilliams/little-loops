---
discovered_date: 2026-03-13
discovered_by: capture-issue
---

# FEAT-724: Session Linking in ll-loop History for Prompt States

## Summary

Add session linking to `ll-loop history` output so that Claude Code log files (JSONL) can be traced back to specific FSM loop state executions that invoke Claude (i.e., `action_type: prompt` or `slash_command` states).

## Context

**Direct mode**: User description: "Add session linking (like we do for Issues) to the output of ll-loop history, so that we can tie claude code log files to any FSM loop state execution that uses a claude call (eg 'prompt' states)"

## Motivation

When an FSM loop runs a `prompt` or `slash_command` state, Claude Code spawns a new session (or continues one), producing a JSONL log file in `~/.claude/projects/<project>/`. Currently, those log files have no link back to the loop run or state that triggered them — and the loop history has no link forward to those files. This makes it impossible to:

- Debug why a prompt state produced a particular output
- Audit what Claude actually did during a loop iteration
- Correlate `ll-loop history` events with specific Claude Code session logs
- Replay or inspect the Claude conversation for a given iteration

Issues already have a `## Session Log` section (managed by `scripts/little_loops/session_log.py`) that records JSONL paths per command invocation. The same pattern should apply to loop history events.

## Expected Behavior

After a `prompt`/`slash_command` state completes:

1. The `action_complete` event emitted to the loop's `.events.jsonl` file includes a `session_jsonl` field pointing to the Claude Code session file that was active when the action ran.
2. `ll-loop history <loop>` displays the session JSONL path alongside `action_complete` events for prompt states (in verbose mode, or always in a compact short form).

### Example history output (verbose)

```
10:42:31  action_start    fix-issue  [prompt]
10:42:55  action_complete ✓  12400ms  session=~/.claude/projects/.../abc123.jsonl
```

### Example events.jsonl entry

```json
{"event": "action_complete", "ts": "...", "exit_code": 0, "duration_ms": 12400, "is_prompt": true, "session_jsonl": "/Users/.../.claude/projects/.../abc123.jsonl"}
```

## Implementation Steps

1. **Capture session JSONL at action completion** (`fsm/executor.py`): After `action_runner.run()` returns for a prompt/slash_command state, call `get_current_session_jsonl()` (from `session_log.py`) and include the result in the `action_complete` event payload under key `session_jsonl`.

2. **Display in history** (`cli/loop/info.py`, `_format_history_event`): In the `action_complete` branch, if the event has `is_prompt=True` and a `session_jsonl` key, append a short display of the path (basename or truncated) to the detail string. In verbose mode, show the full path.

3. **Schema/documentation**: Update the FSM loop events documentation to note the new optional `session_jsonl` field on `action_complete` events.

## Affected Files

- `scripts/little_loops/fsm/executor.py` — emit `session_jsonl` in `action_complete` for prompt states
- `scripts/little_loops/cli/loop/info.py` — display `session_jsonl` in `_format_history_event`
- `scripts/little_loops/session_log.py` — reuse `get_current_session_jsonl()` (no changes needed)

## API / Interface Changes

- New optional field `session_jsonl: str | None` added to `action_complete` events in `.events.jsonl` files when `is_prompt=True`.
- No CLI flag changes required; display is automatic in existing `history` output.

## Out of Scope

- Linking sessions for `shell` action types (those don't spawn Claude).
- Back-filling existing history files.

## Status

---

## Status

`backlog`

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/fsm/executor.py` emits `action_complete` at lines 583–588 with `is_prompt` but no `session_jsonl` field. `scripts/little_loops/session_log.py` exists with `get_current_session_jsonl()` available for reuse but not yet called from `executor.py`. Feature not yet implemented.

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/711e6b32-70cb-4d26-8b4e-bc302750cb79.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34ee1913-aa14-4e60-9d80-efda0df3efc0.jsonl`
