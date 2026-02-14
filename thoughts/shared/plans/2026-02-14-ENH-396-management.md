# ENH-396: Relabel "file contention" to "file overlap"

**Issue**: P4-ENH-396-relabel-sprint-show-file-contention-to-file-overlap.md
**Action**: improve
**Date**: 2026-02-14

## Research Findings

All references to "file contention" verified in codebase. Changes are display-only — internal identifiers (`refine_waves_for_contention`, `WaveContentionNote`, `contention_notes`) are explicitly out of scope per issue.

## Changes

### 1. sprint.py — Display string (line 303)
- `"file contention"` → `"file overlap"` in wave header

### 2. sprint.py — Health summary (line 491)
- `"contention serialized"` → `"overlap serialized"` in health summary suffix

### 3. sprint.py — Comments (lines 301, 335, 387, 962)
- Update comments referencing "file contention" to "file overlap"

### 4. dependency_graph.py — Docstrings and log messages (lines 22, 342, 422)
- Update docstring on `WaveContentionNote` class
- Update docstring on `refine_waves_for_contention` function
- Update logger.info message

### 5. test_cli.py — Test assertions (lines 1110, 1130, 1168-1169, 1268)
- Update `"file contention"` assertions to `"file overlap"`
- Update `"contention serialized"` assertion to `"overlap serialized"`
- Update test docstrings/comments for terminology consistency

### 6. test_dependency_graph.py — Test docstring (line 674)
- Update comment referencing "file contention"

## Success Criteria

- [ ] All user-facing "file contention" strings replaced with "file overlap"
- [ ] Health summary "contention serialized" replaced with "overlap serialized"
- [ ] Comments/docstrings updated for consistency
- [ ] Tests pass
- [ ] Lint passes
- [ ] Type check passes
