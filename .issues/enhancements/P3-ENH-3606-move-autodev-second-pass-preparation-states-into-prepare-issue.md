---
id: ENH-3606
type: ENH
title: Move autodev second-pass preparation states into prepare-issue
priority: P3
status: open
discovered_by: issue-size-review
discovered_date: '2026-09-26'
decision_needed: false
blocks:
- ENH-3600
relates_to:
- ENH-3590
- ENH-3577
- ENH-3609
- ENH-3610
parent: ENH-3601
confidence_score: 80
outcome_confidence: 46
score_complexity: 0
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3606: Move autodev second-pass preparation states into prepare-issue

## Summary

Second half of ENH-3601 (Option B), re-cut on 2026-09-26. With the `prepare-issue`
pass-through wrapper and its ledger-ownership rule in place (ENH-3605), move the whole
second-pass cluster out of `autodev.yaml` in one change:

- wire/refine;
- reconcile and design remedy;
- size-review and atomic remediation;
- go/no-go;
- pre-deferral remedy;
- the obligation selectors ENH-3610/3611 add.

Afterwards autodev owns only the queue, the ledger bookkeeping, and the fail-closed proof
gate in front of `implement_current`. The go/no-go trigger stays the existing deterministic
`deferred_reason: oversized_atomic` predicate, unchanged.

## Why one change

The states form one strongly connected cluster: reconcile → size-review →
`recheck_after_size_review` → pre-deferral remedy → reconcile, with the selectors
re-entering the refine child from several points. A `loop:` child cannot route into its
parent's states. Any cut through the cluster leaves edges with no destination, or forces an
interim "continue in autodev" outcome that `PreparationOutcome` does not have. That is why
the original ENH-3605/3606 split was replaced with plumbing (ENH-3605) followed by this
single move.

## Parent Issue

Decomposed from ENH-3601: Move autodev second-pass preparation routing into a preparation
controller. See the parent for the decision rationale.

## Current Behavior

After ENH-3605 and ENH-3609–3611, autodev still owns the second-pass ladder behind its
`check_passed` gate. That ladder is `select_obligation_post_refine` →
`check_missing_artifacts` → wire/refine → reconcile/design remedy → size-review/atomic →
`select_obligation_post_size_review` → go/no-go and pre-deferral remedy →
`select_obligation_pre_implement`. It also owns the `wire`, `reconcile` and `atomic`
rescoring triplets. Each ladder exit re-enters `refine_current` or reaches the proof gate
inside autodev.

## Expected Behavior

`prepare-issue` runs its inner `refine-to-ready-issue` and then its own pass gate and
second-pass ladder. It re-enters its inner loop when a selector returns `DECISION*` or
`PROOF*`, and emits one terminal record: `READY`, a ledgered `BLOCKED:*` / `DEFERRED:*`
stop, `DECOMPOSED`, `CANCELLED` or `RETRYABLE_ERROR:*`. Autodev has no second-pass state.

## Scope Boundaries

- **In scope**: every state listed in Scope, the shared rescoring path, the wrapper
  terminals, the autodev fail-safes for tokens that become impossible, the tests/docs that
  pin these states, and the queue-only absence test.
- **Out of scope**:
  - widening the go/no-go trigger with a risk signal (separate follow-up);
  - removing legacy sentinels and ledger files (ENH-3600);
  - new `PreparationOutcome` values or run-record tokens;
  - changes to `refine-to-ready-issue.yaml`;
  - `recursive-refine.yaml`'s same-named states (`size_review_snap`, `check_broke_down`,
    `recheck_scores`, `enqueue_or_skip`, `detect_children`).

## Scope

### Boundary edge table (regenerated 2026-09-26 against post-ENH-3611 `autodev.yaml`)

Computed by parsing `autodev.yaml` against the move set below (`on_*`, `next`, `route.*`;
fragment-supplied edges excluded). Every entry ends internal to the wrapper, as a wrapper
terminal, or retargeted in autodev. Re-run the computation before editing if `autodev.yaml`
has changed since.

**Staying → moving (retarget in autodev):**

| Edge | Today | After |
|---|---|---|
| `refine_current.on_success` | `count_repair_cycle_refine` | `copy_broke_down` |
| `check_passed.on_yes` | `select_obligation_pre_implement` | `check_proof_defer_or_implement` |
| `check_passed.on_no` / `on_cannot_judge` | `select_obligation_post_refine` | `skip_inflight` |
| `check_broke_down.on_no` | `enqueue_or_skip` | deleted with `check_broke_down` (see States that stay) |
| `check_parent_resolved.on_no` / `on_error` | `recheck_scores` | `skip_inflight` (only reachable on a DECOMPOSED-guarantee violation) |

**Moving → staying (becomes wrapper-internal or a wrapper terminal):**

| Edge(s) | Today | In the wrapper |
|---|---|---|
| `count_repair_cycle_refine.next` / `on_error` | `copy_broke_down` | `run_refine_to_ready` |
| `select_obligation_post_refine` `DECISION` / `PROOF`, `select_obligation_post_size_review` `PROOF`, `select_obligation_pre_implement` `DECISION` / `PROOF`, `dispatch_pre_deferral_remedy.on_yes` | `refine_current` | `count_repair_cycle_refine` (never `run_refine_to_ready` directly; see Repair-cycle counter) |
| `select_obligation_pre_implement` `_` / `_error` | `check_proof_defer_or_implement` | `mark_ready` terminal |
| `select_obligation_post_refine._error`, `check_missing_artifacts.on_no` / `on_error` | `detect_children` | wrapper `detect_ladder_children` (see Inner-loop success routing) |
| `check_parent_resolved_post_size_review.on_yes` | `recover_subloop_children` | `mark_decomposed` terminal (see Queue ownership) |
| `enqueue_or_skip.on_yes` | `dequeue_next` | `mark_decomposed` terminal |
| `check_scores_present.on_cannot_judge` / `on_error`, `clear_scores.on_error`, `mark_rescore_origin_atomic.on_error`, `recheck_after_size_review.on_cannot_judge`, `regate_after_atomic_remediation.on_cannot_judge` (post-ENH-3615 shared chain; the per-origin `*_wire` / `*_reconcile` / `*_atomic` triplet names no longer exist) | `mark_scores_absent_infra` | `mark_scores_absent` terminal |
| `on_rate_limit_exhausted` of `run_wire`, `run_refine`, `rerun_confidence` (shared), `reconcile_current`, `refine_for_design`, `remediate_oversized_atomic`, `run_go_no_go` | `finalize_rate_limited` | `mark_rate_limited` terminal |
| `run_size_review.on_rate_limit_exhausted` | `dequeue_next` | `mark_rate_limited` terminal (decided halt, see Rate limits) |
| `check_go_no_go_eligible.on_no`, `check_go_no_go_waiver.on_no`, `check_pre_deferral_remedy.on_no`, `record_reentry_exhausted.next` | `dequeue_next` | `failed` (the stop was already ledgered and recorded upstream; see Terminal table) |
| `on_error` of `check_atomic_design_remedy`, `check_go_no_go_eligible`, `check_go_no_go_waiver`, `check_pre_deferral_remedy`, `enqueue_or_skip`, `recheck_after_size_review`, `regate_after_atomic_remediation`, `reopen_waived`, `record_reentry_exhausted` | `dequeue_next` | `mark_ladder_error` terminal (see Terminal table) |

### States that move into `prepare-issue.yaml`

- **Pass gate and selectors**: a wrapper-local `check_passed` (reached from
  `route_inner_success`, see Inner-loop success routing), `select_obligation_post_refine`,
  `select_obligation_post_size_review`, `select_obligation_pre_implement` (ENH-3610/3611),
  and `record_reentry_exhausted` (the `DECISION_EXHAUSTED` target of both DECISION-probing
  selectors).
  - A selector's `refine_current` re-entry target becomes the wrapper's
    `count_repair_cycle_refine`, which then runs `run_refine_to_ready`.
  - Its proof-gate target (`check_proof_defer_or_implement`) becomes the wrapper's
    `mark_ready` terminal.
  - The wrapper's `check_passed.on_error` and `select_obligation_post_refine._error` go to
    `detect_ladder_children` (today's `detect_children` target).
- **Wire/refine**: `check_missing_artifacts`, `run_wire`, `run_refine`,
  `count_repair_cycle_wire`, and the `wire` rescoring triplet
  (`rerun_confidence_after_wire`, `clear_scores_before_wire`, `check_scores_present_wire`),
  which the shared rescoring path replaces.
- **Reconcile/design remedy**: `check_reconcile_needed`, `reconcile_current`,
  `refine_for_design`, `check_atomic_design_remedy`, `dispatch_design_remedy`,
  `count_repair_cycle_reconcile`, `count_repair_cycle_refine_for_design`, and the
  `reconcile` rescoring triplet (`rerun_confidence_after_reconcile`,
  `clear_scores_before_reconcile`, `check_scores_present_reconcile`).
- **Size-review/atomic**: `run_size_review`, `count_repair_cycle_size_review`,
  `check_size_review_ran_this_pass`, `check_guard2_verdict`, `check_guard2_score_fallback`,
  `check_readiness_for_atomic_remediation`, `remediate_oversized_atomic`,
  `regate_after_atomic_remediation`, `recheck_after_size_review`, `recheck_scores`,
  `check_parent_resolved_post_size_review`, the `atomic` rescoring triplet
  (`rerun_confidence_after_atomic_remediation`, `clear_scores_before_atomic`,
  `check_scores_present_atomic`), plus the child-detection half of `enqueue_or_skip` (see
  Queue ownership).
- **Go/no-go**: `check_go_no_go_eligible`, `run_go_no_go`, `check_go_no_go_waiver`,
  `reopen_waived` (only for `deferred_reason: oversized_atomic`).
- **Pre-deferral remedy**: `check_pre_deferral_remedy`, `dispatch_pre_deferral_remedy`.
- **Repair-cycle counter**: `count_repair_cycle_refine` moves to become the wrapper's
  pre-state of `run_refine_to_ready` (`clear_record` → `count_repair_cycle_refine` →
  `run_refine_to_ready`). After the move, re-entries happen inside the wrapper and no
  longer pass autodev's `refine_current → count_repair_cycle_refine`. Left in autodev, the
  counter would undercount, and `recheck_after_size_review`'s stagnation backstop (count ≥
  2) would stop firing. Moving it keeps "every inner entry increments" for the first entry
  and every re-entry. **Every re-entry edge must target `count_repair_cycle_refine`, never
  `run_refine_to_ready` directly** — that includes `dispatch_pre_deferral_remedy.on_yes`
  (today → `refine_current`), not only the selectors. Today the counter increments *after*
  the sub-loop returns; the wrapper increments *before*. The count seen by
  `recheck_after_size_review` is the same, because both orders complete the increment
  before any ladder state runs.

