---
id: ENH-3615
type: ENH
title: Consolidate autodev rescoring, halt on size-review rate limit, write run records at ladder stops
priority: P3
status: open
discovered_by: manual
discovered_date: '2026-09-26'
decision_needed: false
blocks:
- ENH-3606
relates_to:
- ENH-3601
- ENH-3600
---

# ENH-3615: Consolidate autodev rescoring, halt on size-review rate limit, write run records at ladder stops

## Summary

A prep issue for ENH-3606. ENH-3606 moves autodev's second-pass ladder into
`prepare-issue.yaml`. This issue lands three parts of that work in `autodev.yaml` first,
while the ladder is still in place. None of them needs the wrapper, and each can be tested
against today's topology. That leaves ENH-3606 as mostly relocation.

1. **Shared rescoring path**: replace the `wire` / `reconcile` / `atomic` rescoring triplets
   with one chain that dispatches on an origin marker.
2. **`run_size_review` rate-limit halt**: `on_rate_limit_exhausted` goes to
   `finalize_rate_limited` instead of `dequeue_next`.
3. **Run records at ladder stops**: each state that writes a stop row to
   `autodev-skipped.txt` also writes a `prepare-issue` run record in the same action. A
   `refine-broke-down` reset at the ladder entry keeps those records from reading as
   `DECOMPOSED`.

Behavior stays the same except item 2, which is one of ENH-3606's accepted behavior
changes and now lands here.

## Current Behavior

- Three near-identical triplets (`clear_scores_before_X` → `rerun_confidence_after_X` →
  `check_scores_present_X`) differ only in entry point, successor and retry-marker name.

  | Origin | Entry predecessors | Successor |
  |---|---|---|
  | `wire` | `run_refine` (`next` / `on_error`) | `enqueue_or_skip` |
  | `reconcile` | `count_repair_cycle_reconcile`, `count_repair_cycle_refine_for_design` | `recheck_after_size_review` |
  | `atomic` | `remediate_oversized_atomic` (rerun state `rerun_confidence_after_atomic_remediation`) | `regate_after_atomic_remediation` |

  Every triplet sends its absent-score and error exits to `mark_scores_absent_infra`, and its
  rate-limit exit to `finalize_rate_limited`. Each rerun state repeats the
  `confidence-check-recheck` `pruning_profile`. Retry markers are
  `autodev-rescore-retry-<origin>-<ID>`, cleared by `dequeue_next`'s
  `rm -f autodev-rescore-retry-*-$CURRENT`.
- `run_size_review.on_rate_limit_exhausted: dequeue_next` drops the issue silently: no row,
  no halt. Every other slash state in the ladder halts through `finalize_rate_limited`.
- The ladder's stop rows carry no run record:
  - `recheck_after_size_review` writes `design_gate_failed`, `decision_unresolved`,
    `readiness_stagnated` and `low_readiness`;
  - `regate_after_atomic_remediation` writes `design_gate_failed` and `oversized_atomic`;
  - `record_reentry_exhausted` writes `decision_unresolved`.

  The only `prepare-issue` record for the pass is whatever the wrapper forwarded when
  `refine_current` returned (usually `READY` / `BLOCKED`).

## Expected Behavior

### 1. Shared rescoring path

- Each origin gets a one-line entry that writes `autodev-rescore-origin-<ID>`
  (`wire` | `reconcile` | `atomic`), then goes to the shared `clear_scores`. `run_refine`
  and `remediate_oversized_atomic` are slash states, so they need a thin shell pre-state.
  `count_repair_cycle_reconcile` and `count_repair_cycle_refine_for_design` can write the
  marker inline.
- The shared chain is `clear_scores` → `rerun_confidence` → `check_scores_present` →
  `route_after_rescore`:
  - `rerun_confidence` keeps `with_rate_limit_handling`, `on_rate_limit_exhausted:
    finalize_rate_limited`, and the `confidence-check-recheck` `pruning_profile` (declared
    once).
  - `check_scores_present` keeps the BUG-3588 freshness rules: it builds the retry marker
    name from the origin, so the names stay `autodev-rescore-retry-<origin>-<ID>`. First
    miss → `rerun_confidence`; second miss → `mark_scores_absent_infra`.
  - `route_after_rescore` reads the origin marker and routes `wire` → `enqueue_or_skip`,
    `reconcile` → `recheck_after_size_review` and `atomic` →
    `regate_after_atomic_remediation`. An unknown or missing origin, and `_error`, go to
    `mark_scores_absent_infra` (fail closed).
- `dequeue_next` removes `autodev-rescore-origin-<ID>` explicitly. The existing
  `autodev-rescore-retry-*` glob does not match it.

