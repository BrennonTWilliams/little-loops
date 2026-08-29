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
- BUG-3348
relates_to:
- FEAT-3323
decision_needed: false
reconcile_attempted: true
confidence_score: 90
verify_verdict: NON_VALID
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
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

- `parallel.worker_started` — worker began processing an issue (emitted just after worktree creation); include worktree path and branch
- `parallel.worker_blocked` — issue deferred on overlap conflict (the only real blocked transition in `parallel/`); include a `reason` discriminator (`Literal["overlap"]`, extensible)
- `parallel.worker_unblocked` — paired resume on requeue
- `parallel.merge_started` / `parallel.merge_completed` — with outcome (`merged`, `failed`) plus an `error` string so merge-gate stalls are visible
- `parallel.queue_changed` — the five queue counters (pending/active/completed/failed/skipped), so a consumer can render progress without replaying history

Run-scoped identity: ENH-3345 landed (`d712e20b4`), but its stamping mechanism lives in `FSMExecutor._emit()`, which `parallel/` emitters never route through — it cannot be reused here. Instead, stamp `run_id` inline from `ParallelOrchestrator.run_id` (already exists, `orchestrator.py:123`) and thread it into `MergeCoordinator`/`IssuePriorityQueue` alongside `event_bus`; omit `loop`, which has no meaning for a parallel run.

Acceptance: see the formal `## Acceptance Criteria` section below (lifted from this summary and Success Metrics).


## Current Behavior

Only two `parallel.*` events are ever emitted: `parallel.worker_completed` (`orchestrator.py:1285`, on worker finish) and `parallel.epic_branch_stale` (`worker_pool.py:1979`, on stale-branch detection). A subscriber sees a worker only at the moment it finishes — there is no signal for spawn, blocked/waiting, merge outcome, or queue depth while a run is in progress.

## Expected Behavior

The orchestrator, worker pool, priority queue, and merge coordinator emit `parallel.worker_started`, `parallel.worker_blocked`, `parallel.worker_unblocked`, `parallel.merge_started`, `parallel.merge_completed`, and `parallel.queue_changed` from the state-change points that already know about them — every event carrying `run_id`, and each worker-scoped event (all but `queue_changed`) carrying `worker_id` and `issue_id`. A consumer subscribed to `parallel.*` can reconstruct active-worker count and per-worker status at any point in a run without reading `.issues/` or the filesystem (parallel-dispatched issues; sequential/P0 lacks `worker_completed` — see Scope Boundaries).

## Motivation

The `parallel.*` namespace is documented in `docs/reference/EVENT-SCHEMA.md` as a first-class subsystem but is effectively write-only for terminal accounting today. That makes a wedged worker invisible — the single failure mode most worth watching (one worker stuck while the rest sail) produces no event at all until timeout — and makes any live dashboard/visualizer of an in-progress run impossible to build.

## Proposed Solution

Add six new event emissions alongside the existing two, at the orchestrator/worker-pool call sites that already own each state transition:

- `parallel.worker_started` — emitted from `WorkerPool._process_issue` immediately after worktree creation, when `worktree_path`/`branch` are known (see Program Design timing decision); payload adds `worktree_path`, `branch`.
- `parallel.worker_blocked` / `parallel.worker_unblocked` — paired events at the overlap-deferral point in `ParallelOrchestrator._process_parallel` and the resubmit point in `_requeue_deferred_issues`; payload adds a `reason` discriminator (`Literal["overlap"]`) on `worker_blocked`. **`worker_unblocked` must be gated on the requeue actually succeeding** — see the BUG-3348 blocker in Pre-Implementation Review Findings: today `_requeue_deferred_issues` calls `queue.add()`, which silently returns `False` for any deferred issue (it is still in `_in_progress`), dropping it. Emit `worker_unblocked` only after a successful re-add (post-fix: `queue.requeue()`), never unconditionally at the call site.
- `parallel.merge_started` / `parallel.merge_completed` — emitted from `MergeCoordinator._process_merge` and `_finalize_merge`/`_handle_failure`. **Placement**: emit `merge_started` at the **top of `_process_merge`, before the circuit-breaker check** — not at the `MergeStatus.IN_PROGRESS` assignment. `_process_merge` calls `_handle_failure` *before* IN_PROGRESS is set when `self._paused` (`merge_coordinator.py:597-603`), so an IN_PROGRESS-anchored emit would produce `merge_completed(failed)` with no preceding `merge_started` on the paused-skip path. **Retry gating**: `_process_merge` re-runs the *same* `MergeRequest` on `MergeStatus.RETRYING` (`merge_coordinator.py:938,1031` requeue it), so `merge_started` must be gated on `request.retry_count == 0` — retries do not re-emit `merge_started`. Note `_handle_failure` *can* fire with `retry_count >= 1` (used-merge-strategy `:838`, stash-pop conflict `:936`, rebase-failed path) — pairing still holds because `merge_started` fired on attempt 0 and `_handle_failure` is terminal (fires at most once per request). `merge_completed` payload adds `outcome` (`Literal["merged","failed"]`) plus `error: str | None` (`None` on success) — see MergeOutcome rationale in Program Design Types.
- `parallel.queue_changed` — emitted from *inside* `IssuePriorityQueue`'s six mutators (`add`/`get`/`mark_completed`/`mark_failed`/`mark_skipped`/`requeue`), not from orchestrator call sites; payload is the five counters (pending/active/completed/failed/skipped). Rationale: the orchestrator has ~15 scattered mutating call sites across both the parallel and sequential paths (`orchestrator.py:909,934,1019,1120-1138,1220-1234,1312,1551-1599`) and any future mutator call would silently drift out of coverage; the queue's mutators are a single choke point covering both modes. Emit *outside* the queue's internal lock (build the payload under the lock, call `emit()` after releasing) so a re-entrant observer cannot deadlock. `add_many` emits **once** after the batch, not N times (override or emit-suppression flag on the inner `add` calls). **`get()` emits only on a successful dequeue** — the orchestrator main loop polls `get(block=False)` on every iteration (`orchestrator.py:934`), so an unconditional emit would flood the bus with identical events from empty polls; likewise `add()` does not emit when it returns `False` (rejected duplicate — no counter changed). The resume-path bulk loaders `load_completed`/`load_failed` (`priority_queue.py:225-241`) also mutate the counters and **emit one `queue_changed` each** after their batch update, so post-resume counters are truthful from the first event.

