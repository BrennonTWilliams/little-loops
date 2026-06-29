---
id: BUG-2396
title: 'rn-remediate: decide.on_no routes un-auto-resolvable decision to emit_implement_failed
  (mislabels needs-decision as IMPLEMENT_FAILED)'
type: BUG
priority: P2
status: open
discovered_date: '2026-06-29'
discovered_by: audit-loop-run
source_loop: rn-implement
source_state: decide
affects: scripts/little_loops/loops/rn-remediate.yaml
relates_to:
- BUG-1985
- BUG-2193
- BUG-2169
labels:
- rn-implement
- rn-remediate
- loop-defect
- routing
confidence_score: 100
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-2396: rn-remediate decide.on_no mislabels un-decidable issue as IMPLEMENT_FAILED

## Summary

In the `rn-remediate` sub-loop, the `decide` state runs
`/ll:decide-issue ${issue_id} --auto` and routes:

```yaml
decide:
  action: "/ll:decide-issue ${context.issue_id} --auto"
  action_type: slash_command
  on_yes: re_assess
  on_no: emit_implement_failed      # <-- defect
  on_error: emit_implement_failed
  on_partial: re_assess
```

When `decide-issue --auto` legitimately **cannot** auto-resolve a decision —
e.g. the open questions are author-marked "do not pre-decide" or carry no
structured `### Option A/B` blocks — the command returns a non-success verdict
(`no`). The loop then routes to `emit_implement_failed`, writing
`IMPLEMENT_FAILED` to the sub-loop outcome sidecar and incrementing the parent
`summary.json` `failed` counter.

An issue that is blocked on an **un-auto-resolvable, author-gated decision** is a
*needs-human-decision / manual-review* outcome, **not** an implementation
failure. `rn-remediate` already has the correct terminal for this case —
`emit_needs_manual_review` (`MANUAL_REVIEW_NEEDED` → parent
`route_rem_manual_review`) — but the `decide` state's `on_no` does not use it.

## Steps to Reproduce

1. Run `rn-implement` (which drives the `rn-remediate` sub-loop) on an issue
   whose open design questions are author-marked "do not pre-decide" and carry
   no structured `### Option A/B` blocks (e.g. FEAT-2387).
2. The `decide` state invokes `/ll:decide-issue <id> --auto`, which legitimately
   returns `no` (`✗ No resolvable provisional decision found`).
3. Observe: the sub-loop routes `on_no → emit_implement_failed`, writing
   `IMPLEMENT_FAILED` to the outcome sidecar and incrementing the parent
   `summary.json` `failed` counter — even though no implementation was attempted
   or broken.

## Current Behavior

The `rn-remediate` `decide` state's `on_no` route targets
`emit_implement_failed`. When `/ll:decide-issue --auto` returns `no` because the
decision is author-gated and non-auto-resolvable, the sub-loop records the issue
as `IMPLEMENT_FAILED` and increments the parent `summary.json` `failed` counter,
conflating "needs a human decision" with "implementation failed".

## Expected Behavior

A `no` verdict from `decide-issue --auto` (no resolvable decision) should
terminate the sub-loop via `emit_needs_manual_review`
(`MANUAL_REVIEW_NEEDED` → parent `route_rem_manual_review`), leaving the `failed`
counter unaffected. Only `on_error` (a genuine infra crash / non-zero CLI exit)
should route to `emit_implement_failed`.

## Root Cause

- **File**: `scripts/little_loops/loops/rn-remediate.yaml`
- **Anchor**: `in the decide state's on_no route`
- **Cause**: `decide.on_no` is wired to `emit_implement_failed`, which treats an
  un-auto-resolvable (author-gated) decision as an implementation failure. The
  correct terminal for this outcome — `emit_needs_manual_review` — already
  exists but is not referenced from this path. Prior fixes (BUG-1985, BUG-2193,
  BUG-2169) covered the `check_convergence` and `on_partial` paths but never the
  `on_no` failure-classification.

## Evidence

