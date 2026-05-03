---
id: ENH-1349
type: ENH
priority: P3
status: open
discovered_date: 2026-05-03
discovered_by: capture-issue
captured_at: "2026-05-03T16:43:25Z"
related: [ENH-1348, ENH-1350, ENH-1341]
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
- `scripts/little_loops/loops/recursive-refine.yaml` — `enqueue_children` and `enqueue_or_skip` (children branch): add peek block after existing echo.

### Dependent Files (Callers/Importers)
- N/A — enqueue functions are internal FSM state handlers; no external callers.

### Similar Patterns
- `enqueue_children` and `enqueue_or_skip` share the same enqueue pattern; the peek block should be identical in both and placed after the `echo "Parent ... decomposed ..."` line.

### Tests
- `scripts/tests/test_loops_recursive_refine.py` — verify peek line content in synthetic run.

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add the `PEEK_COUNT` / `QUEUE_LINES` / `PEEK` bash block to `enqueue_children` after the existing `echo`.
2. Duplicate the same block in `enqueue_or_skip`'s children-found branch after the existing `echo`.
3. Add test coverage for peek line content in a synthetic multi-child run.

## Impact

- **Priority**: P3 — Nice-to-have visibility; no behavior change.
- **Effort**: Small — Two identical 8-line bash blocks.
- **Risk**: None — Output-only change; does not affect routing or file state.
- **Breaking Change**: No.

## Labels

`enhancement`, `recursive-refine`, `fsm-loops`, `observability`, `cli-output`

## Status

**Open** | Created: 2026-05-03 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-05-03T19:20:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ac7040e-7ed3-4fc9-8eb6-0a927d3649e8.jsonl`
- `/ll:capture-issue` - 2026-05-03T16:43:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81b5153d-e662-4abf-af0e-b3ec54065e0b.jsonl`
