---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
---

# FEAT-832: `ll-issues count` missing `--status` flag

## Summary

`ll-issues count` always calls `find_issues` which only scans active issue directories. Unlike `cmd_list` and `cmd_search` (which both accept `--status`), there is no way to count completed or deferred issues.

## Location

- **File**: `scripts/little_loops/cli/issues/count_cmd.py`
- **Line(s)**: 14-53 (at scan commit: 8c6cf90)
- **Anchor**: `in function cmd_count`
- **Code**:
```python
def cmd_count(config: BRConfig, args: argparse.Namespace) -> int:
    from little_loops.issue_parser import find_issues
    type_prefixes = {args.type} if getattr(args, "type", None) else None
    issues = find_issues(config, type_prefixes=type_prefixes)
```

## Current Behavior

`ll-issues count` only counts active issues. Users cannot ask "how many BUGs have been completed?"

## Expected Behavior

`ll-issues count` should accept `--status` (active/completed/deferred/all) to match the filtering available in `ll-issues list` and `ll-issues search`.

## Use Case

A developer wants to check how many bugs have been completed this sprint. They run `ll-issues count --type BUG --status completed` to get a quick number for a status update.

## Acceptance Criteria

- [ ] `ll-issues count --status completed` counts issues in the completed directory
- [ ] `ll-issues count --status deferred` counts issues in the deferred directory
- [ ] `ll-issues count --status all` counts across all directories
- [ ] Default behavior unchanged (active only)
- [ ] `--json` output includes the status filter used

## Proposed Solution

Use `_load_issues_with_status` from `search.py` (already implements status filtering) instead of `find_issues`. Add `--status` argument to the `count` subparser in `__init__.py`.

## Impact

- **Priority**: P4 - Missing CLI feature; workaround is `ll-issues list --status completed | wc -l`
- **Effort**: Small - Reuse existing `_load_issues_with_status` function
- **Risk**: Low - Additive flag, default behavior unchanged
- **Breaking Change**: No

## Labels

`feature`, `cli`, `issues`

## Status

**Open** | Created: 2026-03-19 | Priority: P4


## Session Log
- `/ll:scan-codebase` - 2026-03-19T22:12:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
