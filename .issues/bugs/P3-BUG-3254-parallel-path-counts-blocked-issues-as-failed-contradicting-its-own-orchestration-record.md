---
id: BUG-3254
type: BUG
title: ll-parallel counts BLOCKED issues as failed in the queue while recording them
  as skipped, diverging from the sequential path
priority: P3
status: open
testable: true
discovered_by: review
discovered_date: '2026-08-18'
discovered_source: pre-implementation review of BUG-3252/BUG-3253, 2026-08-18
relates_to:
- BUG-3252
- BUG-3253
confidence_score: 90
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# BUG-3254: ll-parallel counts BLOCKED issues as failed in the queue while recording them as skipped, diverging from the sequential path

## Summary

`ParallelOrchestrator._on_worker_complete` classifies a single BLOCKED-verdict
result two different ways within one function. Its queue-counter dispatch
(`orchestrator.py:1096-1232`) has no `was_blocked` arm, so a BLOCKED result
falls through to the terminal `else: self.queue.mark_failed(...)` at
`orchestrator.py:1229-1232`. Forty lines later the same result is recorded as
`orchestration_status = "skipped"` (`orchestrator.py:1249-1251`) — the function
already knows the outcome is not a failure and says so in the persisted record,
while the counters say the opposite.

The sequential path resolved this: `AutoManager._process_issue` routes
`was_blocked` to `mark_skipped()` (`issue_manager.py:2132-2135`). The parallel
path never got the matching arm.

Separately, `WorkerResult.corrections` is populated only on the success return
(`worker_pool.py:743-744`); every failure return, including BLOCKED
(`worker_pool.py:508-520`), omits it. So a blocked-after-correction issue on the
parallel path is counted in the correction-rate denominator but can never appear
in its numerator — the mirror image of the sequential path's defect.

This was factored out of BUG-3253 during its 2026-08-18 review, which correctly
scoped it out as a distinct defect rather than a variant of the one it was
fixing. BUG-3253 was subsequently cancelled into BUG-3252, so this was left
unowned; filed here to keep it tracked.

## Steps to Reproduce

1. Run `ll-parallel` over a set including an issue whose `/ll:ready-issue` pass
   returns a BLOCKED verdict (open dependency).
2. Observe the run summary's failed count, and the correction rate if any other
   issue was corrected.
3. Compare against the orchestration record for the same issue.

Expected divergence: the issue is `status="skipped"` in the orchestration record
but contributes to `queue.failed_count` and therefore to the summary's failed
tally and its correction-rate denominator.

## Current Behavior

**Queue dispatch — no `was_blocked` arm.** `_on_worker_complete`'s branching
(`orchestrator.py:1096-1232`) covers `should_close` (1096), `success` (1124), and
a terminal `else` (1229):

```python
else:
    self.logger.error(f"{result.issue_id} failed: {result.error}")
    self._worker_errors[result.issue_id] = result.error or "Failed"
    self.queue.mark_failed(result.issue_id)
```

A BLOCKED result has `success=False` and `should_close=False`
(`worker_pool.py:508-520`), so it lands here — logged at `error` level as
"failed", with its BLOCKED verdict string as the error text.

**Orchestration record — correctly classified.** Immediately after, at
`orchestrator.py:1249-1251`:

```python
if result.was_blocked:
    orchestration_status = "skipped"
    orchestration_reason = result.error or recorded_error
```

Both read the same `result`. The field the record consults is the field the
dispatch does not.

**Corrections attached on success only.** `worker_pool.py:743-744` passes
`corrections=corrections` on the success return. The BLOCKED return
(`508-520`), the NOT_READY return, and the exception return all omit it. The
orchestrator's rate (`orchestrator.py:1647-1653`) divides
`len(corrections_snapshot)` by `queue.completed_count + queue.failed_count`
(`priority_queue.py:167,173`), so a corrected-then-blocked issue sits in the
denominator with its corrections discarded.

The corrections *are* available at the BLOCKED return point: they come from
`ready_parsed.get("corrections", [])` (`worker_pool.py:551`) — the ready-issue
pass, not manage-issue validation — and `ready_parsed` is already in scope at
`:507`. The current code simply returns before line 551 reads it.

