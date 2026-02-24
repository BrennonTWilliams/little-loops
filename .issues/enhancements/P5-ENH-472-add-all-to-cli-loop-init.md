---
discovered_commit: 896c4ea858eb310d1a187c9f94e9368cf49a4f18
discovered_branch: main
discovered_date: 2026-02-24
discovered_by: audit-architecture
focus_area: organization
---

# ENH-472: Add __all__ to cli/loop/__init__.py

## Summary

Architectural issue found by `/ll:audit-architecture`. The `cli/loop/__init__.py` is the only package init file missing an explicit `__all__` export list. All other 5 packages define `__all__`.

## Current Behavior

Package `__all__` status across the codebase:
- `little_loops/__init__.py` — HAS `__all__`
- `parallel/__init__.py` — HAS `__all__`
- `issue_history/__init__.py` — HAS `__all__`
- `cli/__init__.py` — HAS `__all__`
- `fsm/__init__.py` — HAS `__all__`
- **`cli/loop/__init__.py` — MISSING `__all__`**

Wildcard imports (`from little_loops.cli.loop import *`) may export unintended names.

## Expected Behavior

`cli/loop/__init__.py` defines an `__all__` list consistent with the other 5 packages, listing only the intended public API.

## Motivation

This enhancement would:
- Maintain consistency: all other packages define `__all__`, making this the sole exception
- Prevent accidental exports: wildcard imports may include unintended names
- Effort is minimal for a small consistency win

## Proposed Solution

Add `__all__` to `cli/loop/__init__.py` listing the public API:

1. Review which names from `cli/loop/__init__.py` are imported by other modules
2. Add `__all__` with those names
3. Verify no existing `from little_loops.cli.loop import *` usage breaks

## Scope Boundaries

- **In scope**: Adding `__all__` to `cli/loop/__init__.py`
- **Out of scope**: Refactoring the loop CLI package, adding new exports, changing other packages

## Implementation Steps

1. Identify public names exported by `cli/loop/__init__.py`
2. Check what other modules import from `cli.loop`
3. Add `__all__` list with the identified public names
4. Run tests to verify no breakage

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `__all__`

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "from.*cli.loop import\|cli\.loop\." scripts/`

### Similar Patterns
- All other `__init__.py` files in the package — follow their `__all__` format

### Tests
- N/A — adding `__all__` shouldn't break existing imports

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P5 — Consistency improvement with minimal runtime impact
- **Effort**: Small — Add a few lines
- **Risk**: Low — Additive change
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `auto-generated`

## Session Log
- `/ll:format-issue` - 2026-02-24 - auto-format batch

---

## Status

**Open** | Created: 2026-02-24 | Priority: P5
