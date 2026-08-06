---
id: ENH-3075
title: Convert autodev's inline decision cluster to the shared decision sub-loop
type: ENH
priority: P3
status: open
discovered_by: pre-implementation-review
discovered_date: 2026-08-05
captured_at: '2026-08-05T22:40:00Z'
depends_on:
- BUG-3065
relates_to:
- BUG-3065
- BUG-1416
- BUG-2595
- ENH-2443
- ENH-2446
- ENH-2717
- ENH-1415
- FEAT-937
labels:
- loops
- fsm
- decision-gate
- refactor
testable: true
decision_needed: false
---

# ENH-3075: Convert `autodev`'s inline decision cluster to the shared decision sub-loop

## Summary

BUG-3065 authors `scripts/little_loops/loops/oracles/resolve-decision.yaml` — a sub-loop extracted
from `autodev.yaml`'s inline decision cluster — and adopts it in `refine-to-ready-issue.yaml` to fix
the dead-end bug. It deliberately **does not** touch `autodev.yaml`, to keep the P3 bug fix behind a
small diff.

That leaves the codebase in a transitional state: `autodev.yaml` still carries its own inline copy of
the cluster, so the same logic exists twice (three times counting `rn-remediate.yaml`'s independent
copy). This issue closes that gap by converting `autodev.yaml` to call the sub-loop, which is the
whole point of BUG-3065's Option B decision — duplication of these five bug-fix-derived guards
(BUG-1416, BUG-2595, ENH-2443, ENH-2446, ENH-2717) is exactly what has already caused a shipped bug
once.

**Read BUG-3065's `### The extraction boundary`, `### Marker semantics`, and
`### Rate-limit exhaustion` first** — they define the sub-loop contract this conversion must fit.

## Current Behavior

`autodev.yaml` contains the cluster inline across four blocks:

| Block | Lines (approx., drifts) | States |
|---|---|---|
| Decidability probe + deposit | `:529-573` | `check_decision_decidable`, `deposit_options`, `record_options_deposited` |
| Stall gate | `:579-608` | `check_open_question_progress` |
| Decide | `:610-624`, `:627-637` | `run_decide`, `check_decision_after_decide_error` |
| Post-decide assert | `:685-697` | `assert_decision_cleared` |

Five entry points route into it: `check_decision_at_dequeue` (`:236`),
`check_decision_after_refine` (`:491`), `check_decision_before_size_review` (`:526`),
`check_decision_before_size_review`'s sibling gate (`:1218`), and `triage_outcome_failure` (`:1236`
— routes **directly** to `run_decide`, bypassing the probe).

## Expected Behavior

`autodev.yaml` reaches the same behavior through `loop: oracles/resolve-decision` call states, with
`mark_decide_ran`, `rerun_confidence_after_decide`, `recheck_after_decide`, and
`record_decision_unresolved` remaining caller-side. The inline cluster states are deleted from
`autodev.yaml`'s own `states:` block.

## Proposed Solution

### Conversion steps

1. Replace the four inline blocks with `loop: oracles/resolve-decision` call states binding
   `with: {issue_id: "${captured.input.output}"}`. Route `on_success` → `mark_decide_ran` and
   `on_failure` → `record_decision_unresolved`.
2. Retarget the four probe-first entry points (`:236`, `:491`, `:526`, `:1218`) to the call state.
3. Bind `skip_probe: "true"` at `triage_outcome_failure` (`:1236`) only — this is the fifth entry
   point BUG-3065's `route_entry` demultiplexer exists to serve.
4. Delete `check_decision_after_decide_error` (`:627-637`); its ENH-2717 short-circuit collapses into
   the sub-loop's `assert_decision_cleared`. See BUG-3065's `### The extraction boundary` for the one
   accepted behavioral difference.
5. Rename the options-deposited marker to the per-issue form at all **three** live sites (below), so
   `autodev` and the sub-loop share one marker rather than each keeping its own.
6. Handle the rate-limit discrimination problem (below) and the `assert` reorder consequence (below).

### Marker rename — three sites, and a `$CURRENT` trap

The literal `autodev-decide-options-deposited` appears at three functional sites, all of which must
move together to the per-issue name the sub-loop already writes:

