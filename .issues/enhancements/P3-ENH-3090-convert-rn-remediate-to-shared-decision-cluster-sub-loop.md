---
id: ENH-3090
type: ENH
title: Convert rn-remediate's inline decision cluster to the shared decision sub-loop
priority: P3
status: open
discovered_date: 2026-08-06
discovered_by: pre-implementation-review
captured_at: '2026-08-06T18:10:00Z'
depends_on:
- ENH-3075
verify_verdict: VALID
relates_to:
- BUG-3065
- ENH-3075
- BUG-1416
- BUG-2595
- ENH-2443
- ENH-2446
- ENH-2717
labels:
- loops
- fsm
- decision-gate
- refactor
testable: true
decision_needed: false
confidence_score: 95
outcome_confidence: 70
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 20
---

# ENH-3090: Convert `rn-remediate`'s inline decision cluster to the shared decision sub-loop

## Summary

The decision cluster (decidability probe → deposit options → stall gate → decide →
post-decide assert) exists in three independent copies. BUG-3065 extracted it to
`oracles/resolve-decision.yaml` and adopted it in `refine-to-ready-issue.yaml`;
ENH-3075 converts `autodev.yaml`. This issue closes the sequence by converting the
third and last copy, in `rn-remediate.yaml`.

Duplication of these five bug-fix-derived guards (BUG-1416, BUG-2595, ENH-2443,
ENH-2446, ENH-2717) has already caused one shipped bug — a fix applied to one copy
and missed in another. Leaving exactly one duplicate behind is the worst resting
state: it is the case most likely to be forgotten, because the cluster will *look*
consolidated everywhere a reader is likely to check.

## Current Behavior

`rn-remediate.yaml` carries its own inline copy of the cluster. Verified state anchors
(2026-08-06):

| State | Line | Role |
|---|---|---|
| `check_decision_needed` | `:272` | first entry gate |
| `check_decision_decidable` | `:279` | decidability probe |
| `deposit_options` | `:306` | option deposit |
| `record_options_deposited` | `:321` | write-once marker |
| `check_open_question_progress` | `:340` | stall gate |
| `check_decision_needed_post` | `:733` | second entry gate |

ENH-3075's scope note cites three approximate regions (`~:275-370`, `~:633-741`,
`~:784-955`); the table above supersedes the first of those. **The decide and
post-decide-assert states have not been located yet** — enumerate them, and confirm
whether `check_decision_needed_post` re-enters the same cluster or a partial copy,
during refinement.

`autodev.yaml`'s `check_decision_decidable` carries a "parity insertion mirroring
rn-remediate" cross-reference comment pointing at this copy.

Once ENH-3075 lands, that comment goes stale in both directions: `autodev` no
longer has an inline block to mirror, and `rn-remediate` becomes the only place
the shape still exists.

**Line ranges above are unverified and were captured second-hand from ENH-3075's
scope note.** Re-derive them against the current file before planning the edit —
this issue has not had its own `/ll:refine-issue` pass.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- Confirmed anchors (unchanged since the issue's 2026-08-06 verification):
  `check_decision_needed:274`, `check_decision_decidable:281`, `deposit_options:308`,
  `record_options_deposited:323`, `check_open_question_progress:342`,
  `check_decision_needed_post:748`.
- The previously-unlocated `decide` state is at `rn-remediate.yaml:648`
  (`fragment: with_rate_limit_handling`, `action: /ll:decide-issue ${context.issue_id} --auto`,
  `on_yes/on_partial: re_assess`, `on_no: emit_needs_manual_review`,
  `on_error: emit_implement_failed`, `on_rate_limit_exhausted: rate_limit_diagnostic`).
- There is no "post-decide-assert" state in `rn-remediate.yaml` — no equivalent of
  `oracles/resolve-decision.yaml`'s `assert_decision_cleared` (the BUG-2595
  flag re-verify). Grep for `assert_decision`/`BUG-2595` in the file returns nothing.
  `decide.on_yes` routes straight to `re_assess:764`; the only post-decide safety
  net is `check_convergence`'s own `decision_needed` re-read at
  `rn-remediate.yaml:868,876` (`POST_DECISION=$(jq -r '.decision_needed // "false"' ...)`).
