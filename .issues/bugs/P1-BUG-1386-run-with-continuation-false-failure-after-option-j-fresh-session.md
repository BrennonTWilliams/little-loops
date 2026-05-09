---
captured_at: "2026-05-09T18:34:23Z"
discovered_date: "2026-05-09"
discovered_by: capture-issue
---

# BUG-1386: run_with_continuation false failure after Option J fresh session

## Summary

`run_with_continuation()` incorrectly fires Option E (resume) after an Option J (guillotine) fresh session completes successfully. The fresh session writes a `.ll/ll-context-handoff-needed` sentinel, Option E detects it and calls `claude --resume -p` — but that session is already done. The `--resume` call fails (CLI now requires a session ID with `--print`), the non-zero exit is misclassified as REAL failure, and `create_issue_from_failure()` fires — producing a phantom bug issue even though the work was fully completed.

## Current Behavior

1. Session hits 1614% context → Option J fires, runs a fresh guillotine session
2. Fresh session implements the issue, commits, closes it, exits with code 0
3. Stop hook writes `.ll/ll-context-handoff-needed` sentinel (63% context used)
4. Back in the `while` loop, Option E detects the sentinel and calls `claude --dangerously-skip-permissions --resume -p <prompt>`
5. CLI errors: `Error: --resume requires a valid session ID or session title when used with --print.`
6. `run_with_continuation()` returns the `--resume` call's non-zero `CompletedProcess`
7. `process_issue_inplace()` calls `classify_failure()` → REAL → `create_issue_from_failure()` → phantom BUG created
8. Phase 3 (check completed/) never runs because Phase 2 errors out first

## Expected Behavior

After Option J fires a fresh session that exits 0, Option E should not attempt to resume. The function should return the fresh session's `CompletedProcess` (returncode 0). No phantom issue should be created.

## Motivation

This caused BUG-1385 — a phantom issue created even though BUG-1383 was fully implemented and committed. Every time a guillotine fires and the fresh session writes a sentinel, `ll-auto`/`ll-sprint` will produce a false failure and a spurious child issue, corrupting the issue backlog.

## Root Cause

Two interacting bugs:

**Bug 1 (primary):** `run_with_continuation()` has no state tracking for whether the previous iteration ran a fresh guillotine session. Option E's sentinel check runs unconditionally, so it always resumes the last session — even when that session was the guillotine session that already finished.

- **File**: `scripts/little_loops/issue_manager.py`
- **Anchor**: `run_with_continuation()` (~lines 273–350)
- **Cause**: No `_just_ran_fresh_session` flag; Option E check at ~line 304 has no guard against post-J iterations.

**Bug 2 (secondary):** `run_claude_command(..., resume_session=True)` builds `claude --resume -p <prompt>` with no session ID. The current Claude CLI requires a session ID or title when `--print` is used with `--resume`. This breaks Option E for all code paths, not just post-J.

- **File**: `scripts/little_loops/issue_manager.py`
- **Anchor**: `run_claude_command()` (builds the resume command)
- **Cause**: CLI behavior changed; implicit "resume last session" no longer works with `--print`.

**Bug 3 (defense gap):** `process_issue_inplace()` calls `create_issue_from_failure()` before checking whether the issue was already moved to `.issues/completed/`. Phase 3 verification only runs on the success path.

- **File**: `scripts/little_loops/issue_manager.py`
- **Anchor**: `process_issue_inplace()` (~line 767)

## Steps to Reproduce

1. Run `ll-loop run autodev <ISSUE>` where the issue is large enough to trigger guillotine
2. Fresh guillotine session completes successfully (commits, moves to completed/)
3. Observe: `ll-auto` reports the issue as failed; a phantom child issue is created

## Proposed Solution

Three targeted changes — no refactoring beyond what's needed:

### Change 1 — Skip Option E after an Option J fresh session

Add a `_just_ran_fresh_session` flag in `run_with_continuation()`. Set it before the Option J `continue`; read-and-reset at the top of each loop. In Option E, always call `read_sentinel()` to consume/clean the file, but skip the `--resume` call when the flag is set.

