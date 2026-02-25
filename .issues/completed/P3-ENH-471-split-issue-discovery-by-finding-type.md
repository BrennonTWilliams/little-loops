---
discovered_commit: 896c4ea858eb310d1a187c9f94e9368cf49a4f18
discovered_branch: main
discovered_date: 2026-02-24
discovered_by: audit-architecture
focus_area: large-files
confidence_score: 95
outcome_confidence: 86
---

# ENH-471: Split issue_discovery.py by finding type

## Summary

Architectural issue found by `/ll:audit-architecture`. The `issue_discovery.py` module is 954 lines with 19 top-level functions and 3 dataclasses, handling all issue finding/matching/deduplication logic in a single file.

## Current Behavior

The module `scripts/little_loops/issue_discovery.py` (954 lines) contains 2 dataclasses, 1 Enum, and 19 functions covering distinct responsibilities:
- **Search functions**: `search_issues_by_content`, `search_issues_by_file_path`, `_get_all_issue_files`
- **Matching/scoring**: `_normalize_text`, `_extract_words`, `_calculate_word_overlap`, match scoring logic
- **Completed issue extraction**: `_extract_fix_commit`, `_extract_files_changed`, `_extract_completion_date`
- **Regression detection**: `RegressionEvidence`, finding classification
- **Deduplication**: `FindingMatch` (dataclass), `MatchClassification` (Enum), dedup logic

## Expected Behavior

The `issue_discovery.py` module is split into an `issue_discovery/` package with focused sub-modules for search, matching, extraction, and classification. The public API remains unchanged via re-exports from `__init__.py`.

## Motivation

This enhancement would:
- Improve development velocity: 19 functions spanning search, matching, extraction, and classification are hard to navigate in a single file
- Reduce maintenance risk: changes to search logic can inadvertently affect matching/classification
- Improve code clarity: grouping related functions into focused modules

## Proposed Solution

Split into focused modules within an `issue_discovery/` package:

1. Create `issue_discovery/` package (convert from single module)
2. `issue_discovery/search.py` — Issue file search and content matching
3. `issue_discovery/matching.py` — Match scoring, deduplication, classification
4. `issue_discovery/extraction.py` — Completed issue metadata extraction
5. `issue_discovery/__init__.py` — Re-export public API
6. Update imports in dependent modules (`issue_manager.py`, `config.py`)

## Scope Boundaries

- **In scope**: Splitting `issue_discovery.py` into a package with sub-modules; updating imports
- **Out of scope**: Refactoring function internals, adding new search/matching features, changing function signatures

## Implementation Steps

1. Create `issue_discovery/` package directory
2. Group functions by domain (search, matching, extraction) and move to sub-modules
3. Move dataclasses to their respective modules
4. Update internal cross-references between relocated functions
5. Create `__init__.py` with re-exports of all public names
6. Update external callers to use re-exported imports
7. Run tests to verify no breakage

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_discovery.py` — convert to package

### Dependent Files (Callers/Importers)
- `scripts/tests/test_issue_discovery.py` — imports all public symbols and several private functions
- No production code directly imports `issue_discovery`; it is invoked via Claude tools only

### Similar Patterns
- `issue_history/` package — already uses sub-module pattern for analysis

### Tests
- `scripts/tests/` — existing issue_discovery tests should pass unchanged

### Documentation
- `docs/ARCHITECTURE.md` — references `issue_discovery.py` in module listing
- `docs/reference/API.md` — documents `little_loops.issue_discovery` module (path and example imports)
- `CONTRIBUTING.md` — references `issue_discovery.py` in module listing

### Configuration
- N/A

## Impact

- **Priority**: P3 — 954 lines with 19 functions spanning multiple domains
- **Effort**: Small-Medium — Pure functions with clean split points
- **Risk**: Low — Move functions + update imports; public API unchanged via re-exports
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Session Log
- `/ll:format-issue` - 2026-02-24 - auto-format batch
- `/ll:verify-issues` - 2026-02-24 - Corrected "3 dataclasses" to "2 dataclasses + 1 Enum"
- `/ll:ready-issue` - 2026-02-25 - Corrected Dependent Files (issue_manager.py removed, test_issue_discovery.py added); added docs to Documentation section

---

## Resolution

- **Completed**: 2026-02-25
- **Fix Commit**: TBD
- **Action**: refactor

### Summary

Split `scripts/little_loops/issue_discovery.py` (954 lines) into an
`issue_discovery/` package with three focused sub-modules:

- `matching.py` — `MatchClassification`, `RegressionEvidence`, `FindingMatch`, text helpers, `_matches_issue_type`
- `extraction.py` — git history analysis, `detect_regression_or_duplicate`, `_build_reopen_section`
- `search.py` — file search functions, `find_existing_issue`, `reopen_issue`, `update_existing_issue`
- `__init__.py` — re-exports all public + test-accessed private names

Public API unchanged. All 56 tests pass, mypy clean, ruff clean.

### Files Changed

- `scripts/little_loops/issue_discovery/` (new package, 4 files)
- `scripts/little_loops/issue_discovery.py` (deleted)
- `docs/ARCHITECTURE.md`
- `docs/reference/API.md`
- `CONTRIBUTING.md`

## Status

**Completed** | Created: 2026-02-24 | Completed: 2026-02-25 | Priority: P3
