---
discovered_commit: 3e9beea
discovered_branch: main
discovered_date: 2026-03-12
discovered_by: audit-architecture
focus_area: integration
---

# ENH-681: Break circular import: config <-> parallel.types <-> issue_parser

## Summary

Architectural issue found by `/ll:audit-architecture`.

Circular dependency detected on a critical import path:
`config` -> `parallel.types` -> `issue_parser` -> `config`

## Location

- **File**: `scripts/little_loops/config.py`, `scripts/little_loops/parallel/types.py`, `scripts/little_loops/issue_parser.py`
- **Module**: `little_loops.config`, `little_loops.parallel.types`, `little_loops.issue_parser`

## Finding

### Current State

Three core modules form a circular import chain:
- `config.py` is imported by `parallel/types.py` (for `BRConfig` or related types)
- `parallel/types.py` is imported by `issue_parser.py`
- `issue_parser.py` imports from `config.py` (via `frontmatter`)

This is the most concerning cycle as it involves the central configuration module.

### Impact

- **Development velocity**: New imports touching these modules risk import errors
- **Maintainability**: Circular imports make refactoring risky and reasoning about load order difficult
- **Risk**: Can cause `ImportError` at runtime depending on import order

## Proposed Solution

Extract shared types into a `core_types` module that all three can depend on without creating a cycle, or use lazy imports (`TYPE_CHECKING` guard) where the dependency is only needed for type annotations.

### Suggested Approach

1. Identify which specific symbols create the cycle (likely type annotations vs runtime)
2. If type-only: guard with `if TYPE_CHECKING:` and use string annotations
3. If runtime: extract shared types/interfaces to `little_loops/core_types.py`
4. Verify no import errors with `python -c "import little_loops"`

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
