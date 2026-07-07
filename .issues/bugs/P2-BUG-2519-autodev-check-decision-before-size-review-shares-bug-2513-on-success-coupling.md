---
id: BUG-2519
title: autodev `check_decision_before_size_review` shares BUG-2513's `on_success`-coupled
  decision-gate defect
type: BUG
status: open
priority: P2
captured_at: '2026-07-07T14:50:00Z'
discovered_date: '2026-07-07'
discovered_by: capture-issue
relates_to:
- BUG-2513
- BUG-2501
labels:
- loops
- fsm
- autodev
- decide-issue
- decision-gate
- follow-on
confidence_score: 95
outcome_confidence: 78
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 18
decision_needed: false
---

# BUG-2519: autodev `check_decision_before_size_review` shares BUG-2513's `on_success`-coupled decision-gate defect

## Summary

BUG-2513 fixed the `refine_current.on_no → dequeue_next` bypass for the
`decision_needed` gate, but `autodev.yaml` has a second decision gate —
`check_decision_before_size_review` — that has the *same* `on_success`-coupled
dependency on `refine_current`. BUG-2513's `### Similar Patterns` section
(line 203-206) explicitly flagged this as "out of scope for this issue but
worth a follow-on if the bug class recurs" — this issue is that follow-on.

The gate is reachable only on `refine_current.on_success → rerun_confidence_after_decide
→ ... → check_decision_before_size_review`. On the other four exits
(`on_failure`, `on_error`, `on_no`, `on_rate_limit_exhausted`), the issue
re-enters `dequeue_next` without ever consulting `decision_needed`. The
flag is never cleared, so a `decision_needed: true` issue can be
re-dequeued and re-refined indefinitely — the exact same bypass loop BUG-2513
just closed on the post-refine gate.

## Motivation

- **Same defect class as the just-closed BUG-2513 (P1)**: BUG-2513's Resolution
  section fixed the post-refine gate; this issue exists because the second gate
  has identical structure and an identical hole. Leaving it unfixed leaves
  one of two structurally-defective decision gates in production.
- **Silent correctness violation (same flavor)**: A user-facing
  `/ll:decide-issue` step explicitly requested by `decision_needed: true`
  is never invoked on this entry path. No error is raised — the loop just
  continues refining.
- **Identical "infinite bypass loop" risk**: Because the flag is never cleared
  on a non-success exit through this gate, the same issue can be re-dequeued
  and re-refined indefinitely, wasting compute and blocking the queue.
- **Trace evidence**: The killed-run trace in `autodev-bug2501-kill-analysis.md`
  (lines 189-207) explicitly notes "Both gates require `on_success` from
  `refine_current` to fire" and confirms the symmetric hole.
- **P2 priority**: Defense-in-depth on a related-but-not-currently-affected
  gate. The killed run exhibited the post-refine-gate bypass (Mode B on
  `check_decision_after_refine`); the pre-size-review gate shares the
  same structural defect but was not the route the killed run took. Fix
  is small and well-scoped.

## Current Behavior

A dequeued issue with `decision_needed: true` whose `refine_current` sub-loop
returns `on_failure`, `on_error`, `on_no`, or `on_rate_limit_exhausted` skips
both decision gates. The post-refine gate (`check_decision_after_refine`) is
now routed through `check_decision_at_dequeue` per BUG-2513's fix — so
`decision_needed: true` reaches `run_decide` regardless of refine outcome.

However, on the *pre-size-review* path (`refine_current.on_success →
rerun_confidence_after_decide → ... → check_decision_before_size_review`),
if the post-refine-conf gate reads `decision_needed: true`, it routes to
`run_decide`. But this gate is reachable *only* on `on_success` from
`refine_current`. If `decision_needed: true` was added *during* the
post-refine confidence check (e.g., by a future decide hook), and the
issue was originally entered with `decision_needed: false` (so the new
`check_decision_at_dequeue` gate correctly routed to `refine_current`),
then a `decision_needed: true` issue can complete refine successfully,
reach `check_decision_before_size_review`, and route to `run_decide` —
which is the *correct* flow for this entry path.

The asymmetry: `check_decision_before_size_review` is downstream of
`rerun_confidence_after_decide → recheck_after_decide → size_review`,
which are themselves only reachable on `on_success`. So this gate is
*always* downstream of an `on_success`, and the bypass hole BUG-2513
closed on the upstream gate does not actually apply to this gate's
entry path.

