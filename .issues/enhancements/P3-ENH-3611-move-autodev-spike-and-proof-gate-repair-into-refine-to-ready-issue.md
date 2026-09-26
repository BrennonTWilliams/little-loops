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
verify_verdict: VALID
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
confidence_score: 90
outcome_confidence: 51
score_complexity: 5
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
size: Large
---

# ENH-3611: Move autodev spike and proof-gate repair into refine-to-ready-issue

## Summary

Third of three children of ENH-3608. Move autodev's spike and proof-gate repair into
`refine-to-ready-issue` and remove the remaining 22 autodev spike/decision states. The child
gains a proof gate before `done`, so an open `structured_proof` gate on a high-scoring issue is
still spiked (ENH-3575), now inside the child. Autodev's selectors add `PROOF` re-entry (the
pre-implement selector probes `check-gate` directly, because `next-obligation` never reports
`PROOF` once scores pass), and `check_proof_defer_or_implement` becomes the only proof stage
before `implement_current`.

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
- `PROOF` has sources that a spike cannot satisfy. `assess_proof` also reports
  `absent`/`stale`/`refuted` for Learning Test Registry targets that the issue declares in its
  frontmatter. Only `/ll:explore-api` provisions those. `PROOF:stale` comes **only** from those
  targets. `PROOF:refuted` comes from `spike_refuted` **or** from a refuted registry record
  (`learning_tests/assess.py`, `_learning_test_statuses`). The token's sub-reason is the
  worst status across all targets (`_SEVERITY`: `refuted` 3 > `absent` 2 > `stale` 1), so a
  refuted registry target masks `spike=absent`. The sub-reason therefore cannot tell whether a
  spike could clear the obligation. Only the spike flags can.
- `spike_needed` does not depend on readiness. Its `FlagRule` precondition is outcome-only
  (`set_flags.py` `_rules_for_threshold`). Today autodev spikes a `spike_needed` issue at **any**
  readiness: `select_obligation_post_refine`'s `_` catches `SCORES:readiness_below` →
  `check_spike_needed`, and `check_spike_needed_before_skip` has no score predicate. The
  child's spike band sits behind `check_readiness.on_yes`, and `next-obligation` reports
  `PROOF` only when readiness passes.
- The child has a lifetime refine cap. Every child run passes `check_lifetime_limit`, which
  routes to `breakdown_issue` once `ll-issues refine-status <ID> --json` `refine_count`
  (session-log `/ll:refine-issue` count) reaches `commands.max_refine_count` (default 5). A
  child re-entry also runs `/ll:refine-issue` unconditionally (`precheck_format` →
  `refine_issue`), which adds one to that count.
- `PROOF` is a tier-3 obligation: `select_next_obligation` reports it only when readiness
  passes and outcome is **below** threshold (`next_obligation.py`, tier 3). Once scores pass
  (with `--honor-waiver`, including a waived outcome) it returns `NONE`. So
  `select_obligation_pre_implement` can never see a `PROOF` token from `next-obligation`.
- `select_obligation_pre_implement` has five predecessors: `check_passed.on_yes`,
  `recheck_scores.on_yes`, `regate_after_atomic_remediation.on_yes`, `reopen_waived.next` and
  `recheck_after_size_review.on_yes`. Only the first follows a child run that just reached
  `done`; the other four follow autodev-side repair (wire/refine, atomic remediation, the
  go/no-go waiver, size review). Today `check_proof_gate_before_implement` spikes an open
  `structured_proof` gate on all five.
- `dispatch_pre_deferral_remedy` is not read-only: on the `spike` remedy it **increments**
  `spike-runs-<ID>` and writes `autodev-pre-spike-readiness.txt` before routing to `run_spike`.
  `recheck_after_size_review` arms `spike` on a gate marker (`structured_proof`/`prose`) **or**
  on an ambiguity-dominant score pattern, regardless of the `spike_needed` flag.
- Autodev reads/writes `autodev-pre-spike-readiness.txt` (`dequeue_next`, the spike states,
  `check_reconcile_needed`, `dispatch_pre_deferral_remedy`), `autodev-spike-no-verdict.txt`
  (`init`, `mark_spike_no_verdict_infra`, `finalize_done`), `autodev-decide-ran`
  (`dequeue_next`, `mark_decide_ran`) and writes `spike-runs-<ID>`.

## Expected Behavior

