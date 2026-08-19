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
confidence_score: 100
outcome_confidence: 80
score_complexity: 15
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 18
---

# BUG-3254: ll-parallel counts BLOCKED issues as failed in the queue while recording them as skipped, diverging from the sequential path

## Summary

`ParallelOrchestrator._on_worker_complete` classifies a single BLOCKED-verdict
result two different ways within one function. Its queue-counter dispatch
(`orchestrator.py:1096-1232`) has no `was_blocked` arm, so a BLOCKED result
falls through to the terminal `else: self.queue.mark_failed(...)` at
`orchestrator.py:1229-1232`. Forty lines later the same result is recorded as
`orchestration_status = "skipped"` (`orchestrator.py:1250-1252`) — the function
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
`orchestrator.py:1250-1252`:

```python
if result.was_blocked:
    orchestration_status = "skipped"
    orchestration_reason = result.error or recorded_error
```

Both read the same `result`. The field the record consults is the field the
dispatch does not.

**Corrections attached on success only.** `worker_pool.py:743-744` passes
`corrections=corrections` on the success return — grep confirms `corrections`
appears nowhere else in the file except its source read at `:549-551`. The
orchestrator's rate (`orchestrator.py:1646-1653`) divides
`len(corrections_snapshot)` by `queue.completed_count + queue.failed_count`
(`priority_queue.py:167,173`), so a corrected-then-blocked issue sits in the
denominator with its corrections discarded.

**Every return but one has this defect — on both sides of the read, not just
above it.** `_run_issue`'s twelve `_stamped_result(...)` returns
(`worker_pool.py:462,477,493,509,537,558,622,680,695,717,731,748`) omit
`corrections=` everywhere except the success return at `:731`. They divide into
two groups, and **the fix must cover both**:

*Above the read (`:462,477,493,509,537`)* — these return before `:549-551` reads
`ready_parsed`, the positional cause the third review pass identified: interrupted
(`:462`), ready-issue returncode ≠ 0 (`:477`), CLOSE (`:493`), BLOCKED (`:509`),
NOT_READY (`:537`).

*Below the read (`:558,622,680,695,717,748`)* — these have `corrections` **already
in scope** and simply never pass it: proof-first gate failure (`:558`),
post-implement interrupt (`:622`), manage-issue returncode ≠ 0 (`:680`), work not
verified (`:695`), base-update/rebase failure (`:717`), and the exception handler
(`:748`). Every one of these except `:622` routes to `mark_failed`
(`orchestrator.py:1231-1232`) and is therefore **already in the denominator today
with an unreachable numerator** — and *corrected-then-failed-verification* is a far
more common real run than corrected-then-blocked. A hoist alone does not touch
them; see **D2** for the mechanism that does.

CLOSE and NOT_READY likewise already sit in the denominator today (via
`mark_completed` at `orchestrator.py:1114` and `mark_failed` at `:1232`). This is
one defect with one cause — "the kwarg is opt-in on twelve return sites" — and D2
fixes it at that cause.

The corrections *are* available at the BLOCKED return point: they come from
`ready_parsed.get("corrections", [])` (`worker_pool.py:551`) — the ready-issue
pass, not manage-issue validation — and `ready_parsed` is already in scope at
`:507`.

**The orchestrator drops corrections on any non-success path regardless.**
`state.corrections` is written only at `orchestrator.py:1135-1137`, inside
`if result.was_corrected:`, which is itself inside `elif result.success:`
(`:1124`). A BLOCKED result can never reach it. Attaching `corrections=` in
`worker_pool.py` is therefore a **no-op on its own** — the new skipped arm must
also write `state.corrections`. This is a second, orchestrator-side half of the
corrections defect that is easy to miss.

**The CLOSE and NOT_READY verdicts have the identical defect, already live in the
denominator.** The `should_close` return (`worker_pool.py:491-505`) and the
NOT_READY return (`:522-547`) omit `corrections=` for the same reason the BLOCKED
return does — all three return before `:549-551` reads `ready_parsed`. But
`should_close` routes to `queue.mark_completed()` (`orchestrator.py:1114`) and
NOT_READY routes to `queue.mark_failed()` (`:1232`), so a corrected-then-closed
or corrected-then-not-ready issue is *already* in the denominator with its
corrections discarded. This is not a consequence of the fix; it is the same
numerator/denominator asymmetry D2 exists to correct, present on the parallel
path today and unmentioned by the original analysis. Both are in scope — see D2.

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
   `skipped_count`, `skipped_ids`), mirroring the existing
   `mark_failed`/`failed_count`/`failed_ids` trio at
   `priority_queue.py:120-128,173,191`.
   - `requeue()` (`:130-149`) currently discards from `_in_progress` and
     `_failed` only; it must also discard from `_skipped`, or a requeued issue
     stays permanently in the skip set.
   - `add()` (`:60-66`) refuses ids already in `_completed`/`_failed`. `_skipped`
     **does not** join that guard — see decision **D1**. There is no
     `load_skipped()` either, for the same reason.
2. Add an `elif result.was_blocked:` arm ahead of the terminal `else` at
   `orchestrator.py:1229`, routing to `queue.mark_skipped()` and logging at
   `info` rather than `error`. Reuse the same `result.was_blocked` the record
   consults at `1250`. **Also set `self._worker_errors[result.issue_id]`** to
   `result.error or "Blocked"`, matching every other arm — see D2's
   `_worker_errors` note for why.
3. Fix the corrections defect **at its cause, once on each side** (see decision
   **D2**) rather than arm by arm:
   - `worker_pool.py` — make `corrections` **opt-out instead of opt-in** by
     injecting it through the existing `_stamped_result` closure (`:390-396`).
     Declare `was_corrected = False` / `corrections: list[str] = []` above the
     `try` (`:398`), have `_stamped_result` `setdefault` both onto its kwargs, and
     leave the assignment where `:549-551` reads `ready_parsed` today. **No hoist
     is needed**: returns below the assignment pick up the real values, returns
     above it pick up the `False`/`[]` defaults, which is correct for them. All
     twelve returns are covered by one edit and no future return can regress.
   - `orchestrator.py` — replace the arm-local write at `:1135-1137` with a single
     write beside the already-unconditional timing write at `:1242-1246`, after
     the whole dispatch chain. **Keep the `if result.corrections:` truthiness
     guard** — the numerator is `len(corrections_snapshot)` (`:1646`), which counts
     *keys*, so writing `[]` for every result pins the rate at 100%. Unconditional
     in *position*, guarded on non-empty.
   - `orchestrator.py:1647` — include `skipped_count` in the denominator.