**The actual remaining defect**: the gate is *redundant* in the
post-BUG-2513 world, because `check_decision_at_dequeue` (new in
BUG-2513's fix) catches every `decision_needed: true` issue before
`refine_current`. The `check_decision_before_size_review` gate now
only matters if `decision_needed` was *added* during refine (a future
decide-hook scenario that doesn't currently exist). The simplest fix
is to remove the now-redundant gate or document its scope explicitly.

## Expected Behavior

- The pre-size-review decision gate behavior is fully characterized:
  either it is reachable on a real path where it can fire, or it is
  dead code in the post-BUG-2513 routing and should be removed.
- `ll-loop validate autodev` passes; no dead `no` / `partial` ends in
  the routing.
- A pytest under `scripts/tests/` documents whether the gate is reachable
  in the current routing (and from which entry conditions) so future
  changes don't reintroduce a silent bypass.

## Steps to Reproduce

Read the post-BUG-2513 routing graph:

```bash
# Show the current routing
grep -nE "check_decision_before_size_review|check_decision_at_dequeue|check_decision_after_refine|refine_current|recheck_after_decide|size_review" \
    scripts/little_loops/loops/autodev.yaml
```

Verify:
1. `check_decision_at_dequeue` (new in BUG-2513) routes
   `decision_needed: true → run_decide` *before* `refine_current`.
2. `check_decision_before_size_review` is only reachable on
   `refine_current.on_success → rerun_confidence_after_decide → ... → check_decision_before_size_review`.
3. There is no path where `decision_needed: true` issues reach
   `check_decision_before_size_review` *without* first hitting
   `check_decision_at_dequeue` (which would have already routed them
   to `run_decide`).

If step 3 is true, the gate is dead code in the current routing and
should be removed. If step 3 is false (a future decide-hook adds a
path), the gate's contract is documented and tested.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `check_decision_before_size_review` (around line 546) and the
  upstream `refine_current` routing
- **Cause**: BUG-2513's fix added `check_decision_at_dequeue` upstream of
  `refine_current`, which catches every `decision_needed: true` issue
  *before* the sub-loop. The `check_decision_before_size_review` gate,
  which sits downstream of an `on_success`-only path, is now either
  (a) dead code (no path reaches it without first hitting the new
  upstream gate), or (b) defense-in-depth for a hypothetical
  during-refine flag-addition path. Either way, its presence is
  uncharacterized and it duplicates the BUG-2513 fix's coverage.

## Proposed Solution

Three options, ranked by leverage:

### Option A — Remove the gate (highest leverage, smallest change)

If analysis confirms `check_decision_before_size_review` is unreachable
in the post-BUG-2513 routing graph, remove it. This eliminates the
dead code and the implicit documentation cost of having an
unjustified-looking gate in the YAML.

```yaml
# Remove the check_decision_before_size_review state and its inbound
# route from size_review's pre-check chain.
```

### Option B — Document the gate's defensive role (medium leverage)

> **Selected:** Option B — the routing analysis confirms the gate IS reachable (from `recheck_scores.on_no`/`on_error`, autodev.yaml:557-558), so it is redundant-but-not-dead; documenting it as defense-in-depth mirrors BUG-2513's precedent for the sibling `check_decision_after_refine` gate.

If the gate *is* reachable on a hypothetical future path (e.g., a
post-refine decide hook that sets `decision_needed: true`), document
this explicitly in the YAML and add a pytest that asserts the gate is
*only* reachable on the documented entry conditions.

```yaml
check_decision_before_size_review:
  comment: |
    Defense-in-depth for the post-refine path. Reachable only when
    `decision_needed` is added *during* refine (e.g., by a future
    decide hook). The upstream `check_decision_at_dequeue` (BUG-2513)
    catches every pre-refine `decision_needed: true` issue.
  action: "ll-issues check-flag ${captured.input.output} decision_needed"
  on_yes: run_decide
  on_no: size_review
  on_error: size_review
```

### Option C — Do nothing (lowest leverage)

Document the deferral in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`
and close this issue. Accept the dead-code risk for now.

### Decision

**Selected**: Option B — Document the gate's defensive role. The routing-graph
analysis (the prerequisite for choosing A vs B) has now been performed and is
recorded below: the gate is reachable but redundant, which rules out Option A's
"remove dead code" premise.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-07.

**Selected**: Option B — Document the gate's defensive role (with two corrections to the drafted spec, below).

**Reasoning**: A routing-graph analysis of the post-BUG-2513 `autodev.yaml` shows
`check_decision_before_size_review` **is reachable** — its only inbound edges are
`recheck_scores.on_no` (line 557) and `recheck_scores.on_error` (line 558), both on
live paths. This falsifies Option A's premise ("confirm unreachable, then remove"):
the gate is *redundant* for `decision_needed:true` issues (three upstream gates —
`check_decision_at_dequeue`, `check_decision_after_refine`, `triage_outcome_failure` —
route them to `run_decide` first), but it is not dead code. Removing it would also
reverse BUG-1277's documented rationale (the issue that added the gate) and delete four
passing tests (test_builtin_loops.py:2836-2868 plus the `required` set at line 2360).
Option B is directly precedented: BUG-2513 documented the sibling gate
`check_decision_after_refine` as defense-in-depth with an inline `#` comment
(autodev.yaml:107-109); the same rationale applies symmetrically here, at ~5 lines and
zero test churn.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — Remove the gate | 0/3 | 1/3 | 1/3 | 1/3 | 3/12 |
| B — Document the gate | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |
| C — Do nothing (defer) | 1/3 | 3/3 | 0/3 | 2/3 | 6/12 |

**Key evidence**:
- **Option A**: Gate is reachable (autodev.yaml:557-558), so "remove dead code" cannot execute; removal reverses BUG-1277 and drops existing coverage (test_builtin_loops.py:2360, 2836-2868).
- **Option B**: Direct precedent at autodev.yaml:107-109 (BUG-2513 defense-in-depth comment); additive, preserves the defense-in-depth invariant for a future during-refine flag-add.
- **Option C**: Lowest churn but leaves the gate uncharacterized; `ll-loop validate` reachability is WARNING-only and cannot detect the routing asymmetry (validation.py:1200-1210).

#### Corrections to the drafted Option B spec (from evidence)

1. **Use an inline `#` comment, not a `comment:` YAML key.** `comment` is not a valid
   `StateConfig` field (schema.py:888 defines it only on `ParameterSpec`); a top-level
   `comment:` would parse as an unknown state key. Follow the established convention
   (autodev.yaml:107-109).
2. **Close the latent partial-route dead-end.** `check_decision_before_size_review`
   defines `on_yes`/`on_no` but no `on_error` (line 567); if `ll-issues check-flag`
   errors, the FSM loses the issue. Add `on_error: run_size_review`, mirroring the
   sibling gates' error fallbacks. The reachability test (reuse 2/3) should assert both
   the documented entry conditions and the new `on_error` route.

## Implementation Steps

1. **Routing-graph analysis** (1-2 hours): Trace every path that reaches
   `check_decision_before_size_review` in the post-BUG-2513
   `autodev.yaml`. Document entry conditions (which `refine_current`
   exit, which intermediate states).
2. **Decision**: based on step 1, choose Option A (remove), Option B
   (document), or Option C (defer). Use `/ll:decide-issue` to record.
3. **Apply**:
   - **Option A**: delete `check_decision_before_size_review` and its
     inbound route. Run `ll-loop validate autodev`. Update tests in
     `scripts/tests/test_autodev_decision_gate.py` to assert the gate's
     absence.
   - **Option B**: add the `comment:` block to the YAML state. Add a
     pytest in `scripts/tests/test_autodev_decision_gate.py` that
     asserts the gate is reachable only from the documented entry
     conditions.
   - **Option C**: add a section to
     `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § "Decision gates"
     documenting the deferred status.
4. **Verify**: `python -m pytest scripts/tests/ -k autodev` passes;
   `ll-loop validate autodev` returns "autodev is valid".

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be
included in the Option B implementation. Without them the fix is
incomplete._

5. **Inline-`#` comment, NOT `comment:` key** — replace the drafted
   Option B spec (which shows a top-level `comment:` block). The current
   gate (autodev.yaml:560-568) uses an inline `#` comment at line 561-562;
   the sibling `check_decision_after_refine` (autodev.yaml:165-173) also
   uses inline `#`. Follow the convention. The drafted `comment:` block
   would parse as an unknown `StateConfig` key (`StateConfig` at
   schema.py:465-565 has no `comment` field; the issue's `schema.py:888`
   reference is `CommandEntry.comment`, not `ParameterSpec.comment`).

6. **Improve the comment content** — the drafted comment omits the
   contract entry conditions and upstream predecessor. Recommended
   replacement for the inline `#` block above the gate:
   ```yaml
   # Defense-in-depth for the pre-size-review path. Reachable only from
   # recheck_scores.on_no / recheck_scores.on_error (autodev.yaml:557-558)
   # when decision_needed was added during refine (e.g., a future decide
   # hook). The upstream check_decision_at_dequeue (BUG-2513) catches
   # every pre-refine decision_needed:true issue. Mirrors the
   # check_decision_after_refine defense-in-depth precedent.
   ```
   The comment must (a) reference BOTH inbound edges so future readers
   understand the contract, (b) name `check_decision_at_dequeue` as the
   predecessor that catches pre-refine `decision_needed:true`, and (c)
   reference BUG-1277 as the gate's origin (the issue that added it;
   currently no YAML comment preserves this history).

7. **Add `on_error: run_size_review`** — close the latent
   partial-route dead-end (currently only `on_yes`/`on_no` are defined;
   if `ll-issues check-flag` errors, the FSM loses the issue). Mirror
   the sibling gates' error fallbacks (`check_decision_after_refine.on_error:
   check_passed` at line 172; `run_size_review` is the natural
   counterpart here since `on_no` already lands on `run_size_review`).
   No validation rule fires on the current state, so this is purely
   structural — but `ll-loop validate autodev` will continue to return
   "autodev is valid" post-fix.

8. **Add new structural assertions** to `scripts/tests/test_builtin_loops.py`
   (sibling to existing tests at lines 2836-2868):
   - `test_recheck_scores_on_error_routes_to_check_decision_before_size_review`
     (mirror the existing `test_recheck_scores_on_no_routes_to_*` at line 2836)
   - `test_check_decision_before_size_review_on_error_routes_to_run_size_review`
     (mirror the existing `test_check_decision_after_refine_routes_correctly`
     pattern at lines 2597-2608)

9. **Add executor-driven test class** to `scripts/tests/test_autodev_decision_gate.py`
   (currently 301 lines, BUG-2513-scoped). Use the existing `_StubRunner`
   + `_state` + `_loop` + `_run_decision_chain` pattern. The new class
   should cover at least one `recheck_scores.on_error →
   check_decision_before_size_review → run_size_review` end-to-end path
   using `runner = _StubRunner(results=[("ll-issues check-flag", {"exit_code":
   2, "stderr": "issue not found"})])` (the same mock shape used at
   line 260-277 for BUG-2513's error-fallthrough test).

10. **Do NOT touch `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`** — the
    issue's Documentation subsection references a "Decision gates"
    section that does not exist in that guide. Per the wiring pass
    finding, this is a documentation phantom; the gate is already
    covered in `docs/guides/LOOPS_REFERENCE.md` autodev state-machine
    diagrams at lines 569-583, 900-933.

11. **Verify (extended)**:
    - `python -m pytest scripts/tests/test_builtin_loops.py -k autodev` passes
    - `python -m pytest scripts/tests/test_autodev_decision_gate.py` passes
    - `ll-loop validate autodev` returns "autodev is valid"
    - `grep -n "comment:" scripts/little_loops/loops/autodev.yaml | grep -v "^#"` returns nothing (no top-level `comment:` keys were accidentally introduced)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — Option A removes the gate;
  Option B adds a `comment:` to the gate.
- `scripts/tests/test_autodev_decision_gate.py` — Option A updates the
  "decision_needed=true → run_decide before refine_current" assertion
  suite to confirm no other path bypasses the upstream gate; Option B
  adds a new test for the documented entry conditions.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Option C adds a deferred-status note.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/recursive-refine.yaml` — has analogous
  pre-decision gate chain (`check_decision_needed` at lines 534, 536,
  538, 558 reached from `recheck_scores` at lines 438, 454–456, 458)
  but uses different state names; out of scope for BUG-2519 but worth
  a separate follow-on if the same defect class recurs (the
  `recursive-refine` chain already includes `on_error` routes on its
  `recheck_scores` predecessors).
- `scripts/little_loops/fsm/schema.py` — `StateConfig` definition at
  lines 465-565 has NO `comment` field (the `comment:` field at line
  888 belongs to `CommandEntry`, lines 882-892; `ParameterSpec` at
  lines 234-278 has no `comment` either). The issue's `schema.py:888`
  line reference is off; the conclusion (use inline `#` not `comment:`)
  is correct.
- `scripts/little_loops/fsm/validation.py` — no validation rule fires
  on the current or post-fix state. `_find_reachable_states`
  (lines 1200-1210) is WARNING-only and the state is already reachable;
  `_validate_partial_route_dead_end` (line 1558, MR-4) requires
  LLM-judged states and `check_decision_before_size_review` uses the
  `shell_exit` fragment (lib/common.yaml:15-21), so MR-4 does not
  apply. No validation work needed.
- `scripts/little_loops/loops/lib/common.yaml:15-21` — `shell_exit`
  fragment contract: "State must supply: action, on_yes, on_no (and
  optionally on_error, timeout)." `on_error` is optional, so the new
  `on_error: run_size_review` route is additive and within contract.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — sub-loop
  delegate; unchanged contract.
