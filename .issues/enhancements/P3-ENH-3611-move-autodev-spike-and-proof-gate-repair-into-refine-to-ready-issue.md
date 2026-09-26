---
id: ENH-3611
type: ENH
title: Move autodev spike and proof-gate repair into refine-to-ready-issue
priority: P3
status: open
discovered_by: issue-size-review
discovered_date: '2026-09-26'
captured_at: '2026-09-26T03:47:27Z'
parent: EPIC-3565
decision_needed: false
blocked_by:
- ENH-3610
blocks:
- ENH-3605
- ENH-3600
relates_to:
- ENH-3608
- ENH-3599
- ENH-3575
- ENH-3602
- BUG-3603
- BUG-3593
---

# ENH-3611: Move autodev spike and proof-gate repair into refine-to-ready-issue

## Summary

Third of three children of ENH-3608. Move autodev's spike and proof-gate repair into
`refine-to-ready-issue` and remove the remaining 22 autodev spike/decision states. The child
gains a proof gate before `done`, so an open `structured_proof` gate on a high-scoring issue is
still spiked (ENH-3575), now inside the child. Autodev's selectors add `PROOF` re-entry, and
`check_proof_defer_or_implement` becomes the only proof stage before `implement_current`.

## Current Behavior

- Autodev duplicates the child's spike path: `check_spike_needed`, `run_spike`,
  `count_repair_cycle_spike`, `route_spike_verdict`, `check_spike_budget`,
  `record_spike_inconclusive`, `mark_spike_no_verdict_infra`, the `spike` rescoring triplet
  (`rerun_confidence_after_spike`, `clear_scores_before_spike`, `check_scores_present_spike`)
  and `check_spike_needed_before_skip`. Its refuted-spike leg (`check_spike_budget`) keeps the
  post-decision chain alive after ENH-3610: `resolve_decision`, `mark_decide_ran`,
  the `decide` rescoring triplet, `recheck_after_decide`, `check_rearmed_spike_after_decide`,
  `check_decide_rate_limited`, `record_decision_unresolved` and `snap_and_size_review` (which is
  entered only from those states).
- `check_proof_gate_before_implement` is a first proof stage. A `structured_proof` gate with
  spike budget left → `PROOF_SPIKE` → autodev's `run_spike`. Otherwise it goes to
  `check_proof_defer_or_implement`.
- The child never consults `ll-issues check-gate`. Its `check_spike_needed` fires only on
  `spike_needed: true` and only in the low-outcome band. A high-scoring issue with an open
  `structured_proof` gate reaches `done` without a spike.
- `next-obligation`'s `PROOF` differs from the child's predicate. It also reports `absent` for
  `spike_attempted` without `spike_completed`, and it folds in a `structured_proof` gate
  verdict (documented on `Obligation`). A selector that re-enters the child on `PROOF` could
  therefore cycle without a spike ever running.
- Autodev reads/writes `autodev-pre-spike-readiness.txt` (`dequeue_next`, the spike states,
  `check_reconcile_needed`, `dispatch_pre_deferral_remedy`), `autodev-spike-no-verdict.txt`
  (`init`, `mark_spike_no_verdict_infra`, `finalize_done`), `autodev-decide-ran`
  (`dequeue_next`, `mark_decide_ran`) and writes `spike-runs-<ID>`.

## Expected Behavior

- **Child proof gate.** A new `check_proof_before_done` sits between
  `check_decision_before_done`'s no-flag branch and `write_done_record`. It runs
  `ll-issues check-gate <ID>`. On `structured_proof` with `spike_attempted` unset and
  `spike-runs-<ID>` < 2, it increments the counter and routes to `run_spike` (the existing
  `route_spike_verdict` → `PROVEN` → `confidence_check` chain re-scores and returns through
  `check_outcome`). Every other verdict, and a helper error, → `write_done_record`. This gate is
  fail-open because autodev's `check_proof_defer_or_implement` stays fail-closed downstream
  (BUG-3603).
