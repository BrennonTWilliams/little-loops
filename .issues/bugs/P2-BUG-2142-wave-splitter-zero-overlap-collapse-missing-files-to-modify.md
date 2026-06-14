---
id: BUG-2142
type: BUG
priority: P2
captured_at: '2026-06-14T03:50:03Z'
completed_at: '2026-06-14T05:13:36Z'
discovered_date: '2026-06-14'
discovered_by: capture-issue
status: done
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

## Steps to Reproduce

1. Create a sprint with issues that lack `### Files to Modify` sections (use prose descriptions or `## Technical Details` instead)
2. Run `ll-sprint show` to view the wave plan — observe all hint-less issues land in wave 1
3. Run `ll-sprint run` with 2+ parallel workers (`--workers 2`)
4. Observe rebase conflicts as workers collide on the same files that the wave scheduler thought were non-overlapping

**Repro shortcut (field-confirmed):** Run any sprint where 10+ issues have no `### Files to Modify` section — the wave splitter will place them all in wave 1, and 3+ workers will hit rebase conflicts immediately.

## Impact

- **Severity**: High — causes silent parallel collapse and rebase conflicts on every sprint with issues missing `### Files to Modify`
- **Effort**: Medium — warning is easy; conservative serialization requires touching wave logic
- **Risk**: Low for warning; Low-Medium for conservative serialization (may over-serialize)
- **Breaking Change**: No

## Related Issues

- BUG-511 (done): File hint overlap detection too aggressive (opposite problem — this is too permissive)
- ENH-1061 (done): Scope directory hints to `### Files to Modify` section only
- ENH-301 (done): Integrate dependency mapper into sprint — but full-text scan still not wired to scheduling

## Labels

`sprint`, `wave-splitter`, `parallel`, `file-hints`, `scheduling`

## Resolution

**Fixed** (2026-06-14)

Implemented two complementary fixes per the proposed solution:

1. **Conservative serialization** (`dependency_graph.py`): Added `has_unknown_hints: bool = False` field to `WaveContentionNote`. In `refine_waves_for_contention()`, after the pairwise file-overlap loop, a new block identifies all issues with no file OR directory hints (`not hints.files and not hints.directories`) and adds synthetic conflict edges between every pair of such issues. The greedy graph coloring then naturally places each hintless issue in its own sub-wave, preventing parallel collision.

2. **Warning at plan time** (`cli/sprint/_helpers.py`, `show.py`, `run.py`):
   - `_render_execution_plan()` now shows `"serialized — unknown file hints"` (instead of `"file overlap"`) when the split was caused entirely by missing hints, and appends `"Tip: add '### Files to Modify' sections to enable precise overlap detection"`.
   - `_render_health_summary()` reflects unknown-hint serialization in the suffix: `"serialized (missing file hints)"` or `"serialized (overlap + missing file hints)"`.
   - `ll-sprint run` emits a logger warning when any sub-wave was produced by conservative serialization.

## Session Log
- `/ll:manage-issue` - 2026-06-14T05:13:36Z
- `/ll:ready-issue` - 2026-06-14T04:57:56 - `97c87f48-a008-4f09-b42a-29ebade6da2e.jsonl`
- `/ll:capture-issue` - 2026-06-14T03:50:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Status
**Done** | Priority: P2
