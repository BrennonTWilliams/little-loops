---
discovered_date: 2026-03-04
discovered_by: analysis
---

# BUG-585: ll-sprint run Uses Worktrees for Serialized Contention Sub-waves

## Summary

`ll-sprint run` dispatches contention sub-waves (displayed as "serialized — file overlap" steps) through `ParallelOrchestrator` with git worktrees, contradicting the sequential in-place execution implied by the `ll-sprint show` display.

## Context

A sprint with 7 issues where one file-overlap conflict exists between FEAT-543 and ENH-541. `refine_waves_for_contention()` splits them into sub-waves: 6 issues in sub-wave 0, 1 issue in sub-wave 1. `ll-sprint show` renders both sub-waves under a single "Wave 1 (7 issues, serialized — file overlap): Step 1/7... Step 7/7" block, strongly implying sequential in-place execution. But `ll-sprint run` dispatched sub-wave 0 (6 issues, `len > 1`) to `ParallelOrchestrator` with `max_workers=2`, creating up to 6 git worktrees and running 2 in parallel.

## Current Behavior

Sub-wave dispatch logic at `run.py:288` branched solely on `len(wave) == 1`:
- Sub-wave with 1 issue → `process_issue_inplace()` (correct)
- Sub-wave with >1 issues → `ParallelOrchestrator` with worktrees (wrong for contention sub-waves)

`contention_notes` (computed at line 197 and used for display at lines 204–208) was never consulted in the dispatch logic.

## Root Cause

- **File**: `scripts/little_loops/cli/sprint/run.py`
- **Anchor**: dispatch branch at line 288 (`if len(wave) == 1:`)
- **Cause**: `contention_notes[wave_num - 1]` was already in scope but ignored during dispatch. The guard `len(wave) == 1` correctly handles the single-issue case but has no path for multi-issue contention sub-waves that must run sequentially.
- **Effect**: Contention sub-waves spun up worktrees and ran in parallel, producing behaviour inconsistent with the "serialized" display label and violating the intent of `refine_waves_for_contention()`.

## Expected Behavior

Any wave carrying a `WaveContentionNote` (i.e., any contention sub-wave, regardless of size) should run its issues sequentially in-place, matching the "serialized — file overlap" label shown by `ll-sprint show`.

## Integration Map

### Files Modified
- `scripts/little_loops/cli/sprint/run.py` — dispatch branch at line 288

### Key Supporting Code (unchanged)
- `scripts/little_loops/dependency_graph.py:340` — `refine_waves_for_contention()` produces `contention_notes`
- `scripts/little_loops/dependency_graph.py` — `WaveContentionNote` dataclass
- `scripts/little_loops/cli/sprint/_helpers.py:15` — `_render_execution_plan()` — why display implies sequential

## Implementation Steps

1. Before the `if len(wave) == 1:` check, compute `wave_note = contention_notes[wave_num - 1]` and derive `is_contention_subwave = wave_note is not None`
2. Change condition to `if len(wave) == 1 or is_contention_subwave:`
3. Convert the single-issue in-place body to a loop over `wave`, tracking per-issue success/failure with a `wave_failed` flag
4. Increment `failed_waves` once after the loop (not per failed issue), then log wave-level success or failure

## Impact

- **Priority**: P2 — Runtime behaviour contradicts display semantics; contention sub-waves bypass the file-overlap serialization that `refine_waves_for_contention()` exists to enforce
- **Effort**: Low — Single file, ~30-line change reusing existing patterns
- **Risk**: Low — Only affects waves with `WaveContentionNote`; true parallel waves (no contention note) are unaffected; all 135 sprint tests pass
- **Breaking Change**: No

## Labels

`bug`, `sprint`, `worktrees`, `contention`, `dispatch`

## Resolution

**Status**: Fixed | Resolved: 2026-03-04

### Changes Made

**`scripts/little_loops/cli/sprint/run.py`** (line 288):
- Added `wave_note` lookup from `contention_notes[wave_num - 1]` before the dispatch branch
- Changed dispatch condition from `if len(wave) == 1:` to `if len(wave) == 1 or is_contention_subwave:`
- Converted single-issue in-place body to a `for issue in wave:` loop with per-issue success/failure tracking
- Added `wave_failed` flag; `failed_waves` incremented once after the loop; wave-level success/failure logged after all issues complete
- `_save_sprint_state` and shutdown check remain in place after the loop, unchanged

### Root Cause Confirmed

`contention_notes` was computed at line 197 and used for the display log (lines 204–208) but was never consulted in the dispatch logic. The `len(wave) == 1` guard was the sole criterion, causing all multi-issue contention sub-waves to be routed to `ParallelOrchestrator`.

### Verification

- `python -m pytest scripts/tests/ -k sprint` — 135 passed, 0 failures
- True parallel waves (no `WaveContentionNote`) continue to use `ParallelOrchestrator` unchanged

## Session Log
- implementation - 2026-03-04 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e36e758-afb4-4a9c-84f7-b17aa3b11a27.jsonl`

---
## Status
**Fixed** | Resolved: 2026-03-04