- `check_decision_needed_post:748` does **not** re-enter the 5-state cluster — it is
  a bare flag check (`ll-issues check-flag ${context.issue_id} decision_needed`)
  whose `on_yes` routes directly to `decide:648`, skipping
  `check_decision_decidable`/`deposit_options` entirely. Reached from
  `mark_refined:736` and `mark_wired:746`.
- A second direct-to-`decide` entry exists at `diagnose`'s classify route
  (`rn-remediate.yaml:442`, `DECIDE: decide`), fired when `check_decision_needed`'s
  dimensional analysis sets `DECISION_NEEDED=true` (`:414-415`). So there are
  three entries into `decide`, not one: the full cluster
  (`check_decision_needed:274 → check_decision_decidable:281 → ...`), and two
  direct entries (`check_decision_needed_post:748`, `diagnose`'s classify route
  at `:442`) that both skip the probe/deposit states — structurally identical to
  autodev's `triage_outcome_failure` direct entry (`skip_probe: "true"` case).
- Options-deposited marker literal is
  `${context.run_dir}/decide_options_deposited_${context.issue_id}.txt`
  (underscore-separated, `.txt` extension) — textually distinct from
  `oracles/resolve-decision.yaml`'s own marker,
  `${context.run_dir}/decide-options-deposited-${context.issue_id}` (hyphenated,
  no extension; `resolve-decision.yaml:59,101`). Sites: write at
  `rn-remediate.yaml:330` (`record_options_deposited`), reads at `:299`
  (`check_decision_decidable`), `:989` and `:1074` (both inside
  `emit_needs_manual_review`, discriminating its outcome token/handoff text).
  No clear/`rm -f` of this marker exists anywhere in the file — `rn-remediate`
  is invoked fresh per-issue by its parent (`rn-implement.yaml:757-764`), so
  per-issue filename scoping substitutes for the clear step autodev needs at
  its long-running dequeue loop.
- No post-decide escape path analogous to autodev's
  `recheck_after_decide.on_no: snap_and_size_review` exists. `decide.on_no`
  goes to `emit_needs_manual_review:653`; after `decide.on_yes`, flow re-enters
  `re_assess:764 → verify_re_assess_scores:777 → check_convergence:803`, whose
  failure-to-converge branches route through `check_remediation_budget:902` to
  either retry `diagnose` (route target at `:915`, state defined at `:379`) or
  `emit_stalled_needs_decompose:959` → `failed`.
  rn-remediate's "escape on failed re-score after decide" is this generic
  convergence/budget machinery, not a decide-specific fork.

## Expected Behavior

`rn-remediate.yaml` reaches the same behavior through `loop: oracles/resolve-decision`
call states. `oracles/resolve-decision.yaml` is the single definition of the
cluster in the tree, and a future fix to any of its five embedded guards is applied
exactly once.

## Motivation

This is drift prevention, not a user-visible defect — the same rationale as
ENH-3075, with the added argument that a lone remaining duplicate is more
dangerous than three obvious ones.

## Proposed Solution

Follow the conversion pattern ENH-3075 establishes, and **do not re-derive it**.
By the time this issue starts, ENH-3075 will have settled the two hard questions
on the `autodev` path:

- **Rate-limit exhaustion cannot propagate out of a `loop:` state.** ENH-3075
  decided Option A: the sub-loop writes a
  `${context.run_dir}/decide-rate-limited-${issue_id}` marker before exiting
  `failed`, and the caller gates on it. Reuse that handshake; the sub-loop side is
  already built by then, so this issue only adds the caller-side gate.
