---
id: FEAT-2552
title: 'F2b — wire code-run-gate oracle into rn-remediate + rn-implement token routing'
type: FEAT
priority: P2
status: open
captured_at: '2026-07-08T00:00:00Z'
discovered_date: 2026-07-08
discovered_by: split-from-FEAT-2413
parent: FEAT-2413
relates_to:
- EPIC-2412
- FEAT-2413
- FEAT-2551
- FEAT-2414
labels:
- loops
- verification
- fsm-rewiring
- rn-remediate
- rn-implement
- greenfield
decision_needed: false
learning_tests_required:
- pytest-json-report
size: Large
---

# FEAT-2552: F2b — wire code-run-gate oracle into rn-remediate / rn-implement

> **Split from FEAT-2413** (split 2026-07-08; see FEAT-2413 for umbrella
> motivation, parent EPIC-2412 context, and original 13-step plan). F2b
> wires the asset shipped in **FEAT-2551** (`oracles/code-run-gate.yaml`
> + config schema) into the implement path. After F2b, an
> `IMPLEMENTED` verdict requires the gate to pass; failing code routes
> to `IMPLEMENT_FAILED`. **F2b depends on F2a landing first.**

> **Behavioral change** — modifies the completion verdict of
> `rn-implement` / `rn-remediate`. Two existing tests intentionally
> break (`test_rn_remediate.py:482-486` and `:1374-1379`) and must be
> updated in the same commit. The change affects 7+ downstream loops
> transitively via the `subloop_outcome_<ID>.txt` token channel; see
> Outcome Risk Factors below.

## Summary

Insert a new `run_code_gate` state in `rn-remediate.yaml` between
`implement.on_yes` and `emit_implemented`. The state invokes the
`code-run-gate` oracle (FEAT-2551) as a sub-loop. The oracle's
verdict (`GATE_PASS` / `GATE_FAILED` / `GATE_SKIP`) routes the flow:
pass → `emit_implemented`; fail → counter-incremented remediation
pass or `IMPLEMENT_FAILED`; skip → treated as pass.

Thread the gate's outcome through `rn-implement.yaml`'s existing
`classify_remediation` routing so counters and the completion summary
reflect real build status (a `GATE_FAILED` token falls through to
`record_failure` at `rn-implement.yaml:941`).

Update the existing tests that break under the new wiring and add
new tests covering the gate's routing behavior end-to-end.

## Current Behavior

`rn-remediate.yaml:483-500` (`implement.on_yes`) routes directly to
`emit_implemented`. `rn-implement.yaml:720-735` (`classify_remediation`)
classifies the implementation outcome. Neither path runs anything —
completion is judged from LLM-scored issue prose plus
`verify_work_was_done` (`work_verification.py:44-161`) which only
checks that a git diff exists. Plausible-but-broken code earns
`IMPLEMENTED`.

## Expected Behavior

After F2b:

- `implement.on_yes` in `rn-remediate.yaml` routes to a new
  `run_code_gate` state (not directly to `emit_implemented`).
