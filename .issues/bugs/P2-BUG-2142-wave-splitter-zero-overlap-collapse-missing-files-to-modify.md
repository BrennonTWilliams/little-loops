---
id: BUG-2142
type: BUG
priority: P2
captured_at: '2026-06-14T03:50:03Z'
discovered_date: '2026-06-14'
discovered_by: capture-issue
status: open
relates_to:
- BUG-511
- ENH-1061
- ENH-301
confidence_score: 88
outcome_confidence: 80
score_complexity: 20
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 20
---

# BUG-2142: Wave splitter zero-overlap collapse when `### Files to Modify` section absent

## Summary

`extract_file_hints()` in `file_hints.py` only parses `### Files to Modify` and
`### Files Changed` structured sections to populate the `files` set. When issues lack
these sections entirely, `files` is empty → the issue appears to have zero file overlap
with any other issue → `refine_waves_for_contention()` keeps all such issues in a single
parallel wave → workers collide with rebase conflicts.

The dependency mapper's full-text scan does detect overlaps and displays them, but its
output is never fed into wave scheduling. This means the only protection against parallel
collision — file hint contention detection — silently fails for all issues without the
section header.

## Current Behavior

`_extract_write_target_files()` in `file_hints.py:287` scans only lines within
`### Files to Modify` or `### Files Changed` section boundaries. Issues that use
prose descriptions, `## Technical Details`, or no file listing at all return
`files = set()`.

`refine_waves_for_contention()` in `dependency_graph.py:388` then sees no overlap
between these issues and places them all in wave 1. With 4 parallel workers all
touching the same files (e.g., `Table.tsx`, `DragContext.tsx`), 3 of 4 workers
fail on rebase.

**Observed in the field (2026-06-13, `cards` project, Run 1):**
- 14 issues, none with `### Files to Modify` sections
- Wave splitter saw zero overlaps → 14 issues in wave 1
- 4 parallel workers → 3 failed with rebase conflicts immediately
- Adding `### Files to Modify` to all 14 issue files fixed detection for Run 2

## Expected Behavior

When `### Files to Modify` is absent, the wave scheduler should either:
- Fall back to the dependency mapper's full-text scan results for that issue, OR
- Warn at `ll-sprint show` time that N issues lack file hints and may collide, OR
- Treat issues with empty file sets as `unknown overlap` and serialize them conservatively

## Root Cause

- **File**: `scripts/little_loops/parallel/file_hints.py`
- **Lines**: 287–340 (`extract_file_hints()`, `_extract_write_target_files()`)
- **Anchor**: function `_extract_write_target_files`

The function uses a section-header state machine that only activates on
`### Files to Modify` or `### Files Changed`. Lines outside these sections are ignored.
There is no fallback for issues that omit the section.

The dependency mapper (`dependency_graph.py:172`, `get_execution_waves()`) runs its
own full-text scan and produces confident overlap annotations, but these are only
surfaced in the display layer — they are never used to add edges or modify wave
assignments.

## Proposed Fix

Two complementary fixes:

1. **Warning at plan time**: In `ll-sprint show` / `ll-sprint run --dry-run`,
   list any issues with empty `FileHints.files` sets and warn that contention
   detection is blind to them.

2. **Conservative serialization**: In `refine_waves_for_contention()`, treat issues
   with `len(hints.files) == 0 and len(hints.directories) == 0` as `unknown` rather
   than `no overlap`. Conservatively keep them in separate waves or flag them for
   manual review. This avoids false-confidence in the no-hint case.

3. **(Long-term)**: Feed dependency mapper full-text scan output into wave edge
   construction so HIGH-confidence overlaps detected in prose are respected by the
   scheduler even when structured sections are absent.

## Files to Modify

- `scripts/little_loops/parallel/file_hints.py` — `_extract_write_target_files()`, `extract_file_hints()`
- `scripts/little_loops/dependency_graph.py` — `refine_waves_for_contention()` (conservative no-hint case)
- `scripts/little_loops/cli/sprint/run.py` — `ll-sprint show` warning for hint-less issues

## Impact

- **Severity**: High — causes silent parallel collapse and rebase conflicts on every sprint with issues missing `### Files to Modify`
- **Effort**: Medium — warning is easy; conservative serialization requires touching wave logic
- **Risk**: Low for warning; Low-Medium for conservative serialization (may over-serialize)
- **Breaking Change**: No

## Related Issues

- BUG-511 (done): File hint overlap detection too aggressive (opposite problem — this is too permissive)
- ENH-1061 (done): Scope directory hints to `### Files to Modify` section only
- ENH-301 (done): Integrate dependency mapper into sprint — but full-text scan still not wired to scheduling

## Session Log
- `/ll:capture-issue` - 2026-06-14T03:50:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Status
**Open** | Priority: P2
