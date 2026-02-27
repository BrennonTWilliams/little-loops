# ENH-512: Remove redundant runtime overlap detection layer

## Summary

Disable runtime overlap detection (`OverlapDetector`) in the sprint runner path since `refine_waves_for_contention()` already guarantees no overlapping issues run concurrently within the same wave.

## Research Findings

- Sprint runner calls `refine_waves_for_contention()` at `run.py:171`, which uses `extract_file_hints()` + `FileHints.overlaps_with()` to split waves via greedy graph coloring
- Sprint runner then passes `overlap_detection=True` at `run.py:306`, creating a redundant `OverlapDetector` in the orchestrator that uses the **identical** `FileHints.overlaps_with()` pipeline
- Standalone `ll-parallel` does NOT use wave splitting, so it needs the runtime `OverlapDetector` (opt-in via `--overlap-detection`)
- `ParallelConfig.overlap_detection` defaults to `False` already in `types.py:342`

## Changes

### 1. `scripts/little_loops/cli/sprint/run.py` (line 306)
- Change `overlap_detection=True` to `overlap_detection=False`
- Add comment: wave splitting via `refine_waves_for_contention()` already handles overlap

### 2. `scripts/tests/test_sprint_integration.py` (lines 415-481)
- Update `test_sprint_enables_overlap_detection` test:
  - Rename to `test_sprint_disables_runtime_overlap_detection`
  - Update docstring to reflect new behavior
  - Assert `overlap_detection is False` instead of `True`
  - Keep `serialize_overlapping is True` assertion (default value, unchanged)

## No Changes Needed
- `cli/parallel.py` — standalone parallel keeps `--overlap-detection` opt-in (default False)
- `orchestrator.py` — respects the flag, no changes needed
- `types.py` — `ParallelConfig` default is already `False`
- `test_orchestrator.py` — tests orchestrator behavior independently

## Risk Assessment
- **Behavioral change**: None for sprint path (wave splitting already prevented overlaps)
- **Standalone parallel**: Unaffected (different code path)
- **Breaking change**: No
