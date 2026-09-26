---
id: ENH-3610
type: ENH
title: Move autodev decision repair into refine-to-ready-issue behind an obligation
  selector
priority: P3
status: open
discovered_by: issue-size-review
discovered_date: '2026-09-26'
captured_at: '2026-09-26T03:47:26Z'
parent: EPIC-3565
decision_needed: false
blocked_by:
- ENH-3609
blocks:
- ENH-3611
relates_to:
- ENH-3608
- ENH-3599
- FEAT-3598
- ENH-3604
confidence_score: 100
outcome_confidence: 65
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# ENH-3610: Move autodev decision repair into refine-to-ready-issue behind an obligation selector

## Summary

Second of three children of ENH-3608. Move autodev's decision **entry points** into
`refine-to-ready-issue`. The child gains a decision gate before `done`, and autodev gains an
obligation selector that sends an issue back into the child when a decision is still needed.
Autodev's eight decision entry states are removed, and one exhaustion state
(`record_reentry_exhausted`) is added. The post-decision chain that autodev's refuted-spike leg
still uses stays until ENH-3611 removes it.

## Current Behavior

- Autodev checks and resolves `decision_needed` itself at five points: at dequeue
  (`check_decision_at_dequeue` → `resolve_decision_at_dequeue` → `mark_decide_ran_at_dequeue`),
  after refine (`check_decision_after_refine`), on low outcome (`triage_outcome_failure` →
  `resolve_decision_direct`, which also fires on `score_ambiguity <= 10`), before size review
  (`check_decision_before_size_review`), and before implementation on every score-pass site
  (`decide_current`, reached from `recheck_scores`, `recheck_after_size_review`,
  `regate_after_atomic_remediation`, `reopen_waived`).
- The child can reach `done` with `decision_needed: true`. `check_outcome.on_yes` goes straight
  to `done`, and the child's only decision gates are mid-chain (`check_decision_mid_refine`,
  `check_decision_mid_wire`) and in the low-outcome band (`check_decision_needed`).
- `ll-issues next-obligation` cannot answer "is a decision still needed?" once scores pass.
  `select_next_obligation` returns `NONE` whenever scores meet thresholds (and also when
  `SCORES` is skipped), so a selector built only on it is blind at every score-pass site.

## Expected Behavior

- **Child invariant**: `refine-to-ready-issue` never reaches `done` with
  `decision_needed: true`, except through `write_broke_down`. A new `check_decision_before_done`
  state sits on the three no-class `done` edges (`check_outcome.on_yes`,
  `check_missing_artifacts.on_yes`, `check_scores_from_file.on_yes`):
  - flag set → `check_decide_attempts`, the existing decide budget and path;
  - otherwise → `write_done_record` → `done`. The no-class `run-record write` moves from
    those three states into `write_done_record`, so a record is written only when `done` is
    really next.
- **Autodev never resolves a decision itself.** It has two selector states. Each one runs, in
  order:
  1. `ll-issues check-flag <ID> decision_needed`, which works when scores pass.
     - Exit 0 (flag set): apply the re-entry cap below and print `DECISION` or
       `DECISION_EXHAUSTED`. Do not run `next-obligation`.
     - Exit 1 (flag unset), or exit 2 (ID not resolvable): go to step 2. An ID that cannot be
       resolved makes `next-obligation` exit 2 too, so it reaches `_error`.
  2. `ll-issues next-obligation <ID> --format token --readiness-threshold
     ${context.readiness_threshold} --outcome-threshold ${context.outcome_threshold}
     --honor-waiver`, matching `check_passed`'s predicate. Print its token. A non-zero exit
     goes to `_error`.

  `next-obligation` does not change any route in this issue. Its `DECISION` predicate is the
  same `decision_needed` flag that step 1 already reads (`_tier3_probe`), so it cannot print
  `DECISION` here, and every other token goes to `_`. It is included so that ENH-3611 can add
  `PROOF:*` routes to the same selectors. Its only effect in this issue is an extra `_error`
  source; see Accepted behavior changes.

  | Selector | Placed at | `DECISION` | `DECISION_EXHAUSTED` | `_` (anything else) | `_error` |
  |---|---|---|---|---|---|
  | `select_obligation_post_refine` | `check_passed.on_no`, `.on_cannot_judge` | `refine_current` | `record_reentry_exhausted` | `check_spike_needed` | `detect_children` |
  | `select_obligation_pre_implement` | `check_passed.on_yes`, `recheck_scores.on_yes`, `recheck_after_size_review.on_yes`, `regate_after_atomic_remediation.on_yes`, `reopen_waived.next` | `refine_current` | `record_reentry_exhausted` | `check_proof_gate_before_implement` | `check_proof_gate_before_implement` |

  The `_error` routes copy the removed states' `on_error` targets: `triage_outcome_failure` →
  `detect_children`, and `decide_current` → the proof gate, which is fail-closed (BUG-3603).

  `check_passed.on_yes` goes through the pre-implement selector as well. The removed
  `check_decision_after_refine` checked the flag before `check_passed`. Without a selector at
  this site, the first score-pass site after refine would rely on the child invariant alone,
  while the other four score-pass sites have an autodev-side check. If the child and autodev
  predicates drift, this site is where it shows, so the check costs one `check-flag` call here.
