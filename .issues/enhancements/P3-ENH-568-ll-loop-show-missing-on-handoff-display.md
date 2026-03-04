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

## Acceptance Criteria

- [ ] `ll-loop show <loop>` output includes `On handoff: <value>` for all loops (always shown)
- [ ] Default value `pause` is printed (e.g., `On handoff: pause`) — not hidden
- [ ] Non-default values `spawn` and `terminate` are also displayed correctly
- [ ] Existing `test_show_displays_metadata` test passes with the new field present
- [ ] A new test `test_show_displays_on_handoff` verifies the line appears in output

## Success Metrics

- `On handoff:` line appears in `ll-loop show` output for all loops (100% of invocations)
- No regression in existing `cmd_show` tests

## Scope Boundaries

- **In scope**: Adding `On handoff: <value>` to the metadata block in `cmd_show`
- **Out of scope**: Other potentially missing fields (e.g., `maintain`, `backoff` are already shown conditionally — not changing that pattern for other fields); changes to `ll-loop run` output; changes to `ll-loop status`

## Implementation Steps

1. In `cmd_show` (`scripts/little_loops/cli/loop/info.py`), after the `max_iterations` line (~line 524), add unconditional display:
   ```python
   print(f"On handoff: {fsm.on_handoff}")
   ```
2. Add a test in `scripts/tests/test_ll_loop_commands.py` (`TestShowCommand` class) that creates a loop with `on_handoff: spawn` and asserts `"On handoff: spawn"` appears in output; also test default (`pause`) is shown.
3. Run `python -m pytest scripts/tests/test_ll_loop_commands.py -v` to verify.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_show` function (~line 524)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py` — passes `fsm` to `cmd_show`
- `scripts/little_loops/fsm/schema.py` — defines `FSMLoop.on_handoff` field (line 365, default `"pause"`)

### Similar Patterns
- `fsm.timeout`, `fsm.backoff`, `fsm.maintain` in `cmd_show` (~lines 525–530) — conditional display pattern; `on_handoff` intentionally breaks this pattern to always show

### Tests
- `scripts/tests/test_ll_loop_commands.py` — `TestShowCommand` class (add new test here)

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d569869-6d78-45db-ae07-4c05f23b46fe.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2ee51b92-5622-4ca1-90d3-5475832955c3.jsonl`
