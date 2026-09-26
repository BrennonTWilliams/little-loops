---
id: ENH-3615
type: ENH
title: Consolidate autodev rescoring, halt on size-review rate limit, write run records
  at ladder stops
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
confidence_score: 95
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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
   `refine-broke-down` reset in `copy_broke_down` keeps those records from reading as
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

- Each origin writes `autodev-rescore-origin-<ID>` (`wire` | `reconcile` | `atomic`)
  before the shared `clear_scores`:
  - `wire`: inline in `count_repair_cycle_wire`, which is `run_refine`'s only predecessor
    (`next` and `on_error`) and already a shell state. `run_refine.next` / `on_error` →
    `clear_scores`.
  - `reconcile`: inline in `count_repair_cycle_reconcile` and
    `count_repair_cycle_refine_for_design`, whose `next` / `on_error` → `clear_scores`.
  - `atomic`: one new shell state, `mark_rescore_origin_atomic`, between
    `remediate_oversized_atomic` (`next` / `on_error`) and `clear_scores`. Its predecessor
    `check_readiness_for_atomic_remediation` is a heredoc predicate, and
    `remediate_oversized_atomic` is a slash state, so neither can write the marker inline.
    `mark_rescore_origin_atomic.on_error` → `mark_scores_absent_infra`.
- The shared chain is `clear_scores` → `rerun_confidence` → `check_scores_present` →
  `route_after_rescore`:
  - `rerun_confidence` keeps `with_rate_limit_handling`, `on_rate_limit_exhausted:
    finalize_rate_limited`, and the `confidence-check-recheck` `pruning_profile` (declared
    once).
  - `check_scores_present` keeps the BUG-3588 freshness rules: it builds the retry marker
    name from the origin, so the names stay `autodev-rescore-retry-<origin>-<ID>`. First
    miss → `rerun_confidence`; second miss → `mark_scores_absent_infra`. A missing or
    unknown origin exits 3 → `mark_scores_absent_infra` before any retry marker is built
    (otherwise the name would be `autodev-rescore-retry--<ID>`).
  - `route_after_rescore` reads the origin marker, deletes it, and routes `wire` →
    `enqueue_or_skip`, `reconcile` → `recheck_after_size_review` and `atomic` →
    `regate_after_atomic_remediation`. An unknown or missing origin, and `_error`, go to
    `mark_scores_absent_infra` (fail closed). Deleting on read matters because one pass can
    rescore twice (for example `wire`, then `reconcile` through the pre-deferral remedy):
    a marker left behind would let an entry that forgot to write its own silently reuse
    the previous origin instead of failing closed.
  - Read the marker in shell (`cat`), not inside a `python3 -c` body, so the ENH-3338
    interpolation scanner finds no new site.
- `dequeue_next` also removes `autodev-rescore-origin-<ID>` explicitly, for passes that
  leave the chain through `mark_scores_absent_infra` or a rate-limit halt. The existing
  `autodev-rescore-retry-*` glob does not match it.

### 2. `run_size_review` rate-limit halt

`run_size_review.on_rate_limit_exhausted` → `finalize_rate_limited`. ENH-3606 later
retargets it to the wrapper's `mark_rate_limited`, which reaches the same halt. Rewrite
`run_size_review`'s comment (autodev.yaml:1881-1883), which still says exhaustion "skips
this issue and moves to the next queued one". `finalize_done`'s abandoned-inflight check
still reports the issue, because `autodev-inflight` is not cleared on this path.

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
- `record_reentry_exhausted` writes its record only in the `else` branch, next to the
  `set-status deferred`. Its ledger row is unconditional, but on an issue that is already
  `done` / `completed` / `cancelled` the record would read `CANCELLED` (rule 1 wins) or
  `BLOCKED:decision_unresolved` for a done issue. `recheck_after_size_review` and
  `regate_after_atomic_remediation` need no such guard: a done or cancelled issue leaves
  both through `resolved_by_subloop` before any stop row.
- `reopen_waived` clears the record it undoes (`run-record clear --writer prepare-issue`)
  next to its existing `grep -vxF "$ID  oversized_atomic"` removal.