- `scripts/little_loops/fsm/executor.py` — runs FSM states; no change
  needed.
- `scripts/little_loops/cli/loop/_helpers.py` — invoked by `run_decide`;
  no change needed.

### Similar Patterns
- BUG-2513 (just-closed) — fixed `check_decision_after_refine`'s bypass
  by adding `check_decision_at_dequeue`. This issue is the follow-on for
  `check_decision_before_size_review`, which has the same defect class
  in the post-fix routing graph.
- `check_decision_after_refine` (in `autodev.yaml`) — the post-refine
  gate; BUG-2513 retained it as defense-in-depth (line 263-264 of the
  Resolution) for "flags added during refinement (e.g. by a future
  decide hook)". The same defense-in-depth argument applies to
  `check_decision_before_size_review` if Option B is chosen.

### Tests
- `scripts/tests/test_autodev_decision_gate.py` (added in BUG-2513)
  covers the new gate. Update it per Option A/B to cover this gate's
  reachability.

### Tests (added by `/ll:wire-issue`)

_Wiring pass added by `/ll:wire-issue`:_

**Existing assertions to retain** (no change needed):
- `test_builtin_loops.py:2836-2843` — `test_recheck_scores_on_no_routes_to_check_decision_before_size_review` (asserts `recheck_scores.on_no`)
- `test_builtin_loops.py:2845-2850` — `test_check_decision_before_size_review_uses_shell_exit_fragment` (asserts `fragment == "shell_exit"`)
- `test_builtin_loops.py:2852-2859` — `test_check_decision_before_size_review_on_yes_routes_to_run_decide` (asserts `on_yes == "run_decide"`)
- `test_builtin_loops.py:2861-2868` — `test_check_decision_before_size_review_on_no_routes_to_run_size_review` (asserts `on_no == "run_size_review"`)
- `test_builtin_loops.py:2360` — `test_required_states_exist` includes the gate in the required set
- `test_autodev_decision_gate.py:284-300` — `test_autodev_yaml_loads_and_validates` (validates after the fix; will continue to pass since no ERROR-level rule is affected)

