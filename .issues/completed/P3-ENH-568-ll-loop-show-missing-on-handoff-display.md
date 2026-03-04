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

1. In `cmd_show` (`scripts/little_loops/cli/loop/info.py`), after the `max_iterations` print at line 526, add unconditional display:
   ```python
   print(f"On handoff: {fsm.on_handoff}")
   ```
2. Add two tests in `scripts/tests/test_ll_loop_commands.py` (`TestCmdShow` class, starts at line 312):
   - `test_show_displays_on_handoff`: create a loop with `on_handoff: spawn`, assert `"On handoff: spawn"` in output
   - Extend `test_show_displays_metadata` (line 333) to assert `"On handoff: pause"` for the default fixture (no `on_handoff` key in YAML → defaults to `"pause"`)
   - Follow the pattern from `test_ll_loop_display.py:464` (`test_metadata_shown`) — write YAML with the field set, `monkeypatch.chdir`, capture with `capsys`, assert substring
3. Run `python -m pytest scripts/tests/test_ll_loop_commands.py -v` to verify.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_show` function (line 503); metadata block lines 519–537; insert `on_handoff` print after line 526 (`Max iterations`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — imports `cmd_show` (line 20), dispatches on `args.command == "show"` (lines 195–196)
- `scripts/little_loops/cli/loop/_helpers.py` — `load_loop_with_spec` (line 71) returns `(FSMLoop, dict)` consumed by `cmd_show` at `info.py:508`
- `scripts/little_loops/fsm/schema.py` — defines `FSMLoop.on_handoff: Literal["pause", "spawn", "terminate"] = "pause"` at line 372; deserialized via `from_dict` at line 429; serialized conditionally in `to_dict` at lines 396–397
- `scripts/little_loops/fsm/compilers.py:205` — reads `on_handoff` from raw YAML spec via `spec.get("on_handoff", "pause")`
- `scripts/little_loops/fsm/persistence.py:253` — consumes `fsm.on_handoff` to construct `HandoffHandler`

### Loop YAMLs Using `on_handoff`
- `.loops/issue-refinement.yaml:65` — `on_handoff: spawn` (only built-in loop with a non-default value; the motivating example from the issue)

### Similar Patterns
- `info.py:525–530` — `timeout`, `backoff`, `maintain` in `cmd_show` use conditional (`if fsm.X:`) display; `on_handoff` intentionally breaks this pattern to always print (even the default `"pause"`)
- `test_ll_loop_display.py:464–491` — `test_metadata_shown` is the closest test model: writes a YAML field (`timeout: 3600`), asserts `"Timeout: 3600s"` appears in captured output — follow the same shape for `on_handoff`

### Tests
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdShow` class (line 312); add `test_show_displays_on_handoff` here

## Resolution

- Added `print(f"On handoff: {fsm.on_handoff}")` after `Max iterations` in `cmd_show` (`info.py:527`)
- Extended `test_show_displays_metadata` to assert `"On handoff: pause"` for default loops
- Added `test_show_displays_on_handoff` verifying `spawn` value displays correctly
- All 4 `TestCmdShow` tests pass

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d569869-6d78-45db-ae07-4c05f23b46fe.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2ee51b92-5622-4ca1-90d3-5475832955c3.jsonl`
- `/ll:refine-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e696e00-4453-4689-9b15-ff56c9d9b686.jsonl`
- `/ll:ready-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/441e7cc1-edbf-48d6-8b4a-39df8dd356bd.jsonl`
- `/ll:manage-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
