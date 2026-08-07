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
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- Line-range verification against current `autodev.yaml` (2026-08-06): all four inline blocks still present and structurally unchanged, only shifted 1-2 lines from unrelated intervening edits — `check_decision_decidable`/`deposit_options`/`record_options_deposited` now `:529-574` (was `:529-573`); `check_open_question_progress` body `:580-608` (comment starts `:576`); `run_decide` now ends `:625` (was `:624`); `assert_decision_cleared` now `:687-699` (was `:685-697`).
- All five entry-point line numbers (`:236`, `:491`, `:526`, `:1218`, `:1236`) verified exact, zero drift, against current `autodev.yaml`.

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **Entry-point line drift (verified 2026-08-07)** — the two tail entry points moved +28 lines since this issue's block ranges were cited, caused by ENH-3084's `check_learning_gate_infra` (`:943`) and `mark_gate_infra` (`:955`) insertion. `check_decision_before_size_review.on_yes` is now `:1246` (state `:1236-1248`; issue cites `:1218`); `triage_outcome_failure.on_yes: run_decide` is now `:1264` (state `:1250-1266`; issue cites `:1236`). The three earlier entry points are unchanged: `check_decision_at_dequeue` `:236`, `check_decision_after_refine` `:491`, `decide_current.on_yes` `:526` — note `:526` is `decide_current.on_yes`, not `check_decision_before_size_review` (that state is the `:1236-1248` one); the issue's five-entry-point list conflates the two gates. Routing substance is unchanged — all four probe-first entries still target `check_decision_decidable`, `triage_outcome_failure` still routes directly to `run_decide`.
- **`dequeue_next`'s marker clear confirmed current** (`autodev.yaml:105`): `rm -f ${context.run_dir}/autodev-decide-options-deposited` uses the flat marker name, not `$CURRENT` and not `${captured.input.output}`. The trap described in the issue (at the `rm -f` point, `captured.input.output` holds the *previous* iteration's ID — the capture is written by `dequeue_next` itself at `:154`/`:156`) is real and current. Post-conversion the clear targets the per-issue path with bareword `$CURRENT` as AC 4 requires.

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

> **Decided 2026-08-06 (pre-implementation review): Option A.**
>
> Option B is not a documented degradation, it is an operational failure. Once the 429
> budget is spent, *every* subsequent issue hits the same exhaustion the moment it reaches
> decide — so B does not defer one issue, it walks the entire remaining queue into
> `decision_unresolved` in rapid succession, each one burning a dequeue and writing a
> `DECISION_UNRESOLVED` ledger entry that `auto-refine-and-implement.yaml:840` will act on.
> The operator is then left with a backlog of issues marked deferred-for-decision whose
> actual cause was a rate limit, and no signal distinguishing them. That is precisely the
> misclassification failure mode ENH-3084 exists to fix on the learning-gate axis; do not
> introduce a fresh instance of it here.
>
> Option A's cost is one marker write in the sub-loop and one gate state in autodev, using
> the inherited `${context.run_dir}` and the marker-handshake idiom this cluster already
> uses in four other places. The asymmetry in cost is large and one-sided.
>
> **Implementation shape:** `oracles/resolve-decision.yaml` writes
> `${context.run_dir}/decide-rate-limited-${context.issue_id}` immediately before routing to
> its `failed` terminal on `on_rate_limit_exhausted` (both sites — `deposit_options` and
> `run_decide`). Autodev's `on_failure` routes to a new `check_decide_rate_limited` gate
> that tests for the file: present → terminate the run (preserving today's
> `on_rate_limit_exhausted: done` semantics), absent → `record_decision_unresolved` as
> before. The marker is per-issue and lives under the run dir, so it needs no explicit
> clearing.

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

