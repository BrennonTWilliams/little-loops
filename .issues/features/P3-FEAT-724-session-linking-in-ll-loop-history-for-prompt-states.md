---
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# FEAT-724: Session Linking in ll-loop History for Prompt States

## Summary

Add session linking to `ll-loop history` output so that Claude Code log files (JSONL) can be traced back to specific FSM loop state executions that invoke Claude (i.e., `action_type: prompt` or `slash_command` states).

## Context

**Direct mode**: User description: "Add session linking (like we do for Issues) to the output of ll-loop history, so that we can tie claude code log files to any FSM loop state execution that uses a claude call (eg 'prompt' states)"

## Use Case

**Who**: Developer running FSM loops with `prompt` or `slash_command` states

**Context**: After a loop run completes (or during debugging), the developer needs to inspect what Claude actually did during a specific state execution — e.g., why a prompt state produced unexpected output or what commands were run in a given iteration.

**Goal**: Trace the Claude Code JSONL session file that corresponds to a specific loop state execution directly from `ll-loop history`.

**Outcome**: `ll-loop history <loop>` shows the session file path alongside `action_complete` events for prompt states, enabling direct inspection of the Claude conversation for that iteration without manual correlation.

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

## Acceptance Criteria

- [ ] `action_complete` events for `is_prompt=True` states in `.events.jsonl` include a `session_jsonl` field (string path or null)
- [ ] `ll-loop history <loop>` displays session JSONL basename alongside `action_complete` events for prompt states in default mode
- [ ] `ll-loop history <loop> --verbose` displays the full session JSONL path
- [ ] Non-prompt states (`shell` action types) do not emit a `session_jsonl` field
- [ ] Existing history files without `session_jsonl` display without errors (graceful degradation)
- [ ] `get_current_session_jsonl()` from `session_log.py` is reused without modification

## Implementation Steps

1. **Capture session JSONL at action completion** (`fsm/executor.py`): After `action_runner.run()` returns for a prompt/slash_command state, call `get_current_session_jsonl()` (from `session_log.py`) and include the result in the `action_complete` event payload under key `session_jsonl`.

2. **Display in history** (`cli/loop/info.py`, `_format_history_event`): In the `action_complete` branch, if the event has `is_prompt=True` and a `session_jsonl` key, append a short display of the path (basename or truncated) to the detail string. In verbose mode, show the full path.

3. **Schema/documentation**: Update the FSM loop events documentation to note the new optional `session_jsonl` field on `action_complete` events.

## Affected Files

- `scripts/little_loops/fsm/executor.py` — emit `session_jsonl` in `action_complete` for prompt states
- `scripts/little_loops/cli/loop/info.py` — display `session_jsonl` in `_format_history_event`
- `scripts/little_loops/session_log.py` — reuse `get_current_session_jsonl()` (no changes needed)

## API/Interface

- New optional field `session_jsonl: str | None` added to `action_complete` events in `.events.jsonl` files when `is_prompt=True`.
- No CLI flag changes required; display is automatic in existing `history` output.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — emit `session_jsonl` in `action_complete` event for prompt/slash_command states
- `scripts/little_loops/cli/loop/info.py` — display `session_jsonl` in `_format_history_event` for `action_complete` events

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_log.py` — `get_current_session_jsonl()` reused as-is (no changes needed)

### Similar Patterns
- `.issues/` session log pattern managed by `session_log.py` — same JSONL path resolution approach used for issue session links

### Tests
- TBD — add test for `executor.py` `action_complete` payload including `session_jsonl` field when `is_prompt=True`
- TBD — add test for `info.py` `_format_history_event` rendering session path with/without `session_jsonl` key

### Documentation
- FSM loop events documentation — note new optional `session_jsonl` field on `action_complete` events

### Configuration
- N/A

## Out of Scope

- Linking sessions for `shell` action types (those don't spawn Claude).
- Back-filling existing history files.

## Impact

- **Priority**: P3 — Developer quality-of-life improvement; debugging prompt state outputs currently requires manual JSONL correlation
- **Effort**: Small — Reuses existing `get_current_session_jsonl()` from `session_log.py`; only 2 files need modification
- **Risk**: Low — Additive change; new optional field on existing events; no breaking changes to existing history format
- **Breaking Change**: No

## Labels

`feature`, `ll-loop`, `session-linking`, `captured`

## Status

`backlog`

## Verification Notes

- **Date**: 2026-03-14
- **Verdict**: VALID
- `scripts/little_loops/fsm/executor.py` emits `action_complete` at lines 583–588 with `is_prompt` (line 588) but no `session_jsonl` field — confirmed by grep. `scripts/little_loops/session_log.py` has `get_current_session_jsonl()` at line 62, not yet called from `executor.py`. `scripts/little_loops/cli/loop/info.py` has `_format_history_event` at line 152 with no `session_jsonl` handling. Feature not yet implemented.

## Session Log
- `/ll:verify-issues` - 2026-03-15T00:11:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/623195d5-5e50-40d6-b2b9-5b105ad77689.jsonl`
- `/ll:capture-issue` - 2026-03-13T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/711e6b32-70cb-4d26-8b4e-bc302750cb79.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34ee1913-aa14-4e60-9d80-efda0df3efc0.jsonl`
- `/ll:format-issue` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:verify-issues` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