### 2. `run_size_review` rate-limit halt

`run_size_review.on_rate_limit_exhausted` → `finalize_rate_limited`. ENH-3606 later
retargets it to the wrapper's `mark_rate_limited`, which reaches the same halt.

### 3. Run records at ladder stops

- In the same action as each stop row above, after the `set-status`:

  ```bash
  ll-issues run-record write "$ID" --run-dir ${context.run_dir} --writer prepare-issue --legacy-class <class> || true
  ```

  | Row | `--legacy-class` | Token |
  |---|---|---|
  | `oversized_atomic`, `design_gate_failed`, `readiness_stagnated`, `low_readiness` | `gate_unmet` | `DEFERRED:gate_unmet` |
  | `decision_unresolved` (both writers) | `decision_unresolved` | `BLOCKED:decision_unresolved` |

  `resolved_by_subloop` rows get no record here. ENH-3606 gives that row a single writer
  (`recover_subloop_children`).
- `reopen_waived` clears the record it undoes (`run-record clear --writer prepare-issue`)
  next to its existing `grep -vxF "$ID  oversized_atomic"` removal.
- `recheck_scores` writes `0` to `refine-broke-down` before anything else. It is the only
  ladder entry reached with the flag at `1` (inner breakdown, no children, parent not
  resolved: `check_broke_down.on_yes` → `check_parent_resolved.on_no`). Nothing in autodev
  reads `refine-broke-down` after `copy_broke_down`, so the reset is safe. Without it,
  `outcome_from_legacy_class` rule 2 turns every stop record written later in the pass into
  `DECOMPOSED`.
- Nothing in autodev reads these records yet: the stop states still route to
  `dequeue_next`, and `route_refine_outcome` / `route_refine_success` read only right after
  `refine_current`. The next wrapper run's `clear_record` clears them. That is why this part
  is behavior-preserving. ENH-3606 then routes on them.

## Scope Boundaries

- **In scope**: the three items above, their tests, and the doc lines they change.
- **Out of scope** (all stay in ENH-3606):
  - moving any state into `prepare-issue.yaml`;
  - the single-writer rules for `autodev-staged.txt` and `resolved_by_subloop` rows. Today
    `recheck_scores`, `recheck_after_size_review`, `regate_after_atomic_remediation` and
    `reopen_waived` reach `check_proof_defer_or_implement` through
    `select_obligation_pre_implement` without passing `check_passed`, so dropping their
    staging appends now would stop staging those issues;
  - the `refine-terminal-class` sentinel on stop terminals (`dequeue_next` does not clear
    the sentinel, and nothing reads it on these paths before the move);
  - the atomic-remediation-failure `BLOCKED:quality` record;
  - `mark_ladder_error`, and deleting `mark_scores_absent_infra`.
- Do not change `refine-to-ready-issue.yaml` or `recursive-refine.yaml` (its states share
  names but are separate).

## Tests

- `scripts/tests/test_autodev_scores_freshness.py`: rewrite `PATHS` (:31) and its
  parametrized structural and behavioral tests (:44-70, :161-237) around the shared chain:
  - each origin's entry writes its marker and reaches `clear_scores`;
  - `route_after_rescore` routes each origin to its successor, and unknown or missing
    origin → `mark_scores_absent_infra`;
  - retry-marker names are unchanged per origin;
  - `test_dequeue_next_clears_retry_markers` also covers the origin marker.
- Structural: exactly one `clear_scores` / `rerun_confidence` / `check_scores_present` /
  `route_after_rescore`. No `clear_scores_before_*` / `rerun_confidence_after_*` /
  `check_scores_present_*` remains; add them to autodev's removed-states list.
- `run_size_review.on_rate_limit_exhausted == "finalize_rate_limited"`, with a real-FSM
  test that it halts the queue instead of advancing.
- Real-FSM, one case per stop row: the record token matches the table, and the ledger rows
  in `autodev-skipped.txt` are unchanged.
- Broke-down trap: inner breakdown with no children and an unresolved parent, then a
  `design_gate_failed` stop, records `DEFERRED:gate_unmet`, not `DECOMPOSED`.
- `reopen_waived` removes the `oversized_atomic` row and clears the record.
- Existing suites that pin the triplet names, updated in place:
  - `test_builtin_loops.py::TestAutodevLoop` (`rerun_confidence_after_wire` ~:9534-9590);
  - `test_autodev_decision_gate.py`;
  - `test_autodev_loop.py` (`TestRepairCycleCounterStates`);
  - `test_fsm_topology.py::test_autodev_topology` count, with a delta comment (9 triplet
    states → 4 shared + up to 2 origin pre-states).
