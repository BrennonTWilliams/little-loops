---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# ENH-694: Unused file read in `find_existing_issue` Pass 1

## Summary

In Pass 1 of `find_existing_issue`, each matching issue file is read via `issue_path.read_text()` at line 191, but the resulting `content` variable is never used — the type-match check on the next line only uses the file path. The same file was already read internally by `search_issues_by_file_path`. Each matching file gets read twice with the second read discarded.

## Location

- **File**: `scripts/little_loops/issue_discovery/search.py`
- **Line(s)**: 189-217 (at scan commit: 3e9beea)
- **Anchor**: `in function find_existing_issue()`, Pass 1 loop

## Current Behavior

`content = issue_path.read_text(encoding="utf-8")` at line 191 reads the file, but `content` is never referenced. `_matches_issue_type` on line 192 only examines `str(issue_path)` and `config`.

## Expected Behavior

Remove the unused `content = issue_path.read_text(...)` line. If content is needed for future logic, thread it through from the single read in `search_issues_by_file_path`.

## Scope Boundaries

- Remove the unused read only; do not refactor the broader search flow

## Impact

- **Priority**: P4 - Minor performance waste, no correctness impact
- **Effort**: Small - Delete one line
- **Risk**: Low - Removing dead code
- **Breaking Change**: No

## Labels

`enhancement`, `performance`, `issue-discovery`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4