> **Decided 2026-08-06 (pre-implementation review): accept the change; record it in the
> Behavior Parity table. Do not add the caller-side score branch.**
>
> The alternative — branching off `on_failure` on readiness/outcome scores to reach
> `snap_and_size_review` — requires the caller to re-read the scores and re-implement a
> threshold comparison that `recheck_after_decide` already owns, purely to reconstruct a
> path the sub-loop boundary removed. That reintroduces exactly the caller/cluster coupling
> the extraction exists to eliminate, and it does so on the `on_failure` edge, which is the
> least-exercised path in the whole conversion.
>
> What is actually lost is narrow: an issue that reaches decide, *fails to clear
> `decision_needed`*, **and** has sub-threshold scores no longer gets a size-review attempt
> before deferral. An issue whose decision genuinely did not resolve is not a good
> decomposition candidate — its options are still unresolved, so `snap_and_size_review` would
> be reasoning about an issue in an undefined state. Deferral with a
> `DECISION_UNRESOLVED` ledger entry is the more honest outcome, and it is recoverable: the
> issue returns to the queue with an accurate reason.
>
> Record as an accepted difference in the Behavior Parity table with a pointer to ENH-1415,
> so the next reader sees this was weighed rather than dropped.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **`resolve-decision.yaml` confirmed fully ready for this conversion** (read in full, 184 lines): `route_entry`'s own comment (`:28-35`) explicitly names `autodev`'s `triage_outcome_failure` and states "That binding itself lands with ENH-3075; this sub-loop only needs to expose the branch" — the sub-loop was pre-wired by BUG-3065 specifically for this issue's fifth entry point. `deposit_options.on_partial: record_options_deposited` is present (`:81`), confirming survival is not in question. Both `deposit_options` and `run_decide` route `on_rate_limit_exhausted: failed` (`:83`, `:156`), with an inline comment (`:68-71`) already stating the same "a `loop:` sub-loop state can never observe the rate-limit terminal" reasoning this issue's Rate-limit-exhaustion subsection independently derives — the sub-loop's own answer is "route to `failed`, push discrimination to the caller," not a marker handshake; Option A's marker is additive on top of that, not a prerequisite for it.
- **Correction — the `$${CURRENT}` escape claim is likely wrong as stated.** Per `codebase-analyzer`: `dequeue_next` currently references `CURRENT` as a **bareword** `$CURRENT` (plain bash assignment `:94`, referenced unbraced at `:101`, `:821`), and the FSM interpolator only rewrites `${...}` (braced) patterns — bare `$VAR` passes through untouched, per existing convention (`reference_fsm_bash_brace_escape` precedent: the double-dollar escape exists specifically to stop the FSM interpolator from mis-resolving a **braced** `${VAR}` as an FSM context-path lookup, e.g. `$${RUN_DIR}` at `check_open_question_progress` `:583-604` and mirrored in `resolve-decision.yaml:109-130`). If the marker-clear line keeps `$CURRENT` unbraced (as `dequeue_next` does everywhere else today), it needs **no escaping at all** — writing `$${CURRENT}` would instead push the string `${CURRENT}` through FSM interpolation, which raises "expected namespace.path" per the existing brace-escape hazard, since `CURRENT` is not an FSM context path. The escape is only needed if the marker-clear line is written with braces (`${CURRENT}`); confirm which form is used before applying the `$${...}` doubling.
- Per-issue marker path confirmed: `resolve-decision.yaml`'s `record_options_deposited` (`:85-95`) writes `${context.run_dir}/decide-options-deposited-${context.issue_id}` and `check_decision_decidable` (`:41-61`) reads the same path (`:53`) — this is the exact per-issue name Site 3 (`dequeue_next`'s clear) must target.
- Current line numbers for the three marker-rename sites in `autodev.yaml` (2026-08-06): read `:540`, write `:573`, clear `:105` — all match the issue's cited numbers exactly (no drift, unlike the block ranges above).
- `refine-to-ready-issue.yaml`'s three existing `resolve-decision` call sites (`:205`, `:255`, `:434`) all omit `skip_probe` (relying on its `"false"` default) — none is precedent for the `skip_probe: "true"` binding this issue's `triage_outcome_failure` site needs; that wiring has no existing call-site example to model after.

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **Resolved — the marker-clear line needs bareword `$CURRENT`, not `$${CURRENT}`.** Verified against every other `CURRENT` reference in `autodev.yaml` (`:101`, `:114`, `:154`, `:821`, `:844`): all are unbraced `$CURRENT`, none escaped. The correct Site 3 edit is `rm -f ${context.run_dir}/decide-options-deposited-$CURRENT` — `${context.run_dir}` interpolated FSM-side (braced), `$CURRENT` left as a plain bash variable (unbraced, shell-side), matching this action block's existing style throughout. Do not apply the `$${...}` doubling here; it is unnecessary and would break interpolation (raises "expected namespace.path") since `CURRENT` is not an FSM context path.

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **Option A already has in-tree precedent — the `loop:`-can't-surface-429 limitation and the marker-file remedy are documented at two independent places that are NOT callers of `resolve-decision`**: `recursive-refine.yaml:239-250` (its comment names `_execute_sub_loop` (`executor.py:820`), the `action_result is not None` gate (`executor.py:1673`), the bool `failure_terminal`, and states the Option A remedy directly: "a child writes a marker file before exiting `failed`; the caller checks for it on `on_failure`") and `rn-implement.yaml:745-746` ("a loop child can never yield a rate-limit verdict; RATE_LIMITED now arrives via the token channel"). Both are precedent for the pattern, not sites to update — cite them in `### Rate-limit exhaustion`'s rationale rather than treating the marker handshake as novel. Note `rn-implement.yaml`'s token-channel comment means the `on_rate_limit_exhausted: failed` semantics in the sub-loop and the caller-side marker are complementary, not competing signals.
- **Confirmed today's inline `on_rate_limit_exhausted: done` sites** the sub-loop's `failed` replaces: `deposit_options` `autodev.yaml:566`, `run_decide` `autodev.yaml:625`. The sub-loop already states the routing contract (`resolve-decision.yaml:68-71`: "route to failed, push discrimination to the caller") and `assert_decision_cleared`'s comment (`:169-172`) already documents the `on_error: implement_current` → `on_error: failed` flip against autodev's inline `on_error` (`:624` region).