**New assertions to add** (follow the `test_check_decision_after_refine_routes_correctly` pattern at `test_builtin_loops.py:2597-2608`):

1. `test_builtin_loops.py` (new) — `test_check_decision_before_size_review_on_error_routes_to_run_size_review` — structural assertion:
   ```python
   assert state.get("on_error") == "run_size_review"
   ```
   Mirrors the sibling gate's `on_error` assertion at line 2606. **No
   existing test asserts the absence of `on_error`, so adding the route
   will not break any assertion.**

2. `test_builtin_loops.py` (new) — `test_recheck_scores_on_error_routes_to_check_decision_before_size_review` — structural assertion:
   ```python
   assert state.get("on_error") == "check_decision_before_size_review"
   ```
   The `on_error` inbound edge from `recheck_scores` is currently
   untested (autodev.yaml:558). The `on_no` edge IS covered at line
   2836; this closes the symmetry gap.

3. `test_autodev_decision_gate.py` (new class) — `TestCheckDecisionBeforeSizeReview*` using the existing `_StubRunner` + `_state` + `_loop` + `_run_decision_chain` pattern (file is 301 lines, BUG-2513-scoped):
   - Structural tests mirroring `TestCheckDecisionAtDequeueStructural` (lines 101-185): state exists, predicate uses `ll-issues check-flag`, fragment is `shell_exit`, `on_yes` → `run_decide`, `on_no` → `run_size_review`, `on_error` → `run_size_review`
   - One executor-driven routing test mirroring `test_check_flag_error_falls_through_to_refine_current` (line 260): drives `recheck_scores.on_error → check_decision_before_size_review` with `check-flag` exit_code=2 and asserts `run_size_review` is reached (not `run_decide`)

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § "Decision gates" — link
  the closed BUG-2513 and this issue as a follow-on; document the
  post-BUG-2513 routing-graph rationale.
