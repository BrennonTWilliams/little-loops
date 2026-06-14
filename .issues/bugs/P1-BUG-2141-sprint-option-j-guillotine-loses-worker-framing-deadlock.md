---
id: BUG-2141
type: BUG
priority: P1
captured_at: '2026-06-14T03:50:03Z'
discovered_date: '2026-06-14'
discovered_by: capture-issue
status: open
relates_to:
- BUG-1386
- ENH-1996
confidence_score: 91
outcome_confidence: 82
score_complexity: 18
score_test_coverage: 15
score_ambiguity: 18
score_change_surface: 19
---

# BUG-2141: Sprint Option J guillotine loses worker framing → fresh session deadlock

## Summary

When a sprint worker running in sequential mode hits the context limit and Option J fires,
the guillotine resume file (`guillotine-prompt.md`) contains only generic continuation
instructions — no sprint worker framing. The fresh session spawned via `/ll:resume` does
not know it is a sprint worker, does not know to stop after ONE issue, and does not know
to exit when done. It implements whichever issues look interesting, then blocks asking
"What next?" — deadlocking the sprint orchestrator indefinitely.

## Current Behavior

`worker_pool.py:837` writes `guillotine-prompt.md` with:
```
## Intent
Resume an interrupted automation session that hit the context limit.
Original task: {task_first_line}
...
## Next Steps
1. Check git log ...
2. Check the issue file status — if already done/cancelled, stop
3. Review .loops/tmp/scratch/ for partial progress notes
4. Continue the original task from where it left off, skipping already-completed work
```

The fresh session started via `/ll:resume <guillotine-prompt.md>` has no knowledge of:
- Being a sprint worker (vs. a general automation session)
- Which single issue ID it is responsible for
- That it must stop after completing exactly one issue
- That it must exit cleanly without waiting for further user input

**Observed in the field (2026-06-13, `cards` project):**
- FEAT-025 processing hit 4095% context → Option J fired
- Fresh session read the summary, implemented FEAT-025, FEAT-027, FEAT-030, FEAT-037 (all
  issues visible in the context summary), committed them all to branch `feat-037-...`
- Fresh session then asked "What would you like me to do next?" → blocked forever
- Sprint orchestrator (`sprint/run.py:369`) waited indefinitely for `process_issue_inplace()`
  to return → manual kill required

## Expected Behavior

When Option J fires inside a sprint worker, the guillotine resume file must inject sprint
worker framing so the fresh session knows its constraints:
```
## Sprint Worker Context
You are processing exactly ONE sprint issue: FEAT-025
After completing this issue, exit immediately — do NOT process other issues.
Do NOT ask for further instructions. Exit with code 0.
Branch: main (or the worktree branch)
```

## Root Cause

- **File**: `scripts/little_loops/parallel/worker_pool.py`
- **Lines**: 837–854 (`guillotine_file.write_text(...)`)
- **Anchor**: in method `_run_with_continuation`

`_run_with_continuation()` has no knowledge of whether it is operating inside a sprint
worker context. It receives only `command` (the original task string) and `run_dir`. The
sprint worker framing (issue ID, branch, stop-after-one, exit-when-done) is never passed
in, so it cannot be written into the resume file.

`process_issue_inplace()` calls `_run_with_continuation()` but does not pass sprint-specific
metadata. The sprint runner (`sprint/run.py:369`) calls `process_issue_inplace()` with only
`info`, `config`, `logger`, and `dry_run` — no sprint context parameter.

## Proposed Fix

1. Add a `sprint_context: SprintWorkerContext | None = None` parameter to
   `_run_with_continuation()` (and through `process_issue_inplace()`).

2. When building `guillotine-prompt.md` and `sprint_context` is set, prepend a
   `## Sprint Worker Context` block:
   ```python
   if sprint_context is not None:
       framing = (
           f"## Sprint Worker Context\n"
           f"You are a sprint worker. Process exactly ONE issue: "
           f"{sprint_context.issue_id}\n"
           f"After completing this issue, exit immediately — do NOT process other issues.\n"
           f"Do NOT ask for further instructions. Exit with code 0.\n"
           f"Branch: {sprint_context.branch}\n\n"
       )
       guillotine_file.write_text(framing + body)
   ```

3. Pass sprint context from `sprint/run.py` through `process_issue_inplace()` to
   `_run_with_continuation()`.

## Files to Modify

- `scripts/little_loops/parallel/worker_pool.py` — `_run_with_continuation()`, guillotine resume file writer
- `scripts/little_loops/issue_manager.py` — `process_issue_inplace()` signature
- `scripts/little_loops/cli/sprint/run.py` — pass sprint context at call site (line 369)

## Impact

- **Severity**: Critical — sprint deadlocks with no automatic recovery
- **Effort**: Medium — adding a parameter through 3 layers, writing framing block
- **Risk**: Low — additive change; non-sprint callers pass `None`, behavior unchanged
- **Breaking Change**: No

## Related Issues

- BUG-1386 (done): `run_with_continuation` false failure after Option J
- ENH-1996 (done): Option J should use `/ll:resume` instead of summary blob
- BUG-2144: Sprint orchestrator deadlock timeout gap (mitigation)
- ENH-2143: Sequential sprint worktree isolation (mitigation)

## Session Log
- `/ll:capture-issue` - 2026-06-14T03:50:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Status
**Open** | Priority: P1
