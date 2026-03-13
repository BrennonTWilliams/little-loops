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
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- Confirmed: `dependency_mapper/__init__.py` line 95 does `from little_loops.cli.deps import main_deps`, and `cli/deps.py` line 65 imports from `little_loops.dependency_mapper`. Mutual import is present. Runtime imports don't fail currently (Python resolves the cycle), but the architectural inversion (library depending on CLI) is confirmed as described.

## Status

**Open** | Created: 2026-03-12 | Priority: P3