## Integration Map

### Behavior Parity

Replaced artifact: `autodev.yaml`'s inline decision cluster (states moved into `oracles/resolve-decision`). Rows marked `autodev` stay caller-side. Dispositions follow BUG-3065's table; both accepted design differences (rate-limit Option A, assert reorder) are recorded here as required by AC 7 and the "Decided" blockquotes.

| Behavior (autodev.yaml) | Artifact | Status |
|---|---|---|
| Marker short-circuit skips re-validation once options deposited (`check_decision_decidable`, `:540`) | sub-loop | **CHANGED** — probe lives in the sub-loop (`resolve-decision.yaml:41-61`); marker becomes the per-issue name AC 4 targets |
| `check-open-questions \|\| check-decidable` probe order (ENH-2446) | sub-loop | PRESERVED |
| `deposit_options` bounded single retry via `/ll:refine-issue --auto` (`:550-565`) | sub-loop | PRESERVED — `on_partial: record_options_deposited` carried (`resolve-decision.yaml:81`) |
| Write-once options-deposited marker (`:573`) | sub-loop | **CHANGED** — per-issue name `decide-options-deposited-${context.issue_id}`; `dequeue_next` clears it on re-dequeue (AC 4, bareword `$CURRENT`) |
| `check_open_question_progress` stall gate (ENH-2446, `:580-608`) | sub-loop | **CHANGED** — becomes functional: `evaluate.history_file` declared at `resolve-decision.yaml:132-133`, whereas the inline copy's read path was inert (BUG-3065 `### Open-question stall gate is inert`) |
| `run_decide` `/ll:decide-issue --auto` + pruning profile (`:610-625`) | sub-loop | PRESERVED |
| `on_rate_limit_exhausted: done` on `run_decide`/`deposit_options` (`:625`, `:566`) | sub-loop + autodev | **CHANGED** — sub-loop routes `failed`; Option A's `decide-rate-limited-<issue_id>` marker gates autodev's `on_failure` to terminate the run rather than defer |
| `assert_decision_cleared` post-decide flag re-verify (BUG-2595, `:687-699`) | sub-loop | **REORDERED** — directly after `run_decide`; accepted difference (AC 7) |
| `check_decision_after_decide_error` short-circuit on still-armed flag (ENH-2717, `:627-637`) | — | **DELETED** — collapses into `assert_decision_cleared` |
| `mark_decide_ran` → `autodev-decide-ran` marker (ENH-1415, `:639-648`) | autodev | PRESERVED — caller-side |
| `rerun_confidence_after_decide` re-score (`:650-667`) | autodev | PRESERVED — caller-side |
| `recheck_after_decide` threshold re-check + `on_no: snap_and_size_review` (`:669-685`) | autodev | **CHANGED** — caller-side, but the `snap_and_size_review` escape for still-armed-plus-sub-threshold issues is removed (accepted, AC 7, ENH-1415) |
| `record_decision_unresolved` defer + `DECISION_UNRESOLVED` ledger (`:701-724`) | autodev | PRESERVED — caller-side; `auto-refine-and-implement.yaml:848` consumes |
| `triage_outcome_failure` direct `run_decide` route (`:1250-1266`) | autodev | PRESERVED — via `skip_probe: "true"` binding (AC 3) |

