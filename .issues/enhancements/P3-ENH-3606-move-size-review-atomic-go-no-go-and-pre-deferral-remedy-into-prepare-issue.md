---
id: ENH-3606
type: ENH
title: Move size-review/atomic, go/no-go and pre-deferral remedy into prepare-issue
priority: P3
status: open
discovered_by: issue-size-review
discovered_date: '2026-09-26'
decision_needed: false
blocked_by:
- ENH-3605
blocks:
- ENH-3600
relates_to:
- ENH-3590
- ENH-3577
parent: ENH-3601
---

# ENH-3606: Move size-review/atomic, go/no-go and pre-deferral remedy into prepare-issue

## Summary

Second half of ENH-3601 (Option B). With the `prepare-issue` wrapper in place (ENH-3605), move
the remaining second-pass states out of `autodev.yaml` so it owns only the queue: size-review /
atomic remediation, go/no-go, and pre-deferral remedy. The go/no-go trigger stays the existing
deterministic `deferred_reason: oversized_atomic` predicate, unchanged (widening it with a risk
signal is a separate follow-up).

## Parent Issue

Decomposed from ENH-3601: Move autodev second-pass preparation routing into a preparation controller.
See the parent for the decision rationale, research findings and inventories; the items below
are the D2 share.

## Current Behavior

After ENH-3605, `autodev.yaml` still owns the size-review/atomic, go/no-go and pre-deferral
remedy states, plus the `*_atomic` rescoring triplet, so autodev is not yet queue-only.

## Expected Behavior

Those states live in `prepare-issue.yaml`, the `*_atomic` triplet folds into the shared
rescoring path, and `autodev.yaml` contains only queue logic. Terminals map to the six-value
`PreparationOutcome` and each writes a `writer: prepare-issue` run record.

## Scope Boundaries

- **In scope**: moving the listed size-review, go/no-go and pre-deferral states and their tests/docs.
- **Out of scope**: widening the go/no-go trigger with a risk signal (separate follow-up);
  removing legacy sentinels (ENH-3600); new `PreparationOutcome` values.

## Scope

- Move from `autodev.yaml` into `prepare-issue.yaml`:
  - **pre-deferral remedy**: `check_pre_deferral_remedy`, `dispatch_pre_deferral_remedy`
    (markers `autodev-pre-deferral-remedy.txt`, `autodev-pre-deferral-remedy-fired`)
  - **size-review/atomic**: `detect_children`, `size_review_snap`, `check_broke_down`,
    `snap_and_size_review`, `run_size_review`, `enqueue_or_skip`, `check_size_review_ran_this_pass`,
    `check_guard2_verdict`, `check_guard2_score_fallback`, `check_readiness_for_atomic_remediation`,
    `remediate_oversized_atomic`, `regate_after_atomic_remediation`, `recheck_after_size_review`,
    `count_repair_cycle_size_review`
  - **go/no-go**: `check_go_no_go_eligible`, `run_go_no_go`, `check_go_no_go_waiver`,
    `reopen_waived` (only for `deferred_reason: oversized_atomic`)
  - shared: `recheck_scores`, remaining `count_repair_cycle_*`, and the `*_atomic` rescoring
    triplet folded into ENH-3605's shared rescoring path
- Terminal mapping stays within the six-value `PreparationOutcome`: go/no-go escalation and
  `oversized_atomic` deferral → `deferred`; atomic-remediation failure → `blocked`; breakdown →
  `decomposed`. Sentinels autodev reads stay written until ENH-3600.
- Result: `autodev.yaml` contains no wire/reconcile/design-remedy/pre-deferral/size-review/go-no-go states.
- Rate-limit handling on skill states (`run_size_review`, go/no-go) uses the fragment and routes
  exhaustion to a wrapper-local `retryable_error` terminal.

## Tests (in this child)

