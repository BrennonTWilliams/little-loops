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
- `/ll:refine-issue` - 2026-09-26T03:22:25 - `7612ef86-47f8-4d5d-aa01-e50211538dc3.jsonl`
- `/ll:format-issue` - 2026-09-26T03:07:12 - `34887897-5e19-4ee2-b656-5f0a00c15f02.jsonl`