**The orchestrator drops corrections on any non-success path regardless.**
`state.corrections` is written only at `orchestrator.py:1133-1135`, inside
`if result.was_corrected:`, which is itself inside `elif result.success:`
(`:1124`). A BLOCKED result can never reach it. Attaching `corrections=` in
`worker_pool.py` is therefore a **no-op on its own** — the new skipped arm must
also write `state.corrections`. This is a second, orchestrator-side half of the
corrections defect that is easy to miss.

## Expected Behavior

1. **One classification per outcome.** A BLOCKED result is a skip in the queue
   counters as well as the orchestration record. It should not be logged at
   `error` level as a failure.
2. **Parity with the sequential path.** `issue_manager.py:2132-2135` is the
   reference behavior for *routing*; the parallel path mirrors it. Note the
   sequential path is **not** a safe reference for the corrections half — see
   Decision D2 below.
3. **Numerator and denominator filtered on the same predicate.** Whatever is
   excluded from `completed_count + failed_count` must also be excluded from
   the corrections snapshot, or the rate can exceed 100% — or divide by zero
   with a nonzero numerator. This invariant is inherited from BUG-3252 Part 4;
   it is the reason the corrections-attachment half cannot be fixed
   independently of the counter half without checking the interaction.

## Impact

- **Severity**: P3 — no data loss, and the persisted orchestration record is
  already correct, so post-hoc analysis over that table is unaffected. The
  live run summary and the counters are what mislead.
- **Frequency**: every `ll-parallel` run containing a BLOCKED-verdict issue.
- **Data Risk**: None.

## Root Cause

The two paths were built separately and are maintained as lockstep-edited
duplicate blocks rather than a shared module, so a fix applied to one does not
propagate. `mark_skipped`-style routing was added to the sequential path
(BUG-3005 precedent) without a parallel counterpart, and `IssuePriorityQueue`
has no skip bucket to route to — it tracks only `completed_count` and
`failed_count` (`priority_queue.py:110-194`), so the arm has nowhere to land
without a queue-side change first.

## Proposed Solution

The queue-side gap makes this larger than the sequential fix it mirrors.

1. Give `IssuePriorityQueue` a skip concept (`_skipped`, `mark_skipped()`,
   `skipped_count`, `skipped_ids`, `load_skipped()`), mirroring the existing
   `mark_failed`/`failed_count`/`failed_ids`/`load_failed` quartet at
   `priority_queue.py:120-128,173,191,205-212`.
   - `requeue()` (`:130-149`) currently discards from `_in_progress` and
     `_failed` only; it must also discard from `_skipped`, or a requeued issue
     stays permanently in the skip set.
   - `add()` (`:60-66`) refuses ids already in `_completed`/`_failed`. Whether
     `_skipped` joins that guard is decision **D1** below — it is a live
     resume-behavior change, not a mechanical addition.
2. Add an `elif result.was_blocked:` arm ahead of the terminal `else` at
   `orchestrator.py:1229`, routing to `queue.mark_skipped()` and logging at
   `info` rather than `error`. Reuse the same `result.was_blocked` the record
   consults at `1250`.
3. Fix the corrections half in **both** places (see decision **D2**):
   - `worker_pool.py:507-520` — pass `corrections=ready_parsed.get("corrections", [])`
     (and the matching `was_corrected`) on the BLOCKED return.
   - `orchestrator.py` — write `state.corrections[result.issue_id]` from the new
     skipped arm; the existing write at `:1133-1135` is unreachable for a
     BLOCKED result, so the `worker_pool.py` change alone accomplishes nothing.
   - `orchestrator.py:1649` — include `skipped_count` in the denominator.

Whether the summary should surface a skipped count is settled for the parallel
path here (step 4 in the Wiring Phase); the sequential path already renders a
`Skipped issues:` block at `issue_manager.py:1981-1984`.

### Decisions Required

