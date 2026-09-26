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
- `/ll:format-issue` - 2026-09-26T03:07:12 - `34887897-5e19-4ee2-b656-5f0a00c15f02.jsonl`