### Files to Modify

- `scripts/little_loops/loops/autodev.yaml` — the conversion itself.
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — adds the rate-limit marker
  write (Option A, decided 2026-08-06) before both `on_rate_limit_exhausted: failed` routes
  (`deposit_options`, `run_decide`); also modified if the `autodev-decide-ran` write is added
  to the child.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/scan-and-implement.yaml:77` — calls `loop: autodev`; must observe the
  same `on_success`/`on_failure` outcomes after the conversion.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:840` — consumes the
  `DECISION_UNRESOLVED` ledger; the caller-side `record_decision_unresolved` must keep writing it.
- `scripts/little_loops/loops/rn-remediate.yaml` (~`:275-370`, `~:633-741`, `~:784-955`) — a third,
  independent inline copy of the same cluster shape, cross-referenced by a "parity insertion
  mirroring rn-remediate" comment in `autodev.yaml`'s `check_decision_decidable`. **Out of scope** —
  now tracked as **[[ENH-3090]]** (filed 2026-08-06, `depends_on: ENH-3075`), which also removes
  the parity comment this issue leaves stale. ENH-3090 inherits both design decisions settled
  here (rate-limit Option A, assert-reorder accepted), so do not re-derive them there.

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
- `dequeue_next`'s marker clear targets the per-issue path and uses **bareword `$CURRENT`**,
  not `${captured.input.output}` and not `$${CURRENT}` — the regression guard for the trap
  above. (An earlier draft of this bullet said `$${CURRENT}`; that is wrong and was
  corrected in the Codebase Research Findings below. `CURRENT` is a plain bash local, so the
  braced-and-doubled form would push the literal `${CURRENT}` through FSM interpolation and
  raise "expected namespace.path". Assert the bareword form.)
- The rate-limit marker handshake (Option A, decided below): the sub-loop writes
  `decide-rate-limited-<issue_id>` before exiting `failed`, and autodev's `on_failure` gate
  reads it and terminates the run rather than deferring the issue.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **Drift — most `test_builtin_loops.py` anchors in the Tests section above are stale** (verified 2026-08-07). The decision-cluster tests the rewrite must touch now live in `TestAutodevLoop` at `:6313-6866`. Current anchors: `test_required_states_exist` `:4547-4580` (was `:4215-4249`; required set includes `run_decide` `:4568`, `mark_decide_ran` `:4569`, `rerun_confidence_after_decide` `:4570`); `test_check_decision_at_dequeue_on_yes_routes_to_check_decision_decidable` `:4669-4677` (was `:4337`); `test_record_decision_unresolved_defers_via_set_status` `:5693-5696` (was `:5359-5362`); `test_check_decision_after_refine_routes_correctly` `:5831-5848` (was `:5498`); the `check_decision_before_size_review`/`triage_outcome_failure` group `:6313-6392` (was `:6007`/`:6046`); the cluster-core group `:6638-6866` (was `:6304`/`:6314`/`:6324`/`:6375-6396`/`:6460-6479`), specifically `test_decide_current_on_yes_routes_to_check_decision_decidable` `:6638`, `test_check_decision_decidable_state_exists_and_routes` `:6648`, `test_deposit_options_state_exists_and_routes` `:6658`, `test_check_open_question_progress_state_exists` `:6687`, `test_dequeue_next_clears_decide_options_deposited_marker` `:6696`, `test_run_decide_uses_with_rate_limit_handling_fragment` `:6709`, `test_run_decide_next_routes_to_mark_decide_ran` `:6714`, `test_run_decide_on_error_routes_to_implement_current` `:6721`, `test_run_decide_on_rate_limit_exhausted_routes_to_done` `:6728`, `test_rerun_confidence_after_decide_*` `:6733-6791`, `test_mark_decide_ran_*` `:6794-6813`, `test_recheck_after_decide_on_no_routes_to_snap_and_size_review` `:6838`; `TestBuiltinLoopReferencesResolve.test_all_static_loop_references_resolve` `:13336` (was `:12963`). Only `:6341-6360`, `:6375-6396`, and `:6767` remain roughly accurate. `test_autodev_decision_gate.py` anchors are essentially current (within ~4 lines): `:1061`/`:1070` (cited `~:1066`/`~:1072`), `:965-1016` (cited `~:967-1018`), `:1020-1041` (cited `~:1022-1041`).