Run `2026-06-29T161824-rn-implement`, FEAT-2387 (the only issue processed):

```
check_decision_needed (decision_needed=true) → decide [call #1] verdict=yes → re_assess
re_assess → check_convergence=CONVERGED_IMPROVED → diagnose → "DECIDE"
  → decide [call #2] verdict=no → emit_implement_failed → failed
```

Both `decide-issue` calls returned verbatim:

> `✗ No resolvable provisional decision found — leaving decision_needed unchanged`
> `⊘ No decision applied — decision_needed remains true`
> "the two open design questions are explicitly marked 'do not pre-decide' …
> Automation cannot override an author-marked non-decidable gate."

`summary.json`: `{ "implemented": 0, "failed": 1 }`. FEAT-2387 post-run:
`decision_needed=true`, `outcome=62` (< 75 threshold), `status=Open` — i.e. the
loop did exactly the right thing at the `decide-issue` level, but the **routing**
recorded it as a failed implementation.

## Distinction from prior fixes

- **BUG-1985** (done) fixed the `check_convergence` *CONVERGED_STALLED* branch
  (`decision_needed` true → manual-review).
- **BUG-2193** (done) fixed *CONVERGED_PASS* bypassing the decision check.
- **BUG-2169** (done) fixed the `decide` state's *`on_partial`* MR-4 gap.

None touch the `decide` state's **`on_no`** failure-classification. This is the
remaining uncovered path.

_Wiring pass added by `/ll:wire-issue`:_ **BUG-2396 reverses an ENH-2307
decision.** The two existing tests that will break
(`test_decide_on_no_routes_to_emit_implement_failed`,
`test_decide_failure_routes_to_emit_implement_failed`) both cite **ENH-2307**
("surface failure immediately") as the rationale for routing `decide.on_no →
emit_implement_failed`. ENH-2307 fixed a *degenerate gate* (on_yes/on_no both
→ re_assess) by giving `on_no` a distinct destination — but chose
`emit_implement_failed`, conflating "no resolvable decision" with "implementation
failed". BUG-2396 corrects that classification to `emit_needs_manual_review`. The
implementer should update the ENH-2307 docstrings on both tests to reference
BUG-2396, so the routing rationale stays traceable.

## Proposed Solution

```yaml
decide:
  action: "/ll:decide-issue ${context.issue_id} --auto"
  action_type: slash_command
  on_yes: re_assess
  on_no: emit_needs_manual_review     # un-auto-resolvable decision ≠ implement failure
  on_error: emit_implement_failed      # infra crash stays a real failure
  on_partial: re_assess
```

Apply the same change to `check_decision_needed_post` → `decide` consumers if
they share the routing. Verify the parent then reports the issue under a
manual-review/blocked counter rather than `failed`.

## Integration Map

_Added by `/ll:refine-issue` — verified against current codebase:_

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — the `decide` state (≈L432):
  change `on_no: emit_implement_failed` → `on_no: emit_needs_manual_review`.
  Leave `on_error: emit_implement_failed` unchanged (genuine infra crash stays a
  failure). `on_yes`/`on_partial` already route to `re_assess` — no change.
- `scripts/tests/test_builtin_loops.py` — update the AC #4 regression test (see Tests below).

_Wiring pass added by `/ll:wire-issue` — these were missing from the list above and must also be edited:_
- `scripts/tests/test_rn_remediate.py` — update `TestRemediationActions.`
  `test_decide_failure_routes_to_emit_implement_failed` (`:330`) `on_no` assertion
  (see Tests below). [Agent 1+2+3 finding]
- `docs/guides/LOOPS_REFERENCE.md` — update the stale `rn-remediate` `decide` FSM
  flow notation (`:573`) (see Documentation below). [Agent 1+2 finding]

### `decide` Entry Paths (all converge on the single `decide` state)
Fixing `decide.on_no` covers **every** caller — there is no separate per-caller route to patch:
- `check_decision_needed.on_yes → decide` (`rn-remediate.yaml:290`)
- `check_decision_needed_post.on_yes → decide` (`rn-remediate.yaml:540`) — the
  BUG-2222 post-refine/post-wire gate. It routes *into* `decide`, so the issue's
  "mirror to `check_decision_needed_post`" note is satisfied automatically; **no
  separate edit needed**.
