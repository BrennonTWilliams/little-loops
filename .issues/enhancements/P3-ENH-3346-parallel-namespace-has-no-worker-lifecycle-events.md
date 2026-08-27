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
decision_needed: true
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

Only two `parallel.*` events are ever emitted: `parallel.worker_completed` (`orchestrator.py:1285`, on worker finish) and `parallel.epic_branch_stale` (`worker_pool.py:1979`, on stale-branch detection). A subscriber sees a worker only at the moment it finishes — there is no signal for spawn, blocked/waiting, merge outcome, or queue depth while a run is in progress.

## Expected Behavior

The orchestrator/worker-pool emit `parallel.worker_started`, `parallel.worker_blocked`, `parallel.worker_unblocked`, `parallel.merge_started`, `parallel.merge_completed`, and `parallel.queue_changed` from the state-change points that already know about them, each carrying `worker_id` and `issue_id`. A consumer subscribed to `parallel.*` can reconstruct active-worker count and per-worker status at any point in a run without reading `.issues/` or the filesystem.

## Motivation

The `parallel.*` namespace is documented in `docs/reference/EVENT-SCHEMA.md` as a first-class subsystem but is effectively write-only for terminal accounting today. That makes a wedged worker invisible — the single failure mode most worth watching (one worker stuck while the rest sail) produces no event at all until timeout — and makes any live dashboard/visualizer of an in-progress run impossible to build.

## Proposed Solution

Add six new event emissions alongside the existing two, at the orchestrator/worker-pool call sites that already own each state transition:

- `parallel.worker_started` — emitted where a worker claims an issue and its worktree/branch are known (near `_event_bus.emit()` in `orchestrator.py`, mirroring the `parallel.worker_completed` call at `orchestrator.py:1285`); payload adds `worktree_path`, `branch`.
- `parallel.worker_blocked` / `parallel.worker_unblocked` — paired events at the lock/worktree/dependency/rate-limit backoff wait points in `worker_pool.py`; payload adds a `reason` discriminator on `worker_blocked`.
- `parallel.merge_started` / `parallel.merge_completed` — emitted around the epic-branch merge path in `worker_pool.py` (near the existing `parallel.epic_branch_stale` emission at `worker_pool.py:1979`); `merge_completed` payload adds `outcome` (`merged`, `conflict`, `skipped`).
- `parallel.queue_changed` — emitted wherever the orchestrator's pending/active/done counts change; payload is the three counts.

Each new emitter builds its event dict inline via `self._event_bus.emit({...})`, following the existing `parallel.worker_completed`/`parallel.epic_branch_stale` pattern, and routes `run_id`/`loop` stamping through the mechanism landed by ENH-3345 rather than duplicating that logic here.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **Event dict convention**: every emit call builds a raw `dict` with `"event"` and `"ts"` (`datetime.now(UTC).isoformat()`) plus payload fields — no dataclass or schema. Two shapes coexist: inline-per-call-site (both current `parallel.*` emitters, `orchestrator.py:1285-1294`, `worker_pool.py:1979-1989`) and a shared `_emit(event_type, payload)` helper (`state.py:109-112`, `StateManager._emit`) that merges `{"event": event_type, "ts": _iso_now(), **payload}`. Either is an established convention here; `parallel/` specifically uses inline construction today.
- **`docs/reference/EVENT-SCHEMA.md` is not the schema source of truth for `docs/reference/schemas/`**: `scripts/little_loops/generate_schemas.py` hand-maintains a separate `SCHEMA_DEFINITIONS` dict that the `.json` files are generated from, and `test_generate_schemas.py` pins both a literal count (`== 42`) and an exact key set — both need updating alongside the markdown doc (see Integration Map findings).
- **Test pattern for new event coverage**: instantiate a real `EventBus`, register a list-appending lambda observer, invoke the method that should emit, assert on the captured dict — no mocking. `test_orchestrator.py::test_on_worker_complete_emits_event_on_success` (`:2706-2735`) and `test_worker_pool.py`'s `TestEpicBranchStaleEvent` class (`:4134-4210`, whose own docstring says it was "Modeled on test_orchestrator.py's" test) are the two precedents. Each also pairs a "no event bus attached" no-op test (`test_on_worker_complete_no_emission_without_event_bus`, `test_worker_pool.py:4249`).
- **No existing paired start/complete event family exists under `parallel.*`** to model the new pairs after — both current `parallel.*` events are single, non-paired emissions. The closest precedent elsewhere is FSM's `state_enter`/action-lifecycle events (`action_start`/`action_complete`/`action_error`), which share a dot-namespace prefix but no explicit shared correlation ID field like the proposed `worker_id`.