**D1 — Are blocked issues re-attempted on resume?**
`IssuePriorityQueue.add()` (`priority_queue.py:60-66`) refuses ids present in
`_completed`/`_failed`. Today a BLOCKED issue lands in `_failed`, so `_load_state`'s
`load_failed(...)` (`orchestrator.py:725`) keeps it out of the queue on resume.
Once it moves to `_skipped`, a resumed run **re-attempts it** unless `_skipped`
is added to that guard.

Recommendation: **do add the guard**, preserving today's behavior, and treat
"retry blocked issues on resume whose dependency has since closed" as a separate
enhancement. Re-attempting is arguably more useful but is a scope expansion that
changes run cost, and no existing test pins either behavior.

**D2 — Corrections on the BLOCKED path: attach, and fix the denominator.**
Resolve the open question rather than deferring it. Attach corrections at the
BLOCKED return, store them in the new skipped arm, and change the denominator at
`orchestrator.py:1649` from `completed_count + failed_count` to
`completed_count + failed_count + skipped_count`. This keeps numerator and
denominator filtered on the same predicate, per the invariant in Expected
Behavior #3.

**Do not mirror the sequential path here.** `issue_manager.py:2157-2158` records
corrections unconditionally, outside the routing if/elif chain, while its
denominator (`:1989`) is `completed + failed` — excluding skipped. BUG-3252's
comment at `:1991-1995` justifies that asymmetry only for `was_gated`, which
"never carries `corrections=`". `was_blocked` is **not** covered by that
argument, so the sequential path carries the same latent >100% defect this
issue's Decision Rules forbid; it is simply unexercised. Copying it propagates
the bug. File a follow-up to apply the same denominator fix to
`issue_manager.py:1989`.

### Non-Goals

- **NOT_READY stays a failure.** The NOT_READY return (`worker_pool.py:522+`)
  also has `success=False, should_close=False` and lands in the same terminal
  `else`. It is a quality verdict, not a dependency wait, and is deliberately
  left in `mark_failed`. Do not generalize this fix to "route all non-failures
  out of `mark_failed`".