- Move/rewrite the `TestAutodevLoop` second-pass cluster in `test_builtin_loops.py`
  (~:8095-8920: `test_recheck_after_size_review_*`, `test_check_guard2_*`,
  `test_go_no_go_escalation_chain_shape`, `test_check_go_no_go_eligible_one_shot_and_reason_scoped`,
  `test_reopen_waived_reopens_stages_and_rearms_inflight`, `test_enqueue_or_skip_*`,
  `test_pre_deferral_remedy_*`); `TestRecheckAfterSizeReview*` and
  `TestRegateAfterAtomicRemediationDesignGateBranch` in `test_autodev_loop.py`;
  `TestGuard2VerdictBypass` in `test_autodev_decision_gate.py`; `test_go_no_go_skill.py:42` docstring.
- Re-check `TestMr11MarkerSet`, `TestSubLoopStateTimeoutAudit`, and `loop_interpolation_baseline.json`
  entries (`enqueue_or_skip`, `recheck_scores`) for the moved states.
- Pattern: `TestRecursiveRefineLoop` second-pass tests (~:9887-10056) and
  `test_rn_decompose.py:78` for the `on_rate_limit_exhausted` routing.
- Go/no-go trigger unchanged: existing predicate tests pass against the moved states.

## Docs (in this child)

- `skills/go-no-go/SKILL.md:402` and `skills/audit-loop-run/SKILL.md:271` re-anchored to
  `prepare-issue`; regenerate mirrors (`ll-adapt --host <gemini|kimi-code|qwen> --apply`).
- `docs/reference/DEFERRAL_CODES.md:24` (Source citations), `docs/reference/CLI.md`
  (`:2318`, `:2334`), `docs/reference/API.md:4662-4678`, `docs/guides/LOOPS_REFERENCE.md`
  (BUG-2734/BUG-3390 go/no-go and pre-deferral/`recheck_after_size_review` paragraphs).
- Comments citing moved states: `cli/issues/show.py:148`, `loops/rn-refine.yaml:419,500`.

## Acceptance Criteria

- [ ] `autodev.yaml` has no wire/reconcile/design-remedy/pre-deferral/size-review/go-no-go states
- [ ] All five rescoring triplets are gone from autodev; `prepare-issue` has one shared rescoring path
- [ ] Go/no-go trigger is the documented, deterministic `oversized_atomic` predicate, unchanged
- [ ] Every `prepare-issue` terminal (including the new ones) writes a `writer: prepare-issue` run record
- [ ] Moved behavioral suites pass; BUG-3603 invariant still passes

## Impact

