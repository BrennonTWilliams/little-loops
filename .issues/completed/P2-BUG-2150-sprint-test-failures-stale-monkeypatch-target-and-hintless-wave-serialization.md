---
id: BUG-2150
type: bug
priority: P2
status: done
title: "Sprint test failures: stale monkeypatch target and hintless-wave serialization"
labels: [testing, sprint, regression]
completed_date: 2026-06-14
---

## Summary

21 test failures introduced by two independent changes in recent commits:

1. `_run_issue_with_wall_clock_timeout` wrapper (commit `f5eb703b`) made `process_issue_inplace` in `run.py` a module-level import, so tests that patched `little_loops.issue_manager.process_issue_inplace` stopped intercepting calls — the sprint runner called the real `claude` CLI instead of the mock.

2. Conservative wave serialization (commit `569c00e4`) split hintless issues into sequential sub-waves, so `ParallelOrchestrator` was never invoked in tests whose fixture issues lacked `### Files to Modify` sections.

A third independent failure: doc-count assertions in `test_wiring_guides_and_meta.py` still checked for `"37 skills"` after docs were updated to `"38 skills"`.

## Current Behavior

- 17 sprint tests call the real `claude` CLI during test runs because the monkeypatch targeting `little_loops.issue_manager.process_issue_inplace` no longer intercepts the call path.
- `test_wave_parallel_config_passes_clean_start` and 6 `TestMultiWaveExecution`/`TestErrorRecovery` tests never reach `ParallelOrchestrator` because fixture issues are serialized into single-issue sub-waves.
- 4 `test_wiring_guides_and_meta` tests fail because the needle `"37 skills"` is absent from docs that now say `"38"`.

## Expected Behavior

All 21 tests pass with fast mocks; no real `claude` subprocess is spawned.

## Root Causes

| # | Root cause | Introduced by |
|---|---|---|
| 1 | `_run_issue_with_wall_clock_timeout` uses `process_issue_inplace` from `run.py`'s module namespace, not from `issue_manager`. Patching the latter doesn't intercept the call. | `f5eb703b` |
| 2 | Hintless issues (no `### Files to Modify`) in the same wave are given synthetic conflict edges, so the greedy coloring places each in its own sub-wave. Test fixtures didn't include file hints. | `569c00e4` |
| 3 | Docs updated skill count to 38; test assertions not updated to match. | Prior session |

## Fix

### `scripts/little_loops/cli/sprint/run.py`
- Removed redundant `from little_loops.issue_manager import process_issue_inplace` inside the sequential-retry block (line 533). The function is already imported at module level; the local re-import prevented monkeypatching from covering the retry path.

### `scripts/tests/test_sprint.py` and `scripts/tests/test_sprint_integration.py`
- Changed all 25 monkeypatch targets from `"little_loops.issue_manager.process_issue_inplace"` to `"little_loops.cli.sprint.run.process_issue_inplace"` so patches intercept the module-level binding that `_run_issue_with_wall_clock_timeout` uses.
- Added non-overlapping `### Files to Modify` sections (e.g. `- src/bug001.py`, `- src/feat002.py`) to fixture issue content in three setup helpers (`TestSprintWaveCleanStart._setup_multi_issue_sprint`, `TestMultiWaveExecution._setup_multi_wave_project`, `TestErrorRecovery._setup_error_recovery_project`) so the wave splitter keeps parallel-eligible issues together.

### `scripts/tests/test_wiring_guides_and_meta.py`
- Updated 4 needle strings from `"37 skills"` / `"37 skill definitions"` / `"# 37 skill definitions"` to the corresponding `38` values to match current doc content.

## Verification

```
python -m pytest scripts/tests/test_sprint.py scripts/tests/test_sprint_integration.py scripts/tests/test_wiring_guides_and_meta.py -q
# 0 failed, all 21 previously-failing tests now pass
```

Full suite: 11418 passed, 7 skipped → 0 failures in `test_sprint*` and `test_wiring_guides_and_meta`.
