---
id: ENH-3608
type: ENH
title: Remove autodev spike and decision routes and route on the child run record
priority: P3
status: done
discovered_by: issue-size-review
discovered_date: '2026-09-26'
captured_at: '2026-09-26T03:19:50Z'
decision_needed: false
blocked_by:
- ENH-3607
blocks:
- ENH-3605
- ENH-3600
relates_to:
- ENH-3577
- ENH-3597
- BUG-3603
- ENH-3599
parent: EPIC-3565
confidence_score: 70
outcome_confidence: 48
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 0
completed_at: '2026-09-26T03:48:02Z'
---

# ENH-3608: Remove autodev spike and decision routes and route on the child run record

## Summary

Second half of ENH-3599. Delete autodev's spike and decision repair routes, route
`refine_current` on the child's `RunRecord.outcome` through the `route_refine_outcome`
state ENH-3607 added, retarget every surviving edge into a removed state, and adopt
`ll-issues next-obligation` for the "still needs a decision or spike?" question.

## Parent Issue

Decomposed from ENH-3599: Move spike and decision repair routing from autodev into
refine-to-ready-issue. The parent holds the full design rationale, current line anchors
(Codebase Research Findings, 2026-09-26 list) and the complete test/doc wiring inventory
(Integration Map); the items below are this child's share.

## Current Behavior

Autodev duplicates the child's spike/decision states (`check_spike_needed`, `run_spike`,
`route_spike_verdict`, `check_spike_budget`, `record_spike_inconclusive`,
`mark_spike_no_verdict_infra`, `check_decide_rate_limited`, `record_decision_unresolved`)
and adds its own decision entry points (`check_decision_at_dequeue`,
`resolve_decision_at_dequeue`, `mark_decide_ran_at_dequeue`, `check_decision_after_refine`,
`decide_current`, `resolve_decision`, `resolve_decision_direct`, `mark_decide_ran`,
`check_rearmed_spike_after_decide`, `check_decision_before_size_review`,
`check_spike_needed_before_skip`, `check_proof_gate_before_implement`), the `decide`/`spike`
rescoring triplets, `triage_outcome_failure`, `recheck_after_decide` and
`count_repair_cycle_spike`. It reads and writes `autodev-decide-ran`,
`autodev-spike-inconclusive.txt`, `autodev-spike-no-verdict.txt`,
`autodev-decision-unresolved.txt`, `autodev-pre-spike-readiness.txt` and `spike-runs-*`.

## Expected Behavior

Autodev never invokes `/ll:spike` or `oracles/resolve-decision`. It routes on the child's
run record; when an issue still needs a decision or spike, it re-enters the child.

## Scope Boundaries

- **In scope**: removing the states above, the outcome routing on the success path,
  `ledger_child_stop`, `select_obligation`, the edge retargets, the marker removals, and
  the tests/docs that pin them.
- **Out of scope**: the read path, child `run_spike` rate-limit handling and the
  `rate_limited` route (ENH-3607); moving wire/refine and reconcile/design remedy (ENH-3605)
  or size-review/atomic, go/no-go and pre-deferral remedy (ENH-3606) — only their edges into
  removed states change here; migrating `auto-refine-and-implement` to run records
  (ENH-3600); `oracles/resolve-decision.yaml`'s contract.

## Proposed Solution

### Outcome routing table

Extend `route_refine_outcome` (from ENH-3607) and enter it from `copy_broke_down` as well
as `refine_current.on_failure`:

| Token | Route |
|---|---|
| `READY` | `check_passed` → `on_yes: check_proof_defer_or_implement` |
| `DECOMPOSED` | `detect_children` |
| `CANCELLED` | `dequeue_next` |
| `BLOCKED:*` / `DEFERRED:*` | `ledger_child_stop` (ledger row from the record's `legacy_class`) → `dequeue_next` |
| `RETRYABLE_ERROR:rate_limited` | `finalize_rate_limited` (ENH-3607) |
| `RETRYABLE_ERROR:*` | `skip_inflight_infra` |
| `MISSING` / `_` / `_error` | `skip_inflight` (keeps the evidenced exit-143 / inflight-sentinel handling) |

`ledger_child_stop` replaces the double-count guard of `skip_inflight`'s three marker
greps. `finalize_done` counts decision-unresolved and spike-inconclusive stops from its
rows instead of from the child's marker files. The row format must not make
`auto-refine-and-implement`'s `finalize` count one decision-unresolved stop twice (it counts
`autodev-skipped.txt` **and** `autodev-decision-unresolved.txt`).

### Selector state