- `diagnose` route table `DECIDE: decide` (`rn-remediate.yaml:362`)

### Terminal Target (already exists)
- `emit_needs_manual_review` (`rn-remediate.yaml:744`) — writes
  `MANUAL_REVIEW_NEEDED` to the outcome sidecar, `next: failed`.

### ⚠ Critical dependency — sidecar write must be present
The fix only works if `emit_needs_manual_review` actually writes
`MANUAL_REVIEW_NEEDED` to `${context.run_dir}/subloop_outcome_${context.issue_id}.txt`.
The parent reads this file in `classify_remediation`
(`rn-implement.yaml:535-539`) with a `|| echo "IMPLEMENT_FAILED"` fallback —
**a missing sidecar re-introduces the exact misclassification this bug fixes.**

> The current **working tree** has the sidecar write removed from
> `emit_needs_manual_review` (`echo "MANUAL_REVIEW_NEEDED"  # sidecar write
> removed to test regression guard` — an experimental edit, not committed).
> The implementer MUST restore the redirect
> (`echo "MANUAL_REVIEW_NEEDED" > "${context.run_dir}/subloop_outcome_${context.issue_id}.txt"`)
> as part of this fix, or the retargeted `on_no` lands on a no-op terminal.

> _Wiring pass correction (`/ll:wire-issue`):_ **The above note is now STALE.**
> The working tree is clean (`git diff scripts/little_loops/loops/rn-remediate.yaml`
> is empty) and `emit_needs_manual_review` (`:744–748`) **already writes the
> sidecar** (`echo "MANUAL_REVIEW_NEEDED" > "${context.run_dir}/subloop_outcome_${context.issue_id}.txt"`).
> The experimental removal has already been reverted — **no sidecar restoration
> is required**. The only YAML change is the one-line `decide.on_no` retarget.
> `TestSubloopSidecarContract` and `TestOutcomeTokenChannel` are currently
> **passing** and will remain green.

### Parent Accounting (confirms AC #3)
- `classify_remediation` (`rn-implement.yaml:535`) reads the sidecar token.
- `route_rem_manual_review` (`rn-implement.yaml:681`, pattern `MANUAL_REVIEW_NEEDED`)
  diverts the run to manual-review handling, bypassing `record_failure`
  (`rn-implement.yaml:710`). Result: `summary.json` `failed` stays `0`.

### Tests
- **AC #4 (new)** — model after the existing parametrized routing assertions in
  `TestBuiltinLoopFiles`, e.g.
  `test_check_decision_needed_on_no_routes_to_check_missing_artifacts`
  (`test_builtin_loops.py:1256`). Assert
  `states["decide"]["on_no"] == "emit_needs_manual_review"` and
  `states["decide"]["on_error"] == "emit_implement_failed"` for `rn-remediate`.
- **Already in the working tree** —
  `TestSubloopSidecarContract.test_terminal_routing_states_write_sidecar`
  (`test_builtin_loops.py:~295`) generically asserts every sub-loop state routing
  to a terminal writes the sidecar token. It already enforces the sidecar
  dependency above and **will fail against the current working-tree
  `emit_needs_manual_review` edit** — restoring the write also greens this guard.

_Wiring pass added by `/ll:wire-issue`:_

> **Correction — AC #4 is an UPDATE, not a new test.** The Integration Map above
> frames AC #4 as adding a new assertion. In fact two **existing** tests already
> assert the *old* routing (`decide.on_no == emit_implement_failed`) and will
> **break** when the route is changed. AC #4 is satisfied by retargeting the
> first of these, not by writing a fresh test:

- `scripts/tests/test_builtin_loops.py` — `TestRnRemediateAssessRouting.`
  `test_decide_on_no_routes_to_emit_implement_failed` (`:7368`) currently asserts
  `state.get("on_no") == "emit_implement_failed"` with docstring "ENH-2307:
  surface failure immediately". **Rename to**
  `test_decide_on_no_routes_to_emit_needs_manual_review` and change the assertion
  to `== "emit_needs_manual_review"` (BUG-2396). This is the AC #4 deliverable.
  Leave the sibling `test_decide_on_error_routes_to_emit_implement_failed`
  (`:7375`) unchanged — `on_error` stays `emit_implement_failed`. [Agent 1+3 finding]
- `scripts/tests/test_rn_remediate.py` — `TestRemediationActions.`
  `test_decide_failure_routes_to_emit_implement_failed` (`:330`) asserts BOTH
  `dec["on_no"] == "emit_implement_failed"` and
  `dec["on_error"] == "emit_implement_failed"` in a single method. Update the
  `on_no` assertion to `== "emit_needs_manual_review"`, keep the `on_error`
  assertion, and revise the docstring (currently cites ENH-2307). **This file is
  not listed in "Files to Modify" above — it must also be edited.** [Agent 1+2+3 finding]
- `scripts/tests/test_rn_remediate.py` — `TestOutcomeTokenChannel` already verifies
  `emit_needs_manual_review` exists and emits `MANUAL_REVIEW_NEEDED`; no change
  needed (confirms the terminal is sound). [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` (`:573`, `rn-remediate` FSM flow block) — currently
  documents `decide … on_yes → re_assess | on_no/on_error → emit_implement_failed`.
  Update the notation to
  `on_yes → re_assess | on_no → emit_needs_manual_review | on_error → emit_implement_failed`.
  **Not listed in "Files to Modify" above — must be edited.** [Agent 1+2 finding]
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` (outcome-token table, ~`:203–211`) —
  already documents `MANUAL_REVIEW_NEEDED` = "Needs a human decision" → "Mark blocked",
  which matches the post-fix behavior. **Verify only; no edit expected.** [Agent 2 finding]

## Acceptance Criteria

1. When `/ll:decide-issue --auto` returns `no` (no resolvable decision), the
   sub-loop terminates via `emit_needs_manual_review`, not
   `emit_implement_failed`.
2. `on_error` (genuine infra crash / non-zero CLI exit) still routes to
   `emit_implement_failed`.
3. A run over an author-gated, non-resolvable issue reports it in `summary.json`
   as manual-review/blocked, with `failed == 0`.
4. Regression test in `test_builtin_loops.py` asserting `decide.on_no ==
   emit_needs_manual_review` for `rn-remediate`.

## Notes

Discovered via `/ll:audit-loop-run rn-implement`. Verdict for that run was
`honest-failure` — the loop reported its failure truthfully; this bug is about
the *classification* of that outcome, not a phantom success.

## Impact

- **Priority**: P2 - Misclassifies a needs-decision outcome as a failure,
  corrupting `summary.json` `failed` counts and masking manual-review-needed
  issues behind a false IMPLEMENT_FAILED. No data loss, but it undermines trust
  in the loop's outcome accounting.
- **Effort**: Small - Retarget a single routing key (`decide.on_no`) to an
  existing terminal, plus one regression test; possibly mirror to a sibling
  `check_decision_needed_post` consumer if it shares the route.
- **Risk**: Low - One-line route change to an already-defined terminal state;
  the `on_error` (real-failure) path is unchanged.
- **Breaking Change**: No

---

**Open** | Created: 2026-06-29 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-06-29T18:15:00 - `a6949c04-c2c6-4f5d-8751-ebc22a5d843a.jsonl`
- `/ll:wire-issue` - 2026-06-29T17:30:52 - `be9de5a8-9c38-4dcc-84c5-79686f3ced49.jsonl`
- `/ll:refine-issue` - 2026-06-29T17:14:33 - `e7d74289-f32b-48e5-b1fc-0dc56410799b.jsonl`
- `/ll:format-issue` - 2026-06-29T17:10:15 - `ffd092a1-8266-42ea-92d9-725cd9b75735.jsonl`
