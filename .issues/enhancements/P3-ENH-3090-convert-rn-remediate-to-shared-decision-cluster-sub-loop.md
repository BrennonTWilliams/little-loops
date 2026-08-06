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

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/rn-remediate.yaml` — the conversion.
- `scripts/little_loops/loops/autodev.yaml` — remove the stale parity comment only.

### Tests

- Whichever tests assert on `rn-remediate`'s inline cluster state names — enumerate
  during refinement. ENH-3075's Tests section is the model for the shape and scale
  of this surface.
- `TestBuiltinLoopReferencesResolve` and `TestBuiltinLoopFiles`
  (`scripts/tests/test_builtin_loops.py`) auto-cover unresolvable `loop:` targets
  and FSM validity; no new test needed for those.

### Documentation

- `docs/guides/LOOPS_REFERENCE.md` — `rn-remediate` decision-cluster prose.
- `CHANGELOG.md`

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