`select_obligation` runs `ll-issues next-obligation <ID> --format token`: `DECISION*` /
`PROOF*` → `refine_current`; otherwise → the not-needed successor in the table below. Use
one selector state per distinct not-needed successor (e.g. `select_obligation_post_refine`,
`select_obligation_pre_implement`, `select_obligation_post_size_review`). The selector does
not spend `spike-runs-<ID>`; the child's `check_spike_budget` enforces the budget on
re-entry.

### Edge retarget table

| Surviving state | Edge | Removed target | New target |
|---|---|---|---|
| `check_status_at_dequeue` | `on_no`, `on_error` | `check_decision_at_dequeue` | `check_blockers_at_dequeue` |
| `copy_broke_down` | `next`, `on_error` | `check_decision_after_refine` | `route_refine_outcome` |
| `check_passed` | `on_yes` | `check_proof_gate_before_implement` | `check_proof_defer_or_implement` |
| `check_passed` | `on_no`, `on_cannot_judge` | `triage_outcome_failure` | selector (not needed → `check_missing_artifacts`) |
| `recheck_scores` | `on_yes` | `decide_current` | selector (not needed → `check_proof_defer_or_implement`) |
| `recheck_scores` | `on_no`, `on_cannot_judge`, `on_error` | `check_decision_before_size_review` | `run_size_review` |
| `recheck_after_size_review` | `on_yes` | `decide_current` | selector (not needed → `check_proof_defer_or_implement`) |
| `regate_after_atomic_remediation` | `on_yes` | `decide_current` | selector (not needed → `check_proof_defer_or_implement`) |
| `reopen_waived` | `next` | `decide_current` | selector (not needed → `check_proof_defer_or_implement`) |
| `check_parent_resolved_post_size_review` | `on_no`, `on_error` | `check_spike_needed_before_skip` | selector (not needed → `check_reconcile_needed`) |
| `dispatch_pre_deferral_remedy` | `on_yes` | `run_spike` | `refine_current` |

### Proof gate

`check_proof_defer_or_implement` becomes the only proof stage and the only predecessor of
`implement_current`. No first-stage proof classification survives; "proof unmet → spike"
lives in the child (`check_spike_needed`) and, on the autodev side, in the selector
(`PROOF*` → re-enter the child).

### Stagnation and freshness

- Deleting `count_repair_cycle_spike` (FEAT-2751) is covered by re-entry: every re-entry
  passes `refine_current → count_repair_cycle_refine`.
- The child's post-spike freshness guard is `route_spike_verdict` (`PROVEN`) →
  `confidence_check` (`oracles/verify-confidence-scores`) → `mark_evidence_absent_infra`
  on missing scores (BUG-3588).

### Mechanics

- Removed states read the ID from `captured.input.output`; the child uses
  `captured.issue_id.output`. Scope state-name greps to `autodev.yaml`: `spike-gate.yaml` and
  `rn-remediate.yaml` have same-named states that must survive.
- The child keeps writing `autodev-decide-ran`, `autodev-decision-unresolved.txt`,
  `autodev-proposal-unsound.txt` and `autodev-spike-inconclusive.txt` until ENH-3600.
- `spike-runs-<ID>` becomes child-only; `resolve_issue` in the child must keep not
  resetting it (`test_resolve_issue_does_not_reset_spike_counter`).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`
- Stale comments: `little_loops.cli.issues.show` (ENH-2640 comments), `little_loops.cli.issues.check_gate`
  (module docstring), `little_loops.issue_lifecycle` (deferral-reason comments),
  `rn-remediate.yaml` ("Mirrors autodev's resolve_decision_direct")

### Tests
Rewrite, don't delete (ENH-3075 AC 8); add stays-deleted guards (pattern:
`TestAssertDecisionClearedStructural`). Full per-test inventory in the parent's Integration
Map.
- `test_autodev_scores_freshness.py` — `decide`/`spike` cases rewritten to the child's
  freshness route; `wire`/`atomic`/`reconcile` unchanged
- `test_spike_verdict_routing.py`, `test_autodev_decision_gate.py` — autodev legs rewritten
  against the child; BUG-3593 behavioral routing still holds
- `test_ll_issues_check_gate.py` — `TestAutodevRouting`; `TestProofGateFailClosed`
  (`check_proof_gate_before_implement.on_error` assertion replaced by a stays-deleted guard)
- `test_builtin_loops.py` — decide/spike chains, dequeue-decision routing, skip-ledger
  tests, `AUTODEV_NOT_READY_STATES` (drop `record_decision_unresolved`)
- `test_fsm_topology.py` — `test_autodev_topology` count with history comment
- `test_autodev_loop.py`, `test_rn_remediate.py` (parity docstrings), `test_show.py` (docstrings)
- `scripts/tests/data/loop_interpolation_baseline.json` — delete `check_spike_needed` and
  `check_spike_needed_before_skip` (autodev) in the same commit

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` (autodev section), `docs/reference/DEFERRAL_CODES.md`,
  `docs/reference/CLI.md` (`check-gate` FSM use, `--honor-waiver` callers),
  `docs/reference/API.md`, `docs/reference/ISSUE_TEMPLATE.md` (`spike_attempted`),
  `docs/guides/DECISIONS_LOG_GUIDE.md`
