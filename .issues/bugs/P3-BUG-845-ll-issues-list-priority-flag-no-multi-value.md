---
id: BUG-845
title: "ll-issues list --priority flag does not accept comma-separated values"
priority: P3
status: open
discovered_date: 2026-03-20
discovered_by: capture-issue
---

# BUG-845: ll-issues list --priority flag does not accept comma-separated values

## Problem Statement

`ll-issues list --priority P1,P2` fails because the flag is declared with `choices=["P0","P1","P2","P3","P4","P5"]`, which enforces a single-value string match. Other CLI tools (`ll-auto`, `ll-parallel`) accept comma-separated priority values via the shared `parse_priorities()` helper in `cli_args.py`.

## Root Cause

- **File**: `scripts/little_loops/cli/issues/__init__.py` line 75–79
- **Function**: `setup_parser()` — `list` subcommand argument registration
- **Explanation**: The `--priority` argument for `ll-issues list` uses `choices=` to validate a single priority string. It does not use `parse_priorities()` from `cli_args.py`, which splits and normalizes comma-separated input like `"P1,P2"` into a `set[str]`. The `list_cmd.py` filter (line 46) also compares `issue.priority == priority_filter` (equality), which would need to change to `in` to support multiple values.

The same issue affects the `search` subcommand's `--priority` flag at line 137.

## Steps to Reproduce

```bash
ll-issues list --priority P1,P2
# error: argument --priority: invalid choice: 'P1,P2' (choose from 'P0', 'P1', 'P2', 'P3', 'P4', 'P5')

ll-auto --priority P1,P2
# works fine — uses parse_priorities()
```

## Expected Behavior

`ll-issues list --priority P1,P2` and `ll-issues search --priority P1,P2` should filter issues to those matching any of the listed priorities, consistent with `ll-auto` and `ll-parallel`.

## Implementation Steps

1. In `scripts/little_loops/cli/issues/__init__.py`:
   - Remove `choices=` from the `--priority` argument in both `list` and `search` subcommands
   - Import `parse_priorities` from `little_loops.cli_args`
   - Call `parse_priorities(args.priority)` in both subcommand handlers before filtering

2. In `scripts/little_loops/cli/issues/list_cmd.py` line 46:
   - Change `issue.priority == priority_filter` to `issue.priority in priority_filter` (after making `priority_filter` a `set[str] | None`)

3. Do the same for `search` subcommand handler if it has analogous equality filtering.

4. Update help text to document comma-separated usage: `"Filter by priority level (e.g. P1,P2)"`

## Affected Files

- `scripts/little_loops/cli/issues/__init__.py`
- `scripts/little_loops/cli/issues/list_cmd.py`
- `scripts/little_loops/cli/issues/search.py` (likely)

## Session Log
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7180b81f-d6f9-4361-8292-01d583d240bd.jsonl`

---
## Status

Open