- **Child proof gate.** A new `check_proof_before_done` sits between
  `check_decision_before_done` and `write_done_record`: both `check_decision_before_done.on_no`
  and `.on_error` retarget to it (today both go to `write_done_record`). It runs
  `ll-issues check-gate <ID>`. On `structured_proof` with `spike_attempted` unset and
  `spike-runs-<ID>` < 2, it increments the counter and routes to `run_spike` (the existing
  `route_spike_verdict` → `PROVEN` → `confidence_check` chain re-scores and returns through
  `check_outcome`; a proven spike sets `spike_completed`, which flips `check-gate` to
  `structured_satisfied`, so the second pass reaches `write_done_record`). Every other
  verdict, and a helper error, → `write_done_record`. This gate is fail-open because autodev's
  `check_proof_defer_or_implement` stays fail-closed downstream (BUG-3603).
  - **Match the token, not the exit code.** `check-gate` exits 0 for every in-force verdict
    (`structured_open`, `structured_proof`, `prose`). The state must capture stdout and match
    `structured_proof` exactly (the `case` idiom in `check_proof_gate_before_implement`). A
    bare `shell_exit` on the exit code would spike an external/manual or prose gate.
  - **Step budget.** The proof cycle (`check_proof_before_done → run_spike →
    route_spike_verdict → confidence_check → check_readiness → check_outcome →
    check_decision_before_done → check_proof_before_done → write_done_record`) adds ~8 steps.
    The refuted leg (`check_spike_budget → resolve_decision_pre_breakdown → confidence_check →
    …`) adds more. Raise `max_steps` 90 → 100 with a history comment in the file's
    existing convention. The history comment must state why +10 is enough: the shared
    `spike-runs-<ID>` cap (< 2) means a proof spike **replaces** one of the two spikes that
    BUG-3593's 60 → 70 bump already budgets. It does not add a third. The new cost is the two
    `check_proof_before_done` hops plus one extra `confidence_check → check_readiness →
    check_outcome → check_decision_before_done` band pass. Confirm that
    `circuit.repeated_failure.recurrent_window: 6` is not tripped by the new
    `(check_decision_before_done, 1, no)` triples (`check-flag` exits 1 when the flag is unset)
    and the `(check_proof_before_done, …)` triples on the worst-case path.
  - **Accepted:** `check_decision_before_done` is shared by all three no-class done edges, so
    the gate also fires on `check_missing_artifacts.on_yes` (a low-outcome issue exiting for
    autodev to wire). A `structured_proof` spike there runs before wiring and spends the
    shared budget. The proof question is independent of the missing artifacts, and the budget
    cap (< 2) bounds the cost, so the gate is not restricted to the score-pass edges.
  - **Accepted: contract change for non-autodev callers.** `recursive-refine.yaml`
    (`refine_issue` state) also runs this child, and so do the loops that wrap it
    (`issue-refinement`, `sprint-build-and-validate`, `rn-build`, `eval-driven-development`).
    Those runs now also spike an open `structured_proof` gate before `done`. Today they reach
    `done` with the gate open, and nothing downstream spikes it. This is intended: it extends
    ENH-3575's invariant (never "ready" with an unspiked proof gate while budget remains) to
    every caller. Outside autodev the child owns its own `${context.run_dir}`, so
    `spike-runs-<ID>` is per child run there. The `spike_attempted` guard still makes the gate
    one-shot per issue. This differs from widening the spike band (Scope Boundaries). That
    change would spike low-readiness issues for every caller, and no invariant requires it.