- `skills/decide-issue/reference.md` — then `ll-adapt --host <gemini|kimi-code|qwen> --apply`

## Acceptance Criteria

- [ ] No state in `autodev.yaml` runs `/ll:spike` or `oracles/resolve-decision`
- [ ] Every state listed in Current Behavior is gone from `autodev.yaml`, and every row of
  the *Edge retarget table* holds (structural test: no autodev edge targets a removed
  state; stays-deleted guard per removed state)
- [ ] Autodev no longer reads or writes the listed marker files
- [ ] The only route into `implement_current` is `route_refine_outcome` (`READY`) →
  `check_passed` → fail-closed `check_proof_defer_or_implement`; `MISSING` never reaches
  it; `TestProofGateFailClosed` still asserts predecessors are exactly
  `{"check_proof_defer_or_implement"}` with no `on_error`/`on_cannot_judge` edge
- [ ] `route_refine_outcome` routes every token in the *Outcome routing table* and is entered
  from both `copy_broke_down` and `refine_current.on_failure` (structural test per token;
  real-FSM test that a `BLOCKED:decision_unresolved` stop is ledgered once and not counted
  as `refine_failed`)
- [ ] The selector states route `DECISION*`/`PROOF*` to `refine_current` and everything
  else to the not-needed successor in the retarget table (structural test)
- [ ] `spike-runs-<ID>` persists across autodev re-entries into the child (real-FSM test:
  the spike budget does not reset)
- [ ] `auto-refine-and-implement` and `oracles/resolve-decision` behavior unchanged,
  including `auto-refine-and-implement`'s `finalize` counts for a decision-unresolved stop
- [ ] `test_autodev_scores_freshness.py` `wire`/`atomic`/`reconcile` cases pass unchanged;
  `decide`/`spike` cases assert the child's freshness route; refuted/inconclusive spike
  routing (BUG-3593) holds end to end

## Impact

- **Priority**: P3 - child of ENH-3599 (EPIC-3565 consolidation); blocks ENH-3605
- **Effort**: Large - removes ~24 autodev states, adds 3–5, retargets 19 edges
- **Risk**: High - rewrites routing in the most-used loop
- **Breaking Change**: No - loop-internal

## Program Design

### Types

- No new types; consumes `RunRecord` / `PreparationOutcome` from ENH-3597

### Signatures

- `cmd_run_record_read(config: BRConfig, args: argparse.Namespace) -> int` — from ENH-3607; `route_refine_outcome` routes on its token
- `cmd_next_obligation(config: BRConfig, args: argparse.Namespace) -> int` — existing (FEAT-3598); the selector states route on its token

### Call Path

`autodev.yaml:route_refine_outcome` -> `cmd_run_record_read` -> `autodev.yaml:check_passed` -> `autodev.yaml:check_proof_defer_or_implement` -> `cmd_check_gate` -> `autodev.yaml:implement_current`

`autodev.yaml:select_obligation` -> `cmd_next_obligation` -> `autodev.yaml:refine_current`

## Status

**Open** | Created: 2026-09-26 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-25_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 48/100 → LOW

### Concerns
- Spec is otherwise clear and gate-clean (Program Design passes, no claim/parity/structure gaps); readiness is 70 before the dependency override.

### Gaps to Address
- Unresolved `blocked_by`: ENH-3607 (open). `route_refine_outcome` and `run-record read` do not exist in `autodev.yaml` yet; this issue extends them. Land ENH-3607 first, then re-run.

### Outcome Risk Factors
- broad enumeration across ~24 removed states, 3–5 added, 19 retargeted edges and 8+ test files (very wide blast radius)
- deep per-site complexity: control-flow restructuring of the most-used loop's routing
- selector-state count left as "e.g." (3–5) — minor open detail

## Session Log
- `/ll:confidence-check` - 2026-09-26T03:32:06 - `e6ad8ea2-14d6-441f-a607-435314c2d056.jsonl`
- `/ll:verify-issues` - 2026-09-26T03:26:55 - `0645a9c4-2e38-4d02-9b76-47ae90b8a2ea.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-09-26
- **Decomposed into**: ENH-3609, ENH-3610, ENH-3611

Work for ENH-3608 is now carried by its child issues; this parent was closed by rn-decompose.
