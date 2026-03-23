# ENH-840: Split workflow_sequence_analyzer.py into Package

**Date**: 2026-03-22
**Action**: improve
**Status**: In Progress

## Problem

`scripts/little_loops/workflow_sequence_analyzer.py` is 1,079 lines mixing four concerns:
1. Data models (5 dataclasses)
2. Analysis functions (pure logic)
3. IO/loading helpers (file I/O)
4. CLI entry point (`main()`)

## Solution

Convert to `workflow_sequence/` package with focused modules. Package named `workflow_sequence/` (not `workflow_sequence_analyzer/`) per issue spec.

## Architecture Decision: Circular Import Resolution

The original code has implicit circular dependencies if split naively:
- `_link_sessions`, `_parse_timestamps`, `_group_by_session` use `extract_entities`, `entity_overlap`, `_detect_handoff`, `SessionLink`
- `analyze_workflows` uses both IO (`_load_messages`, `_load_patterns`) and analysis functions

**Resolution**: Split as two clean layers:
- `io.py` — only pure file I/O (`_load_messages`, `_load_patterns`). No imports from `analysis.py`.
- `analysis.py` — everything else: constants, all functions including `_group_by_session`, `_parse_timestamps`, `_link_sessions`, `_cluster_by_entities`, etc., plus `analyze_workflows`. Imports from `io.py` and `models.py`.

This differs slightly from the issue's prescribed mapping (which put `_group_by_session`, `_parse_timestamps`, `_link_sessions` in `io.py`) but these are data-processing functions (not file I/O), and putting them in `io.py` would create circular imports.

## Module Map

| Module | Contents |
|--------|----------|
| `models.py` | `SessionLink`, `EntityCluster`, `WorkflowBoundary`, `Workflow`, `WorkflowAnalysis` |
| `io.py` | `_load_messages`, `_load_patterns` |
| `analysis.py` | All constants (regex, VERB_CLASSES, etc.), all analysis/grouping functions, `analyze_workflows` |
| `__init__.py` | Module docstring, `_DEFAULT_INPUT_PATH`, `main()`, re-exports, `__all__` |

## Import Graph (no cycles)

```
models.py  ← io.py
models.py  ← analysis.py ← io.py
models.py  ← analysis.py ← __init__.py
io.py      ← analysis.py ← __init__.py
```

## Files Changed

- **Create**: `scripts/little_loops/workflow_sequence/__init__.py`
- **Create**: `scripts/little_loops/workflow_sequence/models.py`
- **Create**: `scripts/little_loops/workflow_sequence/io.py`
- **Create**: `scripts/little_loops/workflow_sequence/analysis.py`
- **Delete**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Update**: `scripts/pyproject.toml` — entry point `little_loops.workflow_sequence:main`
- **Update**: `scripts/tests/test_workflow_sequence_analyzer.py` — import path

## Success Criteria

- [ ] All 4 package files created
- [ ] `python -m pytest scripts/tests/test_workflow_sequence_analyzer.py` passes
- [ ] `python -m pytest scripts/tests/` passes (no regressions)
- [ ] `ruff check scripts/` passes
- [ ] `python -m mypy scripts/little_loops/workflow_sequence/` passes
- [ ] Old `workflow_sequence_analyzer.py` deleted
- [ ] `ll-workflows` CLI entry point works (importable)