### States that stay in autodev (queue-only)

- `init`, `dequeue_next` and the dequeue checks (`check_status_at_dequeue`,
  `check_blockers_at_dequeue`, `check_gate_at_dequeue` and their skip/defer states).
- `refine_current`, `copy_broke_down`, the ENH-3607/3609 routers and `ledger_child_stop`.
- `check_passed`, kept as a fail-closed double check on `READY`; its `on_no` and
  `on_cannot_judge` become `skip_inflight`. This is a second copy: the wrapper gets its own
  `check_passed` (see "States that move"), and autodev's copy stays with the retargets in
  "Boundary edge retargets" below.
- `check_proof_defer_or_implement`, `implement_current` and the post-implementation states.
- Queue and ledger states: `skip_inflight*`, `mark_*_infra`, `detect_children`,
  `enqueue_children`, `check_parent_resolved`, `recover_subloop_children`,
  `finalize_rate_limited`, `finalize_done` and the terminals.
- **Decided (2026-09-26)**: delete `size_review_snap` and `check_broke_down`. They exist to
  feed `recheck_scores` → `run_size_review`, which move. The "flag set and children exist"
  case they shortcut is already `detect_children.on_yes`. Autodev's no-children path
  becomes `detect_children.on_no` / `on_error` → `check_parent_resolved`, with
  `check_parent_resolved.on_yes` → `recover_subloop_children` and `on_no` / `on_error` →
  `skip_inflight`. The `on_no` leg is reachable only if the wrapper breaks the DECOMPOSED
  guarantee, so `refine_failed` is the right row for it.
- **Decided (2026-09-26)**: delete `mark_scores_absent_infra`. After the move, only moving
  states target it (verified by the edge table), and the wrapper's `mark_scores_absent`
  terminal replaces it. `autodev-scores-absent.txt` loses its only writer; remove any
  reader or note that it is no longer written.

### Boundary edge retargets (autodev, verified 2026-09-26 against post-ENH-3611)

- `refine_current.on_success` → `copy_broke_down` (was `count_repair_cycle_refine`, which
  moves into the wrapper).
- autodev `check_passed.on_yes` → `check_proof_defer_or_implement` (was
  `select_obligation_pre_implement`, which moves); `on_no` / `on_cannot_judge` →
  `skip_inflight`; `on_error` stays `detect_children`.
- `route_refine_success` (ENH-3609) sends `READY` / `BLOCKED` / `MISSING` / `_` →
  `check_passed`, `DECOMPOSED` → `detect_children`, and every suffixed `BLOCKED:*` /
  `DEFERRED:*` / `RETRYABLE_ERROR:*` → `skip_inflight`. So the wrapper ends `ready` and
  `decomposed` in its `done` terminal and **every stop row in its `failed` terminal**, which
  reaches `route_refine_outcome` → `ledger_child_stop` / `finalize_rate_limited` /
  `skip_inflight_infra`. A stop ending in `done` would be double-ledgered by `skip_inflight`.
- `route_refine_outcome` maps `DECOMPOSED` → `skip_inflight`; the wrapper never emits
  `decomposed` through `failed`, so that route stays a fail-safe.
- `detect_children.on_no` / `on_error` → `check_parent_resolved` (was `size_review_snap`,
  deleted); `check_parent_resolved.on_no` / `on_error` → `skip_inflight` (was
  `recheck_scores`, which moves).

### Inner-loop success routing and the broke-down flag

The wrapper's inner `done` can no longer go `forward_done` → `done`, because a
thresholds-unmet inner `done` must run the ladder. Replace it with a wrapper-local router:

