---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
---

# FEAT-833: `ll-issues sequence` missing `--type` filter

## Summary

`ll-issues sequence` always processes all active issues with no type filtering. All comparable subcommands (`list`, `count`, `impact-effort`, `refine-status`) expose `--type`, but `sequence` does not. The underlying `find_issues` function already supports `type_prefixes`.

## Location

- **File**: `scripts/little_loops/cli/issues/sequence.py`
- **Line(s)**: 14-76 (at scan commit: 8c6cf90)
- **Anchor**: `in function cmd_sequence`
- **Code**:
```python
def cmd_sequence(config: BRConfig, args: argparse.Namespace) -> int:
    from little_loops.dependency_graph import DependencyGraph
    from little_loops.issue_parser import find_issues

    issues = find_issues(config)  # No type_prefixes parameter
```

## Current Behavior

`ll-issues sequence` always includes all issue types. No way to see "just bugs in dependency order."

## Expected Behavior

`ll-issues sequence --type BUG` shows only bugs in dependency-resolved order.

## Use Case

A developer is doing a bug-fix pass and wants to see all bugs in the correct dependency order. They need `ll-issues sequence --type BUG` to get a prioritized, dependency-aware list of just bugs.

## Acceptance Criteria

- [ ] `ll-issues sequence --type BUG` filters to bug issues only
- [ ] Dependency graph still considers cross-type dependencies for ordering
- [ ] Default behavior unchanged (all types)
- [ ] `--json` output includes the type filter used

## Proposed Solution

Add `--type` argument to the `sequence` subparser in `__init__.py`. Pass `type_prefixes={args.type}` to `find_issues` when the flag is provided.

## Impact

- **Priority**: P4 - Missing filter; workaround is manual filtering of full sequence output
- **Effort**: Small - Add argument, pass to existing function parameter
- **Risk**: Low - Additive flag, default behavior unchanged
- **Breaking Change**: No

## Labels

`feature`, `cli`, `issues`

## Status

**Open** | Created: 2026-03-19 | Priority: P4


## Session Log
- `/ll:scan-codebase` - 2026-03-19T22:12:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