- **The `assert_decision_cleared` reorder.** ENH-3075 accepted the loss of the
  sub-threshold `snap_and_size_review` escape and recorded it in a Behavior Parity
  table. Check whether `rn-remediate` has an analogous escape on its own
  post-decide path; if it does, make the same call and record it the same way. If
  it does not, note that explicitly rather than leaving it unstated.

Read ENH-3075's `### Rate-limit exhaustion cannot propagate out of a `loop:` state`
and `### The `assert_decision_cleared` reorder` sections before starting.

### Entry points and markers

`rn-remediate`'s entry points into the cluster, and whether any of them needs the
`skip_probe: "true"` binding (as `autodev`'s `triage_outcome_failure` does), must
be enumerated during refinement. Its options-deposited marker — if it keeps a
distinct literal from `autodev`'s `autodev-decide-options-deposited` — needs the
same three-site rename treatment (read / write / per-iteration clear), including
the same `$CURRENT`-vs-`${captured.input.output}` trap ENH-3075 documents: at the
dequeue point the captured input still holds the *previous* iteration's ID.

Grep the marker literal before editing. A missed **read** site silently disables
ENH-2443's write-once bound without failing any test.

## Scope Boundaries

**In scope**: `rn-remediate.yaml`'s conversion to the sub-loop, deletion of its
inline cluster states, its marker rename, the caller-side rate-limit gate, the
associated test rewrite, and the `rn-remediate` sections of `LOOPS_REFERENCE.md`.
Also: removing the now-stale "parity insertion mirroring rn-remediate"
cross-reference comment left in `autodev.yaml` by ENH-3075.

**Out of scope**:

- Any change to `oracles/resolve-decision.yaml`'s contract. If this conversion
  needs one, that is a signal the extraction boundary was drawn wrong — raise it
  rather than widening the sub-loop for a third caller.
- `rn-implement.yaml`'s separate outcome-token routing chain (see ENH-3084).

## Acceptance Criteria

1. `rn-remediate.yaml` contains no inline decidability-probe / deposit-options /
   stall-gate / decide / post-decide-assert states; all are reached via
   `loop: oracles/resolve-decision` call states.
2. `oracles/resolve-decision.yaml` is unchanged by this issue (see Scope
   Boundaries — a needed change is a signal, not a task).
3. The options-deposited marker literal is renamed at every site, and the old
   literal appears nowhere in `scripts/little_loops/` or `scripts/tests/`.
   Grep-enforceable.
4. Any per-iteration marker clear uses the correct current-issue shell variable,
   not the stale `${captured.input.output}`, with a test asserting the exact form.
5. The rate-limit marker handshake established by ENH-3075 is wired caller-side,
   with both branches (marker present → terminate; absent → normal failure route)
   covered by tests.
6. Any behavior difference introduced by the assert reorder is recorded in a
   Behavior Parity table, or its absence is explicitly noted.
7. Existing `rn-remediate` decision-cluster test assertions are **rewritten** to
   target the sub-loop, not deleted to make the suite pass.
8. `ll-loop validate` passes for `rn-remediate.yaml`.
9. `autodev.yaml`'s stale "parity insertion mirroring rn-remediate" comment is
   removed.
   > ⚠ Superseded — phrase not found verbatim in autodev.yaml
10. `docs/guides/LOOPS_REFERENCE.md`'s `rn-remediate` cluster prose is updated.
11. A manual `ll-loop run rn-remediate` completes at least one issue end to end —
    there is no automated end-to-end coverage for this loop either.
12. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 — no user-visible defect. Pure drift prevention, deferred
  behind ENH-3075 because converting it means re-verifying a separate remediation
  loop's routing on top of an already Medium-High-risk rewrite.
- **Effort**: Medium-Large — smaller than ENH-3075 in design work (both hard
  questions are pre-answered) but comparable in mechanical and test surface.
- **Risk**: Medium — `rn-remediate` is the remediation path for failed
  implementations, so a routing defect here degrades recovery rather than the
  happy path. No end-to-end coverage.
- **Breaking Change**: No.

## Program Design

The deliverable is loop YAML, not Python — no new modules, types, or functions. The
engine facts this conversion rides on are identical to ENH-3075's; read that issue's
`## Program Design` before planning the edit.

### Types

- `StateConfig.loop: str` — the sub-loop reference each converted call state carries.
- `StateConfig.with_: dict[str, str]` — the `{issue_id, skip_probe}` bindings crossing the
  boundary.
- `ExecutionResult.failure_terminal: bool` (`scripts/little_loops/fsm/types.py:60`) — a
  **bool**, not a terminal name. This is the type fact that rules out discriminating
  rate-limit exhaustion from decision-unresolved by inspecting the child's terminal, and
  therefore the reason the marker handshake exists at all.

### Signatures

- `_execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None`
  (`scripts/little_loops/fsm/executor.py:820`, routing at `:1058-1086`) — returns a routing
  target directly from `child_result.terminated_by`, producing no `ActionResult`. Unchanged
  by this issue; listed because that is precisely why the 429 interception at
  `executor.py:1673-1685` (gated on `action_result is not None`) can never see a child.
- `resolve_loop_path(name_or_path: str, loops_dir: Path) -> Path`
  (`scripts/little_loops/fsm/loop_paths.py:19`) — resolves `oracles/resolve-decision`.

### Call Path

`rn-remediate.yaml`'s `check_decision_needed` (`:272`) and `check_decision_needed_post`
(`:733`) are the two entry gates; each currently falls into the inline cluster —
`check_decision_decidable` (`:279`) → `deposit_options` (`:306`) →
`record_options_deposited` (`:321`) → `check_open_question_progress` (`:340`) → decide.
Post-conversion each entry gate routes instead to a `loop: oracles/resolve-decision` call
state → `_execute_sub_loop` (`scripts/little_loops/fsm/executor.py:820`) →
`resolve_loop_path` (`scripts/little_loops/fsm/loop_paths.py:19`) →
`oracles/resolve-decision.yaml`, returning through the caller-side rate-limit marker gate
before reaching the normal unresolved-decision route.

**This section is deliberately thin.** The design work that remains is enumeration, not
invention: the entry-point list, the marker literal(s), and the test surface. It needs a
`/ll:refine-issue` pass against the real file, not a second design pass — every design
question was answered by BUG-3065 and ENH-3075.

### Behavior Parity

_To be filled during refinement._ ENH-3075 establishes the format and two entries that
may or may not have `rn-remediate` analogues:

| Behavior | Owner after conversion | Status |
|---|---|---|
| Post-decide assert reordering ahead of the score recheck | sub-loop | **Unknown for `rn-remediate`** — determine whether it has an escape path analogous to `autodev`'s `recheck_after_decide.on_no: snap_and_size_review`. If yes, accept the loss as ENH-3075 did and record it here. If no, state that explicitly. |
| Rate-limit exhaustion terminating the run rather than deferring the issue | caller-side gate on the sub-loop's marker | Inherited from ENH-3075 (Option A); wire the caller-side half here. |
| `autodev.yaml`'s "parity insertion mirroring rn-remediate" cross-reference | deleted | This conversion is what makes the comment meaningless. |

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Behavior Parity row 1 resolved**: `rn-remediate` has no post-decide-assert
  escape path analogous to `autodev`'s `recheck_after_decide.on_no:
  snap_and_size_review` — decide-failure and re-score-failure both fall through
  to the generic `check_convergence` → `check_remediation_budget` →
  `emit_stalled_needs_decompose` cycle shared by every remediation branch (see
  Current Behavior findings). State that explicitly in the Behavior Parity
  table rather than leaving it "Unknown".
- `oracles/resolve-decision.yaml` contract (the sub-loop being adopted):
  `initial: route_entry` (`:10`), `max_steps: 20`, `timeout: 3600` (`:11-12`),
  `scope: [".issues/", "${context.run_dir}"]` (`:16-18`). Parameters:
  `issue_id` (string, required, `:20-22`), `skip_probe` (string, optional,
  `default: "false"`, `:23-26`). `route_entry` (`:34-45`) branches on
  `${context.skip_probe}` to `run_decide` (yes) or `check_decision_decidable`
  (no). Internal chain: `check_decision_decidable:47 → deposit_options:69 →
  record_options_deposited:91 → check_open_question_progress:104` (loops back
  or forwards to `run_decide:145`). `run_decide` routes `next`/`on_error` to
  `assert_decision_cleared:185`, and `on_rate_limit_exhausted` to
  `mark_decide_rate_limited:165` (writes
  `${context.run_dir}/decide-rate-limited-${context.issue_id}` then `next:
  failed`). `assert_decision_cleared` re-checks the `decision_needed` flag:
  `on_yes: failed` (still armed), `on_no: done` (cleared), `on_error: failed`.
  Terminals `done:206`/`failed:209`, both `terminal: true`.
- Call-state contract confirmed by `_execute_sub_loop` routing
  (`scripts/little_loops/fsm/executor.py:1058-1086`): a `loop:` state has no
  `next`/`on_yes`/`on_no` of its own — it routes on `child_result.terminated_by`
  to `on_success` (terminal, non-failure), `on_failure` (terminal, failure),
  `on_error` (error, falling back to `on_failure` if absent), or
  `extra_routes["timeout"]`/`on_failure` (timeout/max_steps/max_iterations).
  `with:` bindings are validated against the child's declared `parameters:` at
  load time — unknown keys or missing required keys are structural-rule errors
  (`scripts/little_loops/fsm/validation/structural_rules.py:258-330`).
  `loop:` and `action:` are mutually exclusive (`:472-480`); `with:` and
  `context_passthrough:` are mutually exclusive (`:537-548`).
- Existing adopters disagree on the caller-side rate-limit gate:
  `refine-to-ready-issue.yaml` (BUG-3065, first adopter) has none — its three
  `resolve_decision_*` call states route `on_failure`/`on_error` straight to
  `record_decision_unresolved` (`:213-214,263-264,442-443`).
  `autodev.yaml` (ENH-3075, landed — comment headers at `:539,561,577` cite it)
  added `check_decide_rate_limited` (`:576-596`), reached from both
  `resolve_decision` and `resolve_decision_direct`'s `on_failure`/`on_error`:
  it checks `[ -f ${context.run_dir}/decide-rate-limited-${captured.input.output} ]`,
  routing `on_yes: done` (graceful terminate) / `on_no: record_decision_unresolved`.
  This is the pattern ENH-3090 must add caller-side per AC5.
- `autodev.yaml`'s two call states for reference:
  `resolve_decision:538-557` (`with: {issue_id}`, relies on sub-loop default
  `skip_probe: "false"`) and `resolve_decision_direct:559-574` (`with:
  {issue_id, skip_probe: "true"}`, entered from `triage_outcome_failure.on_yes`
  — the direct-entry pattern `rn-remediate`'s `check_decision_needed_post:748`
  and `diagnose`'s `:442` classify route both need). Both set a unique
  `capture:` per call state and route `on_failure`/`on_error` to the *same*
  target (never treated distinctly).

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/rn-remediate.yaml` — the conversion.
- `scripts/little_loops/loops/autodev.yaml` — remove the stale parity comment only.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py:1158` — stale comment citing
  `rn-remediate.yaml:907` for the `IMPLEMENT_FAILED` outcome token; the line
  number will drift once the inline cluster is removed and the file shrinks
  [Agent 2 finding, side-effect surface].

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-implement.yaml:757-764` — the sole caller
  of `rn-remediate.yaml`, via a `loop: rn-remediate` call state with `with:`
  bindings (`issue_id`, `readiness_threshold`, `outcome_threshold`,
  `max_remediation_passes`, `run_dir`, `skip_learning_gate`). It enters at
  `rn-remediate`'s `initial: ensure_formatted`, never at a specific cluster
  state, so the conversion breaks no external `next:`/`on_yes` edge into the
  cluster — confirmed by Agent 2 [side-effect surface finding]. No change
  needed to `rn-implement.yaml` itself, but its caller-side contract tests
  (see Tests below) confirm this invariant and should stay green.

### Tests

- Whichever tests assert on `rn-remediate`'s inline cluster state names — enumerate
  during refinement. ENH-3075's Tests section is the model for the shape and scale
  of this surface.
- `TestBuiltinLoopReferencesResolve` and `TestBuiltinLoopFiles`
  (`scripts/tests/test_builtin_loops.py`) auto-cover unresolvable `loop:` targets
  and FSM validity; no new test needed for those.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_remediate.py:1198-1211`
  (`test_mr1_non_llm_evaluators_present`) — the state-name-to-evaluator-type
  dict at `:1206-1207` keys `check_decision_needed` and
  `check_decision_decidable`; the `check_decision_decidable` entry dangles
  once that state is deleted [Agent 3 finding — this is the same dict already
  cited in the Current Behavior research findings, called out here by exact
  test name since it is easy to miss inside an MR-1-compliance class not
  named for the decision cluster].
- `scripts/tests/test_rn_remediate.py:174-179`
  (`TestReadinessAndDecisionGates.test_check_decision_needed_routes_yes_to_decide`)
  — asserts `check_decision_needed.on_yes == "check_decision_decidable"`; must
  retarget to whatever `loop: oracles/resolve-decision` call-state name
  replaces it, mirroring `test_check_decision_at_dequeue_on_yes_routes_to_resolve_decision`
  in `test_autodev_decision_gate.py:135-146` [Agent 3 finding].
- `scripts/tests/test_fsm_topology.py` — no `TestRnRemediateSmoke`-equivalent
  exists; add one mirroring `TestAutodevSmoke.test_autodev_topology`
  (`:233-259`), which asserts an exact `len(topo["states"])` count with a
  comment documenting every state removed/added by the conversion [Agent 3
  finding, new test].
- `scripts/tests/test_rn_implement.py:242-259`
  (`TestSubLoopDelegation.test_run_remediation_is_loop_delegation` /
  `test_run_remediation_has_with_bindings`) — the caller-side contract test
  for `rn-implement.yaml`'s `loop: rn-remediate` call state and its `with:`
  bindings; unaffected by an internal cluster conversion but should be run to
  confirm the invariant holds (no change to `rn-remediate`'s own
  `parameters:` block) [Agent 1 + Agent 3 findings].
- No FSMExecutor-driven routing test exists for `rn-remediate`'s decision
  cluster today (`test_rn_remediate.py` coverage is all static
  YAML-structural via `_load_loop()`) — a gap relative to the `autodev`
  precedent's `TestAssertDecisionClearedRouting` /
  `TestCheckDecisionAtDequeueRouting` classes
  (`test_autodev_decision_gate.py:197-283,1021-1080+`), which drive a minimal
  `_loop()`/`_state()`/`_StubRunner` fixture through `FSMExecutor`. Consider a
  mirrored `TestRnRemediateDecisionGateRouting` class if AC11's manual
  end-to-end run is meant to be backed by an automated equivalent later
  [Agent 3 finding — optional, not required by any AC as stated].

### Documentation

- `docs/guides/LOOPS_REFERENCE.md` — `rn-remediate` decision-cluster prose.
- `CHANGELOG.md`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:1851` — "The `check_decision_decidable` gate in
  `rn-remediate.yaml` (and its parity insertion in `autodev.yaml`) calls this
  [`ll-issues check-decidable`] as a shell action" — stale once
  `check_decision_decidable` no longer lives in `rn-remediate.yaml` [Agent 2
  finding].
- `docs/reference/CLI.md:1911` — cites an exact stale line anchor,
  "`check_decision_decidable` gate in `rn-remediate.yaml:263`" — both the
  file attribution and the line number go stale [Agent 2 finding].
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — the `rn-remediate` four-phase
  narrative and outcome-token table still describe the cluster in terms of
  inline states (e.g. Dimensional Diagnosis / DECIDE); behaviorally
  unchanged post-conversion but no longer an accurate description of the
  file's literal state list [Agent 2 finding].

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

### Tests (research findings)

- `scripts/tests/test_rn_remediate.py` is the pre-conversion inline-cluster test
  surface this issue's rewrite targets: `TestReadinessAndDecisionGates:101-186`
  (`check_decision_needed` routing), `TestCheckDecisionDecidableState:193-233`
  (asserts the `decide_options_deposited_${context.issue_id}.txt` marker path
  literal at `:227-230`), `TestDepositOptionsState`/
  `TestRecordOptionsDepositedState:240-303` (`on_rate_limit_exhausted:
  rate_limit_diagnostic` at `:272-273` — note this is `rn-remediate`'s existing
  generic rate-limit handling, distinct from the marker-writing
  `mark_decide_rate_limited` handshake `oracles/resolve-decision.yaml` uses),
  `TestDecisionDecidableFlow:308-324` (full chain walk),
  `TestCheckDecisionDecidableCoverageAware:327-339` (ENH-2446 coverage-aware
  chaining), a state-name-to-evaluator-type dict at `:1206-1207`, and
  `emit_needs_manual_review` marker-reader tests at `:342-368,2004-2009`
  (downstream readers of the same marker literal, not part of the cluster
  itself but grep-hits for the literal that must be renamed everywhere).
- Rewrite-target precedent from ENH-3075's `autodev.yaml` conversion, in
  `scripts/tests/test_autodev_decision_gate.py`: deleted-state tests
  (`TestAssertDecisionClearedStructural:940-983`, asserting the removed state
  is both absent from `states` and unreferenced by any edge) paired with
  routing-continuity tests on the surviving caller edge
  (`test_recheck_after_decide_on_yes_routes_to_implement_current`); and
  call-state routing-shape tests
  (`test_check_decision_at_dequeue_on_yes_routes_to_resolve_decision:135-143`,
  mirrored at `:353-361`).
- The sub-loop itself has its own dedicated test class,
  `TestResolveDecisionOracle` (`scripts/tests/test_builtin_loops.py:2322-2461`)
  — `test_autodev_decision_gate.py:1010-1018` explicitly cites it as the
  replacement location for deleted caller-side routing assertions ("The 5
  routing assertions that used to live in
  TestCheckDecisionAfterDecideErrorStructural are replaced by
  test_run_decide_on_error_routes_to_assert_decision_cleared in
  TestResolveDecisionOracle"). No new sub-loop test class is needed for
  ENH-3090 since `oracles/resolve-decision.yaml` is unchanged (Scope
  Boundaries) — only `rn-remediate`'s caller-side tests need rewriting.

### Documentation (research findings)

- `docs/guides/LOOPS_REFERENCE.md:81` — one-line reference-table entry for
  `oracles/resolve-decision`, currently naming only `refine-to-ready-issue` as
  an adopter (predates ENH-3075 and this issue).
- `docs/guides/LOOPS_REFERENCE.md:143` — full prose paragraph under a
  `**Decision resolution (BUG-3065)**` heading describing
  `refine-to-ready-issue`'s three-gate wiring; this is the section AC10's
  `rn-remediate` prose update should extend, alongside adding `rn-remediate`
  and `autodev` to the `:81` adopter line.

## Related Issues

- ENH-3075 — converts `autodev.yaml`; **must land first** (`depends_on`), and
  settles the two design questions this issue inherits.
- BUG-3065 — authored `oracles/resolve-decision.yaml` and defines the sub-loop
  contract.
- BUG-1416 / BUG-2595 — the shipped bug caused by this cluster's duplication.

## Status

- [ ] Not started — **needs a `/ll:refine-issue` pass**. Line ranges, entry
      points, marker literals, and the test surface are all unverified;
      this issue was filed to hold the scope, not to be implemented as written.

## Verification Notes

_Added by `/ll:verify-issues --check --auto` — 2026-08-08:_

The great majority of this issue's line-number anchors (rn-remediate.yaml,
autodev.yaml, oracles/resolve-decision.yaml, executor.py, types.py,
loop_paths.py, structural_rules.py, and the cited test files) were re-checked
against the current tree and are still accurate. Two anchors had drifted and
were corrected in place:

- `emit_stalled_needs_decompose` is at `rn-remediate.yaml:959`, not `:919`
  (the `check_remediation_budget.on_no` route target line, `:919`, is
  unchanged; only the target state's own definition line moved).
- `TestCheckDecisionDecidableCoverageAware` spans `test_rn_remediate.py:327-339`,
  not `:327-348` — the claimed range bled into the next test class.

Also corrected: frontmatter `depends_on: []` was inconsistent with this
issue's own "Related Issues" section, which states ENH-3075 "must land first
(`depends_on`)". `ll-issues show ENH-3075` confirms it is now `done`, so the
dependency is satisfied — `depends_on` was updated to `[ENH-3075]` to make
the frontmatter match the issue's stated premise.

Separately confirmed still-stale (not fixed here — already tracked in this
issue's own Documentation/Integration Map sections as AC10 work):
`docs/reference/CLI.md:1851,1911` still describe `autodev.yaml` as carrying
a "parity insertion" of `check_decision_decidable`, which ENH-3075 already
removed; `:1911`'s `rn-remediate.yaml:263` sub-citation is also wrong (actual
line is `:281`).


## Session Log
- `/ll:confidence-check` - 2026-08-09T05:09:39 - `b7457e6e-9654-45e5-a9bd-43e1bcddbd28.jsonl`
- `/ll:verify-issues` - 2026-08-09T05:07:12 - `1a0323b3-fb2f-47b3-b5e2-6334cdd695e1.jsonl`
- `/ll:refine-issue` - 2026-08-09T05:01:09 - `5d39a81f-e4c2-4c4f-b723-9102112bb63c.jsonl`
- `/ll:verify-issues` - 2026-08-09T04:56:48 - `492270bb-612b-4566-9401-b7e8119d8d26.jsonl`
- `/ll:wire-issue` - 2026-08-09T04:49:58 - `2e8e3d48-c705-4949-b0f6-0778032e9f73.jsonl`
- `/ll:refine-issue` - 2026-08-09T04:40:22 - `fd4e0063-8cc2-4878-b795-7d9b91a89ae5.jsonl`
- `/ll:refine-issue` - 2026-08-09T04:40:14 - `fd4e0063-8cc2-4878-b795-7d9b91a89ae5.jsonl`

## Documentation

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- `docs/guides/LOOPS_REFERENCE.md:1062` — the **autodev** section's "Decidability
  gate parity (ENH-2443, BUG-2605)" paragraph itself contains a cross-reference
  into `rn-remediate`'s inline cluster: "the same `ll-issues check-decidable
  <ID>` deterministic pre-check used by `rn-remediate`". This is a second,
  previously-untracked stale site — distinct from the `rn-remediate` cluster
  prose at `:143` already listed above, and distinct from the two
  `docs/reference/CLI.md` sites already noted in Verification Notes. AC10 as
  currently scoped ("`rn-remediate` cluster prose") does not obviously cover
  this line since it lives in the *autodev* paragraph, not the rn-remediate
  one; either broaden AC10's read or add an explicit sub-bullet during
  implementation. [pattern-finder finding, 2026-08-09]
