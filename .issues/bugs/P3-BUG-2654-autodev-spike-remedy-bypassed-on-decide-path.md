---
id: BUG-2654
type: BUG
priority: P3
status: done
captured_at: '2026-07-15T21:40:10Z'
completed_at: '2026-07-15T22:00:18Z'
discovered_date: 2026-07-15
discovered_by: capture-issue
labels:
- fsm
- loops
- autodev
- confidence
- spike
relates_to:
- ENH-2640
- BUG-2650
- ENH-2568
parent: EPIC-2570
confidence_score: 98
outcome_confidence: 88
score_complexity: 23
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 23
---

# BUG-2654: autodev spike remedy bypassed for spike_needed issues on the decide path

## Summary

The `check_spike_needed` → `run_spike` remediation branch that ENH-2640 added to
`autodev.yaml` is only reachable from `triage_outcome_failure` (the
`check_passed.on_no` path). An issue that is **both** `decision_needed: true`
**and** `spike_needed: true` is routed down the **decide path**
(`check_decision_* → run_decide → … → recheck_after_decide → snap_and_size_review
→ run_size_review → enqueue_or_skip → recheck_after_size_review`), which never
visits `check_spike_needed`. The spike remedy is structurally bypassed and the
issue is skipped as `low_readiness` even though an applicable remedy exists.

## Root Cause

`scripts/little_loops/loops/autodev.yaml` — the spike gate is wired onto a single
edge. ENH-2640 retargeted only `triage_outcome_failure.on_no`
(`check_missing_artifacts` → `check_spike_needed`). The decide path resolves the
decision, re-scores, and when outcome confidence is still below threshold it
routes `recheck_after_decide.on_no → snap_and_size_review → run_size_review`
(autodev.yaml:355, 386-404). From there `enqueue_or_skip.on_no →
recheck_after_size_review` (autodev.yaml:807) skips the issue with
`low_readiness` (autodev.yaml:823) without ever checking `spike_needed`.

`triage_outcome_failure` (autodev.yaml:665) — the only state that reaches the
spike gate — sits on the `check_passed.on_no` edge (autodev.yaml:205), which is
mutually exclusive with the decide path in a given iteration.

## Current Behavior

Observed on the `ll-loop run autodev BUG-2650` run
(`.loops/runs/autodev-20260715T161809/`, 2026-07-15). BUG-2650 carried both an
Option A/B decision block (`decision_needed: true`) and `spike_needed: true`
(unproven root-cause mechanism). The loop:

1. refined it, ran `/ll:decide-issue` (resolved Option A),
2. re-ran `/ll:confidence-check` → outcome_confidence 68 (< 75 threshold),
3. `recheck_after_decide` failed → `snap_and_size_review` → `run_size_review`,
4. size-review declined to decompose (no children),
5. `recheck_after_size_review` failed again → wrote `BUG-2650  low_readiness` to
   `autodev-skipped.txt` and dequeued.

`/ll:spike` — the remedy that could have lifted the outcome score — was never
invoked, despite `spike_needed: true` being set.

## Expected Behavior

A `spike_needed: true` (and not-yet-`spike_attempted`) issue reaches
`check_spike_needed → run_spike → rerun_confidence_after_spike` regardless of
whether it also carried a `decision_needed` flag — i.e. the decide path checks
for a pending spike after the decision is resolved and re-scored, before falling
through to size-review-then-skip. The `spike_attempted` one-shot guard still
prevents a completed-or-attempted spike from re-running.

## Steps to Reproduce

1. Have an issue with `decision_needed: true`, `spike_needed: true`,
   `spike_attempted` unset, confidence_score ≥ readiness_threshold, and
   outcome_confidence below `outcome_threshold` (75) — e.g. BUG-2650 before any
   spike.
2. `ll-loop run autodev <ID>`.
3. Observe the run dumps `<ID>  low_readiness` to
   `${run_dir}/autodev-skipped.txt`; `usage.jsonl` shows `run_decide`,
   `rerun_confidence_after_decide`, `run_size_review` but **no** `run_spike`
   state.

## Proposed Solution

Insert a `check_spike_needed` gate on the decide path so a pending spike is
attempted before the issue is skipped. Candidate insertion point:
`recheck_after_size_review` (the decide/size-review terminal skip at
autodev.yaml:810-830) — before writing `low_readiness`, route a
`spike_needed AND NOT spike_attempted` issue to `run_spike` rather than skipping.
Alternatively, retarget `recheck_after_decide.on_no` (or
`snap_and_size_review`) through `check_spike_needed` first.

