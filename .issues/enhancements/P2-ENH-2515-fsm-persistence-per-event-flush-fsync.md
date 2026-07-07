---
id: ENH-2515
title: Add per-event flush+fsync at StatePersistence append sites
type: ENH
status: done
priority: P2
parent: ENH-2514
decision_needed: false
captured_at: '2026-07-07T06:36:33Z'
completed_at: 2026-07-07 10:07:55+00:00
discovered_date: '2026-07-07'
discovered_by: issue-size-review
relates_to:
- ENH-2514
- BUG-2501
- BUG-2513
labels:
- loops
- fsm
- ll-loop
- persistence
- durability
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 21
---

# ENH-2515: Add per-event flush+fsync at StatePersistence append sites

## Summary

Add kernel-level durability to `StatePersistence` append-only writers by calling
`f.flush()` + `os.fsync(f.fileno())` after every write. Closes the SIGKILL gap
where events buffered in the kernel page cache are lost on hard kill.

## Parent Issue

Decomposed from ENH-2514: ll-loop should flush events.jsonl / state.json on
forced termination. The signal-handling path is decomposed into ENH-2516; this
child covers only the persistence-layer durability change.

## Background

Verified by codebase research: `StatePersistence.append_event`
(`scripts/little_loops/fsm/persistence.py:425`) already opens and closes the
file per call, which drains Python's user-space buffer to the kernel. What is
NOT in place is `f.flush()` + `os.fsync(f.fileno())` after the write — the
kernel page cache itself is not forced to disk. SIGKILL (which Python cannot
trap) still loses any pending transitions because the OS-level buffer hasn't
been flushed.

This child implements the "Selected: Incremental append" path from ENH-2514.

## Current Behavior

`StatePersistence.append_event` and the three sister append-only writers
(`usage.jsonl`, `messages.jsonl`, `_write_meta_eval_entry`) open and close
the file per call but **do not** issue `flush()` + `os.fsync()` after the
write. On graceful termination (normal exit, SIGINT handler from ENH-2516)
the OS eventually flushes the page cache; on SIGKILL (which Python cannot
trap) the kernel page cache contents are lost — leaving events.jsonl with
a truncated trail of only those writes the OS had already pushed to disk.

## Expected Behavior

After this change, every append-only writer in `persistence.py` finishes a
write with a paired `f.flush()` + `os.fsync(f.fileno())` so the kernel page
cache is drained before the file object is closed. SIGKILL immediately
after an `append_event` call preserves the just-written event; an outside
reader opening `events.jsonl` mid-execution sees every event already
flushed (not buffered).

## Motivation

- **Audit-trail durability**: Closes the SIGKILL data-loss gap surfaced by
  BUG-2501 post-mortem — without per-event fsync, the events.jsonl trail can
  end short of the actual transition count when the loop is hard-killed.
- **Complements ENH-2516**: The signal-handler improvement alone (ENH-2516)
  can't help on SIGKILL — Python has no trap for it. Persistence-layer fsync
  is the only path that survives a hard kill.
- **Decomposition discipline**: The parent ENH-2514 mixed two concerns
  (signal handling + persistence durability); this child isolates the
  four write-site changes so they can be merged, reviewed, and reverted
  independently of ENH-2516.

## Implementation Steps

1. Modify `StatePersistence.append_event` (`scripts/little_loops/fsm/persistence.py:425`)
   to call `f.flush()` + `os.fsync(f.fileno())` after the write. Add an inline
   comment explaining the kernel-cache → disk semantic for future readers.
2. Apply the same flush+fsync treatment to the three sister append-only writers
   inside `_handle_event` / `_write_meta_eval_entry`:
   - `usage.jsonl` write at `scripts/little_loops/fsm/persistence.py:696-697`
   - `messages.jsonl` write at `scripts/little_loops/fsm/persistence.py:710-711`
   - `_write_meta_eval_entry` at `scripts/little_loops/fsm/persistence.py:776-777`
3. Add unit tests in `scripts/tests/test_fsm_persistence.py` alongside
   `test_append_events` (line 308, inside `class TestStatePersistence`). Mock
   the file object and `os.fsync`, then assert:
   - `f.flush()` is called exactly once per `append_event` invocation.
   - `os.fsync(f.fileno())` is called exactly once per `append_event`
     invocation.
   - Same assertions for the three sister writers (or refactor into a shared
     helper if useful).