- **Priority**: P3 - completes the ENH-3601 decomposition and unblocks ENH-3600
- **Effort**: Large - ~20 states plus a large test/doc migration
- **Risk**: Medium - go/no-go and atomic-remediation routing are subtle; mitigated by leaving the trigger predicate unchanged and reusing existing behavioral suites
- **Breaking Change**: No

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- **Files to modify**: `scripts/little_loops/loops/autodev.yaml` (states in Scope; ~:1013 `snap_and_size_review`, ~:1413 `detect_children`, ~:1490 `size_review_snap`, ~:1503 `check_broke_down`, ~:1882 `run_size_review`, ~:1905 `count_repair_cycle_size_review`, ~:1924 `enqueue_or_skip`, ~:2152-2242 guard2 / readiness / `remediate_oversized_atomic`, ~:2317 `regate_after_atomic_remediation`, ~:2436-2497 go/no-go states, ~:2682 `recheck_after_size_review`, ~:2930/2975 pre-deferral states); `scripts/little_loops/loops/prepare-issue.yaml` (created by ENH-3605).
- **Not named in Scope but coupled to it**: `recheck_scores` is listed as shared, yet `count_repair_cycle_refine`, `count_repair_cycle_spike`, `count_repair_cycle_refine_for_design` and `count_repair_cycle_reconcile` also write `autodev-repair-cycle-count.txt`, which `recheck_after_size_review` reads for its stagnation backstop (count ≥ 2 with confidence not above `autodev-pre-readiness.txt`). Any split of the `count_repair_cycle_*` family across the two loops must keep one shared counter file.
- **Exits from the moved cluster into states that stay in autodev** (ENH-3599 owns the spike/decide side): `recheck_after_size_review` and `regate_after_atomic_remediation` (on_yes) → `decide_current`; `check_decision_before_size_review` → `resolve_decision`; `dispatch_pre_deferral_remedy` (on_yes) → `run_spike`; `check_parent_resolved*` → `recover_subloop_children`; `detect_children` (on_yes) → `enqueue_children`. `enqueue_children`, `recover_subloop_children` and `dequeue_next` mutate the shared queue file. These edges need a defined destination inside `prepare-issue` once autodev is queue-only.
- **Acceptance-criterion dependency**: "All five rescoring triplets are gone from autodev" covers `decide` and `spike` as well as `wire`, `reconcile`, `atomic`; the `decide` and `spike` triplets sit with states owned by ENH-3599 (open). The criterion is only satisfiable if ENH-3599 lands first (it is a transitive blocker via ENH-3605).
- **Size-review sentinels**: `autodev-pre-ids.txt` / `-post-ids.txt` / `-diff-ids.txt` / `-new-children.txt` (written by `snap_and_size_review`, `size_review_snap`, `detect_children`, `enqueue_or_skip`, `recover_subloop_children`); `autodev-size-review-ran-this-pass` (set by `count_repair_cycle_size_review`, read by `check_size_review_ran_this_pass`, cleared by `dequeue_next`); `captured.size_review_output` feeds `check_guard2_verdict` / `check_guard2_score_fallback` through `evaluate.source`. Design-remedy state: `autodev-atomic-design-remedy-pending` (written by `regate_after_atomic_remediation`, consumed by `check_atomic_design_remedy`), `autodev-design-remedy-attempted-<ID>`, `autodev-pre-deferral-remedy.txt` / `-fired` (written by `recheck_after_size_review`, cleared by `dequeue_next`), `autodev-go-no-go-attempted-<ID>` (per-issue, never cleared — one-shot). `reopen_waived` re-arms `autodev-inflight`, which `dequeue_next` and most resolving states also touch.
- **Terminal mapping constraint**: `outcome_from_legacy_class` (`run_record.py`) maps `spike_inconclusive`/`gate_unmet` → `deferred`, `decision_unresolved`/`proposal_unsound`/`quality` → `blocked`, `infra` → `retryable_error`, `broke_down` → `decomposed`, status `cancelled` → `cancelled`. It has no dedicated branch for go/no-go escalation, `oversized_atomic` deferral or atomic-remediation failure; the run-record CLI accepts `--legacy-class` only from the existing six `LEGACY_CLASSES`, so the Scope's terminal mapping (go/no-go and `oversized_atomic` → `deferred`, atomic failure → `blocked`) has to be reachable through those classes or the CLI's outcome derivation, without adding a seventh `PreparationOutcome` value (out of scope). `--child-ids` overrides child derivation (`derive_child_ids` otherwise scans `parent:` frontmatter).
- **Rate-limit constraint**: `run_size_review` currently uses `with_rate_limit_handling` with `on_rate_limit_exhausted` → `dequeue_next`, unlike the other 11 sites that go to `finalize_rate_limited`. Inside a wrapper, exhaustion needs a wrapper-local terminal writing `retryable_error` (legacy class `infra`). `rn-decompose.yaml` `run_size_review` → `rate_limit_diagnostic` (fragment `subloop_rate_limit_diagnostic`, `lib/common.yaml`) is the existing sub-loop-side shape; `test_rn_decompose.py` pins it. Note the child loop's own slash-command states carry no rate-limit fragment.
- **Tests to relocate** (state-name hit counts at research time): `test_builtin_loops.py` (~371 hits; `TestAutodevLoop` from ~:6643), `test_autodev_decision_gate.py` (~128; `TestCheckDecisionBeforeSizeReviewStructural` ~:334, others), `test_autodev_loop.py` (~75; classes `TestCheckGuard2VerdictPattern` :106, `TestCheckGuard2ScoreFallback` :150, `TestRecheckAfterSizeReview*` :497/:571/:715/:807, `TestPreDeferralRemedyContradictionExemption` :850, `TestRegateAfterAtomicRemediationDesignGateBranch` :917, `TestRecheckScoresDesignGateEndToEnd` :1056), `test_autodev_scores_freshness.py` (~12), `test_rn_decompose.py` (~27), `test_loops_recursive_refine.py` (~14), `test_spike_verdict_routing.py`, `test_go_no_go_skill.py`, `test_ll_issues_check_gate.py`. Topology count pin: `test_fsm_topology.py::TestAutodevSmoke::test_autodev_topology` (~:233-261).
- **Docs/comments citing moved states** (beyond those in Docs): `commands/reconcile-issue.md` (~:368), `docs/reference/API.md` (~:4681), `docs/reference/DEFERRAL_CODES.md` (~:27), `docs/guides/LOOPS_REFERENCE.md` (~:1049-1176), `docs/reference/COMMANDS.md`; mirrors of `skills/go-no-go` and `skills/audit-loop-run` under `.gemini/`, `.kimi-code/`, `.qwen/` regenerate via `ll-adapt`. Some `autodev.yaml:NNN` line citations in test docstrings (`test_builtin_loops.py` ~:3759, ~:8957; `test_autodev_decision_gate.py` ~:409) look stale and are unverified.

