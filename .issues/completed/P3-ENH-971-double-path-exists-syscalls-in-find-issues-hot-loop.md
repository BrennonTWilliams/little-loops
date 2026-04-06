---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 85
---

# ENH-971: `find_issues` makes double `Path.exists()` syscalls per file in hot loop

## Summary

`find_issues` iterates every `.md` file in an active issue directory and checks two `Path.exists()` syscalls per file — one for the completed path and one for the deferred path — to skip already-moved issues. `find_issues` is called on every `ll-auto`, `ll-parallel`, sprint run, and several CLI commands. Pre-materializing the completed and deferred filename sets as a `frozenset` before the loop replaces O(N) syscalls with O(1) membership tests.

## Location

- **File**: `scripts/little_loops/issue_parser.py`
- **Line(s)**: 638–661 (at scan commit: 96d74cda)
- **Anchor**: `in function find_issues`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/issue_parser.py#L638-L661)
- **Code**:
```python
for issue_file in issue_dir.glob("*.md"):
    completed_path = completed_dir / issue_file.name
    if completed_path.exists():        # syscall per file
        continue
    deferred_path = deferred_dir / issue_file.name
    if deferred_path.exists():         # syscall per file
        continue
```

## Current Behavior

For a project with 200 active issues, each `find_issues` call performs up to 400 `stat` syscalls (2 per file). `find_issues` is called by `IssuePriorityQueue.scan_issues`, `SprintManager.load_issue_infos`, `cmd_sequence`, and multiple CLI commands, so the overhead compounds across a typical run.

## Expected Behavior

The completed and deferred filename sets are materialized once with a single `glob` before the loop. Each per-file check becomes an O(1) `frozenset` membership test.

## Motivation

`find_issues` sits on the critical path of `ll-auto`, `ll-parallel`, and sprint execution. Reducing 400 syscalls to 2 `glob` calls improves startup latency for every automated run, which compounds when `find_issues` is called repeatedly.

## Proposed Solution

```python
completed_names = (
    frozenset(p.name for p in completed_dir.glob("*.md"))
    if completed_dir.exists() else frozenset()
)
deferred_names = (
    frozenset(p.name for p in deferred_dir.glob("*.md"))
    if deferred_dir.exists() else frozenset()
)

for issue_file in issue_dir.glob("*.md"):
    if issue_file.name in completed_names:
        continue
    if issue_file.name in deferred_names:
        continue
    ...
```

The two `glob` calls read directory entries in a single OS call each, which is more cache-friendly than N individual `stat` calls.

## Scope Boundaries

- Only change the skip-check mechanism; do not alter filtering logic, sorting, or return value structure
- The `completed_dir.exists()` guard is needed since the directory may not exist on fresh projects

## Success Metrics

- `find_issues` on a 200-issue project should issue 2 directory reads (one for completed, one for deferred) instead of up to 400 stat calls for the skip checks

## API/Interface

N/A - No public API changes

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `find_issues`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/priority_queue.py:242` — `IssuePriorityQueue.scan_issues` calls `find_issues` directly
- `scripts/little_loops/issue_manager.py:791` — `IssueManager.__init__` calls `find_issues(self.config, self.category)`
- `scripts/little_loops/cli/issues/sequence.py:28` — `cmd_sequence` calls `find_issues(config, type_prefixes=type_prefixes)`
- `scripts/little_loops/cli/issues/next_issue.py:29` — calls `find_issues(config, skip_ids=...)`
- `scripts/little_loops/cli/issues/next_action.py:29` — calls `find_issues(config, skip_ids=...)`
- `scripts/little_loops/cli/issues/next_issues.py:27` — calls `find_issues(config)`
- `scripts/little_loops/cli/issues/refine_status.py:248` — calls `find_issues(config, type_prefixes=...)`
- `scripts/little_loops/cli/issues/impact_effort.py:188` — calls `find_issues(config, type_prefixes=...)`
- `scripts/little_loops/cli/deps.py:32` — calls `find_issues(config, only_ids=...)`

> **Note**: `SprintManager.load_issue_infos` does **not** call `find_issues`; it uses `IssueParser.parse_file` directly via `_find_issue_path`.

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/issue_parser.py:140-151` — `get_next_issue_number` pre-compiles a regex union before iterating files; same "compute-once outside loop" pattern in the same file
- `scripts/little_loops/issue_history/parsing.py:263-287` — `scan_completed_issues` pre-batches all git dates before the per-file loop via `_batch_completion_dates`, then does O(1) dict lookups per file — direct structural analogue
- `scripts/little_loops/parallel/file_hints.py:45-50` — `frozenset(config.exclude_common_files)` materialized once from config before use in set comprehensions
- `scripts/little_loops/workflow_sequence/analysis.py:441-461` — pre-computes entity sets via list comprehension outside a sliding-window loop with explicit comment explaining the intent

