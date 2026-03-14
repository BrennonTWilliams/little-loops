---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# ENH-694: Unused file read in `find_existing_issue` Pass 1

## Summary

In Pass 1 of `find_existing_issue`, each matching issue file is read via `issue_path.read_text()` at line 191, but the resulting `content` variable is never used — the type-match check on the next line only uses the file path. The same file was already read internally by `search_issues_by_file_path`. Each matching file gets read twice with the second read discarded.

## Motivation

Dead code that performs I/O is costly and misleading — it suggests content is used downstream when it isn't, and it doubles the file reads for every Pass 1 match. Removing it eliminates confusion for future readers and avoids unnecessary disk I/O.

## Location

- **File**: `scripts/little_loops/issue_discovery/search.py`
- **Line(s)**: 189-217 (at scan commit: 3e9beea)
- **Anchor**: `in function find_existing_issue()`, Pass 1 loop

## Current Behavior

`content = issue_path.read_text(encoding="utf-8")` at line 191 reads the file, but `content` is never referenced. `_matches_issue_type` on line 192 only examines `str(issue_path)` and `config`.

## Expected Behavior

Remove the unused `content = issue_path.read_text(...)` line. If content is needed for future logic, thread it through from the single read in `search_issues_by_file_path`.

## Implementation Steps

1. In `search.py`, locate `find_existing_issue` Pass 1 loop at line 191
2. Delete the line `content = issue_path.read_text(encoding="utf-8")`
3. Run `python -m pytest` to confirm no tests break

## Integration Map

- **Modified**: `scripts/little_loops/issue_discovery/search.py` — `find_existing_issue()` (line 191, Pass 1 loop)

## Scope Boundaries

- Remove the unused read only; do not refactor the broader search flow

## Impact

- **Priority**: P4 - Minor performance waste, no correctness impact
- **Effort**: Small - Delete one line
- **Risk**: Low - Removing dead code
- **Breaking Change**: No

## Labels

`enhancement`, `performance`, `issue-discovery`

## Blocked By

- ENH-691

## Session Log
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/issue_discovery/search.py` line 191 confirms `content = issue_path.read_text(encoding="utf-8")` is present in the Pass 1 loop. The `content` variable is assigned but never used — the following `_matches_issue_type` call (line 192) only uses `finding_type`, `issue_path`, and `config`. The unused read is confirmed.
