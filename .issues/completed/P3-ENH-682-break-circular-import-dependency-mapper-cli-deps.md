---
discovered_commit: 3e9beea
discovered_branch: main
discovered_date: 2026-03-12
discovered_by: audit-architecture
focus_area: integration
confidence_score: 93
outcome_confidence: 76
---

# ENH-682: Break circular import: dependency_mapper <-> cli.deps

## Summary

Architectural issue found by `/ll:audit-architecture`.

Circular dependency between library and CLI layer:
`dependency_mapper` -> `cli.deps` -> `dependency_mapper`

## Current Behavior

`dependency_mapper/__init__.py` contains a `main()` backward-compat function that performs a deferred import from `little_loops.cli.deps`, and `cli/deps.py` imports from `little_loops.dependency_mapper`. This creates a mutual dependency where a library module depends on a CLI module, violating the architectural boundary.

## Expected Behavior

`dependency_mapper` should have zero imports from CLI modules. Only `cli.deps` should import from `dependency_mapper`. The `main()` backward-compat alias in `dependency_mapper/__init__.py` should be removed or replaced with a non-CLI-dependent implementation.

## Motivation

Library modules (`dependency_mapper`) should never depend on CLI modules (`cli.deps`). This violates the clean layering where CLI depends on library but not vice versa. The cycle prevents using `dependency_mapper` as a standalone library and makes the CLI/library boundary undefined.

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

## Scope Boundaries

- Only move or reorganize shared functionality; no behavior changes
- `cli.deps` public interface must remain intact after the refactor
- Do not modify `dependency_mapper`'s public API

## Implementation Steps

1. Identify what `dependency_mapper` imports from `cli.deps`
2. Move that shared functionality into `dependency_mapper` or a new shared utility module
3. Update `cli.deps` to import from `dependency_mapper` only (not vice versa)
4. Verify with import cycle detection and `python -m pytest`

## Integration Map

- **Modified**: `scripts/little_loops/dependency_mapper/__init__.py`, `scripts/little_loops/cli/deps.py`
- **Direction after fix**: `cli.deps` → `dependency_mapper` (one-way only)

## Impact Assessment

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Session Log
- `/ll:ready-issue` - 2026-03-17T01:43:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f7f7c123-3ad1-4eb0-a435-1328b4b8fdaf.jsonl`
- `/ll:verify-issues` - 2026-03-15T00:11:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/623195d5-5e50-40d6-b2b9-5b105ad77689.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`

---

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- Confirmed: `dependency_mapper/__init__.py` line 95 does `from little_loops.cli.deps import main_deps`, and `cli/deps.py` line 65 imports from `little_loops.dependency_mapper`. Mutual import is present. Runtime imports don't fail currently (Python resolves the cycle), but the architectural inversion (library depending on CLI) is confirmed as described.

## Resolution

- **Date**: 2026-03-16
- **Status**: COMPLETE
- Removed `main()` backward-compat function and `"main"` from `__all__` in `dependency_mapper/__init__.py`
- Updated `scripts/tests/test_dependency_mapper.py` to import `main_deps as main` from `little_loops.cli.deps` directly
- `dependency_mapper` now has zero imports from CLI modules; only `cli.deps` imports from `dependency_mapper`
- Verified: importing `dependency_mapper` no longer loads `cli.deps`; all 100 tests pass

## Status

**Closed** | Created: 2026-03-12 | Closed: 2026-03-16 | Priority: P3
