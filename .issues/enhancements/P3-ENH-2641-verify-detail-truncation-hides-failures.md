---
id: ENH-2641
type: ENH
priority: P3
status: open
captured_at: '2026-07-14T23:40:13Z'
discovered_date: 2026-07-14
discovered_by: capture-issue
relates_to:
- BUG-2640
- BUG-2614
---

# ENH-2641: verify-detail.txt truncation hides the real failure

## Summary

The epic-merge verify gate writes `verify-detail.txt` into the run dir as a blind
character-prefix of `test_cmd` output (capped at ~500 chars). For a pytest run that
begins with pytest-benchmark/xdist warnings, this cap captures **only the warnings**
and cuts off before the `FAILED …` short-summary lines — so the artifact records that
verify failed but not *why*. The run becomes undiagnosable from its own artifacts.

## Motivation

On run `sprint-refine-and-implement-20260714T180411` (EPIC-2370, see BUG-2640),
`verify-detail.txt` contained nothing but two `PytestBenchmarkWarning` blocks; the 9
actual `FAILED test_issues_cli.py::…` lines were truncated away. Diagnosing the false
negative required a full manual re-run of the suite (~71s) to see the real failures.
A better artifact would have surfaced the root cause immediately.

## Current Behavior

`verify-detail.txt` = first ~500 chars of combined stdout/stderr. When leading output
is warnings/banners, the substantive failure summary is dropped.

## Expected Behavior

The artifact should preserve the diagnostic tail of a pytest run — at minimum the
`=== short test summary info ===` / `FAILED …` block and the final
`N failed, M passed …` line. Options:
- Capture the **last** N lines (tail) rather than the first N chars, or
- Grep for and always include `FAILED`/`ERROR`/`short test summary` lines regardless
  of position, or
- Raise the cap and prefer the tail.

## Impact

Low severity but high friction: every failed verify is currently opaque, forcing a
manual re-run to learn what broke. Fixing this makes false negatives (like BUG-2640)
and true failures alike diagnosable directly from the run dir.

## Implementation Steps

1. Find where `verify-detail.txt` is written (the epic-merge verify path;
   `scripts/little_loops/parallel/orchestrator.py` verify helpers or the FSM
   finalize/merge states).
2. Change the capture to tail-based (or grep-for-failures) so the pytest summary is
   retained; keep a reasonable size bound.
3. Verify with a deliberately-failing suite that `FAILED` lines appear in the artifact.

## Acceptance Criteria

- [ ] `verify-detail.txt` includes the pytest `FAILED`/summary lines when the suite fails.
- [ ] Leading warnings no longer crowd out the failure summary.
- [ ] Size stays bounded (no unbounded full-log dump into the run dir).

## API/Interface

No public API change; internal artifact-capture behavior only.

## Session Log
- `/ll:capture-issue` - 2026-07-14T23:40:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bb11f3d4-9b5d-4067-814a-1a27441ae683.jsonl`

---

## Status

- **Status**: open
- **Priority**: P3