Each new emitter builds its event dict inline via `self._event_bus.emit({...})`, following the existing `parallel.worker_completed`/`parallel.epic_branch_stale` pattern, and stamps `run_id` from `ParallelOrchestrator.run_id` (threaded into `MergeCoordinator`/`IssuePriorityQueue` alongside `event_bus`). ENH-3345's `FSMExecutor._emit()` stamping is FSM-path-only and is not reused here; `loop` is omitted since it has no meaning for a parallel run. Additionally, add the same `run_id` stamp to the two existing emitters (`parallel.worker_completed`, `parallel.epic_branch_stale`) — an additive field, explicitly in scope (see Scope Boundaries), since correlation across a merged stream is the point of this issue.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **Event dict convention**: every emit call builds a raw `dict` with `"event"` and `"ts"` (`datetime.now(UTC).isoformat()`) plus payload fields — no dataclass or schema. Two shapes coexist: inline-per-call-site (both current `parallel.*` emitters, `orchestrator.py:1285-1294`, `worker_pool.py:1979-1989`) and a shared `_emit(event_type, payload)` helper (`state.py:109-112`, `StateManager._emit`) that merges `{"event": event_type, "ts": _iso_now(), **payload}`. Either is an established convention here; `parallel/` specifically uses inline construction today.
- **`docs/reference/EVENT-SCHEMA.md` is not the schema source of truth for `docs/reference/schemas/`**: `scripts/little_loops/generate_schemas.py` hand-maintains a separate `SCHEMA_DEFINITIONS` dict that the `.json` files are generated from, and `test_generate_schemas.py` pins both a literal count (`== 42`) and an exact key set — both need updating alongside the markdown doc (see Integration Map findings).
- **Test pattern for new event coverage**: instantiate a real `EventBus`, register a list-appending lambda observer, invoke the method that should emit, assert on the captured dict — no mocking. `test_orchestrator.py::test_on_worker_complete_emits_event_on_success` (`:2706-2735`) and `test_worker_pool.py`'s `TestEpicBranchStaleEvent` class (`:4134-4210`, whose own docstring says it was "Modeled on test_orchestrator.py's" test) are the two precedents. Each also pairs a "no event bus attached" no-op test (`test_on_worker_complete_no_emission_without_event_bus`, `test_worker_pool.py:4249`).
- **No existing paired start/complete event family exists under `parallel.*`** to model the new pairs after — both current `parallel.*` events are single, non-paired emissions. The closest precedent elsewhere is FSM's `state_enter`/action-lifecycle events (`action_start`/`action_complete`/`action_error`), which share a dot-namespace prefix but no explicit shared correlation ID field like the proposed `worker_id`.

**Open decision: what `worker_id` actually is.** No such identifier exists today (see Program Design findings) — `WorkerPool` and its event tracks everything by `issue_id` or a worktree-derived `worker_name`. This must be resolved before the six emitters can be written consistently.

**Option A**: Alias `worker_id` to `issue_id`.
> **Selected:** Option A — every existing worker-tracking structure and the prior lifecycle event already key on `issue_id`; no new state required. Simplest — `WorkerPool._process_issue` processes exactly one issue per invocation and no worker-reassignment path exists in this codebase, so `issue_id` is already 1:1 and stable for a worker's full lifetime. No new state to introduce or thread through `IssuePriorityQueue`/`MergeCoordinator`. Downside: makes `worker_id` a redundant field alongside `issue_id` on every event (both proposed as required), which invites the question of why both exist.

**Option B**: Derive `worker_id` from the existing worktree name (`result.worktree_path.name`, already emitted as `worker_name` on `parallel.worker_completed`). Slightly more distinct from `issue_id` in spirit, but is computed later than dispatch time (the worktree is created inside `_process_issue`, `worker_pool.py:342-`) and would need to be threaded backward to a `parallel.worker_started` emission that fires at claim time, before the worktree necessarily exists.

**Recommended**: Option A for v1 — it requires no new state and matches how every other identity concept in `parallel/` (`_active_workers`, `_worker_stages`, `_pending_callbacks`) already keys on `issue_id`. If a future need for true worker-thread identity (independent of the issue being processed) emerges, it can be introduced then without disrupting this event surface's contract, since `worker_id == issue_id` is a valid instance of "stable for the worker's lifetime."

### Decision Rationale

**Selected**: Option A — alias `worker_id` to `issue_id`.

Every worker-tracking structure in `worker_pool.py` (`_active_workers`, `_pending_callbacks`, `_worker_stages`, `_active_processes`, `_worker_epic_branches`) is already keyed on `issue_id`, and `WorkerPool._process_issue` handles exactly one issue per invocation with no reassignment path — `issue_id` is already 1:1 and stable for a worker's full lifetime. Option B (deriving `worker_id` from the worktree name) has a timing mismatch: dispatch happens in `orchestrator.py`'s `_process_parallel`/`_process_sequential` before any worktree exists, so a `worker_started` event fired at true dispatch time cannot use a worktree-derived ID without either delaying the event or duplicating naming logic to precompute one.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — alias to `issue_id` | 3 | 3 | 3 | 3 | 12/12 |
| B — derive from worktree name | 1 | 0 | 1 | 1 | 3/12 |

