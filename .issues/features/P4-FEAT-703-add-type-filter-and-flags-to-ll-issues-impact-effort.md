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

- **File**: `scripts/little_loops/cli/issues/impact_effort.py` — `cmd_impact_effort` (line 180)
- **File**: `scripts/little_loops/cli/issues/__init__.py` — subparser (lines 104-106)

## Current Behavior

`cmd_impact_effort` calls `find_issues(config)` with no type filtering. The `args` parameter is unused. All issue types are always shown.

## Expected Behavior

`impact-effort` accepts `--type BUG|FEAT|ENH` to filter the matrix by issue type, consistent with other subcommands.

## Use Case

A developer running sprint planning wants to see only bug impact-effort distribution: `ll-issues impact-effort --type BUG`.

## Proposed Solution

Add `--type` argument (same spec as other subcommands: `choices=["BUG", "FEAT", "ENH"]`, `nargs="*"`) to the `impact-effort` subparser. In `cmd_impact_effort`, convert `args.type` to `type_prefixes` and pass to `find_issues(config, type_prefixes=...)`.

## Acceptance Criteria

- [ ] `ll-issues impact-effort --type BUG` shows only bugs in the matrix
- [ ] Multiple types supported: `--type BUG --type FEAT`
- [ ] Default (no flag) shows all types (unchanged behavior)

## Implementation Steps

1. In `scripts/little_loops/cli/issues/__init__.py`, add `--type` argument to the `impact-effort` subparser (same spec as `list` subparser: `nargs="*"`, `choices=["BUG", "FEAT", "ENH"]`)
2. In `impact_effort.py`, update `cmd_impact_effort` (line 180) to pass `type_prefixes=args.type or []` to `find_issues(config, ...)`
3. Verify empty `--type` list defaults to all types (no change to current behavior)

## Integration Map

- **Modified**: `scripts/little_loops/cli/issues/__init__.py` — `impact-effort` subparser (lines 104-106)
- **Modified**: `scripts/little_loops/cli/issues/impact_effort.py` — `cmd_impact_effort()` (line 180)
- **Reused**: `scripts/little_loops/issue_manager.py` — `find_issues(config, type_prefixes=...)` (already supports filtering)

## Impact

- **Priority**: P4 - Consistency improvement, uses existing infrastructure
- **Effort**: Small - Add `--type` arg, pass to `find_issues(config, type_prefixes=...)`
- **Risk**: Low - Additive feature, reuses existing filtering
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-issues`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4