- **New — `TestResolveDecisionOracle` (17 tests, `test_builtin_loops.py:2287-2445`)** — dedicated coverage of `oracles/resolve-decision.yaml`, added since this issue's Tests section was written. The rewrite must keep these green, and the moved assertions (AC 8) belong here. Notable: `test_route_entry_skip_probe_true_routes_to_run_decide` `:2336` and `test_route_entry_default_routes_to_check_decision_decidable` `:2344` — the existing model for AC 3's asymmetry assertion; `test_no_loop_state_declares_on_rate_limit_exhausted_done` `:2362` — must not regress when the rate-limit marker (AC 6) lands; `test_options_deposited_marker_is_per_issue` `:2375` — pins the per-issue marker name AC 4's `dequeue_next` clear must target; `test_run_decide_and_assert_decision_cleared_routing` `:2410` and `test_assert_decision_cleared_terminal_contract` `:2427` — the sub-loop-internal model for AC 8's replacement assertion. `TestRefineToReadyIssueSubLoop` (`:1257`, call-state tests `:1982-2269`) is the model for autodev's new `loop:` call-state assertions.
- **Correction — `rn-remediate.yaml` does not use the `autodev-decide-options-deposited` literal** (grep-verified). Its inline copy uses its own marker `decide_options_deposited_${context.issue_id}.txt`, routes to a `decide` state rather than `run_decide`, and is covered by `scripts/tests/test_rn_remediate.py:175-348` — a separate file this issue's Tests section does not mention. Consequences: (a) AC 5's except-clause "except where `rn-remediate.yaml`'s independent copy legitimately retains it" is vacuous — no autodev-marker literal exists there to retain, so the AC effectively requires the string gone from `scripts/little_loops/` and `scripts/tests/` with no carve-out; (b) the "parity copy and its cross-reference comment" sweep item is about the parity comment in `autodev.yaml`'s `check_decision_decidable` (`:540` region), which points at rn-remediate's *shape*, not its marker name — `test_rn_remediate.py` and `test_fsm_open_question_stall.py` are unaffected by the marker rename.
- **Drift — the `auto-refine-and-implement.yaml:840` citation no longer resolves to the consumption**; the `DECISION_UNRESOLVED=$(count autodev-decision-unresolved.txt)` line moved to `auto-refine-and-implement.yaml:848` (count helper `:710`, BUG-2595 comment block `:843-847`, summary.json `:959`/`:965`). The issue cites `:840` in four places (Proposed Solution "Decided" blockquote, "Preserved behaviors", this Integration Map bullet, AC 2) — all should read `:848`.

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **Test-anchor drift (verified 2026-08-07)** — most `test_builtin_loops.py` cluster-group anchors have moved +34 since the last refine. Current anchors in `TestAutodevLoop`: `test_required_states_exist` `:4547-4589` (unchanged); `test_decide_current_on_yes_routes_to_check_decision_decidable` `:6672` (was `:6638`); `test_check_decision_decidable_state_exists_and_routes` `:6682` (was `:6648`); `test_deposit_options_state_exists_and_routes` `:6692` (was `:6658`); the `test_run_decide_*` group `:6743-6762` (was `:6709-6728`); `test_rerun_confidence_after_decide_state_exists` `:6767` (was `:6733`); marker literal asserted at `:6712` and `:6734`. `test_autodev_decision_gate.py` anchors are essentially current (within ~4 lines): `:965-1016`, `:1020-1041`, `:1061-1128` (was `~:967-1018`, `~:1022-1041`, `~:1066/1072`). `TestResolveDecisionOracle` `:2287-2445` and `TestRefineToReadyIssueSubLoop` call-state tests `:1982-2269` unchanged — the models for the rewrite.
- **Doc-anchor drift (verified 2026-08-07)** — `docs/guides/LOOPS_REFERENCE.md` cluster-prose region moved +3: ASCII diagram now `:1003-1048` (was `:1000-1045`), "Diagram omissions" `:1050` (was `:1047`), "Outcome failure triage" `:1056` (was `:1053`), "Decidability gate parity" `:1058` (was `:1055`). Content unchanged — still spells out the inline cluster by exact state name and still contains the pre-existing inaccuracy about `triage_outcome_failure` that AC 10 says to fix.
- **`auto-refine-and-implement.yaml:848` confirmed current** — the `DECISION_UNRESOLVED=$(count autodev-decision-unresolved.txt)` count line (issue cites `:848` in AC 2 and "Preserved behaviors").
- **Convention: caller-side `on_failure` marker gates are established** — `autodev.yaml:385-400` (`refine_current`, `loop: refine-to-ready-issue`) routes `on_failure: skip_inflight`; the child's `classify_terminal` (`refine-to-ready-issue.yaml:721-737`) writes `${context.run_dir}/refine-terminal-class` immediately before `next: failed`, and `skip_inflight` (`autodev.yaml:422-436`) reads it with `[ -f ... ]`. This is the identical "child writes a marker before exiting `failed`, caller gates on it" shape Option A's `decide-rate-limited` marker needs — an in-tree working precedent, not just the two docs-comment precedents (`recursive-refine.yaml:239-250`, `rn-implement.yaml:745-746`).

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- `_execute_sub_loop` function definition confirmed at `scripts/little_loops/fsm/executor.py:820`; the routing dispatch table the issue cites (`:1058-1086`) is unchanged and confirmed current — `terminated_by == "terminal"` + `failure_terminal` (bool) is the only signal a `loop:` caller receives, with no branch specific to rate-limit exhaustion. The 429 interception gate at `:1673-1685` (`if action_result is not None:`) is confirmed structurally unreachable for a `loop:` state, since `_execute_sub_loop` produces a `child_result`, never an `action_result`.
- `ExecutionResult.failure_terminal: bool = False` confirmed current at `scripts/little_loops/fsm/types.py:60`, exposed to JSON serialization but carrying no terminal name.
- `assert_decision_cleared`'s behavior difference is explicit in `resolve-decision.yaml`'s own comments (`:169-172`), which directly contrast its `on_error: failed` against autodev's inline copy's `on_error: implement_current` and call it out as the accepted extraction-boundary difference — this is documentation already in place in the sub-loop, not something this issue needs to newly establish.

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **Engine anchor refinement** (verified 2026-08-07): `_execute_sub_loop`'s child-routing dispatch is at `executor.py:1055-1079` (issue cites `:1058-1086` — off by 3, same shape): `terminated_by == "terminal"` + `not failure_terminal` → `on_yes` (`:1060-1062`); `+ failure_terminal` → `on_no` (`:1063-1065`); `terminated_by == "error"` → `on_error`/`on_no` (`:1066-1072`); timeout family → `extra_routes`/`on_no` (`:1073-1080`); everything else (`interrupted`, `user_stopped`, `system_signal`, `cycle_detected`, `stall_detected`, `host_pressure_abort`, `host_budget_exceeded`, `handoff`) → `on_no` (`:1081-1086`). No `on_rate_limit_exhausted` branch exists. The 429 gate is `executor.py:1673-1686` (issue cites `:1673-1685`), gated on `action_result is not None` — confirmed structurally unreachable for a `loop:` state (`_execute_state`'s loop branch at `:1454-1460` returns `_execute_sub_loop`'s `str | None` directly; `action_result` is only assigned on the non-loop action path `:1546-1563`). The exhaustion path itself: `_handle_rate_limit` `:2878` → `_exhaust_rate_limit` `:3098` → `target = state.on_rate_limit_exhausted or state.on_error` `:3110`; `failure_terminal` set at `executor.py:3206-3208` (`terminated_by == "terminal" and self.current_state in failure_states`).

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **Confirmed — the sub-loop's `failed` terminal is a failure terminal even without explicit `failure: true`**: `resolve-decision.yaml:182-183` declares `failed: {terminal: true}`; `scripts/little_loops/fsm/schema.py:33-35` (`FAILURE_TERMINAL_NAMES` includes `"failed"`) plus `schema.py:870-875` (terminal states default `failure` to `name in FAILURE_TERMINAL_NAMES`) make a caller's `loop:` state route it to `on_no`/`on_failure` (`executor.py:1055-1065`). This is what makes the sub-loop's `on_rate_limit_exhausted: failed` observable by autodev's `on_failure` gate — Option A's `check_decide_rate_limited` can rely on it without the caller distinguishing terminal names.
- **Behavioral delta — the sub-loop's stall gate is functional where autodev's inline copy is inert**: `resolve-decision.yaml:132-133` declares `evaluate.history_file` explicitly; autodev's inline `check_open_question_progress` (`:580-608`) writes a per-issue `.open_questions_<ID>.history` file but never declares `history_file`, so its evaluator falls back to a flat default path nothing writes — the gate is inert today (BUG-3065's `### Open-question stall gate is inert`). Post-conversion autodev inherits the *functional* gate. This is a behavior change beyond the accepted assert-reorder difference; it should be recorded in the Behavior Parity table as a CHANGED (functional) stall gate.
- **Anchor moved — `recursive-refine.yaml`'s dead `on_rate_limit_exhausted: dequeue_next` is now `:251`, not `:236`** (+15, shifted by the BUG-3065 comment block at `:239-250`; `:236` is now `on_success: check_passed`). The deadness claim itself is unchanged and is now documented inline at `:239-250`.

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