- **Re-entry is bounded.** Before printing `DECISION`, the selector increments
  `${context.run_dir}/autodev-reentry-DECISION-<ID>`. If that counter is already ≥ 1 and the flag
  is still set, it prints `DECISION_EXHAUSTED` instead. `dequeue_next` clears
  `autodev-reentry-*-$CURRENT`, next to its `autodev-rescore-retry-*` clear. With the child
  invariant a second re-entry should never be needed; the cap guarantees the run ends even if
  the two predicates drift.
- **Exhaustion ledgers `decision_unresolved`.** The new `record_reentry_exhausted` state:
  - appends `<ID>  decision_unresolved` to `autodev-skipped.txt`;
  - clears `autodev-inflight`;
  - runs `ll-issues set-status <ID> deferred --by automation --reason decision_unresolved`,
    with the BUG-2729 guard that leaves a done/completed/cancelled issue unchanged;
  - then advances to `dequeue_next`.

  This is the same shape as `recheck_after_size_review`'s decision branch
  (`autodev.yaml`, the ENH-2936 block). `skip_inflight` is the wrong target: it ledgers
  `refine_failed` and does not defer the issue, so every run would pick the issue up again.
  `record_decision_unresolved` is also the wrong target, because ENH-3611 removes it. The
  state's name is generic because ENH-3611 can reuse it for `PROOF` exhaustion.
- **Selectors un-stage before re-entry.** All five pre-implement placement sites append the ID
  to `autodev-staged.txt` before the selector runs: `check_passed`, `recheck_scores`,
  `regate_after_atomic_remediation`, `reopen_waived` and `recheck_after_size_review`. On
  `DECISION` and `DECISION_EXHAUSTED`, the selector therefore removes the ID from
  `autodev-staged.txt` before printing the token. It uses the `grep -vxF` idiom from `mark_not_started`. Without this, an
  issue that the re-entered child defers (`BLOCKED:decision_unresolved` →
  `ledger_child_stop`), or that hits the cap, stays staged. `finalize_done` would then also list
  it in `autodev-unverified.txt`, which counts against the run verdict. A child run that
  succeeds re-stages the ID at `check_passed`.