### Conventions in Force

- State-move tests: extracted-loop suites live in their own file and assert states by `data["states"][name]` (`test_rn_decompose.py`); source loops assert absence via a `REMOVED_INLINE_STATES` parametrized test (`TestIssueRefinementSubLoop`, ~`test_builtin_loops.py:1323`).
- Baseline JSON entries are keyed `(file, state, var, class)` and must be moved in the same commit as the state (`TestInterpSweepBaseline::test_completeness_guard`).
- Mirror gates after skills/README edits: `test_adapters.py` (~:1176-1203) and `test_packaging_duplicate_files.py` (~:22); docs-audience gate (`test_docs_audience_gate.py`) forbids `scripts/tests/` and `scripts/little_loops/` path citations in `docs/guides`, `docs/reference`, `skills/`, `commands/`.
- No existing test spans the whole autodev graph for "no wire/reconcile/design/pre-deferral/size-review/go-no-go states"; the "autodev is queue-only" acceptance criterion needs an explicit absence assertion of the `REMOVED_INLINE_STATES` shape.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — builds `SKILL_BREAKDOWN` from the reason column of `autodev-skipped.txt` (~:1118-1133); `oversized_atomic`/`decomposed` reasons appear there. Ledger writers must keep writing `ID  <reason>` lines until ENH-3600 [Agent 1/2]
- `scripts/little_loops/loops/autodev.yaml` `finalize_done` (~:3066-3129) parses `autodev-skipped.txt` by reason substring (`refine_failed_infra`, `already_`, `blocked_by_unmet`, `notstarted_`); `oversized_atomic`/`decomposed`/`design_gate_failed` fall into the generic Skipped bucket. `reopen_waived` (~:2511-2514) edits the ledger with `grep -vxF "$ID  oversized_atomic"` — line-exact format coupling [Agent 2]
- `scripts/little_loops/loops/recursive-refine.yaml` — has its **own** `size_review_snap`, `check_broke_down`, `recheck_scores`, `enqueue_or_skip`, `detect_children`; name collision only, do not touch or count as moved. `rn-decompose.yaml` has its own `run_size_review` (`size_review_snap_$${ID}.json` artifact) [Agent 1]
- `scripts/little_loops/cli/issues/run_record.py` + `scripts/little_loops/run_record.py` — `outcome_from_legacy_class` is first-match-wins (`cancelled` → `broke_down` → `infra` → `decision_unresolved`/`proposal_unsound`/`quality` → `spike_inconclusive`/`gate_unmet` → thresholds). Reachable terminal mapping without a 7th outcome: go/no-go escalation and `oversized_atomic` → `--legacy-class gate_unmet` (loses reason in `legacy_class`; `deferred_reason` frontmatter via `ll-issues set-status --reason oversized_atomic` still carries it); atomic-remediation failure → `--legacy-class quality`; breakdown → write `1` to shared `refine-broke-down` (CLI `_read_broke_down`) [Agent 2]
- `scripts/little_loops/cli/issues/check_readiness.py` (`--honor-waiver`, `outcome_gate_waived`), `show.py:147-158`/`:296`, `deferred_triage.py:25` (`_REASON_RANK`), `set_status.py` (`DeferReason` validation), `issue_lifecycle.py:83` (`OVERSIZED_ATOMIC`), `check_gate.py:4` docstring (names `recheck_after_size_review`), `issue_manager.py:1230` comment — consumers of `deferred_reason`/moved-state names; no code change, comments may go stale [Agent 1/2]
- Rate-limit: `run_size_review` currently routes `on_rate_limit_exhausted: dequeue_next` (~:1882-1903) while `run_go_no_go` routes to `finalize_rate_limited` (~:2486, pinned `test_builtin_loops.py:8254-8258`). Inside the wrapper both need a wrapper-local `retryable_error` terminal; `subloop_rate_limit_diagnostic` (`lib/common.yaml:446`) needs `operation` via `with:` and `${context.issue_id}` [Agent 2]
- Queue coupling: `enqueue_children`, `recover_subloop_children`, `dequeue_next` mutate `autodev-queue.txt`; `detect_children`/`enqueue_or_skip`/`recover_subloop_children` write `autodev-new-children.txt` read by `check_broke_down`/`enqueue_children`/`ll-issues finalize-decomposition --children-file`. Nothing stops a child writing the parent queue (shared `run_dir` copy), but `dequeue_next` must remain sole cleaner of `autodev-size-review-ran-this-pass` and `autodev-pre-deferral-remedy*` [Agent 2]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/DEFERRAL_CODES.md` — additionally `:25` (`oversized_atomic` cites `remediate_oversized_atomic`) and `:26` (`readiness_stagnated` cites `recheck_after_size_review`) [Agent 2]
- `docs/reference/CLI.md` — additionally `:3090-3095` (`deferred-triage` "autodev's not-ready exits" + rank order), `:2403-2438` (run-record section; new terminals), `:2884` (`--honor-waiver`) [Agent 2]
- `docs/guides/LOOPS_REFERENCE.md` — additionally `:1035-1037` (pre-dequeue flow), `:1069-1072` (state-graph diagram with `check_guard2_verdict`/`recheck_after_size_review`), `:1087` (pre-deferral/`oversized_atomic`/go-no-go paragraph), `:579` (`run_size_review` with `with_rate_limit_handling`; confirm which loop). `:1128` covers `recursive-refine`'s own states — likely no change [Agent 2]
- `docs/ARCHITECTURE.md:672`, `:821` — go/no-go/size-review mentions (unread; check) [Agent 2]
- `docs/reference/ISSUE_TEMPLATE.md:916` (`missing_artifacts` "before attempting size-review") [Agent 2]
- `skills/go-no-go/SKILL.md:402` mirrors at `.gemini/`, `.kimi-code/`, `.qwen/skills/go-no-go/SKILL.md:401` regenerate via `ll-adapt`; `skills/audit-loop-run/SKILL.md` has no mirror hits. Incidental (no change): `skills/create-loop/loop-types.md`, `spike`, `verify-issue-loop`, `advise` [Agent 1/2]
- Comments: `cli/issues/deferred_triage.py:12,25`, `cli/issues/check_gate.py:4` [Agent 1]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_builtin_loops.py::TestAutodevLoop` beyond the listed ~8095-8920 range — hard break: `test_required_states_exist` (~:6659; lists `detect_children`, `size_review_snap`, `check_broke_down`, `recheck_scores`, `run_size_review`, `enqueue_or_skip`, `recheck_after_size_review`, `snap_and_size_review`, `check_guard2_verdict`, `check_readiness_for_atomic_remediation`, `remediate_oversized_atomic`, `rerun_confidence_after_atomic_remediation`, `regate_after_atomic_remediation`). Edge pins to retarget: `test_recheck_scores_on_*` (~:8890-8920), `test_check_decision_before_size_review_on_no/on_error` (~:8943-8960), `test_enqueue_or_skip_on_no_routes_to_decide_path_spike_gate` (:9051), `test_check_spike_needed_before_skip_on_error` (~:9084), `test_check_reconcile_needed` routing (~:9136), `test_triage_outcome_failure_on_error_routes_to_detect_children` (:9168), `test_check_missing_artifacts_on_no/on_error_routes_to_detect_children` (:9197, :9204), `test_snap_and_size_review_*` (~:9437-9473), `test_rerun_confidence_after_wire_next_routes_to_enqueue_or_skip` (~:9563-9573), the loop at :7970. Queue-adjacent: `test_enqueue_children_*` (~:8443-8716), `test_check_broke_down_on_no_routes_to_enqueue_or_skip` (:8510), `test_dequeue_next_clears_pre_deferral_remedy_files` (:8832), `test_dequeue_next_resets_contradiction_budget` (:8878); `TestAutodevRnImplementDeferralParity::test_autodev_not_ready_exit_matches_mark_deferred_shape` (~:9736; `recheck_after_size_review` in `AUTODEV_NOT_READY_STATES`) [Agent 3]
- `scripts/tests/test_autodev_scores_freshness.py` — `_PAIRS` (:28-31), `test_repair_predecessors_target_clear_states`, `test_readiness_readers_route_exit_3`, `test_check_passed_still_reaches_detect_children_on_error` (cross-loop edge), `TestInlineGateAbsence` (:218-219), `test_dequeue_next_clears_retry_markers` [Agent 3]
- `scripts/tests/test_autodev_loop.py` — additionally `TestRepairCycleCounterStates` (`test_all_six_counter_states_exist`, `test_run_size_review_routes_through_counter_before_enqueue_or_skip`), `TestDesignGateStep0Detection`, `TestRecheckAfterSizeReviewStagnationBackstop` (:497), `...DesignGateBranch` (:571), `...MeasurementGateBranch` (:715), `...DecisionUnresolvedBranch` (:807), `TestDequeueNextPreReadinessSnapshot::test_action_resets_repair_cycle_counter` (cross-loop file contract), `TestCheckGateAtDequeueMarkerLiterals` [Agent 3]
- `scripts/tests/test_autodev_decision_gate.py` — additionally `TestDesignGateRefineRemedy` (`test_dispatch_design_remedy_routes_refine_design_token`, `test_check_pre_deferral_remedy_routes_through_design_gate_first`, `test_dispatch_pre_deferral_remedy_plateau_routing_unmodified`, `test_marker_not_cleared_at_dequeue_next`), `TestAtomicDesignRemedyRouting`, `TestCheckDecisionBeforeSizeReviewRouting` (:903) [Agent 3]
- `scripts/tests/test_spike_verdict_routing.py` — `test_dispatch_pre_deferral_remedy_spike_budget` (loads `autodev.yaml`, KeyError after move), `test_autodev_routing_table` (:99, :106; `check_scores_present_spike.on_yes == "enqueue_or_skip"`, `check_rearmed_spike_after_decide.on_no == "snap_and_size_review"` — both targets move) [Agent 3]
- `scripts/tests/test_ll_issues_check_gate.py` (docstring ~:268 cites `recheck_after_size_review`; ~:376 asserts an autodev state `next == "dequeue_next"`), `test_recursive_finalize.py:133-140` (`autodev-new-children.txt`), `test_auto_refine_closure_accounting.py`, `TestAutoRefineAndImplementLoop` (~:4761, :4998-5146, :5001-5620) — pin queue/ledger files that must stay autodev-owned [Agent 3/2]
- `scripts/tests/test_run_record.py` — extend: `TestOutcomeMapping.CASES` (:235-250), `TestCmdRunRecordWrite::test_legacy_class_mapping_via_cli` (:340-348) with rows for the terminals' chosen legacy classes; `test_prepare_issue_writer_via_cli` (:430); a `prepare-issue` mirror of `TestLoopCallSites` (hard-wired to `refine-to-ready-issue.yaml`, :494-550) [Agent 3]
- `scripts/tests/data/loop_interpolation_baseline.json` — correction to the Tests bullet: `enqueue_or_skip`/`recheck_scores` entries (~:715-741) are keyed to `loops/recursive-refine.yaml` and do **not** move; autodev's baselined states are `check_blockers_at_dequeue`, `check_reconcile_needed`, `check_spike_needed`, `check_spike_needed_before_skip` (none in this issue's scope). Add `prepare-issue.yaml` entries if the moved states carry unbaselined interpolation sites (`TestInterpSweepBaseline::test_completeness_guard`) [Agent 3]
- **Unaffected (name collision with recursive-refine)**: `test_loops_recursive_refine.py`, `TestRecursiveRefineLoop` (~:9780-10170), `test_issue_refinement_broke_down.py`, `test_rn_refine.py`, `test_rn_implement.py` [Agent 3]
- `scripts/tests/test_wiring_skills_and_commands.py` (~:750-751) — line-pinned entries for `skills/go-no-go/SKILL.md` at 176 and 276; break if the SKILL.md edit shifts lines [Agent 3]
- **New**: whole-autodev-graph queue-only absence test in `REMOVED_INLINE_STATES` shape (`TestIssueRefinementSubLoop` ~:1323/:1413; `TestAutodevLoop::test_old_states_removed` ~:6705 is the set-intersection variant), plus an explicit assertion that `enqueue_children`/`dequeue_next`/`recover_subloop_children` are autodev's only queue writers [Agent 3]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_

