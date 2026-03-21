---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 95
outcome_confidence: 93
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

- [x] `ll-issues sequence --type BUG` filters to bug issues only
- [x] Dependency graph still considers cross-type dependencies for ordering
- [x] Default behavior unchanged (all types)
- [x] `--json` output includes the type filter used

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

**Completed** | Created: 2026-03-19 | Resolved: 2026-03-21 | Priority: P4

## Resolution

Added `--type` argument to the `sequence` subparser in `__init__.py` (same pattern as `count`, `impact-effort`, `refine-status`). Updated `cmd_sequence` in `sequence.py` to pass `type_prefixes={args.type}` to `find_issues` when the flag is provided. JSON output includes `type_filter` field in each item when a type filter is active. Four new tests added to `TestIssuesCLISequence` covering filter by BUG, filter by FEAT, empty results, and JSON `type_filter` field.


## Verification Notes

**Verdict**: VALID — Issue accurately describes current codebase state (verified 2026-03-19).

- `sequence.py:27`: `find_issues(config)` called with no `type_prefixes` — confirmed
- `cmd_sequence` at lines 14-76 — exact match
- `issue_parser.py:617`: `find_issues` accepts `type_prefixes: set[str] | None = None` — confirmed
- `__init__.py:212-220`: `sequence` subparser has only `--limit` and `--json`, no `--type` — confirmed
- `list`, `count`, `impact-effort`, `refine-status` all expose `--type` — confirmed

## Session Log
- `/ll:manage-issue` - 2026-03-21T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c2f8a4f6-3ee2-4a2d-836e-a1e6fa1a16fe.jsonl`
- `/ll:ready-issue` - 2026-03-21T21:09:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c2f8a4f6-3ee2-4a2d-836e-a1e6fa1a16fe.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:19:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
