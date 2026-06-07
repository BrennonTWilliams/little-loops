---
id: BUG-2004
title: 'rn-decompose: enqueue_children writes to visited.txt before items are dequeued,
  inflating tracking'
type: BUG
priority: P3
status: done
captured_at: '2026-06-07T00:00:00Z'
completed_at: '2026-06-07T21:55:47Z'
discovered_date: '2026-06-07'
discovered_by: audit-loop-run
relates_to:
- ENH-1338
- ENH-1940
labels:
- rn-decompose
- rn-implement
- loop-defect
- cycle-detection
---

# BUG-2004: rn-decompose enqueue_children writes to visited.txt before items are dequeued

## Summary

`enqueue_children` in `rn-decompose` appends child issue IDs to `visited.txt` at enqueue time.
`fifo_pop`/`select_next` in `rn-implement` independently also append to `visited.txt` at dequeue
time. Children that survive cycle detection are written twice; children that are skipped
(already in queue or visited) may be written once from `enqueue_children` without ever being
dequeued, permanently marking them as visited.

## Current Behavior

Run `rn-implement-20260607T122052`:

- `dequeue_count.txt` = 6 (6 actual dequeues)
- `visited.txt` = 9 entries:
  ```
  FEAT-1902  ← dequeue 1
  FEAT-2000  ← dequeue 2  (also written by enqueue_children when FEAT-1902 decomposed)
  FEAT-2001  ← dequeue 3  (also written by enqueue_children — already in initial queue)
  FEAT-2002  ← dequeue 4  (also written by enqueue_children — already in initial queue)
  FEAT-2000  ← duplicate from enqueue_children
  FEAT-2001  ← duplicate from enqueue_children
  FEAT-2002  ← duplicate from enqueue_children
  FEAT-1899  ← dequeue 5
  FEAT-1903  ← dequeue 6
  ```
- FEAT-2001 and FEAT-2002 were already in the initial queue when FEAT-1902 was decomposed.
  `enqueue_children` wrote them to `visited.txt` (cycle-detection read), but since they were
  in `queue.txt`, the cycle check correctly skipped re-queuing them. However, `visited.txt`
  now has their entry twice.

## Expected Behavior

- After a run completes, `wc -l visited.txt` equals `dequeue_count.txt` value
- Resuming a run after interruption correctly re-processes children that were queued but
  never dequeued (not skipped as false-visited)

## Steps to Reproduce

1. Run `rn-implement` on an issue that triggers `rn-decompose` (child issues are created)
2. After the run completes, compare `wc -l $RUN_DIR/visited.txt` with `cat $RUN_DIR/dequeue_count.txt`
3. Observe: `visited.txt` count exceeds `dequeue_count.txt` (duplicates written by `enqueue_children`)
4. To reproduce resume corruption: interrupt the run after decomposition but before child dequeues complete
5. Resume via `context.resume`; observe that queued-but-not-dequeued children are silently skipped

## Motivation

On a resumed run (via `context.resume`), `init` preserves `visited.txt`. Children written by
`enqueue_children` but never actually dequeued will appear as "visited" in the next cycle
detection pass, causing them to be silently skipped even if they haven't been processed.

This manifests as permanently-lost queue items when:
1. A run is interrupted after decomposition but before the newly-queued children are dequeued
2. The run is resumed — `init` preserves the inflated `visited.txt`
3. Cycle detection sees those children as already visited and drops them silently

## Root Cause

`enqueue_children` in `rn-decompose` has:
```bash
echo "$child" >> "$RUN_DIR/visited.txt"
```
This was likely added to prevent the same child from being enqueued twice during the same
decomposition pass. However, `visited.txt` is the authoritative "processed" log, not a
"queued" log. The correct deduplication mechanism during a single `enqueue_children` call
is an in-memory set, not `visited.txt`.

## Proposed Solution

Remove the `visited.txt` write from `enqueue_children`. Use an in-memory set within the
Python block to deduplicate children within a single enqueue call:

```yaml
# rn-decompose, enqueue_children action — remove:
- echo "$child" >> "$RUN_DIR/visited.txt"
```

The cycle detection already reads `visited.txt` + `queue.txt` to build the exclusion set.
Writing to `visited.txt` from `enqueue_children` is redundant for cycle detection and
harmful for resume correctness.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-decompose.yaml` — remove `visited.txt` write from `enqueue_children` action

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/rn-implement.yaml` — reads `visited.txt` in `fifo_pop`/`select_next` states

### Similar Patterns
- Other loop YAML files with `enqueue_children` patterns — check for analogous `visited.txt` misuse

### Tests
- N/A — loop YAML change; validate via post-run comparison of `visited.txt` vs `dequeue_count.txt`

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — Affects resume correctness; only manifests on interrupted runs
- **Effort**: Small — Single line removal from `rn-decompose.yaml` `enqueue_children` action
- **Risk**: Low — Removes an incorrect write; cycle detection still guards via `queue.txt` check
- **Breaking Change**: No

## Resolution

**Fixed** in `scripts/little_loops/loops/rn-decompose.yaml` (`enqueue_children` action):

1. Removed the `echo "$child" >> "$RUN_DIR/visited.txt"` write from the depth-assignment
   loop. `visited.txt` is the authoritative *dequeued* log written by `rn-implement`'s
   `fifo_pop`/`select_next` at dequeue time (alongside the `dequeue_count.txt` increment).
   Writing it at enqueue time double-counted survivors and — critically — marked
   queued-but-not-yet-dequeued children as "visited", so a resumed run (which preserves
   `visited.txt` in `init`) silently dropped them during cycle detection.
2. Added in-memory dedup (`visited.add(cid)`) in the cycle-detection survivor loop so a
   child repeated within a single `enqueue_children` candidate list is enqueued only once —
   the correct dedup mechanism the original `visited.txt` write was (incorrectly) standing in for.

**Verification**:
- `ll-loop validate rn-decompose` passes.
- `python -m pytest scripts/tests/` — 711 passed (2 pre-existing, unrelated sprint-integration
  failures confirmed against the clean tree).
- Post-run invariant now holds: `wc -l visited.txt` == `dequeue_count.txt`.

**Audit of analogous loops**: `autodev.yaml` and `recursive-refine.yaml` `enqueue_children`
actions do NOT write `visited.txt` at enqueue time (recursive-refine writes it only at dequeue),
so no analogous defect exists — `rn-decompose` was the sole offender.

## Status

**Done** | Created: 2026-06-07 | Completed: 2026-06-07 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-06-07T21:55:47 - `f6efb25f-82f2-446e-803e-0251ff756c14.jsonl`
- `/ll:ready-issue` - 2026-06-07T21:53:14 - `2a15a559-df1f-4aa3-ac0f-40570937aa2f.jsonl`
- `/ll:format-issue` - 2026-06-07T20:59:38 - `8f5b7fbd-10dd-41b7-b7e6-6117a812b179.jsonl`