Decide the exact edge at implementation time, but the invariant is: **every path
that ends in a `low_readiness` skip must first give a not-yet-attempted
`spike_needed` issue its one shot at `run_spike`.** Reuse the existing
`check_spike_needed` / `run_spike` / `rerun_confidence_after_spike` states
(autodev.yaml:683-731) — this is a routing/edge change plus (possibly) a small
re-entry guard, not new states. Mind the `spike_attempted` one-shot guard so the
decide-path and triage-path spike checks don't double-fire in one iteration.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The candidate `recheck_after_size_review` insertion point is too late.** That
  state's `low_readiness` write is baked *inline* in its shell action
  (autodev.yaml:823) and fires **before** the route decision — its `on_no` then
  just goes to `dequeue_next` (autodev.yaml:829). Interposing a spike check at
  `recheck_after_size_review` itself would already have appended `low_readiness`.
  Insert the gate **upstream** of the skip write instead.
- **Cleanest edge: `enqueue_or_skip.on_no` (autodev.yaml:807).** It currently
  routes the no-children case straight to `recheck_after_size_review`. Retarget it
  to a spike check first (`check_spike_needed` on match → `run_spike`; on no-match
  → `recheck_after_size_review`, preserving the leaf-skip regression). This single
  edge covers *both* the decide path (`recheck_after_decide.on_no →
  snap_and_size_review → run_size_review → enqueue_or_skip`, autodev.yaml:355) and
  the no-decide size-review path, since both funnel through `enqueue_or_skip`
  before any `low_readiness` skip — one gate closes the whole class, not just the
  BUG-2650 decide case.
- **Re-entry is already clean.** `rerun_confidence_after_spike.next` →
  `enqueue_or_skip` (autodev.yaml:729). After a spike runs and re-scores, control
  returns through `enqueue_or_skip` → (still no children) → the new spike gate,
  where the `spike_attempted` one-shot predicate (autodev.yaml:698) now evaluates
  false and falls through to `recheck_after_size_review`. No new re-entry guard is
  needed — the existing `spike_attempted` flag prevents the second fire.
- **Reuse `check_spike_needed` verbatim.** Its `on_no`/`on_error` already point at
  `check_missing_artifacts` (autodev.yaml:701-702), which is the *triage*-path
  fall-through, not the decide-path one. If the same state is shared across both
  entry edges its no-match fall-through can only go one place — so either (a) point
  the new `enqueue_or_skip.on_no` at `check_spike_needed` and accept that a
  no-match decide-path issue detours through `check_missing_artifacts` (harmless —
  it re-converges), or (b) add a thin decide-path-specific spike gate whose
  `on_no` is `recheck_after_size_review`. Option (b) keeps the two paths' skip
  semantics identical and is the lower-surprise choice.

## Files to Modify

- `scripts/little_loops/loops/autodev.yaml` — add a spike check on the decide /
  size-review skip path (candidate: `recheck_after_size_review`, autodev.yaml:810,
  and/or `recheck_after_decide.on_no`, autodev.yaml:355).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — **stale after this fix.** The ASCII routing
  diagram (lines 982-1010) shows `check_spike_needed` hanging **only** off the
  outcome-failure/triage branch and shows the decide-path failure going straight
  `recheck_after_decide → snap_and_size_review → run_size_review → enqueue_or_skip`
  with no spike branch — i.e. it documents the exact bypass this bug fixes. Add a
  `enqueue_or_skip.on_no → check_spike_needed` arrow. The triage prose (line 1016)
  and the `enqueue_or_skip` in-flight-tracking paragraph (line 1014) also need a
  clause noting the decide path now reaches the spike check before skipping.
  [Agent 1 + 2 finding]
- `scripts/little_loops/loops/README.md` (lines 34, 61, 84) — summary-level
  `spike-gate`/`autodev` mentions; no decide-path detail, lower-priority. Verify
  no contradiction after the edit. [Agent 1 finding]
