---
id: ENH-1348
type: ENH
priority: P3
status: done
discovered_date: 2026-05-03
discovered_by: capture-issue
captured_at: '2026-05-03T16:43:25Z'
completed_at: '2026-05-03T21:27:21Z'
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
relates_to: ['ENH-1347', 'ENH-1338', 'ENH-1339', 'ENH-1350']
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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — invokes `loop: recursive-refine` in `refine_issue` state; reads `recursive-refine-passed.txt` and `recursive-refine-skipped.txt` post-run. No modification needed — interface contract (exit code, output files) is unchanged by ENH-1348.
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — same sub-loop invocation pattern with `context_passthrough: true`; reads same output files. No modification needed.
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — invokes `loop: recursive-refine` as sub-loop. No modification needed.

### Dependencies / Enhances
- ENH-1347 — depth field in progress line depends on `recursive-refine-current-depth.txt` written there; graceful fallback when absent.
- ENH-1350 — skipped count in progress line will become more meaningful once skip reasons are partitioned.

### Similar Patterns
- `scripts/little_loops/loops/recursive-refine.yaml` — existing counter files (`passed.txt`, `queue.txt`, `skipped.txt`) use the same `grep -c` pattern; new counter files follow the same convention.
- `scripts/little_loops/loops/lib/common.yaml` — `retry_counter` fragment is the canonical read-increment-write pattern: `N=$(cat "$FILE" 2>/dev/null || echo 0); N=$((N + 1)); printf '%s' "$N" > "$FILE"`. Inline this for `dequeued-count` rather than invoking the fragment (routing logic differs).
- Other FSM loops in `scripts/little_loops/loops/` — check for any that emit progress lines via `printf` to stderr for consistency.

### Tests
- `scripts/tests/test_loops_recursive_refine.py` — add: synthetic 3-issue run capturing stderr; assert all 3 `[N/M] → ID` progress lines are present with correct format.
- `scripts/tests/test_builtin_loops.py` — add: `dequeue_next` action references `recursive-refine-dequeued-count.txt`.
- `scripts/tests/test_builtin_loops.py` — add: `test_parse_input_initializes_dequeued_count_and_total_enqueued` asserting `parse_input` action body references both `recursive-refine-dequeued-count.txt` and `recursive-refine-total-enqueued.txt`. [_Wiring pass added by `/ll:wire-issue`_]

### Documentation
- N/A — internal observability improvement; no user-facing docs require updates.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — Notes paragraph enumerates all `.loops/tmp/recursive-refine-*.txt` state files. The two new counter files (`recursive-refine-total-enqueued.txt`, `recursive-refine-dequeued-count.txt`) are absent from that list. Optional: update the Notes paragraph to include them if the convention is to document all state files. Core N/A ruling stands — no behavioral docs change required.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact insertion points in `recursive-refine.yaml`:**
- `parse_input` — insert the two new `printf '' >` counter-init lines after line 59 (last `printf '' >` for `recursive-refine-decomposition.tsv`) and before line 60 (`COUNT=$(wc -l …)`)
- `dequeue_next` — insert after line 83 (`printf '%s' "${DEPTH:-0}" > …current-depth.txt`) and before line 84 (`echo "$CURRENT"`) — depth value is already resolved here, safe to read same-action
- `enqueue_children` — insert after line 289 (`CHILD_COUNT=$(wc -l …)`) and before line 290 (`echo "Parent … decomposed"`)
- `enqueue_or_skip` — insert after line 492 (`CHILD_COUNT=$(wc -l …)`) and before line 493 (`echo "Parent … decomposed by size-review"`) — only inside the `if [ -s … ]` children-found branch

**ENH-1347 is already completed** (`.issues/completed/P2-ENH-1347-*`). `dequeue_next` already writes `recursive-refine-current-depth.txt` via `printf '%s' "${DEPTH:-0}"` on every dequeue. The depth value is always available in the same action block; no file-existence guard is needed (the `2>/dev/null` fallback on the `cat` read is still appropriate for robustness).

**FSM `${}` escaping**: `dequeue_next` already uses single-dollar `${DEPTH:-0}` syntax successfully (FSM only expands dotted-path tokens like `${captured.input.output}`; plain `${VARNAME:-default}` passes through to bash). The `done` state's `$${PASSED_LIST:-none}` double-dollar pattern appears because `PASSED_LIST` is set inside a heredoc/subshell context — not relevant for inline `dequeue_next` action bash. Use single-dollar `${DEPTH:+…}` as the proposed solution shows.

**Test pattern for stderr assertions** (from `test_loops_recursive_refine.py`): use `_bash(script, tmp_path)` helper (runs `bash -c <script>`, returns `CompletedProcess`). Assert `result.stderr` directly, e.g. `assert "[1/3] → ENH-001" in result.stderr`. Copy the relevant `dequeue_next` action block verbatim as the test script, pre-creating the counter files in `loops_tmp`.

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

## Resolution

Implemented in `scripts/little_loops/loops/recursive-refine.yaml`:

1. **`parse_input`** — initializes `recursive-refine-dequeued-count.txt` to `0` and `recursive-refine-total-enqueued.txt` to the root queue count.
2. **`dequeue_next`** — increments `dequeued-count`, reads `total-enqueued` and live counts from passed/queued/skipped files, then emits `[N/M] → ID (depth: D) | passed: P | queued: Q | skipped: S` to stderr before the `echo "$CURRENT"` capture line.
3. **`enqueue_children`** — bumps `total-enqueued` by the child count after prepending children.
4. **`enqueue_or_skip`** (children-found branch) — same total bump.

Test coverage added:
- `TestDequeueProgressLine` (7 tests) in `test_loops_recursive_refine.py` — exercises the full bash logic including the 3-issue synthetic run, depth inclusion/omission, counter increment, and stderr-only output.
- 3 structural assertions added to `TestRecursiveRefineLoop` in `test_builtin_loops.py` — verify parse_input initializes both counter files and dequeue_next references them with stderr redirect.

## Status

**Completed** | Created: 2026-05-03 | Completed: 2026-05-03 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-05-03T21:27:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-03T21:18:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e707af3-cf6e-4f2e-9f3b-b72a86d802c5.jsonl`
- `/ll:confidence-check` - 2026-05-03T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c4e6ce0-8004-4a8f-bb90-942b42832dd6.jsonl`
- `/ll:wire-issue` - 2026-05-03T21:15:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e707af3-cf6e-4f2e-9f3b-b72a86d802c5.jsonl`
- `/ll:refine-issue` - 2026-05-03T21:10:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c4e6ce0-8004-4a8f-bb90-942b42832dd6.jsonl`
- `/ll:format-issue` - 2026-05-03T19:20:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16a69f6f-62b6-4282-8d76-179c33de8c88.jsonl`
- `/ll:capture-issue` - 2026-05-03T16:43:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81b5153d-e662-4abf-af0e-b3ec54065e0b.jsonl`