4. Add a partial-trail test in `scripts/tests/test_fsm_persistence.py`:
   - Construct `StatePersistence` with a `tmp_path`-backed `running_dir`.
   - Call `append_event({"event": "loop_start", ...})` 3 times.
   - Without closing the persistence object, use a separate file descriptor to
     `open(events_file, "r")` and read — assert ≥3 lines visible.

## Success Metrics

- **Durability**: `f.flush()` and `os.fsync(f.fileno())` are each invoked
  exactly once per append-only writer call (verified by mock-based tests
  in `test_fsm_persistence.py`).
- **Mid-execution visibility**: A separate file descriptor opened against
  `events.jsonl` between `append_event` calls sees all events written up
  to that point (no stale kernel-buffer lag).
- **Performance budget**: Per-event `os.fsync()` overhead stays under
  ~10ms/event on SSD; if benchmark shows worse, escalate to interval-
  batched fsync (out of scope here, tracked as a potential follow-up).

## Scope Boundaries

- **In scope**: The four append-only writers in `scripts/little_loops/fsm/persistence.py`.
- **Out of scope**: The second-SIGINT force-exit path (covered by ENH-2516).
- **Out of scope**: Extending `archive_run` to copy `usage.jsonl` /
  `messages.jsonl` (potential follow-up; not blocking this child).
- **Out of scope**: Refactoring all five atomic-write sites to use a shared
  `atomic_write_json(path, data, fsync=True)` helper (potential follow-up;
  ENH-2514 Codebase Research Findings flagged this but inlined the change for
  scope-tightness here).

## API/Interface

No public API changes. Internal-only: `append_event` (and the three sister
writers) gain two extra calls per invocation.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — flush+fsync at four write sites
  (`append_event` line 425; `usage.jsonl` write at line 696-697; `messages.jsonl`
  write at line 710-711; `_write_meta_eval_entry` at line 776-777).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — calls `append_event` from the
  state-machine main loop; behavior unchanged (caller signature preserved).
- `scripts/little_loops/parallel/orchestrator.py` — reads `events.jsonl` for
  audit; benefits transparently from the durability improvement.
- `scripts/little_loops/cli/loop/_helpers.py` — reads `events.jsonl` /
  `usage.jsonl` / `messages.jsonl` for run inspection; benefits transparently.

### Similar Patterns
- The five atomic-write sites (separate from the four append-only writers)
  still lack fsync and are flagged in ENH-2514 Codebase Research Findings as
  a potential follow-up — not addressed in this child.

### Tests
- `scripts/tests/test_fsm_persistence.py` — extend `test_append_events` (line
  308, inside `class TestStatePersistence`) with mock-based assertions:
  - `f.flush()` called exactly once per `append_event` invocation.
  - `os.fsync(f.fileno())` called exactly once per `append_event` invocation.
  - Same assertions for the three sister writers (refactor into a shared
    helper if useful).
- `scripts/tests/test_fsm_persistence.py` — add a partial-trail test:
  - Construct `StatePersistence` with a `tmp_path`-backed `running_dir`.
  - Call `append_event({"event": "loop_start", ...})` 3 times.
  - Without closing the persistence object, use a separate file descriptor to
    `open(events_file, "r")` and read — assert ≥3 lines visible.

### Documentation
- N/A — internal behavior change; no user-facing docs reference the
  append-only writer internals.

### Configuration
- N/A — no config files affected.

## Impact

- **Priority**: P2 — Audit-trail gap surfaces only on SIGKILL; required to
  fully close ENH-2514.
- **Effort**: Small — local change at four write sites; ~50 lines of test code.
- **Risk**: Low — additive; no change to read paths or graceful-exit behavior.
- **Performance**: Per-event `os.fsync()` is ~1-10ms on SSD. High-event-rate
  loops may see noticeable slowdown. Mitigation: benchmark before commit; if
  performance is unacceptable, batch fsync at fixed intervals (out of scope
  here).

## Status

**Open** | Created: 2026-07-07 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-07-07T09:57:34 - `d4092018-986f-4914-b727-2ab48e1dac5e.jsonl`
- `/ll:format-issue` - 2026-07-07T09:52:17 - `e61ca79e-7eec-4de9-9408-018928efb2bf.jsonl`
- `/ll:issue-size-review` - 2026-07-07T06:36:33Z - `fc70cacc-0621-41d5-a7b3-89f8f15d4569.jsonl`
- `/ll:confidence-check` - 2026-07-07T10:30:00 - `96e9d37c-629d-4ef1-b116-8e5f7a181824.jsonl`
- `/ll:manage-issue` - 2026-07-07T10:07:55Z - `72b61ec6-a39d-4dd9-be5e-d9604bc1afdd.jsonl`