---
discovered_commit: 3e9beea
discovered_branch: main
discovered_date: 2026-03-12
discovered_by: audit-architecture
focus_area: integration
confidence_score: 91
outcome_confidence: 86
---

# ENH-683: Break circular import: cli.loop._helpers <-> cli.loop.info

## Summary

Architectural issue found by `/ll:audit-architecture`.

Circular dependency within the CLI loop subpackage:
`cli.loop._helpers` -> `cli.loop.info` -> `cli.loop._helpers`

## Motivation

Helper modules (`_helpers`) should be leaf dependencies — consumed by feature modules, not consumers of them. When `_helpers` imports from `info`, it inverts the intended dependency direction, making both modules harder to test independently and introducing an ordering trap for future developers.

## Location

- **File**: `scripts/little_loops/cli/loop/_helpers.py`, `scripts/little_loops/cli/loop/info.py`
- **Module**: `little_loops.cli.loop._helpers`, `little_loops.cli.loop.info`

## Current Behavior

`cli/loop/_helpers.py` has a lazy import of `_render_fsm_diagram` from `cli/loop/info.py` (line 316), while `info.py` imports from `_helpers.py` (line 11). This creates a circular dependency: `_helpers` → `info` → `_helpers`.

## Expected Behavior

`info.py` depends on `_helpers.py` only (one-way). `_helpers.py` contains no imports from `info.py`. Dependency flows in a single direction: `info` → `_helpers`.

## Finding

### Current State

The helper module and info display module have mutual imports. Helper modules should be leaf dependencies, not consumers of the modules they support.

### Impact

- **Development velocity**: Minor; contained within one subpackage
- **Maintainability**: Confusing dependency direction
- **Risk**: Low

## Proposed Solution

Extract shared utilities/constants into a dedicated module or reorganize so `_helpers` doesn't import from `info`.

### Suggested Approach

1. Identify what `_helpers` imports from `info`
2. Move shared constants/utilities to a `_constants.py` or keep in `_helpers`
3. Make `info` depend on `_helpers` only (not vice versa)

## Scope Boundaries

- Contained to `cli/loop/` subpackage only
- No changes to public command interfaces or user-visible behavior
- May introduce a `_constants.py` if shared values need a neutral home

## Implementation Steps

1. Identify what `_helpers` imports from `info`
2. Move shared constants or utilities to a `_constants.py` or keep them in `_helpers`
3. Update `info` to import from `_helpers` only (one-way dependency)
4. Remove the back-reference from `_helpers` to `info`

## Integration Map

- **Modified**: `scripts/little_loops/cli/loop/_helpers.py`, `scripts/little_loops/cli/loop/info.py`
- **Possibly introduced**: `scripts/little_loops/cli/loop/_constants.py` (for shared values)
- **Direction after fix**: `info` → `_helpers` (one-way only)

## Impact Assessment

- **Priority**: P4 - Low severity architectural cleanup, no user-visible impact
- **Severity**: Low
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Session Log
- `/ll:ready-issue` - 2026-03-17T01:50:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/107d545b-7908-43db-ab43-583614e6f720.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ccc2230-6d69-46a3-8836-f6cde953377c.jsonl`
- `/ll:verify-issues` - 2026-03-15T00:11:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/623195d5-5e50-40d6-b2b9-5b105ad77689.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

## Verification Notes

- **Date**: 2026-03-14
- **Verdict**: NEEDS_UPDATE
- Lazy import in `_helpers.py` has drifted to **line 316** (was line 302). `info.py:11` still imports from `_helpers`. Circular dependency confirmed as described.

## Resolution

- **Date**: 2026-03-16
- **Approach**: Changed lazy import in `_helpers.py` line 316 from `little_loops.cli.loop.info` to `little_loops.cli.loop.layout` — `_render_fsm_diagram` already lives in `layout.py`; `info.py` was merely re-exporting it.
- **Files changed**: `scripts/little_loops/cli/loop/_helpers.py`, `scripts/tests/test_ll_loop_display.py` (updated 2 test mocks from `info_mod` to `layout_mod`)
- **Verification**: All 3586 tests pass.

## Status

**Completed** | Created: 2026-03-12 | Resolved: 2026-03-16 | Priority: P4