| Site | Line | Role |
|---|---|---|
| `check_decision_decidable` | `:540` | reads the marker (`[ -f ... ] && exit 0` short-circuit) |
| `record_options_deposited` | `:573` | writes it |
| `dequeue_next` | `:105` | clears it per-iteration |

Sites 1 and 2 are deleted outright by the conversion (they move into the sub-loop). **Site 3 stays**,
and it carries a silent-failure trap:

`dequeue_next`'s `capture: input` is written **by** `dequeue_next`, so at the point of the `rm -f`
the interpolated `${captured.input.output}` still holds the **previous** iteration's issue ID. Using
it would clear the wrong file and leave the current issue's marker stale, silently suppressing
`deposit_options` on this issue. The only correct ID in scope there is the shell-local `$CURRENT`
(`autodev.yaml:94`), which must be escaped `$${CURRENT}` so FSM interpolation does not eat it.

Why the clear is still needed at all, given a per-issue name: it is what lets a **re-dequeued** issue
retry `deposit_options` in the same run. It is not what enforces ENH-2443's write-once bound — the
bound comes from the marker's *presence*. (BUG-3065's `### Marker semantics` states this inverted;
that section is corrected there.)

Note this deviates from `dequeue_next`'s own stated convention (comments at `:130`, `:157`) that
per-issue filename-scoped markers "self-isolate" and are deliberately **not** cleared. The deviation
is intentional — those markers gate one-shot-per-issue behavior, this one gates a retry that should
be available again on re-dequeue. Say so in the comment.

Also sweep the non-functional references that go stale: `rn-remediate.yaml`'s parity copy and its
cross-reference comment, `test_builtin_loops.py` / `test_autodev_decision_gate.py` assertions on the
literal string, and `docs/guides/LOOPS_REFERENCE.md`'s cluster prose. Grep the literal before
editing; a missed read site silently disables the write-once bound.

### Rate-limit exhaustion cannot propagate out of a `loop:` state

_This is the hard part of the conversion and must be designed, not assumed._

Today `run_decide` (`:624`) and `deposit_options` (`:565`) carry `on_rate_limit_exhausted: done`,
which gracefully terminates the **entire** autodev run when the 429 budget is spent. Post-conversion
those states live in the child, where BUG-3065 requires them to route to `failed` instead (routing to
`done` would hand autodev a false success with `decision_needed` still armed).

The natural-looking recovery — re-declaring `on_rate_limit_exhausted` on autodev's `loop:` call state
— **does not work**:

- `_execute_sub_loop` (`scripts/little_loops/fsm/executor.py:1058-1086`) returns a routing target
  directly from `child_result.terminated_by`; it never produces an `ActionResult`.
- The 429 interception at `executor.py:1673-1685` is gated on `action_result is not None` and
  `exit_code != 0`, so a `loop:` state is never classified as rate-limited.
- The child's exit is also indistinguishable after the fact: `captured.<state>.terminated_by` is
  `"terminal"` for every terminal exit, and `captured.<state>.failure_terminal` is a **bool**
  (`fsm/types.py:60`, set at `executor.py:3206`), not the terminal's name — so a distinct
  `rate_limited` failure terminal in the child is invisible to the parent.

(`recursive-refine.yaml:236`'s existing `on_rate_limit_exhausted: dequeue_next` on its `loop:` state
is dead config for the same reason — pre-existing, out of scope, but worth a comment noting it.)

**Consequence if left unhandled:** 429 exhaustion inside decide stops looking like "gracefully end
the run" and starts looking like "defer this issue as `decision_unresolved`, dequeue the next one" —
which will immediately hit the same 429 on the next issue and walk the whole queue into deferral.

**Options:**

- **A (recommended)** — the sub-loop writes a `${context.run_dir}/decide-rate-limited-${issue_id}`
  marker before exiting `failed`; autodev's `on_failure` routes to a small gate that checks for it
  and terminates the run rather than deferring. Uses the inherited `run_dir` and matches the
  codebase's existing marker-handshake idiom.
- **B** — accept the degradation, delete the `on_rate_limit_exhausted: done` semantics from the
  autodev path, and document it.

Pick one explicitly during implementation; do not leave it implicit.

