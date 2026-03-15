---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# FEAT-702: Add `--json` output to `ll-loop history`, `status`, and `show`

## Summary

The `ll-loop history`, `status`, and `show` subcommands lack `--json` output mode, while the sibling `ll-loop list` subcommand supports it.

## Motivation

`ll-loop list --json` already exists, setting user expectations that all loop subcommands support programmatic output. The three missing subcommands produce structured internal data that is directly serializable — the gap is output path only, not data availability. All three commands produce structured data internally (`get_loop_history` returns `list[dict]`, `StatePersistence.load_state` returns a dataclass, `FSMLoop` is a structured dataclass) that could be directly serialized.

## Location

- **File**: `scripts/little_loops/cli/loop/info.py` — `cmd_history` (lines 397-448), `cmd_show` (lines 557-757)
- **File**: `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_status` (lines 36-74)
- **File**: `scripts/little_loops/cli/loop/__init__.py` — subparser definitions

## Current Behavior

`history` formats events as colored text. `status` prints individual fields. `show` renders an FSM description with diagram. Only `list` supports `--json`.

## Expected Behavior

All three subcommands accept `--json` flag and emit structured JSON to stdout when set.

## Use Case

A developer building monitoring or automation around FSM loops wants to check loop state programmatically. They pipe `ll-loop status --json my-loop` to `jq` for integration with dashboards or alerting.

## Proposed Solution

Add `--json` argument to the `history`, `status`, and `show` subparsers. In each command, add a JSON output branch using `json.dumps` on the already-available structured data (`list[dict]` from `get_loop_history`, dataclass from `StatePersistence.load_state`, `FSMLoop` dataclass).

## Acceptance Criteria

- [x] `ll-loop history --json <loop>` outputs event list as JSON
- [x] `ll-loop status --json <loop>` outputs loop state as JSON
- [x] `ll-loop show --json <loop>` outputs FSM config as JSON
- [x] Human-readable output remains the default

## Implementation Steps

1. In `scripts/little_loops/cli/loop/__init__.py`, add `--json` flag to `status` (line ~163) and `show` (line ~279) subparsers — history already has it at line 234
2. Update `cmd_status` in `lifecycle.py` to accept `args` parameter; update dispatch at `__init__.py:299-300` to forward `args`
3. In `lifecycle.py`, add JSON branch in `cmd_status`: call `state.to_dict()` and optionally append PID, then call `print_json()`
4. In `info.py`, add JSON branch in `cmd_show` (~line 590): call `fsm.to_dict()` and call `print_json()`
5. Use `.to_dict()` (not `dataclasses.asdict()`) — both `LoopState` and `FSMLoop` have `.to_dict()` returning JSON-native types; no datetime conversion needed (timestamps stored as plain ISO strings)
6. Add tests in `scripts/tests/test_ll_loop_commands.py` using `argparse.Namespace(json=True)` pattern

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`--json` flag parser registration** (follow this exact pattern):
```python
status_parser.add_argument("--json", action="store_true", help="Output loop state as JSON")
show_parser.add_argument("--json", action="store_true", help="Output FSM config as JSON")
```
- `list` pattern: `__init__.py:161`
- `history` already done: `__init__.py:234` (no change needed there)

**`cmd_status` signature issue** — current signature is `cmd_status(loop_name, loops_dir, logger)` with no `args`. Dispatch at `__init__.py:299-300` does not forward `args`. Both must change:
```python
# lifecycle.py — add args parameter
def cmd_status(loop_name: str, loops_dir: Path, logger: Logger, args: argparse.Namespace | None = None) -> int:

# __init__.py:299-300 — forward args
return cmd_status(args.loop, loops_dir, logger, args)
```

**Serialization** — no custom encoder or `dataclasses.asdict()` needed:
- `LoopState.to_dict()` → `persistence.py:93-111` — all fields are JSON-native (timestamps pre-serialized as ISO strings)
- `FSMLoop.to_dict()` → `schema.py:406-437` — recursive, includes all nested dataclasses
- `print_json` import: `from little_loops.cli.output import print_json`
- JSON branch guard pattern: `if getattr(args, "json", False):`

**PID for `status` JSON** — `_read_pid_file()` returns `int | None` (`lifecycle.py:22-33`). Recommend including in output:
```python
d = state.to_dict()
running_dir = loops_dir / ".running"
pid_file = running_dir / f"{loop_name}.pid"
d["pid"] = _read_pid_file(pid_file)
print_json(d)
```

**Test file**: `scripts/tests/test_ll_loop_commands.py`
- See lines 247-297 for `cmd_list --json` test pattern (direct function call + `capsys`)
- See lines 934-965 for `LoopState` construction in tests
- Test pattern: `args = argparse.Namespace(json=True)`, then `json.loads(capsys.readouterr().out)`

## Integration Map

- **Modified**: `scripts/little_loops/cli/loop/__init__.py` — add `--json` to `status` (~line 163) and `show` (~line 279) subparsers; update dispatch at line 299-300 to forward `args` to `cmd_status`
- **Modified**: `scripts/little_loops/cli/loop/info.py` — add JSON branch in `cmd_show()` (~line 590 after `fsm` is loaded); `cmd_history()` JSON is already partially implemented (run-id path at line 428-430 uses `print_json`, list-runs path at line 347-363 uses manual `_json.dumps`)
- **Modified**: `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_status()` (lines 36-74): add `args` parameter, add JSON branch using `state.to_dict()`
- **Tests**: `scripts/tests/test_ll_loop_commands.py` — add JSON output tests for `cmd_status` and `cmd_show`

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/loop/__init__.py:299-300` — dispatches `cmd_status`; must forward `args`
- `scripts/little_loops/fsm/persistence.py:93-111` — `LoopState.to_dict()` (ready to use)
- `scripts/little_loops/fsm/schema.py:406-437` — `FSMLoop.to_dict()` (ready to use)
- `scripts/little_loops/cli/output.py:97-99` — `print_json()` utility (import and use)

## Impact

- **Priority**: P4 - Consistency improvement across CLI subcommands
- **Effort**: Small - Data structures already serializable
- **Risk**: Low - Additive feature
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-loop`

## Session Log
- `/ll:ready-issue` - 2026-03-15T16:04:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7756d1b-485d-458f-b460-d73ffbb35470.jsonl`
- `/ll:verify-issues` - 2026-03-15T15:13:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eaa8d229-0594-4366-bff7-6d5160769e5e.jsonl`
- `/ll:refine-issue` - 2026-03-15T15:11:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/47847ab1-3690-456f-8bbd-e8c2d6719032.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Completed** | Created: 2026-03-13 | Resolved: 2026-03-15 | Priority: P4

## Resolution

- Added `--json` flag to `status` subparser in `cli/loop/__init__.py`
- Added `--json` flag to `show` subparser in `cli/loop/__init__.py`
- Updated dispatch for `status` to forward `args` to `cmd_status`
- Updated `cmd_status` in `lifecycle.py` to accept optional `args` and output JSON via `state.to_dict()` with `pid` included
- Added JSON branch to `cmd_show` in `info.py` using `fsm.to_dict()`
- Added 6 tests covering JSON output and human-readable preservation for both commands

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/cli/loop/__init__.py` line 143 confirms `ll-loop list` has `--json`. `scripts/little_loops/cli/loop/info.py` `cmd_history` and `cmd_show` functions have no JSON output branch (no `--json` arg found in `info.py` besides the `list` command). `lifecycle.py` `cmd_status` has no JSON output. Feature not yet implemented for `history`, `status`, and `show`.
