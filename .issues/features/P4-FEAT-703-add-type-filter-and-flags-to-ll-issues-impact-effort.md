---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# FEAT-703: Add `--type` filter and flags to `ll-issues impact-effort`

## Summary

The `ll-issues impact-effort` subcommand has no filtering flags — its `args` parameter is documented as "unused, reserved for future flags". Sibling subcommands (`list`, `count`, `sequence`, `refine-status`) all support `--type BUG|FEAT|ENH` filtering. The `find_issues` function already supports `type_prefixes` as a parameter.

## Location

- **File**: `scripts/little_loops/cli/issues/impact_effort.py` — `cmd_impact_effort` (line 180)
- **File**: `scripts/little_loops/cli/issues/__init__.py` — subparser (lines 104-106)

## Current Behavior

`cmd_impact_effort` calls `find_issues(config)` with no type filtering. The `args` parameter is unused. All issue types are always shown.

## Expected Behavior

`impact-effort` accepts `--type BUG|FEAT|ENH` to filter the matrix by issue type, consistent with other subcommands.

## Use Case

A developer running sprint planning wants to see only bug impact-effort distribution: `ll-issues impact-effort --type BUG`.

## Acceptance Criteria

- [ ] `ll-issues impact-effort --type BUG` shows only bugs in the matrix
- [ ] Multiple types supported: `--type BUG --type FEAT`
- [ ] Default (no flag) shows all types (unchanged behavior)

## Impact

- **Priority**: P4 - Consistency improvement, uses existing infrastructure
- **Effort**: Small - Add `--type` arg, pass to `find_issues(config, type_prefixes=...)`
- **Risk**: Low - Additive feature, reuses existing filtering
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-issues`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4