4. Render the skip count on **both** output surfaces, not just the final summary:
   - `_report_results` (`:1585-1706`) — a `Skipped: {count}` line beside
     `Failed:` (`:1604`) and a `Skipped issues:` block mirroring the existing
     `Failed issues:` block (`:1618-1622`) and `issue_manager.py:1981-1984`.
   - `_maybe_report_status` (`:843-844`) — the 5-second live progress line, which
     builds `Failed: {n}` from `queue.failed_count`. Without a matching
     `Skipped: {n}` part, a blocked issue silently vanishes from live progress —
     the exact surface this issue's Impact section names as the misleading one.
5. Leave `_cleanup_state()` and the exit code at `orchestrator.py:956,959`
   **unchanged**, both gated on `failed_count == 0` — see decision **D3**. A
   blocked-only run newly exits `0` and deletes its state file, which is the
   correct outcome under D1.

### Decisions Required

**D1 — Are blocked issues re-attempted on resume? Yes — do not suppress them.**

Resolved: **add no suppression paths at all.** `add()`'s guard
(`priority_queue.py:60-66`) is left alone, no `load_skipped()` is added to
`_load_state` (`orchestrator.py:724-725`), and `_scan_issues`'s `skip_ids` union
(`:968`) is left alone. The skip bucket is a within-run counter, not resume state.

An earlier draft recommended the opposite — add all three guards, to "preserve
today's behavior." That is wrong on both halves:

*It does not preserve today's behavior; it inverts it for the common case.*
`_load_state` is called unconditionally from the constructor (`orchestrator.py:235`),
gated only on `clean_start` — **there is no `--resume` flag**, so any surviving
state file suppresses its issues on every subsequent run. Today a blocked-only run
has `failed_count == 0`, so it exits `0` and **deletes** its state file
(`:956-959`) — those issues *are* re-attempted next run. Today's suppression of a
blocked issue only happens incidentally, when something *else* in the same run
failed and kept the state file alive. There is no coherent existing semantic to
preserve.

*Combined with the old D3, it suppressed them permanently.* Old-D3 kept the state
file whenever `skipped_count > 0`; D1's guard then filtered those issues out of
the next run; `load_skipped` repopulated `_skipped`, so `skipped_count > 0` again
and the file was kept again. A blocked issue would be filtered out forever,
including long after its dependency closed. That is strictly worse than the bug
being fixed.

The right analogue is not `_failed` but `_interrupted_issues`
(`orchestrator.py:1085-1092`), which the orchestrator deliberately leaves unmarked
in the queue precisely so it retries next run: *"Don't mark as failed - they can
be retried on next run."* A dependency wait is transient in exactly the same way.

Consequences: D3 dissolves (see below), and `OrchestratorState` needs no
enforcement-bearing skip field. Persisting `skipped_issues` as a pure
observability record is optional; if added, it must be read with `.get()` for
pre-upgrade files (see Non-Goals) and must **not** be wired into `skip_ids`.

**D2 — Corrections: fix at the cause on both sides, and widen the denominator.**
Resolve the open question rather than deferring it. Widen the denominator at
`orchestrator.py:1647` from `completed_count + failed_count` to
`completed_count + failed_count + skipped_count`, keeping numerator and
denominator filtered on the same predicate per the invariant in Expected
Behavior #3 — and fix the numerator at its cause rather than arm by arm.

**The worker-side cause is that `corrections=` is opt-in on twelve return sites.**
An earlier draft of this decision diagnosed it as purely *positional* — "they all
return before `worker_pool.py:549-551` reads `ready_parsed`" — and prescribed
hoisting that read above the CLOSE check at `:491`. That diagnosis covers only
five of the eleven defective returns. Six more (`:558,622,680,695,717,748`) sit
*below* the read with `corrections` already in scope and simply never pass it, and
five of those six route to `mark_failed` — they are in the denominator today. See
Current Behavior for the full table. A hoist cannot fix them.

**So make it opt-out.** `_stamped_result` (`worker_pool.py:390-396`) is a closure
every return path already funnels through, and its docstring states this exact
principle for `base_sha`: *"Every return path inside this method uses it — a
failed worker's base state is as worth recording as a successful one."*
Corrections have the same property. Declare the two locals above the `try`,
`setdefault` them inside `_stamped_result`, and leave the assignment at
`:549-551`:

```python
was_corrected: bool = False
corrections: list[str] = []

def _stamped_result(**kwargs: Any) -> WorkerResult:
    kwargs.setdefault("was_corrected", was_corrected)
    kwargs.setdefault("corrections", corrections)
    return WorkerResult(base_sha=base_sha, base_dirty=base_dirty, **kwargs)
```

One edit, twelve sites covered, no hoist, and a thirteenth return added later
cannot regress it. This is what makes the Decision Rule "do not fix this arm by
arm" actually achievable.

**On the orchestrator side, move the write but keep its guard.**
`state.corrections` is written at one point only (`:1135-1137`), nested inside
`elif result.success:` → `if result.was_corrected:`; move it beside the timing
write at `:1242-1246`, below the entire dispatch chain. **Retain
`if result.corrections:`.** The numerator is `total_corrected =
len(corrections_snapshot)` (`:1646`) — it counts *keys*, not corrections — so a
genuinely unconditional `state.corrections[id] = result.corrections` writes an
empty list for every issue and pins the reported rate at 100% on every run. The
correct reading of "unconditional" here is *positional*: outside the if/elif
chain, still guarded on a non-empty list.

**Why moving it below the chain is safe, and why per-arm is not.** Once the
denominator is `completed + failed + skipped`, every result that reaches `:1242`
sits in exactly one of those three buckets — the only early return above it is the
`interrupted` path (`:1085-1092`), which is excluded from all three counters and
from the write alike. Per-arm writes, by contrast, would need four sites and
would still be fragile: the `should_close` arm itself forks to `mark_failed` when
`close_issue()` returns false (`:1116-1120`), so "write it in the close success
path" quietly drops corrections for closes that fail to close.

**`_worker_errors` on the new blocked arm — set it.** Every other arm writes
`self._worker_errors[result.issue_id]` (`:1116,1122,1225,1231`); the blocked arm
should too (`result.error or "Blocked"`). It cannot corrupt the orchestration
record — `if result.was_blocked:` (`:1250`) is evaluated before `recorded_error`
is consulted — and it cannot leak into persisted state, because `_save_state`
(`:748-752`) keys `failed_issues` off `queue.failed_ids`, which no longer contains
the id. It is where the optional `skipped_issues` observability field would read
its reason from. Decided here so the implementer does not have to guess.

**CLOSE and NOT_READY are in scope for this decision** — not as extra arms, but
as automatic consequences of fixing the position. Both already sit in the
denominator today (`mark_completed` at `:1114`, `mark_failed` at `:1232`) with an
unreachable numerator, so neither needs a denominator change; both are the same
invariant this issue exists to enforce. Note this widening of scope is
**corrections only** — NOT_READY's *routing* remains `mark_failed`, per Non-Goals.

