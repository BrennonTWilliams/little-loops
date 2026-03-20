---
id: BUG-845
title: "ll-issues list --priority flag does not accept comma-separated values"
priority: P3
status: open
discovered_date: 2026-03-20
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`count` subcommand is also affected**: `__init__.py:204-208` defines `--priority` with identical `choices=` constraint; `count_cmd.py:37-38` uses the same `==` equality comparison. Add it to scope alongside `list`.
- **`search` subcommand already handles multi-value**: `__init__.py:136-142` uses `action="append"` (no `choices=`), and `search.py:73-85` has its own `_parse_priority_filter()` supporting range notation. Step 3 above is **not needed** — `search` is not broken.
- **Import pattern to follow** (from `auto.py:10-16`, `parallel.py:11-26`):
  ```python
  from little_loops.cli_args import parse_priorities
  # after parse_args():
  priority_filter = parse_priorities(args.priority)
  ```
- **Revised step 1 scope**: Remove `choices=` from `list` (line 75-79) and `count` (lines 204-208) in `__init__.py`; `search` already has no `choices=`.
- **Test to add**: `test_issues_cli.py:190-213` has a single-value `list --priority P0` test. Add a parallel test for `list --priority P0,P1` asserting both P0 and P1 issues are shown and P2+ are excluded. Follow the `test_list_filter_by_priority` pattern.

## Affected Files

- `scripts/little_loops/cli/issues/__init__.py`
- `scripts/little_loops/cli/issues/list_cmd.py`
- `scripts/little_loops/cli/issues/count_cmd.py` — same `choices=`/equality bug as `list_cmd.py`
- `scripts/little_loops/cli_args.py` — source of `parse_priorities()` to import
- `scripts/little_loops/cli/issues/search.py` — **not affected** (already multi-value via `action="append"`)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py:75-79` — remove `choices=` from `list` `--priority`; update help text
- `scripts/little_loops/cli/issues/__init__.py:204-208` — remove `choices=` from `count` `--priority`; update help text
- `scripts/little_loops/cli/issues/list_cmd.py:40,46` — change `priority_filter: str|None` to `set[str]|None`; change `==` to `in`
- `scripts/little_loops/cli/issues/count_cmd.py:37-38` — same equality change as `list_cmd.py`

### Callers of `parse_priorities` (reference pattern)
- `scripts/little_loops/cli/auto.py:82` — calls `parse_priorities(args.priority)` immediately after `parse_args()`
- `scripts/little_loops/cli/parallel.py:160` — identical pattern

### Tests
- `scripts/tests/test_issues_cli.py:190-213` — existing `test_list_filter_by_priority`; add multi-value variant here
- `scripts/tests/test_cli_args.py:415-497` — unit tests for `parse_priorities`; no changes needed

### Documentation
- `docs/reference/CLI.md:473-476` — documents `ll-issues list --priority` usage; update example to show comma-separated form

## Session Log
- `/ll:confidence-check` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae4f7fa9-4038-444b-b34c-8c4cea5178e2.jsonl`
- `/ll:refine-issue` - 2026-03-20T20:49:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a0f20ea2-de01-4aad-9b50-0fb474f379d2.jsonl`
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7180b81f-d6f9-4361-8292-01d583d240bd.jsonl`

---
## Status

Open