- `run_code_gate` invokes `code-run-gate` via
  `loop: code-run-gate` + `with:` bindings (FEAT-2551's contract).
- Gate verdict semantics:
  - `GATE_PASS` → `emit_implemented` (success path unchanged).
  - `GATE_FAILED` → increments the same `remediation_count_<ID>.txt`
    counter that `check_remediation_budget` (`:782-800`) enforces;
    routes to `record_gate_failure` (writes `GATE_FAILED` to the
    `subloop_outcome_<ID>.txt` token channel, which `rn-implement`'s
    `classify_remediation` reads).
  - `GATE_SKIP` → treated identically to `GATE_PASS` (no-op for
    docs-only / no-commands-configured issues).
- A deliberately broken implementation (compile error or failing
  test) terminates as `IMPLEMENT_FAILED`, never `IMPLEMENTED`.

## Use Case

**Who**: A developer running `rn-remediate` (directly or via `ll-auto`)
on any issue that produces runnable code.

**Context**: The implement path has produced a code change and is
about to emit a completion verdict.

**Goal**: Trust that `IMPLEMENTED` means the code actually builds and
passes tests — not just that a diff exists.

**Outcome**: Implementations that fail to compile or fail tests
terminate as `IMPLEMENT_FAILED`, closing the biggest robustness hole
in the greenfield family.

## Motivation

The LLM-only completion signal is the single biggest robustness hole
in the greenfield family and directly violates the MR-1 doctrine the
repo enforces on meta-loops (LLM self-grades are 33–55% accurate per
the SHOR Table 1 cited in
`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:94-107`). The proven
`cli-anything-bootstrap.yaml` + `oracles/generator-evaluator.yaml`
patterns already exist; F2b is the wiring that lets them act on
`rn-remediate`'s verdict.

## Proposed Solution

Add a `run_code_gate` state to `rn-remediate.yaml` and a token-routing
chain entry to `rn-implement.yaml`. Mirror the `run_remediation`
pattern at `rn-implement.yaml:695-718` for sub-loop dispatch.

```yaml
# rn-remediate.yaml — new state inserted between implement.on_yes
# and emit_implemented.
run_code_gate:
  loop: code-run-gate
  with:
    issue_id: "${context.issue_id}"
    run_dir: "${context.run_dir}"
    min_pass_rate: "${context.min_pass_rate}"   # default 1.0 if absent
  on_success: emit_implemented
  on_failure: record_gate_failure    # writes GATE_FAILED to token channel
  on_error:   record_gate_error      # on_error is for child-crash, not failure
```

`record_gate_failure` increments `remediation_count_<ID>.txt` so
`check_remediation_budget` (`rn-remediate.yaml:782-800`) naturally
enforces `max_remediation_passes` without a parallel counter.

For `rn-implement.yaml`:
- No structural change required to `classify_remediation`
  (`:720-735`); the existing `route_rem_*` chain classifies every
  known failure token, and `GATE_FAILED` falls through to
  `record_failure` at `:941`.
- Optional: add `route_rem_gate_failed` adjacent to
  `route_rem_scores_missing` (mirrors `:898-910`) for diagnostic
  counter separation.

## Implementation Steps

1. **Insert `run_code_gate` state in `rn-remediate.yaml`** after
   `implement` (line 499) and before `emit_implemented` (line 810).
   Reuse the `shell_exit` fragment from `loops/lib/common.yaml:15-21`
   if any inline shell-state is needed (typically not — the sub-loop
   dispatch handles exit-code semantics).
2. **Add `record_gate_failure` state** that:
   - Writes `GATE_FAILED` to
     `${context.run_dir}/subloop_outcome_<ID>.txt`.
   - Increments `remediation_count_<ID>.txt` by 1 (the same counter
     `check_remediation_budget` enforces).
   - Routes back to `implement` (giving the loop one more
     remediation pass) or to `emit_implement_failed` if
     `max_remediation_passes` is exhausted.
3. **Update `rn-implement.yaml:720-735` token chain (optional)**:
   add `route_rem_gate_failed` next to `route_rem_scores_missing`
   (`:898-910`) for counter separation. If skipped, `GATE_FAILED`
   falls through to `record_failure` at `:941`, which is acceptable
   for an initial wiring.
4. **Update existing tests that break**:
   - `scripts/tests/test_rn_remediate.py:482-486`
     (`test_implement_routes_to_done`) — assertion changes from
     `on_yes == "emit_implemented"` → `on_yes == "run_code_gate"`.
   - `scripts/tests/test_rn_remediate.py:1374-1379`
     (`test_implement_success_emits_implemented`) — same change.
   - `scripts/tests/test_builtin_loops.py:333-361`
     (`TestSubloopSidecarContract`) — the new oracle writes its
     own `subloop_outcome_<ID>.txt`; either add
     `"oracles/code-run-gate.yaml"` to `SUBLOOPS` (if the oracle
     writes the sidecar directly, matching FEAT-2551's design) or
     keep the parent contract unchanged and let `rn-remediate`
     translate the oracle's verdict into the standard
     `IMPLEMENTED` / `IMPLEMENT_FAILED` token.
   - `scripts/tests/test_builtin_loops.py:46-54`
     (`test_all_validate_as_valid_fsm`) — confirm `rn-remediate`
     still validates cleanly after the new state is added.
5. **Add new tests** (per Implementation Steps below) in
   `test_rn_remediate.py`, `test_rn_implement.py`, and
   `test_builtin_loops.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be
included in the implementation:_

6. **Precondition lock-in with FEAT-2551** (load-bearing — both
   issues must ship together):
   - Confirm FEAT-2551's `oracles/code-run-gate.yaml` declares
     `parameters.min_pass_rate` with `default: 1.0` (not
     `required: false` with no default); otherwise
     `_execute_sub_loop` (`scripts/little_loops/fsm/executor.py:789-795`)
     raises `ValueError` when `rn-remediate`'s context does not
     override `min_pass_rate` [Agent 2 finding].
   - Confirm FEAT-2551's `oracles/code-run-gate.yaml` file exists;
     `_validate_loop_references`
     (`scripts/little_loops/fsm/validation.py:508-544`) raises
     ERROR-severity on unresolvable static `loop:` references.
     Without FEAT-2551, `ll-loop validate rn-remediate` exits 1
     after F2b's `loop: code-run-gate` insertion.
   - Confirm `_validate_with_bindings`
     (`scripts/little_loops/fsm/validation.py:431-505`) cross-check
     passes — the `with:` keys (`issue_id`, `run_dir`,
     `min_pass_rate`) must match FEAT-2551's declared parameters.
7. **Add `min_pass_rate` as a new context default** to
   `rn-remediate.yaml` (mirrors `max_remediation_passes` at line
   60). Per refine-issue Additional Findings (FEAT-2552:256-264),
   `rn-remediate.yaml:57-76` does not currently define
   `min_pass_rate`. Without this default, sub-loop dispatch will
   fail context-resolution for issues that don't override
   `min_pass_rate`. Recommended: add `min_pass_rate: 1.0` to the
   loop's `context.defaults` block [refine-issue finding,
   confirmed by Agent 1].
8. **Decide and lock in the sidecar-write contract** (FEAT-2551
   dependency):
   - Option (a): FEAT-2551's oracle writes
     `subloop_outcome_<ID>.txt` directly; then F2b must extend
     `SUBLOOPS = ("rn-remediate", "rn-decompose")` at
     `scripts/tests/test_builtin_loops.py:314` to include
     `"oracles/code-run-gate"`.
   - Option (b): `rn-remediate` translates the oracle's verdict;
     `SUBLOOPS` stays unchanged but `record_gate_failure` and
     `record_gate_error` MUST write the sidecar to satisfy
     `TestSubloopSidecarContract.test_terminal_routing_states_write_sidecar`
     (`:333-361`).
   - The decision must be locked in FEAT-2551 before F2b lands.
9. **Mirror autodev's gate-parity shape** — `autodev.yaml:212-254`
   implements a parallel gate pattern (ENH-2443). For cross-loop
   consistency, F2b's `run_code_gate` state should match the
   `loop: <sub-oracle>` + `with:` + `on_success` / `on_failure` /
   `on_error` shape used in `autodev.yaml`'s parallel insertion.
   This is advisory (no direct change to `autodev.yaml`) but
   prevents future divergence.
10. **Add Documentation updates** — per Documentation subsection
    above: `scripts/little_loops/loops/README.md:64, 174-186`,
    `docs/guides/LOOPS_REFERENCE.md:200-202, 366-446`,
    `docs/guides/RECURSIVE_LOOPS_GUIDE.md:43, 199-211`.

### Codebase Research Findings

_Concrete anchor references per step (from FEAT-2413 refine-issue + wire-issue passes):_

- **Sub-loop dispatch** — pattern from `rn-implement.yaml:695-718`
  (`run_remediation`). The `loop: code-run-gate` + `with:` form
  invokes `_execute_sub_loop` (`scripts/little_loops/fsm/executor.py:734-855`).
- **Token protocol** — the oracle writes to
  `${context.run_dir}/subloop_outcome_<ID>.txt`; the parent reads
  the same path via `output_contains` in the `route_rem_*` chain.
  Reused unchanged from the existing
  `rn-implement.yaml:720-735` pattern.
- **Counter integration** — `remediation_count_<ID>.txt` is the
  counter `check_remediation_budget` (`rn-remediate.yaml:782-800`)
  enforces via `output_numeric` against `max_remediation_passes`.
  Incrementing from `record_gate_failure` gives free enforcement.
- **Docs-only no-op-pass** — handled inside the oracle's
  `resolve_commands` state (FEAT-2551). F2b's wiring treats
  `GATE_SKIP` identically to `GATE_PASS` (proceed to
  `emit_implemented`); no extra routing logic in F2b.
- **Sub-loop sidecar contract** — `TestSubloopSidecarContract`
  (`test_builtin_loops.py:296-316`) auto-enforces that terminal
  routing states write the sidecar. The oracle
  (`oracles/code-run-gate.yaml`) and `rn-remediate.yaml`'s
  `record_gate_failure` / `emit_implemented` /
  `emit_implement_failed` must each write to
  `subloop_outcome_<ID>.txt` if option (a) is taken in
  Implementation Step 4 above.

#### Additional Findings (added by `/ll:refine-issue` on 2026-07-08)

_Based on follow-up codebase research pass (3 parallel agents):_

- **On-error vs on-failure token distinction (ENH-2005 precedent)** —
  `_execute_sub_loop` (`scripts/little_loops/fsm/executor.py:734-855`)
  routes a child `terminated_by == "error"` (runtime crash / timeout /
  context-resolution failure) to `state.on_error`, distinct from
  `state.on_no` (which fires for a child that reached the `failed`
  terminal). The parent `rn-implement.yaml:run_remediation.on_error`
  routes to `record_sub_loop_crash` (`rn-implement.yaml:1177-1189`),
  which writes a distinct `SUB_LOOP_CRASH` tag to `failures.txt` —
  this is the load-bearing pattern that prevents infrastructure
  failure from being misclassified as implementation failure.
  **`record_gate_error` should mirror this**: write a distinct token
  (recommended: `GATE_FAILED_INFRA`) to the sidecar so the parent's
  `route_rem_*` chain (or `record_failure` at `:941`) can disambiguate
  gate child crash from gate code-quality failure. If
  `record_gate_error` writes plain `GATE_FAILED` (indistinguishable
  from `record_gate_failure`), a gate child crash becomes silent in
  the failure tally.
- **Counter increment is "lazy" (one-cycle delay)** —
  `remediation_count_<ID>.txt` is bumped inside `check_convergence`
  (`rn-remediate.yaml:727-730`), BEFORE the classify route — not at
  the moment `record_gate_failure` writes to the sidecar. So a gate
  failure consumes a budget slot only after the next
  diagnose → converge → `check_remediation_budget` cycle
  (`rn-remediate.yaml:782-800`). If F2b wants immediate
  budget-aware termination in `record_gate_failure` (skip the
  re-entry into `implement` when `max_remediation_passes` is
  exhausted), an inline check is needed — the existing
  `check_remediation_budget` is unreachable from `record_gate_failure`'s
  direct routing. Recommended: route `record_gate_failure` to
  `implement` for the retry (cheap, one extra `ll-auto` call) and
  accept the one-cycle budget delay.
- **`min_pass_rate` is a new context key** — `rn-remediate.yaml:57-76`
  does not currently define `min_pass_rate`. F2b must either add
  it as a new context default (recommended; mirrors
  `max_remediation_passes` at line 60) or thread it from the parent
  via `run_remediation.with:` (`rn-implement.yaml:695-718`). The
  oracle's `resolve_commands` reads `min_pass_rate` from context
  (FEAT-2551's contract); without a default at the rn-remediate
  layer, sub-loop dispatch will fail context-resolution for
  issues that don't override `min_pass_rate`.
- **Docs-only no-op-pass precedent** —
  `cli-anything-bootstrap.yaml:run-cli-tests:304-337` writes
  `pytest_rc=99\ntest_pass_rate=0.0\nreason=NO_TESTS_DIR\n` to
  `${run_dir}/test-results.txt` and exits 0 when `tests/` is
  missing. This is the canonical model for FEAT-2551's
  `GATE_SKIP` (no commands configured) handling. F2b's
  `GATE_SKIP` → treated-as-`GATE_PASS` mapping routes to
  `emit_implemented` (no extra routing logic in F2b) — confirmed
  correct by the precedent.
- **Test pattern model for `route_rem_gate_failed`** — The
  canonical test for any new `route_rem_<token>` router is
  `test_route_rem_scores_missing_splits_to_record_state`
  (`scripts/tests/test_builtin_loops.py:8264-8293`) inside
  `TestRnImplementDiagnosticOutcomes` (`:8246-8330`).
  `TestRnImplementAuthFastFail` (`:9122-9180`) is the second
  model (auth-fast-fail variant). New `TestRouteRemGateFailed`
  test class in `test_rn_implement.py` (per Integration Map
  § Tests to Add) should mirror `test_route_rem_scores_missing_splits_to_record_state`'s
  shape exactly: assert `evaluate.type == "output_contains"`,
  `evaluate.pattern == "GATE_FAILED"`,
  `evaluate.source` contains `"${captured.rem_outcome.output}"`,
  `on_yes` matches the new `record_gate_failure` target,
  `on_no` advances to the next router (or `record_failure` if
  `route_rem_gate_failed` is the chain terminus), `on_error` is
  `record_failure`.
- **Standard token-write pattern is the `emit_*` shape** — All
  existing token writers in `rn-remediate.yaml:810-1026`
  (`emit_implemented`, `emit_needs_decompose`,
  `emit_stalled_needs_decompose`, `emit_needs_manual_review`,
  `emit_implement_failed`, `emit_env_not_ready`,
  `emit_scores_missing`, `emit_learning_gate_blocked`) use the
  same shape: `echo "<TOKEN>" > "${context.run_dir}/subloop_outcome_${context.issue_id}.txt"`.
  `record_gate_failure` and `record_gate_error` should follow
  this same `echo ... > sidecar` shape (with the counter
  increment and `failures.txt` tag as the differentiator).
  Naming follows the diagnostic-routing convention
  (`record_*` rather than `emit_*`) consistent with
  `record_failure`, `record_sub_loop_crash`,
  `record_scores_missing`, `record_learning_gate_blocked`
  (`rn-implement.yaml:1166-1226`).
- **`failures.txt` tagging precedent (optional but recommended)** —
  Existing tagged recorders write `"$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  $${ID} <TAG>" >> "${captured.run_dir.output}/failures.txt"` (see
  `record_sub_loop_crash` at `rn-implement.yaml:1177-1189` writing
  `SUB_LOOP_CRASH`, `record_scores_missing` writing
  `SCORES_MISSING`, `record_learning_gate_blocked` writing
  `LEARNING_GATE_BLOCKED`). `record_gate_failure` should write
  `GATE_FAILED` and `record_gate_error` should write
  `GATE_FAILED_INFRA` to the same `failures.txt` so downstream
  `report` tallying can distinguish gate failures from generic
  `IMPLEMENT_FAILED` records. Without this tagging, all gate
  failures merge into the generic `FAILED` bucket at
  `record_failure` (`rn-implement.yaml:1166-1175`) and the
  gate's failure rate becomes invisible in summaries.
- **`shell_exit` fragment is NOT needed** — `rn-remediate.yaml`
  does not need to inline `shell_exit` from
  `loops/lib/common.yaml:15-21` because the `loop:` + `with:`
  sub-loop dispatch already handles exit-code semantics via
  `_execute_sub_loop` (`scripts/little_loops/fsm/executor.py:734-855`).
  The issue's "typically not — the sub-loop dispatch handles
  exit-code semantics" note is correct; this research pass
  confirms it.
- **`TestSubloopSidecarContract` regression guard coverage
  depends on FEAT-2551's sidecar decision** — The contract test
  (`test_builtin_loops.py:296-361`) enforces that every
  terminal-routing state writes `subloop_outcome_<ID>.txt`. If
  FEAT-2551's oracle writes the sidecar directly (option a in
  Implementation Step 4), the test must extend
  `SUBLOOPS = ("rn-remediate", "rn-decompose")` to include
  `"oracles/code-run-gate"`. If FEAT-2551 keeps the verdict
  internal and `rn-remediate` translates (option b, the
  issue's preferred path), `SUBLOOPS` stays unchanged but
  `record_gate_failure` / `record_gate_error` MUST write the
  sidecar to satisfy the contract. The issue correctly flags
  this as the cross-issue dependency that locks in before F2b
  lands.

## Acceptance Criteria

- A deliberately broken implementation (compile error or failing
  test) yields `IMPLEMENT_FAILED`, never `IMPLEMENTED`.
- `test_pass_rate` and build/typecheck/lint exit codes are captured
  to `${run_dir}/` and are the routing signal (non-LLM), satisfying
  MR-1.
- `ll-loop validate rn-remediate` passes; `ll-loop validate rn-implement`
  passes.
- Integration test: `rn-remediate` on a seeded failing issue does
  not terminate as `IMPLEMENTED`.
- Existing `TestSubloopSidecarContract` passes against the new
  wiring.

## Scope Boundaries

- **Reuses** existing evaluator types; no new FSM primitive.
- **Modifies** `rn-implement`/`rn-remediate` completion verdict.
- **Breaks** two existing tests intentionally (must update in same
  commit).
- **Inherits** transitive token-channel updates — 7+ downstream
  loops inherit the gate behavior for free.
- Deployment/CD is out of scope — `service_health` is a local start
  + probe only (handled in FEAT-2551).

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/rn-remediate.yaml:483-500, 810-820,
  996-1000` — insert `run_code_gate` and `record_gate_failure`
  states; re-route `implement.on_yes` →
  `run_code_gate` → `emit_implemented`.
- `scripts/little_loops/loops/rn-implement.yaml:720-735,
  898-910, 941` — optional: add `route_rem_gate_failed` adjacent
  to `route_rem_scores_missing`.
- `scripts/tests/test_rn_remediate.py:482-486, 1374-1379` —
  assertion updates (intentional breakage).
- `scripts/tests/test_builtin_loops.py:333-361` — add the oracle
  to `SUBLOOPS` if FEAT-2551's oracle writes the sidecar directly;
  otherwise keep the parent contract unchanged.

### Pattern Sources (read-only references)

- `scripts/little_loops/loops/rn-implement.yaml:695-718`
  (`run_remediation`) — sub-loop dispatch + counter pattern.
- `scripts/little_loops/loops/rn-remediate.yaml:782-800`
  (`check_remediation_budget`) — `output_numeric` enforcement of
  `max_remediation_passes` via `remediation_count_<ID>.txt`.
- `scripts/little_loops/fsm/executor.py:734-855`
  (`_execute_sub_loop`) — `loop:` + `with:` dispatch.
- `scripts/little_loops/loops/lib/common.yaml:15-21` —
  `shell_exit` fragment (if needed).
- `scripts/tests/test_builtin_loops.py:296-316`
  (`TestSubloopSidecarContract`) — sidecar auto-enforcement.
- `scripts/little_loops/loops/autodev.yaml:212-254` —
  parallel gate parity insertion per ENH-2443 (the `autodev` loop
  implements its own gate pattern; F2b's `run_code_gate` shape should
  match for cross-loop consistency) [Agent 1 finding].
- `scripts/little_loops/loops/lib/common.yaml:368` —
  shared `subloop_outcome_<ID>.txt` writer using
  `param.outcome_token`; pattern that `record_gate_failure` /
  `record_gate_error` should mirror [Agent 1 finding].
- `scripts/little_loops/loops/rn-implement.yaml:1177-1189`
  (`record_sub_loop_crash`) — failure-tagging template
  (`SUB_LOOP_CRASH` → `failures.txt`); load-bearing precedent for
  `record_gate_error` writing `GATE_FAILED_INFRA` to disambiguate
  child crash from gate code-quality failure [Agent 2 finding,
  cross-referenced from refine-issue Additional Findings].

### Transitive Consumers (no direct change required, listed for completeness)

- `scripts/little_loops/loops/autodev.yaml:80, 435` — parent
  orchestrator; delegates to `ll-auto --only` → `rn-implement` →
  `rn-remediate` → `code-run-gate`. **No direct change.**
- `scripts/little_loops/loops/scan-and-implement.yaml:75` —
  `loop: autodev`. Inherits transitively. **No direct change.**
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:133` —
  `loop: autodev`. Inherits transitively. **No direct change.**
- `scripts/little_loops/loops/rn-build.yaml:535` — dispatches
  `rn-implement(value_ranked)`. Inherits gate transitively.
  **No direct change.**
- `scripts/little_loops/loops/goal-cluster.yaml:533` — dispatches
  batches to `rn-implement`. Inherits transitively.
  **No direct change.**
- `scripts/little_loops/recursive_finalize.py` — `rn-implement`
  lifecycle integration. `GATE_FAILED` will appear in completion
  summaries; verify lifecycle bookkeeping handles the new token
  gracefully (likely falls through to existing `failure` branch).
- `scripts/little_loops/workflow_sequence/analysis.py` — sequence
  analysis treats `rn-implement` runs as "plan → implement → verify"
  steps. The new gate inserts a "gate" step between implement and
  verify; verify the analyzer handles the new intermediate step
  (advisory — should fall through by default).
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:21, 37, 52`
  — sibling pattern: reads the sidecar via
  `OUTCOME="$RUN_DIR/subloop_outcome_auto-refine-and-implement.txt"`.
  Same sidecar contract being extended here; no direct change.
- `scripts/little_loops/loops/rn-decompose.yaml:227, 244, 250` —
  sibling sub-loop writing the same `subloop_outcome_<ID>.txt` token
  family. The `rn-decompose` entry in `SUBLOOPS` (`test_builtin_loops.py:314`)
  shares the sidecar-contract enforcement that `record_gate_failure`
  inherits.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:80` —
  references the `rn-remediate` pattern (does not dispatch it).
  No direct change.
- `scripts/little_loops/loops/lib/policy-router.yaml:65` —
  references `rn-remediate`'s deterministic scorer pattern; advisory
  only.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/loops/README.md:64` — catalog table
  describes `rn-remediate` without mentioning the gate; append a
  parenthetical (e.g., "→ `run_code_gate`") to the row so the
  user-facing catalog stays in lockstep with the wiring.
- `scripts/little_loops/loops/README.md:174-186` — "Oracle
  Sub-loops" table; once FEAT-2551 ships `oracles/code-run-gate.yaml`,
  add a row for `code-run-gate` mirroring the existing
  `generator-evaluator` / `generator-evaluator-cli` siblings.
- `docs/guides/LOOPS_REFERENCE.md:200-202, 366-446` —
  `rn-implement` flow diagram (`:444-446`) shows `run_remediation`
  as a terminal sub-loop delegation; insert a `run_code_gate` node
  between `run_remediation` and the success/FAIL branches, and a
  new column on the per-loop table at `:368` noting the gate
  sub-call.
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md:43, 199-211` —
  "What the `rn-*` Family Is" table at `:43` lists `rn-remediate`
  as "Outcome token" without the gating semantic; the outcome-token
  table at `:199-211` enumerates `IMPLEMENTED`, `NEEDS_DECOMPOSE`,
  etc., but omits `GATE_FAILED` and `GATE_SKIP`. Append both
  tokens; note that `GATE_SKIP` is treated as `IMPLEMENTED` by
  F2b's wiring (per the issue body) so it does not need its own
  routing row in `rn-implement`'s table.

### Tests to Add

In `scripts/tests/test_rn_remediate.py`, add a `TestRunCodeGate`
class (mirror `TestSubLoopDelegation` at `:233-350` in
`test_rn_implement.py`):

- `test_run_code_gate_state_exists` — `run_code_gate` state is
  added to `rn-remediate`.
- `test_run_code_gate_is_subloop_delegation` —
  `state["loop"] == "code-run-gate"`.
- `test_run_code_gate_has_with_bindings` — passes `issue_id`,
  `run_dir`, `min_pass_rate` (default 1.0).
- `test_run_code_gate_routes_on_success_to_emit_implemented`.
- `test_run_code_gate_routes_on_failure_to_record_gate_failure`.
- `test_run_code_gate_routes_on_error_to_record_gate_error`.
- `test_implement_on_yes_routes_to_run_code_gate` — replaces
  `test_implement_routes_to_done` assertion.

In `scripts/tests/test_rn_implement.py`, add a
`TestRouteRemGateFailed` class (mirror `route_rem_scores_missing`
tests at `:898-910`):

- `test_route_rem_gate_failed_state_exists`.
- `test_route_rem_gate_failed_matches_gate_failed_token` —
  `evaluate.pattern == "GATE_FAILED"`.
- `test_route_rem_gate_failed_routes_to_record_failure` (or new
  `record_gate_failure`).
- `test_route_rem_gate_failed_source_uses_rem_outcome_capture`.

In `scripts/tests/test_builtin_loops.py`, add an integration test
in the new `TestCodeRunGateOracle` class (FEAT-2551 owns the bulk
of these; F2b owns the parent-side tests):

- `test_rn_remediate_validates_after_gate_wiring` — confirms
  `ll-loop validate rn-remediate` exits 0 after F2b's state
  insertions.

_Wiring pass added by `/ll:wire-issue`:_

Regression tests that pin the new tokens' end-to-end behavior:

- `scripts/tests/test_rn_implement.py:454-471`
  (`test_report_writes_per_issue_array_with_outcome_per_id`) —
  synthesize a `subloop_outcome_<ID>.txt` containing `GATE_FAILED`
  and assert the per-issue entry preserves the token verbatim
  (rather than coercing to `IMPLEMENT_FAILED`). The existing
  `_run_report` helper at `:430-453` already runs the `report`
  state via subprocess against synthesized sidecars; mirror its
  shape for the new token.
- `scripts/tests/test_builtin_loops.py:8295-8312`
  (`test_diagnostic_record_states_tag_and_continue`) — parametrize
  matrix currently covers
  `("record_scores_missing", "SCORES_MISSING")` and
  `("record_size_review_failed", "SIZE_REVIEW_FAILED")`; extend
  with `("record_gate_failure", "GATE_FAILED")` and
  `("record_gate_error", "GATE_FAILED_INFRA")` so the diagnostic
  recorder contract is locked in for the new states (mirrors the
  existing `record_*` shape).
- `scripts/tests/test_builtin_loops.py:8314-8330`
  (`test_report_tallies_diagnostics_separately_from_failures`) —
  extends the diagnostic-tally assertion to include the new
  `GATE_FAILED` substring so the `report` state's per-tag counter
  distinguishes gate failures from generic `FAILED`.

_Pattern references for the new tests:_

- `TestSubLoopDelegation` at `scripts/tests/test_rn_implement.py:237-344`
  — mirrors the `TestRunCodeGate` class shape: per-state section
  headers (`# --- run_code_gate ---`), method naming
  `test_<state>_<aspect>`, and `with:` binding assertions of the
  form `with_bindings["issue_id"] == "${context.issue_id}"`.
- `test_route_rem_scores_missing_splits_to_record_state` at
  `scripts/tests/test_builtin_loops.py:8264-8276` — exact assertion
  shape for `TestRouteRemGateFailed`: `evaluate.type ==
  "output_contains"`, `evaluate.pattern == "GATE_FAILED"`,
  `evaluate.source` contains `"${captured.rem_outcome.output}"`,
  `on_yes == record_failure` (or new `record_gate_failure`),
  `on_error == record_failure`.
- `test_record_sub_loop_crash_records_distinct_marker` at
  `scripts/tests/test_rn_implement.py:895-902` — pattern for the
  new `record_gate_error` test (`assert "failures.txt" in action`,
  `assert "GATE_FAILED_INFRA" in action`,
  `assert state["next"] == "dequeue_next"`).

### Tests That Must Update (intentional breakage)

- `scripts/tests/test_rn_remediate.py:482-486`
  (`test_implement_routes_to_done`) — assertion update.
- `scripts/tests/test_rn_remediate.py:1374-1379`
  (`test_implement_success_emits_implemented`) — assertion update.
- `scripts/tests/test_builtin_loops.py:333-361`
  (`TestSubloopSidecarContract`) — either add
  `"oracles/code-run-gate.yaml"` to `SUBLOOPS` or confirm the
  parent contract still holds after F2b's wiring.

### Tests That May Need Review (no direct assertion)

- `scripts/tests/test_fsm_persistence.py:3028-3041` — `rn-implement`
  snapshots. Should be unaffected (F2b changes only `rn-remediate`'s
  routing, not `rn-implement`'s persistence).
- `scripts/tests/test_rn_implement.py:454-471` — synthesis with
  known tokens (`IMPLEMENTED` / `MANUAL_REVIEW_RECOMMENDED` /
  `LEARNING_GATE_BLOCKED`). `GATE_FAILED` flows through without
  breaking the assertion (test asserts presence of 3 known keys,
  not full enumeration).
- `scripts/tests/test_rn_implement.py:494-553` — malformed sidecar
  + scalar-key preservation. Verify the report action handles the
  new token without crashing.
- _Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_remediate.py:1179-1185`
  (`test_fsm_validates_without_errors`) — uses
  `load_and_validate(RN_REMEDIATE_PATH)` directly. Will fail if
  F2b's new states violate FSM validation; the new
  `test_rn_remediate_validates_after_gate_wiring` test in
  `TestCodeRunGateOracle` covers this. Verify it remains green
  after F2b's insertions and that no `ValidationSeverity.ERROR`
  is emitted.
- `scripts/tests/test_rn_remediate.py:1193-1233`
  (`test_mr1_non_llm_evaluators_present`) — MR-1 regression guard.
  F2b's `run_code_gate` is a sub-loop delegation (no LLM evaluator),
  but the gate's verdict (`test_pass_rate`, exit codes) is the
  non-LLM signal that MR-1 doctrine requires. Confirm the MR-1
  check still passes for the new state (it should, since
  `run_code_gate` is structurally identical to `run_remediation`).
- `scripts/tests/test_general_task_loop.py:1015-1049` — existing
  `min_pass_rate` test for `general-task.yaml`; F2b reuses the same
  context-key name. No change required (F2b's `with:` binding is
  a different loop), but worth confirming the context-key namespace
  does not collide (different loop, different `context:` scope).
- `scripts/tests/test_fsm_executor.py:4869+` (`TestSubLoopExecution`,
  `TestSubLoopWithBindings`) — generic sub-loop dispatch tests; no
  rn-remediate-specific assertions but exercise the same code path
  F2b relies on. Should remain unaffected.

## Impact

- **Priority**: P2 — closes the single biggest robustness hole in the greenfield family; `IMPLEMENTED` becomes a meaningful signal only after F2b's wiring lands.
- **Effort**: Large — modifies the completion verdict of `rn-remediate`; updates 2 existing tests intentionally; adds ~6 new test cases; spans loops/, tests/, and the transitive token-channel fanout.
- **Risk**: Medium — behavioral change to the implement path; bug propagates across 7+ downstream loops via `subloop_outcome_<ID>.txt` (autodev, scan-and-implement, auto-refine-and-implement, rn-build, goal-cluster, recursive_finalize, workflow_sequence/analysis).
- **Breaking Change**: Yes — `test_implement_routes_to_done` and `test_implement_success_emits_implemented` assertions change intentionally (pre-gate direct route to `emit_implemented` is being broken). `TestSubloopSidecarContract` may need `SUBLOOPS` extension depending on FEAT-2551's sidecar-write decision.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-08_

**Readiness Score**: 95/100 → PROCEED (threshold 85)
**Outcome Confidence**: 62/100 → MODERATE (threshold 75)

### Outcome Risk Factors

- **Transitive token-channel fanout** — 7+ loops inherit the gate
  behavior via `subloop_outcome_<ID>.txt` (`autodev`,
  `scan-and-implement`, `auto-refine-and-implement`, `rn-build`,
  `goal-cluster`, `recursive_finalize`,
  `workflow_sequence/analysis`). A bug in the new wiring or its
  routing propagates across the entire greenfield family. This is
  the dominant risk axis.
- **Intentional test breakage** — two tests in
  `test_rn_remediate.py` must be updated in the same commit as the
  wiring. If the commit is split between author and reviewer, the
  intermediate state will fail the suite.
- **Sub-loop sidecar decision (FEAT-2551 dependency)** —
  `TestSubloopSidecarContract`'s coverage depends on whether the
  oracle writes `subloop_outcome_<ID>.txt` directly (option (a) in
  Implementation Step 4) or whether `rn-remediate` translates the
  oracle's verdict (option (b)). This decision must be locked in
  FEAT-2551 before F2b lands.

_No `decision_needed`, `missing_artifacts`, `mechanical_fanout_suppressed`,
or `implementation_order_risk` flag updates triggered by these risk
factors (no signal-phrase matches)._

## Session Log
- `/ll:wire-issue` - 2026-07-08T23:20:13 - `113eeae5-056f-4c48-9087-564f58c747ad.jsonl`
- `/ll:refine-issue` - 2026-07-08T23:09:09 - `cd8692a4-2e8f-451c-a9c5-c3c7d206c1fd.jsonl`

- `/ll:confidence-check` - 2026-07-08T23:10:00 - `a081f85a-6f32-4531-b0ca-f9df5eae6f9f.jsonl`
- `/ll:split-issue` - 2026-07-08T23:10:00 - `a081f85a-6f32-4531-b0ca-f9df5eae6f9f.jsonl`

## Status

**Open** | Split from FEAT-2413 on 2026-07-08 | Priority: P2 | Depends on FEAT-2551