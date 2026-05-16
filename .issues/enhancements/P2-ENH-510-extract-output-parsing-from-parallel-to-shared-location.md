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

## Current Behavior

`issue_manager.py` (root level) imports `parse_ready_issue_output` from `parallel/output_parsing.py`, creating bidirectional coupling between the root package and the `parallel/` sub-package. See [Finding](#finding) for details.

## Expected Behavior

`output_parsing.py` should live at the root package level (`scripts/little_loops/output_parsing.py`) since it serves both sequential and parallel workflows. See [Proposed Solution](#proposed-solution) for the migration plan.

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
2. Update module docstring to describe shared purpose (follow `work_verification.py` pattern: name both `ll-auto` and `ll-parallel` as consumers)
3. Update import in `issue_manager.py:33`:
   `from little_loops.output_parsing import parse_ready_issue_output`
4. Update import in `parallel/worker_pool.py:24`:
   `from little_loops.output_parsing import parse_ready_issue_output`
5. Delete `parallel/output_parsing.py` entirely (no backwards-compat shim)
6. Add exports to `scripts/little_loops/__init__.py`:
   - `parse_ready_issue_output` and `parse_manage_issue_output` in `__all__`
   - Follow existing `# output_parsing` comment grouping convention
7. Update test imports:
   - `test_output_parsing.py:5` — top-level import block
   - `test_issue_manager.py:83,160,242,285` — 4 inline imports
   - `test_workflow_integration.py:348` — 1 inline import
8. Update documentation references:
   - `docs/reference/API.md:1927,1960,2638` — module path and import examples
   - `docs/ARCHITECTURE.md:243` — move file in directory tree
   - `CONTRIBUTING.md:235` — move file in directory tree
   - `docs/research/claude-cli-integration-mechanics.md:168,253` — update paths
9. Run full test suite: `python -m pytest scripts/tests/ -v`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Zero internal dependencies**: `output_parsing.py` imports only `re` and `typing` from stdlib — no `little_loops` imports at all. Moving to root creates zero circular dependency risk.
- **Direct precedent**: `work_verification.py` was extracted from `parallel/` to root using the same pattern. Its docstring explicitly names both consumers (`ll-auto` and `ll-parallel`). Follow this precedent.
- **Not re-exported from parallel**: `parallel/__init__.py` does NOT re-export `output_parsing` — no cleanup needed there.
- **5 public functions**: `parse_sections`, `parse_validation_table`, `parse_status_lines`, `parse_ready_issue_output`, `parse_manage_issue_output` — all move together.
- **Cross-issue dependency**: ENH-470 (refactor parallel god classes) at `.issues/enhancements/P4-ENH-470-refactor-parallel-god-classes.md:132` explicitly recommends extracting `output_parsing` to root first before proceeding.

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
- `scripts/little_loops/issue_manager.py:33` — top-level import of `parse_ready_issue_output`; used at lines 323, 379
- `scripts/little_loops/parallel/worker_pool.py:24` — top-level import of `parse_ready_issue_output`; used at line 301
- `scripts/tests/test_output_parsing.py:5` — imports all 5 public functions
- `scripts/tests/test_issue_manager.py:83,160,242,285` — inline imports of `parse_ready_issue_output`
- `scripts/tests/test_workflow_integration.py:348` — inline import of `parse_ready_issue_output`

### Tests
- `scripts/tests/test_output_parsing.py` — update top-level import block (line 5)
- `scripts/tests/test_issue_manager.py` — update 4 inline imports (lines 83, 160, 242, 285)
- `scripts/tests/test_workflow_integration.py` — update 1 inline import (line 348)

### Documentation
- `docs/reference/API.md:1927,1960,2638` — module path and import examples
- `docs/ARCHITECTURE.md:243` — directory tree listing
- `CONTRIBUTING.md:235` — directory tree listing
- `docs/research/claude-cli-integration-mechanics.md:168,253` — source path references

## Impact

- **Severity**: Medium
- **Effort**: Small-Medium (9 files to update imports + 4 doc files; more than originally scoped)
- **Risk**: Low (zero internal dependencies; purely mechanical import path changes)
- **Breaking Change**: No — clean break with all imports updated atomically; no external consumers
- **Unblocks**: ENH-470 (refactor parallel god classes)

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

---

## Resolution

**Completed** on 2026-03-01.

Moved `output_parsing.py` from `parallel/` to root package level, eliminating bidirectional coupling between root and parallel sub-package. Updated all imports (2 production, 6 test locations), added exports to `__init__.py`, and updated 4 documentation files. All 3030 tests pass, lint and type checks clean.

### Files Changed
- `scripts/little_loops/parallel/output_parsing.py` → `scripts/little_loops/output_parsing.py` (moved + docstring updated)
- `scripts/little_loops/__init__.py` — added `output_parsing` exports
- `scripts/little_loops/issue_manager.py` — updated import path
- `scripts/little_loops/parallel/worker_pool.py` — updated import path + sort order
- `scripts/tests/test_output_parsing.py` — updated import path + docstring
- `scripts/tests/test_issue_manager.py` — updated 4 inline imports
- `scripts/tests/test_workflow_integration.py` — updated 1 inline import
- `docs/reference/API.md` — updated 3 path references
- `docs/ARCHITECTURE.md` — updated directory tree
- `CONTRIBUTING.md` — updated directory tree
- `docs/research/claude-cli-integration-mechanics.md` — updated 2 path references

## Status

**Completed** | Created: 2026-02-26 | Completed: 2026-03-01 | Priority: P2

## Session Log
- `/ll:audit-architecture` - 2026-02-26 - Created from dependency mapping audit; bidirectional root↔parallel coupling finding
- `/ll:refine-issue` - 2026-03-01 - `f62210c4-549d-4a28-a330-5f7afebd68f9.jsonl`
- `/ll:manage-issue` - 2026-03-01 - Implemented: moved file, updated all imports and docs