Key evidence: `worker_pool.py:187,297` (`_active_workers` keyed by `issue_id`), `worker_pool.py:200,2012,2024,2048` (`_worker_stages` keyed by `issue_id`), `worker_pool.py:278-304` (`submit()` takes one `IssueInfo`, no reassignment), `worker_pool.py:352-362` (worktree/timestamp not computed until inside `_process_issue`, after dispatch), `orchestrator.py:1287-1293` (existing `worker_completed` event's only precedent for worker identity).

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — add `parallel.worker_blocked`/`parallel.worker_unblocked` at the overlap-deferral (`_process_parallel`) and requeue (`_requeue_deferred_issues`) points — the only real blocked/unblocked transition in `parallel/`; stamp `run_id` on the existing `parallel.worker_completed` emitter (`queue_changed` is NOT emitted from orchestrator call sites — see priority_queue.py entry)
- `scripts/little_loops/parallel/worker_pool.py` — add `parallel.worker_started` emission in `_process_issue` immediately after worktree creation; stamp `run_id` on the existing `parallel.epic_branch_stale` emitter (requires threading `run_id` into `WorkerPool` alongside its existing `event_bus`)
- `scripts/little_loops/parallel/merge_coordinator.py` — add `parallel.merge_started` in `_process_merge` (gated on `request.retry_count == 0` — retries re-enter `_process_merge` and must not re-emit) and `parallel.merge_completed` in `_finalize_merge`/`_handle_failure` (outcome `merged`/`failed` + `error`)
- `scripts/little_loops/parallel/priority_queue.py` — add `event_bus`/`run_id` support and emit `parallel.queue_changed` from inside `add`/`get`/`mark_completed`/`mark_failed`/`mark_skipped`/`requeue` plus `load_completed`/`load_failed` (decision resolved: queue-side, not orchestrator-side — single choke point covering both parallel and sequential paths; emit outside the internal lock; `add_many` and the two loaders coalesce to one event per batch; `get()` emits only on successful dequeue, `add()` only when it returns `True`)
- `scripts/little_loops/generate_schemas.py` — add the six new event types to `SCHEMA_DEFINITIONS`
- `docs/reference/EVENT-SCHEMA.md` — document each new event type and its payload table

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/observability/schema.py` — add six new `@dataclass(frozen=True)` `DESVariant` subclasses to the `DES_VARIANTS` registry (pattern: `ParallelWorkerCompletedVariant` `:505`/`ParallelEpicBranchStaleVariant` `:514`; `DES_VARIANTS` registry at `:657`, existing parallel entries `:718-719`); without these, `test_des_schema.py::test_variants_cover_all_schema_definitions` fails listing the six new `parallel.*` types as missing [Agent 1/2 finding]

### Dependent Files (Callers/Importers)
- Any subscriber of `self._event_bus` (event consumers, dashboards, `ll-events` tooling) — new event types are additive, so existing subscribers filtering on known `event` values are unaffected

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/priority_queue.py` — `IssuePriorityQueue.__init__` (`:40-48`) takes no `event_bus` param today (constructor has no args at all); `parallel.queue_changed` needs `event_bus: EventBus | None = None` added, mirroring `WorkerPool.__init__`'s existing pattern [Agent 2 finding]
- `scripts/little_loops/parallel/merge_coordinator.py` — `MergeCoordinator.__init__` (`:47-53`) takes `config, logger, repo_path, git_lock` with no `event_bus` param; `parallel.merge_started`/`parallel.merge_completed` need it added the same way [Agent 2 finding]
- `scripts/little_loops/parallel/orchestrator.py:132,147-149` — `self.queue = IssuePriorityQueue()` and `self.merge_coordinator = MergeCoordinator(parallel_config, self.logger, self.repo_path, self._git_lock)` are the sole instantiation sites; both need `event_bus=self._event_bus` threaded in, mirroring the existing `WorkerPool(...)` wiring three lines above (comment: "so parallel.epic_branch_stale reaches the same bus/transports as parallel.worker_completed") [Agent 2 finding]
- `scripts/tests/test_priority_queue.py:34`, `scripts/tests/test_issue_workflow_integration.py:265` — construct `IssuePriorityQueue()` with no args; new `queue_changed` tests need a bus-injected fixture variant [Agent 2 finding]

### Similar Patterns
- `parallel.worker_completed` (`orchestrator.py:1285`) and `parallel.epic_branch_stale` (`worker_pool.py:1979`) are the existing `_event_bus.emit()` call sites to model the new emitters after
- ENH-3345's stamping landed in `FSMExecutor._emit()` (FSM path only) and is NOT reusable here — parallel emitters stamp `run_id` inline from `ParallelOrchestrator.run_id` (`orchestrator.py:123`), threaded into `WorkerPool`/`MergeCoordinator`/`IssuePriorityQueue` alongside `event_bus`

### Tests
- `scripts/tests/test_orchestrator.py` — add coverage asserting `worker_blocked` and `worker_unblocked` each fire with the expected payload at their trigger point, and that the existing `worker_completed` event now carries `run_id` (`queue_changed` coverage lives in `test_priority_queue.py` since emission is queue-side)
- `scripts/tests/test_worker_pool.py` — add coverage asserting `worker_started` fires from `_process_issue` after worktree creation with `worktree_path`/`branch`, and that `epic_branch_stale` now carries `run_id`
- `scripts/tests/test_generate_schemas.py` — bump the four pinned `== 42` counts to `== 48` and extend `test_expected_event_types_present`'s literal set with the six new `parallel.*` keys

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_des_schema.py` — `test_variants_count_meets_minimum` (`:30-41`, `len(DES_VARIANTS) >= len(SCHEMA_DEFINITIONS)`) and `test_variants_cover_all_schema_definitions` (`:43-54`) will fail once `SCHEMA_DEFINITIONS` gains six entries, until matching `DESVariant` classes exist in `observability/schema.py` [Agent 1/2 finding]
- `scripts/tests/test_generate_schemas.py` — four pinned-count assertions break (42→48): `test_all_41_event_types_defined` (`:17-19`), `test_creates_41_files` (`:73-77`), `test_creates_output_dir_if_missing` (`:79-84`), `TestGenerateSchemasCLI.test_cli_creates_files` (`:207-213`); plus `test_expected_event_types_present` (`:21-67`)'s literal `expected` set needs the six new `parallel.*` strings [Agent 2/3 finding]
- `scripts/tests/test_merge_coordinator.py` — no existing `EventBus`/event-emission tests (confirmed via grep, zero hits); add a new test class for `merge_started`/`merge_completed` following `test_worker_pool.py`'s `TestEnsureEpicBranchEventEmission` template (`:4133-4277`) — real `EventBus()`, lambda observer, assert on captured dict [Agent 3 finding]
- `scripts/tests/test_priority_queue.py` — no existing `EventBus`/event-emission tests; add a new test class for `queue_changed` (same template), plus a bus-injectable fixture variant since the current fixture (`:34`) builds `IssuePriorityQueue()` with no args [Agent 3 finding]

### Documentation
- `docs/reference/EVENT-SCHEMA.md` — add payload tables for the six new event types
- `docs/reference/schemas/` — regenerate via `ll-generate-schemas` after the schema doc changes

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md` has three additional enumeration sites beyond the subsystem section itself, each listing only the two existing parallel events today: the `## Reserved Event Names`/`## Machine-Readable Schemas` file-tree block (`:1379-1423`), the `### Naming Convention` table (`:1429-1435`), and the `## Quick Reference` table (`:1545-1546`, sourced to `parallel/orchestrator.py`/`parallel/worker_pool.py` — new rows must also cite `merge_coordinator.py`/`priority_queue.py`) [Agent 2 finding]
- `docs/reference/API.md:4097,7871` — line 7871's prose bullet hardcodes the current `parallel.*` names (`parallel.worker_completed`, `parallel.epic_branch_stale`); line 4097 shows a no-arg `IssuePriorityQueue()` example that goes stale once `event_bus` is added to the constructor [Agent 2 finding]
- `docs/observability/des-audit.md` — generated report (`<!-- DO NOT EDIT - generated by ll-verify-des-audit -->`); regenerate via `ll-verify-des-audit` (`scripts/little_loops/cli/verify_des_audit.py`) after `DES_VARIANTS` is updated — do not hand-edit [Agent 2 finding]
- `CONTRIBUTING.md:784-798` — the "Event Schema Maintenance" checklist's 4 steps don't mention updating `DES_VARIANTS`, an existing process gap this issue's implementation will hit directly [Agent 2 finding]

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

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **`docs/reference/EVENT-SCHEMA.md` line citations are stale** (file changed 2026-08-27T21:54 UTC, after this issue's prior refine pass): the "Reserved Event Names" heading is now at line 1367; the "Machine-Readable Schemas" file-tree block now runs lines 1383-1427 (`parallel_epic_branch_stale.json`/`parallel_worker_completed.json` entries at 1412-1413); the `### Naming Convention` table's `parallel.*` rows are now at lines 1438-1439; the `## Quick Reference` heading moved to line 1495, with its `parallel.*` rows now at lines 1549-1550. No new event types were added by the intervening change — it was a prose-only update to existing events for ENH-3345 (run_id/loop stamping); the sections this issue targets are structurally unchanged, only shifted ~4 lines.
- **`ParallelWorkerCompletedVariant` (`scripts/little_loops/observability/schema.py:505-509`) does not mirror the full wire payload**: it models only `issue_id`/`status`, omitting `worker_name` and `duration_seconds` that `orchestrator.py:1287-1293` actually emits. The six new `DESVariant` subclasses this issue's wiring phase adds should decide per-field inclusion deliberately — 1:1 payload parity is not the existing convention for `parallel.*` variants.

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- `scripts/little_loops/cli/parallel.py:316,333` — constructs `EventBus()` and passes `event_bus=event_bus` into `ParallelOrchestrator.__init__`; confirms the six new emitters will reach the same runtime bus/transports as the existing `parallel.*` events with no further CLI wiring changes needed

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **EVENT-SCHEMA.md line citations drifted again** (file changed 2026-08-28T15:35:43, an unrelated ENH-3351 commit adding `artifact_interaction`/Level-3 SSE bridge docs): current locations — `## Reserved Event Names` heading still at line 1367 (unchanged); `## Machine-Readable Schemas` file-tree block now runs 1386-1430 (`parallel_epic_branch_stale.json`/`parallel_worker_completed.json` entries at 1415-1416, previously cited 1412-1413); `### Naming Convention` table's `parallel.*` rows now at 1441-1442 (previously 1438-1439); `## Quick Reference` heading now at 1498 (previously 1495), its `parallel.*` rows now at 1553-1554 (previously 1549-1550). No new event types landed in the sections this issue targets — same prose-only shift pattern as the prior correction, not a structural change.
- **`docs/reference/API.md` hardcoded `parallel.*` list has drifted further than previously noted**: the `parallel.worker_completed`/`parallel.epic_branch_stale` bullet is now at line 7967 (previously cited 7871 — the file grew substantially from the same ENH-3351 commit); the no-arg `IssuePriorityQueue()` example is now at line 4098 (previously 4097).
- **`scripts/little_loops/cli/sprint/run.py:808-814` is a second `ParallelOrchestrator(...)` instantiation site beyond `cli/parallel.py`** (confirmed via `ll-code importers-of` + grep): it already passes `event_bus=event_bus, run_id=run_id` (both wired independently of this issue) — so the six new emitters reach `ll-sprint` runs identically to `ll-parallel` runs, with no additional CLI wiring needed at either call site.
- **No drift found in any previously-cited source-code anchor** (re-verified against the live tree): `orchestrator.py` (`_process_sequential:993`, `_process_parallel:1021`, `_on_worker_complete:1077`, existing emit `:1285`, `_requeue_deferred_issues:1296`, `queue.requeue():1312`), `merge_coordinator.py` (`_process_merge:580`, paused-check `:597`, IN_PROGRESS assignment `:605`, `_finalize_merge:1033`, `_handle_failure:1066`, retry call sites `:838`/`:936`/`:1031`), `priority_queue.py` (`add:50`, in-progress rejection `:62`, `get:92`, `mark_completed:111`, `mark_failed:121`, `mark_skipped:131`, `requeue:146`, count properties `176-199`, `load_completed:228`, `load_failed:237`), the three constructor signatures (still no `event_bus`/`run_id` param on `MergeCoordinator.__init__`/`IssuePriorityQueue.__init__`), and `observability/schema.py`/`test_des_schema.py` anchors (`:505`, `:514`, `:657`, `:718-719`, `:30`, `:43`) all match exactly as previously documented.
- **Pinned counts reconfirmed unaffected by intervening changes**: `SCHEMA_DEFINITIONS` is still exactly 42 (`generate_schemas.py`); `DES_VARIANTS` is now 77 (grew from the unrelated ENH-3351 `artifact_interaction` DES entry), still comfortably `>= len(SCHEMA_DEFINITIONS)` after this issue's planned 42→48 bump, so `test_variants_count_meets_minimum` needs no adjustment beyond what this issue already plans.

## Implementation Steps

1. ~~Land ENH-3345 first~~ — DONE (`d712e20b4`); note its stamping lives in `FSMExecutor._emit()` and is NOT reused here — parallel emitters stamp `run_id` inline from `ParallelOrchestrator.run_id` (see Proposed Solution). **Land BUG-3348 first as well** — `_requeue_deferred_issues`'s `queue.add()` call silently drops deferred issues (rejected as `_in_progress`), and `worker_unblocked` is emitted at that resubmit point; without the fix the event either never fires or lies
   > ⚠ Superseded — BUG-3348 done; `queue.requeue()` confirmed at `orchestrator.py:1312`
2. Add `parallel.worker_blocked`/`parallel.worker_unblocked` emissions in `orchestrator.py` (at the overlap-deferral/requeue points, not a lock wait); add `parallel.worker_started` in `worker_pool.py`'s `_process_issue` immediately after worktree creation (see Program Design timing decision); add `parallel.queue_changed` inside `priority_queue.py`'s six mutators (queue-side — see Program Design); stamp `run_id` on the two existing emitters
3. Add `parallel.merge_started` (gated on `retry_count == 0`) / `parallel.merge_completed` (outcome `merged|failed` + `error`) emissions in `merge_coordinator.py` (`_process_merge`, `_finalize_merge`, `_handle_failure`); thread `event_bus` and `run_id` into `IssuePriorityQueue`/`MergeCoordinator` per the Wiring Phase
4. Add six new `DESVariant` dataclasses to `observability/schema.py`'s `DES_VARIANTS`, and six new entries to `generate_schemas.py`'s `SCHEMA_DEFINITIONS`
5. Add/update tests asserting each event fires with the expected `worker_id`/`issue_id` payload, including `test_merge_coordinator.py`/`test_priority_queue.py` (no prior event coverage) and the pinned counts in `test_generate_schemas.py`/`test_des_schema.py`
6. Document the six new event types across all `EVENT-SCHEMA.md` enumeration sites, refresh `docs/reference/API.md`'s stale examples, and regenerate `docs/reference/schemas/` via `ll-generate-schemas` and `docs/observability/des-audit.md` via `ll-verify-des-audit`
7. Verify a `parallel.*` subscriber can reconstruct active-worker count and per-worker status from the event stream alone

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- Step 3 as written ("Add ... emissions in `worker_pool.py`") is incomplete: `parallel.merge_started`/`parallel.merge_completed` belong in `scripts/little_loops/parallel/merge_coordinator.py` (`_process_merge`, `_finalize_merge`, `_handle_failure`), not `worker_pool.py`, which has no merge-processing code. `parallel.queue_changed` needs `scripts/little_loops/parallel/priority_queue.py`'s count properties wired to an `EventBus` it does not currently hold. See Integration Map findings for the corrected file list.
- Step 5 ("Document ... in `docs/reference/EVENT-SCHEMA.md` and regenerate ... via `ll-generate-schemas`") also requires updating `scripts/little_loops/generate_schemas.py`'s `SCHEMA_DEFINITIONS` dict and `scripts/tests/test_generate_schemas.py`'s pinned count/key-set — `ll-generate-schemas` reads from that dict, not from the markdown doc.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Inject at `scripts/little_loops/parallel/priority_queue.py` — add `event_bus: EventBus | None = None` and `run_id: str | None = None` to `IssuePriorityQueue.__init__` (`:40-48`)
- Inject at `scripts/little_loops/parallel/merge_coordinator.py` — add `event_bus: EventBus | None = None` and `run_id: str | None = None` to `MergeCoordinator.__init__` (`:47-53`)
- Update `scripts/little_loops/parallel/orchestrator.py:132,147-149` — pass `event_bus=self._event_bus, run_id=self.run_id` into the `IssuePriorityQueue(...)` and `MergeCoordinator(...)` constructor calls
- Update `scripts/little_loops/observability/schema.py` — add six new `DESVariant` frozen dataclasses to `DES_VARIANTS`, or `test_des_schema.py` fails
- Update `scripts/tests/test_generate_schemas.py` — bump four pinned `== 42` assertions to `== 48` and extend `test_expected_event_types_present`'s literal set
- Update `scripts/tests/test_des_schema.py` — verify `test_variants_count_meets_minimum`/`test_variants_cover_all_schema_definitions` pass once `DES_VARIANTS` is updated
- Update `scripts/tests/test_merge_coordinator.py` — add new event-emission test class (no prior coverage) following `test_worker_pool.py::TestEnsureEpicBranchEventEmission`; include a retry-path test asserting a RETRYING re-entry does NOT re-emit `merge_started` (retry_count gate), that exactly one `merge_completed` fires per request, and a circuit-breaker test asserting the paused-skip path (`self._paused`) still yields a `merge_started`/`merge_completed(failed)` pair (top-of-method placement)
- Update `scripts/tests/test_priority_queue.py` — add new event-emission test class + bus-injectable fixture (no prior coverage); include tests that `get(block=False)` on an empty queue emits NOTHING (main-loop polling), that a rejected `add()` (duplicate) emits nothing, that `add_many` emits exactly once, and that `load_completed`/`load_failed` each emit once per batch
- Update `scripts/tests/test_orchestrator.py` — the `worker_unblocked` test must use a REAL `IssuePriorityQueue` (not a mock) walking `add → get → defer → requeue-deferred`, so it exercises the BUG-3348 fix and asserts no emit on a failed re-add
- Update `docs/reference/EVENT-SCHEMA.md` — update all three additional enumeration sites (`:1379-1423`, `:1429-1435`, `:1545-1546`), not just the subsystem section
- Update `docs/reference/API.md:4097,7871` — refresh the hardcoded `parallel.*` example list and the no-arg `IssuePriorityQueue()` example
- Regenerate `docs/observability/des-audit.md` via `ll-verify-des-audit` after `DES_VARIANTS` changes (do not hand-edit)

## Program Design

### Types

- `WorkerBlockedReason: Literal["overlap"]` — the only real blocked transition in `parallel/` is overlap deferral (`_process_parallel` → `_deferred_issues`); a `Literal` keeps the field extensible if lock-wait or rate-limit blocking ever moves into this package (rate-limit handling currently lives in the FSM executor, not here). The originally proposed `"lock"`/`"worktree"`/`"dependency"`/`"rate_limit"` values have no emission sites in this codebase.
- `MergeOutcome: Literal["merged", "failed"]` — originally proposed as `merged|conflict|skipped`, but every non-success ending funnels through `_handle_failure(request, error: str)` (`merge_coordinator.py:1066`) — including the circuit-breaker "skip" (`:602`) and non-conflict failures — with no structured discriminator; classifying `conflict`/`skipped` would mean parsing error strings. v1 uses `merged|failed` plus an `error: str | None` payload field carrying the failure detail. If finer outcomes are needed later, change `_handle_failure` to take an explicit outcome parameter (~10 call sites) in a follow-up.

### Signatures

- `WorkerPool._emit_worker_started(self, issue_id: str, worktree_path: Path, branch: str) -> None` — called from `_process_issue` immediately after worktree creation (see timing decision below)
- `ParallelOrchestrator._emit_worker_blocked(self, issue_id: str, reason: WorkerBlockedReason) -> None` — at the overlap-deferral point in `_process_parallel`
- `ParallelOrchestrator._emit_worker_unblocked(self, issue_id: str) -> None` — at the resubmit point in `_requeue_deferred_issues`, called **only when the requeue succeeds** (post-BUG-3348: `queue.requeue(issue)`; never emit on a rejected/no-op re-add)
- `IssuePriorityQueue._emit_queue_changed(self) -> None` — called from inside each of the mutators (`add`/`get`/`mark_completed`/`mark_failed`/`mark_skipped`/`requeue`, plus `load_completed`/`load_failed` once per batch); builds the counter snapshot under the queue's internal lock but calls `emit()` after releasing it (re-entrant-observer safety); `add_many` suppresses per-item emission and emits once after the batch; `get()` emits only on a successful dequeue (the main loop polls `get(block=False)` every iteration) and `add()` only when it returns `True`. (Resolved: queue-side, not `ParallelOrchestrator`-side — the orchestrator's ~15 scattered mutating call sites across parallel and sequential paths would drift out of coverage.)
- `MergeCoordinator._emit_merge_started(self, issue_id: str, branch: str) -> None` — at the **top of `_process_merge`, before the circuit-breaker check** (NOT at the `MergeStatus.IN_PROGRESS` assignment — the paused path calls `_handle_failure` before IN_PROGRESS is set, `merge_coordinator.py:597-603`, which would break pairing), gated on `request.retry_count == 0` so RETRYING re-entries (`merge_coordinator.py:938,1031` requeue the same request) don't emit unpaired starts
- `MergeCoordinator._emit_merge_completed(self, issue_id: str, outcome: MergeOutcome, error: str | None = None) -> None` — in `_finalize_merge` (success, `error=None`) and `_handle_failure` (failure, `error` = its message). `_handle_failure` is terminal (fires at most once per request; it CAN fire with `retry_count >= 1` — used-merge-strategy `:838`, stash-pop conflict `:936`, rebase-failed — but never twice), so completed fires exactly once per merge request

`worker_id` is stamped inside each emitter as an alias of `issue_id` (Option A) rather than passed separately.

**Timing decision for `worker_started`**: emit from inside `WorkerPool._process_issue` on the worker thread, immediately after worktree creation — not from `submit()` at dispatch time. Rationale: the payload requires `worktree_path`/`branch`, which do not exist at dispatch (`worker_pool.py:352-362`), and "claimed but not yet running" is already visible via `parallel.queue_changed`'s pending/active counts. This resolves the claim-time-vs-worktree-time tradeoff raised in the research findings in favor of a complete payload.

### Call Path

`ParallelOrchestrator._process_parallel`/`_process_sequential` (`orchestrator.py:1021-1047`, `~1008` — actual dispatch call, no existing emission point) -> `WorkerPool.submit()` (`worker_pool.py:278-304`) -> ... -> `ParallelOrchestrator._on_worker_complete` (`orchestrator.py:1077-1294`) -> `self._event_bus.emit(...)` (existing `parallel.worker_completed` call at `orchestrator.py:1285-1294`). Corrected from `Orchestrator._run_worker`, which does not exist — see Codebase Research Findings below.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **`worker_id` does not exist anywhere in `scripts/little_loops/parallel/`** (confirmed by grep — zero matches). The existing `parallel.worker_completed` event uses `worker_name` (`result.worktree_path.name`, e.g. `ll-worker-BUG-007-abc123`) derived from the worktree directory, not an independent identity. `WorkerPool` tracks live work exclusively keyed on `issue_id` (`_active_workers[issue.issue_id]`, `worker_pool.py:296-297`; `_worker_stages`, `:2004-2024`). There is no persistent "worker object" or slot — a `ThreadPoolExecutor` thread may be reused across issues, but that reuse is invisible to application code, and `WorkerPool._process_issue` (`:342-`) processes exactly one issue per invocation, so no reassignment case exists to worry about. `worker_id` as this issue proposes it is a new concept that needs an explicit definition before implementation, not a rename of something already tracked.
- **`EventBus.emit()` (`scripts/little_loops/events.py:117-138`) does no schema validation, required-field checking, or run_id/loop stamping** — it takes a raw `dict[str, Any]`, reads only `event["event"]` to route to filtered observers, and passes every other field through untouched. Any `worker_id`/`issue_id` presence guarantee this issue wants is enforced by convention at each call site, not by the bus.
- **`_run_worker` does not exist.** The Call Path above has been corrected to the confirmed dispatch/completion methods.
- **Signatures section's owning classes are wrong for the merge pair.** `_emit_merge_started`/`_emit_merge_completed` are listed under `WorkerPool`, but merge processing lives entirely in `MergeCoordinator` (`merge_coordinator.py`) — `_process_merge` (`:580`, sets `MergeStatus.IN_PROGRESS`), `_finalize_merge` (`:1033-1064`), `_handle_failure` (`:1066-1080`). `worker_pool.py` has no merge code. Likewise `_emit_queue_changed` has no natural home on `Orchestrator`/`WorkerPool` — the counts it needs (`qsize()`, `in_progress_count`, `completed_count`, `failed_count`, `skipped_count`) live on `IssuePriorityQueue` (`priority_queue.py:173-224`), which holds no `EventBus` reference today.

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **`EventBus.emit()` (`events.py:117-138`) is fully synchronous and exception-isolating**: each observer and transport call is individually wrapped in `try/except Exception` (logged via `logger.warning(..., exc_info=True)`), so a failing observer cannot break another observer or raise back to the emitting code; `emit()` performs no schema/shape validation on the passed dict.
- **New emitters run on different threads depending on placement**: `MergeCoordinator._process_merge`/`_finalize_merge`/`_handle_failure` execute on the dedicated `"merge-coordinator"` daemon thread (`merge_coordinator.py:90-95`), so `merge_started`/`merge_completed` emissions happen off the orchestrator's main thread. A `worker_started` emission placed in `WorkerPool.submit()` (called from `_process_parallel`/`_process_sequential`) runs on the orchestrator's main thread, before the worktree exists; placed inside `_process_issue` instead, it runs on the `ThreadPoolExecutor` worker thread, after worktree creation — the same "claimed but no worktree yet" vs "worktree exists" timing tradeoff already raised by the worker_id Option A/B decision above.
- **Dispatch call-site line correction**: `_process_sequential` is defined at `orchestrator.py:993` (not `~1008`); its `worker_pool.submit(issue)` call without a completion callback is at `:1008`. `_process_parallel`'s dispatching submit-with-callback call is at `:1047`.
- **`parallel.epic_branch_stale` precedent for non-issue-scoped events**: it carries no `issue_id`/`worker_id` field at all (only `branch`/`base`/`commits_behind`/`mode`/`action`), consistent with this issue's own `queue_changed` payload (API/Interface section) already omitting `worker_id`/`issue_id` — confirms that design choice matches existing precedent rather than introducing a new inconsistency.

## Pre-Implementation Review Findings

_Added 2026-08-27 — manual code review against the live codebase before implementation:_

1. **BLOCKER — BUG-3348 (filed): the defer→requeue path silently drops issues.** `_requeue_deferred_issues` (`orchestrator.py:1296-1314`) re-adds via `queue.add(issue)`, but `add()` rejects ids in `_in_progress` (`priority_queue.py:62`) — and every deferred issue IS in `_in_progress` (moved there by `queue.get()` at `orchestrator.py:934` before `_process_parallel` deferred it). `add()` returns `False`, the issue is dropped from `_deferred_issues`, and it never runs. The existing test (`test_orchestrator.py:4532`) mocks the queue and misses it. This issue now `depends_on` BUG-3348 (fix: `queue.requeue()`), and `worker_unblocked` is gated on the requeue succeeding.
2. **`merge_started` placement corrected**: anchoring it at the `MergeStatus.IN_PROGRESS` assignment breaks 1:1 pairing on the circuit-breaker path — `_process_merge` calls `_handle_failure` before IN_PROGRESS when `self._paused` (`merge_coordinator.py:597-603`). Emit at the top of `_process_merge`, before the circuit-breaker check, still gated on `retry_count == 0`. Also corrected: `_handle_failure` CAN fire with `retry_count >= 1` (`:838`, `:936`, rebase-failed) — the prior claim it "is never reached on a RETRYING pass" was wrong; pairing holds anyway because started fired on attempt 0 and `_handle_failure` is terminal.
3. **`queue_changed` conditional-emit rules made explicit**: `get()` emits only on successful dequeue (main loop polls `get(block=False)` every iteration — unconditional emit floods the bus); `add()` only when it returns `True`.
4. **`load_completed`/`load_failed` resume-path loaders added to the emitter set** (`priority_queue.py:225-241`): they mutate the counters but were absent from the original six-mutator list; each now emits one `queue_changed` after its batch so post-resume counters are truthful.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **BUG-3348 confirmed resolved in the live tree**: `_requeue_deferred_issues` (`orchestrator.py:1296-1314`) now calls `self.queue.requeue(issue)` at `:1312` (not `queue.add()`), and `IssuePriorityQueue.requeue()` (`priority_queue.py:146-170`) already contains the duplicate-enqueue guard (`if issue.issue_id in self._queued: return`, `:154-155`) that discards the id from `_in_progress`/`_failed`/`_skipped` before re-enqueueing. BUG-3348's frontmatter shows `status: done`, `completed_at: 2026-08-28T00:56:59Z`. Item 1's BLOCKER language (below) is now stale — `parallel.worker_unblocked` can be safely gated on `requeue()` succeeding, since it no longer silently drops.
- **No other `parallel.*` implementation exists yet**: repo-wide search confirms none of the six proposed event names (`worker_started`, `worker_blocked`, `worker_unblocked`, `merge_started`, `merge_completed`, `queue_changed`) appear anywhere outside `.issues/`; `IssuePriorityQueue`/`MergeCoordinator` still take no `event_bus`/`run_id` parameters (`priority_queue.py:40-48`, `merge_coordinator.py:47-53`). The rest of this issue's research and Program Design remain current.

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

Out of scope: building the dashboard/visualizer consumer itself (this issue only adds the emitters); changing existing fields or the emission point of the existing `parallel.worker_completed`/`parallel.epic_branch_stale` events (the additive `run_id` stamp on both IS in scope — see API/Interface); adding lifecycle events outside the `parallel.*` namespace (e.g. FSM state-transition events); retrofitting historical runs with these events after the fact; **fixing the sequential-mode `worker_completed` gap** — `_process_sequential` submits without a callback (`orchestrator.py:1008`) so sequential/P0 issues never reach the sole `worker_completed` emitter in `_on_worker_complete` (`:1285`); this is a pre-existing asymmetry (sequential issues DO get the new `worker_started`, merge, and `queue_changed` events), left for a follow-up issue rather than adding an emission to `_process_sequential`/`_merge_sequential` here.

## API/Interface

```python
# New parallel.* event payloads (all include run_id; all but queue_changed include worker_id, issue_id)
# worker_id == issue_id (Option A alias); reason is Literal["overlap"]; outcome is Literal["merged","failed"]
{"event": "parallel.worker_started", "run_id": str, "worker_id": str, "issue_id": str, "worktree_path": str, "branch": str}
{"event": "parallel.worker_blocked", "run_id": str, "worker_id": str, "issue_id": str, "reason": str}
{"event": "parallel.worker_unblocked", "run_id": str, "worker_id": str, "issue_id": str}
{"event": "parallel.merge_started", "run_id": str, "worker_id": str, "issue_id": str, "branch": str}
{"event": "parallel.merge_completed", "run_id": str, "worker_id": str, "issue_id": str, "outcome": str, "error": str | None}
{"event": "parallel.queue_changed", "run_id": str, "pending": int, "active": int, "completed": int, "failed": int, "skipped": int}
# merge_started fires once per merge request (gated on retry_count == 0; RETRYING re-entries don't re-emit),
# emitted at the TOP of _process_merge (before the circuit-breaker check) so the paused-skip path,
# which calls _handle_failure before IN_PROGRESS is set, still gets a started before its completed —
# started/completed pairs are 1:1. error is None when outcome == "merged".
# worker_unblocked fires only when the deferred issue is actually re-queued (requires BUG-3348's
# requeue() fix; never emitted on a rejected re-add).
# queue_changed: get() emits only on successful dequeue (main loop polls get(block=False) every
# iteration); add() only when it returns True; add_many/load_completed/load_failed emit once per batch.
# NOTE (2026-08-28): FEAT-3323 stamps a producer identifier onto the socket-transport envelope at the
# same top level these payloads are splatted into. run_id is reserved for THIS issue's field; FEAT-3323's
# key will be something else (producer_id or similar) — coordinated in that issue's Resolved Decisions.
# queue_changed carries all five IssuePriorityQueue counters rather than a lossy pending/active/done triple —
# a dashboard wants failed broken out; consumers needing "done" compute completed + failed + skipped.
# ("active" = in_progress_count, "pending" = qsize().)
# NOTE: the counters are NOT exhaustive — overlap-deferred issues live in the orchestrator's
# _deferred_issues list, outside the queue, and appear in-flight by these counters; consumers
# reconstruct the blocked set from worker_blocked/worker_unblocked events instead.

# Existing events gain the same additive run_id stamp (payloads otherwise unchanged):
{"event": "parallel.worker_completed", "run_id": str, ...}
{"event": "parallel.epic_branch_stale", "run_id": str, ...}
```

## Acceptance Criteria

_Formalized from the acceptance prose in Summary and Success Metrics — no new criteria added._

- [ ] Each of the six new event types (`parallel.worker_started`, `worker_blocked`, `worker_unblocked`, `merge_started`, `merge_completed`, `queue_changed`) is emitted from the code path that already knows the state change (per Proposed Solution / Program Design placements)
- [ ] Every `parallel.*` event carries `run_id`, including the two existing emitters (`parallel.worker_completed`, `parallel.epic_branch_stale`)
- [ ] Every worker-scoped event carries `worker_id` and `issue_id` (`queue_changed` and `epic_branch_stale` are run-scoped, not worker-scoped)
- [ ] A consumer subscribed to `parallel.*` can reconstruct active-worker count and per-worker status at any point in a run without reading `.issues/` or the filesystem — for parallel-dispatched issues (sequential/P0 issues get `worker_started`, merge, and `queue_changed` events but no `worker_completed`; see Scope Boundaries)
- [ ] A worker stuck for its full timeout produces at least one `parallel.worker_blocked` event before that timeout fires
- [ ] `docs/reference/EVENT-SCHEMA.md` documents each new type with its payload table, and `docs/reference/schemas/` is regenerated via `ll-generate-schemas`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-27_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- `unapplied_decision` still fires, but on a different pair than the prior run: "Program Design/Implementation Steps/Files to Modify still specifies `_process_issue` (rejected option)". **RESOLVED 2026-08-27 (pre-implementation review): confirmed false positive** — `_process_issue` is the *selected* placement for `worker_started` (the Program Design "Timing decision" explicitly rejects `submit()` in favor of `_process_issue`).
- `stale_symbol_ref` still flags all six new/existing event names as "claimed in `scripts/little_loops/cli/parallel.py`". **RESOLVED 2026-08-27 (pre-implementation review): confirmed false positive** — grep of `cli/parallel.py` finds no event-name references, and the Integration Map does not cite that file.
- Moderate breadth × moderate depth: six new emitters plus `run_id` stamping on two existing ones span 6 source files (orchestrator.py, worker_pool.py, merge_coordinator.py, priority_queue.py, generate_schemas.py, observability/schema.py) and 6 doc/test files, with constructor-signature changes (threading `event_bus` into `IssuePriorityQueue`/`MergeCoordinator`) rather than pure mechanical substitution — expect more iteration than a single-file change.

## Session Log
- `/ll:verify-issues` - 2026-08-29T15:57:01 - `c54a423f-c560-4b02-ba94-5edb4f845eaa.jsonl`
- `/ll:refine-issue` - 2026-08-29T15:47:04 - `e1f51e56-4700-4629-9064-1d81eae9d21d.jsonl`
- `/ll:refine-issue` - 2026-08-28T03:18:19 - `90104caa-276e-4ccd-9e14-4b75908612aa.jsonl`
- `/ll:confidence-check` - 2026-08-27T23:52:49 - `669eb13b-852d-427b-9f5f-ccf15758ffa9.jsonl`
- `/ll:confidence-check` - 2026-08-27T22:17:22 - `dd56bf1f-7933-4d9c-980c-762867d3ce6b.jsonl`
- `/ll:reconcile-issue` - 2026-08-27T22:14:34 - `3e6453f3-ac93-435f-934e-1a9d7dc7adfd.jsonl`
- `/ll:refine-issue` - 2026-08-27T22:09:56 - `79106a4f-4393-4e7a-9f77-a9f63f9c673b.jsonl`
- `/ll:wire-issue` - 2026-08-27T21:00:23 - `3300bae1-29e4-43aa-be1f-dbf44d0ba9ec.jsonl`
- `/ll:decide-issue` - 2026-08-27T20:51:11 - `627b8139-f4c5-4fdb-82a9-07a01d666f59.jsonl`
- `/ll:refine-issue` - 2026-08-27T20:10:28 - `9e4fa033-0b0b-43cd-be66-950ccb670df0.jsonl`
- `/ll:refine-issue` - 2026-08-27T20:10:19 - `3cf55431-2b3c-40fa-ad5c-a3fd2b0789ab.jsonl`
- `/ll:format-issue` - 2026-08-27T20:01:01 - `e13ddb3f-38f3-4515-910f-59c195a89ea8.jsonl`
- `/ll:capture-issue` - 2026-08-27T19:56:52 - `f1d9d0f2-280e-4e9e-bb4a-45c14f878f7b.jsonl`
