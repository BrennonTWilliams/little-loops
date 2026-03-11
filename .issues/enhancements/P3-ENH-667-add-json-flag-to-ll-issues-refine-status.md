---
discovered_date: 2026-03-10
discovered_by: capture-issue
---

# ENH-667: Add `--json` flag to `ll-issues refine-status`

## Current Behavior

`ll-issues refine-status` supports machine-readable output via `--format json`, which outputs one JSON record per line (NDJSON). However, `ll-issues list` uses `--json` (a boolean flag) for its JSON mode. The inconsistency means scripts and FSM loops must use different flag styles depending on which subcommand they call.

## Expected Behavior

`ll-issues refine-status` accepts a `--json` boolean flag as a shorthand alias for `--format json`, matching the interface of `ll-issues list`. Both flags can coexist: `--json` sets format to JSON, `--format json` continues to work as before.

Optionally, consider aligning the output shape: `list --json` outputs a JSON array while `refine-status --format json` outputs NDJSON. Decide whether to standardize on JSON array for `--json`.

## Summary

Add `--json` flag to `ll-issues refine-status` for interface consistency with `ll-issues list`.

## Motivation

FSM loops and automation scripts that use `ll-issues list --json` expect a consistent `--json` flag pattern across all `ll-issues` subcommands. Requiring `--format json` for `refine-status` is a papercut that breaks muscle memory and makes shell pipelines inconsistent.

## Implementation Steps

1. In `scripts/little_loops/cli/issues/__init__.py`, add `--json` boolean argument to the `refine-status` subparser (alongside existing `--format`).
2. In `cmd_refine_status` (`refine_status.py`), check `getattr(args, "json", False)` and treat it as equivalent to `fmt == "json"`.
3. Decide output shape: NDJSON (current) vs JSON array (matches `list`). Update accordingly.
4. Update help text and epilog example in `__init__.py`.
5. Add/update tests in `scripts/tests/` for `--json` flag on `refine-status`.

## Related Files

- `scripts/little_loops/cli/issues/__init__.py` — argument registration (lines 91-110)
- `scripts/little_loops/cli/issues/refine_status.py` — `cmd_refine_status` (lines 155-355)
- `scripts/little_loops/cli/issues/list_cmd.py` — reference implementation for `--json` flag

---

## Status

**Active** | P3 | ENH

## Session Log
- `/ll:capture-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/534f29dc-9078-4565-b6a5-14cb33271b6f.jsonl`