- **No `was_gated` counterpart.** `WorkerResult` (`parallel/types.py:97`) has no
  `was_gated` field and the parallel path runs no confidence gate, so BUG-3252's
  gated routing arm has nothing to mirror here. Only `was_blocked` is in scope.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/parallel/orchestrator.py` — `ParallelOrchestrator._on_worker_complete` (1071-1263): queue-counter dispatch (1096-1232, terminal `else` -> `mark_failed` at 1229-1232) and orchestration-record classification (1248-1263, `if result.was_blocked: orchestration_status = "skipped"`). Correction-rate calculation at 1646-1654.
- `scripts/little_loops/parallel/priority_queue.py` — `IssuePriorityQueue` (22-233). Has `_completed`/`_failed` sets, `mark_completed`/`mark_failed` (110-128), `completed_count`/`failed_count` properties (166-176), `completed_ids`/`failed_ids` properties (184-194), `load_completed`/`load_failed` (196-212). No skip bucket in any form (`_skipped`, `mark_skipped`, `skipped_count`, `skipped_ids`, `load_skipped` — none exist).
- `scripts/little_loops/parallel/worker_pool.py` — BLOCKED return (507-520, `was_blocked=True`, `success=False`, no `corrections=` passed); success return (731-745, the only return path that populates `corrections`).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/show.py`, `scripts/little_loops/cli/logs.py`, `scripts/little_loops/cli/ctx_stats.py` — reference `failed_count`/`skipped_issues`/`correction_rate`; a queue-side skip bucket, if added, may need surfacing here for parity with the sequential-path summary.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/parallel.py:216,328` — instantiates `ParallelOrchestrator`; this is the actual `ll-parallel` CLI entry point and was missing from the original map entirely.
- `scripts/little_loops/cli/sprint/run.py:808` — instantiates `ParallelOrchestrator` for multi-issue waves, then consumes `orchestrator.queue.completed_ids`/`failed_ids` directly at `:821-822` to bucket into `state.completed_issues`/`state.failed_issues` (`:824-836`). A BLOCKED issue inside a *multi-issue parallel wave* currently lands in `actually_failed`; the sequential retry loop (`:837-903`, ENH-308) happens to reclassify it correctly via its own `elif retry_result.was_blocked:` arm (`:887-896`) when retried, which masks the wave-level bug for retried issues but not for a run with no retry pass.
- `scripts/little_loops/parallel/types.py` — `WorkerResult` (`was_blocked` field ~`:97`, `to_dict`/`from_dict`) already carries the signal needed. `OrchestratorState` (`:243-293`), the parallel driver's persisted-state dataclass, has `completed_issues`/`failed_issues`/`pending_merges`/`timing`/`corrections` but **no skip bucket or `to_dict`/`from_dict` entry for one** — asymmetric with `ProcessingState.skipped_issues` (`state.py:54`) on the sequential path.
- `scripts/little_loops/parallel/orchestrator.py` `_load_state`/`_save_state` (`:709-765`) — **both halves are required.** `_load_state` needs `self.queue.load_skipped(self.state.skipped_issues)` mirroring `load_completed`/`load_failed` at `:724-725`. `_save_state` (`:745-752`) builds `state.failed_issues` from `queue.failed_ids` × `self._worker_errors` and needs a matching `state.skipped_issues = {...}` block — **without it the new `OrchestratorState` field is always persisted empty and `load_skipped` restores nothing**, a silent no-op that queue-mocking tests will not catch.
- `scripts/little_loops/parallel/priority_queue.py` `requeue` (`:130-149`) — discards from `_in_progress` and `_failed`; needs a `_skipped` discard too, or a requeued issue is permanently stuck in the skip set.
- `scripts/little_loops/parallel/priority_queue.py` `add` (`:60-66`) — the `_completed`/`_failed` re-add guard; whether `_skipped` joins it is decision **D1** (resume re-attempt semantics), not a mechanical addition.
- `scripts/little_loops/parallel/orchestrator.py` `_maybe_complete_epic` (`:1355-1450`, gate at `:1426`) — `failed_here = epic_child_ids & (set(self.queue.failed_ids) | set(self.state.failed_issues))` reads `failed_ids` directly, so a BLOCKED child moving out of `failed_ids` no longer trips it. **Low risk in practice**: the `all_done` check at `:1417-1420` requires `done_count == total`, and a ready-issue-BLOCKED child is still `open` on disk, so the function returns early well before `failed_here` is evaluated. Union the new skip-id set in as a defensive one-liner for consistency with the docstring at `:1364-1370` ("Any child failed/blocked → the epic branch is held open"), but this is not a behavioral fork requiring its own design decision.
- `scripts/little_loops/parallel/orchestrator.py:956,959` — gates `_cleanup_state()` and the process exit code purely on `self.queue.failed_count == 0`. Once BLOCKED issues stop incrementing `failed_count`, a run containing only BLOCKED issues will newly exit `0` and have its state file cleaned up — an intended second-order effect of the fix, not a bug, but should be called out explicitly since no existing test pins the old exit-code-1-on-blocked-only behavior.
- `scripts/little_loops/sprint.py:103,115,129` — `SprintState.skipped_blocked_issues` is a **third**, independently-named precedent for "blocked, not failed" state (alongside `ProcessingState.skipped_issues` and the planned `IssuePriorityQueue` skip bucket). The naming choice for the new parallel-side field should be made consciously against both existing precedents, not just `ProcessingState`.

### Reference Implementation (Sequential Path)
- `scripts/little_loops/issue_manager.py:2130-2155` — `AutoManager._process_issue`'s single-point classification: `was_closed` -> `mark_completed`; `was_blocked` -> `mark_skipped` (logged at `info`, not `error`); `was_gated` -> `mark_skipped` + `_gated_issue_ids.add()` (BUG-3252); `success` -> `mark_completed`; `plan_created` -> `mark_skipped`; else -> `mark_failed`.
- `scripts/little_loops/state.py:221-232` — `StateManager.mark_skipped(issue_id, reason)`, writes to `ProcessingState.skipped_issues: dict[str, str]` (`state.py:54`), structurally parallel to `mark_completed`/`mark_failed`.
- `scripts/little_loops/issue_manager.py:1976-1997` — run summary already renders a `Skipped issues:` block (1981-1984) and excludes `skipped_issues` from the correction-rate denominator (1987-1989: `len(state.completed_issues) + len(state.failed_issues)`), plus a `_gated_issue_ids` disclosure suffix (1991-1997). The parallel-path summary (orchestrator.py:1600-1685) has no equivalent skip rendering.
  - **Counter-reference, do not copy:** corrections are recorded unconditionally at `issue_manager.py:2157-2158`, outside the routing if/elif chain, so a blocked-with-corrections issue enters the numerator while the `:1989` denominator excludes it. The BUG-3252 comment at `:1991-1995` justifies the exclusion only for `was_gated` ("never carries `corrections=`"), which does not extend to `was_blocked`. The sequential path therefore carries the same latent >100% asymmetry — unexercised, not fixed. See decision **D2**.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/run.py:711-725,888-903` — a **third, independent** correct reference implementation, closer to this issue's own driver family than `issue_manager.py`: `elif issue_result.was_blocked:` / `elif issue_result.was_gated:` (the latter's comment cites BUG-3252 explicitly: "confidence-gate skip, never attempted — not a failure. Mirrors issue_manager.py's was_gated routing arm") both set `orchestration_status = "skipped"` and route into `state.skipped_blocked_issues[issue.issue_id]`, logged at `logger.warning`, not `logger.error`. This is the single-issue/contention sub-wave path in `ll-sprint`, distinct from the multi-issue `ParallelOrchestrator` path in the same file (`:808`) that this bug is about — worth citing precisely because it shows the correct pattern already exists one call away from the buggy code, in a file that also directly calls the buggy `ParallelOrchestrator`.

