---
discovered_date: 2026-03-13
discovered_by: capture-issue
---

# BUG-725: `ll-loop history` lacks `--json` flag; `ll-loop list --running --json` silently ignores `--json`

## Summary

Two related output-flag gaps in `ll-loop`:

1. `ll-loop history <loop> --json` is not supported — the `history` subparser never registers a `--json` argument, so argparse rejects it as an unrecognized argument.
2. `ll-loop list --running --json` silently ignores `--json` — the `--running` branch in `cmd_list` returns early (line 68) before the JSON check at lines 86/92, so running-loop output is always human-readable regardless of `--json`.

## Location

- **File**: `scripts/little_loops/cli/loop/__init__.py`
- **Line(s)**: 192–202 — `history` subparser missing `--json` argument
- **Anchor**: `history_parser` configuration block

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Line(s)**: 46–68 — `cmd_list` `--running` branch never checks `args.json`
- **Anchor**: `cmd_list` early-return block for `--running`

## Current Behavior

```
$ ll-loop history my-loop --json
error: unrecognized arguments: --json

$ ll-loop list --running --json
Running loops:
  my-loop: run_tests (iteration 3) [running] 42s
# ^^^ plain text, --json ignored
```

## Expected Behavior

```
$ ll-loop history my-loop --json
[{"event": "start", "timestamp": "...", ...}, ...]

$ ll-loop list --running --json
[{"loop_name": "my-loop", "current_state": "run_tests", "iteration": 3, "status": "running", ...}]
```

## Steps to Reproduce

**For `list --running --json`:**
1. Start a loop: `ll-loop run my-loop --background`
2. Run `ll-loop list --running --json`
3. Output is human-readable text, not JSON

**For `history --json`:**
1. Run `ll-loop history my-loop --json`
2. Argparse errors: `unrecognized arguments: --json`

## Root Cause

- **File**: `scripts/little_loops/cli/loop/__init__.py`
- **Anchor**: `history` subparser, lines 192–202
- **Cause**: `history_parser` never adds `--json` argument, unlike `list_parser` which adds it at line 148.

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Anchor**: `cmd_list`, lines 46–68
- **Cause**: The `--running` early-return path (returns at line 68) is taken before `getattr(args, "json", False)` is checked at line 86. JSON formatting is only applied in the non-running path.

## Proposed Solution

**Fix 1 — add `--json` to `history` subparser** (`__init__.py` line 202):
```python
history_parser.add_argument("--json", action="store_true", help="Output events as JSON array")
```

**Fix 2 — honour `--json` in `cmd_list --running` branch** (`info.py`):
```python
if getattr(args, "running", False) or status_filter:
    states = list_running_loops(loops_dir)
    if status_filter:
        states = [s for s in states if s.status == status_filter]
    if not states:
        ...
        return 0
    if getattr(args, "json", False):
        print_json([s.to_dict() for s in states])  # LoopState.to_dict() at persistence.py:85
        return 0
    print("Running loops:")
    for state in states:
        ...
    return 0
```

**Fix 3 — honour `--json` in `cmd_history`** (`info.py`):

Insert after the filtering at line 243 (`events = [e for e in events if ...]`) and before the for-loop at line 244 (`for event in events[-tail:]:`):
```python
if getattr(args, "json", False):
    print_json(events[-tail:])  # events are list[dict] — already JSON-serializable
    return 0
```

## Implementation Steps

1. In `__init__.py:201`, add after `history_parser`'s `--verbose` arg:
   `history_parser.add_argument("--json", action="store_true", help="Output as JSON array")`
2. In `info.py:68`, after the `for state in states:` loop (currently returns at line 68), insert JSON check before `print("Running loops:")` at line 58
3. In `info.py:244`, insert JSON branch after the verbose-filter line (`events = [e for e in events if ...]`) and before `for event in events[-tail:]:` — use `print_json(events[-tail:])`
4. Add tests to `scripts/tests/test_ll_loop_commands.py` following the pattern of `test_list_json_output` (line ~249) and `test_list_json_empty` (line ~279), using `argparse.Namespace(running=True, status=None, json=True)` for Fix 2 and `argparse.Namespace(tail=50, verbose=False, json=True)` for Fix 3

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — `history_parser` definition (lines 192–202); add `--json` arg after line 201
- `scripts/little_loops/cli/loop/info.py` — `cmd_list` running branch (lines 46–68); `cmd_history` (lines 225–249)

### Referenced (Read-Only)
- `scripts/little_loops/fsm/persistence.py:85` — `LoopState.to_dict()` — use this (not `__dict__`) for JSON serialization of running states
- `scripts/little_loops/fsm/persistence.py:455` — `get_loop_history()` returns `list[dict[str, Any]]` — directly JSON-serializable, no conversion needed

### Tests
- `scripts/tests/test_ll_loop_commands.py` — add tests for `list --running --json` and `history --json`; follow patterns at line ~249 (`test_list_json_output`) and ~279 (`test_list_json_empty`)
- `scripts/tests/test_ll_loop_parsing.py` — add parser-level test confirming `history --json` is accepted (currently no such test)

### Shared Utilities
- `scripts/little_loops/cli/output.py:97` — `print_json(data)` — already imported in `info.py:22`

## Impact

- **Priority**: P3 - Inconvenient but non-blocking; workaround is to pipe through human-readable output
- **Effort**: Small — three localized changes, no logic complexity
- **Risk**: Low — only adds a new output branch; existing human-readable paths unchanged
- **Breaking Change**: No

## Labels

`bug`, `cli`, `output`

## Resolution

**Status**: Fixed
**Resolved**: 2026-03-13

### Changes Made

1. **`scripts/little_loops/cli/loop/__init__.py`** — Added `--json` argument to `history_parser`
2. **`scripts/little_loops/cli/loop/info.py`** — `cmd_list`: inserted JSON branch before human-readable output in the `--running` path; `cmd_history`: inserted JSON branch after verbose-filter, before the for-loop

### Tests Added

- `TestHistoryTail::test_history_json_output` — verifies JSON array output
- `TestHistoryTail::test_history_json_respects_tail` — verifies `--tail` respected in JSON mode
- `TestHistoryTail::test_history_json_empty` — verifies empty history behaviour
- `TestCmdListRunningJson::test_list_running_json_output` — verifies `list --running --json` JSON output
- `TestCmdListRunningJson::test_list_running_json_empty` — verifies no running loops path
- `TestCmdListRunningJson::test_list_running_without_json_unchanged` — verifies human-readable path unchanged
- `TestLoopArgumentParsing::test_history_json_accepted_by_real_parser` — verifies parser-level acceptance

All 76 tests pass.

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/20b47448-a4ee-4c68-a90e-1574eafbf9f4.jsonl`
- `/ll:refine-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/489dd3dc-b0e8-40d4-8608-bda5ef8256a7.jsonl`
- `/ll:ready-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/672265d6-a677-41aa-9572-d4eac047150d.jsonl`
- `/ll:manage-issue` - 2026-03-13T00:00:00Z - fix

---

**Completed** | Created: 2026-03-13 | Resolved: 2026-03-13 | Priority: P3
