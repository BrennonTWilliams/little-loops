---
id: ENH-1349
type: ENH
priority: P3
status: open
discovered_date: 2026-05-03
discovered_by: capture-issue
captured_at: '2026-05-03T16:43:25Z'
completed_at: '2026-05-03T21:45:54Z'
related:
- ENH-1348
- ENH-1350
- ENH-1341
confidence_score: 100
outcome_confidence: 86
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-1349: Queue Peek After Enqueue in `recursive-refine`

## Summary

After `enqueue_children` or `enqueue_or_skip` prepends new child issues to the queue, the user has no visibility into what the queue now looks like. Add a brief "next up" line that shows the first 3–5 IDs waiting in the queue after every enqueue operation, so the user can see what the loop will process next without waiting for those `dequeue_next` lines to arrive.

## Motivation

When a parent decomposes into 4 children and they're prepended to the queue, the only output is "Parent ENH-1100 decomposed; enqueued 4 child issue(s)." The user doesn't know:
- Which children were created
- What order they'll be processed in
- Whether any sibling issues from the original queue are still pending after the children

A queue peek immediately after enqueue costs one `head` call and gives the user a complete snapshot of what's coming next.

## Current Behavior

`enqueue_children` prints:
```
Parent ENH-1100 decomposed; enqueued 4 child issue(s)
```

`enqueue_or_skip` (children branch) prints:
```
Parent ENH-1100 decomposed by size-review; enqueued 4 child issue(s)
```

Neither shows which IDs were enqueued or what the queue looks like afterward.

## Expected Behavior

After the existing enqueue message, append a second line:

```
Parent ENH-1100 decomposed; enqueued 4 child issue(s)
  Next up: ENH-1200, ENH-1201, ENH-1202, ENH-1203 [+2 more]
```

