---
discovered_commit: 896c4ea858eb310d1a187c9f94e9368cf49a4f18
discovered_branch: main
discovered_date: 2026-02-24
discovered_by: audit-architecture
focus_area: large-files
---

# ENH-471: Split issue_discovery.py by finding type

## Summary

Architectural issue found by `/ll:audit-architecture`. The `issue_discovery.py` module is 954 lines with 19 top-level functions and 3 dataclasses, handling all issue finding/matching/deduplication logic in a single file.

## Current Behavior

The module `scripts/little_loops/issue_discovery.py` (954 lines) contains 3 dataclasses and 19 functions covering distinct responsibilities:
- **Search functions**: `search_issues_by_content`, `search_issues_by_file_path`, `_get_all_issue_files`
- **Matching/scoring**: `_normalize_text`, `_extract_words`, `_calculate_word_overlap`, match scoring logic
- **Completed issue extraction**: `_extract_fix_commit`, `_extract_files_changed`, `_extract_completion_date`
- **Regression detection**: `RegressionEvidence`, finding classification
- **Deduplication**: `FindingMatch`, `MatchClassification`, dedup logic

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
- `scripts/little_loops/issue_manager.py` — imports from issue_discovery
- TBD - use grep to find additional references: `grep -r "from.*issue_discovery import\|issue_discovery\." scripts/`

### Similar Patterns
- `issue_history/` package — already uses sub-module pattern for analysis

### Tests
- `scripts/tests/` — existing issue_discovery tests should pass unchanged

### Documentation
- N/A

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

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3