- `scripts/tests/data/loop_interpolation_baseline.json`: re-key any entries for the renamed
  states in the same commit (`TestInterpSweepBaseline::test_completeness_guard`).

## Docs

- `docs/guides/LOOPS_REFERENCE.md`:
  - the autodev score-freshness / rescoring paragraphs;
  - `:579` (`run_size_review`);
  - add the rate-limit halt to the behavior-change notes.
- The autodev ASCII tree, where it names the triplets.

## Acceptance Criteria

- [ ] `autodev.yaml` has one rescoring chain (`clear_scores` → `rerun_confidence` → `check_scores_present` → `route_after_rescore`) that dispatches per origin through `autodev-rescore-origin-<ID>`; unknown or missing origin fails closed to `mark_scores_absent_infra`
- [ ] Retry-marker names (`autodev-rescore-retry-<origin>-<ID>`) and the BUG-3588 freshness behavior are unchanged; `dequeue_next` clears the origin marker
- [ ] `run_size_review` rate-limit exhaustion halts through `finalize_rate_limited`
- [ ] Every stop row written by `recheck_after_size_review`, `regate_after_atomic_remediation` and `record_reentry_exhausted` has a `prepare-issue` record matching the table, written in the same action; ledger rows are unchanged
- [ ] `recheck_scores` resets `refine-broke-down` to `0`; the broke-down trap test passes
- [ ] `reopen_waived` clears the record it undoes
- [ ] `auto-refine-and-implement` summary counts are unchanged in a real-FSM run except for the `run_size_review` halt

## Impact

- **Priority**: P3. It shrinks ENH-3606, whose outcome confidence was 46.
- **Effort**: Medium. About 9 states collapse to 6, 7 record-write lines are added, and the
  scores-freshness suite needs a test rewrite.
- **Risk**: Low to medium. It stays inside autodev's current topology. The records it adds
  are write-only until ENH-3606.
- **Breaking Change**: No public interface. One control-flow change: `run_size_review`
  rate-limit exhaustion halts the queue.

## Integration Map

- `scripts/little_loops/loops/autodev.yaml` (post-ENH-3611 anchors):
  - `dequeue_next` retry-marker clear ~:127-129;
  - `run_refine` ~:1046 and wire retry marker ~:1100;
  - `mark_scores_absent_infra` ~:1563, `recheck_scores` ~:1831, `run_size_review` ~:1878;
  - atomic retry marker ~:2246, `regate_after_atomic_remediation` ~:2267, `reopen_waived`
    ~:2447;
  - reconcile retry marker ~:2611, `recheck_after_size_review` ~:2632;
  - `record_reentry_exhausted`.
- `little_loops.run_record`:
  - `outcome_from_legacy_class` is first-match-wins, and rule 2 (`broke_down`) comes
    before the legacy class;
  - `record_token` maps `blocked` / `deferred` plus a legacy class to the suffixed tokens;
  - `run-record write` reads `refine-broke-down` and honors the outcome waiver.
- No change to `little_loops.run_record` or its CLI: `prepare-issue` is already in
  `WRITERS`.

## Implementation Steps

1. Add the tests first: shared-chain structure, origin dispatch, the size-review halt, the
   per-row record tokens and the broke-down trap. Confirm they fail.
2. Build the shared chain and origin entries, then delete the nine triplet states.
3. Retarget `run_size_review.on_rate_limit_exhausted`.
4. Add the record writes, the `reopen_waived` clear and the `recheck_scores` reset.
5. Update the existing suites, the topology count, the baseline JSON and the docs.
6. Run `ll-loop validate autodev` and `python -m pytest scripts/tests/`.

## Program Design

### Types

- `PreparationOutcome`: six-value Literal in `little_loops.run_record` (reused; the stop records use `deferred` and `blocked`)

### Signatures

- `outcome_from_legacy_class(legacy_class: str | None, broke_down: bool, thresholds_met: bool, status: str | None) -> PreparationOutcome` — maps each stop's `--legacy-class`; the `refine-broke-down` reset keeps rule 2 from firing
- `record_token(record: RunRecord | None) -> str` — yields `DEFERRED:gate_unmet` / `BLOCKED:decision_unresolved` for the new records

### Call Path

`autodev.yaml:count_repair_cycle_reconcile` -> `autodev.yaml:clear_scores` -> `autodev.yaml:rerun_confidence` -> `autodev.yaml:check_scores_present` -> `autodev.yaml:route_after_rescore` -> `autodev.yaml:recheck_after_size_review`

`autodev.yaml:recheck_after_size_review` -> `outcome_from_legacy_class` -> `record_token`

## Status

**Open** | Created: 2026-09-26 | Priority: P3
