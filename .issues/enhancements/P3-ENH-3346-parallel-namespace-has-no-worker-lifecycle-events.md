---
id: ENH-3346
type: ENH
title: parallel namespace has no worker lifecycle events
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T19:56:34Z'
depends_on:
- ENH-3345
---

# ENH-3346: parallel namespace has no worker lifecycle events

## Summary

The `parallel.*` event namespace is documented in `docs/reference/EVENT-SCHEMA.md` as a first-class subsystem, but only two events are ever emitted across the whole `scripts/little_loops/parallel/` package:

- `parallel.worker_completed` — `parallel/orchestrator.py:1285` (fields: `issue_id`, `worker_name`, `status`, `duration_seconds`)
- `parallel.epic_branch_stale` — `parallel/worker_pool.py:1979` (fields: `branch`, `base`, `commits_behind`, `mode`, `action`)

(The third `_event_bus.emit()` call site, `orchestrator.py:1835`, emits `issue.closed` — an issue-lifecycle event, not a `parallel.*` one.)

So an observer sees a worker only when it *finishes*. There is no spawn event, no blocked/waiting event, no merge outcome, and no queue-depth signal. That makes the namespace effectively write-only for terminal accounting and unusable for any live view of a run in progress: a dashboard or realtime visualizer cannot show how many workers are active, which issue each one holds, which are stalled on worktree contention or a rate-limit backoff, or whether a merge succeeded — until after the fact.

It also means a wedged worker is invisible. The single failure mode most worth watching (one worker stuck while the rest sail) produces no event at all until timeout.

Proposed additions to the `parallel.*` surface, each carrying `worker_id` (stable for the worker's lifetime) and `issue_id`:

- `parallel.worker_started` — worker claimed an issue; include worktree path and branch
- `parallel.worker_blocked` — waiting on a lock, worktree, dependency, or rate-limit backoff; include a reason discriminator
- `parallel.worker_unblocked` — paired resume
- `parallel.merge_started` / `parallel.merge_completed` — with outcome (`merged`, `conflict`, `skipped`) so merge-gate stalls are visible
- `parallel.queue_changed` — pending/active/done counts, so a consumer can render progress without replaying history

Depends on the sibling `run_id`/`loop` stamping issue: these emitters build their dicts inline rather than routing through `FSMExecutor._emit()`, so they need run-scoped identity applied here too, or they stay uncorrelatable in a merged stream.

Acceptance: each new event type is emitted from the orchestrator/worker-pool paths that already know the state change; every `parallel.*` event carries `worker_id` and `issue_id`; a consumer subscribed to `parallel.*` can reconstruct active-worker count and per-worker status at any point in a run without reading `.issues/` or the filesystem; `docs/reference/EVENT-SCHEMA.md` documents each new type with its payload table; `docs/reference/schemas/` regenerated via `ll-generate-schemas`.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Current Pain Point

## Success Metrics

## Scope Boundaries

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:capture-issue` - 2026-08-27T19:56:52 - `f1d9d0f2-280e-4e9e-bb4a-45c14f878f7b.jsonl`