Where:
- "Next up" lists the first `N` (default 5) IDs from the live queue file after the prepend.
- `[+K more]` is appended when the queue has more than `N` remaining items.
- Omitted entirely when the queue is empty after enqueue (shouldn't happen, but defensive).

## Proposed Solution

Add the following block to both `enqueue_children` and `enqueue_or_skip` (children-found branch), immediately after the existing enqueue echo:

```bash
PEEK_COUNT=5
QUEUE_LINES=$(grep -c '[^[:space:]]' .loops/tmp/recursive-refine-queue.txt 2>/dev/null || echo 0)
if [ "$QUEUE_LINES" -gt 0 ]; then
  PEEK=$(head -"$PEEK_COUNT" .loops/tmp/recursive-refine-queue.txt | tr '\n' ',' | sed 's/,$//')
  if [ "$QUEUE_LINES" -gt "$PEEK_COUNT" ]; then
    REMAINING=$((QUEUE_LINES - PEEK_COUNT))
    printf '  Next up: %s [+%d more]\n' "$PEEK" "$REMAINING"
  else
    printf '  Next up: %s\n' "$PEEK"
  fi
fi
```

The peek count could optionally be driven by a `context.queue_peek_count: 5` variable, but defaulting to 5 inline is sufficient.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Output stream**: Append `>&2` to the `printf` call. ENH-1348's dequeue progress line (`dequeue_next` state, ~line 95) established `>&2` as the convention for observability output; both enqueue states use `next:` routing (no `capture:`) so stdout is uncaptured, but stderr keeps all observability output on the same stream.
- **Variable availability**: At the insertion point, `CHILDREN` (newline-separated IDs just prepended) is already in scope. An equivalent alternative to re-reading the queue file: `echo "$CHILDREN" | head -5 | tr '\n' ','`. Reading the live queue file (as the proposal does) is equally correct and shows the full post-prepend order including any prior queue tail.
- **`grep -c` idiom**: `grep -c '[^[:space:]]' .loops/tmp/recursive-refine-queue.txt 2>/dev/null || echo 0` matches the existing idiom in `dequeue_next` (~line 91) for counting non-blank queue lines.

## Acceptance Criteria

- [ ] `enqueue_children` prints a `Next up: ...` line after its existing enqueue message.
- [ ] `enqueue_or_skip` (children branch) prints the same.
- [ ] When queue has ≤ 5 items, all IDs are listed.
- [ ] When queue has > 5 items, the `[+K more]` suffix is appended.
- [ ] When the queue is empty, the line is omitted.
- [ ] `enqueue_or_skip` (no-children branch, dead-end) does not emit a peek line.
- [ ] Test: synthetic 2-parent, 3-child-each run captures expected "Next up" lines in output.

## Scope Boundaries

- **In scope**: "Next up" peek line in both `enqueue_children` and `enqueue_or_skip` children branch.
- **Out of scope**: Configurable peek count via `ll-config.json` (keep it a hardcoded default for now).
- **Out of scope**: Showing the full queue at each dequeue (that would be too verbose; ENH-1348's progress line already handles per-dequeue state).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml`
  - `enqueue_children` state: insert peek block after ~line 303 (total-enqueued counter `printf '%s'` write) and before ~line 304 (`echo "Parent … decomposed; enqueued …"`)
  - `enqueue_or_skip` children-found branch: same insertion — after ~line 508 (total-enqueued counter write), before ~line 509 (`echo "Parent … decomposed by size-review; enqueued …"`)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — invokes `recursive-refine` as sub-loop at `refine_issue` state; reads `recursive-refine-passed.txt` and `recursive-refine-skipped.txt` output files. No changes needed — peek lines go to stderr only and don't affect output files or routing. [Agent 1 finding]
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — invokes `recursive-refine` as sub-loop at `refine_issue` state; same output-file handshake as above. No changes needed. [Agent 1 finding]
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — invokes `recursive-refine` as sub-loop at `refine_unresolved` state. No changes needed. [Agent 1 finding]
- `scripts/little_loops/loops/autodev.yaml` — interleaves with `recursive-refine` via `recursive-refine-broke-down` flag and queue files (lines 70, 107–113). No changes needed — peek output does not affect flag or queue file state. [Agent 1 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — initializes `recursive-refine-broke-down` flag at `write_broke_down` state (line 26/272). No changes needed. [Agent 1 finding]

### Similar Patterns
- `enqueue_children` and `enqueue_or_skip` share the same enqueue pattern; the peek block should be identical in both and placed after the `echo "Parent ... decomposed ..."` line.
- `dequeue_next` state (~line 86): ENH-1348's dequeue progress line is the direct convention model — uses `>&2` for observability output, `grep -c '[^[:space:]]'` for non-blank line counts, `printf` for formatted output. The peek line should follow the same `>&2` convention.
- `dequeue_next` state (~line 78): `head -1` queue-peek idiom already established; `head -"$PEEK_COUNT"` is the natural extension.

### Tests
- `scripts/tests/test_loops_recursive_refine.py` — verify peek line content in synthetic run.
  - Model after `TestDequeueProgressLine` class (line 1104): define `_ENQUEUE_CHILDREN_SCRIPT` and `_ENQUEUE_OR_SKIP_SCRIPT` module-level string constants mirroring each state's action body; write a `_setup_enqueue_env()` helper following `_setup_dequeue_env()` (line 1072) pattern.
  - Assert peek line appears on `result.stderr` (not stdout), matching `TestDequeueProgressLine` assertion style: `assert "Next up:" in result.stderr`.
  - New `TestEnqueuePeekLine` class should cover: peek on stderr after `enqueue_children`; peek on stderr after `enqueue_or_skip` children branch; ≤5 IDs without suffix; >5 IDs with `[+K more]` suffix; empty queue omits peek line; no-children branch of `enqueue_or_skip` does not emit peek.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `TestRecursiveRefineLoop` (line 1596) has structural tests for `enqueue_children` and `enqueue_or_skip` states: `test_required_states_exist` (line 1612) checks both states exist; other tests assert on action substrings like `"find .issues"`, `"mv"`, `"Decomposed from"`, `"recursive-refine-diff-ids.txt"` that are unaffected by adding the peek block. **No changes needed — these tests will not break.** [Agent 3 finding]

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add the `PEEK_COUNT` / `QUEUE_LINES` / `PEEK` bash block to `enqueue_children` after the existing `echo`.
2. Duplicate the same block in `enqueue_or_skip`'s children-found branch after the existing `echo`.
3. Add test coverage for peek line content in a synthetic multi-child run.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file references:_

1. In `scripts/little_loops/loops/recursive-refine.yaml`, `enqueue_children` state: insert peek block after ~line 303 (`printf '%s' "$((PREV_TOTAL + CHILD_COUNT))"`) and before ~line 304 (`echo "Parent … decomposed; enqueued …"`). Add `>&2` to the `printf` inside the peek block.
2. In same file, `enqueue_or_skip` children-found branch: same insertion after ~line 508 / before ~line 509.
3. In `scripts/tests/test_loops_recursive_refine.py`: define `_ENQUEUE_CHILDREN_SCRIPT` / `_ENQUEUE_OR_SKIP_SCRIPT` constants (mirroring `_DEQUEUE_NEXT_SCRIPT` pattern, line 1046) and `_setup_enqueue_env()` helper (mirroring `_setup_dequeue_env()`, line 1072). Assert `"Next up:" in result.stderr`.
4. Run `python -m pytest scripts/tests/test_loops_recursive_refine.py -v -k "enqueue"` to verify.

## Impact

- **Priority**: P3 — Nice-to-have visibility; no behavior change.
- **Effort**: Small — Two identical 8-line bash blocks.
- **Risk**: None — Output-only change; does not affect routing or file state.
- **Breaking Change**: No.

## Labels

`enhancement`, `recursive-refine`, `fsm-loops`, `observability`, `cli-output`

## Resolution

Implemented in `scripts/little_loops/loops/recursive-refine.yaml`:
- Added 8-line peek block after `enqueue_children` echo (6-space indent)
- Added identical peek block inside `enqueue_or_skip` children-found branch (8-space indent)
- Both blocks use `>&2` convention matching ENH-1348's dequeue progress line

Added `TestEnqueuePeekLine` class to `scripts/tests/test_loops_recursive_refine.py` with 6 tests covering all acceptance criteria. All 53 tests pass.

## Status

**Completed** | Created: 2026-05-03 | Completed: 2026-05-03 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-03T21:42:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d93594b-528f-4f68-9762-ff86f2ab1c75.jsonl`
- `/ll:confidence-check` - 2026-05-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6631e7df-b0f4-49b5-b188-539aa5e59767.jsonl`
- `/ll:wire-issue` - 2026-05-03T21:37:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad656149-49c1-4ad1-a76c-25599a57f54c.jsonl`
- `/ll:refine-issue` - 2026-05-03T21:32:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9be08ced-69e6-4d22-a6da-f48f7091aef9.jsonl`
- `/ll:format-issue` - 2026-05-03T19:20:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ac7040e-7ed3-4fc9-8eb6-0a927d3649e8.jsonl`
- `/ll:manage-issue` - 2026-05-03T21:45:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6631e7df-b0f4-49b5-b188-539aa5e59767.jsonl`
- `/ll:capture-issue` - 2026-05-03T16:43:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81b5153d-e662-4abf-af0e-b3ec54065e0b.jsonl`