## Acceptance Criteria

_Added 2026-08-06 during pre-implementation review — this issue previously had none, which
was the largest gap given its Large effort and Medium-High risk._

1. `autodev.yaml` contains no `check_decision_decidable`, `deposit_options`,
   `record_options_deposited`, `check_open_question_progress`, `run_decide`, or
   `check_decision_after_decide_error` state in its own `states:` block — all four inline
   blocks are replaced by `loop: oracles/resolve-decision` call states.
2. `mark_decide_ran`, `rerun_confidence_after_decide`, `recheck_after_decide`, and
   `record_decision_unresolved` remain caller-side in `autodev.yaml` and are unchanged in
   behavior. `record_decision_unresolved` still defers and still writes the
   `DECISION_UNRESOLVED` ledger entry that `auto-refine-and-implement.yaml:848` consumes
   (the count line moved from `:840`; count helper at `:710`).
3. All five entry points route to the call state. The four probe-first entries
   (`check_decision_at_dequeue` `:236`, `check_decision_after_refine` `:491`,
   `decide_current.on_yes` `:526`, `check_decision_before_size_review.on_yes` `:1246`)
   bind no `skip_probe` (relying on the `"false"` default);
   `triage_outcome_failure.on_yes: run_decide` (`:1264`) binds `skip_probe: "true"`. A
   test asserts this asymmetry explicitly — it is the only reason `route_entry` exists.