- **Selectors gain `PROOF`.** Each selector routes `PROOF:absent`, `PROOF:stale` and
  `PROOF:refuted` to `refine_current`, capped by `autodev-reentry-PROOF-<ID>` exactly like
  `DECISION`. When the cap is hit, the selector passes `--skip PROOF` to `next-obligation` and
  falls through to its not-needed successor. That successor is never implementation without the
  proof gate, because `check_proof_defer_or_implement` still defers an open gate. A third
  selector covers the post-size-review site. Final layout:

  | Selector | Not-needed (`_`) successor | `_error` |
  |---|---|---|
  | `select_obligation_post_refine` | `check_missing_artifacts` (was `check_spike_needed`) | `detect_children` |
  | `select_obligation_pre_implement` | `check_proof_defer_or_implement` (was `check_proof_gate_before_implement`) | `check_proof_defer_or_implement` |
  | `select_obligation_post_size_review` (new) | `check_reconcile_needed` | `recheck_after_size_review` |

- **Retargets** (the 22 removed states' inbound edges from surviving states):

  | Surviving state | Edge | Removed target | New target |
  |---|---|---|---|
  | `check_passed` | `on_yes` | `check_proof_gate_before_implement` | `check_proof_defer_or_implement` |
  | `check_parent_resolved_post_size_review` | `on_no`, `on_error` | `check_spike_needed_before_skip` | `select_obligation_post_size_review` |
  | `dispatch_pre_deferral_remedy` | `on_yes` | `run_spike` | `refine_current` |
  | `select_obligation_post_refine` | `_` | `check_spike_needed` | `check_missing_artifacts` |
  | `select_obligation_pre_implement` | `_`, `_error` | `check_proof_gate_before_implement` | `check_proof_defer_or_implement` |

- **Proof gate.** `check_proof_defer_or_implement` is the only predecessor of
  `implement_current` and the only proof stage. The only route into implementation is
  `route_refine_success` (`READY`) → `check_passed` or a selector → `check_proof_defer_or_implement`.
- **Markers.** Autodev never writes `spike-runs-<ID>`. Its surviving read-only consumers
  (`recheck_after_size_review`, `dispatch_pre_deferral_remedy`) keep reading it as the budget
  signal the child spends. Neither `resolve_issue` nor autodev resets it
  (`test_resolve_issue_does_not_reset_spike_counter`). `autodev-pre-spike-readiness.txt` is
  gone: `check_reconcile_needed` uses the per-issue pre-refine snapshot
  `autodev-pre-readiness.txt` that `dequeue_next` already writes (FEAT-2751). Nothing writes
  `autodev-spike-no-verdict.txt` any more (the child's no-verdict surfaces as
  `RETRYABLE_ERROR:infra` → `refine_failed_infra`), so it leaves `init` and `finalize_done`.
  `dequeue_next` drops its `autodev-decide-ran` clear. The child-written
  `autodev-decision-unresolved.txt`, `autodev-spike-inconclusive.txt`,
  `autodev-proposal-unsound.txt` and `autodev-decide-ran` stay until ENH-3600.
- **Stagnation.** Deleting `count_repair_cycle_spike` (FEAT-2751) is covered by re-entry. Every
  re-entry passes `refine_current` → `count_repair_cycle_refine`.

### Behavior Parity

| Removed autodev state | Behavior | Disposition | Where it lives now |
|---|---|---|---|
| `check_proof_gate_before_implement` (`PROOF_SPIKE`) | Spike a high-scoring issue whose `structured_proof` gate is open and budget remains | MOVED | Child: `check_proof_before_done` |
| `check_proof_gate_before_implement` (`PROOF_DEFER` / `PROOF_INFRA`) | Defer an open gate; defer on helper failure | PRESERVED | `check_proof_defer_or_implement` (unchanged, fail-closed) |
| `check_spike_needed` / `run_spike` / `route_spike_verdict` | Spike on `spike_needed`, four-way verdict routing (BUG-3593) | MOVED | Child's same-named states (already present) |
| `run_spike` rate-limit handling | Wait up to 14400s, halt the run on exhaustion | MOVED | Child `run_spike` (ENH-3607) → `RETRYABLE_ERROR:rate_limited` → `finalize_rate_limited` |
| `check_spike_budget` → `resolve_decision` chain | Refuted spike → decide once, second refutation → `decision_unresolved` | MOVED | Child: `check_spike_budget` → `resolve_decision_pre_breakdown` / `record_decision_unresolved`; autodev sees `BLOCKED:decision_unresolved` → `ledger_child_stop` |
| `record_spike_inconclusive` / `mark_spike_no_verdict_infra` | Defer inconclusive; infra-skip no verdict | MOVED | Child's same-named states → `DEFERRED:spike_inconclusive` / `RETRYABLE_ERROR:infra` |
| `spike` / `decide` rescoring triplets + `recheck_after_decide` | Fresh scores after a spike or decision (BUG-3588) | MOVED | Child: `route_spike_verdict` `PROVEN` → `confidence_check` → `mark_evidence_absent_infra` on missing scores |
| `check_rearmed_spike_after_decide` | Re-spike once after a decision re-arms the spike | MOVED | Child: `check_spike_needed` with the shared `spike-runs-<ID>` budget (< 2) |
| `count_repair_cycle_spike` | Count a spike toward the FEAT-2751 stagnation backstop | PRESERVED | Every re-entry passes `count_repair_cycle_refine` |
| `check_spike_needed_before_skip` | Last spike chance before the post-size-review skip | PRESERVED | `select_obligation_post_size_review` `PROOF:*` → child re-entry |
| `check_decide_rate_limited` | Halt the run on decide-oracle 429 exhaustion | MOVED | Child `check_decide_rate_limited` → `mark_rate_limit_infra` → `RETRYABLE_ERROR:rate_limited` (ENH-3607) |
| `snap_and_size_review` | Snapshot active IDs before a post-decision size review | DROPPED | Only reachable from removed states; the main path (`recheck_scores.on_no` → `run_size_review`) never took the snapshot |
| `autodev-pre-spike-readiness.txt` consumers | Plateau baseline for `check_reconcile_needed` | CHANGED | Uses `autodev-pre-readiness.txt` (pre-refine, written by `dequeue_next`) |

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`: remove 22 states, add
  `select_obligation_post_size_review`, `PROOF` routes, retargets, `init` / `dequeue_next` /
  `check_reconcile_needed` / `finalize_done` marker edits, the `dispatch_pre_deferral_remedy`
  comment
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`: `check_proof_before_done`; the
  `check_spike_needed` comment (ENH-3250 "mirrors autodev.yaml's check_spike_needed")
- Stale comments: `little_loops.cli.issues.show` (ENH-2640), `little_loops.cli.issues.check_gate`
  (module docstring: autodev callers), `little_loops.issue_lifecycle` (deferral-reason comments)
- `scripts/tests/data/loop_interpolation_baseline.json`: delete autodev's `check_spike_needed`
  and `check_spike_needed_before_skip` entries in the same commit

### Tests
Rewrite, don't delete (ENH-3075 AC 8); stays-deleted guard per removed state.
- `test_autodev_scores_freshness.py`: `decide`/`spike` cases rewritten to the child's freshness
  route (`route_spike_verdict` `PROVEN` → `confidence_check` → `mark_evidence_absent_infra` on
  missing scores, BUG-3588); `wire`/`atomic`/`reconcile` cases unchanged
- `test_spike_verdict_routing.py`: autodev legs rewritten against the child; BUG-3593
  refuted/inconclusive routing holds end to end
- `test_ll_issues_check_gate.py`: `TestProofGateFailClosed` (predecessors of
  `implement_current` are exactly `{"check_proof_defer_or_implement"}`, no
  `on_error`/`on_cannot_judge` edge; `check_proof_gate_before_implement.on_error` assertion
  replaced by a stays-deleted guard); `TestAutodevRouting` proof legs
- `test_builtin_loops.py`: spike chains, `AUTODEV_NOT_READY_STATES` (drop
  `record_decision_unresolved`), selector `PROOF` routes, child `check_proof_before_done`
- `test_autodev_loop.py`, `test_rn_remediate.py` (parity docstrings), `test_show.py` (docstrings)
- `test_fsm_topology.py`: autodev −22 +1, child +1, each with a history comment
- New real-FSM tests:
  - a high-scoring issue with a `structured_proof` gate is spiked in the child, then
    implemented or deferred;
  - `spike-runs-<ID>` persists across autodev re-entries (the budget does not reset);
  - a `PROOF:absent` issue whose child never spikes (`spike_attempted` set without
    `spike_completed`) re-enters once, then terminates via `--skip PROOF`.

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` (autodev section), `docs/reference/DEFERRAL_CODES.md`,
  `docs/reference/CLI.md` (`check-gate` FSM use, `--honor-waiver` callers),
  `docs/reference/API.md`, `docs/reference/ISSUE_TEMPLATE.md` (`spike_attempted`)

## Program Design

### Types

- No new types

### Signatures

- `cmd_check_gate(config: BRConfig, args: argparse.Namespace) -> int` — existing; the child's new proof gate and autodev's surviving proof stage both call it
- `cmd_next_obligation(config: BRConfig, args: argparse.Namespace) -> int` — existing (FEAT-3598); the selectors route its `PROOF:*` tokens and pass `--skip PROOF` once capped

### Call Path

`autodev.yaml:select_obligation_post_refine` -> `cmd_next_obligation` -> `autodev.yaml:refine_current` -> `refine-to-ready-issue.yaml:check_proof_before_done` -> `cmd_check_gate` -> `refine-to-ready-issue.yaml:run_spike`

`autodev.yaml:check_passed` -> `autodev.yaml:check_proof_defer_or_implement` -> `cmd_check_gate` -> `autodev.yaml:implement_current`

## Impact

- **Priority**: P3, child of ENH-3608 (EPIC-3565 consolidation); last blocker for ENH-3605 and
  ENH-3600
- **Effort**: Large: −22/+1 autodev states, +1 child state, 7 edge retargets, marker cleanup
  across four surviving states
- **Risk**: High: removes autodev's spike path; the child proof gate and the fail-closed
  implement gate are the safety net
- **Breaking Change**: No (loop-internal)

## Parent Issue

Decomposed from ENH-3608: Remove autodev spike and decision routes and route on the child run
record. Lands after ENH-3609 and ENH-3610; uses the selectors and re-entry cap ENH-3610 adds. ENH-3599 holds the original design rationale.

## Scope Boundaries

- **In scope**: removing the 22 states listed in Current Behavior; the child's
  `check_proof_before_done`; `PROOF` routes and the third selector; the retargets; the marker
  changes above; stale comments; tests and docs.
- **Out of scope**: `oracles/resolve-decision.yaml`'s contract; the child's own spike states
  (they stay; `spike-gate.yaml` and `rn-remediate.yaml` also have same-named states that must
  survive, so scope state-name greps to `autodev.yaml`); ENH-3600's marker retirement;
  ENH-3605/ENH-3606 remedy moves (only their edges into removed states change here).

## Acceptance Criteria

- [ ] No state in `autodev.yaml` runs `/ll:spike` or `oracles/resolve-decision`
- [ ] All 22 states are gone, with a stays-deleted guard each; no autodev edge targets a removed
  state; every retarget row holds (structural tests)
- [ ] `implement_current`'s only predecessor is the fail-closed `check_proof_defer_or_implement`;
  `MISSING` never reaches it
- [ ] A high-scoring issue with a `structured_proof` gate and spike budget left is spiked by the
  child before `done` (real-FSM test); the child never reaches `done` with that gate open and
  budget unspent
- [ ] `PROOF` re-entry is capped at one per issue and the run terminates when the child cannot
  satisfy it (real-FSM test)
- [ ] Autodev never writes `spike-runs-<ID>`; the budget persists across re-entries (real-FSM
  test); autodev no longer reads or writes `autodev-pre-spike-readiness.txt` or
  `autodev-spike-no-verdict.txt`
- [ ] `auto-refine-and-implement` and `oracles/resolve-decision` behavior unchanged, including
  `auto-refine-and-implement`'s `finalize` counts for a decision-unresolved stop; full suite
  passes

## Status

**Open** | Created: 2026-09-26 | Priority: P3