### Tests
- `scripts/tests/test_issue_parser.py:806` — `test_find_all_issues` — **passes unchanged**
- `scripts/tests/test_issue_parser.py:818` — `test_find_issues_by_category` — **passes unchanged**
- `scripts/tests/test_issue_parser.py:832` — `test_find_issues_with_skip_ids` — **passes unchanged**
- `scripts/tests/test_issue_parser.py:847` — `test_find_issues_sorted_by_priority` — **passes unchanged**
- `scripts/tests/test_issue_parser.py:863` — `test_find_issues_empty_category` — **passes unchanged**
- `scripts/tests/test_issue_parser.py:875-907` — `test_find_issues_skips_duplicates_in_completed` already covers the skip-completed behavior using real filesystem via `tmp_path`; **passes unchanged** after the refactor
- `scripts/tests/test_issue_parser.py:909-935` — `test_find_issues_skips_duplicates_in_deferred` — same, covers deferred; **passes unchanged**
- `scripts/tests/test_issue_parser.py:937` — `test_find_issues_only_ids_ordered` — **passes unchanged**
- `scripts/tests/test_issue_parser.py:959` — `test_find_issues_only_ids_set_uses_priority_sort` — **passes unchanged**
- `scripts/tests/test_issue_parser_fuzz.py:277` — `TestIssueParserFindIssuesFuzz.test_find_issues_handles_mixed_files` — Hypothesis fuzz test over real filesystem; **passes unchanged**
- `scripts/tests/test_issue_workflow_integration.py:133,152,429` — 3 `find_issues` call sites in integration tests using real filesystem; **all pass unchanged**
- `scripts/tests/test_priority_queue.py:649-704` — 4 `scan_issues` tests patch `find_issues` at the `priority_queue` module boundary and never reach the real implementation; **pass unchanged**
- New test to add: verify glob call count is reduced; model after `scripts/tests/test_issue_history_parsing.py:168-238` (`test_scan_completed_issues_single_git_log_call`) which patches the I/O function and asserts `called_once()`; patch `little_loops.issue_parser.Path.glob` and assert `call_count == 2` for the skip-check regardless of file count

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser_fuzz.py:277` — fuzz test; passes unchanged (listed above)
- `scripts/tests/test_issue_workflow_integration.py:133,152,429` — integration tests; pass unchanged (listed above)
- `scripts/tests/test_priority_queue.py:649-704` — mock-boundary tests; pass unchanged (listed above)
- 7 additional `TestFindIssues` unit tests at lines 806–977 not previously listed; all pass unchanged

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:654-684` — documents `find_issues` signature and usage; **no update needed** (function signature and return type unchanged)
- `docs/development/TROUBLESHOOTING.md:570,1001` — inline diagnostic snippets calling `find_issues(BRConfig(Path.cwd()))`; **no update needed** (call pattern unchanged)

### Configuration
- N/A

## Implementation Steps

1. In `scripts/little_loops/issue_parser.py`, at lines 639-641 (after `completed_dir`/`deferred_dir` are resolved), add frozenset pre-computation before the category loop:
   ```python
   completed_names = frozenset(p.name for p in completed_dir.glob("*.md")) if completed_dir.exists() else frozenset()
   deferred_names = frozenset(p.name for p in deferred_dir.glob("*.md")) if deferred_dir.exists() else frozenset()
   ```
2. Replace `completed_path = ...; if completed_path.exists()` / `deferred_path = ...; if deferred_path.exists()` (lines 656-661) with `if issue_file.name in completed_names` / `if issue_file.name in deferred_names`
3. Run existing tests: `python -m pytest scripts/tests/test_issue_parser.py -v -k "find_issues"` — all should pass unchanged
4. Add a new test in `scripts/tests/test_issue_parser.py` under `TestFindIssues`, following the mock pattern from `scripts/tests/test_issue_history_parsing.py:168-238`: patch `Path.glob` to count calls and assert only 2 `glob` calls are made for the skip-check regardless of file count

## Impact

- **Priority**: P3 — Hot path optimization; benefits every automated run and CLI command that calls `find_issues`
- **Effort**: Small — 6-line change before the loop
- **Risk**: Low — Logic-equivalent transformation; no change in return values
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `performance`, `captured`

## Resolution

- **Completed**: 2026-04-06
- **Solution**: Pre-materialized `completed_names` and `deferred_names` as `frozenset` before the category loop in `find_issues`. Replaced per-file `Path.exists()` calls with O(1) `in` membership tests.
- **Files Changed**: `scripts/little_loops/issue_parser.py` (6-line change), `scripts/tests/test_issue_parser.py` (new `test_find_issues_skip_check_uses_two_globs_not_stat_per_file`)

## Session Log
- `/ll:ready-issue` - 2026-04-06T21:14:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8aa967c-eaf9-442d-8599-474377c1b812.jsonl`
- `/ll:confidence-check` - 2026-04-06T23:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86cc90f6-dad7-44a0-bba5-c09e343e690a.jsonl`
- `/ll:wire-issue` - 2026-04-06T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5071c3bc-b6a1-4a9c-b8ff-fb3cdbc35a5d.jsonl`
- `/ll:refine-issue` - 2026-04-06T21:06:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5071c3bc-b6a1-4a9c-b8ff-fb3cdbc35a5d.jsonl`
- `/ll:format-issue` - 2026-04-06T21:02:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/372e180e-3c92-4d33-a2a3-bde54ba69314.jsonl`
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`
- `/ll:manage-issue` - 2026-04-06T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

## Status

**Completed** | Created: 2026-04-06 | Completed: 2026-04-06 | Priority: P3