### Tests
- `scripts/tests/test_orchestrator.py` `TestOnWorkerComplete` (~2530) and a dispatch-routing class (~4990) — construct `WorkerResult(...)`, call `_on_worker_complete`, assert on `orchestrator.queue.mark_completed`/`mark_failed` call counts via `MagicMock`. Confirmed via grep: no existing test constructs `WorkerResult(was_blocked=True)` and asserts on `orchestrator.queue`.
- `scripts/tests/test_priority_queue.py` `TestIssuePriorityQueueStateTransitions` (331-386) — direct-instantiation tests on `mark_completed`/`mark_failed` and counter/id-list properties; `TestIssuePriorityQueuePersistence` (509-547) tests `load_completed`/`load_failed`. A symmetry assertion at line 638 (`queue.completed_count + queue.failed_count == 20`) would need revisiting if a skip bucket is added.
- `scripts/tests/test_issue_manager.py` — reference coverage for the sequential path's `was_blocked` -> `mark_skipped` routing, for parity comparison.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_worker_pool.py` — no existing test covers the BLOCKED return path (`worker_pool.py:507-520`) at all; new coverage needed for `was_blocked=True`/`corrections` shape. (Do not confuse with `TestRunPerWorktreeProofFirstGate::test_blocked_result_skips_manage_issue` at `:3755-3788` — that's the unrelated proof-first-task gate's terminal-exit-code concept.)
- `scripts/tests/test_priority_queue.py:361-386` — new `test_mark_skipped_removes_from_in_progress`/`test_mark_skipped_adds_to_skipped`/`test_mark_skipped_increments_count` trio, mirroring the existing `mark_failed` trio exactly. `TestIssuePriorityQueuePersistence` (`:509-547`) needs a matching `test_load_skipped_adds_ids`/`test_load_skipped_prevents_add` pair, mirroring `test_load_failed_adds_ids`/`test_load_failed_prevents_add` (`:527-540`).
- `scripts/tests/test_orchestrator.py::TestDispatchRouting` — new `test_on_worker_complete_blocked_marks_skipped`, mirroring `test_on_worker_complete_failure_marks_failed` (`:5074-5091`) for the positive assertion and `test_on_worker_complete_interrupted_not_marked_failed` (`:5093-5110`) for the `mark_failed.assert_not_called()` negative-assertion idiom. The `orchestrator` fixture (`:141-145`) sets MagicMock defaults for `completed_ids`/`failed_ids`/`completed_count`/`failed_count` on `orch.queue` — needs matching `skipped_ids = []`/`skipped_count = 0` defaults added.
- `scripts/tests/test_sprint_integration.py` — `MockQueue` classes at `:297-307` and `:377-387` (used by `test_sprint_multi_wave_dependency_ordering` and `test_sprint_parallel_within_wave`) define only `completed_ids`/`failed_ids`; need a `skipped_ids` property once `cli/sprint/run.py`'s wave-consumption code (`:821-836`) branches on it. No existing test exercises a BLOCKED issue inside a *multi-issue parallel wave* in isolation — `test_sprint_blocked_issue_skipped_not_failed` (`:815-873`) covers only the sequential single-issue path (mocks `process_issue_inplace` directly, never touches `ParallelOrchestrator`).
- `scripts/tests/test_issue_workflow_integration.py:265` — constructs its own `IssuePriorityQueue()` directly; needs non-breakage confirmation (or added coverage) once a `mark_skipped`/`skipped_count`/`skipped_ids` surface exists.

