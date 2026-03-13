---
discovered_commit: 3e9beea
discovered_branch: main
discovered_date: 2026-03-12
discovered_by: audit-architecture
focus_area: integration
---

# ENH-682: Break circular import: dependency_mapper <-> cli.deps

## Summary

Architectural issue found by `/ll:audit-architecture`.

Circular dependency between library and CLI layer:
`dependency_mapper` -> `cli.deps` -> `dependency_mapper`

## Location

- **File**: `scripts/little_loops/dependency_mapper/__init__.py`, `scripts/little_loops/cli/deps.py`
- **Module**: `little_loops.dependency_mapper`, `little_loops.cli.deps`

## Finding

### Current State

The `dependency_mapper` package imports from `cli.deps`, violating the architectural boundary where CLI modules should depend on library modules but not vice versa.

### Impact

- **Development velocity**: Blurs the CLI/library boundary
- **Maintainability**: Makes it harder to use `dependency_mapper` as a standalone library
- **Risk**: Low runtime risk but architectural smell

## Proposed Solution

Move any shared functionality from `cli.deps` into the `dependency_mapper` package so the CLI only consumes the library.

### Suggested Approach

1. Identify what `dependency_mapper` imports from `cli.deps`
2. Move that functionality into `dependency_mapper` or a shared utility
3. Update `cli.deps` to import from `dependency_mapper` only
4. Verify with import cycle detection

## Impact Assessment

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

---

## Status

**Open** | Created: 2026-03-12 | Priority: P3
