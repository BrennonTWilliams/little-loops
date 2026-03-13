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

- **File**: `scripts/little_loops/cli/loop/info.py` — `cmd_history` (lines 225-248), `cmd_show` (lines 370-570)
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

- [ ] `ll-loop history --json <loop>` outputs event list as JSON
- [ ] `ll-loop status --json <loop>` outputs loop state as JSON
- [ ] `ll-loop show --json <loop>` outputs FSM config as JSON
- [ ] Human-readable output remains the default

## Implementation Steps

1. In `scripts/little_loops/cli/loop/__init__.py`, add `--json` flag to `history`, `status`, and `show` subparsers
2. In `info.py`, add JSON branch in `cmd_history` (serialize `get_loop_history` result) and `cmd_show` (serialize `FSMLoop` dataclass)
3. In `lifecycle.py`, add JSON branch in `cmd_status` (serialize `StatePersistence.load_state` dataclass)
4. Use `dataclasses.asdict()` for dataclass serialization and ensure datetime fields are converted to strings

## Integration Map

- **Modified**: `scripts/little_loops/cli/loop/__init__.py` — add `--json` to `history`, `status`, `show` subparsers
- **Modified**: `scripts/little_loops/cli/loop/info.py` — `cmd_history()` (lines 225-248), `cmd_show()` (lines 370-570)
- **Modified**: `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_status()` (lines 36-74)

## Impact

- **Priority**: P4 - Consistency improvement across CLI subcommands
- **Effort**: Small - Data structures already serializable
- **Risk**: Low - Additive feature
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-loop`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4