## Program Design

_Verified against the tree during the 2026-08-19 pre-implementation review. Two
decisions (D1, D2) are stated with recommendations in the Proposed Solution and
should be confirmed before implementation; everything else is settled._

### Types
- `IssuePriorityQueue` — `scripts/little_loops/parallel/priority_queue.py:110-194` — tracks `completed_count` (`:167`) and `failed_count` (`:173`) via `mark_completed()` (`:110`) and `mark_failed()` (`:120`). Has no skip concept; a skip arm has nowhere to land until one is added. Contrast `ProcessingState.skipped_issues: dict[str, str]` (`state.py:53`), which the sequential path already has.
- `WorkerResult` — `scripts/little_loops/parallel/types.py:97` (`was_blocked`), constructed in `worker_pool.py` — already carries `was_blocked` (set at `worker_pool.py:513`) and a corrections field (populated only at `:744`). No new field is needed on it; the defect is in which consumers read them, plus which returns populate `corrections`. Note it has **no** `was_gated` field — unlike `IssueResult` (`issue_manager.py:648`) on the sequential path.

### Signatures
- `ParallelOrchestrator._on_worker_complete(self, result: WorkerResult) -> None` — `scripts/little_loops/parallel/orchestrator.py:1071` — contains both halves of the contradiction: the queue-counter dispatch (`1096-1232`, terminal `else` → `mark_failed` at `1229-1232`) and the orchestration-record classification (`1249-1251`, `if result.was_blocked` → `"skipped"`).
- `IssuePriorityQueue.mark_failed(self, issue_id: str) -> None` — `scripts/little_loops/parallel/priority_queue.py:120` — where BLOCKED results wrongly land today.
- `StateManager.mark_skipped(issue_id: str, reason: str) -> None` — `scripts/little_loops/state.py:221-232` — the sequential path's reference implementation, for shape only; it operates on `ProcessingState`, not the queue.

### Call Path
`ll-parallel` worker finishes -> `ParallelOrchestrator._on_worker_complete(result)` (`orchestrator.py:1071`) -> dispatch falls past `should_close` (`:1096`) and `success` (`:1124`) to the terminal `else` (`:1229`) -> `self.queue.mark_failed(result.issue_id)` (`:1232`) -> `queue.failed_count` (`priority_queue.py:173`) -> the run summary's failed tally and the correction-rate denominator at `orchestrator.py:1649`.

The same `result` then reaches `:1249`, where `if result.was_blocked` sets `orchestration_status = "skipped"` for `_record_orchestration_result()` — the divergence this issue reports.