**Open decision: what `worker_id` actually is.** No such identifier exists today (see Program Design findings) — `WorkerPool` and its event tracks everything by `issue_id` or a worktree-derived `worker_name`. This must be resolved before the six emitters can be written consistently.

**Option A**: Alias `worker_id` to `issue_id`. Simplest — `WorkerPool._process_issue` processes exactly one issue per invocation and no worker-reassignment path exists in this codebase, so `issue_id` is already 1:1 and stable for a worker's full lifetime. No new state to introduce or thread through `IssuePriorityQueue`/`MergeCoordinator`. Downside: makes `worker_id` a redundant field alongside `issue_id` on every event (both proposed as required), which invites the question of why both exist.

**Option B**: Derive `worker_id` from the existing worktree name (`result.worktree_path.name`, already emitted as `worker_name` on `parallel.worker_completed`). Slightly more distinct from `issue_id` in spirit, but is computed later than dispatch time (the worktree is created inside `_process_issue`, `worker_pool.py:342-`) and would need to be threaded backward to a `parallel.worker_started` emission that fires at claim time, before the worktree necessarily exists.

**Recommended**: Option A for v1 — it requires no new state and matches how every other identity concept in `parallel/` (`_active_workers`, `_worker_stages`, `_pending_callbacks`) already keys on `issue_id`. If a future need for true worker-thread identity (independent of the issue being processed) emerges, it can be introduced then without disrupting this event surface's contract, since `worker_id == issue_id` is a valid instance of "stable for the worker's lifetime."

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — add `parallel.worker_started` and `parallel.queue_changed` emissions at the state-change points that already track worker claim and pending/active/done counts
- `scripts/little_loops/parallel/worker_pool.py` — add `parallel.worker_blocked`/`parallel.worker_unblocked` at the lock/worktree/dependency/rate-limit wait points, and `parallel.merge_started`/`parallel.merge_completed` around the epic-branch merge path
  > ⚠ Superseded — merge events belong in `merge_coordinator.py`, not `worker_pool.py`; see § Codebase Research Findings
- `docs/reference/EVENT-SCHEMA.md` — document each new event type and its payload table

### Dependent Files (Callers/Importers)
- Any subscriber of `self._event_bus` (event consumers, dashboards, `ll-events` tooling) — new event types are additive, so existing subscribers filtering on known `event` values are unaffected

### Similar Patterns
- `parallel.worker_completed` (`orchestrator.py:1285`) and `parallel.epic_branch_stale` (`worker_pool.py:1979`) are the existing `_event_bus.emit()` call sites to model the new emitters after
- ENH-3345's `run_id`/`loop` stamping mechanism, once landed, should be reused by these new emitters rather than duplicated

### Tests
- `scripts/tests/test_orchestrator.py` — add coverage asserting each new event fires with the expected payload at its trigger point
- `scripts/tests/test_worker_pool.py` — same, for the worker-pool-owned events (`worker_blocked`/`worker_unblocked`, `merge_started`/`merge_completed`)

### Documentation
- `docs/reference/EVENT-SCHEMA.md` — add payload tables for the six new event types
- `docs/reference/schemas/` — regenerate via `ll-generate-schemas` after the schema doc changes

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **Merge lifecycle lives in `merge_coordinator.py`, not `worker_pool.py`**: `MergeCoordinator._process_merge` (`scripts/little_loops/parallel/merge_coordinator.py:580`) sets `MergeStatus.IN_PROGRESS` — the true "merge started" instant. Outcome is decided in `_finalize_merge` (`:1033-1064`, success) or `_handle_failure` (`:1066-1080`, failure/conflict). `worker_pool.py` has no merge-processing code at all; only the existing `parallel.epic_branch_stale` emission lives there (`_ensure_epic_branch`, `:1948-1991`).
- **Queue depth counters live in `priority_queue.py`**: `IssuePriorityQueue` (`scripts/little_loops/parallel/priority_queue.py:22`) exposes `qsize()`, `in_progress_count`, `completed_count`, `failed_count`, `skipped_count` (`:173-224`), mutated by `add`/`get`/`mark_completed`/`mark_failed`/`mark_skipped`/`requeue` (`:50-144`). This class holds no `EventBus` reference today — it is not imported in `events.py` or vice versa. A `parallel.queue_changed` emitter needs either an `EventBus` threaded into `IssuePriorityQueue`, or the orchestrator emitting after each queue-mutating call it already makes.
- **"Blocked" is overlap-deferral in `orchestrator.py`, not a lock wait in `worker_pool.py`**: the only meaningful blocked/unblocked state transition is `ParallelOrchestrator._process_parallel` (`orchestrator.py:1021-1047`) deferring an issue to `self._deferred_issues` on overlap conflict, and `_requeue_deferred_issues` (`orchestrator.py:1296-1314`, invoked from `_on_worker_complete`) re-submitting it once clear. `worker_pool.py`'s only lock primitive is `GitLock._run_with_retry` (`git_lock.py:110-181`), a transient (<8s) retry loop on `index.lock` conflicts — not a semantic "worker blocked" state, and no rate-limit backoff exists in this package (rate-limit handling lives in the FSM executor, outside `parallel/`).
- **Worker dispatch (no existing emission point) is `_process_parallel`/`_process_sequential`** (`orchestrator.py:1021-1047`, `~1008`), which call `self.worker_pool.submit(issue, self._on_worker_complete)` — neither currently calls `EventBus.emit`, and `WorkerPool.submit()` (`worker_pool.py:278-304`) holds no `EventBus` reference at all.
- **`## Files to Modify` is missing two files this issue needs**: `scripts/little_loops/parallel/merge_coordinator.py` (merge_started/merge_completed) and `scripts/little_loops/parallel/priority_queue.py` (queue_changed, or the orchestrator call sites that invoke its mutators).
- **Schema regeneration is not markdown-driven**: `scripts/little_loops/generate_schemas.py` maintains its own hand-written `SCHEMA_DEFINITIONS` dict (`:82` onward, e.g. `parallel.worker_completed` at `:600`) that `docs/reference/schemas/*.json` is generated from — not parsed from `EVENT-SCHEMA.md`. `scripts/tests/test_generate_schemas.py::test_all_41_event_types_defined` pins `len(SCHEMA_DEFINITIONS) == 42` and `test_expected_event_types_present` pins the exact key set — both need updating for six new keys, in addition to `EVENT-SCHEMA.md`. Missing `generate_schemas.py`.

