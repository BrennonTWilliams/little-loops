---
id: ENH-1348
type: ENH
priority: P3
status: open
discovered_date: 2026-05-03
discovered_by: capture-issue
captured_at: "2026-05-03T16:43:25Z"
related: [ENH-1347, ENH-1338, ENH-1339, ENH-1350]
---

# ENH-1348: Real-Time Dequeue Progress Line in `recursive-refine`

## Summary

`dequeue_next` currently emits no output to the user — between the sub-loop's own output there can be long silent gaps. Add a single progress line emitted on every dequeue that shows the current position in the overall run (e.g., `[3/9] → ENH-1234 (depth: 0) | passed: 2 | queued: 5 | skipped: 1`), so the user always has a live sense of where the loop is and how far it has to go.

## Motivation

`recursive-refine` can run for hours against a large tree. The only current indicators of progress are the sub-loop's own stdout and the sparse `enqueue_children` lines. When a sub-loop is grinding through a large issue, the parent loop is entirely silent. Users watching a terminal have no way to know:
- How many issues have been processed so far
- How many remain in the queue
- Whether the loop is near the end or has just started

A simple counter line — cheap to add, easy to read — addresses this entirely.

## Current Behavior

`dequeue_next` silently pops the queue head and echoes the issue ID (captured internally). No user-visible progress line is emitted.

## Expected Behavior

After dequeuing, before handing off to `capture_baseline`, emit a line:

```
[3/9] → ENH-1234 (depth: 0) | passed: 2 | queued: 5 | skipped: 1
```