**Do not mirror the sequential path here.** `issue_manager.py:2157-2158` records
corrections unconditionally, outside the routing if/elif chain, while its
denominator (`:1989`) is `completed + failed` — excluding skipped. BUG-3252's
comment at `:1991-1995` justifies that asymmetry only for `was_gated`, which
"never carries `corrections=`". `was_blocked` is **not** covered by that
argument, so the sequential path carries the same latent >100% defect this
issue's Decision Rules forbid; it is simply unexercised. Copying it propagates
the bug. File a follow-up to apply the same denominator fix to
`issue_manager.py:1989`.

**D3 — State cleanup and exit code: change nothing.**
`orchestrator.py:956,959` gate both `_cleanup_state()` and the process exit code
on `self.queue.failed_count == 0`:

```python
if not self._shutdown_requested and self.queue.failed_count == 0:
    self._cleanup_state()
return 0 if self.queue.failed_count == 0 else 1
```

Resolved: **leave both as they are.** After the fix a run whose only
non-completions are BLOCKED exits `0` and deletes its state file. Both halves are
correct: a dependency wait is not a failure, and deleting the state is what makes
the blocked issue eligible again on the next run — the behavior D1 wants.

An earlier draft proposed gating cleanup on
`failed_count == 0 and skipped_count == 0` to preserve state for D1's resume
suppression to read. With D1 resolved the other way, that motivation is gone, and
the combination was actively harmful — see D1 for the permanent-suppression loop
it created. This decision is now a no-op edit; it is retained only to record that
the `:956,959` interaction was examined rather than overlooked.

No existing test pins the current exit-code-1-on-blocked-only behavior, so the
new exit-`0` behavior still needs coverage even though the code at `:956,959` is
untouched.

### Non-Goals

- **NOT_READY stays a failure — for routing.** The NOT_READY return
  (`worker_pool.py:522-547`) also has `success=False, should_close=False` and
  lands in the same terminal `else`. It is a quality verdict, not a dependency
  wait, and is deliberately left in `mark_failed`. Do not generalize this fix to
  "route all non-failures out of `mark_failed`". **This fence is routing-only:**
  NOT_READY *is* covered by D2's corrections fix, because that defect is
  per-return-site rather than verdict-specific, and NOT_READY already sits in the
  denominator via `mark_failed`.
- **No `was_gated` counterpart.** `WorkerResult` (`parallel/types.py:97`) has no
  `was_gated` field and the parallel path runs no confidence gate, so BUG-3252's
  gated routing arm has nothing to mirror here. Only `was_blocked` is in scope.
- **No retroactive reclassification of pre-upgrade state files.** A BLOCKED issue
  recorded by the *current* build sits in `OrchestratorState.failed_issues`. On
  the first resume after this fix it stays classified as failed, and — because
  `_scan_issues` reads `state.failed_issues` (`:968`) — stays suppressed.
  **This does not self-clear**, and an earlier draft of this bullet claiming it
  would ("self-clears as soon as the state file is cleaned") was wrong: the state
  file is never cleaned while the entry exists. `_load_state` calls
  `queue.load_failed(state.failed_issues.keys())` (`:725`), so `failed_count > 0`
  immediately; `_cleanup_state()` is gated on `failed_count == 0` (`:956`) and so
  never fires; `_save_state` (`:748-752`) re-persists the entry from `failed_ids`.
  The issue is suppressed on *every* subsequent run until a manual `--clean-start`
  or a hand-deleted state file. Accepted anyway — migrating would mean guessing
  intent from a free-text failure reason, and the blast radius is one state file
  written before the upgrade — but the real consequence is recorded here rather
  than a comfortable one. Note this is a **pre-existing defect for genuine
  failures too** (any failed issue is permanently suppressed by a surviving state
  file, and its own failure keeps that file alive); file it as a follow-up
  alongside the `issue_manager.py:1989` one. Conditional on D1: if `OrchestratorState` gains a
  `skipped_issues` observability field at all, `from_dict`
  (`parallel/types.py:281+`) reads keys explicitly, so it must be read with
  `.get(..., default)` or every state file written before this change fails to
  load.