### The `assert_decision_cleared` reorder loses a `snap_and_size_review` escape

BUG-3065's `### The extraction boundary` moves `assert_decision_cleared` to sit directly after
`run_decide` inside the sub-loop, and calls this "a tightening, not a loss." **That holds only for
the score-passing branch.**

Today's chain is `run_decide → mark_decide_ran → rerun_confidence_after_decide → recheck_after_decide`,
and `recheck_after_decide.on_no: snap_and_size_review` (`autodev.yaml:684`) **bypasses
`assert_decision_cleared` entirely**. So an issue with a still-armed flag *and* failing scores goes to
size review today — ENH-1415's "on failure, route to snap_and_size_review rather than dropping the
issue."

Post-conversion the assert fires first, so that case returns `failed` → `record_decision_unresolved`
→ deferred, and never reaches `snap_and_size_review`.

This is a defensible trade (an issue whose decision genuinely did not resolve is not obviously
improved by decomposition), but it is a **behavior change on a guarded path**, not a pure tightening.
Record it in the Behavior Parity table as accepted, or add a caller-side branch off `on_failure` that
routes to `snap_and_size_review` when readiness/outcome scores are below threshold.

### Preserved behaviors

Everything in BUG-3065's `### Behavior Parity` table marked `autodev` stays caller-side and must
survive: `mark_decide_ran` → `autodev-decide-ran` (ENH-1415's re-entry short-circuit),
`rerun_confidence_after_decide`, `recheck_after_decide` (reads `${context.readiness_threshold}`,
routes `on_no: snap_and_size_review`), and `record_decision_unresolved`'s defer +
`DECISION_UNRESOLVED` ledger entry that `auto-refine-and-implement.yaml:840` consumes.

`deposit_options`'s `on_partial: record_options_deposited` (`:564`) must survive the move — BUG-3065
carries it into the sub-loop; verify it is not lost when the inline copy is deleted.

### Cross-nesting check

After BUG-3065, `refine-to-ready-issue` also calls the decision sub-loop, and `autodev.yaml:385`
(`refine_current`) calls `refine-to-ready-issue`. Two consequences to design for:

- `autodev`'s `check_decision_after_refine` (`:491`) becomes largely dead on the post-refine path —
  the child already cleared the flag. Keep it as defense in depth (its own comment already frames it
  that way), but stop treating it as the primary resolution path.
- `mark_decide_ran` is caller-side, so a decide performed **inside** `refine-to-ready-issue`'s nested
  sub-loop call does not set `autodev-decide-ran`. If `recheck_after_size_review` later routes back to
  `decide_current`, ENH-1415's short-circuit will not fire and decide could run a second time. The
  `assert_decision_cleared` / `check-decidable` guards make that a no-op rather than a correctness
  bug, but confirm it — or have the sub-loop write the `autodev-decide-ran` marker itself, which the
  inherited `run_dir` makes possible.
- No infinite nesting: the decision sub-loop is a leaf and never calls back. There is no depth cap in
  `executor.py` (`_depth` at `:409` is used only for event forwarding), so verify this by inspection
  rather than relying on an engine guarantee.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/autodev.yaml` — the conversion itself.
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — only if the rate-limit marker
  (Option A) or the `autodev-decide-ran` write is added to the sub-loop.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/scan-and-implement.yaml:77` — calls `loop: autodev`; must observe the
  same `on_success`/`on_failure` outcomes after the conversion.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:840` — consumes the
  `DECISION_UNRESOLVED` ledger; the caller-side `record_decision_unresolved` must keep writing it.
- `scripts/little_loops/loops/rn-remediate.yaml` (~`:275-370`, `~:633-741`, `~:784-955`) — a third,
  independent inline copy of the same cluster shape, cross-referenced by a "parity insertion
  mirroring rn-remediate" comment in `autodev.yaml`'s `check_decision_decidable`. **Out of scope**,
  but it becomes the last remaining duplicate once this issue lands, and its parity comment goes
  stale. File a follow-up rather than expanding scope here.

### Tests

This is the large surface BUG-3065 deliberately defers. All of the following assert on inline cluster
state names inside `autodev.yaml`'s own `states:` dict and **will break**:

`scripts/tests/test_autodev_decision_gate.py` (1211 lines):
- `run_decide` `on_error` routing (~`:1066-1068`)
- `assert_decision_cleared` existence + 5 routing assertions (~`:967-1018`)
- `check_decision_after_decide_error` existence + 5 routing assertions (~`:1072-1128`) — **delete
  outright**, the state is removed; replace with a sub-loop-internal assertion that
  `run_decide.on_error == "assert_decision_cleared"`.
- `record_decision_unresolved` action-content + defer assertions (~`:1022-1041`) — stays caller-side,
  should survive.
- `check_decision_decidable` as a target string at ~`:143`, `~:360-361` — retarget to the call state.
- `TestCheckDecisionAtDequeueRouting` (~`:203-280`) and `TestAssertDecisionClearedRouting`
  (~`:1138-1211`) build their own fixture FSMs and won't break, but encode the same state names as
  literals and will drift out of sync with the real topology.

`scripts/tests/test_builtin_loops.py`:
- `test_required_states_exist` (~`:4215-4249`) — `required` set literal including `run_decide`,
  `mark_decide_ran`, `rerun_confidence_after_decide`; KeyError-class break once these move.
- `test_check_decision_at_dequeue_...` (~`:4337`), `test_check_decision_after_refine_...` (~`:5498`),
  `test_check_decision_before_size_review_...` (~`:6007`),
  `test_triage_outcome_failure_on_yes_routes_to_run_decide` (~`:6046`),
  `test_decide_current_on_yes_routes_to_check_decision_decidable` (~`:6304`),
  `test_check_decision_decidable_state_exists_and_routes` (~`:6314`),
  `test_deposit_options_state_exists_and_routes` (~`:6324`),
  `test_check_open_question_progress_...` (~`:6341-6360`),
  `test_run_decide_uses_with_rate_limit_handling_fragment` /
  `test_run_decide_next_routes_to_mark_decide_ran` /
  `test_run_decide_on_error_routes_to_implement_current` /
  `test_run_decide_on_rate_limit_exhausted_routes_to_done` (~`:6375-6396`),
  `test_mark_decide_ran_state_exists` / `..._next_routes_to_rerun_confidence_after_decide` /
  `..._writes_decide_ran_flag` (~`:6460-6479`),
  `test_record_decision_unresolved_defers_via_set_status` (~`:5359-5362`) and further
  `record_decision_unresolved` assertions (~`:5638`, `~:6767`) — all need rewriting to assert against
  `oracles/resolve-decision.yaml` instead.

**New coverage:**
- `triage_outcome_failure`'s `with:` block binds `skip_probe: "true"` and the other four entry points
  do not.
- `dequeue_next`'s marker clear targets the per-issue path and uses `$${CURRENT}`, not
  `${captured.input.output}` — the regression guard for the trap above.
- Whichever rate-limit option is chosen (marker handshake or documented degradation).

**Auto-covered, no new test needed:** `TestBuiltinLoopReferencesResolve.test_all_static_loop_references_resolve`
(~`:12963`) fails on an unresolvable `loop:` target; `TestBuiltinLoopFiles` (`:29-38`) runs
`test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`, and
`test_no_failure_edge_routes_to_a_success_terminal` over every builtin loop.

No end-to-end coverage exists — no test runs `ll-loop run autodev` live. Verification is structural
plus a manual run.

### Documentation

- `docs/guides/LOOPS_REFERENCE.md:1000-1045` — the `autodev` FSM-flow ASCII diagram spells out
  `run_decide → mark_decide_ran → rerun_confidence_after_decide → recheck_after_decide` by exact
  state name, multiple times.
- `docs/guides/LOOPS_REFERENCE.md:1047` — "Diagram omissions" paragraph, the densest prose
  description of the cluster's internal wiring by exact state name.
- `docs/guides/LOOPS_REFERENCE.md:1053` — "Outcome failure triage" paragraph documenting
  `triage_outcome_failure`'s direct `run_decide` route.
- `docs/guides/LOOPS_REFERENCE.md:1055` — "Decidability gate parity" paragraph claims all four
  `decision_needed: true` entry points share `check_decision_decidable` before `run_decide`. Already
  inaccurate against `triage_outcome_failure`'s direct route (pre-existing); correct it regardless,
  then re-verify post-conversion.
- `CHANGELOG.md`

## Program Design

The deliverable is loop YAML, not Python — no new modules, types, or functions. What the design must
pin down is which existing engine paths the conversion rides on and what it cannot rely on.

### Types

- `StateConfig.loop: str` — the sub-loop reference each converted call state carries
- `StateConfig.with_: dict[str, str]` — `{issue_id, skip_probe}` bindings crossing the boundary
- `ExecutionResult.failure_terminal: bool` (`scripts/little_loops/fsm/types.py:60`) — a **bool**, not
  a terminal name. This is the type fact that rules out discriminating rate-limit exhaustion from
  decision-unresolved via the terminal name; see `### Rate-limit exhaustion cannot propagate`.

### Signatures

- `_execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None`
  (`scripts/little_loops/fsm/executor.py:820`, routing at `:1058-1086`) — returns a routing target
  directly from `child_result.terminated_by`, producing no `ActionResult`; unchanged by this issue,
  listed because that is precisely why the 429 interception at `:1673-1685` cannot see a child.
- `resolve_loop_path(name_or_path: str, loops_dir: Path) -> Path`
  (`scripts/little_loops/fsm/loop_paths.py:19`) — resolves `oracles/resolve-decision`.

### Call Path

Per entry point: `check_decision_at_dequeue` | `check_decision_after_refine` |
`check_decision_before_size_review` (×2) → the `loop:` call state → `_execute_sub_loop` →
`oracles/resolve-decision` → `on_success: mark_decide_ran` | `on_failure: record_decision_unresolved`.
`triage_outcome_failure` enters the same call state with `skip_probe: "true"`.

Terminal contract inherited from BUG-3065: sub-loop `done` = `decision_needed` cleared;
`failed` = still armed after decide, decide never reached, or 429 budget exhausted — the three are
**not distinguishable by the caller** without the marker handshake in Option A above.

## Scope Boundaries

**In scope:** `autodev.yaml`'s conversion to the sub-loop, deletion of its inline cluster states and
`check_decision_after_decide_error`, the options-deposited marker rename at its three sites, the
rate-limit and assert-reorder design decisions on the `autodev` path, the associated test rewrite in
`test_autodev_decision_gate.py` and `test_builtin_loops.py`, and the `autodev` sections of
`LOOPS_REFERENCE.md`.

**Out of scope:**

- Authoring `oracles/resolve-decision.yaml` and adopting it in `refine-to-ready-issue.yaml` — that is
  BUG-3065, which must land first (`depends_on`).
- `rn-remediate.yaml`'s third independent copy of the cluster. It becomes the last remaining
  duplicate once this lands; file a follow-up rather than widening this change, since converting it
  means re-verifying a separate remediation loop's routing on top of an already Medium-High-risk
  rewrite.
- Fixing `recursive-refine.yaml:236`'s dead `on_rate_limit_exhausted` config. Note it in a comment
  where noticed; removing it is a separate, unrelated correctness cleanup.
- Any change to the sub-loop's contract itself beyond the two additions this conversion may require
  (the rate-limit marker under Option A, and optionally writing `autodev-decide-ran` from the child).

## Impact

- **Priority**: P3 — no user-visible defect; this is drift prevention for a cluster whose duplication
  has already caused one shipped bug (BUG-1416 → BUG-2595). The user-facing dead-end is fixed by
  BUG-3065 without this.
- **Effort**: Large — the conversion itself is mechanical, but the test-rewrite surface spans two
  files and ~25 assertions, and two design questions (rate-limit propagation, assert reorder) must be
  settled first.
- **Risk**: Medium-High — `autodev` is the main implementation path and its decision cluster encodes
  five distinct prior bug fixes. No end-to-end coverage backstops the structural rewrite.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.issues/bugs/P3-BUG-3065-refine-to-ready-issue-dead-ends-on-decision-needed.md` | Defines the sub-loop contract this conversion adopts |
| `docs/guides/LOOPS_REFERENCE.md` | `autodev` FSM flow + decision-cluster prose |
| `.claude/CLAUDE.md` | § Loop Authoring — `ll-loop validate` enforcement |

## Status

- [ ] Not started