Where:
- `3/9` = issues dequeued so far / total ever enqueued (cumulative counter, not just original queue size — grows as children are added)
- `→ ENH-1234` = the ID just dequeued
- `(depth: 0)` = subtree depth of this issue (requires ENH-1347's depth tracking to be in place; fall back to omitting if depth file absent)
- `passed: 2` = count from `recursive-refine-passed.txt`
- `queued: 5` = count of remaining lines in `recursive-refine-queue.txt`
- `skipped: 1` = count from `recursive-refine-skipped.txt`

## Proposed Solution

### Step 1 — Total-enqueued counter

In `parse_input`, after writing the queue file, initialize:
```bash
COUNT=$(wc -l < .loops/tmp/recursive-refine-queue.txt | tr -d ' ')
echo "$COUNT" > .loops/tmp/recursive-refine-total-enqueued.txt
```

### Step 2 — Enqueued counter bump on child enqueue

In both `enqueue_children` and `enqueue_or_skip` (children-found branch), after prepending children:
```bash
CHILD_COUNT=$(wc -l < .loops/tmp/recursive-refine-new-children.txt | tr -d ' ')
PREV=$(cat .loops/tmp/recursive-refine-total-enqueued.txt 2>/dev/null || echo 0)
echo $((PREV + CHILD_COUNT)) > .loops/tmp/recursive-refine-total-enqueued.txt
```

### Step 3 — Dequeue counter increment

In `dequeue_next`, after capturing `CURRENT`, maintain a dequeue counter:
```bash
DEQUEUED=$(cat .loops/tmp/recursive-refine-dequeued-count.txt 2>/dev/null || echo 0)
DEQUEUED=$((DEQUEUED + 1))
echo "$DEQUEUED" > .loops/tmp/recursive-refine-dequeued-count.txt
```

### Step 4 — Emit progress line

In `dequeue_next`, immediately before `echo "$CURRENT"`:
```bash
TOTAL=$(cat .loops/tmp/recursive-refine-total-enqueued.txt 2>/dev/null || echo '?')
PASSED=$(grep -c '[^[:space:]]' .loops/tmp/recursive-refine-passed.txt 2>/dev/null || echo 0)
QUEUED=$(grep -c '[^[:space:]]' .loops/tmp/recursive-refine-queue.txt 2>/dev/null || echo 0)
SKIPPED=$(grep -c '[^[:space:]]' .loops/tmp/recursive-refine-skipped.txt 2>/dev/null || echo 0)
DEPTH=$(cat .loops/tmp/recursive-refine-current-depth.txt 2>/dev/null)
DEPTH_STR=${DEPTH:+" (depth: $DEPTH)"}
printf '[%s/%s] → %s%s | passed: %d | queued: %d | skipped: %d\n' \
  "$DEQUEUED" "$TOTAL" "$CURRENT" "$DEPTH_STR" "$PASSED" "$QUEUED" "$SKIPPED" >&2
```

(Written to stderr so it doesn't interfere with the `capture: input` capture of stdout.)

## Acceptance Criteria

- [ ] `parse_input` initializes `recursive-refine-total-enqueued.txt` with root count and `recursive-refine-dequeued-count.txt` at 0.
- [ ] `enqueue_children` and `enqueue_or_skip` (children branch) increment `recursive-refine-total-enqueued.txt` by the child count.
- [ ] `dequeue_next` increments `recursive-refine-dequeued-count.txt` and emits a `[N/M] → ID (depth: D) | passed: P | queued: Q | skipped: S` line to stderr.
- [ ] Depth field is omitted gracefully when ENH-1347 depth tracking is not in place.
- [ ] Line appears before every sub-loop invocation; no other loop behavior changes.
- [ ] Test: synthetic 3-issue run captures all 3 progress lines in stderr output.

## Scope Boundaries

- **In scope**: `dequeue_next` progress line, counter bookkeeping files.
- **Out of scope**: graphical progress bars, ETA estimation, rate calculations.
- **Out of scope**: per-state heartbeat lines (that would be a separate proposal).

## Success Metrics

- Progress line emitted on every dequeue: all 3 lines visible in synthetic 3-issue stderr capture.
- Format correctness: `[N/M] → ID | passed: P | queued: Q | skipped: S` matches expected format on each line.
- Depth field: gracefully absent when `recursive-refine-current-depth.txt` is not present (no crash, no malformed line).
- Total-enqueued counter: grows correctly as children are enqueued mid-run (counter reflects cumulative total, not initial queue size).

## API/Interface

N/A — No public API changes. All changes are internal to `recursive-refine.yaml` bash actions; new counter files (`.loops/tmp/recursive-refine-total-enqueued.txt`, `recursive-refine-dequeued-count.txt`) are runtime state only.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — `parse_input` (init counters), `dequeue_next` (counter + emit), `enqueue_children` (bump total), `enqueue_or_skip` (bump total in children branch).

### Dependent Files
- `scripts/tests/test_loops_recursive_refine.py` — verify progress line content in synthetic run.
- `scripts/tests/test_builtin_loops.py` — `TestRecursiveRefineLoop`: minimal structural check that `dequeue_next` action references counter files.

### Dependencies / Enhances
- ENH-1347 — depth field in progress line depends on `recursive-refine-current-depth.txt` written there; graceful fallback when absent.
- ENH-1350 — skipped count in progress line will become more meaningful once skip reasons are partitioned.

### Similar Patterns
- `scripts/little_loops/loops/recursive-refine.yaml` — existing counter files (`passed.txt`, `queue.txt`, `skipped.txt`) use the same `grep -c` pattern; new counter files follow the same convention.
- Other FSM loops in `scripts/little_loops/loops/` — check for any that emit progress lines via `printf` to stderr for consistency.

### Tests
- `scripts/tests/test_loops_recursive_refine.py` — add: synthetic 3-issue run capturing stderr; assert all 3 `[N/M] → ID` progress lines are present with correct format.
- `scripts/tests/test_builtin_loops.py` — add: `dequeue_next` action references `recursive-refine-dequeued-count.txt`.

### Documentation
- N/A — internal observability improvement; no user-facing docs require updates.

### Configuration
- N/A — runtime state only (`.loops/tmp/recursive-refine-*.txt`); no configuration file changes required.

## Implementation Steps

1. Add counter init to `parse_input` (`total-enqueued` = root count, `dequeued-count` = 0).
2. Increment `total-enqueued` in both `enqueue_children` and `enqueue_or_skip` children branch.
3. In `dequeue_next`: increment `dequeued-count`, compute counts, emit progress line to stderr before `echo "$CURRENT"`.
4. Add test coverage for the progress line content.

## Impact

- **Priority**: P3 — Pure observability; no behavior change.
- **Effort**: Small — Counter files + one printf in dequeue_next + two counter bumps on enqueue.
- **Risk**: Minimal — stderr output only; does not affect capture mechanism or loop routing.
- **Breaking Change**: No.


## Blocks

- ENH-1350

## Labels

`enhancement`, `recursive-refine`, `fsm-loops`, `observability`, `cli-output`

## Status

**Open** | Created: 2026-05-03 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-05-03T19:20:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16a69f6f-62b6-4282-8d76-179c33de8c88.jsonl`
- `/ll:capture-issue` - 2026-05-03T16:43:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81b5153d-e662-4abf-af0e-b3ec54065e0b.jsonl`
