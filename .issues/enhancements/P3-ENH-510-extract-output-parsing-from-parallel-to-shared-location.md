---
discovered_commit: 12420a2
discovered_branch: main
discovered_date: 2026-02-26
discovered_by: audit-architecture
focus_area: integration
---

# ENH-510: Extract `output_parsing` from `parallel/` to shared location

## Summary

Architectural issue found by `/ll:audit-architecture`. The `parse_ready_issue_output` function in `parallel/output_parsing.py` is imported by `issue_manager.py` (root level), creating the only runtime bidirectional coupling between the root package and the `parallel/` sub-package.

## Location

- **File**: `scripts/little_loops/parallel/output_parsing.py`
- **Line(s)**: 1–464 (entire file)
- **Module**: `little_loops.parallel.output_parsing`

## Finding

### Current State

`issue_manager.py` (Layer 3 in the dependency graph) imports `parse_ready_issue_output` from `parallel/output_parsing.py`:

```python
# issue_manager.py
from little_loops.parallel.output_parsing import parse_ready_issue_output
```

Meanwhile, `parallel/worker_pool.py` also imports from the same module:

```python
# parallel/worker_pool.py
from little_loops.parallel.output_parsing import parse_ready_issue_output
```

This creates bidirectional coupling:
- Root → Parallel: `issue_manager` → `parallel.output_parsing`
- Parallel → Root: `parallel.worker_pool` → `subprocess_utils`, `work_verification`

All other parallel→root imports are for foundational utilities (`subprocess_utils`, `work_verification`, `issue_parser`, `logger`), which is expected. But root→parallel creates a back-dependency that blurs package boundaries.

### Impact

- **Package boundaries**: The `parallel/` package cannot be cleanly treated as optional or independently testable since root-level code depends on it
- **Maintainability**: Changes to `parallel/output_parsing.py` can unexpectedly affect sequential processing (`issue_manager.py`)
- **Conceptual clarity**: Output parsing for Claude's response is not inherently a "parallel" concern — it's used by both sequential (`ll-auto`) and parallel (`ll-parallel`) workflows

## Proposed Solution

Move `output_parsing.py` from `parallel/` to root level:

```
# Before
scripts/little_loops/parallel/output_parsing.py

# After
scripts/little_loops/output_parsing.py
```

### Suggested Approach

1. Move `scripts/little_loops/parallel/output_parsing.py` → `scripts/little_loops/output_parsing.py`
2. Update imports in `issue_manager.py`:
   `from little_loops.output_parsing import parse_ready_issue_output`
3. Update imports in `parallel/worker_pool.py`:
   `from little_loops.output_parsing import parse_ready_issue_output`
4. Update re-export in `parallel/__init__.py` (if any)
5. Add backwards-compat re-export in `parallel/output_parsing.py` (optional, for transition)
6. Update test imports in `test_output_parsing.py`
7. Run full test suite to verify

## Scope Boundaries

- **In scope**: Moving the file, updating imports, verifying tests pass
- **Out of scope**: Changing the output_parsing logic itself, adding new functionality

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/output_parsing.py` — move to root
- `scripts/little_loops/output_parsing.py` — new location
- `scripts/little_loops/issue_manager.py` — update import
- `scripts/little_loops/parallel/worker_pool.py` — update import
- `scripts/little_loops/parallel/__init__.py` — remove re-export if present

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:12` — imports `parse_ready_issue_output`
- `scripts/little_loops/parallel/worker_pool.py:29` — imports `parse_ready_issue_output`
- `scripts/tests/test_output_parsing.py` — tests for the module

### Tests
- `scripts/tests/test_output_parsing.py` — update import paths

## Impact Assessment

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low (purely moving a module with import updates)
- **Breaking Change**: No (if backwards-compat re-export is added)

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-26 | Priority: P3

## Session Log
- `/ll:audit-architecture` - 2026-02-26 - Created from dependency mapping audit; bidirectional root↔parallel coupling finding