4. `dequeue_next`'s marker clear targets the per-issue path
   `${context.run_dir}/decide-options-deposited-$CURRENT` using **bareword `$CURRENT`**, not
   `${captured.input.output}` (which holds the *previous* iteration's ID at that point) and
   not `$${CURRENT}`. A test asserts the exact form. The accompanying comment explains why
   this marker is cleared when the neighbouring per-issue markers deliberately are not.
5. The literal `autodev-decide-options-deposited` appears nowhere in
   `scripts/little_loops/` or `scripts/tests/` after the conversion — with no carve-out:
   `rn-remediate.yaml`'s inline copy uses its own
   `decide_options_deposited_${context.issue_id}.txt` marker, not the autodev literal.
   Grep-enforceable — a missed *read* site silently disables ENH-2443's write-once bound.
6. **Rate limit (Option A):** `oracles/resolve-decision.yaml` writes
   `${context.run_dir}/decide-rate-limited-${context.issue_id}` before both
   `on_rate_limit_exhausted: failed` routes, and `autodev.yaml`'s `on_failure` path gates on
   that marker — present terminates the run, absent falls through to
   `record_decision_unresolved`. A test covers both branches. Without the present-branch,
   429 exhaustion walks the whole queue into deferral.
7. **Assert reorder:** the loss of the `recheck_after_decide.on_no → snap_and_size_review`
   escape for still-armed-plus-sub-threshold issues is recorded as an accepted difference in
   the Behavior Parity table, referencing ENH-1415. No caller-side score branch is added.
8. Every assertion listed in the Tests section is rewritten, not deleted to make the suite
   pass. Specifically: `check_decision_after_decide_error`'s 5 routing assertions
   (`test_autodev_decision_gate.py:~1072-1128`) are **replaced** by a sub-loop-internal
   assertion that `run_decide.on_error == "assert_decision_cleared"`, placed in
   `TestResolveDecisionOracle` (modeled on `test_run_decide_and_assert_decision_cleared_routing`
   at `:2410` and `test_assert_decision_cleared_terminal_contract` at `:2427`), and
   `test_builtin_loops.py`'s `required` state-set literal (`test_required_states_exist`, now
   `:4547-4589` in `TestAutodevLoop`) is updated rather than having the moved names removed.
