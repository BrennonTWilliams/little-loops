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
        print_json([s.__dict__ for s in states])  # or dataclasses.asdict
        return 0
    print("Running loops:")
    for state in states:
        ...
    return 0
```

**Fix 3 — honour `--json` in `cmd_history`** (`info.py`):
```python
if getattr(args, "json", False):
    print_json(events[-tail:])
    return 0
```

## Implementation Steps

1. In `__init__.py`, add `--json` arg to `history_parser` (after line 201)
2. In `info.py` `cmd_list`, insert JSON branch inside the `--running` block before the human-readable print loop
3. In `info.py` `cmd_history`, insert JSON branch after loading `events` and before the human-readable loop
4. Add/extend tests in `scripts/tests/` covering `list --running --json` and `history --json`

## Integration Map

- **Modified**: `scripts/little_loops/cli/loop/__init__.py` — `history_parser` definition
- **Modified**: `scripts/little_loops/cli/loop/info.py` — `cmd_list` (running branch), `cmd_history`
- **Tests**: `scripts/tests/` — unit tests for both commands' JSON output path

## Impact

- **Priority**: P3 - Inconvenient but non-blocking; workaround is to pipe through human-readable output
- **Effort**: Small — three localized changes, no logic complexity
- **Risk**: Low — only adds a new output branch; existing human-readable paths unchanged
- **Breaking Change**: No

## Labels

`bug`, `cli`, `output`

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/20b47448-a4ee-4c68-a90e-1574eafbf9f4.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P3
