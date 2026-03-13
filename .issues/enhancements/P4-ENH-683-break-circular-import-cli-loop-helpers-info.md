---
discovered_commit: 3e9beea
discovered_branch: main
discovered_date: 2026-03-12
discovered_by: audit-architecture
focus_area: integration
---

# ENH-683: Break circular import: cli.loop._helpers <-> cli.loop.info

## Summary

Architectural issue found by `/ll:audit-architecture`.

Circular dependency within the CLI loop subpackage:
`cli.loop._helpers` -> `cli.loop.info` -> `cli.loop._helpers`

## Location

- **File**: `scripts/little_loops/cli/loop/_helpers.py`, `scripts/little_loops/cli/loop/info.py`
- **Module**: `little_loops.cli.loop._helpers`, `little_loops.cli.loop.info`

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

## Impact Assessment

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

---

## Status

**Open** | Created: 2026-03-12 | Priority: P4
