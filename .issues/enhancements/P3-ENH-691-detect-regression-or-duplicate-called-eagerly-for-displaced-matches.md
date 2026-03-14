---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# ENH-691: `detect_regression_or_duplicate` called eagerly for displaced matches

## Summary

In `find_existing_issue` Passes 2 and 3, `detect_regression_or_duplicate` is called for every candidate that beats the current best score.

## Motivation

Each eager call forks two git subprocesses and reads a file — for intermediate candidates that will be displaced by a better match. This is wasteful work that scales with the number of completed issues in the repository. Deferring the call to after the loop matches how Pass 1 already works and eliminates the unnecessary subprocess overhead. Each call reads the issue file and forks two git subprocesses. If 5 completed issues compete for best match, that's 5 file reads and 10 subprocess forks — but only the final winner's result is used.

## Location

- **File**: `scripts/little_loops/issue_discovery/search.py`
- **Line(s)**: 219-276 (at scan commit: 3e9beea)
- **Anchor**: `in function find_existing_issue()`, Pass 2 and Pass 3 loops

## Current Behavior

`detect_regression_or_duplicate` is called eagerly for every candidate that beats the current best score. Each call involves one `read_text()`, one `git cat-file` subprocess, and one `git log` subprocess. Intermediate results are discarded when a better match is found.

## Expected Behavior

Regression analysis should be performed lazily — only for the final winning match after the loop completes, not for every intermediate candidate that is later displaced.

## Proposed Solution

In Passes 2 and 3, track `(issue_path, is_completed, match_score, matched_terms)` tuples without calling `detect_regression_or_duplicate`. After the loop, call it once on the best match. This matches how Pass 1 already works.

## Implementation Steps

1. In `find_existing_issue`, Pass 2 and Pass 3 loops: replace the eager `detect_regression_or_duplicate` call with tracking `(issue_path, is_completed, match_score, matched_terms)` tuples
2. After each loop ends, call `detect_regression_or_duplicate` once on the winning tuple
3. Verify behavior matches Pass 1's existing deferred pattern
4. Run existing tests to confirm no regression in issue discovery results

## Integration Map

- **Modified**: `scripts/little_loops/issue_discovery/search.py` — `find_existing_issue()` (lines 219-276), Pass 2 and Pass 3 loops
- **Unchanged**: `detect_regression_or_duplicate` implementation itself

## Scope Boundaries

- Only changes the call order of `detect_regression_or_duplicate`, not its implementation
- Does not affect the matching logic or scoring

## Impact

- **Priority**: P3 - Performance improvement for issue discovery, especially with large completed issue sets
- **Effort**: Small - Restructure loop to defer the function call
- **Risk**: Low - Same function call, just deferred to after loop completion
- **Breaking Change**: No

## Labels

`enhancement`, `performance`, `issue-discovery`

## Blocks

- ENH-694

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/issue_discovery/search.py` confirms `detect_regression_or_duplicate` is called at lines 199, 234, and 264. Lines 199 and 234 are inside comparison loops (Pass 2 and Pass 3) and are called each time a candidate beats the best match. Line 264 is Pass 3 (also eager). The pattern of calling this function for each intermediate winner — each incurring file reads and git subprocess forks — is confirmed.

## Session Log
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P3