- No schema/config/manifest change: `run_record.py` already accepts `prepare-issue` writer and the six `LEGACY_CLASSES`; `pyproject.toml` glob covers the YAML [Agent 1/2]

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Decide and pin the terminal → `--legacy-class` mapping (`gate_unmet` for go/no-go and `oversized_atomic`, `quality` for atomic failure, `refine-broke-down=1` for breakdown) and add `TestOutcomeMapping`/CLI rows
- Keep one shared `autodev-repair-cycle-count.txt` across `count_repair_cycle_*` states in both loops; keep `dequeue_next` as sole cleaner of moved sentinels
- Preserve `ID  oversized_atomic` ledger line format for `reopen_waived` and `auto-refine-and-implement` breakdown until ENH-3600
- Give exits into staying autodev states (`decide_current`, `resolve_decision`, `run_spike`, `recover_subloop_children`, `enqueue_children`) wrapper-local destinations or outcome terminals
- Route `run_size_review` and go/no-go rate-limit exhaustion to a wrapper-local `retryable_error` terminal
- Retarget/relocate tests listed above; add the queue-only absence test; update `test_fsm_topology.py` count with a delta comment
- Update the docs listed above; re-anchor `skills/go-no-go`, regenerate mirrors with `ll-adapt --host <gemini|kimi-code|qwen> --apply`; re-check `test_wiring_skills_and_commands.py` line pins

## Program Design

### Types

- `PreparationOutcome`: six-value Literal in `little_loops.run_record` (reused; `deferred`, `blocked`, `decomposed`, `retryable_error` used by the moved terminals)

### Signatures

- `write_run_record(run_dir: Path, record: RunRecord) -> Path` — reached via `ll-issues run-record write ... --writer prepare-issue` at each new terminal

### Call Path

`autodev.yaml:refine_current` -> `prepare-issue.yaml` (size-review / go-no-go / pre-deferral states) -> `ll-issues run-record write` -> autodev `finalize_done`

## Status

**Open** | Created: 2026-09-26 | Priority: P3

## Session Log
- `/ll:wire-issue` - 2026-09-26T03:36:28 - `e6ad8ea2-14d6-441f-a607-435314c2d056.jsonl`
- `/ll:refine-issue` - 2026-09-26T03:22:25 - `7612ef86-47f8-4d5d-aa01-e50211538dc3.jsonl`
- `/ll:format-issue` - 2026-09-26T03:07:12 - `34887897-5e19-4ee2-b656-5f0a00c15f02.jsonl`