- **No resume-suppression of skipped issues.** Per D1, `_skipped` is a within-run
  counter only. Do not add `load_skipped()`, do not extend `add()`'s re-add
  guard, and do not union `state.skipped_issues` into `_scan_issues`'s `skip_ids`
  — an earlier draft of this issue recommended all three; see D1 for why that
  produces permanent suppression.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/parallel/orchestrator.py` — `ParallelOrchestrator._on_worker_complete` (1071-1263): queue-counter dispatch (1096-1232, terminal `else` -> `mark_failed` at 1229-1232) and orchestration-record classification (1248-1263, `if result.was_blocked: orchestration_status = "skipped"`). Correction-rate calculation at 1646-1654.
- `scripts/little_loops/parallel/priority_queue.py` — `IssuePriorityQueue` (22-233). Has `_completed`/`_failed` sets, `mark_completed`/`mark_failed` (110-128), `completed_count`/`failed_count` properties (166-176), `completed_ids`/`failed_ids` properties (184-194), `load_completed`/`load_failed` (196-212). No skip bucket in any form (`_skipped`, `mark_skipped`, `skipped_count`, `skipped_ids`, `load_skipped` — none exist).
- `scripts/little_loops/parallel/worker_pool.py` — BLOCKED return (507-520, `was_blocked=True`, `success=False`, no `corrections=` passed); CLOSE return (491-505, `success=True`, `should_close=True`, no `corrections=`); NOT_READY return (522-547, no `corrections=`); success return (731-745, the only return path that populates `corrections`). The `was_corrected`/`corrections` reads live at `:549-551`. **Superseded in part by the fourth review pass:** the reads being below CLOSE/BLOCKED/NOT_READY is only half the cause — six further returns (`:558,622,680,695,717,748`) sit *below* the reads and omit `corrections=` anyway, so D2 fixes it by default-injection through the `_stamped_result` closure (`:390-396`), not by hoisting.

_Added by `/ll:refine-issue` — 2026-08-19 — based on codebase analysis:_

- Verified 2026-08-19 (post-D1/D2/D3 resolution) against the current tree via `ll:codebase-analyzer`: every specific code claim in this issue holds exactly, including nearly all cited line numbers. No skip-bucket, `mark_skipped`, or corrections-hoisting code exists anywhere in `scripts/little_loops/parallel/` — the Proposed Solution is entirely unimplemented; nothing new to add.
- Trivial citation drift only (no behavioral discrepancy): `orchestrator.py`'s `if result.was_blocked:` block is at lines 1250-1252 (issue cites 1249-1251/1248-1263, off by one). `test_priority_queue.py::test_load_failed_prevents_add` is at lines 534-540 (issue cites 527-540, which spans it plus the preceding `test_load_failed_adds_ids` test).
- `ll:codebase-pattern-finder` confirms the reference-implementation shape: `IssuePriorityQueue`'s existing `_completed`/`_failed` buckets are bare `set[str]` (no reason string) with a `mark_*`/`*_count`/`*_ids`/`load_*` four-piece shape — the pattern a new `_skipped` bucket should match. By contrast `state.py`'s `skipped_issues`/`failed_issues` and `sprint.py`'s `skipped_blocked_issues` are `dict[str, str]` (id -> reason) — a deliberate shape divergence between the queue-side and state-tracker-side buckets, not an inconsistency to reconcile. `_report_results`'s `Failed:` line is unconditional while `_maybe_report_status`'s `Failed:` part is truthy-guarded (`if failed > 0`) — the two existing call sites already disagree with each other on this convention, so the new `Skipped:` line has no single existing precedent to match exactly; match each call site's own existing convention rather than forcing uniformity between them.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/show.py`, `scripts/little_loops/cli/logs.py`, `scripts/little_loops/cli/ctx_stats.py` — reference `failed_count`/`skipped_issues`/`correction_rate`; a queue-side skip bucket, if added, may need surfacing here for parity with the sequential-path summary.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/parallel.py:216,328` — instantiates `ParallelOrchestrator`; this is the actual `ll-parallel` CLI entry point and was missing from the original map entirely.
- `scripts/little_loops/cli/sprint/run.py:808` — instantiates `ParallelOrchestrator` for multi-issue waves, then consumes `orchestrator.queue.completed_ids`/`failed_ids` directly at `:821-822` to bucket into `state.completed_issues`/`state.failed_issues` (`:824-836`). A BLOCKED issue inside a *multi-issue parallel wave* currently lands in `actually_failed`; the sequential retry loop (`:837-903`, ENH-308) happens to reclassify it correctly via its own `elif retry_result.was_blocked:` arm (`:887-896`) when retried, which masks the wave-level bug for retried issues but not for a run with no retry pass.
- `scripts/little_loops/parallel/types.py` — `WorkerResult` (`was_blocked` field ~`:97`, `to_dict`/`from_dict`) already carries the signal needed. `OrchestratorState` (`:243-293`), the parallel driver's persisted-state dataclass, has `completed_issues`/`failed_issues`/`pending_merges`/`timing`/`corrections` but **no skip bucket or `to_dict`/`from_dict` entry for one** — asymmetric with `ProcessingState.skipped_issues` (`state.py:54`) on the sequential path. Per **D1** this asymmetry is now *optional* to close: the parallel skip bucket carries no resume semantics, so a persisted field here would be observability only.
- `scripts/little_loops/parallel/orchestrator.py` `_load_state`/`_save_state` (`:709-765`) — **per D1, no `load_skipped()` is added.** Note `_load_state` is called unconditionally from the constructor (`:235`), gated only on `clean_start` — there is **no `--resume` flag**, so anything persisted-and-reloaded here suppresses issues on *every* later run, not just an explicit resume. That is the fact that reverses D1. If `_save_state` (`:745-752`) grows a `state.skipped_issues = {...}` block mirroring its `failed_issues` build, it is observability only and must have no reader in `_scan_issues` or the queue. The `_load_state` resume log line (`:727-731`, `"N completed, N failed"`) needs a third clause if and only if the field is persisted.
- `scripts/little_loops/parallel/priority_queue.py` `requeue` (`:130-149`) — discards from `_in_progress` and `_failed`; needs a `_skipped` discard too, or a requeued issue is permanently stuck in the skip set.
- `scripts/little_loops/parallel/priority_queue.py` `add` (`:60-66`) — the `_completed`/`_failed` re-add guard; `_skipped` **does not** join it, per **D1**.
- `scripts/little_loops/parallel/orchestrator.py` `_maybe_report_status` (`:820-884`, counters read at `:842-844`) — the 5-second live progress line, emitting `Failed: {n}` from `queue.failed_count` at `:849-850`. Distinct edit site from `_report_results`, and previously missing from this map entirely: without a `Skipped: {n}` part, a blocked issue disappears from live progress once it stops incrementing `failed_count`.
- `scripts/little_loops/parallel/orchestrator.py` `_maybe_complete_epic` (`:1355-1450`, gate at `:1426`) — `failed_here = epic_child_ids & (set(self.queue.failed_ids) | set(self.state.failed_issues))` reads `failed_ids` directly, so a BLOCKED child moving out of `failed_ids` no longer trips it. **Low risk in practice**: the `all_done` check at `:1417-1420` requires `done_count == total`, and a ready-issue-BLOCKED child is still `open` on disk, so the function returns early well before `failed_here` is evaluated. Union the new skip-id set in as a defensive one-liner for consistency with the docstring at `:1364-1370` ("Any child failed/blocked → the epic branch is held open"), but this is not a behavioral fork requiring its own design decision.
- `scripts/little_loops/parallel/orchestrator.py:956,959` — gates `_cleanup_state()` and the process exit code purely on `self.queue.failed_count == 0`. **Unchanged by this fix** (see **D3**), but its behavior shifts: once BLOCKED issues stop incrementing `failed_count`, a run containing only BLOCKED issues newly exits `0` and has its state file cleaned up. Both are the desired outcome under D1 — the cleanup is precisely what makes a blocked issue eligible again next run. No existing test pins the old exit-code-1-on-blocked-only behavior, so this needs new coverage despite being a zero-line change.
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
- `scripts/tests/test_priority_queue.py:361-386` — new `test_mark_skipped_removes_from_in_progress`/`test_mark_skipped_adds_to_skipped`/`test_mark_skipped_increments_count` trio, mirroring the existing `mark_failed` trio exactly. Per **D1** there is no `load_skipped`, so `TestIssuePriorityQueuePersistence` (`:509-547`) gains **no** new pair — instead it gains the inverse pin, `test_add_accepts_previously_skipped_id`, asserting the deliberate asymmetry against `test_load_failed_prevents_add` (`:527-540`).
- `scripts/tests/test_orchestrator.py::TestDispatchRouting` — new `test_on_worker_complete_blocked_marks_skipped`, mirroring `test_on_worker_complete_failure_marks_failed` (`:5074-5091`) for the positive assertion and `test_on_worker_complete_interrupted_not_marked_failed` (`:5093-5110`) for the `mark_failed.assert_not_called()` negative-assertion idiom. The `orchestrator` fixture (`:141-145`) sets MagicMock defaults for `completed_ids`/`failed_ids`/`completed_count`/`failed_count` on `orch.queue` — needs matching `skipped_ids = []`/`skipped_count = 0` defaults added.
- `scripts/tests/test_sprint_integration.py` — `MockQueue` classes at `:297-307` and `:377-387` (used by `test_sprint_multi_wave_dependency_ordering` and `test_sprint_parallel_within_wave`) define only `completed_ids`/`failed_ids`; need a `skipped_ids` property once `cli/sprint/run.py`'s wave-consumption code (`:821-836`) branches on it. No existing test exercises a BLOCKED issue inside a *multi-issue parallel wave* in isolation — `test_sprint_blocked_issue_skipped_not_failed` (`:815-873`) covers only the sequential single-issue path (mocks `process_issue_inplace` directly, never touches `ParallelOrchestrator`).
- `scripts/tests/test_issue_workflow_integration.py:265` — constructs its own `IssuePriorityQueue()` directly; needs non-breakage confirmation (or added coverage) once a `mark_skipped`/`skipped_count`/`skipped_ids` surface exists.

## Program Design

_Verified against the tree during the 2026-08-19 pre-implementation reviews (four
passes). All three decisions (D1, D2, D3) are now **resolved** in the Proposed
Solution — D1 and D3 were reversed by the third pass; D2's mechanism was replaced
by the fourth (hoist → `_stamped_result` default-injection) and its "unconditional
write" corrected to keep the non-empty guard. Nothing remains open; implementation
can proceed directly._

### Types
- `IssuePriorityQueue` — `scripts/little_loops/parallel/priority_queue.py:110-194` — tracks `completed_count` (`:167`) and `failed_count` (`:173`) via `mark_completed()` (`:110`) and `mark_failed()` (`:120`). Has no skip concept; a skip arm has nowhere to land until one is added. Contrast `ProcessingState.skipped_issues: dict[str, str]` (`state.py:53`), which the sequential path already has.
- `WorkerResult` — `scripts/little_loops/parallel/types.py:97` (`was_blocked`), constructed in `worker_pool.py` — already carries `was_blocked` (set at `worker_pool.py:513`) and a corrections field (populated only at `:744`, the success return; all eleven other `_stamped_result(...)` sites omit it). No new field is needed on it; the defect is in which consumers read them, plus which returns populate `corrections`. Note it has **no** `was_gated` field — unlike `IssueResult` (`issue_manager.py:648`) on the sequential path.

### Signatures
- `ParallelOrchestrator._on_worker_complete(self, result: WorkerResult) -> None` — `scripts/little_loops/parallel/orchestrator.py:1071` — contains both halves of the contradiction: the queue-counter dispatch (`1096-1232`, terminal `else` → `mark_failed` at `1229-1232`) and the orchestration-record classification (`1250-1252`, `if result.was_blocked` → `"skipped"`).
- `_stamped_result(**kwargs: Any) -> WorkerResult` — `scripts/little_loops/parallel/worker_pool.py:390-396` — a per-worker closure that all twelve of `_run_issue`'s returns already funnel through, existing precisely to make `base_sha`/`base_dirty` opt-out rather than opt-in: *"Every return path inside this method uses it — a failed worker's base state is as worth recording as a successful one."* D2 extends the same mechanism to `was_corrected`/`corrections`.
- `IssuePriorityQueue.mark_failed(self, issue_id: str) -> None` — `scripts/little_loops/parallel/priority_queue.py:120` — where BLOCKED results wrongly land today.
- `StateManager.mark_skipped(issue_id: str, reason: str) -> None` — `scripts/little_loops/state.py:221-232` — the sequential path's reference implementation, for shape only; it operates on `ProcessingState`, not the queue.

### Call Path
`ll-parallel` worker finishes -> `ParallelOrchestrator._on_worker_complete(result)` (`orchestrator.py:1071`) -> dispatch falls past `should_close` (`:1096`) and `success` (`:1124`) to the terminal `else` (`:1229`) -> `self.queue.mark_failed(result.issue_id)` (`:1232`) -> `queue.failed_count` (`priority_queue.py:173`) -> the run summary's failed tally and the correction-rate denominator at `orchestrator.py:1647`.

The same `result` then reaches `:1249`, where `if result.was_blocked` sets `orchestration_status = "skipped"` for `_record_orchestration_result()` — the divergence this issue reports.

### Decision Rules
- **Fix the queue half and the corrections half together, or neither.** They move the denominator and the numerator of the same rate in opposite directions; changing one alone can push it above 100% or produce `N/0`. Inherited from BUG-3252 Part 4's symmetry invariant. Resolved as decision **D2**: attach + store + widen the denominator to `completed + failed + skipped`.
- **The corrections fix has two sides, and neither is a hoist.** `worker_pool.py` must attach it (`setdefault` inside the `_stamped_result` closure, `:390-396`) and the orchestrator must store it (one write below the dispatch chain, replacing `:1135-1137`). Changing only `worker_pool.py` is a no-op, because `state.corrections` is written solely under `elif result.success:` (`orchestrator.py:1124,1135-1137`). **Do not fix this arm by arm, and do not fix it by hoisting the `:549-551` read** — the defect spans twelve return sites on *both* sides of that read (see Current Behavior's table), and the `should_close` arm itself forks to `mark_failed` at `:1116-1120`, so even a careful per-arm implementation drops corrections for closes that fail to close.
- **An empty corrections list is not a correction.** The numerator is `total_corrected = len(corrections_snapshot)` (`orchestrator.py:1646`), which counts *keys*. Any write of `state.corrections[id]` must stay guarded on a non-empty list, or the reported rate is 100% on every run. "Unconditional write" in D2 means *unconditional in position* (outside the if/elif chain), never unguarded.
- **Reuse `result.was_blocked`, do not introduce a new signal.** The field already exists, is already set by `worker_pool.py:513`, and is already consulted forty lines below the dispatch that ignores it.
- **The sequential path is the reference for routing only.** `issue_manager.py:2132-2135` establishes the intended `was_blocked` → skip routing; its `mark_skipped`/`skipped_issues` mechanism operates on `ProcessingState` and cannot be lifted into `IssuePriorityQueue` unchanged. Its **corrections/denominator handling must not be copied** — see D2.
- **Only `was_blocked` is in scope** *for routing*. NOT_READY stays a failure; `was_gated` has no parallel-path equivalent. See Non-Goals. The corrections half of D2 is deliberately wider — it also covers `should_close` and NOT_READY, which are routing non-goals but the same corrections defect.
- **Naming is settled, do not re-litigate it.** Against the three precedents (`ProcessingState.skipped_issues`, `SprintState.skipped_blocked_issues`, and the new queue bucket): use `_skipped` / `mark_skipped()` / `skipped_count` / `skipped_ids` on `IssuePriorityQueue`, keeping the `mark_failed` trio exactly symmetric — but **no `load_skipped()`**, per D1. If `OrchestratorState` gains an observability field it is `skipped_issues: dict[str, str]`, matching `failed_issues`' id→reason shape and `ProcessingState`'s name. `SprintState.skipped_blocked_issues` keeps its existing name; it is a different layer and renaming it is out of scope.
- **The skip bucket is a within-run counter, not resume state.** No `load_skipped()`, no `add()` guard, no `_scan_issues` union — see **D1**. `_interrupted_issues` (`orchestrator.py:1085-1092`), not `_failed`, is the structural precedent: a transient non-completion the orchestrator deliberately leaves retryable. Any future change that persists skipped ids into a suppression path must first show it does not recreate the permanent-suppression loop D1 documents.
- **A skip count must appear on every surface a failed count appears on.** That is two sites, not one: `_report_results` (`:1604,1618-1622`) and `_maybe_report_status` (`:842-850`). Fixing the counter while leaving a surface silent reproduces this issue's own defect — one outcome, two contradictory presentations. Match each site's own convention: `_report_results` emits `Failed:` unconditionally at `logger.info`; `_maybe_report_status` truthy-guards its part (`if failed > 0`, `:849`) and emits the whole line at **`logger.debug`** (`:884`), so it is a lower-visibility surface than the run summary this issue's Impact section names — worth fixing, not the headline surface.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4025-4048` — `IssuePriorityQueue` Methods table lists `mark_completed`/`mark_failed`/`completed_count`/`failed_count` but is already missing `completed_ids`/`failed_ids`/`load_completed`/`load_failed` rows for the *current* surface. The new `mark_skipped`/`skipped_count`/`skipped_ids` rows go here, along with the pre-existing gap. Document explicitly that there is **no** `load_skipped` and that `add()` does not reject previously-skipped ids — the asymmetry is deliberate (D1) and will otherwise read as an oversight to the next reader.
- `docs/reference/API.md:4014` — documents `WorkerResult.was_blocked`; needs a note that `corrections`/`was_corrected` are now populated on **every** return path from `_run_issue`, not only the success return — injected by default through `_stamped_result`, with `False`/`[]` on returns that precede the ready-issue parse (D2).
- `docs/reference/API.md:6703` — documents `SprintState.skipped_blocked_issues`, the third naming precedent; relevant context for whatever name the new `IssuePriorityQueue` skip bucket takes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/parallel.py` (`:216,328`) — the actual `ll-parallel` entry point instantiating `ParallelOrchestrator`; confirm/exercise end-to-end once the fix lands.
- Update `scripts/little_loops/cli/sprint/run.py` (`:821-836`) — multi-issue wave BLOCKED-issue bucketing currently relies on the sequential retry loop (`:837-903`) to mask the bug; once `IssuePriorityQueue` has a skip bucket, branch on `orchestrator.queue.skipped_ids` here too, not just `completed_ids`/`failed_ids`. **Two consequences this issue previously left implicit:**
  - **This removes a retry, it does not merely re-bucket.** Today a BLOCKED issue lands in `actually_failed` (`:822`) and is therefore re-attempted in-place by the ENH-308 loop (`:837`), which can legitimately succeed if the dependency closed during the wave. Moving it to `skipped_ids` ends that second attempt. Defensible — a dependency wait is not a transient failure — but it is an intentional behavior change and should be asserted by a test, not discovered.
  - **The new branch must call `completed.add(issue_id)`** like both existing arms do (`:826`, `:830`), routing the reason into `SprintState.skipped_blocked_issues` (`sprint.py:103,115,129`). Omitting `completed.add` drops the issue into the trailing `else` (`:833-835`, "interrupted/stranded — leave untracked so it can be retried on resume"), silently producing a *third* behavior that is neither today's nor the intended one.
- **Optional (observability only), per D1:** `scripts/little_loops/parallel/types.py` — a `skipped_issues` field + `to_dict`/`from_dict` entries on `OrchestratorState` (`:243-293`), populated in `_save_state` (`:745-752`) from `queue.skipped_ids` mirroring the `failed_issues` build, with a third clause in the `_load_state` resume log (`:727-731`). **It must have no reader**: no `load_skipped`, no `_scan_issues` union. If that guarantee feels hard to hold, omit the field entirely — nothing in this fix requires it.
- **Do NOT** add `load_skipped(...)` to `scripts/little_loops/parallel/orchestrator.py` `_load_state` (`:724-725`), per **D1**.
- Update `scripts/little_loops/parallel/priority_queue.py` `requeue` (`:130-149`) — add a `_skipped` discard alongside the existing `_failed` discard.
- **Do NOT** add `_skipped` to `scripts/little_loops/parallel/priority_queue.py` `add`'s re-add guard (`:60-66`), per **D1**. A previously-skipped id is re-addable by design.
- Update `scripts/little_loops/parallel/worker_pool.py` — declare `was_corrected = False` / `corrections: list[str] = []` above the `try` (`:398`) and `setdefault` both inside the `_stamped_result` closure (`:390-396`), leaving the assignment where it already is at `:549-551`. **Do not hoist the read** and do not add `corrections=` to individual returns: the defect spans all twelve `_stamped_result(...)` sites (`:462,477,493,509,537,558,622,680,695,717,731,748`), six of them *below* the read, and only default-injection covers them all — see **D2**.
- Update `scripts/little_loops/parallel/orchestrator.py` `_on_worker_complete` — delete the arm-local `state.corrections` write at `:1135-1137` and replace it with a single write beside the timing write at `:1242-1246`, below the whole dispatch chain (decision **D2**). **Carry the `if result.corrections:` guard with it** — an unguarded write makes the rate 100% always. Keep the per-correction `logger.info` loop wherever it reads best; only the state write must move.
- Update `scripts/little_loops/parallel/orchestrator.py:1647` — widen the correction-rate denominator to `completed_count + failed_count + skipped_count`.
- Update `scripts/little_loops/parallel/orchestrator.py` `_report_results` (`:1585-1706`) — render a `Skipped: {count}` line beside `Failed:` (`:1604`) and a `Skipped issues:` block mirroring the existing `Failed issues:` block (`:1618-1622`) and `issue_manager.py:1981-1984`. Note the corrections-rate block (`:1645-1660`) lives in this same function, so the D2 denominator change and the summary rendering are one edit site, not two.
- Update `scripts/little_loops/parallel/orchestrator.py` `_maybe_report_status` (`:820-884`) — add a `Skipped: {n}` part beside the `Failed: {n}` part built at `:842-850` from `queue.failed_count`. This is the **live 5-second progress line**, a separate surface from `_report_results` and previously absent from this list; without it a blocked issue silently disappears from in-run progress.
- **Do NOT** change `scripts/little_loops/parallel/orchestrator.py:956,959`, per **D3** — cleanup and exit code both stay gated on `failed_count == 0`. The resulting exit-`0`-and-clean-state on a blocked-only run is the intended outcome and is what keeps blocked issues retryable.
- **Do NOT** union `state.skipped_issues` into `_scan_issues`'s `skip_ids` (`:968`), per **D1**.
- **Conditional:** if the optional `OrchestratorState.skipped_issues` field is added, `from_dict` (`parallel/types.py:281+`) must read it with `.get(...)` so pre-upgrade state files still load.
- Update `scripts/little_loops/parallel/orchestrator.py` `_maybe_complete_epic` (`:1426`) — union the new skip-id set into `failed_here`. Defensive one-liner only; the `all_done` gate at `:1417-1420` already returns early for a BLOCKED child (still `open` on disk, so `done_count != total`).
- Add `scripts/tests/test_worker_pool.py` coverage for the BLOCKED return path (`:507-520`), asserting `was_blocked=True` **and** that `corrections` is carried through from `ready_parsed`.
- Add `scripts/tests/test_priority_queue.py` a `mark_skipped` test trio mirroring the existing `mark_failed` one, plus `test_requeue_clears_skipped` (mirroring the `_failed` discard) and `test_add_accepts_previously_skipped_id` — the inverse of `test_load_failed_prevents_add` (`:527-540`), pinning **D1**'s deliberate asymmetry so a future "consistency" refactor cannot silently re-add the guard. There is no `load_skipped` to test.
- Add `scripts/tests/test_orchestrator.py` coverage that a BLOCKED result's corrections reach `state.corrections` (the orchestrator-side half of D2), and that the correction rate cannot exceed 100% when the only corrected issue is blocked.
- Add `scripts/tests/test_orchestrator.py::TestDispatchRouting::test_on_worker_complete_blocked_marks_skipped`; update the `orchestrator` fixture (`:141-145`) with `skipped_ids`/`skipped_count` MagicMock defaults.
- Update `scripts/tests/test_sprint_integration.py`'s `MockQueue` classes with a `skipped_ids` property; add a wave-level (non-retry) BLOCKED-in-multi-issue-wave test. **There are eleven `MockQueue` classes in this file, not the two previously named here** (`:297,377,448,516,586,709,983,1053,1131,1201,1476`), each locally defined inside its own test. `cli/sprint/run.py:821-822` reads `orchestrator.queue.completed_ids`/`failed_ids` unconditionally, so the moment a sibling `actually_skipped = set(orchestrator.queue.skipped_ids)` line is added there, **every** one of these that backs a `ParallelOrchestrator` wave raises `AttributeError` — not just the two the earlier draft listed. Mechanical to fix (one property each), but budget for eleven sites and expect the failures to surface all at once rather than in the two tests named above.
- Add `scripts/tests/test_orchestrator.py` coverage pinning **D1**'s resume semantics end-to-end: after a run that skips an issue, a fresh orchestrator over the same repo **does** queue that issue again. This is the behavior the earlier draft would have inverted, and it is currently unpinned in either direction.
- Add `scripts/tests/test_orchestrator.py` coverage for **D3**: a blocked-only run exits `0` **and** removes its state file. Both halves need asserting; today neither is pinned, and the pairing is what keeps D1's retry reachable.
- Add `scripts/tests/test_worker_pool.py` coverage that the CLOSE-verdict return (`:491-505`) **and** the NOT_READY return (`:522-547`) carry `corrections` through from `ready_parsed`, mirroring the BLOCKED-return test — and `scripts/tests/test_orchestrator.py` coverage that a corrected-then-closed and a corrected-then-not-ready issue both reach `state.corrections`. Include the `close_issue()`-returns-false sub-case (`orchestrator.py:1116-1120`), which a per-arm implementation would drop.
- Add `scripts/tests/test_worker_pool.py` coverage for **at least one return below the `:549-551` read** — `work_verified` false (`:695`) is the cheapest — asserting `corrections` is carried through. These are the returns a hoist-only fix silently misses, and they are the common real-world case (corrected during ready-issue, then failed verification). Ideally assert the invariant structurally instead of per-site: a test that every `_stamped_result` call in `_run_issue` yields a `WorkerResult` whose `corrections` matches the locals at that point, or at minimum a defaults test proving `_stamped_result()` with no corrections kwarg still carries them.
- Add `scripts/tests/test_orchestrator.py` coverage that an issue with **no** corrections does **not** get a `state.corrections` entry, pinning the non-empty guard — without it the moved write silently reports a 100% correction rate and every existing rate assertion still passes.
- Add `scripts/tests/test_orchestrator.py` coverage that the live status line (`_maybe_report_status`) reports a skipped issue rather than omitting it.
- **Conditional (only if the optional persisted field is added):** back-compat coverage that `OrchestratorState.from_dict` loads a state dict with no skip key without raising, plus a `_save_state` → `_load_state` round-trip using a real `IssuePriorityQueue` rather than a `MagicMock` — a mocked queue cannot catch the "field persisted empty" failure mode. Also assert the field does **not** suppress re-queueing, guarding the D1 boundary.
- Add `scripts/tests/test_sprint_integration.py` coverage that a BLOCKED issue in a multi-issue wave lands in `SprintState.skipped_blocked_issues`, is **not** re-attempted by the ENH-308 retry loop, and is not left untracked by the trailing `else` — the three-way distinction the wiring note above describes.
- Update `docs/reference/API.md` (`:4025-4048`, `:4014`) for the new `IssuePriorityQueue` surface — including the deliberate absence of `load_skipped` and of an `add()` skip guard — and the `WorkerResult` corrections-field change.
- **Conditional:** update `docs/reference/API.md` for an `OrchestratorState.skipped_issues` field alongside the existing `failed_issues`/`corrections` rows, only if that optional field is added.

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
- **Follow-up to file:** a surviving `ll-parallel` state file suppresses its failed
  issues permanently, not just on the next resume. `_load_state` restores them via
  `queue.load_failed` (`orchestrator.py:725`), which keeps `failed_count > 0`, which
  keeps `_cleanup_state()` (`:956`) from ever firing, while `_save_state`
  (`:748-752`) re-persists them and `_scan_issues` (`:968`) filters them out. Only
  `--clean-start` or deleting the file breaks the cycle. Pre-existing and
  out of scope here, but it is what makes this issue's "no retroactive
  reclassification" non-goal permanent rather than one-shot — see Non-Goals.
- BUG-3253 — cancelled into BUG-3252. Its Behavior Parity analysis of the three
  run paths, and its Codebase Research Findings on the parallel path's
  divergences, are the origin of this issue.

## Related Key Documentation

- `scripts/little_loops/state.py:32-34` — auto-corrections are tracked as a
  quality signal, the reason the rate's accuracy matters.

## Status

**Open** | Created: 2026-08-18 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-08-19T17:39:29 - `0ef4b20b-7464-4211-a563-1f2c1146071b.jsonl`
- fourth pre-implementation review - 2026-08-19 - re-verified every claim against the tree (all held). Four changes, one of which prevented a new defect being shipped. (1) **D2's "single unconditional write" would have broken the correction rate.** The numerator is `total_corrected = len(corrections_snapshot)` (`orchestrator.py:1646`) — it counts *keys* — so dropping the existing `if result.corrections:` guard at `:1135-1137` writes `[]` for every result and pins the reported rate at 100% on every run. "Unconditional" now explicitly means *positional*; the guard stays. (2) **The corrections defect is roughly twice the size D2 described.** Six returns (`worker_pool.py:558,622,680,695,717,748`) sit *below* the `:549-551` read with `corrections` already in scope and still omit the kwarg; five of the six route to `mark_failed` and are in the denominator today. Corrected-then-failed-verification is a far more common run than corrected-then-blocked. A hoist above `:491` — the third pass's prescription — fixes none of them. (3) **Replaced the hoist with default-injection through `_stamped_result`** (`:390-396`), the closure every return already funnels through and whose docstring states this exact principle for `base_sha`. Declare the locals above the `try`, `setdefault` in the closure, leave the assignment at `:549-551`: one edit, all twelve sites, and a thirteenth return added later cannot regress it. This is what makes the standing "do not fix this arm by arm" rule achievable. (4) **Corrected the Non-Goals' pre-upgrade-state rationale**, which claimed the misclassification "self-clears as soon as the state file is cleaned." It never clears: `load_failed` (`:725`) keeps `failed_count > 0`, which keeps `_cleanup_state()` (`:956`) from firing, while `_save_state` re-persists and `_scan_issues` re-filters — the same self-sustaining loop D1 was reversed over, arriving via the pre-existing failed bucket. Accepted, but recorded accurately, and filed as a follow-up (it affects genuine failures too). Minor: decided the new blocked arm sets `_worker_errors` like every other arm; noted `_maybe_report_status` emits at `logger.debug` (`:884`) and truthy-guards its `Failed:` part (`:849`), so it is a lower-visibility surface than the issue's Impact section implies; corrected drifted citations (`:1133-1135`→`:1135-1137`, `:1649`→`:1647`, `:1249-1251`→`:1250-1252`). Confirmed unchanged: `cli/sprint/run.py:821-822` is still the only external consumer of the queue's id lists.
- `/ll:confidence-check` - 2026-08-19T16:45:01 - `0c784620-0a71-45d7-8ef9-9adabdcddd95.jsonl`
- `/ll:decide-issue` - 2026-08-19T16:41:48 - `0c784620-0a71-45d7-8ef9-9adabdcddd95.jsonl`
- `/ll:refine-issue` - 2026-08-19T16:40:46 - `0c784620-0a71-45d7-8ef9-9adabdcddd95.jsonl`
- third pre-implementation review - 2026-08-19 - re-verified all prior claims against the tree (all held). **Reversed D1 and D3.** (1) `_load_state` is called unconditionally from the constructor (`orchestrator.py:235`), gated only on `clean_start` — there is no `--resume` flag — so old-D1's three suppression paths combined with old-D3's `skipped_count` cleanup gate would have filtered blocked issues out of *every* future run, permanently, in a self-sustaining loop (state kept → issues skipped → `load_skipped` → state kept). Old-D1 also did not preserve today's behavior: a blocked-only run today exits `0`, deletes its state, and *does* retry. Resolved D1 as "no suppression at all — the skip bucket is a within-run counter", with `_interrupted_issues` (`:1085-1092`) as the structural precedent; D3 dissolves into a no-op. (2) Widened D2's corrections fix from per-arm to positional: NOT_READY (`worker_pool.py:522-547`) has the identical defect as CLOSE for the identical reason (returns before `:549-551`) and is likewise already in the denominator via `mark_failed` — fixed by hoisting the reads above `:491` and replacing the arm-local `state.corrections` write at `:1133-1135` with one unconditional write at `:1242-1246`, which also covers the `close_issue()`-returns-false fork at `:1116-1120`. (3) Added `_maybe_report_status` (`:820-884`, counters at `:842-850`) — the live 5-second progress line, a second `Failed:` surface absent from every prior pass. (4) Minor: the `_load_state` resume log (`:727-731`) needs a third clause if a skip field is persisted. Also confirmed non-issues: loop termination is `queue.empty()`/`active_count`-based (`:914-916`), not counter-based, so no hang risk; the parallel queue has no dependency gating.
- `/ll:confidence-check` - 2026-08-19T16:14:30 - `7236fc75-b7eb-4e7a-8230-e4a5ff490bc3.jsonl`
- `/ll:decide-issue` - 2026-08-19T16:11:30 - `0e5a9808-01c3-4717-8181-00e110ebacbc.jsonl`
- second pre-implementation review - 2026-08-19 - re-verified every prior claim against the tree (all held). Added five gaps: (1) `_scan_issues:968` as a third, previously-unnamed resume-suppression path, which makes D1-as-written unachievable on its own; (2) new decision **D3** — `_cleanup_state()`/exit code both gate on `failed_count == 0` (`:956,959`), so a blocked-only run deletes the very state D1's guard reads, recommending cleanup gate on both counters and exit code on `failed_count` alone; (3) the CLOSE-verdict return (`worker_pool.py:491-505`) drops `corrections` identically to BLOCKED but already sits in the denominator via `mark_completed` (`:1114`) — folded into D2; (4) the `cli/sprint/run.py` change removes an ENH-308 retry rather than merely re-bucketing, and needs `completed.add()` or it produces a third behavior via the trailing `else`; (5) `OrchestratorState.from_dict` reads keys explicitly, so the new field needs `.get()` for pre-upgrade state files. Settled the skip-bucket naming against all three precedents; corrected the `_report_results` citation to `:1585-1706`.
- `/ll:confidence-check` - 2026-08-19T15:49:53 - `26efdaf5-1644-47d9-8da6-2ce07fa4e6bd.jsonl`
- pre-implementation review - 2026-08-19 - verified all claims against the tree. Corrected stale `issue_manager.py:2107-2111` citations to `2132-2135`; found the orchestrator-side half of the corrections defect (`state.corrections` written only under `elif result.success:`); established that the sequential path is an unsafe reference for corrections/denominator handling; surfaced the `add()` re-add guard as decision D1 and the `_save_state` persist half as a required wiring step; added `requeue()`; downgraded the `_maybe_complete_epic` touchpoint (unreachable behind the `all_done` gate); fenced NOT_READY and `was_gated` as non-goals.
- `/ll:wire-issue` - 2026-08-19T15:21:48 - `6f435684-155f-4724-92e1-2b56419366c1.jsonl`
- `/ll:refine-issue` - 2026-08-18T14:56:18 - `1b75a5d5-cd19-4f54-9db4-f0438e3206cc.jsonl`
- `/ll:confidence-check` - 2026-08-18T03:58:40 - `e1587cf9-62dc-4b5b-8de8-7b698165c90b.jsonl`
- filed from pre-implementation review - 2026-08-18 - factored out of BUG-3253 before its cancellation into BUG-3252; claims verified against `orchestrator.py:1096-1251`, `worker_pool.py:508-520,743-744`, `priority_queue.py:110-194`