9. `ll-loop validate` passes for `autodev.yaml` and `oracles/resolve-decision.yaml`.
10. `LOOPS_REFERENCE.md:1003-1058` is updated: the ASCII flow diagram, the "Diagram
    omissions" paragraph, the "Outcome failure triage" paragraph, and the "Decidability gate
    parity" paragraph — the last of which is *already* inaccurate against
    `triage_outcome_failure`'s direct route and must be corrected regardless.
11. A manual `ll-loop run autodev` completes at least one issue end to end. There is no
    automated end-to-end coverage for this path, so structural tests alone do not verify
    the conversion.
12. `python -m pytest scripts/tests/` exits 0.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-06_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- Moderate per-site depth: most of the conversion (state deletion, entry-point retargeting, marker rename) is mechanical, but the rate-limit-exhaustion discrimination requires a genuinely new marker-handshake + gate state to work around `_execute_sub_loop`'s inability to surface `on_rate_limit_exhausted` through a `loop:` call state — this is the one subsystem the issue itself flags as needing design, not assumption.
- Breadth spans 6 files (2 to modify, 2 test files with ~25 assertions to rewrite, 2 docs) with no automated end-to-end coverage — AC 11 requires a manual `ll-loop run autodev` pass to backstop the structural rewrite.

## Status

- [ ] Not started


## Session Log
- `/ll:confidence-check` - 2026-08-07T21:50:28 - `e94e5558-c960-4e55-b425-20f7c378ecf8.jsonl`
- `/ll:reconcile-issue` - 2026-08-07T21:44:35 - `cfb55693-d0a0-4b9e-85d0-b30adca32d69.jsonl`
- `/ll:confidence-check` - 2026-08-07T20:01:12 - `a287babb-e322-4cb0-b11c-8aa259850da0.jsonl`
- `/ll:refine-issue` - 2026-08-07T19:57:52 - `c3f6228f-e420-45ad-922f-96e16665418b.jsonl`
- `/ll:reconcile-issue` - 2026-08-07T19:38:27 - `1f5af319-7482-44be-be25-d2e6c1b0a6b2.jsonl`
- `/ll:refine-issue` - 2026-08-07T18:29:34 - `9f8183ff-cd3e-48be-b744-b28f9ff368f6.jsonl`
- `/ll:confidence-check` - 2026-08-06T18:13:35 - `2714e173-0113-42e1-b8e8-e7f650c61db7.jsonl`
- `/ll:refine-issue` - 2026-08-06T17:38:13 - `71a5b5c8-8b5f-4779-9a91-00cc882432b5.jsonl`