## Implementation Steps

1. Land ENH-3345 (run_id/loop stamping) first, since all new emitters route through it
2. Add `parallel.worker_started` and `parallel.queue_changed` emissions in `orchestrator.py`
3. Add `parallel.worker_blocked`/`parallel.worker_unblocked` and `parallel.merge_started`/`parallel.merge_completed` emissions in `worker_pool.py`
   > ⚠ Superseded — merge events belong in `merge_coordinator.py`, not `worker_pool.py`; see § Codebase Research Findings
4. Add/update tests asserting each event fires with the expected `worker_id`/`issue_id` payload
5. Document the six new event types in `docs/reference/EVENT-SCHEMA.md` and regenerate `docs/reference/schemas/` via `ll-generate-schemas`
6. Verify a `parallel.*` subscriber can reconstruct active-worker count and per-worker status from the event stream alone

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- Step 3 as written ("Add ... emissions in `worker_pool.py`") is incomplete: `parallel.merge_started`/`parallel.merge_completed` belong in `scripts/little_loops/parallel/merge_coordinator.py` (`_process_merge`, `_finalize_merge`, `_handle_failure`), not `worker_pool.py`, which has no merge-processing code. `parallel.queue_changed` needs `scripts/little_loops/parallel/priority_queue.py`'s count properties wired to an `EventBus` it does not currently hold. See Integration Map findings for the corrected file list.
- Step 5 ("Document ... in `docs/reference/EVENT-SCHEMA.md` and regenerate ... via `ll-generate-schemas`") also requires updating `scripts/little_loops/generate_schemas.py`'s `SCHEMA_DEFINITIONS` dict and `scripts/tests/test_generate_schemas.py`'s pinned count/key-set — `ll-generate-schemas` reads from that dict, not from the markdown doc.

## Program Design

### Types

- `WorkerBlockedReason: Literal["lock", "worktree", "dependency", "rate_limit"]`
- `MergeOutcome: Literal["merged", "conflict", "skipped"]`

### Signatures

- `Orchestrator._emit_worker_started(self, issue_id: str, worker_id: str, worktree_path: Path, branch: str) -> None`
- `Orchestrator._emit_queue_changed(self, pending: int, active: int, done: int) -> None`
- `WorkerPool._emit_worker_blocked(self, worker_id: str, issue_id: str, reason: WorkerBlockedReason) -> None`
- `WorkerPool._emit_worker_unblocked(self, worker_id: str, issue_id: str) -> None`
- `WorkerPool._emit_merge_started(self, worker_id: str, issue_id: str, branch: str) -> None`
- `WorkerPool._emit_merge_completed(self, worker_id: str, issue_id: str, outcome: MergeOutcome) -> None`

### Call Path

