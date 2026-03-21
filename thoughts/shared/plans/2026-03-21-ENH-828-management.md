# Plan: ENH-828 — `_find_test_file` resolves paths against project root

**Date**: 2026-03-21
**Issue**: ENH-828
**Action**: improve

## Summary

Thread `project_root: Path | None = None` through the call chain so `_find_test_file` checks path existence relative to the project root instead of the process CWD.

## Files to Modify

1. `scripts/little_loops/issue_history/parsing.py` — add `project_root` param to `_find_test_file`
2. `scripts/little_loops/issue_history/quality.py` — add `project_root` param to `analyze_test_gaps`; forward to both `_find_test_file` calls
3. `scripts/little_loops/issue_history/analysis.py` — pass `project_root` to `analyze_test_gaps`
4. `scripts/little_loops/cli/history.py` — pass `project_root` to `calculate_analysis`

## Phase 3a: Tests (Red)

New tests in `TestAnalyzeTestGaps` (`test_issue_history_advanced_analytics.py`):
- `test_project_root_anchors_path_existence`: tmp_path + real test file; change CWD away; pass `project_root=tmp_path`; assert test file found
- `test_none_project_root_falls_back_to_cwd`: tmp_path + real test file; `monkeypatch.chdir(tmp_path)`; call with `project_root=None`; assert found

## Phase 3b: Implementation

Follow existing `detect_config_gaps` pattern in quality.py:
```python
if project_root is None:
    project_root = Path.cwd()
```
Condition in `_find_test_file`:
```python
if (project_root / candidate).exists() if project_root else Path(candidate).exists()
```

## Phase 4: Verification

```bash
python -m pytest scripts/tests/test_issue_history_advanced_analytics.py::TestAnalyzeTestGaps -v
python -m pytest scripts/tests/ -v
ruff check scripts/
python -m mypy scripts/little_loops/
```

## Success Criteria

- [x] Tests written
- [ ] Red phase confirmed (tests fail before impl)
- [ ] Implementation complete
- [ ] All TestAnalyzeTestGaps tests pass
- [ ] Full test suite passes
- [ ] Lint and type checks pass
