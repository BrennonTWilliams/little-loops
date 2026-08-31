---
id: ENH-3366
type: ENH
priority: P3
status: open
captured_at: '2026-08-30T23:30:00Z'
discovered_date: 2026-08-30
discovered_by: audit-loop-run
relates_to:
- ENH-1679
- ENH-2005
decision_needed: false
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3366: `delegate`(autodev) verdict is laundered through `recheck_set`

## Summary

In `scripts/little_loops/loops/auto-refine-and-implement.yaml`, the
`delegate` state that invokes the `autodev` sub-loop (line 299) routes both
outcomes to the same next state:

```
on_success: recheck_set   # line 320
on_failure: recheck_set   # line 321
```

`recheck_set` (line 324) only re-resolves the sprint/EPIC's current issue
list to look for newly-added descendants to re-dispatch — it never reads any
`subloop_outcome_autodev`-style sidecar, so it cannot tell whether `autodev`
actually reached a successful terminal or its `failed` failure terminal.
Note the laundering is **narrower than a full crash/failure collapse**:
`on_error: record_error` (line 322) already routes executor-level crashes to
a distinct recording state (test-enforced by
`test_delegate_crash_routes_to_record_error`). The laundered cases are
exactly (a) `autodev` reaching its `failed` terminal
(`failure_terminal=True`), and (b) budget-class terminations
(`timeout`/`max_steps`) plus other non-terminal classes (interrupted,
signal), all of which fall through the compiled `on_no` → `on_failure`
fallback into `recheck_set`. This is the same
verdict-laundering shape [[ENH-1679]] fixed for `refine_current`'s sub-loop,
but on this different state, and it does not qualify for the ENH-2005 sidecar
exemption `/ll:audit-loop-run` checks for (the shared next state's action
does not contain `subloop_outcome_`).

## Current Behavior

`delegate`'s `on_success` and `on_failure` both route to `recheck_set` (lines
320-321). `recheck_set` only re-resolves the sprint/EPIC's descendant set to
find newly-added children; it never reads any `autodev` outcome sidecar, so
whether `autodev` reached its clean `done` terminal or its `failed` failure
terminal (or was budget-exhausted) is indistinguishable by the time execution
reaches `recheck_set` — those paths look identical. (Executor-level crashes
are already distinct: `on_error: record_error`, line 322.)

One consequence of the current collapse is load-bearing: because compiled
`on_no` falls back to `on_failure`, budget-class terminations
(`timeout`/`max_steps`, `executor.py:1184-1191`) currently land in
`recheck_set`, whose ENH-2686 block folds back `autodev-queue.txt` mid-drain
residuals for re-dispatch. Any fix that redirects `on_failure` must preserve
that healing path for budget-class terminations (see Program Design).

## Expected Behavior

`autodev`'s real terminal verdict should be recoverable downstream — either
by giving `on_success`/`on_failure` distinct next states, or by having
`autodev`'s own finalize write a `subloop_outcome_autodev.txt` sidecar that
`recheck_set` (or a new intermediate state) reads before deciding whether to
re-dispatch, following the same artifact-channel pattern already used for
`auto-refine-and-implement`'s own outcome (`subloop_outcome_auto-refine-and-implement.txt`,
read by `sprint-refine-and-implement.yaml`'s `read_outcome` state).

## Proposed Solution

Two viable resolutions surfaced by research into how this codebase already
fixes this exact defect shape:

**Option A**: Differentiate `delegate`'s `on_success`/`on_failure` into
distinct target states, mirroring ENH-1679's actual fix for `autodev.yaml`'s
own `refine_current` state (lines 470-539) — no new artifact, no change to
`autodev.yaml`. Each target state would decide, using only the executor's
existing `terminated_by`/`failure_terminal` classification already available
via `${captured.delegate.*}` (`executor.py:1147-1196`), whether to proceed
into `recheck_set` (success) or route to a failure-handling state (failure)
before ever reaching `recheck_set`.

