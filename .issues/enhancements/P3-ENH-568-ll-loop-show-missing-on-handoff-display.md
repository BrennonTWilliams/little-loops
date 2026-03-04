---
id: ENH-568
priority: P3
status: active
discovered_date: 2026-03-04
discovered_by: capture-issue
confidence_score: null
outcome_confidence: null
---

# ENH-568: `ll-loop show` missing `on_handoff` display

## Summary

`FSMLoop.on_handoff` is a top-level loop setting defined in the schema and respected at runtime, but `cmd_show` never prints it. Users inspecting a loop cannot see whether it will `pause`, `spawn`, or `terminate` on handoff signal.

## Current Behavior

`ll-loop show issue-refinement` output:
```
Max iterations: 100
Source: .loops/issue-refinement.yaml
```

The `on_handoff: spawn` setting from the YAML is invisible.

## Expected Behavior

```
Max iterations: 100
On handoff: spawn
Source: .loops/issue-refinement.yaml
```

Show `on_handoff` whenever it is set (always show it, or at minimum when non-default). The default is `"pause"`, so `spawn` and `terminate` should always be surfaced.

## Motivation

`on_handoff` controls significant runtime behavior. A loop set to `spawn` will launch a subprocess on handoff rather than pausing — this is important to understand when inspecting a loop's behavior, especially before running it in automation contexts.

## Implementation Steps

1. In `cmd_show` (`scripts/little_loops/cli/loop/info.py`), after the `max_iterations` line, add:
   ```python
   if fsm.on_handoff != "pause":
       print(f"On handoff: {fsm.on_handoff}")
   ```
   Or show it unconditionally with the default noted:
   ```python
   print(f"On handoff: {fsm.on_handoff}")
   ```

## Files to Change

- `scripts/little_loops/cli/loop/info.py` — `cmd_show` function (~line 524)

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d569869-6d78-45db-ae07-4c05f23b46fe.jsonl`