### Decision Rules
- **Fix the queue half and the corrections half together, or neither.** They move the denominator and the numerator of the same rate in opposite directions; changing one alone can push it above 100% or produce `N/0`. Inherited from BUG-3252 Part 4's symmetry invariant. Resolved as decision **D2**: attach + store + widen the denominator to `completed + failed + skipped`.
- **The corrections fix has two sides.** `worker_pool.py` must attach it and the orchestrator's new skipped arm must store it. Changing only `worker_pool.py` is a no-op, because `state.corrections` is written solely under `elif result.success:` (`orchestrator.py:1124,1133-1135`).
- **Reuse `result.was_blocked`, do not introduce a new signal.** The field already exists, is already set by `worker_pool.py:513`, and is already consulted forty lines below the dispatch that ignores it.
- **The sequential path is the reference for routing only.** `issue_manager.py:2132-2135` establishes the intended `was_blocked` → skip routing; its `mark_skipped`/`skipped_issues` mechanism operates on `ProcessingState` and cannot be lifted into `IssuePriorityQueue` unchanged. Its **corrections/denominator handling must not be copied** — see D2.
- **Only `was_blocked` is in scope.** NOT_READY stays a failure; `was_gated` has no parallel-path equivalent. See Non-Goals.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4025-4048` — `IssuePriorityQueue` Methods table lists `mark_completed`/`mark_failed`/`completed_count`/`failed_count` but is already missing `completed_ids`/`failed_ids`/`load_completed`/`load_failed` rows for the *current* surface. If a `mark_skipped`/`skipped_count`/`skipped_ids`/`load_skipped` surface is added, this table needs both the new rows and the pre-existing gap closed.
- `docs/reference/API.md:4014` — documents `WorkerResult.was_blocked`; needs a note if the corrections-attachment decision (Expected Behavior #3) changes what's populated on the BLOCKED return.
- `docs/reference/API.md:6703` — documents `SprintState.skipped_blocked_issues`, the third naming precedent; relevant context for whatever name the new `IssuePriorityQueue` skip bucket takes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/parallel.py` (`:216,328`) — the actual `ll-parallel` entry point instantiating `ParallelOrchestrator`; confirm/exercise end-to-end once the fix lands.
- Update `scripts/little_loops/cli/sprint/run.py` (`:821-836`) — multi-issue wave BLOCKED-issue bucketing currently relies on the sequential retry loop (`:837-903`) to mask the bug; once `IssuePriorityQueue` has a skip bucket, branch on `orchestrator.queue.skipped_ids` here too, not just `completed_ids`/`failed_ids`.
- Update `scripts/little_loops/parallel/types.py` — add a skip field + `to_dict`/`from_dict` entries to `OrchestratorState` (`:243-293`) for resume-safety parity with the new `IssuePriorityQueue` bucket.
- Update `scripts/little_loops/parallel/orchestrator.py` `_load_state` (`:724-725`) — add `load_skipped(...)`, mirroring the existing `load_completed`/`load_failed` calls.
- Update `scripts/little_loops/parallel/orchestrator.py` `_save_state` (`:745-752`) — populate `state.skipped_issues` from `queue.skipped_ids`; without this the persisted field is always empty and the `_load_state` change is inert.
- Update `scripts/little_loops/parallel/priority_queue.py` `requeue` (`:130-149`) — add a `_skipped` discard alongside the existing `_failed` discard.
- Resolve `scripts/little_loops/parallel/priority_queue.py` `add` (`:60-66`) per decision **D1** — add `_skipped` to the re-add guard (recommended) so resume behavior is unchanged.
- Update `scripts/little_loops/parallel/orchestrator.py` `_on_worker_complete` — the new skipped arm must write `state.corrections[result.issue_id]` (decision **D2**); the existing write at `:1133-1135` is unreachable for BLOCKED results.
- Update `scripts/little_loops/parallel/orchestrator.py:1649` — widen the correction-rate denominator to `completed_count + failed_count + skipped_count`.
- Update `scripts/little_loops/parallel/worker_pool.py:507-520` — pass `corrections=ready_parsed.get("corrections", [])` (and `was_corrected`) on the BLOCKED return; `ready_parsed` is already in scope, the same source line `:551` reads.
- Update `scripts/little_loops/parallel/orchestrator.py` `_report_results` (`:1596-1625`) — render a `Skipped issues:` block mirroring `issue_manager.py:1981-1984`, and stop implying a blocked issue failed in the `Failed: {count}` line at `:1604`.
- Update `scripts/little_loops/parallel/orchestrator.py` `_maybe_complete_epic` (`:1426`) — union the new skip-id set into `failed_here`. Defensive one-liner only; the `all_done` gate at `:1417-1420` already returns early for a BLOCKED child (still `open` on disk, so `done_count != total`).
- Add `scripts/tests/test_worker_pool.py` coverage for the BLOCKED return path (`:507-520`), asserting `was_blocked=True` **and** that `corrections` is carried through from `ready_parsed`.
- Add `scripts/tests/test_priority_queue.py` `mark_skipped`/`load_skipped` test trios mirroring the existing `mark_failed`/`load_failed` ones, plus: `test_requeue_clears_skipped` (mirroring the `_failed` discard) and a test pinning decision **D1** — `test_add_rejects_skipped_id` (or its inverse, whichever D1 selects), so the resume semantics stop being unpinned.
- Add `scripts/tests/test_orchestrator.py` coverage that a BLOCKED result's corrections reach `state.corrections` (the orchestrator-side half of D2), and that the correction rate cannot exceed 100% when the only corrected issue is blocked.
- Add `scripts/tests/test_orchestrator.py` round-trip coverage for `_save_state` → `_load_state` with a skipped issue, using a real `IssuePriorityQueue` rather than a `MagicMock` — a mocked queue cannot catch the "field persisted empty" failure mode.
- Add `scripts/tests/test_orchestrator.py::TestDispatchRouting::test_on_worker_complete_blocked_marks_skipped`; update the `orchestrator` fixture (`:141-145`) with `skipped_ids`/`skipped_count` MagicMock defaults.
- Update `scripts/tests/test_sprint_integration.py`'s `MockQueue` classes (`:297-307`, `:377-387`) with a `skipped_ids` property; add a wave-level (non-retry) BLOCKED-in-multi-issue-wave test.
- Update `docs/reference/API.md` (`:4025-4048`, `:4014`) for the new `IssuePriorityQueue` surface and any `WorkerResult` corrections-field change.