`ParallelOrchestrator._process_parallel`/`_process_sequential` (`orchestrator.py:1021-1047`, `~1008` — actual dispatch call, no existing emission point) -> `WorkerPool.submit()` (`worker_pool.py:278-304`) -> ... -> `ParallelOrchestrator._on_worker_complete` (`orchestrator.py:1077-1294`) -> `self._event_bus.emit(...)` (existing `parallel.worker_completed` call at `orchestrator.py:1285-1294`). Corrected from `Orchestrator._run_worker`, which does not exist — see Codebase Research Findings below.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **`worker_id` does not exist anywhere in `scripts/little_loops/parallel/`** (confirmed by grep — zero matches). The existing `parallel.worker_completed` event uses `worker_name` (`result.worktree_path.name`, e.g. `ll-worker-BUG-007-abc123`) derived from the worktree directory, not an independent identity. `WorkerPool` tracks live work exclusively keyed on `issue_id` (`_active_workers[issue.issue_id]`, `worker_pool.py:296-297`; `_worker_stages`, `:2004-2024`). There is no persistent "worker object" or slot — a `ThreadPoolExecutor` thread may be reused across issues, but that reuse is invisible to application code, and `WorkerPool._process_issue` (`:342-`) processes exactly one issue per invocation, so no reassignment case exists to worry about. `worker_id` as this issue proposes it is a new concept that needs an explicit definition before implementation, not a rename of something already tracked.
- **`EventBus.emit()` (`scripts/little_loops/events.py:117-138`) does no schema validation, required-field checking, or run_id/loop stamping** — it takes a raw `dict[str, Any]`, reads only `event["event"]` to route to filtered observers, and passes every other field through untouched. Any `worker_id`/`issue_id` presence guarantee this issue wants is enforced by convention at each call site, not by the bus.
- **`_run_worker` does not exist.** The Call Path above has been corrected to the confirmed dispatch/completion methods.
- **Signatures section's owning classes are wrong for the merge pair.** `_emit_merge_started`/`_emit_merge_completed` are listed under `WorkerPool`, but merge processing lives entirely in `MergeCoordinator` (`merge_coordinator.py`) — `_process_merge` (`:580`, sets `MergeStatus.IN_PROGRESS`), `_finalize_merge` (`:1033-1064`), `_handle_failure` (`:1066-1080`). `worker_pool.py` has no merge code. Likewise `_emit_queue_changed` has no natural home on `Orchestrator`/`WorkerPool` — the counts it needs (`qsize()`, `in_progress_count`, `completed_count`, `failed_count`, `skipped_count`) live on `IssuePriorityQueue` (`priority_queue.py:173-224`), which holds no `EventBus` reference today.

## Impact

- **Priority**: P3 - Observability gap, not a correctness bug; no user-facing failure today, but blocks building a live run visualizer
- **Effort**: Medium - Six new emitters following an established pattern (`_event_bus.emit()`), plus doc/schema regeneration and test coverage; scoped by depending on ENH-3345 landing first
- **Risk**: Low - Additive events only; no changes to existing `parallel.worker_completed`/`parallel.epic_branch_stale` payloads or to control flow
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-27 | Priority: P3

## Success Metrics

A `parallel.*` subscriber can render active-worker count, per-worker status, and merge outcome for an in-progress run without polling `.issues/` or the filesystem; a worker stuck for its full timeout produces at least one `parallel.worker_blocked` event before that timeout fires.

## Scope Boundaries

Out of scope: building the dashboard/visualizer consumer itself (this issue only adds the emitters); changing the payload or emission point of the existing `parallel.worker_completed`/`parallel.epic_branch_stale` events; adding lifecycle events outside the `parallel.*` namespace (e.g. FSM state-transition events); retrofitting historical runs with these events after the fact.

## API/Interface

```python
# New parallel.* event payloads (all include worker_id, issue_id)
{"event": "parallel.worker_started", "worker_id": str, "issue_id": str, "worktree_path": str, "branch": str}
{"event": "parallel.worker_blocked", "worker_id": str, "issue_id": str, "reason": str}
{"event": "parallel.worker_unblocked", "worker_id": str, "issue_id": str}
{"event": "parallel.merge_started", "worker_id": str, "issue_id": str, "branch": str}
{"event": "parallel.merge_completed", "worker_id": str, "issue_id": str, "outcome": str}
{"event": "parallel.queue_changed", "pending": int, "active": int, "done": int}
```


## Session Log
- `/ll:refine-issue` - 2026-08-27T20:10:28 - `9e4fa033-0b0b-43cd-be66-950ccb670df0.jsonl`
- `/ll:refine-issue` - 2026-08-27T20:10:19 - `3cf55431-2b3c-40fa-ad5c-a3fd2b0789ab.jsonl`
- `/ll:format-issue` - 2026-08-27T20:01:01 - `e13ddb3f-38f3-4515-910f-59c195a89ea8.jsonl`
- `/ll:capture-issue` - 2026-08-27T19:56:52 - `f1d9d0f2-280e-4e9e-bb4a-45c14f878f7b.jsonl`
