# ENH-471: Split issue_discovery.py into Package

**Date**: 2026-02-25
**Issue**: ENH-471 — Split issue_discovery.py by finding type
**Action**: refactor

## Summary

Split `scripts/little_loops/issue_discovery.py` (954 lines) into a
`issue_discovery/` package with focused sub-modules. Public API unchanged
via re-exports from `__init__.py`.

## Package Structure

```
scripts/little_loops/issue_discovery/
├── __init__.py     # Re-exports all public + test-accessed names
├── matching.py     # Types (MatchClassification, RegressionEvidence, FindingMatch)
│                   # + text helpers + _matches_issue_type
├── extraction.py   # Git history analysis, detect_regression_or_duplicate,
│                   # _build_reopen_section
└── search.py       # File search, find_existing_issue, reopen_issue,
                    # update_existing_issue
```

## Dependency Direction

```
matching.py    ← no intra-package deps
extraction.py  ← matching.py
search.py      ← matching.py, extraction.py
__init__.py    ← all three
```

## Module Contents

### matching.py
- Classes: `MatchClassification`, `RegressionEvidence`, `FindingMatch`
- Functions: `_normalize_text`, `_extract_words`, `_calculate_word_overlap`,
  `_extract_line_numbers`, `_matches_issue_type`

### extraction.py
- Functions: `_extract_fix_commit`, `_extract_files_changed`,
  `_extract_completion_date`, `_commit_exists_in_history`,
  `_get_files_modified_since_commit`, `detect_regression_or_duplicate`,
  `_build_reopen_section`

### search.py
- Functions: `_get_all_issue_files`, `search_issues_by_content`,
  `search_issues_by_file_path`, `_get_category_from_issue_path`,
  `find_existing_issue`, `reopen_issue`, `update_existing_issue`

### __init__.py
Re-exports all public names + private helpers accessed by tests.

## Implementation Phases

- [x] Phase 1: Research complete
- [ ] Phase 2: Create matching.py
- [ ] Phase 3: Create extraction.py
- [ ] Phase 4: Create search.py
- [ ] Phase 5: Create __init__.py
- [ ] Phase 6: Delete issue_discovery.py
- [ ] Phase 7: Update documentation
- [ ] Phase 8: Run tests and verify

## Success Criteria

- [ ] All tests in `test_issue_discovery.py` pass unchanged
- [ ] `python -m mypy scripts/little_loops/` passes
- [ ] `ruff check scripts/` passes
- [ ] `from little_loops.issue_discovery import X` works for all 17 previously imported names
- [ ] docs/ARCHITECTURE.md, docs/reference/API.md, CONTRIBUTING.md updated