- **Selectors gain `PROOF`.** Every `PROOF` re-entry routes to `refine_current`, is capped at
  one per issue by `autodev-reentry-PROOF-<ID>` (the `DECISION` idiom; cleared at
  `dequeue_next`), and un-stages the ID from `autodev-staged.txt` before routing (the
  `grep -vxF` idiom ENH-3610's `DECISION` branch uses). When the cap is spent, or the child
  cannot act on the obligation (below), the selector re-runs `next-obligation --skip PROOF`
  and routes that token as usual, so it falls through to its not-needed successor. That
  successor never reaches implementation with an open gate, because
  `check_proof_defer_or_implement` still defers it as `blocked_by_gate`. No `PROOF_EXHAUSTED`
  token and no `record_reentry_exhausted` route for `PROOF` (decided: `blocked_by_gate` is the
  accurate reason; `decision_unresolved` would mislabel it). Probe order in
  `select_obligation_post_refine` and `select_obligation_pre_implement`:
  `check-flag decision_needed` first (ENH-3610's exit-code contract), then the `PROOF` probe,
  then `next-obligation`. `select_obligation_post_size_review` has no `check-flag` probe (see
  below). The selector's shell handles every raw `PROOF:*` token from `next-obligation`
  itself. When the guard passes, the selector prints its own bare `PROOF` token. Otherwise it
  re-runs `next-obligation --skip PROOF`. So `PROOF` is the only proof route key, and no
  `PROOF:<sub_reason>` token ever reaches `classify` routing.

  **Shared re-entry guard** (every `PROOF` re-entry, all three selectors): re-enter only when
  all of these hold. Otherwise use `--skip PROOF` (low-outcome sites) or fall through to
  `next-obligation` (pre-implement site).
  - `spike_attempted` is unset.
  - `spike-runs-<ID>` < 2.
  - `autodev-reentry-PROOF-<ID>` is unused.
  - **`refine_count` < the lifetime cap.** Read `refine_count` from
    `ll-issues refine-status <ID> --json`. Resolve the cap the way the child's
    `check_lifetime_limit` does: `commands.max_refine_count` in `.ll/ll-config.json`, default 5.
    Autodev has no `max_refine_count` context key, so read the config and do not add one.

  Without the cap term, a re-entered child at its lifetime cap routes to `breakdown_issue`
  before it reaches `check_proof_before_done`, so a high-scoring issue would be decomposed
  instead of spiked. With the cap term, the issue defers as `blocked_by_gate` instead, which is
  the accurate outcome.

  The `PROOF` probe differs by site, because `next-obligation` only reports `PROOF` below the
  outcome threshold:

  - **Low-outcome sites** (`select_obligation_post_refine`,
    `select_obligation_post_size_review`): **any** `PROOF:*` token from `next-obligation` is
    a re-entry candidate, whatever its sub-reason. The sub-reason is worst-status-wins across
    all targets, so it cannot identify a spikeable obligation (Current Behavior). The selector
    re-enters only when the child's low-outcome band can actually spike: `spike_needed` true,
    plus the shared guard above. Any other `PROOF:*` reading goes to `--skip PROOF`. This
    closes the cycle risk in Current Behavior. A `PROOF` from `spike_attempted` without
    `spike_completed`, a learning-test-only `PROOF`, or a gate-only `PROOF` that the child would
    route to `breakdown_issue` no longer costs a full child run. A spikeable issue whose
    `spike=absent` is masked by a refuted registry target is still re-entered.
  - **Pre-implement site** (`select_obligation_pre_implement`): scores pass, so it calls
    `ll-issues check-gate <ID>` itself. On `structured_proof` plus the shared guard above, it
    prints `PROOF` → `refine_current`,
    where the child's `check_proof_before_done` spikes it. Any other verdict, or a helper
    error, falls through to `next-obligation` (fail-open here is safe: `_`/`_error` go to the
    fail-closed `check_proof_defer_or_implement`). This covers the four sites that reach the
    selector without a fresh child `done` (`recheck_scores`, `regate_after_atomic_remediation`,
    `reopen_waived`, `recheck_after_size_review`).
  - **Post-size-review selector has no `check-flag` probe.**
    Such a probe would only suppress `PROOF` for a decision-flagged issue, and
    `next-obligation` already does that, because tier 3 checks `DECISION` before `PROOF`.
    `DECISION` goes to `_`, so `recheck_after_size_review`'s ENH-2936 decision branch keeps
    owning that case. Consequence, accepted: a decision-flagged issue gets no `PROOF` re-entry
    at this site. Un-staging is defensive here: the selector runs before
    `recheck_after_size_review` stages the ID in this pass, but an earlier pass may have staged
    it.
  - **The post-size-review selector is narrow by construction.** It re-enters only when
    readiness passes, outcome is below threshold, and `spike_needed` is newly set or still
    unspent after the child's last pass. The child's own low-outcome band normally spikes such
    an issue first. The selector remains the last chance before the skip, for a flag that was
    re-armed after the child's `check_spike_needed` ran. It does **not** preserve
    `check_spike_needed_before_skip`'s score-independent firing (see the low-readiness loss
    below).

  Final layout:

  | Selector | `PROOF` source | Not-needed (`_`) successor | `_error` |
  |---|---|---|---|
  | `select_obligation_post_refine` | `next-obligation` `PROOF:*` + `spike_needed` + guard | `check_missing_artifacts` (was `check_spike_needed`) | `detect_children` |
  | `select_obligation_pre_implement` | `check-gate` `structured_proof` + guard | `check_proof_defer_or_implement` (was `check_proof_gate_before_implement`) | `check_proof_defer_or_implement` |
  | `select_obligation_post_size_review` (new) | `next-obligation` `PROOF:*` + `spike_needed` + guard | `check_reconcile_needed` | `recheck_after_size_review` |

- **Retargets** (the 22 removed states' inbound edges from surviving states):

  | Surviving state | Edge | Removed target | New target |
  |---|---|---|---|
  | `check_parent_resolved_post_size_review` | `on_no`, `on_error` | `check_spike_needed_before_skip` | `select_obligation_post_size_review` |
  | `dispatch_pre_deferral_remedy` | `on_yes` | `run_spike` | `refine_current` |
  | `select_obligation_post_refine` | `_` | `check_spike_needed` | `check_missing_artifacts` |
  | `select_obligation_pre_implement` | `_`, `_error` | `check_proof_gate_before_implement` | `check_proof_defer_or_implement` |

- **Proof gate.** `check_proof_defer_or_implement` is the only predecessor of
  `implement_current` and the only proof stage. The only route into implementation is
  a selector → `check_proof_defer_or_implement`. After ENH-3610, `route_refine_success`
  (`READY`) → `check_passed` → `select_obligation_pre_implement` is one of those routes.
- **Pre-deferral `spike` remedy.** `dispatch_pre_deferral_remedy`'s `spike` branch drops its
  `spike-runs-<ID>` increment and its `autodev-pre-spike-readiness.txt` write, keeps the
  budget check (counter >= 2 → exit 1 → `reconcile_current`), adds the lifetime-cap check
  (below), and routes `on_yes` → `refine_current`.
  - **Lifetime-cap check.** This leg must also exit 1 → `reconcile_current` when
    `refine_count` >= the lifetime cap. Use the same `refine-status` read and cap resolution as
    the shared re-entry guard. The leg runs late, on a low-readiness issue that has already
    been refined several times. Without the check, a child re-entered at its cap routes to
    `breakdown_issue`, so the issue is decomposed instead of deferred as
    `low_readiness`/`readiness_stagnated`. BUG-3614 is the same hazard on `DECISION` re-entry.
    This edge is new in this issue, so this issue closes it.
  - **Must drop the increment:** a counter bumped before the child runs makes a
  child spike's refutation see N=2 in `check_spike_budget` and defer as `decision_unresolved`,
  skipping BUG-3593's refute → decide step. **Accepted interim loss until ENH-3606** (which
  moves the whole pre-deferral remedy into `prepare-issue`): the child spikes on re-entry only
  if it reaches `done` with an open `structured_proof` gate, or if `spike_needed` is set in
  its low-outcome band. A `spike` remedy armed by the ambiguity heuristic alone gets another
  refine pass, not a spike. Update the state's comment ("Both remedies ... funnel back to
  `recheck_after_size_review`" no longer holds for the `spike` leg).
  - **Return path.** The `spike` leg now returns via `refine_current` →
    `count_repair_cycle_refine` → `route_refine_success` → `check_passed`, then through the
    selectors and full post-refine triage, not straight to `recheck_after_size_review`. The
    `autodev-pre-deferral-remedy-fired` marker (cleared only at `dequeue_next`) still stops a
    second arming. An issue that is still failing reaches `recheck_after_size_review` again and
    defers as `readiness_stagnated`/`low_readiness`. The updated comment must state this path.
- **Accepted interim loss: low-readiness `spike_needed` issues are no longer spiked.** Today
  autodev spikes a `spike_needed` issue at any readiness (Current Behavior). After this change
  the child spikes only behind `check_readiness.on_yes`, and `next-obligation` reports `PROOF`
  only when readiness passes. A low-readiness, low-outcome `spike_needed` issue therefore gets
  refine and reconcile passes but no spike, and defers as `low_readiness`/`readiness_stagnated`.
  Accepted until ENH-3606, alongside the pre-deferral `spike` remedy loss above. Record it in
  ENH-3606's scope when this lands. Do **not** widen the child's spike band in this issue:
  moving `check_spike_needed` ahead of `check_readiness` would spike low-readiness issues for
  the `recursive-refine` callers too. Unlike `check_proof_before_done`, no invariant requires
  that change.
- **Markers.** Autodev never writes `spike-runs-<ID>`. Its surviving consumers
  (`recheck_after_size_review`, `dispatch_pre_deferral_remedy`, the three selectors) only read
  it as the budget signal the child spends. Neither `resolve_issue` nor autodev resets it
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
| `check_proof_gate_before_implement` (`PROOF_SPIKE`) | Spike a high-scoring issue whose `structured_proof` gate is open and budget remains | MOVED | Child: `check_proof_before_done`. Via `check_passed.on_yes` the child's gate has already run; via the other four pre-implement sites, `select_obligation_pre_implement`'s `check-gate` probe re-enters the child |
| `dispatch_pre_deferral_remedy` `spike` leg | Spike a low-readiness issue before the `low_readiness` deferral (BUG-2803) | CHANGED (interim) | Routes to `refine_current` when budget and lifetime cap allow, else `reconcile_current`; the child spikes only on an open `structured_proof` gate at `done` or `spike_needed` in the low-outcome band. Full move in ENH-3606 |
| (new) child `check_proof_before_done` for `recursive-refine` callers | Reached `done` with an open `structured_proof` gate unspiked | CHANGED (intended) | Child spikes the gate before `done` for every caller (`recursive-refine` and its wrappers), not only autodev |
| `check_proof_gate_before_implement` (`PROOF_DEFER` / `PROOF_INFRA`) | Defer an open gate; defer on helper failure | PRESERVED | `check_proof_defer_or_implement` (unchanged, fail-closed) |
| `check_spike_needed` / `run_spike` / `route_spike_verdict` (readiness-passing issues) | Spike on `spike_needed`, four-way verdict routing (BUG-3593) | MOVED | Child's same-named states (already present) |
| `check_spike_needed` via `select_obligation_post_refine` `_` on `SCORES:readiness_below` | Spike a `spike_needed` issue whose readiness is below threshold | DROPPED (interim) | Nowhere: the child's spike band requires `check_readiness.on_yes`. Accepted until ENH-3606 |
| `run_spike` rate-limit handling | Wait up to 14400s, halt the run on exhaustion | MOVED | Child `run_spike` (ENH-3607) → `RETRYABLE_ERROR:rate_limited` → `finalize_rate_limited` |
| `check_spike_budget` → `resolve_decision` chain | Refuted spike → decide once, second refutation → `decision_unresolved` | MOVED | Child: `check_spike_budget` → `resolve_decision_pre_breakdown` / `record_decision_unresolved`; autodev sees `BLOCKED:decision_unresolved` → `ledger_child_stop` |
| `record_spike_inconclusive` / `mark_spike_no_verdict_infra` | Defer inconclusive; infra-skip no verdict | MOVED | Child's same-named states → `DEFERRED:spike_inconclusive` / `RETRYABLE_ERROR:infra` |
| `spike` / `decide` rescoring triplets + `recheck_after_decide` | Fresh scores after a spike or decision (BUG-3588) | MOVED | Child: `route_spike_verdict` `PROVEN` → `confidence_check` → `mark_evidence_absent_infra` on missing scores |
| `check_rearmed_spike_after_decide` | Re-spike once after a decision re-arms the spike | MOVED | Child: `check_spike_needed` with the shared `spike-runs-<ID>` budget (< 2) |
| `count_repair_cycle_spike` | Count a spike toward the FEAT-2751 stagnation backstop | PRESERVED | Every re-entry passes `count_repair_cycle_refine` |
| `check_spike_needed_before_skip` | Last spike chance before the post-size-review skip, at any readiness | CHANGED (narrowed) | `select_obligation_post_size_review` `PROOF:*` + `spike_needed` + guard → child re-entry, only when readiness passes and outcome is below threshold; the low-readiness case is dropped (row above) |
| `check_decide_rate_limited` | Halt the run on decide-oracle 429 exhaustion | MOVED | Child `check_decide_rate_limited` → `mark_rate_limit_infra` → `RETRYABLE_ERROR:rate_limited` (ENH-3607) |
| `snap_and_size_review` | Snapshot active IDs before a post-decision size review | DROPPED | Only reachable from removed states; the main path (`recheck_scores.on_no` → `run_size_review`) never took the snapshot |
| `autodev-pre-spike-readiness.txt` consumers | Plateau baseline for `check_reconcile_needed` | CHANGED | Uses `autodev-pre-readiness.txt` (pre-refine, written by `dequeue_next`) |

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`: remove 22 states, add
  `select_obligation_post_size_review`, `PROOF` routes, retargets, `init` / `dequeue_next` /
  `check_reconcile_needed` / `finalize_done` marker edits, `dispatch_pre_deferral_remedy`
  (drop the `spike-runs-<ID>` increment and the pre-spike snapshot write; add the lifetime-cap
  check to the `spike` leg; update its comment),
  the pre-implement selector's `check-gate` probe, and `record_reentry_exhausted`'s comment
  (stays `DECISION`-only)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`: `check_proof_before_done`;
  `check_decision_before_done.on_no`/`.on_error` retarget; `max_steps` 90 → 100 with a history
  comment; stale comments that cite autodev's
  removed states: `check_spike_needed` (ENH-3250 "mirrors autodev.yaml's
  check_spike_needed"), `run_spike` ("mirrors autodev.yaml's run_spike"),
  `check_missing_artifacts` (names the `select_obligation_post_refine → check_spike_needed`
  ladder), and the top-of-file topology map (add `check_proof_before_done` on the done edges)
- Stale comments: `little_loops.cli.issues.show` (ENH-2640), `little_loops.cli.issues.check_gate`
  (module docstring: autodev callers), `little_loops.issue_lifecycle` (deferral-reason comments),
  `scripts/little_loops/loops/oracles/resolve-decision.yaml:147` (comment cites autodev's
  `recheck_after_decide` chain; comment-only, the oracle's contract is untouched)
- `scripts/tests/data/loop_interpolation_baseline.json`: delete autodev's `check_spike_needed`
  and `check_spike_needed_before_skip` entries in the same commit. The ratchet forbids adding
  sites, so `check_proof_before_done`, `select_obligation_post_size_review` and the selectors'
  new guard code must not put `${context.run_dir}` inside a heredoc (class C). Pass paths
  through env vars or keep them in plain shell. The `check_reconcile_needed` entry's `count`
  drops 4 → 3 when the `spike_snap` line goes; the ratchet treats `count` as informational, so
  keep the entry.

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
- `test_autodev_decision_gate.py`: `select_obligation_pre_implement` route assertions
  (`_`/`_error` → `check_proof_gate_before_implement`, lines ~207–208; the graph walk at ~439;
  the path list at ~525) retarget to `check_proof_defer_or_implement`. The BUG-2654 class
  (~653–681) asserts that `check_spike_needed_before_skip` exists and is wired. Rewrite it
  against `select_obligation_post_size_review`, which is what now protects the post-size-review
  skip, and add a stays-deleted guard for the old state.
- `test_autodev_loop.py`, `test_rn_remediate.py` (parity docstrings), `test_show.py` (docstrings)
- `test_fsm_topology.py`: autodev −22 +1, child +1, each with a history comment
- New real-FSM tests:
  - a high-scoring issue with a `structured_proof` gate is spiked in the child, then
    implemented or deferred;
  - a high-scoring issue with a `structured_proof` gate reaching `select_obligation_pre_implement`
    via `reopen_waived` (or `recheck_scores`), i.e. not via a fresh child `done`, is re-entered
    and spiked by the child, not deferred as `blocked_by_gate` with budget unspent;
  - `spike-runs-<ID>` persists across autodev re-entries (the budget does not reset);
  - `dispatch_pre_deferral_remedy`'s `spike` leg leaves `spike-runs-<ID>` unchanged, and a
    subsequent child spike that is refuted still reaches `resolve_decision_pre_breakdown`;
  - `dispatch_pre_deferral_remedy`'s `spike` leg with `refine_count` at `max_refine_count`
    routes to `reconcile_current`, never `refine_current` (no `breakdown_issue`);
  - a `PROOF:absent` issue whose child cannot spike (`spike_attempted` set without
    `spike_completed`) is not re-entered: the selector passes `--skip PROOF` immediately;
  - a spikeable issue (`spike_needed` set, `spike_attempted` unset) that also declares a
    refuted Learning Test Registry target reads `PROOF:refuted` and is still re-entered once;
  - a `PROOF` issue the child can spike re-enters once; a second `PROOF` reading falls through
    via `--skip PROOF`, and an open gate is deferred as `blocked_by_gate`;
  - a high-scoring `structured_proof` issue whose `refine_count` is at `max_refine_count` is not
    re-entered (no `breakdown_issue`) and defers as `blocked_by_gate`;
  - a learning-test-only `PROOF:stale` / `PROOF:refuted` (no spike flags) never re-enters the
    child (`--skip PROOF` immediately);
  - the child's `check_proof_before_done` does not spike on `structured_open` or `prose`
    (token match, not exit code);
  - `recursive-refine` running the child on a high-scoring issue with an open
    `structured_proof` gate spikes it before `done` (pins the intended caller contract change);
  - child worst-case path (proof spike + refuted → decide) completes under `max_steps` without
    tripping `recurrent_window`;
  - a low-readiness `spike_needed` issue is not spiked by autodev (pins the accepted interim
    loss so ENH-3606 flips a known assertion).

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

`autodev.yaml:reopen_waived` -> `autodev.yaml:select_obligation_pre_implement` -> `cmd_check_gate` -> `autodev.yaml:refine_current` -> `refine-to-ready-issue.yaml:check_proof_before_done` -> `refine-to-ready-issue.yaml:run_spike`

`autodev.yaml:check_passed` -> `autodev.yaml:select_obligation_pre_implement` -> `autodev.yaml:check_proof_defer_or_implement` -> `cmd_check_gate` -> `autodev.yaml:implement_current`

## Impact

- **Priority**: P3, child of ENH-3608 (EPIC-3565 consolidation); last blocker for ENH-3605 and
  ENH-3600
- **Effort**: Large: −22/+1 autodev states, +1 child state, 6 edge retargets, marker cleanup
  across four surviving states
- **Risk**: High: removes autodev's spike path; the child proof gate and the fail-closed
  implement gate are the safety net
- **Accepted cost**: the old path spiked a high-scoring issue with one `/ll:spike` plus
  rescoring. A `PROOF` re-entry now runs a full child pass (format, `/ll:refine-issue`, wire,
  verify, confidence-check) before `check_proof_before_done`. That pass costs more tokens and
  time, spends one lifetime refine, and can move scores that already passed. The re-entry cap
  (one per issue) and the lifetime-cap guard bound it.
- **Caller contract change**: the child's new proof gate also applies to `recursive-refine`
  and its wrappers (`issue-refinement`, `sprint-build-and-validate`, `rn-build`,
  `eval-driven-development`). Those runs may now invoke `/ll:spike` (up to 2 per issue per
  child run) before `done`.
- **Breaking Change**: No (loop-internal)

## Implementation Sequencing

- **ENH-3613 has landed** (`dc3668f1d`). Its `finalize_done` edits are on `main`, so this
  issue's `autodev-spike-no-verdict.txt` removal there applies directly.
- **Two commits.**
  1. *Additive:* child `check_proof_before_done` + `max_steps` bump; `PROOF` probes in the
     existing selectors; new `select_obligation_post_size_review`, wired in but with the old
     states still present. Safe alone: when the child spikes a proof gate, autodev's
     `check_proof_gate_before_implement` sees `structured_satisfied`, and the shared
     `spike-runs-<ID>` cap bounds any double spend.
  2. *Subtractive:* delete the 22 states, apply the retargets, marker cleanup, the
     `dispatch_pre_deferral_remedy` change, stays-deleted guards, topology counts, baseline
     entries.

  The full suite passes after each commit.

## Parent Issue

Decomposed from ENH-3608: Remove autodev spike and decision routes and route on the child run
record. Lands after ENH-3609 and ENH-3610; uses the selectors and re-entry cap ENH-3610 adds. ENH-3599 holds the original design rationale.

### Carried over from ENH-3610 (review, 2026-09-26)

ENH-3610's review changed parts of the selector contract that this issue builds on:

- **`check_passed.on_yes` already goes to `select_obligation_pre_implement`** (ENH-3610). This
  issue's old `check_passed.on_yes` retarget row is removed. The pre-implement selector's
  `_`/`_error` retarget (→ `check_proof_defer_or_implement`) now covers `check_passed` too.
  Retargets: 7 → 6.
- **`record_reentry_exhausted` is a surviving autodev state.** ENH-3610 adds it; it is not one
  of the 22 removed here. It ledgers `<ID>  decision_unresolved` in `autodev-skipped.txt` and
  defers the issue with that reason. `DECISION_EXHAUSTED` targets it, not
  `record_decision_unresolved`, so removing `record_decision_unresolved` here does not affect
  the selectors. **Decided (2026-09-26 review):** `PROOF` uses the `--skip PROOF` fall-through;
  the fail-closed `check_proof_defer_or_implement` defers an open gate as `blocked_by_gate`.
  No `PROOF_EXHAUSTED` token; `record_reentry_exhausted` stays `DECISION`-only (its comment's
  "so ENH-3611 can reuse it for PROOF" is updated accordingly). Keep it in
  `AUTODEV_NOT_READY_STATES` when `record_decision_unresolved` is dropped from that list.
- **Selectors un-stage on re-entry.** On `DECISION` / `DECISION_EXHAUSTED`, ENH-3610's selectors
  remove the ID from `autodev-staged.txt` before routing away from implementation. `PROOF:*`
  re-entry must do the same; otherwise a staged issue that the re-entered child defers
  appears in `autodev-unverified.txt`. The new `select_obligation_post_size_review` needs this
  too: `recheck_after_size_review` stages the ID before its pass route.
- **Selector exit-code contract.** `check-flag` exit 2 falls through to `next-obligation`, whose
  exit 2 becomes `_error`. When `PROOF` routes are added, keep that ordering: the `DECISION`
  check before the `PROOF` check. The pre-implement selector's `check-gate` probe sits between
  them and falls through on any helper error.

## Scope Boundaries

- **In scope**: removing the 22 states listed in Current Behavior; the child's
  `check_proof_before_done`; `PROOF` routes and the third selector; the retargets; the marker
  changes above; stale comments; tests and docs.
- **Out of scope**: `oracles/resolve-decision.yaml`'s contract (its stale comment at :147 is
  in scope); the child's own spike states
  (they stay; `spike-gate.yaml` and `rn-remediate.yaml` also have same-named states that must
  survive, so scope state-name greps to `autodev.yaml`); ENH-3600's marker retirement;
  ENH-3605/ENH-3606 remedy moves (only their edges into removed states change here); restoring
  low-readiness `spike_needed` spikes (ENH-3606); moving the child's spike band ahead of
  `check_readiness`. ENH-3610's `DECISION` re-entry has the same lifetime-cap hazard (a capped
  issue re-entered for `DECISION` routes to `breakdown_issue`). BUG-3614 tracks it; it is not
  fixed here. (The new `dispatch_pre_deferral_remedy` → `refine_current` edge has the same
  hazard and **is** fixed here, because this issue creates that edge.)

## Acceptance Criteria

- [ ] No state in `autodev.yaml` runs `/ll:spike` or `oracles/resolve-decision`
- [ ] All 22 states are gone, with a stays-deleted guard each; no autodev edge targets a removed
  state; every retarget row holds (structural tests)
- [ ] `implement_current`'s only predecessor is the fail-closed `check_proof_defer_or_implement`;
  `MISSING` never reaches it
- [ ] A high-scoring issue with a `structured_proof` gate and spike budget left is spiked by the
  child before `done` (real-FSM test); the child never reaches `done` with that gate open and
  budget unspent
- [ ] No pre-implement site (`check_passed`, `recheck_scores`, `regate_after_atomic_remediation`,
  `reopen_waived`, `recheck_after_size_review`) defers an open `structured_proof` gate as
  `blocked_by_gate` while `spike_attempted` is unset, budget remains and the `PROOF` re-entry
  is unused (real-FSM test through a non-`check_passed` site)
- [ ] `PROOF` re-entry is capped at one per issue, is skipped outright when the child cannot
  spike, and the run terminates when the child cannot satisfy it (real-FSM test)
- [ ] No `PROOF` re-entry is attempted once `refine_count` >= `max_refine_count`; such an issue
  defers as `blocked_by_gate`, never `breakdown_issue` (real-FSM test)
- [ ] `dispatch_pre_deferral_remedy`'s `spike` leg never routes a lifetime-capped issue to
  `refine_current` (real-FSM test)
- [ ] Low-outcome selectors decide `PROOF` re-entry from the spike flags and guard, not the
  `PROOF:<sub_reason>`; a refuted registry target does not mask a spikeable issue (test)
- [ ] The child's `check_proof_before_done` spikes only on the `structured_proof` token; its
  worst-case path fits the raised `max_steps` without tripping `recurrent_window`
- [ ] The low-readiness `spike_needed` loss is recorded in the Behavior Parity table and pinned
  by a test
- [ ] Autodev never writes `spike-runs-<ID>` (including `dispatch_pre_deferral_remedy`); the
  budget persists across re-entries (real-FSM test); autodev no longer reads or writes
  `autodev-pre-spike-readiness.txt` or `autodev-spike-no-verdict.txt`
- [ ] `auto-refine-and-implement` and `oracles/resolve-decision` behavior unchanged, including
  `auto-refine-and-implement`'s `finalize` counts for a decision-unresolved stop; full suite
  passes
- [ ] `recursive-refine` callers' only behavior change is the child's pre-`done` proof spike,
  recorded in Behavior Parity and pinned by a test

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-26_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 51/100 → LOW

### Concerns
- Accepted interim behavior loss: a `spike` remedy armed only by the ambiguity heuristic gets another refine pass, not a spike, until ENH-3606.
- The child's new `check_proof_before_done` also fires on `check_missing_artifacts.on_yes`, spending the shared spike budget before wiring (accepted in the issue).

### Outcome Risk Factors
- Deep per-site complexity: rewiring control flow across three selectors (one new), a new child gate, and shared-budget/re-entry-cap semantics that interact with `spike-runs-<ID>`.
- Broad enumeration across 22 removed autodev states plus 6 retargets, marker cleanup in four surviving states, and comment/doc/baseline edits.
- Wide test rewrite surface (freshness, spike routing, check-gate, topology, builtin loops) with six new real-FSM tests; a missed inbound edge to a removed state would only surface via those tests.
- Consider landing in two steps (child gate + selectors first, state deletion second) to reduce blast radius.


## Session Log
- `/ll:confidence-check` - 2026-09-26T06:39:11 - `75e3d2d3-f8ce-4d8d-a1e4-0681793eb55f.jsonl`
- `/ll:verify-issues` - 2026-09-26T06:35:49 - `d85f5c48-f990-4ff7-8752-05eb266137ea.jsonl`
- `/ll:ready-issue` - 2026-09-26T06:26:39 - `73daee30-3ee0-41e2-828b-b6ae2b1d133e.jsonl`