> **Selected:** Option A — differentiated `on_success`/`on_failure` routing off the
> executor's existing `terminated_by`/`failure_terminal` classification, mirroring
> ENH-1679's `refine_current` fix in the same subsystem with no new artifact and a
> directly transplantable 5-test regression model (score 12/12 vs. Option B's 7/12).

**Option B**: Have `autodev.yaml`'s `finalize_done` state write a new
`subloop_outcome_autodev.txt` sidecar (a one-line `printf '%s\n' "$VERDICT"`
addition, since `$VERDICT` is already computed there), and have
`recheck_set` (or a new intermediate state) read it before deciding whether
to re-dispatch — matching the existing `auto-refine-and-implement` →
`sprint-refine-and-implement` sidecar convention (ENH-2005).

**Recommended**: Option A — it is the only precedent in this codebase for
this *exact* defect shape (a sub-loop join needing to distinguish
success/failure at the routing level itself), it lives in the same
subsystem (`autodev.yaml`) already, requires no new artifact or change to
`autodev.yaml`, and has an established 5-test regression model to follow
(`test_refine_current_has_success_and_failure_routes` and its four siblings
in `scripts/tests/test_builtin_loops.py`). Option B is the better fit when a
state genuinely needs the child's *full* verdict detail preserved for a
later read by another state (as `sprint-refine-and-implement`'s
`read_outcome` does) — that need has not been demonstrated for
`recheck_set`, which only needs a success/crash distinction to decide
whether to re-dispatch.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-30.

**Selected**: Option A — differentiate `delegate`'s `on_success`/`on_failure` into distinct target states.

**Reasoning**: Option A is the only precedent in this codebase for this exact defect shape (a sub-loop join needing to distinguish success/failure at the routing level itself), it lives in the same subsystem (`autodev.yaml`) that ENH-1679 already fixed identically, requires no new artifact or change to `autodev.yaml` itself, and reuses the executor's already-computed `${captured.delegate.*}` classification (`executor.py:1147-1196`), which is confirmed non-degenerate for this exact call boundary. Option B is a well-established convention elsewhere (ENH-2005) but would require editing `autodev.yaml`'s standalone-used, actively load-bearing `finalize_done` state and adding new conditional-branch logic to `recheck_set` beyond a simple read — more integration surface for no offsetting benefit, since `recheck_set` only needs a success/crash distinction, not the child's full verdict detail.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B | 2/3 | 2/3 | 2/3 | 1/3 | 7/12 |

**Key evidence**:
- For the selected Option A: `autodev.yaml:487-503` (`refine_current`) is the exact pattern to mirror, already documenting anti-laundering intent and a BUG-2611 `on_no:` guard; `executor.py:1147-1196` already classifies `terminated_by`/`failure_terminal` for the `delegate`→`autodev` boundary specifically; `test_refine_current_has_success_and_failure_routes` and its 4 siblings (`test_builtin_loops.py:6103-6161`) are a directly transplantable test model. ~33 of ~41 `loop:` call states repo-wide already use distinct `on_success`/`on_failure` routing — this is the dominant convention.
- For the rejected alternative: `auto-refine-and-implement.yaml:1027-1032` and `sprint-refine-and-implement.yaml:39-49` are a verbatim sidecar-write/read template, and `autodev.yaml:2463-2477` already computes `$VERDICT` ready to redirect — but the fix would touch `autodev.yaml`'s `finalize_done`, a large state exercised by every standalone `ll-loop run autodev` invocation, and `recheck_set`'s existing EPIC-scope/cycle-cap/diff logic means the sidecar read needs new conditional branching (closer to `rn-implement.yaml:1298`'s precedent than to a trivial `cat`).

## Scope Boundaries

- Does not change `recheck_set`'s re-dispatch semantics for EPIC descendant
  resolution (ENH-2615) — only how it (or an intermediate state) learns
  `autodev`'s prior verdict before deciding to re-dispatch.
- Does not add a new terminal-verdict enum value beyond what's needed to
  distinguish an `autodev` crash from a clean pass at this join point; it
  reuses the existing sidecar-file pattern rather than inventing new
  `summary.json` fields.
- Does not touch `refine_current`'s sub-loop join, which [[ENH-1679]]
  already fixed.

## Program Design

### Signatures

- `delegate_failed(terminated_by: str) -> finalize | recheck_set` — new shell state branching on the executor's termination classification read from `${captured.delegate.terminated_by}`: `terminated_by == "terminal"` records `autodev_failed` then routes to `finalize`; every other class routes to `recheck_set` (anchors: `auto-refine-and-implement.yaml:320-321`, `executor.py:1147`).
- No new artifact or sidecar file. `delegate`'s `on_success`/`on_failure` (`auto-refine-and-implement.yaml:320-321`) split into distinct targets: `on_success: recheck_set` unchanged; `on_failure:` the new `delegate_failed` state above.
- **`delegate_failed` does not need to re-derive success vs. failure** — reaching `on_failure` *is* the executor's classification (`executor.py:1170-1176` already branched on `failure_terminal`; non-degenerate for this boundary via `autodev.yaml`'s `done`/`failed` terminals, lines 2497-2500). What it reads from `${captured.delegate.*}` is **`terminated_by`**, to separate:
  - `terminated_by == "terminal"` (genuine `failed` terminal): record `autodev_failed` against the dispatched set (sibling artifact to `auto-refine-and-implement-errored.txt`) → `next: finalize`, mirroring `record_error`'s record-then-finalize shape. Finalize's ledger diff stays the authoritative closure verdict (per the loop's own documented design), so the run still emits a summary / partial-with-errors and still reaches `merge_epic_branch` — do **not** land this edge directly on a `failure: true` terminal, which would silently drop finalize/merge for partial runs.
  - any other `terminated_by` (budget exhaustion `timeout`/`max_steps`, interrupted, signal — everything reaching here via the `on_no` → `on_failure` fallback, `executor.py:1184-1196`): route to `recheck_set`, preserving ENH-2686's mid-drain residual fold-back (`autodev-queue.txt` re-dispatch). Alternatively, declare `on_timeout: recheck_set` on `delegate` (the ENH-3019 extra route the executor already supports) and let `delegate_failed` handle only the remainder — implementer's choice, but the budget-class path MUST keep reaching `recheck_set` either way.
- **BUG-2611 constraint (carried from the mirrored `refine_current` pattern)**: do NOT add an explicit `on_no:` to `delegate` — schema compiles `on_no = on_no or on_failure`, and an explicit `on_no` would shadow the new `on_failure` route. The flip side of that same fallback: every non-terminal, non-error termination class flows into `delegate_failed`, whose recording logic must tolerate them (hence the `terminated_by` branch above).

### Call Path

`delegate` -> (`on_success`, unchanged) `recheck_set`; `delegate` -> (`on_failure`) `delegate_failed` -> branch on `${captured.delegate.terminated_by}`: genuine `failed` terminal → record `autodev_failed` → `finalize`; budget/signal classes → `recheck_set` (ENH-2686 residual healing preserved). Distinct from the current unconditional fan-in where both `on_success` and `on_failure` reach `recheck_set`. `on_error: record_error` unchanged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- ENH-1679's actual fix (`autodev.yaml`'s `refine_current` state, lines 470-539) is differentiated `on_success`/`on_failure`/`on_error` routing at the join itself — it never introduced or reads a `subloop_outcome_` sidecar. This is the convention `/ll:decide-issue` selected (Option A) for this issue; the sidecar convention (ENH-2005, used by `sprint-refine-and-implement.yaml`'s `delegate`/`read_outcome` and `rn-implement.yaml`'s `run_remediation`/`classify_remediation`) was the rejected alternative (Option B).
- The Signatures/Call Path above describe the selected Option A only — no new signature or artifact, only differentiated `on_success`/`on_failure` targets consuming the executor's existing `${captured.delegate.*}` classification (`executor.py:1147-1196`).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — the
  sub-loop-invoking state (lines 299-322) and `recheck_set` state (lines
  324-390); no change to `scripts/little_loops/loops/autodev.yaml` (the
  rejected Option B would have touched autodev's finalize state)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._execute_sub_loop()`
  (line 914) and its `on_success`/`on_failure`/`on_error` classification
  (lines 1160-1196) is what the selected fix reads from via
  `${captured.delegate.*}`
- `skills/audit-loop-run/SKILL.md` (Step 8, lines 329-350) — the ENH-2005
  sidecar-exemption check this issue's own text cites; the selected fix
  satisfies Step 8's laundering check by never collapsing
  `on_success`/`on_failure` in the first place, the same way `refine_current`
  does

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — has its
  own, structurally distinct `delegate` state (lines 24-37) that invokes
  `auto-refine-and-implement` as a sub-loop and reads
  `subloop_outcome_auto-refine-and-implement.txt` via `read_outcome`; reads
  this file's *overall* outcome (already ENH-2005-covered), not the internal
  `delegate`/`recheck_set` routing this issue changes — no code change
  required here, listed for awareness only [Agent 1 finding]

### Conventions in Force
- Two established, working conventions for a sub-loop join needing to
  distinguish real success from failure exist in this codebase today, and
  they are **not** the same convention: (1) differentiated
  `on_success`/`on_failure`/`on_error` routing at the join itself —
  `autodev.yaml`'s `refine_current` (ENH-1679/ENH-2727, both closed); (2) a
  `subloop_outcome_<name>.txt` sidecar the child's own finalize writes,
  read by a shared `on_success`==`on_failure` target while `on_error` stays
  distinct — `sprint-refine-and-implement.yaml`'s `delegate`/`read_outcome`
  and `rn-implement.yaml`'s `run_remediation`/`classify_remediation`
  (ENH-2005, closed).
- `TestSubloopSidecarContract` (`scripts/tests/test_builtin_loops.py:490`)
  already enforces convention (2) mechanically for `rn-remediate`,
  `rn-decompose`, and `oracles/code-run-gate` — its `SUBLOOPS` tuple does
  not include `auto-refine-and-implement`/`autodev`; Option B would be a
  natural (not required) candidate for extending that tuple.
- An existing test, `test_delegate_crash_routes_to_record_error`
  (`test_builtin_loops.py:4300`), currently asserts today's laundered shape
  (`on_success == on_failure == "recheck_set"`) as correct/intentional —
  whichever option is chosen, this test's assertions will need to change.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — the `auto-refine-and-implement` FSM-flow
  diagram (~lines 972-978) shows a single `on_success / on_failure →
  recheck_set` arrow, and the Notes prose (~line 997) repeats the collapsed
  description; both need updating once the routes diverge [Agent 2 finding]
- `docs/ARCHITECTURE.md` — Epic-branch integration section (~lines 452-454)
  describes "After each `delegate` pass, `recheck_set` re-resolves..." with
  the same implicit collapsed-route framing; needs the same update
  [Agent 2 finding]
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — the loop's
  own top-of-file `description:` block (~lines 48-54, the ENH-2615
  paragraph) states "after each delegate pass, recheck_set re-resolves...";
  update alongside the state-comment rewrite already scoped by this issue
  [Agent 2 finding]

### Tests
- `test_refine_current_has_success_and_failure_routes`,
  `test_refine_current_failure_routes_to_skip_inflight`,
  `test_refine_current_error_routes_to_skip_inflight_infra`,
  `test_refine_current_has_no_explicit_on_no`,
  `test_refine_current_compiled_on_no_resolves_to_skip_inflight`
  (`test_builtin_loops.py:6103-6163`) — the regression-test model for
  Option A
- `test_delegate_does_not_launder_subloop_verdict`
  (`test_builtin_loops.py:5430`) — the regression-test model for Option B,
  written against `sprint-refine-and-implement.yaml`'s analogous `delegate`
  state
- `test_delegate_crash_routes_to_record_error` (`test_builtin_loops.py:4300`)
  — must be updated regardless of which option is chosen
- `TestSubloopSidecarContract` (`test_builtin_loops.py:490`) — only
  relevant if Option B is chosen and its `SUBLOOPS` coverage is extended;
  confirmed its `SUBLOOPS` tuple (`test_builtin_loops.py:511`) is
  `("rn-remediate", "rn-decompose", "oracles/code-run-gate")` and does not
  cover `auto-refine-and-implement`/`autodev` today — Option A needs no
  change here [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `TestBuiltinLoopFiles.test_no_failure_edge_routes_to_a_success_terminal`
  (`test_builtin_loops.py:74+`, ENH-2825) — fires only when a failure edge's
  *direct* target is a success terminal (confirmed: it does not follow
  chains, so `record_error → next: finalize` passes today with no exemption
  entry). The chosen design (`on_failure → delegate_failed`, a non-terminal
  intermediate that records then routes to `finalize`/`recheck_set`) is
  clean under this test with no exemption needed — it would only fail if the
  edge were pointed directly at `finalize` [Agent 3 finding; verified
  against the test body during review]
- New state-existence/structure tests for the new failure-handling state
  itself, mirroring `test_skip_inflight_state_exists`,
  `test_skip_inflight_is_shell_action`, and
  `test_skip_inflight_writes_skipped_file` (`test_builtin_loops.py:6163+`)
  — `refine_current`'s companion-state test pattern to transplant once the
  new state's name is chosen [Agent 3 finding]
- `test_required_states_exist` (`test_builtin_loops.py:4222-4237`) — a
  minimum-set (`required - actual`) check, not exhaustive; won't break from
  a new state, but its `required_states` set is the idiomatic place to add
  the new failure-handling state's name once chosen [Agent 3 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation. No existing `## Implementation Steps` section exists in this issue; the Program Design / Call Path sections above cover the routing change itself — these are the completeness touchpoints:_

- Update `docs/guides/LOOPS_REFERENCE.md` — the `auto-refine-and-implement` FSM-flow diagram and Notes prose describing the collapsed `on_success / on_failure → recheck_set` route
- Update `docs/ARCHITECTURE.md` — Epic-branch integration section's collapsed-route description
- Update `scripts/little_loops/loops/auto-refine-and-implement.yaml`'s own top-of-file `description:` block (ENH-2615 paragraph)
- Confirm `delegate.on_failure` points at `delegate_failed` (a non-terminal), never directly at `finalize` — `test_no_failure_edge_routes_to_a_success_terminal` fires on direct-to-success-terminal edges only, so the record-then-finalize shape needs no exemption entry (same as `record_error` today)
- Preserve the budget-class → `recheck_set` path (ENH-2686 residual fold-back): either branch on `${captured.delegate.terminated_by}` inside `delegate_failed`, or declare `on_timeout: recheck_set` on `delegate` (ENH-3019 route) — and add a regression test asserting it, since no existing test covers timeout-class routing through this join
- Do NOT add an explicit `on_no:` to `delegate` (BUG-2611 — it would shadow the new `on_failure`)
- Write state-existence/structure tests for `delegate_failed`, mirroring `test_skip_inflight_state_exists` / `test_skip_inflight_is_shell_action` / `test_skip_inflight_writes_skipped_file`
- Add `delegate_failed` to `test_required_states_exist`'s `required_states` set

## Impact

- **Priority**: P3 — matches [[ENH-1679]]'s severity class (same defect
  shape, different state); doesn't block the run today since `recheck_set`'s
  own `on_error` already routes to `verify` regardless, and executor-level
  crashes are already caught by `on_error: record_error` — but `autodev`
  reaching its `failed` failure terminal (or being budget-exhausted)
  currently produces no distinguishable signal from a clean success at this
  join point.

## Status

**Open** | Created: 2026-08-30 | Priority: P3

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-08-30 — supersedes the 2026-08-30 03:11:18 STOP result_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 86/100 → HIGH

Both gaps from the prior run are resolved: `ll-issues check-design ENH-3366`
now exits 0 (Program Design carries a signature-shaped `delegate_failed(...)`
line), and `format-check`'s `unapplied_decision` is empty (the Integration
Map's "Files to Modify" bullet no longer names the rejected option's
`finalize_done` identifier unmarked). Criterion C (Ambiguity) is uncapped
accordingly: 10/25 → 25/25, raising Outcome Confidence 71 → 86. No open gaps
remain.


## Session Log
- `/ll:confidence-check` - 2026-08-31T03:34:23 - `754758f7-a27d-41c2-ba70-fc1192723658.jsonl`
- `/ll:confidence-check` - 2026-08-31T03:11:18 - `29e8f5ee-bb5d-4aac-ae78-4403d15301ef.jsonl`
- `/ll:wire-issue` - 2026-08-31T02:56:39 - `3198a6b2-0ff9-49c6-a768-b2979f52ed21.jsonl`
- `/ll:decide-issue` - 2026-08-31T02:46:15 - `2778d8be-8e6e-4975-8f6c-4273dcc76d08.jsonl`
- `/ll:refine-issue` - 2026-08-31T02:37:53 - `80c0d0f5-6988-4121-a3c7-d08dabaee7ea.jsonl`
- `/ll:refine-issue` - 2026-08-31T02:36:37 - `b1737911-44d2-40e3-9bd5-5d8a15c8f475.jsonl`
- `/ll:format-issue` - 2026-08-31T02:10:25 - `816b6544-6e69-4192-a4ac-f797f3d82975.jsonl`
