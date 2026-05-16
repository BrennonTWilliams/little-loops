---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# FEAT-703: Add `--type` filter and flags to `ll-issues impact-effort`

## Summary

The `ll-issues impact-effort` subcommand has no filtering flags — its `args` parameter is documented as "unused, reserved for future flags". Sibling subcommands (`list`, `count`, `sequence`, `refine-status`) all support `--type BUG|FEAT|ENH` filtering. The `find_issues` function already supports `type_prefixes` as a parameter.

## Motivation

Sprint planning often focuses on a single issue type (e.g., "show me only bug distribution for this sprint"). Without `--type` filtering, users must mentally filter the full matrix. All sibling subcommands already support `--type`, and `find_issues` already accepts `type_prefixes` — this is a missing wire-up.

## Location

- **File**: `scripts/little_loops/cli/issues/impact_effort.py` — `cmd_impact_effort` (line 166)
- **File**: `scripts/little_loops/cli/issues/__init__.py` — `impact-effort` subparser (lines 184-186)

## Current Behavior

`cmd_impact_effort` (`impact_effort.py:166`) calls `find_issues(config)` at `impact_effort.py:185-187` with no type filtering. The docstring at `impact_effort.py:179-180` explicitly notes `args` is "unused, reserved for future flags". The subparser at `__init__.py:182-184` registers only `add_config_arg(ie)` — no `--type` argument. All issue types are always shown.

## Expected Behavior

`impact-effort` accepts `--type BUG|FEAT|ENH` to filter the matrix by issue type, consistent with other subcommands.

## Use Case

A developer running sprint planning wants to see only bug impact-effort distribution: `ll-issues impact-effort --type BUG`.

## Proposed Solution

Add `--type` argument (same spec as `list`/`count`/`refine-status` subcommands: `choices=["BUG", "FEAT", "ENH"]`, single-value, no `nargs`) to the `impact-effort` subparser. In `cmd_impact_effort`, convert `args.type` to a `set[str]` and pass to `find_issues(config, type_prefixes=...)`.

Exact pattern from sibling commands (`list_cmd.py:26-27`):
```python
type_prefixes = {args.type} if getattr(args, "type", None) else None
issues = find_issues(config, type_prefixes=type_prefixes)
```

## Acceptance Criteria

- [x] `ll-issues impact-effort --type BUG` shows only bugs in the matrix
- [x] `ll-issues impact-effort --type FEAT` shows only features
- [x] Default (no flag) shows all types (unchanged behavior)
- [x] Invalid type (e.g. `--type FOO`) rejected by argparse with exit code 2

## Implementation Steps

1. In `scripts/little_loops/cli/issues/__init__.py` at lines 184-186, add `--type` argument to the `impact-effort` subparser — match `list` subparser spec at `__init__.py:73`:
   ```python
   ie.add_argument("--type", choices=["BUG", "FEAT", "ENH"], help="Filter by issue type")
   ```
2. In `impact_effort.py`, update `cmd_impact_effort` (line 166) to build `type_prefixes` and pass to `find_issues(config, ...)` at line 185 — match sibling pattern from `list_cmd.py:26-27`:
   ```python
   type_prefixes = {args.type} if getattr(args, "type", None) else None
   issues = find_issues(config, type_prefixes=type_prefixes)
   ```
3. Remove the "unused, reserved for future flags" docstring note at `impact_effort.py:179-180` since `args` is now used
4. Add test `test_impact_effort_filter_by_type` in `TestIssuesCLIImpactEffort` class (`scripts/tests/test_issues_cli.py:467`) following the pattern from `TestIssuesCLIList.test_list_filter_by_type` (`test_issues_cli.py:166`): pass `["ll-issues", "impact-effort", "--type", "BUG", ...]`, assert BUG IDs in output and FEAT IDs not in output

## Integration Map

- **Modified**: `scripts/little_loops/cli/issues/__init__.py` — `impact-effort` subparser (lines 184-186): add `--type` argument
- **Modified**: `scripts/little_loops/cli/issues/impact_effort.py` — `cmd_impact_effort()` (line 166): use `args.type`, pass `type_prefixes` to `find_issues` at line 185
- **Reused**: `scripts/little_loops/issue_parser.py` — `find_issues(config, type_prefixes=...)` signature at line 597-603 (already supports filtering)
- **Test**: `scripts/tests/test_issues_cli.py:467` — add `test_impact_effort_filter_by_type` in `TestIssuesCLIImpactEffort` class

## Impact

- **Priority**: P4 - Consistency improvement, uses existing infrastructure
- **Effort**: Small - Add `--type` arg, pass to `find_issues(config, type_prefixes=...)`
- **Risk**: Low - Additive feature, reuses existing filtering
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-issues`

## Session Log
- `/ll:ready-issue` - 2026-03-15T16:14:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3121df56-85b4-49e5-bb6b-db3b263a29d4.jsonl`
- `/ll:verify-issues` - 2026-03-15T15:13:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eaa8d229-0594-4366-bff7-6d5160769e5e.jsonl`
- `/ll:refine-issue` - 2026-03-15T15:10:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71caa695-ccb2-4497-99ca-29e51e4c645f.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Completed** | Created: 2026-03-13 | Priority: P4

## Resolution

- Added `--type` argument to `impact-effort` subparser in `scripts/little_loops/cli/issues/__init__.py`
- Updated `cmd_impact_effort` in `scripts/little_loops/cli/issues/impact_effort.py` to pass `type_prefixes` to `find_issues`
- Added `test_impact_effort_filter_by_type` to `TestIssuesCLIImpactEffort` in `scripts/tests/test_issues_cli.py`
- All 7 `TestIssuesCLIImpactEffort` tests pass

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/cli/issues/impact_effort.py` has no `--type` filter. `scripts/little_loops/cli/issues/__init__.py` subparser for `impact-effort` does not include a `--type` argument. `find_issues` already supports `type_prefixes` parameter. Feature not yet implemented.
