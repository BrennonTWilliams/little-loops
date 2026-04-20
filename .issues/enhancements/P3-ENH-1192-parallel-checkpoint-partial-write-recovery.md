---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1174]
---

# ENH-1192: Handle Mid-Checkpoint-Write Failures in Per-Worker Checkpointing

## Summary

FEAT-1174 specifies per-worker checkpointing for resume-after-interrupt, but does not address what happens when a checkpoint write fails partway through — e.g., disk full, SIGKILL during `write()`, filesystem error mid-flush. On resume, a partially-written checkpoint file could parse as corrupt JSON, or (worse) parse as valid JSON but describe an inconsistent state (e.g., recorded a completion timestamp but not the result payload). Adopt an atomic-write pattern and specify the resume-time recovery rule.

## Current Behavior (as of FEAT-1174 spec)

FEAT-1174 says: "per-worker completion state stored in `parallel_progress[state_name].completed[]`." The write path is implicit — likely a `json.dump(...)` on the progress file. No atomic-write discipline, no `.tmp` + `os.replace` rename, no recovery rule for partial writes.

## Expected Behavior

1. **Atomic-write pattern for checkpoint writes**: every checkpoint write uses write-to-tmp + `os.replace` rename. The `.tmp` file is in the same directory as the target so `os.replace` is atomic on POSIX and Windows.
   ```python
   tmp = target.with_suffix(target.suffix + ".tmp")
   tmp.write_text(json.dumps(state))
   os.replace(tmp, target)
   ```
2. **Resume-time recovery**: on resume, if a `.tmp` file exists for a per-worker checkpoint:
   - Delete the `.tmp` (it's known-bad partial state).
   - Treat the corresponding worker as **unfinished** — re-run its item from scratch.
   - Log a WARNING naming the item and the recovered (re-run) action.
3. **Parent checkpoint (FEAT-1174 main-thread-only)**: same atomic-write pattern. If the parent's `.tmp` exists on resume, the whole state is considered mid-flight and the last checkpoint-on-disk is used (not the `.tmp`).
4. **Corrupt-JSON recovery**: if `json.loads()` on a checkpoint file raises, treat that worker as unfinished (same recovery as `.tmp` presence). Never silently skip.

## Proposed Solution

1. Add a helper `scripts/little_loops/fsm/atomic_write.py::atomic_write_text(path, text)` that encapsulates the tmp + rename pattern. Reuse where possible.
2. Apply to:
   - Parent checkpoint writes (`PersistentExecutor._save_state()`)
   - Per-worker checkpoint writes (`ParallelRunner` worker body)
3. Add resume logic in the load path:
   ```python
   if tmp_path.exists():
       logger.warning(f"Partial checkpoint {tmp_path} — re-running worker for item {i}")
       tmp_path.unlink()
       return None  # caller treats as unfinished
   try:
       return json.loads(path.read_text())
   except json.JSONDecodeError:
       logger.warning(f"Corrupt checkpoint {path} — re-running worker for item {i}")
       return None
   ```
4. Tests:
   - `test_atomic_write_survives_sigkill_sim` — write a tmp, simulate crash (don't rename), assert the original file is unchanged and the tmp can be detected.
   - `test_resume_with_tmp_checkpoint_reruns_worker` — create a bogus `.tmp`, resume, assert worker re-runs and the WARNING log fires.
   - `test_resume_with_corrupt_json_checkpoint_reruns_worker` — write a bad JSON file, resume, assert worker re-runs and the WARNING log fires.

## Files to Modify

- `scripts/little_loops/fsm/atomic_write.py` — new helper module
- `scripts/little_loops/fsm/persistence.py` — parent checkpoint write path
- `scripts/little_loops/fsm/parallel_runner.py` — per-worker checkpoint write path
- `scripts/tests/test_atomic_write.py` — new tests
- `scripts/tests/test_parallel_runner.py` — resume-recovery tests

## Acceptance Criteria

- `atomic_write_text()` helper exists with tmp-file-in-same-dir + `os.replace` rename
- Parent checkpoint and per-worker checkpoint both use the helper
- `.tmp` presence on resume causes WARNING log + worker re-run
- Corrupt JSON on resume causes WARNING log + worker re-run
- Three tests cover the atomic-write and recovery paths
- No checkpoint file can ever be observed in a torn / half-written state by a resume process

## Impact

- **Priority**: P3 — Failure mode requires a specific crash window (SIGKILL during `write()` or disk-full mid-flush). Not common, but when it happens without atomic writes, recovery is a silent data-loss bug.
- **Effort**: Small — one helper + two integration points + three tests
- **Risk**: Low
- **Breaking Change**: No — existing (non-crashing) write paths are unchanged in behavior

## Labels

`fsm`, `parallel`, `checkpoint`, `durability`, `safety`

## Related / See Also

- **FEAT-1174** — per-worker checkpointing (this issue hardens its write path)
- **ENH-1186** — v1 scope doc (should mention the atomic-write guarantee)

---

## Session Log
- `parallel-family-review` - 2026-04-20T00:00:00Z - Created during issue-set review. FEAT-1174's resume story is incomplete without a defined recovery for partial/corrupt checkpoint files.

---

**Open** | Created: 2026-04-20 | Priority: P3