- `copy_broke_down` writes `0` to `refine-broke-down` right after copying it to
  `autodev-broke-down`. Without the reset, `outcome_from_legacy_class` rule 2 turns every
  stop record written later in the pass into `DECOMPOSED`. Why here and not at
  `recheck_scores`: `recheck_scores` is not the only ladder entry that can see the flag at
  `1`. `route_refine_success` fails open to `check_passed` on `MISSING` / `_` / `_error`
  (a `|| true` record write can fail after a real breakdown), and from `check_passed` an
  issue reaches `record_reentry_exhausted` (selectors' `DECISION_EXHAUSTED`) and
  `recheck_after_size_review` (`select_obligation_post_refine` → `check_missing_artifacts` →
  `run_wire` → … → `enqueue_or_skip`) without passing `recheck_scores`. Every successful
  `refine_current` passes `copy_broke_down`, and nothing reads `refine-broke-down` after it:
  `route_refine_success` reads the saved record, and `check_broke_down` reads
  `autodev-broke-down`. A re-entry through `refine_current` (selector `DECISION` / `PROOF`)
  re-runs the child, which rewrites the flag, and passes `copy_broke_down` again.
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
  - each origin's entry writes its marker and reaches `clear_scores`
    (`count_repair_cycle_wire`, `count_repair_cycle_reconcile`,
    `count_repair_cycle_refine_for_design`, `mark_rescore_origin_atomic`);
  - `route_after_rescore` routes each origin to its successor and deletes the marker;
    unknown or missing origin → `mark_scores_absent_infra`;
  - `check_scores_present` with a missing or unknown origin exits 3 and creates no retry
    marker;
  - two rescorings in one pass (`wire`, then `reconcile`) each route to their own
    successor;
  - retry-marker names are unchanged per origin;
  - `test_dequeue_next_clears_retry_markers` also covers the origin marker.
- Structural: exactly one `clear_scores` / `rerun_confidence` / `check_scores_present` /
  `route_after_rescore`. No `clear_scores_before_*` / `rerun_confidence_after_*` /
  `check_scores_present_*` remains. There is no shared autodev removed-states list: add a
  `_RESCORE_TRIPLET_STATES_REMOVED` tuple in `test_autodev_decision_gate.py` next to
  `_DECISION_STATES_REMOVED` / `_SPIKE_STATES_REMOVED`, with the same "gone" and "no edge
  targets it" tests.
- `run_size_review.on_rate_limit_exhausted == "finalize_rate_limited"` (structural). No
  real-FSM test: reaching `on_rate_limit_exhausted` means going through the short-tier
  retries and the 21600s long-wait budget, and the executor's exhaustion routing is already
  covered in `test_fsm_executor.py`.
- Real-FSM (the mock-`action_runner` `FSMExecutor` harness in
  `test_autodev_decision_gate.py`, `_run_decision_chain`), one case per stop row: the record
  token matches the table, and the ledger rows in `autodev-skipped.txt` are unchanged.
- `record_reentry_exhausted` on an already `done` or `cancelled` issue writes the ledger row
  and no record.
- Broke-down trap, two cases, both recording `DEFERRED:gate_unmet`, not `DECOMPOSED`:
  - inner breakdown with no children and an unresolved parent, then a `design_gate_failed`
    stop;
  - `refine-broke-down` at `1` with a `MISSING` record (`route_refine_success` →
    `check_passed`), then a stop.
- `reopen_waived` removes the `oversized_atomic` row and clears the record.
- Existing suites that pin the triplet names, updated in place:
  - `test_builtin_loops.py` (56 references between :6449 and :9115);
  - `test_autodev_decision_gate.py` (including `count_repair_cycle_reconcile.next ==
    "clear_scores_before_reconcile"` at :864-865);
  - `test_fsm_topology.py::test_autodev_topology` count, with a delta comment (9 triplet
    states → 4 shared + 1 origin pre-state, net −4).
  - `test_autodev_loop.py::TestRepairCycleCounterStates` does not name the triplets; re-run
    it, since the counter states' actions change.
- `scripts/tests/data/loop_interpolation_baseline.json` has no entries for these states. The
  scanner only flags interpolation inside Python bodies, so as long as the origin is read in
  shell, no baseline change is needed.

## Docs

- `docs/guides/LOOPS_REFERENCE.md`:
  - the autodev score-freshness / rescoring paragraphs, including the long paragraph at
    `:1103`, which names all three `rerun_confidence_after_*` states;
  - `:593` (`run_size_review`);
  - add the rate-limit halt to the behavior-change notes.
- The autodev ASCII tree (`LOOPS_REFERENCE.md` ~:1059-1088), where it names the triplets.
- Comments in `autodev.yaml` that name the triplet states: :127, :1048, :1069, :1093,
  :1905, :2108-2109, :2215, :2239, :2575, :2604 (pre-change line numbers).

## Acceptance Criteria

- [ ] `autodev.yaml` has one rescoring chain (`clear_scores` → `rerun_confidence` → `check_scores_present` → `route_after_rescore`) that dispatches per origin through `autodev-rescore-origin-<ID>`; `route_after_rescore` deletes the marker after reading it; unknown or missing origin fails closed to `mark_scores_absent_infra` in both `check_scores_present` and `route_after_rescore`
- [ ] The only new origin state is `mark_rescore_origin_atomic`; `wire` and `reconcile` write the marker inline in their `count_repair_cycle_*` states
- [ ] Retry-marker names (`autodev-rescore-retry-<origin>-<ID>`) and the BUG-3588 freshness behavior are unchanged; `dequeue_next` clears the origin marker
- [ ] `run_size_review` rate-limit exhaustion halts through `finalize_rate_limited`, and its comment describes the halt
- [ ] Every stop row written by `recheck_after_size_review`, `regate_after_atomic_remediation` and `record_reentry_exhausted` has a `prepare-issue` record matching the table, written in the same action; ledger rows are unchanged
- [ ] `record_reentry_exhausted` writes no record when the issue is already `done` / `completed` / `cancelled`
- [ ] `copy_broke_down` resets `refine-broke-down` to `0` after copying it; both broke-down trap cases pass
- [ ] `reopen_waived` clears the record it undoes
- [ ] No `autodev.yaml` comment or `LOOPS_REFERENCE.md` line names a removed triplet state

## Impact

- **Priority**: P3. It shrinks ENH-3606, whose outcome confidence was 46.
- **Effort**: Medium. Nine states collapse to five, 7 record-write lines are added, and the
  scores-freshness suite needs a test rewrite.
- **Risk**: Low to medium. It stays inside autodev's current topology. The records it adds
  are write-only until ENH-3606.
- **Breaking Change**: No public interface. One control-flow change: `run_size_review`
  rate-limit exhaustion halts the queue.

## Integration Map

- `scripts/little_loops/loops/autodev.yaml` (post-ENH-3611 anchors):
  - `dequeue_next` retry-marker clear ~:127-129;
  - `copy_broke_down` ~:655 (reset), `route_refine_success` ~:670 (fail-open to
    `check_passed`);
  - `record_reentry_exhausted` ~:962 (record in the `else` branch);
  - `count_repair_cycle_wire` ~:1035, `run_refine` ~:1046 and wire retry marker ~:1100;
  - `mark_scores_absent_infra` ~:1563, `recheck_scores` ~:1831, `run_size_review` ~:1878
    (comment ~:1881-1883);
  - `check_readiness_for_atomic_remediation` ~:2171, `remediate_oversized_atomic` ~:2192;
  - atomic retry marker ~:2246, `regate_after_atomic_remediation` ~:2267, `reopen_waived`
    ~:2447;
  - `count_repair_cycle_refine_for_design` ~:2494, `count_repair_cycle_reconcile` ~:2533;
  - reconcile retry marker ~:2611, `recheck_after_size_review` ~:2632.
- `little_loops.run_record`:
  - `outcome_from_legacy_class` is first-match-wins, and rule 2 (`broke_down`) comes
    before the legacy class;
  - `record_token` maps `blocked` / `deferred` plus a legacy class to the suffixed tokens;
  - `run-record write` reads `refine-broke-down` and honors the outcome waiver.
- No change to `little_loops.run_record` or its CLI: `prepare-issue` is already in
  `WRITERS`.

## Implementation Steps

1. Add the tests first: shared-chain structure, origin dispatch and marker consumption, the
   size-review halt, the per-row record tokens, the done/cancelled `record_reentry_exhausted`
   case and both broke-down trap cases. Confirm they fail.
2. Build the shared chain, the inline origin writes and `mark_rescore_origin_atomic`, then
   delete the nine triplet states.
3. Retarget `run_size_review.on_rate_limit_exhausted` and rewrite its comment.
4. Add the record writes, the `reopen_waived` clear and the `copy_broke_down` reset.
5. Update the existing suites, the topology count, the `autodev.yaml` comments that name
   the triplets, and the docs.
6. Run `ll-loop validate autodev` and `python -m pytest scripts/tests/`.

## Program Design

### Types

- `PreparationOutcome`: six-value Literal in `little_loops.run_record` (reused; the stop records use `deferred` and `blocked`)

### Signatures

- `outcome_from_legacy_class(legacy_class: str | None, broke_down: bool, thresholds_met: bool, status: str | None) -> PreparationOutcome` — maps each stop's `--legacy-class`; the `copy_broke_down` reset keeps rule 2 from firing, and writing `record_reentry_exhausted`'s record only on the deferral branch keeps rule 1 from firing
- `record_token(record: RunRecord | None) -> str` — yields `DEFERRED:gate_unmet` / `BLOCKED:decision_unresolved` for the new records

### Call Path

`autodev.yaml:count_repair_cycle_reconcile` -> `autodev.yaml:clear_scores` -> `autodev.yaml:rerun_confidence` -> `autodev.yaml:check_scores_present` -> `autodev.yaml:route_after_rescore` -> `autodev.yaml:recheck_after_size_review`

`autodev.yaml:recheck_after_size_review` -> `outcome_from_legacy_class` -> `record_token`

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-26T21:43:19 - `8744a6bb-eecc-4dde-822b-a123b4bb673c.jsonl`
- `/ll:confidence-check` - 2026-09-26T21:19:03 - `5e32a00e-dc7e-43b0-801a-5a85182b8f1a.jsonl`