- `autodev-bug2501-kill-analysis.md` (repo root) — link this issue as
  the fix lands.

### Documentation (added by `/ll:wire-issue`)

_Wiring pass added by `/ll:wire-issue`:_

**Stale reference correction** — The `AUTOMATIC_HARNESSING_GUIDE.md` §
"Decision gates" reference in the issue's Documentation subsection has
no anchor: there is NO section by that name in the guide. The only
"Decision" match in the file is line 493's
`**Decision guide — when to reach for each phase:**` heading, which is
about FSM evaluator phases (check_stall / check_concrete / etc.) — not
about the `check_decision_*` gate family. Adding BUG-2519 to that
guide would require creating a new section that doesn't currently
exist. **Recommend removing the `AUTOMATIC_HARNESSING_GUIDE.md` line
from the Documentation subsection entirely**; the change is in-loop
only and the existing autodev state-machine diagrams in
`docs/guides/LOOPS_REFERENCE.md` (lines 569-583, 900-933) already cover
the gate. Flag for the implementer: this is a documentation-coupling
phantom — do not edit the guide as part of this fix.

**In-scope doc updates:**
- `docs/guides/LOOPS_REFERENCE.md:569-583, 900-933` — autodev
  state-machine diagrams already include
  `check_decision_before_size_review`. Verify the diagrams' note about
  `decision_needed` flow is still accurate post-fix (it should be; the
  fix is additive and does not change the gate's on_yes/on_no behavior).
- `autodev-bug2501-kill-analysis.md:189-207` — kill-analysis text is
  now stale with respect to `check_decision_after_refine`'s
  reachability (BUG-2513 added `check_decision_at_dequeue` upstream),
  but remains accurate for `check_decision_before_size_review`. The
  post-BUG-2519 fix does not change this. Out of scope for BUG-2519;
  flag as a separate cleanup task if the user wants the kill-analysis
  refreshed.
- `CHANGELOG.md` — no `[Unreleased]` section; add the BUG-2519 entry
  to the next release's `## [X.Y.Z] - DATE` section per
  `feedback_changelog_no_unreleased.md`. Out of scope for this issue's
  implementation steps; handled at release-prep time.

### Configuration
- N/A — no `ll-config.json` or schema changes.

## Impact

- **Priority**: P2 — defense-in-depth on a related-but-not-currently-affected
  gate. The killed run exhibited the post-refine-gate bypass (Mode B);
  this gate shares the structural defect class but was not the route
  the killed run took.
- **Effort**: Small — routing-graph analysis (1-2 hours) plus one of
  the three Options (each <1 hour).
- **Risk**: Low — Options A and B are mechanical changes to a single
  YAML file plus tests. Option C is documentation-only.
- **Breaking Change**: No — for any path where the gate was reachable
  pre-fix, it remains reachable (Option A removes dead code only; Option B
  documents the gate; Option C leaves it untouched).

## Status

**Open** | Created: 2026-07-07 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-07-07T17:00:00 - `51846f72-c135-4aae-98df-cfb6f2d84afe.jsonl`
- `/ll:wire-issue` - 2026-07-07T16:49:54 - `1d8b1b50-b1df-43ef-aca6-e22349113bf5.jsonl`
- `/ll:decide-issue` - 2026-07-07T16:38:20 - `8c62cce3-d86e-4ab6-b9a3-c43dfd5f7231.jsonl`
- `/ll:capture-issue` - 2026-07-07T14:50:00Z - `183e7df6-0517-4eb0-83d7-ab914af56328.jsonl`