- **Retargets**: the eight removed states' inbound edges, plus `check_passed.on_yes`, which
  gets the new selector without its old target being removed:

  | Surviving state | Edge | Old target | New target |
  |---|---|---|---|
  | `check_status_at_dequeue` | `on_no`, `on_error` | `check_decision_at_dequeue` | `check_blockers_at_dequeue` |
  | `route_refine_success` | `READY`, `BLOCKED`, `MISSING`, `_`, `_error` | `check_decision_after_refine` | `check_passed` |
  | `check_passed` | `on_yes` | `check_proof_gate_before_implement` (kept; now the selector's `_`) | `select_obligation_pre_implement` |
  | `check_passed` | `on_no`, `on_cannot_judge` | `triage_outcome_failure` | `select_obligation_post_refine` |
  | `recheck_scores` | `on_yes` | `decide_current` | `select_obligation_pre_implement` |
  | `recheck_scores` | `on_no`, `on_error`, `on_cannot_judge` | `check_decision_before_size_review` | `run_size_review` |
  | `recheck_after_size_review` | `on_yes` | `decide_current` | `select_obligation_pre_implement` |
  | `regate_after_atomic_remediation` | `on_yes` | `decide_current` | `select_obligation_pre_implement` |
  | `reopen_waived` | `next` | `decide_current` | `select_obligation_pre_implement` |

### Accepted behavior changes

- **Decision trigger narrows.** `triage_outcome_failure` fired on
  `score_ambiguity <= 10 OR decision_needed`. The selector fires on `decision_needed` alone. A
  low ambiguity score without the flag no longer triggers a decision: `/ll:confidence-check`
  and `/ll:refine-issue` set the flag when a decision is actually open, and the ambiguity
  shortcut duplicated that.
- **Dequeue-time decisions move later.** A flagged issue is no longer decided before refine
  starts. The child resolves it mid-refine (`check_decision_mid_refine`) or before `done`.
- **Re-entry costs a full child run.** A `DECISION` re-entry goes through `refine_current`, so
  the child runs format, refine, wire, verify and confidence-check before it reaches a decision
  gate. The old autodev path called the resolve oracle directly. Re-entry also passes
  `count_repair_cycle_refine`, so it counts toward the FEAT-2751 stagnation check in
  `recheck_after_size_review`. This is accepted: with the child invariant, a re-entry happens
  only when an autodev-side repair (size review, atomic remediation, go/no-go waiver) sets the
  flag again, or when the two predicates drift.
- **The post-refine selector has one more `_error` source.** `triage_outcome_failure.on_error`
  fired only when `ll-issues show` failed. The selector's `_error` also fires when
  `next-obligation` exits 2 because a fail-closed VERIFY or SCORES probe raised. That case
  now goes to `detect_children`, where the old path went to `check_spike_needed`. ENH-3611
  keeps `_error` → `detect_children`, so this is accepted rather than remapped.

### Behavior Parity

| Removed autodev state | Behavior | Disposition | Where it lives now |
|---|---|---|---|
| `check_decision_at_dequeue` / `resolve_decision_at_dequeue` / `mark_decide_ran_at_dequeue` | Resolve `decision_needed` before refine starts | MOVED (later) | Child: `check_decision_mid_refine`, `check_decision_before_done` |
| `check_decision_after_refine` | Resolve `decision_needed` after a successful child run, before `check_passed` | MOVED | Child: `check_decision_before_done` (the child cannot reach `done` with the flag set). Autodev keeps a check: `check_passed.on_yes` → `select_obligation_pre_implement`, and `.on_no` → `select_obligation_post_refine` |
| `triage_outcome_failure` → `resolve_decision_direct` | Decide on low outcome when `decision_needed` or `score_ambiguity <= 10` | CHANGED | `select_obligation_post_refine` → child re-entry on `decision_needed` only (see Accepted behavior changes) |
| `triage_outcome_failure` (no-decision leg) | Fall through to the spike check | PRESERVED | `select_obligation_post_refine` `_` → `check_spike_needed` |
| `triage_outcome_failure.on_error` | Probe failure → `detect_children` | PRESERVED | `select_obligation_post_refine` `_error` → `detect_children` |
| `check_decision_before_size_review` | Decide before size review | MOVED | `recheck_scores.on_no` → `run_size_review`; a flagged issue is re-entered into the child from the pre-implement selector instead |
| `decide_current` | Resolve `decision_needed` at every score-pass site before the proof gate | PRESERVED (must be restated) | `select_obligation_pre_implement` with `check-flag` first, because `next-obligation` returns `NONE` when scores pass |
| `decide_current.on_no` / `.on_error` | Go to the fail-closed proof gate | PRESERVED | `select_obligation_pre_implement` `_` / `_error` → `check_proof_gate_before_implement` |
| decide budget (`autodev-decide-ran`, one resolve per issue) | Bound decision attempts | CHANGED | Bounded by the child's structure and the autodev re-entry cap, not by one counter. Per child entry: `check_decide_attempts` (`refine-to-ready-decide-attempts`, reset in `resolve_issue`) allows one resolve at `check_decision_needed` / `check_decision_before_done`. `resolve_decision_mid_refine` and `resolve_decision_mid_wire` have no budget; `refine_followup` returns to `check_decision_mid_refine`, and the shared refine count limits that. So one entry can run the oracle about 3–4 times. Cap of one re-entry → at most two child entries per issue per run. The old autodev path also had these child mid-chain resolves on top of its own |
| `mark_decide_ran_at_dequeue.on_yes` → `record_decision_unresolved` | Defer an issue whose flag survived a dequeue-time resolve | CHANGED | Child: `record_decision_unresolved` → `BLOCKED:decision_unresolved` → `ledger_child_stop`. Autodev: `DECISION_EXHAUSTED` → `record_reentry_exhausted` (same `decision_unresolved` reason) |

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`:
  - remove 8 states; add 2 selectors and `record_reentry_exhausted`;
  - apply the retargets and add the `dequeue_next` clear;
  - update the comments outside the removed states that name removed states: lines 567, 787,
    891–892, 948–949, 1703, 1770, 1968, 2106, 2415, 2500, 2593, 2961 and 3019 at HEAD
    5ea867d5c. Line 3019 is the `dispatch_pre_deferral_remedy` comment ("on_yes →
    decide_current → proof gate"). Line 787 (`check_proof_gate_before_implement`:
    "check_spike_needed is only reachable through triage_outcome_failure") becomes wrong and
    needs a rewrite, not a rename. Lines 891–892 list `resolve_decision`'s entry points, which
    shrink to `check_spike_budget` only.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`:
  - add `check_decision_before_done` and `write_done_record`;
  - retarget the three `done` edges;
  - move the record write out of `check_outcome` / `check_missing_artifacts` /
    `check_scores_from_file`;
  - update the `check_missing_artifacts` comment (line 1130, "outer loop's
    triage_outcome_failure → check_missing_artifacts → run_wire path").
- `scripts/little_loops/loops/oracles/resolve-decision.yaml`: two comment updates only; the
  contract stays out of scope.
  - Line 34 names `triage_outcome_failure` as the `skip_probe` entry. `rn-remediate`'s
    `resolve_decision_direct` is now the only `skip_probe: "true"` caller.
  - Line 248's "Verified non-spinning" argument depends on `decide_current`'s
    `autodev-decide-ran` short-circuit. Restate it in terms of the child's
    `check_decide_attempts` and autodev's re-entry cap.
- `scripts/little_loops/loops/rn-remediate.yaml`: the "Mirrors autodev's
  resolve_decision_direct" comment

### Tests
Rewrite, don't delete (ENH-3075 AC 8); add stays-deleted guards (pattern:
`TestAssertDecisionClearedStructural`).
- `test_autodev_decision_gate.py`: autodev decision legs rewritten as "selector → child
  re-entry"; stays-deleted guard per removed state
- `test_builtin_loops.py`: dequeue-decision routing and decide-chain entry tests rewritten;
  structural tests for both selector route tables and the retarget table; child structural test
  that every no-class `done` edge passes `check_decision_before_done`
- `test_builtin_loops.py`: add `record_reentry_exhausted` to `AUTODEV_NOT_READY_STATES`, so
  it is held to the `mark_deferred` set-status shape
- `test_ll_issues_check_gate.py`: `TestAutodevRouting` has no decision legs. Line 302 asserts
  `check_passed.on_yes == "check_proof_gate_before_implement"`. Change it to
  `select_obligation_pre_implement`, and assert that the selector's `_` goes to the proof gate.
- `test_autodev_scores_freshness.py`: lines 95–96 assert
  `("check_passed", "triage_outcome_failure")` and
  `("recheck_scores", "check_decision_before_size_review")`. Retarget them to
  `select_obligation_post_refine` / `run_size_review`.
- `test_autodev_loop.py`: the line-622 docstring names `decide_current`
- `test_rn_remediate.py`: parity docstrings
- `test_fsm_topology.py`: autodev −8 +3, child +2, each with a history comment
- New real-FSM tests:
  - scores pass with `decision_needed: true` → selector → child re-entry → decision
    resolved → implementation, never implementation with the flag set;
  - the same at `check_passed.on_yes`, with a stubbed child that reaches `done` with the flag
    set (drift): the selector catches it;
  - a child that leaves the flag set twice ends in `DECISION_EXHAUSTED` →
    `record_reentry_exhausted`, and the run terminates. The issue is `deferred` with reason
    `decision_unresolved`, `autodev-skipped.txt` has `<ID>  decision_unresolved` and no
    `refine_failed` row, and the ID is not in `autodev-staged.txt` or
    `autodev-unverified.txt`;
  - a staged issue re-entered on `DECISION` whose child then stops with
    `BLOCKED:decision_unresolved` is not in `autodev-unverified.txt` at `finalize_done`;
  - a numeric input ID behaves the same as a canonical one.

### Documentation
- `docs/guides/LOOPS_REFERENCE.md`, autodev section: decisions are resolved in the child;
  the selector and re-entry cap
- `docs/guides/DECISIONS_LOG_GUIDE.md` and `skills/decide-issue/reference.md`: autodev caller
  paths, then `ll-adapt --host <gemini|kimi-code|qwen> --apply`
- `docs/reference/CLI.md`: `check-flag` / `next-obligation` FSM callers
- `docs/reference/DEFERRAL_CODES.md`: the `decision_unresolved` row's source column adds
  `record_reentry_exhausted`

## Program Design

### Types

- No new types

### Signatures

- `cmd_check_flag(config: BRConfig, args: argparse.Namespace) -> int` — existing; the selector's first probe, valid at score-pass sites
- `cmd_next_obligation(config: BRConfig, args: argparse.Namespace) -> int` — existing (FEAT-3598); the selector's second probe with context thresholds and `--honor-waiver`
- `cmd_run_record_write(config: BRConfig, args: argparse.Namespace) -> int` — existing; now called only from the child's `write_done_record` on the no-class `done` paths

### Call Path

`autodev.yaml:select_obligation_pre_implement` -> `cmd_check_flag` -> `autodev.yaml:refine_current` -> `refine-to-ready-issue.yaml:check_decision_before_done` -> `refine-to-ready-issue.yaml:write_done_record` -> `cmd_run_record_write`

`autodev.yaml:select_obligation_post_refine` -> `cmd_next_obligation` -> `autodev.yaml:check_spike_needed`

`autodev.yaml:check_passed` -> `autodev.yaml:select_obligation_pre_implement` -> `cmd_check_flag` -> `autodev.yaml:record_reentry_exhausted` -> `cmd_set_status`

## Impact

- **Priority**: P3, child of ENH-3608 (EPIC-3565 consolidation)
- **Effort**: Medium-large: −8/+3 autodev states, +2 child states, 17 edge retargets
- **Risk**: High: changes where decisions are resolved in the most-used loop; the child
  invariant and the re-entry cap are the safety net
- **Breaking Change**: No (loop-internal)

## Parent Issue

Decomposed from ENH-3608: Remove autodev spike and decision routes and route on the child run
record. Siblings: ENH-3609 (lands first; adds `route_refine_success`) and ENH-3611 (lands after
this one; removes the remaining 22 states). ENH-3599 holds the
original design rationale.

## Scope Boundaries

- **In scope**: removing `check_decision_at_dequeue`, `resolve_decision_at_dequeue`,
  `mark_decide_ran_at_dequeue`, `check_decision_after_refine`, `decide_current`,
  `check_decision_before_size_review`, `triage_outcome_failure`, `resolve_decision_direct`; the
  two selectors, the re-entry cap, selector un-staging and `record_reentry_exhausted`; the
  child's `check_decision_before_done` and `write_done_record`; the retargets above; comment
  updates at every site listed under Files to Modify; tests and docs.
- **Left on purpose**: after this issue, nothing in autodev reads `autodev-decide-ran`.
  `decide_current` was its only reader. `mark_decide_ran` still writes it and `dequeue_next`
  still clears it. Do not remove it as dead code here: ENH-3611 drops the `dequeue_next` clear,
  and ENH-3600 retires the marker.
- **Out of scope**: `resolve_decision` and its post-decision chain (`mark_decide_ran`, the
  `decide` rescoring triplet, `recheck_after_decide`, `check_rearmed_spike_after_decide`,
  `check_decide_rate_limited`, `record_decision_unresolved`, `snap_and_size_review`). They stay
  reachable from autodev's `check_spike_budget` (the refuted-spike leg) and are removed with the
  spike states in ENH-3611. `PROOF` routing: until ENH-3611 lands,
  `next-obligation`'s `PROOF:*` tokens fall to `_`. `oracles/resolve-decision.yaml`'s contract.
  The child-written marker files (ENH-3600). Renaming the child's
  `resolve_decision_pre_breakdown`, which is now also reached from
  `check_decision_before_done`; update its comment only.

## Acceptance Criteria

- [ ] The eight states above are gone from `autodev.yaml`, with a stays-deleted guard each; no
  autodev edge targets a removed state
- [ ] No autodev state runs `oracles/resolve-decision` except `resolve_decision`, which is
  reachable only from `check_spike_budget`
- [ ] Every row of both selector tables and the retarget table holds (structural tests)
- [ ] The child never reaches `done` with `decision_needed: true` except via `write_broke_down`
  (structural test on every `done` edge plus a real-FSM test)
- [ ] An issue with passing scores and `decision_needed: true` is re-entered into the child and
  never reaches `implement_current` with the flag set (real-FSM test)
- [ ] `check_passed.on_yes` routes through `select_obligation_pre_implement`; a child that
  drifts and reaches `done` with the flag set is caught there (real-FSM test)
- [ ] Re-entry per issue per obligation is capped at one. The capped case routes to
  `record_reentry_exhausted`: the issue is deferred with `decision_unresolved` (not ledgered
  as `refine_failed`), and the run terminates (real-FSM test)
- [ ] On `DECISION` / `DECISION_EXHAUSTED` the selector removes the ID from
  `autodev-staged.txt`, so an issue that re-entry defers never appears in
  `autodev-unverified.txt` (real-FSM test)
- [ ] No comment in `autodev.yaml`, `refine-to-ready-issue.yaml`,
  `oracles/resolve-decision.yaml` or `rn-remediate.yaml` names a removed autodev state as live
- [ ] `auto-refine-and-implement` and `oracles/resolve-decision` behavior unchanged; full suite
  passes

## Status

**Open** | Created: 2026-09-26 | Priority: P3

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the
issue as it now reads is up to date — this section is a record of what was wrong and fixed, not
an outstanding action item)

Verified 2026-09-26 against `autodev.yaml` and `refine-to-ready-issue.yaml` at HEAD 5ea867d5c:
all 8 removed states exist; both selectors are absent as expected (ENH-3609's
`route_refine_success` has landed); the child's three no-class `done` edges
(`check_outcome`, `check_missing_artifacts`, `check_scores_from_file`) and `write_broke_down`
match; every other retarget row, `_error` target, and the `rn-remediate.yaml` and
`dispatch_pre_deferral_remedy` comment sites match. `ll-verify-evidence`: clean. Decisions
gate: no violations. Graph: provider=`codegraph` freshness=`stale` (not used to originate a verdict).

- **Fixed**: the `route_refine_success` retarget row listed only `READY`, `BLOCKED`; the state
  also routes `MISSING`, `_`, and `_error` to `check_decision_after_refine`, so all five
  edges retarget to `check_passed`. Retarget count updated 13 → 16.

## Session Log
- `/ll:confidence-check` - 2026-09-26T06:01:37 - `95a3ad40-ecc6-4e5c-befd-9be7a282a332.jsonl`
- `/ll:verify-issues` - 2026-09-26T05:50:13 - `3a196c8d-c8cb-4f09-ab88-54c0f0f49d57.jsonl`
