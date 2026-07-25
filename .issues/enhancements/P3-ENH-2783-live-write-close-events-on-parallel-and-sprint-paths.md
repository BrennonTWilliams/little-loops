---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:44Z
discovered_by: scan-codebase
relates_to: [ENH-1686]
---

# ENH-2783: Parallel/sprint issue-close events are not live-written to the history event bus

## Summary

ENH-1686 (done) added live-writing of issue-close events to `.ll/history.db`,
but the parallel-worker path (`ll-parallel`) and sprint sequential path
(`ll-sprint`) were left out — five `TODO(ENH-1686)` sites mark closures on
those paths that still bypass the live event write, so those closures only
appear in history after the next backfill.

## Location

- **File**: `scripts/little_loops/parallel/orchestrator.py`
- **Line(s)**: 1071, 1490, 1719 (at scan commit: fb567390)
- **Anchor**: `comment "# TODO(ENH-1686): parallel-path close events not yet live-written"`
- **Code**:
```python
        if result.should_close:
            from little_loops.issue_lifecycle import close_issue
            ...
            if info:
                # TODO(ENH-1686): parallel-path close events not yet live-written
                if close_issue(...):
```
- Also: `scripts/little_loops/cli/sprint/run.py` lines 646, 781
  (`# TODO(ENH-1686): sprint sequential path not yet live-written`).

## Current Behavior

Closures via `ll-parallel`/`ll-sprint` emit no live `issue_events` row;
history queries between the closure and the next backfill miss them.

## Expected Behavior

All five close sites emit the same live event write the single-issue path
uses, keeping `.ll/history.db` consistent regardless of orchestration entry
point.

## Proposed Solution

Extract the live-write call used by the ll-auto/single-issue close path into
a shared helper (or fold it into `close_issue` itself behind a flag) and
invoke it at the five TODO sites; remove the TODOs.

## Impact

- **Effort**: Medium
- One coherent piece of missing wiring across both orchestration entry
  points; closes the observability gap ENH-1686 intended to fix.

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:scan-codebase` - 2026-07-24T22:41:56 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
