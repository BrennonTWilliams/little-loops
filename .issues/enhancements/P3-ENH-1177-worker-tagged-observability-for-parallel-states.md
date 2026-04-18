---
discovered_date: "2026-04-18"
discovered_by: parallel-fsm-review
depends_on: [FEAT-1075, FEAT-1076]
---

# ENH-1177: Worker-Tagged Observability for Parallel States

## Summary

Attach worker identity (`item_index` + optional `item_label`) to every event emitted from inside a parallel worker, so that event logs, CLI output, and downstream consumers can reconstruct per-worker timelines and correlate interleaved activity back to specific items. Today, events from 4 concurrent workers arrive interleaved in a single stream with no way to tell them apart.

## Current Behavior (as of FEAT-1075 / FEAT-1076)

When `ParallelRunner` fans out 4 workers, each worker constructs an `FSMExecutor` and passes the same `event_callback` through. Events emitted from workers (state entry/exit, capture writes, routing decisions) arrive at the parent's event stream in arrival order, interleaved, with no field indicating which worker produced them.

The existing `_depth` tracking (used for sub-loops) hints at nesting level but does not disambiguate siblings: two workers both at `_depth: 1` produce indistinguishable events. CLI log output looks like:

```
[fan_out] State: refine → evaluating
[fan_out] State: refine → evaluating
[fan_out] State: refine → refining
[fan_out] State: refine → evaluating
[fan_out] State: refine → refining
```

There is no way to answer: "which worker processed issue FEAT-1042?" or "what state is worker 3 currently in?" — short of grepping captures after the fact.

## Expected Behavior

Every event emitted from inside a parallel worker carries:
- `worker_index: int` — 0-based position in `items`
- `worker_label: str | None` — the item value itself when it's a string (e.g., the issue ID "FEAT-1042"), truncated to a reasonable length; None when the item is a complex object
- `parallel_state: str` — the name of the parent parallel state (e.g., `"fan_out"`)

These fields flow through as structured metadata on events, not as free-text prefixes on message strings. CLI display rendering (`layout.py`) uses them to format per-worker lines:

```
[fan_out:0 FEAT-1042] State: refine → evaluating
[fan_out:1 FEAT-1043] State: refine → evaluating
[fan_out:2 FEAT-1044] State: refine → refining
[fan_out:3 FEAT-1045] State: refine → evaluating
```

Event consumers (persistence, analysis tools) can group events by `(parallel_state, worker_index)` to reconstruct per-worker timelines.

## Use Case

**Who**: An engineer debugging a parallel fan-out where 1 of 10 workers hung.

**Context**: Event logs show 9 workers reaching `done` and activity falling quiet, but the overall loop is still running. Which worker is stuck? What state is it in? Today this requires cross-referencing timestamps and guessing.

**Goal**: Filter the event log by `worker_index` to see exactly which item's worker is stuck and what state it last entered.

## Proposed Solution

### 1. Event schema extension

`Event` dataclass (wherever it lives in `fsm/`) gains optional `worker_index: int | None = None`, `worker_label: str | None = None`, `parallel_state: str | None = None` fields. All are None for non-parallel contexts (existing callers unchanged).

### 2. Callback wrapping in `ParallelRunner`

When `ParallelRunner._run_worker(item_index, item, ...)` constructs the child `FSMExecutor`, it wraps the parent's `event_callback` in a worker-tagging wrapper (analogous to the existing `_sub_event_callback` depth wrapper at `executor.py:354-361`):

```python
def _worker_event_callback(event: Event) -> None:
    event.worker_index = item_index
    event.worker_label = str(item)[:64] if isinstance(item, str) else None
    event.parallel_state = parallel_state_name
    parent_event_callback(event)
```

### 3. CLI display updates

`cli/loop/layout.py` rendering logic detects events with `worker_index is not None` and formats them with the `[parallel_state:index label]` prefix shown above. Non-parallel events render unchanged.

### 4. Event log consumers

Event persistence (JSONL output, analysis tools) naturally inherits the new fields; no changes needed beyond re-running schema regeneration (`ll-generate-schemas`).

## Use With Existing Tools

- `ll-history` and `ll-messages` can filter on `worker_index` for parallel-specific analysis
- `analyze_log` skill can group events by `(parallel_state, worker_index)` for per-worker timeline reconstruction

## Files to Modify

- `scripts/little_loops/fsm/events.py` (or wherever `Event` is defined) — add 3 fields
- `scripts/little_loops/fsm/parallel_runner.py` — wrap callback per worker
- `scripts/little_loops/cli/loop/layout.py` — render worker-tagged events
- `docs/reference/schemas/` — regenerate event schemas

## Dependencies

- **Hard blockers**: FEAT-1075 (runner), FEAT-1076 (dispatch)
- **Coordinates with**: FEAT-1081 (CLI display for parallel states — this adds the per-worker rendering layer on top of 1081's static display)

## Acceptance Criteria

- Events emitted from inside a parallel worker carry `worker_index`, `worker_label`, `parallel_state` fields
- CLI display shows per-worker tagging when events have these fields
- Non-parallel events are rendered unchanged (no `[:0 ]` noise for normal loops)
- `item_label` truncation handles non-string items (set to None) and long strings (max 64 chars)
- Event schema regenerated and docs updated
- Tests: worker-tagged events rendered correctly; non-parallel unchanged; label truncation; non-string item produces None label

## Impact

- **Priority**: P3 — Observability/debuggability; not a correctness blocker, but the first real debugging session on a parallel fan-out will make this feel critical
- **Effort**: Small-to-Medium — schema field addition + wrapper + renderer updates + schema regen
- **Risk**: Low — Additive event fields; non-parallel callers unaffected
- **Breaking Change**: No — fields are optional; consumers that ignore them continue to work

## Labels

`fsm`, `parallel`, `observability`, `events`, `cli`, `debugging`

---

## Session Log
- `parallel-fsm-review` - 2026-04-18T00:00:00Z - spawned during parallel feature review discussion

---

**Open** | Created: 2026-04-18 | Priority: P3