- `CHANGELOG.md` — add a BUG-2654 entry at release time following the ENH-2640
  pattern (~lines 21-50); **not** under `[Unreleased]` per project convention.
  [Agent 1 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue` — read-only couplings, do NOT modify:_
- `scripts/little_loops/cli/issues/show.py:188-193,375-380` — `ll-issues show
  --json` is what `check_spike_needed` shells out to; it surfaces
  `spike_needed`/`spike_attempted` as lowercased string booleans. The new
  decide-path gate reuses `check_spike_needed` verbatim, so this contract is
  unchanged — noted only so the edge change stays compatible with the existing
  serialization. [Agent 1 finding]
- Asymmetry note: `decision_needed` is a typed `IssueInfo` field
  (`issue_parser.py:608,654,693,800-808`), but `spike_needed`/`spike_attempted`
  are **not** structured parser fields — read only ad hoc via `show.py`'s JSON.
  Out of scope for this routing fix; relevant only if the new gate ever needs to
  read the flags structurally. [Agent 1 finding]

### No-Change Confirmations (checked, nothing to do)

_Wiring pass added by `/ll:wire-issue`:_
- **FSM validation is name-agnostic.** `fsm/validation.py` has no rule against a
  state having multiple inbound edges (`check_spike_needed` already has one from
  `triage_outcome_failure.on_no`; this adds a second). MR-4 dead-end lint applies
  only to LLM-judged states — `check_spike_needed` is a `shell_exit` fragment, so
  it's exempt. The new edge trips no lint rule. [Agent 2 finding]
- **`autodev-skipped.txt` format is reason-string-keyed, not state-keyed.** No new
  reason vocabulary is introduced (a spiked-then-still-failing decide-path issue
  still lands in `recheck_after_size_review`'s existing `low_readiness` write), and
  no `ll-logs`/dashboard code parses this file — only `test_builtin_loops.py`.
  [Agent 2 finding]
- **No committed routing-table/diagram artifact.** `ll-loop edit-routes` renders
  on demand; nothing generated is checked in. No other loop YAML imports
  autodev.yaml's states. [Agent 1 + 2 finding]

## Tests

- `scripts/tests/test_builtin_loops.py` — add a routing test asserting the
  decide-path skip edge reaches `check_spike_needed` (or `run_spike`) for a
  `spike_needed` issue; regression that a non-spike issue still skips via
  `low_readiness`. Clone the ENH-2640 spike-triad routing test cluster.
- `scripts/tests/test_autodev_decision_gate.py` — whole-file
  `test_autodev_yaml_loads_and_validates` (test_autodev_decision_gate.py:271)
  stays zero-`ERROR` (MR-1..MR-11) after the edge change; add a structural/routing
  assertion for the new decide-path spike edge.

### Codebase Research Findings

_Added by `/ll:refine-issue` — existing spike-triad test clusters to clone:_

- `scripts/tests/test_builtin_loops.py:3935-3977` — the ENH-2640 triage-path
  cluster (`test_triage_outcome_failure_on_no_routes_to_check_spike_needed`,
  `test_check_spike_needed_routes_to_run_spike`, `test_run_spike_action_and_routing`).
  Model the new decide-path routing assertion on these — assert
  `enqueue_or_skip.on_no` (or the new gate) reaches `check_spike_needed`/`run_spike`.
- `scripts/tests/test_autodev_decision_gate.py:374-415` — the parallel
  spike-triad structural cluster (`test_spike_states_exist`,
  `test_check_spike_needed_predicate_reads_both_flags`,
  `test_rerun_confidence_after_spike_routing`). Add the decide-path skip-edge
  assertion here alongside the existing decision-gate routing tests
  (`test_check_decision_before_size_review_*`, lines 302-359).
- Regression to preserve: a non-`spike_needed` no-children issue must still route
  `enqueue_or_skip.on_no → recheck_after_size_review → dequeue_next` and land in
  `autodev-skipped.txt` as `low_readiness` (AC 3).

_Wiring pass added by `/ll:wire-issue` — coverage-gap notes (from FSM test audit):_
- **`enqueue_or_skip.on_no` is currently untested** — no existing test pins its
  target, so retargeting it breaks **nothing**. This is a pure coverage gap, not a
  regression risk. (Do not confuse with `check_broke_down.on_no → enqueue_or_skip`
  at `test_builtin_loops.py:4700-4704`, an unrelated edge into this state.)
  [Agent 3 finding]
- **No end-to-end "no spike, no children → low_readiness" behavioral test exists**
  in either file — only static single-edge assertions
  (`recheck_after_size_review.on_no == "dequeue_next"`,
  `test_builtin_loops.py:3838-3843`). The AC 3 regression test is therefore a
  genuinely **new** `FSMExecutor`-driven test, not an update — reuse the
  `_StubRunner` / `_run_decision_chain` pattern
  (`test_autodev_decision_gate.py:36-94`, `TestCheckDecisionBeforeSizeReviewRouting`
  at line 424+) rather than inventing a graph walker (no BFS helper exists). [Agent 3 finding]
- **Full-suite smoke:** `test_fsm_fragments.py`, `test_fsm_schema.py`,
  `test_fsm_interpolation.py` also load `autodev.yaml` (as one example among many)
  for generic structural validity, not routing — unlikely to break, but they run
  under the AC 4 `python -m pytest scripts/tests/` gate. [Agent 3 finding]

## Acceptance Criteria

1. An issue with `decision_needed: true` + `spike_needed: true` +
   `spike_attempted` unset that fails outcome after decide+size-review reaches
   `run_spike` (invokes `/ll:spike --auto`) before any `low_readiness` skip.
2. The `spike_attempted` one-shot guard prevents the spike from running twice in
   one iteration across the triage and decide paths.
3. A non-`spike_needed` issue still skips via `recheck_after_size_review`'s
   `low_readiness` path unchanged (regression).
4. `python -m pytest scripts/tests/test_builtin_loops.py
   scripts/tests/test_autodev_decision_gate.py` passes; `autodev.yaml` loads with
   zero `ValidationSeverity.ERROR`.

## Related Issues

- **ENH-2640** — added the `check_spike_needed`/`run_spike`/`rerun_confidence_after_spike`
  states, but only wired the gate onto `triage_outcome_failure.on_no` (the
  no-decision path). This bug is the uncovered decide path.
- **BUG-2650** — the concrete instance skipped as `low_readiness` because its
  spike remedy was bypassed on the decide path.
- **ENH-2568** — parent theme (autodev spike triage routing).
- **EPIC-2570** — spike workflow / confidence-flag / autodev-routing epic.

## Resolution

Implemented via **Option (b)** from the refine-pass research: added a
decide-path-specific spike gate `check_spike_needed_before_skip` and retargeted
`enqueue_or_skip.on_no` (formerly → `recheck_after_size_review`) through it. The
new gate reuses `check_spike_needed`'s two-field predicate
(`spike_needed AND NOT spike_attempted`); the only difference is its no-match
fall-through goes to `recheck_after_size_review` (preserving the BUG-1230
leaf-skip) instead of the triage-path `check_missing_artifacts`. This single edge
closes the whole class — both the decide path
(`recheck_after_decide.on_no → snap_and_size_review → run_size_review →
enqueue_or_skip`) and the no-decide size-review path funnel through
`enqueue_or_skip` before any `low_readiness` write. Post-spike re-entry
(`rerun_confidence_after_spike.next → enqueue_or_skip`) falls through cleanly
because the `spike_attempted` one-shot guard now reads false.

**Changed**:
- `scripts/little_loops/loops/autodev.yaml` — new `check_spike_needed_before_skip`
  state; `enqueue_or_skip.on_no` retargeted.
- `scripts/tests/test_builtin_loops.py`, `scripts/tests/test_autodev_decision_gate.py`
  — updated the pinned `enqueue_or_skip.on_no` edge; added structural routing
  tests for the new gate (on_yes → run_spike, on_no/on_error →
  recheck_after_size_review, two-flag predicate).
- `docs/guides/LOOPS_REFERENCE.md` — added the decide-path spike branch to the
  routing diagram and a "Decide-path spike parity (BUG-2654)" prose note.

All ACs met: `ll-loop validate autodev` reports zero errors; full
`python -m pytest scripts/tests/` passes (15053 passed, 36 skipped).

## Status

- **Current Status**: done
- **Blockers**: None — self-contained routing/edge change reusing existing states.

## Session Log
- `/ll:manage-issue` - 2026-07-15T21:59:44Z - `dd773afc-cdae-4207-971e-69bcb8cccfb4.jsonl`
- `/ll:confidence-check` - 2026-07-15T21:52:49 - `93c29c49-3f36-4cb4-a13b-5ab3f5fe1f75.jsonl`
- `/ll:wire-issue` - 2026-07-15T21:51:07 - `bb398b76-67a1-4ae6-95fe-6df91aad16b5.jsonl`
- `/ll:refine-issue` - 2026-07-15T21:47:44 - `663b28bd-ea6f-44f1-9ef7-6e4524fb9652.jsonl`
- `/ll:capture-issue` - 2026-07-15T21:40:10Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2a4fbb3-4941-4589-a115-5db99a56d98b.jsonl`
</content>
</invoke>