## Related Issues

- BUG-3252 — the sequential-path equivalent of the classification half, plus the
  correction-rate denominator fix. Establishes the `was_gated`/`mark_skipped`
  routing pattern and the numerator/denominator symmetry invariant this issue
  inherits. Explicitly scoped to exclude the parallel path.
- **Follow-up to file:** the sequential path's correction-rate denominator
  (`issue_manager.py:1989`) excludes `skipped_issues` while the numerator
  (`:2157-2158`) includes blocked-with-corrections issues — the same
  numerator/denominator asymmetry this issue fixes on the parallel side. Not in
  scope here (this issue is explicitly parallel-path), but it should not be left
  undocumented once D2 establishes the correct shape.
- BUG-3253 — cancelled into BUG-3252. Its Behavior Parity analysis of the three
  run paths, and its Codebase Research Findings on the parallel path's
  divergences, are the origin of this issue.

## Related Key Documentation

- `scripts/little_loops/state.py:32-34` — auto-corrections are tracked as a
  quality signal, the reason the rate's accuracy matters.

## Status

**Open** | Created: 2026-08-18 | Priority: P3

## Session Log
- pre-implementation review - 2026-08-19 - verified all claims against the tree. Corrected stale `issue_manager.py:2107-2111` citations to `2132-2135`; found the orchestrator-side half of the corrections defect (`state.corrections` written only under `elif result.success:`); established that the sequential path is an unsafe reference for corrections/denominator handling; surfaced the `add()` re-add guard as decision D1 and the `_save_state` persist half as a required wiring step; added `requeue()`; downgraded the `_maybe_complete_epic` touchpoint (unreachable behind the `all_done` gate); fenced NOT_READY and `was_gated` as non-goals.
- `/ll:wire-issue` - 2026-08-19T15:21:48 - `6f435684-155f-4724-92e1-2b56419366c1.jsonl`
- `/ll:refine-issue` - 2026-08-18T14:56:18 - `1b75a5d5-cd19-4f54-9db4-f0438e3206cc.jsonl`
- `/ll:confidence-check` - 2026-08-18T03:58:40 - `e1587cf9-62dc-4b5b-8de8-7b698165c90b.jsonl`
- filed from pre-implementation review - 2026-08-18 - factored out of BUG-3253 before its cancellation into BUG-3252; claims verified against `orchestrator.py:1096-1251`, `worker_pool.py:508-520,743-744`, `priority_queue.py:110-194`