- `run_refine_to_ready.on_yes` → `route_inner_success`, which reads
  `ll-issues run-record read <ID> --writer refine-to-ready-issue --format token`, then
  writes `0` to `refine-broke-down` in the same action before printing the token:
  - `CANCELLED` → `forward_done` → `done` (autodev's `skip_cancelled` ledgers it);
  - `DECOMPOSED` → `detect_ladder_children` (below);
  - `READY` / `BLOCKED` / `MISSING` / `_` / `_error` → wrapper `check_passed`.

  The reset has to happen here, not only in `detect_ladder_children`: `MISSING` / `_` /
  `_error` fail open to `check_passed` even when the inner loop broke the issue down (its
  `|| true` record write can fail after `write_broke_down` set the flag to `1`), and from
  `check_passed` the ladder reaches every stop terminal without passing
  `detect_ladder_children`. Every inner success passes `route_inner_success`, including
  the selectors' `DECISION` / `PROOF` re-entries. The routing token comes from the saved
  record, not the flag, and `detect_ladder_children` diffs issue IDs, so nothing after
  this state needs the inner loop's flag value. This mirrors ENH-3615's reset in autodev's
  `copy_broke_down`.
- `detect_ladder_children` is the wrapper's copy of `detect_children` plus
  `check_parent_resolved`. It diffs against `autodev-pre-ids.txt` (written by
  `dequeue_next`) with BUG-2729 provenance matching:
  - children found → `mark_decomposed` (autodev's `detect_children` finds the same
    children and `enqueue_children` enqueues them);
  - no children, parent resolved → `mark_decomposed`;
  - no children, parent not resolved → `recheck_scores` (the flag is already `0` from
    `route_inner_success`). This keeps the BUG-1183 fallback: an inner breakdown that
    produced no files still gets the ladder's own size-review.
- It is also the target of the ladder's "go to size review" edges
  (`check_missing_artifacts.on_no` / `on_error`, `select_obligation_post_refine._error`,
  wrapper `check_passed.on_error`), replacing today's trip through autodev's
  `detect_children` → `size_review_snap` → `check_broke_down` → `check_parent_resolved`.
  On that path it also refreshes the size-review baseline (`size_review_snap`'s job)
  before `recheck_scores`, so `enqueue_or_skip`'s diff sees only what `run_size_review`
  creates.
- **Broke-down flag rule.** `outcome_from_legacy_class` (`little_loops.run_record`) checks
  `broke_down` before every legacy class and before thresholds, and `run-record write` reads
  the shared `refine-broke-down`. Any wrapper terminal written while the flag is `1` becomes
  `decomposed`, whatever `--legacy-class` it passes. So:
  - `route_inner_success` writes `0` after every inner success, so no ladder path starts
    with the flag at `1` (above);
  - `mark_decomposed` writes `1` before its record write (a resolved parent with no
    children otherwise records `ready` or `blocked`);
  - no other wrapper terminal runs with the flag at `1`. Pin this with two tests, both
    recording `DEFERRED:gate_unmet`, not `DECOMPOSED`: an inner breakdown with no children
    followed by a `design_gate_failed` stop; and an inner breakdown whose record is
    `MISSING` (routed to `check_passed`) followed by a stop.
- Autodev's `copy_broke_down` runs after the wrapper returns, so it copies the wrapper's
  final flag value.

### Shared rescoring path

ENH-3615 builds this path in `autodev.yaml` first. This issue then relocates it: its
unknown-origin exit and `on_error` exits change from `mark_scores_absent_infra` to the
wrapper's `mark_scores_absent`, and its rate-limit exit from `finalize_rate_limited` to
`mark_rate_limited`. The design as ENH-3615 implements it:

Replace the `wire`, `reconcile` and `atomic` triplets with one path. Each entry point
writes `autodev-rescore-origin-<ID>` (`wire` | `reconcile` | `atomic`; the `autodev-`
prefix matches the other per-pass markers, and `dequeue_next` clears it) → `clear_scores` →
`rerun_confidence` → `check_scores_present` → `route_after_rescore`. `route_after_rescore`
reads the marker and dispatches to that origin's post-ENH-3611 successor. Today those
successors are `enqueue_or_skip`, `recheck_after_size_review` and
`regate_after_atomic_remediation`.

- The origin is written inline in `count_repair_cycle_wire`, `count_repair_cycle_reconcile`
  and `count_repair_cycle_refine_for_design`, and by one new state,
  `mark_rescore_origin_atomic` (after `remediate_oversized_atomic`).
- Keep the per-origin retry marker names (`autodev-rescore-retry-<origin>-<ID>`) so
  `dequeue_next`'s clear is unchanged.
- `route_after_rescore` deletes the origin marker after reading it. An unknown or missing
  origin routes to the scores-absent terminal (fail closed), in both
  `check_scores_present` and `route_after_rescore`.
- Keep the BUG-3588 freshness rules.
- Re-declare the `confidence-check-recheck` `pruning_profile:` once.

### Queue ownership and the DECOMPOSED guarantee

- The wrapper never writes `autodev-queue.txt` and never runs `finalize-decomposition`.
- Size-review decomposition keeps the child detection from `enqueue_or_skip`: diff the IDs
  and match `parent:`/"Decomposed from" provenance (BUG-2729) into
  `autodev-new-children.txt`. It then writes `1` to `refine-broke-down` and ends in a
  `decomposed` record with `--child-ids`.
- Autodev's existing `DECOMPOSED` → `detect_children` → `enqueue_children` path does the
  enqueue. `enqueue_children` already writes the `decomposed` row and runs
  `finalize-decomposition`, exactly as `enqueue_or_skip`'s queue branch does today.
- Confirm that `detect_children`'s `autodev-pre-ids.txt` baseline predates the wrapper, so
  size-review children fall inside its diff. Pin this with a test.
- **Guarantee**: the wrapper emits `decomposed` only when `child_ids` is non-empty or the
  parent is resolved. `check_parent_resolved_post_size_review.on_yes` emits `decomposed`, so
  autodev reaches `recover_subloop_children` through `detect_children` (no children) →
  `check_parent_resolved`. A parent that is not resolved and has no children continues the
  wrapper's ladder and never returns to autodev.
- `dequeue_next` stays the only cleaner of the per-pass markers
  (`autodev-size-review-ran-this-pass`, `autodev-pre-deferral-remedy.txt` / `-fired`, rescore
  retry markers, the new `autodev-rescore-origin-<ID>`, the repair-cycle counter reset). The
  wrapper must not clear them on entry, because re-entries within one pass must still see
  them.
- **`resolved_by_subloop` has one writer.** `recheck_after_size_review` and
  `regate_after_atomic_remediation` write an `ID  resolved_by_subloop` row today, and
  autodev's `recover_subloop_children` writes `decomposed` or `resolved_by_subloop` again
  when the wrapper's `decomposed` record reaches it. Drop the row write from the moved
  states; `recover_subloop_children` owns it. The wrapper also writes no `decomposed` row
  (`enqueue_children` owns that).
- **Staging has one writer.** Five moving states append to `autodev-staged.txt`
  (`check_passed`, `recheck_scores`, `recheck_after_size_review`,
  `regate_after_atomic_remediation`, `reopen_waived`), and autodev's `check_passed` appends
  again. `finalize_done`'s `sort -u` hides the duplicate, but an ID the wrapper staged and
  autodev's `check_passed` then rejects stays staged and lands in `autodev-unverified.txt`.
  Remove the staging appends from the wrapper so autodev's `check_passed` is the only
  writer. The selectors' un-stage blocks can then go (nothing in the wrapper stages);
  keep them only if they stay harmless and a test says why.

### Terminal table

Every row writes a `writer: prepare-issue` record. Per ENH-3605's rule, the wrapper writes
the ledger row with the same reason string as today, and autodev routes every
`BLOCKED:*` / `DEFERRED:*` to `ledger_child_stop` (no row).

| Wrapper stop (today's row) | Outcome / `--legacy-class` | Autodev route |
|---|---|---|
| `oversized_atomic` (incl. go/no-go escalation, waiver declined) | `deferred` / `gate_unmet` | `ledger_child_stop` |
| `design_gate_failed` | `deferred` / `gate_unmet` | `ledger_child_stop` |
| `readiness_stagnated`, `low_readiness` | `deferred` / `gate_unmet` | `ledger_child_stop` |
| `decision_unresolved` (from `recheck_after_size_review`) | `blocked` / `decision_unresolved` | `ledger_child_stop` |
| `decision_unresolved` (from `record_reentry_exhausted`, selector re-entry cap) | `blocked` / `decision_unresolved` | `ledger_child_stop` |
| atomic-remediation failure | `blocked` / `quality` | `ledger_child_stop` |
| `resolved_by_subloop` / parent resolved (no wrapper row; see Queue ownership) | `decomposed` (see guarantee) | `detect_children` → `check_parent_resolved` → `recover_subloop_children` |
| size-review decomposition | `decomposed` + `--child-ids` | `detect_children` → `enqueue_children` |
| rate-limit exhaustion (`mark_rate_limited`) | `retryable_error` / `infra` + `--evidence-refs rate_limit_exhausted` | `finalize_rate_limited` |
| scores absent after repair (`mark_scores_absent`) | `retryable_error` / `infra` | `skip_inflight_infra` |
| state `on_error` exits that today go to `dequeue_next` (`mark_ladder_error`) | `retryable_error` / `infra`, unless a stop record already exists (below) | `skip_inflight_infra` |
| ladder complete, gates pass (`mark_ready`) | `ready` | `check_passed` → `check_proof_defer_or_implement` |

- **The state that writes a ledger row also writes the run record, in the same action.** Today
  the stop rows are written upstream (`recheck_after_size_review`,
  `regate_after_atomic_remediation`, `record_reentry_exhausted`) and the exits that follow
  (`check_pre_deferral_remedy.on_no`, `check_go_no_go_eligible.on_no`,
  `check_go_no_go_waiver.on_no`, `record_reentry_exhausted.next`) cannot tell which reason
  was written. With the record written next to the row, those exits go straight to
  `failed`.
- **A stop row with a later remedy is not final.** `recheck_after_size_review` can arm a
  pre-deferral remedy instead of deferring; that branch writes no row and no record. A
  remedy that re-enters the inner loop therefore starts with no stop record for the pass.
- **Wrapper stops never pass through `forward_stop`.** For `BLOCKED:quality` and
  `DEFERRED:gate_unmet`, `forward_stop` appends a `refine_failed` row. The wrapper's own
  stops (`oversized_atomic`, `design_gate_failed`, `readiness_stagnated`, `low_readiness`,
  atomic-remediation failure) already wrote their row, so they call `run-record write`
  directly. `forward_stop` stays only for the inner loop's own `failed` exit.
- **`mark_ladder_error`** writes `retryable_error` / `infra` only when no `prepare-issue`
  record exists for this pass. When the failing state had already written its stop row and
  record (for example `record_reentry_exhausted` erroring after its `set-status`), the
  existing record stands. An infra record on top would send the issue to
  `skip_inflight_infra` and add a second row.
- **Every terminal that ends in `failed` writes `refine-terminal-class` before its record
  write**, as `mark_inner_error` and the inner loop's stop states do. Record writes are
  `|| true`. When one fails, autodev reads `MISSING` and `skip_inflight` falls back to the
  sentinel. `mark_rate_limited`, `mark_scores_absent` and `mark_ladder_error` write
  `infra`. Without it, a failed write ledgers an infra stop as `refine_failed` (quality).
  The stop states write their legacy class (`gate_unmet`, `decision_unresolved`,
  `quality`). This keeps the MISSING fallback's classification correct. Removing that
  fallback is ENH-3600's job.
- **`mark_ready` and the done-path writes pass `--readiness-threshold` /
  `--outcome-threshold`** from context, as the inner loop's writes do; without them
  `thresholds_met` falls back to config and can disagree with the gates the ladder used.
- Keep the `deferred_reason` frontmatter writes (`ll-issues set-status --reason ...`)
  exactly as today; `deferred_triage`, `show` and `check_readiness --honor-waiver` read them.
- `reopen_waived` runs inside the same wrapper run that wrote the `oversized_atomic` row, so
  its `grep -vxF "$ID  oversized_atomic"` removal and `autodev-inflight` re-arm keep
  working. Because the row and the record are now written together, `reopen_waived` must
  also clear the `DEFERRED:gate_unmet` record it is undoing
  (`run-record clear --writer prepare-issue`). Otherwise `mark_ladder_error` would leave a
  stale stop record in place if a later state errors. Pin both with a test.

### Rate limits

- Every moved slash state (`run_wire`, `run_refine`, `reconcile_current`, `refine_for_design`,
  `rerun_confidence`, `remediate_oversized_atomic`, `run_go_no_go`) keeps
  `with_rate_limit_handling`. Its `on_rate_limit_exhausted` goes to a wrapper-local
  `mark_rate_limited` terminal that writes `--legacy-class infra --evidence-refs
  rate_limit_exhausted`. That preserves today's halt through `finalize_rate_limited`.
- `run_size_review` is the odd one out today: `on_rate_limit_exhausted: dequeue_next` drops
  the issue silently, with no row. **Decided (2026-09-26)**: halt like every other site.
  `run_size_review`'s `on_rate_limit_exhausted` goes to `mark_rate_limited`, which ends in
  `finalize_rate_limited` in autodev. A dedicated test pins it.

### Accepted behavior changes

Document these in `docs/guides/LOOPS_REFERENCE.md`:

- Scores-absent stops and `on_error → dequeue_next` drops now produce one
  `refine_failed_infra` row. Today they are invisible in `finalize_done`, and
  `autodev-scores-absent.txt` is never read.
- `run_size_review` rate-limit exhaustion now halts the queue through `finalize_rate_limited`
  instead of silently dropping the issue and moving to the next one.
- A parent that the ladder finds already `cancelled` now records `CANCELLED` (rule 1 of
  `outcome_from_legacy_class`) and is ledgered `cancelled` by autodev's `skip_cancelled`,
  instead of `resolved_by_subloop`. A `done` parent keeps today's `decomposed` /
  `resolved_by_subloop` row through `recover_subloop_children`.

### Mechanics

- Add `import: [lib/common.yaml]` to `prepare-issue.yaml`. The wrapper imports nothing
  today, and the moved states use the `with_rate_limit_handling`, `shell_exit` and
  `harness_exit` fragments. Rewrite the header comment's "No rate-limit fragment" note: it
  still holds for `run_refine_to_ready` (a `loop:` state, BUG-3390), but the moved slash
  states use the fragment.
- Move `capture_reachability_ok: true` and its rationale comment from `autodev.yaml` to
  `prepare-issue.yaml`. The validator reports `check_guard2_verdict`'s
  `${captured.size_review_output.output}` as reachable without `run_size_review`, through
  `check_reconcile_needed.on_no` → `check_size_review_ran_this_pass`. The runtime marker
  gate (BUG-2744) closes that path, but the static validator cannot model it. After the
  move, autodev has no reader of that capture. Drop the flag from autodev, whose comment
  also cites the deleted `check_broke_down`. Confirm that `ll-loop validate autodev`
  passes without the flag.
- Rewrite every `${captured.input.output}` in the moved states to `${context.input}`
  (passthrough flattens `captured` into the child context). Update or remove the
  `# ll-lint: mr11-ok(captured.input.output)` markers (`TestMr11MarkerSet`).
- Moved states must take their captures from wrapper states. For example,
  `captured.size_review_output` feeds `check_guard2_verdict` / `check_guard2_score_fallback`
  through `evaluate.source`.
- Re-declare `pruning_profile:` blocks: `run_wire` `wire-issue-auto`, `run_refine` /
  `refine_for_design` `refine-issue-repair`, `rerun_confidence` `confidence-check-recheck`,
  `reconcile_current` `reconcile-issue-auto`, `run_size_review` `issue-size-review-auto`,
  and `run_go_no_go` `go-no-go-auto`. Otherwise MR-12 warns.
- Raise `prepare-issue.yaml`'s `max_steps: 20`. The wrapper grows from 7 states to about
  45, and one pass can run the ladder several times (selector re-entries, pre-deferral
  remedy, go/no-go reopen). Size it from the longest path times the re-entry caps (DECISION
  1, PROOF 1, pre-deferral remedy 1, lifetime `max_refine_count`), and pin the value with a
  comment showing the arithmetic. Hitting the limit ends the wrapper outside `done`, which
  autodev routes as a failure.
- Wrapper capture names flatten into the inner loop's context on every re-entry (header
  comment in `prepare-issue.yaml`). Before adding captures (`size_review_output` and any
  others the moved states use), confirm no name collides with a context key or capture
  that `refine-to-ready-issue.yaml` reads.
- Update the `prepare-issue.yaml` header call-chain comment to the new graph.
- Shared per-issue files must keep their names, because both loops read them through the
  shared `run_dir`:
  - `autodev-repair-cycle-count.txt`, `autodev-pre-readiness.txt`,
    `autodev-design-gate-failed-<ID>`, `autodev-design-remedy-attempted-<ID>`,
    `autodev-atomic-design-remedy-pending`;
  - `autodev-contradiction-reconcile-*`, `autodev-go-no-go-attempted-<ID>`,
    `autodev-pre-deferral-remedy*`, `autodev-size-review-ran-this-pass`, `spike-runs-<ID>`.

## Tests

- **Queue-only absence**: a `REMOVED_INLINE_STATES`-shaped parametrized test covering every
  moved state (pattern: `TestIssueRefinementSubLoop` ~`test_builtin_loops.py:1323`/`:1413`).
  Also assert that `enqueue_children`, `dequeue_next` and `recover_subloop_children` are the
  only writers of `autodev-queue.txt` across both loops.
- **Wrapper structure** (`test_prepare_issue.py`): the moved states exist; every re-entry
  edge (the five selector routes and `dispatch_pre_deferral_remedy.on_yes`) targets
  `count_repair_cycle_refine`, and no state other than `count_repair_cycle_refine` targets
  `run_refine_to_ready`; the proof target is `mark_ready`; every terminal writes
  `--writer prepare-issue`; every moved slash state's `on_rate_limit_exhausted` targets
  `mark_rate_limited`; there is exactly one `clear_scores` / `rerun_confidence` /
  `check_scores_present` / `route_after_rescore` chain; `run_refine_to_ready.on_yes`
  targets `route_inner_success`; no wrapper state appends to `autodev-staged.txt` or writes
  a `resolved_by_subloop` / `decomposed` row; no wrapper stop state routes through
  `forward_stop`; `max_steps` matches its pinned arithmetic; the wrapper imports
  `lib/common.yaml` and sets `capture_reachability_ok: true`; every `failed`-bound
  terminal writes `refine-terminal-class` before its record write.
- **Wrapper execution** (real FSM, stub skills):
  - one case per terminal-table row, asserting the record token and the exact ledger rows
    (no double count);
  - the rescoring dispatch for each origin, plus unknown origin → scores-absent;
  - the repair-cycle counter increments on the first entry and on each re-entry, and the
    stagnation backstop still fires at count ≥ 2;
  - the DECOMPOSED guarantee (no `decomposed` record with empty `child_ids` and an
    unresolved parent);
  - `reopen_waived` removes the row, clears the stop record and re-enters;
  - the go/no-go trigger predicate is unchanged;
  - `route_inner_success` leaves `refine-broke-down` at `0` for every token;
  - inner `DECOMPOSED` with no children and an unresolved parent reaches `run_size_review`
    with the flag at `0` (BUG-1183 fallback);
  - broke-down trap, two cases, both recording `DEFERRED:gate_unmet`, not `DECOMPOSED`:
    inner breakdown with no children, then a `design_gate_failed` stop; inner breakdown
    with a `MISSING` record (→ `check_passed`), then a stop;
  - a resolved parent with no children records `DECOMPOSED` (flag written first);
  - `record_reentry_exhausted` records `BLOCKED:decision_unresolved` with one
    `decision_unresolved` row;
  - `mark_ladder_error` after a stop record exists leaves that record in place (one row);
  - a failed record write on `mark_scores_absent` (record absent, sentinel `infra`)
    reaches `skip_inflight_infra` in autodev, not `refine_failed`;
  - inner `CANCELLED` forwards and ends `done`.
- **Autodev**:
  - `check_passed.on_no` / `on_cannot_judge` → `skip_inflight`;
  - `size_review_snap`, `check_broke_down` and `mark_scores_absent_infra` are absent;
  - `autodev.yaml` no longer sets `capture_reachability_ok` and still validates;
    `detect_children.on_no` → `check_parent_resolved`, and `check_parent_resolved.on_no` →
    `skip_inflight`;
  - real-FSM: a wrapper `decomposed` record for a resolved parent with no children
    reaches `recover_subloop_children` and writes exactly one `resolved_by_subloop` row;
  - `dequeue_next` clears `autodev-rescore-origin-<ID>`;
  - `TestProofGateFailClosed` still passes (only `check_proof_defer_or_implement` precedes
    `implement_current`);
  - `test_fsm_topology.py::test_autodev_topology` count updated, with a delta comment;
  - real-FSM: a size-review decomposition enqueues children through `enqueue_children`
    with one `decomposed` row.
- **Relocate or rewrite** (don't delete; ENH-3075 AC 8) against a `prepare-issue.yaml`
  loader. The inventories below list the suites.
- **Record mapping**: extend `test_run_record.py` `TestOutcomeMapping.CASES` (:235-250) and
  `test_legacy_class_mapping_via_cli` (:340-348) with the terminal table's classes, and add
  a `prepare-issue` mirror of `TestLoopCallSites` (:494-550).
- **Baselines and gates**: update `loop_interpolation_baseline.json` (move the autodev
  `check_reconcile_needed` entry to `prepare-issue.yaml`, and add entries for unbaselined
  wrapper sites; `recursive-refine.yaml`'s `enqueue_or_skip` / `recheck_scores` entries do
  not move). Re-check `TestMr11MarkerSet` and `TestSubLoopStateTimeoutAudit`.

## Docs

- `docs/guides/LOOPS_REFERENCE.md`:
  - autodev ASCII tree (~:1038-1072, :1184-1186) and the notes/dispatch paragraphs
    (~:1081-1087);
  - the pre-dequeue flow (~:1035-1037);
  - the BUG-2734/BUG-3390 go/no-go, pre-deferral and `recheck_after_size_review`
    paragraphs, and `:579` (`run_size_review`);
  - move the wire/reconcile/score-freshness paragraphs to `### prepare-issue`, and add the
    accepted behavior changes.
- `docs/reference/DEFERRAL_CODES.md` `:24-30`: Source citations name `prepare-issue` states.
- `docs/reference/CLI.md`: `:2272`, `:2318`, `:2334-2335`, `:2687`, `:2884`,
  `:3090-3095`, and the run-record section (`:2403-2438`).
- `docs/reference/API.md`: `:983`, `:4662-4681`.
- `docs/reference/COMMANDS.md`: `:307`, `:311`, `:366`.
- `docs/reference/ISSUE_TEMPLATE.md`: `:916`, `:919`.
- `docs/ARCHITECTURE.md`: `:463`, `:672`, `:676`, `:821`.
- `commands/reconcile-issue.md` (`:83`, `:145`, `:197`, `:368`) and
  `commands/refine-issue.md:1073`.
- `skills/go-no-go/SKILL.md:402` and `skills/audit-loop-run/SKILL.md:271`, re-anchored to
  `prepare-issue`. Then run `ll-adapt --host <gemini|kimi-code|qwen> --apply` and re-check
  the `test_wiring_skills_and_commands.py` line pins (~:750-751, which pin
  `skills/go-no-go/SKILL.md` lines 176 and 276).
- Comments only:
  - `little_loops.cli.issues.show` (:148), `little_loops.cli.issues.check_gate` (module
    docstring), `little_loops.cli.issues.deferred_triage` (:12, :25) and
    `little_loops.issue_manager` (:1230);
  - `loops/rn-refine.yaml` (:419, :500);
  - the `refine-to-ready-issue.yaml` header comments that cite autodev states.

## Acceptance Criteria

- [ ] `autodev.yaml` has no wire, reconcile, design-remedy, pre-deferral, size-review, go/no-go, selector or rescoring states (explicit absence test)
- [ ] Autodev is the only writer of `autodev-queue.txt` (`enqueue_children`, `dequeue_next`, `recover_subloop_children`); the wrapper writes none
- [ ] `prepare-issue` has exactly one rescoring path with per-origin dispatch and the BUG-3588 freshness rules; the retry marker names are unchanged
- [ ] Every `prepare-issue` terminal writes a `writer: prepare-issue` record matching the terminal table, the ledger rows keep today's reason strings, and no stop is ledgered twice
- [ ] Rate-limit exhaustion in any moved slash state halts autodev through `finalize_rate_limited`, including `run_size_review` (no more silent `dequeue_next` drop)
- [ ] The repair-cycle counter increments on every inner entry, including wrapper re-entries; the stagnation backstop test passes
- [ ] A `decomposed` record always has non-empty `child_ids` or a resolved parent; size-review children are enqueued through autodev's `enqueue_children`
- [ ] The go/no-go trigger is the unchanged, deterministic `oversized_atomic` predicate
- [ ] Autodev edges are retargeted: `refine_current.on_success` → `copy_broke_down`, `check_passed.on_yes` → `check_proof_defer_or_implement`; a structural test pins both, plus that no autodev state targets a removed state
- [ ] The wrapper ends only `ready` / `decomposed` in `done` and every `BLOCKED:*` / `DEFERRED:*` / `RETRYABLE_ERROR:*` stop in `failed`; a real-FSM test asserts no stop reaches `route_refine_success`'s `skip_inflight` legs (no double ledger row)
- [ ] `implement_current`'s only predecessor is `check_proof_defer_or_implement`, and `READY` comes only from the wrapper's pass gate plus `select_obligation_pre_implement`
- [ ] The relocated behavioral suites pass. `auto-refine-and-implement` summary counts in a real-FSM run are unchanged except for the "Accepted behavior changes": scores-absent / `on_error` exits add a `refine_failed_infra` row, `run_size_review` rate-limit exhaustion halts, and a cancelled parent is ledgered `cancelled`. Each difference is pinned by its own test
- [ ] Every re-entry edge (selectors and `dispatch_pre_deferral_remedy.on_yes`) targets the wrapper's `count_repair_cycle_refine`, never `run_refine_to_ready` directly
- [ ] `route_inner_success` resets `refine-broke-down` to `0` on every inner success; an inner `DECOMPOSED` with no children and an unresolved parent continues to the wrapper's size-review (BUG-1183 fallback kept); and no wrapper terminal is written while `refine-broke-down` is `1` except `mark_decomposed`, including after a `MISSING` inner record
- [ ] `record_reentry_exhausted` lives in the wrapper and records `BLOCKED:decision_unresolved`
- [ ] Autodev's `check_passed` is the only writer of `autodev-staged.txt`, and `recover_subloop_children` is the only writer of `resolved_by_subloop` rows
- [ ] `size_review_snap`, `check_broke_down` and `mark_scores_absent_infra` are deleted from autodev
- [ ] `prepare-issue.yaml` imports `lib/common.yaml` and carries `capture_reachability_ok: true` with its rationale; `autodev.yaml` drops the flag and still passes `ll-loop validate`
- [ ] Every wrapper terminal that ends in `failed` writes `refine-terminal-class` before its record write, so a failed record write still routes infra stops to `skip_inflight_infra`

## Impact

- **Priority**: P3 - completes the ENH-3601 decomposition and unblocks ENH-3600
- **Effort**: Very Large - ~40 states plus the selectors, a rescoring consolidation and a large test/doc migration; not splittable further because the cluster is strongly connected
- **Risk**: High - rewrites the second-pass routing of the most-used loop; mitigated by ENH-3605's plumbing and ledger rule landing first, per-row terminal tests, and an unchanged go/no-go predicate
- **Breaking Change**: No public interface changes. There is one control-flow change:
  `run_size_review` rate-limit exhaustion now halts the whole autodev queue through
  `finalize_rate_limited` instead of skipping the issue. The other accepted behavior
  changes add ledger rows only. All of them are listed under "Accepted behavior changes".
- **Sequencing (decided 2026-09-26)**: land ENH-3615 first. It lands three parts in
  `autodev.yaml` before the move; none of them depends on the wrapper:
  - the shared rescoring path;
  - the `run_size_review` rate-limit halt (to `finalize_rate_limited`);
  - record writes next to ledger rows, plus the `refine-broke-down` reset in
    `copy_broke_down`.

  After ENH-3615, ENH-3606 relocates the shared rescoring chain
  (`clear_scores` / `rerun_confidence` / `check_scores_present` / `route_after_rescore`)
  instead of the three triplets. It retargets `run_size_review`'s halt to
  `mark_rate_limited`, and it moves the record writes as they are.
  **The single-writer rules for staging and `resolved_by_subloop` stay in ENH-3606.**
  Today `recheck_scores`, `recheck_after_size_review`, `regate_after_atomic_remediation`
  and `reopen_waived` stage and then reach `check_proof_defer_or_implement` through
  `select_obligation_pre_implement`, without passing `check_passed`. Removing their
  staging appends is only safe once autodev's `check_passed` runs after the wrapper.

## Integration Map

_`autodev.yaml` anchors in "Files to modify" were refreshed 2026-09-26 against
post-ENH-3611 `autodev.yaml` (from the Verification Notes). ENH-3615 lands first and
shifts them again, so treat them as approximate. Test-file anchors below are older.
Research from the original ENH-3605 (wire/refine, reconcile/design) was merged here on
2026-09-26._

### Codebase Research Findings

- **Files to modify**:
  - `scripts/little_loops/loops/autodev.yaml`, boundary states that stay:
    - `refine_current` ~:472, `route_refine_outcome` ~:514, `ledger_child_stop` ~:547;
    - `count_repair_cycle_refine` ~:641 (moves), `route_refine_success` ~:671,
      `check_passed` ~:713, `check_proof_defer_or_implement` ~:988.
  - Selectors: `select_obligation_post_refine` ~:737, `select_obligation_pre_implement`
    ~:824, `select_obligation_post_size_review` ~:908.
  - Wire/reconcile/design:
    - `run_wire` ~:1020, `run_refine` ~:1046, `check_missing_artifacts` ~:1867;
    - `check_reconcile_needed` ~:2004, `check_atomic_design_remedy` ~:2361;
    - `refine_for_design` ~:2473, `reconcile_current` ~:2515, `dispatch_design_remedy`
      ~:2901.
  - Size-review/go-no-go/pre-deferral:
    - `mark_scores_absent_infra` ~:1563, `detect_children` ~:1647, `size_review_snap`
      ~:1724, `check_broke_down` ~:1737;
    - `recheck_scores` ~:1831, `run_size_review` ~:1878, `enqueue_or_skip` ~:1920;
    - `regate_after_atomic_remediation` ~:2267, `run_go_no_go` ~:2420, `reopen_waived`
      ~:2447, `recheck_after_size_review` ~:2632;
    - `check_pre_deferral_remedy` ~:2880, `dispatch_pre_deferral_remedy` ~:2925.
  - `scripts/little_loops/loops/prepare-issue.yaml` (created by ENH-3605; 7 states today).
- **Rescoring triplets**: five existed (`decide`, `wire`, `spike`, `atomic`, `reconcile`);
  ENH-3610/3611 remove `decide` and `spike`. The remaining three differ only in entry point,
  successor and retry-marker name, and are cleared by `dequeue_next`. `refine_for_design`
  and `count_repair_cycle_reconcile` both feed `clear_scores_before_reconcile`. All three
  `check_scores_present_*` / `clear_scores_before_*` route failures to
  `mark_scores_absent_infra`, which writes only `autodev-scores-absent.txt` (no skipped
  row). It is deleted by this issue (see States that stay).
- **Repair-cycle counter**: `count_repair_cycle_{refine,wire,size_review,refine_for_design,reconcile}`
  all write `autodev-repair-cycle-count.txt`. `recheck_after_size_review` reads it for the
  stagnation backstop (count ≥ 2 with confidence not above `autodev-pre-readiness.txt`).
  `dequeue_next` resets it.
- **Size-review sentinels**: `autodev-pre-ids.txt` / `-post-ids.txt` / `-diff-ids.txt` /
  `-new-children.txt` are written by `size_review_snap`, `detect_children`, `enqueue_or_skip`
  and `recover_subloop_children`. `autodev-size-review-ran-this-pass` is set by
  `count_repair_cycle_size_review`, read by `check_size_review_ran_this_pass`, and cleared by
  `dequeue_next`.
- **Design-remedy state**:
  - `autodev-atomic-design-remedy-pending` is written by `regate_after_atomic_remediation`
    and consumed by `check_atomic_design_remedy`;
  - `autodev-design-remedy-attempted-<ID>` has no further notes;
  - `autodev-pre-deferral-remedy.txt` / `-fired` are written by `recheck_after_size_review`
    and cleared by `dequeue_next`;
  - `autodev-go-no-go-attempted-<ID>` is per-issue and never cleared (one-shot).
  - `reopen_waived` re-arms `autodev-inflight`.
- **Coupling to the queue file**:
  - `enqueue_or_skip`'s queue branch duplicates `enqueue_children`: both merge
    `autodev-new-children.txt` into `autodev-queue.txt`, append `ID  decomposed` to
    `autodev-skipped.txt`, run `ll-issues finalize-decomposition --children-file`, and clear
    `autodev-inflight`.
  - `enqueue_or_skip.on_no` → `check_parent_resolved_post_size_review`, and
    `check_broke_down.on_yes` → `check_parent_resolved`.
- **Ledger writes in moved states**:
  - `recheck_after_size_review` writes `resolved_by_subloop`, `design_gate_failed`,
    `decision_unresolved`, `readiness_stagnated` and `low_readiness`;
  - `regate_after_atomic_remediation` writes `resolved_by_subloop`, `design_gate_failed`
    and `oversized_atomic`;
  - `reopen_waived` removes `oversized_atomic` with `grep -vxF`;
  - `enqueue_or_skip` writes `decomposed`.
  - `finalize_done` (~:3066-3129) parses `autodev-skipped.txt` by reason substring;
    `auto-refine-and-implement` builds `SKILL_BREAKDOWN` from the reason column
    (~:1118-1133).
- **Terminal mapping constraint**: `outcome_from_legacy_class` is first-match-wins
  (`cancelled` → `broke_down` → `infra` → `decision_unresolved`/`proposal_unsound`/`quality`
  → `spike_inconclusive`/`gate_unmet` → thresholds). The run-record CLI accepts only the six
  `LEGACY_CLASSES`, so `gate_unmet` loses the specific reason in `legacy_class`. The ledger
  row and the `deferred_reason` frontmatter carry it.
- **Rate-limit**: `run_size_review` uses `on_rate_limit_exhausted: dequeue_next` (to become a
  halt; see Rate limits); the other
  moved slash states go to `finalize_rate_limited` (`run_go_no_go` is pinned at
  `test_builtin_loops.py:8254-8258`). The `subloop_rate_limit_diagnostic` fragment
  (`lib/common.yaml:446`) needs `operation` through `with:` and `${context.issue_id}`.
  `rn-decompose.yaml`'s `run_size_review` → `rate_limit_diagnostic` is the existing
  sub-loop-side shape.
- **Inbound cross-boundary edges (pre-ENH-3611 names)**:
  - `check_spike_needed` → `check_missing_artifacts` becomes ENH-3610's
    `select_obligation_post_refine` `_` → `check_missing_artifacts`;
  - `check_spike_needed_before_skip` → `check_reconcile_needed` becomes ENH-3611's
    `select_obligation_post_size_review`;
  - `check_passed.on_no` → selector;
  - `check_parent_resolved.on_no` → `recheck_scores`;
  - `check_broke_down.on_no` → `enqueue_or_skip`.

### Conventions in Force

- State-move tests: extracted-loop suites live in their own file and assert states through
  `data["states"][name]` (`test_rn_decompose.py`). Source loops assert absence with a
  `REMOVED_INLINE_STATES` parametrized test (`TestIssueRefinementSubLoop`,
  ~`test_builtin_loops.py:1323`).
- Baseline JSON entries are keyed `(file, state, var, class)` and must move in the same
  commit as the state (`TestInterpSweepBaseline::test_completeness_guard`).
- `test_fsm_topology.py::TestAutodevSmoke::test_autodev_topology` (~:233-261) pins
  autodev's state count, with a commented delta per issue.
- Mirror gates after skills/README edits: `test_adapters.py` (~:1176-1203) and
  `test_packaging_duplicate_files.py` (~:22). The docs-audience gate forbids
  `scripts/tests/` and `scripts/little_loops/` citations in `docs/guides`,
  `docs/reference`, `skills/` and `commands/`.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/auto-refine-and-implement.yaml`: reads `autodev-queue.txt`
  (~:477/:1077), `autodev-inflight` (~:1058) and the ledgers (~:1088-1144, `SKILL_BREAKDOWN`
  ~:1118-1133). Its counts must not change. `scan-and-implement.yaml:79` also calls
  `loop: autodev`.
- `scripts/little_loops/loops/recursive-refine.yaml`: has its own `check_missing_artifacts`
  (~:594-602), `size_review_snap`, `check_broke_down`, `recheck_scores`, `enqueue_or_skip`
  and `detect_children`. The names collide only; do not touch them. `rn-decompose.yaml` has
  its own `run_size_review`.
- `little_loops.cli.issues.run_record` / `little_loops.run_record`: no change beyond
  ENH-3605's `forward`. `_read_broke_down` reads the shared `refine-broke-down`.
- `little_loops.cli.issues.check_readiness` (`--honor-waiver`, `outcome_gate_waived`),
  `show` (:147-158, :296), `deferred_triage` (`_REASON_RANK`), `set_status` (`DeferReason`)
  and `issue_lifecycle` (`OVERSIZED_ATOMIC`) consume `deferred_reason`; no code change.

### Tests

- `scripts/tests/test_builtin_loops.py::TestAutodevLoop`:
  - `test_required_states_exist` (~:6659), `test_old_states_removed` (~:6705) and
    `test_context_passthrough_on_refine_current` (~:8588);
  - the second-pass cluster (~:8095-8920): `test_recheck_after_size_review_*`,
    `test_check_guard2_*`, `test_go_no_go_escalation_chain_shape`,
    `test_check_go_no_go_eligible_one_shot_and_reason_scoped`,
    `test_reopen_waived_reopens_stages_and_rearms_inflight`, `test_enqueue_or_skip_*`,
    `test_pre_deferral_remedy_*`, `test_recheck_scores_on_*` (~:8890-8920);
  - wire/reconcile/design pins: `check_missing_artifacts` (~:9183-9209), `run_wire` /
    `run_refine` (~:9214-9238, :9519-9531), `rerun_confidence_after_wire` (~:9534-9590),
    `check_reconcile_needed` (~:8328, :8636-8660, :8839-8872, :9121-9165),
    `reconcile_current` / `count_repair_cycle_reconcile` (~:9145-9166),
    `dispatch_design_remedy` (~:8771-8793), `check_atomic_design_remedy` (~:8229);
  - `test_snap_and_size_review_*` (~:9437-9473; dropped by ENH-3611);
  - queue-adjacent: `test_enqueue_children_*` (~:8443-8716),
    `test_check_broke_down_on_no_routes_to_enqueue_or_skip` (:8510),
    `test_dequeue_next_clears_pre_deferral_remedy_files` (:8832),
    `test_dequeue_next_resets_contradiction_budget` (:8878);
  - `TestAutodevRnImplementDeferralParity` (~:9736; `AUTODEV_NOT_READY_STATES`).
- `scripts/tests/test_autodev_decision_gate.py`:
  - `TestReconcilePlateauStructural` / `Routing` (~:532-695),
    `TestDesignGateRefineRemedy` (~:698-770), `TestAtomicDesignRemedyRouting` (~:772-818),
    `TestGuard2VerdictBypass` (~:820);
  - `TestCheckDecisionBeforeSizeReviewStructural` (~:334) / `Routing` (:903), as they
    survive ENH-3610.
  - `_load_autodev_yaml` needs a `prepare-issue.yaml` twin.
- `scripts/tests/test_autodev_loop.py`: `TestCheckGuard2VerdictPattern` (:106),
  `TestCheckGuard2ScoreFallback` (:150), the `check_reconcile_needed` tests (~:190-300,
  :923-961), `TestRepairCycleCounterStates` (~:450-486), `TestRecheckAfterSizeReview*`
  (:497/:571/:715/:807), `TestPreDeferralRemedyContradictionExemption` (:850),
  `TestRegateAfterAtomicRemediationDesignGateBranch` (:917),
  `TestRecheckScoresDesignGateEndToEnd` (:1056), `TestDesignGateStep0Detection`,
  `TestDequeueNextPreReadinessSnapshot`, `TestCheckGateAtDequeueMarkerLiterals`.
- `scripts/tests/test_autodev_scores_freshness.py`:
  - `_PAIRS` (:28-31), with the `wire`/`reconcile`/`atomic` cases rewritten to the shared
    path;
  - `test_repair_predecessors_target_clear_states`, `test_readiness_readers_route_exit_3`,
    `test_check_passed_still_reaches_detect_children_on_error`;
  - `TestInlineGateAbsence` (:218-219), `test_dequeue_next_clears_retry_markers`;
  - the topology pins at :95-96.
- `scripts/tests/test_spike_verdict_routing.py`: `test_autodev_routing_table` (~:89-106),
  `test_dispatch_pre_deferral_remedy_*` (~:147) and the loop over
  `("autodev.yaml", "refine-to-ready-issue.yaml")` (~:136).
- `scripts/tests/test_ll_issues_check_gate.py` (~:268 docstring, ~:376),
  `test_go_no_go_skill.py:42` docstring, `test_recursive_finalize.py:133-140`,
  `test_auto_refine_closure_accounting.py`, and `TestAutoRefineAndImplementLoop` (~:4761,
  :4998-5620). These pin the queue/ledger files that stay autodev-owned.
- **Unaffected (name collision)**: `test_loops_recursive_refine.py`,
  `TestRecursiveRefineLoop` (~:9780-10170), `test_issue_refinement_broke_down.py`,
  `test_rn_refine.py`, `test_rn_implement.py`.

### Configuration

- No schema, config or manifest change. `run_record.py` already accepts the `prepare-issue`
  writer and the six `LEGACY_CLASSES`, and the `pyproject.toml` glob covers the YAML.

## Implementation Steps

0. Confirm ENH-3615 is `done`. Its shared rescoring chain (plus
   `mark_rescore_origin_atomic` and the inline origin writes in the `count_repair_cycle_*`
   states) replaces the three triplets in the move set, and its record writes move
   unchanged. Its `refine-broke-down` reset lives in `copy_broke_down`, which stays in
   autodev. Once the ladder runs inside the wrapper, that reset no longer protects it:
   the wrapper's own reset in `route_inner_success` (see "Broke-down flag rule") takes
   over. Keep the `copy_broke_down` reset anyway; it is harmless after the wrapper returns.
1. Re-run the boundary edge computation (Scope, "Boundary edge table") and confirm it still
   matches; update the table if `autodev.yaml` has changed.
2. Pin the terminal table (the `TestOutcomeMapping` and CLI rows) and the `run_size_review`
   halt (`on_rate_limit_exhausted: mark_rate_limited`).
3. Build the wrapper ladder: `route_inner_success`, `detect_ladder_children`, the pass gate,
   the moved states with `${context.input}` rewrites, the shared rescoring path, the wrapper
   terminals (`mark_ready`, `mark_decomposed`, `mark_rate_limited`, `mark_scores_absent`,
   `mark_ladder_error`), record writes next to each ledger row, the broke-down flag rule,
   and `count_repair_cycle_refine` as the pre-state of the inner loop. Raise `max_steps`.
4. In the same commit: delete the moved states from autodev, apply the "Boundary edge
   retargets" (including `refine_current.on_success` and `check_passed.on_yes`), set
   `check_passed.on_no` / `on_cannot_judge` → `skip_inflight`, delete `size_review_snap`,
   `check_broke_down` and `mark_scores_absent_infra`, and retarget `detect_children.on_no`
   and `check_parent_resolved.on_no`.
5. Relocate and rewrite the suites; add the absence, queue-writer, terminal-table, rescoring
   dispatch, counter and DECOMPOSED-guarantee tests; update the topology count and the
   baseline JSON.
6. Update the docs and comments; re-anchor the skills; run `ll-adapt` and re-check the line
   pins.

## Program Design

### Types

- `PreparationOutcome`: six-value Literal in `little_loops.run_record` (reused; the moved
  terminals use `ready`, `deferred`, `blocked`, `decomposed` and `retryable_error`)

### Signatures

- `write_run_record(run_dir: Path, record: RunRecord) -> Path` — reached through `ll-issues run-record write ... --writer prepare-issue` at each wrapper terminal
- `select_next_obligation(config: BRConfig, issue_id: str, *, skip: Iterable[Obligation] = (), ...) -> ObligationResult | None` — reached through the moved selector states (`ll-issues next-obligation`)

### Call Path

`autodev.yaml:refine_current` -> `prepare-issue.yaml:count_repair_cycle_refine` -> `prepare-issue.yaml:run_refine_to_ready` -> `prepare-issue.yaml:route_inner_success` -> `prepare-issue.yaml:check_passed` -> `prepare-issue.yaml:select_obligation_post_refine` -> `prepare-issue.yaml:check_missing_artifacts`

`prepare-issue.yaml:run_size_review` -> `prepare-issue.yaml:recheck_after_size_review` -> `write_run_record` -> `autodev.yaml:route_refine_outcome` -> `autodev.yaml:ledger_child_stop`

## Status

**Open** | Created: 2026-09-26 | Priority: P3

## Verification Notes

_Added by `/ll:verify-issues` on 2026-09-26_

Verdict at time of check: **NEEDS_UPDATE** (findings below are recorded, not edited into the sections above; `Remaining:` lists what the implementer must fold in)

Checks: all 40+ named states exist in `autodev.yaml` (3294 lines); no decisions rules apply; `ll-verify-evidence` clean. Graph: provider=`codegraph` freshness=`stale` (not used to originate any verdict).

- **Dependencies satisfied**: ENH-3605 and ENH-3611 are both `done`. `prepare-issue.yaml` and `test_prepare_issue.py` now exist (commit 80449dc2f), so the Confidence Check "Gaps to Address" note is out of date. The wrapper currently has only `clear_record`, `run_refine_to_ready`, `forward_done`, `forward_stop`, `mark_inner_error`, `done`, `failed`. `blocked_by` in frontmatter can drop ENH-3605/ENH-3611.
- **Anchors refreshed (post-ENH-3611)**: `refine_current` :472, `route_refine_outcome` :514, `ledger_child_stop` :547, `count_repair_cycle_refine` :641, `route_refine_success` :671, `check_passed` :713, `select_obligation_post_refine` :737, `select_obligation_pre_implement` :824, `select_obligation_post_size_review` :908, `check_proof_defer_or_implement` :988, `run_wire` :1020, `run_refine` :1046, `mark_scores_absent_infra` :1563, `detect_children` :1647, `size_review_snap` :1724, `check_broke_down` :1737, `recheck_scores` :1831, `check_missing_artifacts` :1867, `run_size_review` :1878, `enqueue_or_skip` :1920, `check_reconcile_needed` :2004, `regate_after_atomic_remediation` :2267, `check_atomic_design_remedy` :2361, `run_go_no_go` :2420, `reopen_waived` :2447, `refine_for_design` :2473, `reconcile_current` :2515, `recheck_after_size_review` :2632, `check_pre_deferral_remedy` :2880, `dispatch_design_remedy` :2901, `dispatch_pre_deferral_remedy` :2925. `snap_and_size_review` is gone (ENH-3611); `detect_children.on_no` → `size_review_snap` is still live.
- **Boundary edges not in the Scope section** (part of the unperformed edge-table step):
  - `refine_current.on_success` → `count_repair_cycle_refine` → `copy_broke_down` → `route_refine_success` (:671). Since `count_repair_cycle_refine` moves, `refine_current.on_success` must retarget to `copy_broke_down`.
  - `route_refine_success` (ENH-3609) routes `READY`/`BLOCKED`/`MISSING`/`_` → `check_passed`, `DECOMPOSED` → `detect_children`, and every suffixed `BLOCKED:*`/`DEFERRED:*`/`RETRYABLE_ERROR:*` → `skip_inflight` (treated as impossible on the success path). The terminal table's `decomposed` and `ready` rows must therefore end in the wrapper's `done` terminal, and every stop row in `failed` (→ `route_refine_outcome` → `ledger_child_stop`); a stop ending in `done` would be double-ledgered by `skip_inflight`.
  - `check_passed.on_yes` currently targets `select_obligation_pre_implement`, which moves. Autodev's `check_passed.on_yes` must retarget to `check_proof_defer_or_implement`. The issue says `check_passed` both moves (wrapper-local) and stays; it means two copies, so state that explicitly.
  - `route_refine_outcome` maps `DECOMPOSED` → `skip_inflight` (:541); the wrapper `decomposed` must not reach it via the failed terminal.
- **Proposal check (B6)**: the mechanism stands. No exception-handler or fixture conflicts found.

Folded into Scope ("Boundary edge retargets"), Acceptance Criteria and Implementation Step 4 in a follow-up edit the same day. The full edge table was later regenerated in Scope, so Implementation Step 1 is now a re-run-if-changed check, not an outstanding item.

### Re-verification (2026-09-26, later pass)

Verdict at time of check: **NEEDS_UPDATE** (the stale sentence above was corrected in the same pass; the issue as it now reads is up to date — this is a record, not an action item)

Re-parsed `autodev.yaml` (90 states) and `prepare-issue.yaml` (7 states, `max_steps: 20`) against the Scope claims; `ll-verify-evidence` clean; no decisions rules apply. Graph: provider=`codegraph` freshness=`stale` (not used for any verdict).

- Confirmed against current edges: `refine_current.on_success` → `count_repair_cycle_refine` → `copy_broke_down`; `check_passed` `on_yes` → `select_obligation_pre_implement`, `on_no`/`on_cannot_judge` → `select_obligation_post_refine`, `on_error` → `detect_children`; `detect_children.on_no`/`on_error` → `size_review_snap` → `check_broke_down`; `check_parent_resolved.on_no`/`on_error` → `recheck_scores`; `check_broke_down.on_no` → `enqueue_or_skip`; `dispatch_pre_deferral_remedy.on_yes` → `refine_current`; `run_size_review.on_rate_limit_exhausted` → `dequeue_next`; `mark_scores_absent_infra` → `dequeue_next`. All match the boundary edge table's "Today" column.
- `route_refine_success` and `route_refine_outcome` route as the Scope section states (`CANCELLED` → `skip_cancelled`; suffixed stops → `skip_inflight` / `ledger_child_stop`).
- Proposal check (B6): mechanism stands; no new findings.

### Re-verification (2026-09-26, post-ENH-3615)

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

Re-parsed `autodev.yaml` (86 states) at HEAD `74747fb1e`. `ll-verify-evidence` clean; no decisions rules apply. Graph: provider=`codegraph` freshness=`stale` (not used for any verdict).

- **Blocker resolved**: ENH-3615 is `done` (landed in `74747fb1e`). Removed `blocked_by: ENH-3615` from frontmatter. The Confidence Check Notes' "Unresolved blocker" gap is out of date; a re-score is due.
- **Edge table rescoring rows corrected**: the shared chain is live (`clear_scores` → `rerun_confidence` → `check_scores_present` → `route_after_rescore`, plus `mark_rescore_origin_atomic`). The per-origin `check_scores_present_*`, `clear_scores_before_*` and `rerun_confidence_after_*` names cited in two edge-table rows no longer exist; rows now name the shared states.
- **Confirmed at HEAD**: `run_size_review.on_rate_limit_exhausted` → `finalize_rate_limited` (ENH-3615 halt landed); `copy_broke_down` resets `refine-broke-down`; every other "Today" edge in the table still matches (`refine_current.on_success`, `check_passed`, `detect_children`, `check_parent_resolved`, `check_broke_down`, `size_review_snap`, `dispatch_pre_deferral_remedy.on_yes`, `mark_scores_absent_infra`).
- Integration Map line anchors remain approximate (ENH-3615 shifted them by roughly 10-40 lines).
- Proposal check (B6): mechanism stands; no new findings.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-26_

_Re-scored 2026-09-26 after the sequencing decision made ENH-3615 a hard `blocked_by` edge._

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 46/100 → LOW

### Gaps to Address
- **Unresolved blocker**: `blocked_by: ENH-3615` is `open` (needs `done`/`cancelled`). Land ENH-3615 first, per the Impact sequencing decision, then re-run. Criterion 5 scores 0; the other four readiness criteria score 20 each.

### Concerns
- ~~The sequencing option under Impact is still open.~~ Decided 2026-09-26: ENH-3615 lands first.
- ENH-3615 shifts the `autodev.yaml` line anchors in the Integration Map, so they are approximate; re-run the boundary edge computation before editing.

### Outcome Risk Factors
- Deep per-site complexity: rewires the strongly connected second-pass cluster, rescoring consolidation and terminal routing.
- Broad enumeration across ~40 states plus a large test/doc migration (Breadth 0).
- Broad change surface: autodev consumers (`auto-refine-and-implement`, `scan-and-implement`, run-record, ledger readers) must keep counts unchanged.
- Mitigation: adopt the behavior-preserving prep issue from the sequencing option to shrink the final move.

## Design Review Notes

_Added 2026-09-26 (manual review against post-ENH-3611 `autodev.yaml` and `little_loops.run_record`)._

Folded into Scope, Terminal table, Mechanics, Tests, Acceptance Criteria, Implementation
Steps and Impact:

- Boundary edge table computed and recorded; it adds the size-review entry crossing
  (`check_missing_artifacts` → `detect_children` … `check_parent_resolved` →
  `recheck_scores`) and `dispatch_pre_deferral_remedy.on_yes` as a re-entry edge.
- Counter contradiction fixed: re-entries target `count_repair_cycle_refine`, not
  `run_refine_to_ready`.
- New "Inner-loop success routing and the broke-down flag": `route_inner_success`,
  `detect_ladder_children` (keeps the BUG-1183 fallback), and the `refine-broke-down`
  priority trap in `outcome_from_legacy_class`.
- `record_reentry_exhausted` added to the move set and terminal table.
- Record writes sit next to ledger rows; wrapper stops bypass `forward_stop`;
  `mark_ladder_error` keeps an existing stop record; `reopen_waived` clears its record.
- Single writers for `autodev-staged.txt` and `resolved_by_subloop` rows.
- Decided: delete `size_review_snap`, `check_broke_down`, `mark_scores_absent_infra`.
- `max_steps`, `--*-threshold` flags on the ready write, `autodev-rescore-origin-<ID>`
  naming, capture-name collisions and `run_go_no_go`'s pruning profile added to Mechanics.
- Sequencing decided 2026-09-26: ENH-3615 lands first (see Impact).

### Second review (2026-09-26)

Folded into Terminal table, Mechanics, Tests, Acceptance Criteria, Impact and Integration
Map:

- `prepare-issue.yaml` needs `import: [lib/common.yaml]`: the moved states use its
  fragments.
- `capture_reachability_ok: true` moves from autodev to the wrapper along with its only
  reason, `check_guard2_verdict`.
- Wrapper terminals that end in `failed` write the `refine-terminal-class` sentinel, so the
  MISSING-record fallback classifies correctly.
- The summary-count AC now excepts the accepted behavior changes.
- The Breaking Change line names the `run_size_review` halt as a control-flow change.
- The Integration Map `autodev.yaml` anchors were refreshed from the Verification Notes.
- Checked with no change needed:
  - `mark_rate_limited`'s write yields `RETRYABLE_ERROR:rate_limited`;
  - `run-record write` honors the outcome waiver;
  - the inner loop clears its own record and `refine-broke-down` at `resolve_issue`;
  - no capture-name collisions.

## Session Log
- `/ll:verify-issues` - 2026-09-26T22:05:24 - `c4864ff1-acf7-4101-a722-b28e5ccfc698.jsonl`
- `/ll:confidence-check` - 2026-09-26T21:19:22 - `80a78edd-363d-4d79-9451-fe1325611d39.jsonl`
- `/ll:confidence-check` - 2026-09-26T20:34:15 - `dcc4151f-8515-4923-9336-bb585d1a7e59.jsonl`
- `/ll:confidence-check` - 2026-09-26T20:20:48 - `6a41b2bc-b016-4ac8-ae48-08305b05403a.jsonl`
- `/ll:verify-issues` - 2026-09-26T20:10:06 - `3c9e6ec9-3d9b-4e64-8ad3-568702407b0a.jsonl`
- `/ll:verify-issues` - 2026-09-26T19:59:52 - `b7feb4d7-6b74-47e8-9464-2371879b3a6f.jsonl`
- `/ll:confidence-check` - 2026-09-26T17:56:40 - `1617bd47-448f-4338-8379-3ae73f71f9bc.jsonl`
- `/ll:verify-issues` - 2026-09-26T17:51:04 - `88c2d513-b5ef-46f0-9f72-8998adaef5bb.jsonl`
- `/ll:wire-issue` - 2026-09-26T03:36:28 - `e6ad8ea2-14d6-441f-a607-435314c2d056.jsonl`
- `/ll:refine-issue` - 2026-09-26T03:22:25 - `7612ef86-47f8-4d5d-aa01-e50211538dc3.jsonl`
- `/ll:format-issue` - 2026-09-26T03:07:12 - `34887897-5e19-4ee2-b656-5f0a00c15f02.jsonl`