```python
# Before the while loop:
_just_ran_fresh_session = False

# Top of while loop:
this_is_fresh = _just_ran_fresh_session
_just_ran_fresh_session = False

# Option J block (~line 294), just before `continue`:
_just_ran_fresh_session = True
continue

# Option E block (~line 304):
sentinel_data = read_sentinel(repo_path)
if sentinel_data is not None and not this_is_fresh and continuation_count < max_continuations:
    # existing --resume logic unchanged
    ...
elif sentinel_data is not None and this_is_fresh:
    logger.info("Fresh session wrote sentinel; consumed without --resume (work already done)")
```

### Change 2 — Classify "requires a valid session ID" as TRANSIENT

In `classify_failure()`, add patterns so the broken `--resume -p` error is treated as TRANSIENT rather than REAL. This prevents phantom issues from any remaining code path that calls `--resume` without a session ID.

```python
# In TRANSIENT patterns list:
"requires a valid session id",
"requires a valid session title",
```

### Change 3 — Early-completion guard in process_issue_inplace()

Before calling `create_issue_from_failure()`, check if the issue was already moved to `.issues/completed/`. If so, log a warning and fall through to Phase 3 as success.

```python
if result.returncode != 0:
    completed_dir = Path(".issues/completed")
    if any(completed_dir.glob(f"*-{info.issue_id}-*.md")):
        logger.warning(
            f"Phase 2 exited non-zero but {info.issue_id} is in completed/; "
            "treating as success (continuation artefact)"
        )
        # fall through to Phase 3
    else:
        failure_type, ... = classify_failure(...)
        ...
```

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_manager.py` — Change 1 (`_just_ran_fresh_session` flag) + Change 3 (early-completion guard)
- `scripts/little_loops/issue_lifecycle.py` — Change 2 (TRANSIENT pattern for session-ID error)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issue_manager.py`: `process_issue_inplace()` calls `run_with_continuation()` and `classify_failure()`
- `scripts/ll_auto.py`, `scripts/ll_sprint.py`, `scripts/ll_parallel.py` — all call `process_issue_inplace()`

### Similar Patterns

- `classify_failure()` TRANSIENT patterns already handle other CLI errors — add alongside existing entries
- `read_sentinel()` already called in Option E — just guard the `--resume` call that follows

### Tests

- `scripts/tests/test_issue_manager.py` — add test: Option J fires, fresh session writes sentinel → Option E does NOT call `--resume`, function returns fresh session's returncode (0)
- `scripts/tests/test_issue_lifecycle.py` — add test: "requires a valid session id" → TRANSIENT
- `scripts/tests/test_issue_manager.py` — add test: Phase 2 returns non-zero but issue is in completed/ → success=True

## Implementation Steps

1. Add `_just_ran_fresh_session` flag to `run_with_continuation()` with read-reset at loop top and set before Option J `continue`
2. Guard Option E's `--resume` call with `not this_is_fresh`
3. Add TRANSIENT patterns to `classify_failure()` for session-ID error
4. Add early-completion guard to `process_issue_inplace()` before `create_issue_from_failure()`
5. Add the three test cases listed above
6. Run: `python -m pytest scripts/tests/test_issue_manager.py scripts/tests/test_issue_lifecycle.py -v`
7. Run: `python -m mypy scripts/little_loops/issue_manager.py scripts/little_loops/issue_lifecycle.py && ruff check scripts/`
8. Close BUG-1385 as a phantom (created by this bug)

## Impact

- **Priority**: P1 — corrupts issue backlog on every guillotine event; already caused BUG-1385
- **Effort**: Small — three narrow, well-scoped changes; no new abstractions
- **Risk**: Low — flag is local to `run_with_continuation()`; TRANSIENT patterns are additive; completion guard is a guard not a rewrite
- **Breaking Change**: No

## Labels

`bug`, `issue-manager`, `run-with-continuation`, `false-failure`, `guillotine`, `p1`

---

## Session Log
- `/ll:capture-issue` - 2026-05-09T18:34:23Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c15bfca8-55be-4e09-8bb8-b49543257890.jsonl`

---

## Status
**Open** | Created: 2026-05-09 | Priority: P1
