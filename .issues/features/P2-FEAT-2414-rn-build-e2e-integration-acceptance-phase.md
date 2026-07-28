---
id: FEAT-2414
title: rn-build end-to-end integration/acceptance phase
type: FEAT
priority: P2
status: done
parent: EPIC-2412
captured_at: '2026-06-30T00:00:00Z'
completed_at: '2026-07-28T21:28:24Z'
discovered_date: 2026-06-30
discovered_by: capture-issue
size: Large
relates_to:
- EPIC-2412
- FEAT-2413
- ENH-2415
labels:
- loops
- verification
- greenfield
- rn-build
- e2e
confidence_score: 97
outcome_confidence: 68
score_complexity: 15
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 15
---

# FEAT-2414: rn-build end-to-end integration/acceptance phase

## Summary

Add an **end-to-end integration/acceptance phase** to `rn-build` that runs after
`cluster_execute` (once all features are built): stand up the assembled project and
execute the spec's `## Acceptance Criteria` as runnable checks. Today every feature
is built and self-judged in isolation via `goal-cluster` → `rn-implement`, so the
features are **never exercised together** and the acceptance criteria in the spec
template are read by an LLM but never executed.

## Current Behavior

`rn-build` builds and self-judges every feature in isolation via `goal-cluster` →
`rn-implement`. Features are never exercised together, and the spec's
`## Acceptance Criteria` are read by an LLM but never executed. Cross-feature
integration bugs (shared state, interface drift) stay invisible until a human runs the
project.

## Expected Behavior

After `cluster_execute` completes, `rn-build` stands up the assembled project and
executes the spec's acceptance criteria as runnable checks, scored by a non-LLM
`output_numeric` gate. A spec whose criteria cannot all be satisfied terminates
non-`done` with a per-criterion breakdown.

## Use Case

**Who**: A developer running `rn-build` against a multi-feature spec.

**Context**: All features have been built independently and the loop is about to report
the build outcome.

**Goal**: Verify the whole project integrates and the spec's acceptance criteria
actually hold before the run is marked `done`.

**Outcome**: Integration failures are caught automatically with a per-criterion report
instead of surfacing only when a human runs the project.

## Motivation

`rn-build` already requires `## Acceptance Criteria` in the spec (`specs/SPEC_TEMPLATE.md`)
and normalizes for its presence via non-LLM grep gates. But nothing turns those
criteria into an executable contract. The existing `eval_gate` verifies *an* installed
harness runs `project.test_cmd`; it does not verify the whole project integrates or
that the spec's acceptance criteria actually hold. Cross-feature integration bugs
(shared state, interface drift between independently-built issues) are invisible until
a human runs the project.

## Proposed Solution

Insert an `integration_gate` phase between `cluster_execute`/`check_build_outcome` and
`synthesize_result`:

1. `derive_acceptance_checks` — LLM converts each spec acceptance criterion into a
   concrete runnable check (a test command, an HTTP request + expected response, a CLI
   invocation + expected output), written to `${run_dir}/acceptance/checks.json`.
2. `run_acceptance` — a shell state that executes each check against the built project
   (starting the service/build first via the FEAT-2413 run-gate where relevant),
   recording pass/fail per criterion to `${run_dir}/acceptance/results.json`.
3. `score_acceptance` — non-LLM: `output_numeric` on pass count / total; routes
   `on_no` to a bounded remediation re-entry (feed failures back as issues), else to
   `synthesize_result`.

Reuse FEAT-2413's run-gate for build/service startup rather than duplicating it.

## Implementation Steps

1. Add the three states to `rn-build.yaml`, artifact-versioned under `${run_dir}/acceptance/`.
2. Wire `eval_gate.on_yes` → `derive_acceptance_checks` → `run_acceptance` →
   `score_acceptance` → `synthesize_result` (after the harness passes, before
   synthesis — see Codebase Research Findings on the insertion point).
3. Route acceptance failures through the existing `capture_eval_failures` →
   `cluster_execute` re-entry, respecting `max_eval_retries`.
4. Distinguish a new terminal `acceptance_failed` (`success: false`) so partial
   integration is not reported `done`.
5. Update `synthesize_result` JSON to include per-criterion acceptance results.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Insert the new phase between `eval_gate.on_yes` and `synthesize_result` (not before
  `check_harness_name`/`eval_gate` as a literal reading of step 2 might suggest) — the
  spec's Acceptance Criteria are best exercised against a project that already passed
  its own harness; see the Integration Map research note on insertion point.
- Model `derive_acceptance_checks`/`run_acceptance`/`score_acceptance` on
  `oracles/code-run-gate.yaml`'s `resolve_commands` → `run_*` → `aggregate` chain
  (lines 85–428): sidecar-JSON-driven, self-skipping `run_*` states, single `aggregate`
  reducer with a `classify` + `route:` evaluator.
- Reuse `oracles/code-run-gate.yaml`'s `service_health` state (lines 308–364) for
  "stand up the assembled project" rather than re-implementing background-process +
  health-poll + `trap cleanup EXIT` logic — invoke it via `loop: oracles/code-run-gate`
  with `with: {run_dir, issue_id, run_cmd, health_url}`.
- Give `score_acceptance` its own retry counter file (e.g.
  `${context.run_dir}/acceptance-retry-count.txt`), separate from
  `check_eval_retry_budget`'s `eval-retry-count.txt`, following the same
  `output_numeric operator: le target: "${context.max_eval_retries}"` shape (or a
  dedicated `max_acceptance_retries` context var if the two failure classes should be
  budgeted independently — worth confirming during implementation).
- Add `finalize_acceptance_failed` (action state, JSON payload + `resume_command` +
  `exit 1`) → `next: acceptance_failed` → bare `acceptance_failed: {terminal: true,
  failure: true}`, matching the existing `finalize_build_failed`/`build_failed` pair
  shape (lines 821–850) rather than a single combined state.
- Extend `scripts/tests/test_rn_build.py::TestE2E::test_rn_build_smoke` (lines
  531–641) with an assertion on `(run_dir / "acceptance" / "results.json").exists()`,
  and add the new state names to `REQUIRED_STATES` (lines 22–48) so
  `test_has_required_states` enforces them.

## Acceptance Criteria

- A spec whose criteria cannot all be satisfied by the built project terminates
  non-`done` with a per-criterion breakdown.
- `results.json` is derived from actually executing checks against the running
  project, not from an LLM reading code.
- E2E test (gated on `PYTEST_INTEGRATION=1`) extends the existing `TestE2E`
  (ENH-2014) to assert acceptance results are produced and honored.

## Scope Boundaries

- Built on FEAT-2413's build/service startup primitives (shipped).
- Does not add archetype-specific check derivation (FEAT-2416 supplies that); a
  generic derivation is sufficient here.

## Integration Map

- Modified: `rn-build.yaml` (new integration phase + `acceptance_failed` terminal,
  `synthesize_result`).
- Reuses: `oracles/code-run-gate.yaml` (FEAT-2413), existing eval-retry loop.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh2814_failure_terminal_e2e.py` — asserts failure terminals
  exit with `FAILURE_TERMINAL_EXIT_CODE`; the new `acceptance_failed` terminal must
  comply with this E2E contract.
- `scripts/tests/test_builtin_loops.py` — generic cross-loop structural gate
  `test_no_failure_edge_routes_to_a_success_terminal` runs against every built-in
  loop including `rn-build.yaml`; the new terminal/routing must satisfy it. Also
  contains `TestCodeRunGateOracle` (structural test class for
  `oracles/code-run-gate.yaml`) and `TestCodeRunGateOracleWiring` (parent-side
  wiring pattern, modeled on `rn-remediate.yaml`'s `run_code_gate` delegation) —
  the closest existing precedent for testing `run_acceptance`'s `loop:
  oracles/code-run-gate` delegation and `with:` binding validation.

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/schema.py` — `FAILURE_TERMINAL_NAMES` (a
  backward-compat-only frozenset per the ENH-2814 comment block) does **not**
  include `acceptance_failed`; the new terminal will not auto-inherit
  `failure: true` and must declare it explicitly in the YAML, mirroring
  `build_failed`'s explicit `terminal: true` / `failure: true` pair.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — rn-build's "Key phases" table (phase 0–7 by state
  name) needs a new row for `integration_gate`
  (`derive_acceptance_checks`/`run_acceptance`/`score_acceptance`) and the
  `acceptance_failed` terminal; phase 7's description ("Only reached when the
  eval gate actually passed") becomes stale once the acceptance gate sits
  between `eval_gate.on_yes` and `synthesize_result`. Also update the "Context
  knobs" table if a new `max_acceptance_retries`-style variable is added.
- `docs/guides/LOOPS_REFERENCE.md` — rn-build's phase-by-phase description and
  "Manual checklist" (step 6, `SYNTHESIS_RESULT:` JSON) need the new phase
  inserted; the "Target sections" table's `## Acceptance Criteria` row
  ("`rn-build` uses these to configure the eval harness") is duplicated from
  `SPEC_TEMPLATE.md` and needs the same update; "Context variables" table needs
  a new row if a retry-budget knob is added.
- `specs/SPEC_TEMPLATE.md` — `## Acceptance Criteria` section's comment
  currently says criteria are used only by the `eval_harness` phase; note that
  `derive_acceptance_checks` also consumes this section, and consider whether
  its "2-3 concrete scenarios" prose guidance needs more structure for
  machine-parseable derivation (today `check_structure`/`verify_structure` in
  `rn-build.yaml` only grep for section-header presence, not internal shape).
- `CHANGELOG.md` — established convention is a dedicated bullet under the
  `rn-build` label for every rn-build-touching change (see prior entries:
  "`refine_seed` migration", "normalize_spec pre-gate", "empty-loop crash");
  add one for the acceptance/integration gate, landed under a concrete version
  section per [[feedback_changelog_no_unreleased]] (not `[Unreleased]`).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_build.py::REQUIRED_STATES` (lines 22–48) — add
  `derive_acceptance_checks`, `run_acceptance`, `score_acceptance`,
  `finalize_acceptance_failed`, `acceptance_failed` so
  `test_has_required_states` enforces them (already noted in Codebase Research
  Findings above; confirmed by wiring pass).
- New routing-completeness tests for `score_acceptance` (if `check_semantic`/
  `llm_structured`) following the existing MR-4 pattern in
  `test_rn_build_check_substrate_has_full_routing` /
  `test_rn_build_harness_missing_has_full_routing` — every LLM-judged gate in
  this file has a paired full-routing test; `score_acceptance` needs one too.
- If `score_acceptance` gets its own retry-budget counter (per the issue's
  "own retry counter file" note), mirror `TestRnBuildEvalGate`'s
  `test_retry_budget_uses_output_numeric_evaluator` /
  `test_retry_budget_on_yes_routes_to_capture_failures` /
  `test_retry_counter_in_run_dir` for the new counter, and check MR-13
  (abandonment-verdict) applies if the budget can be exhausted.

### Correction to Proposed Solution

_Wiring pass added by `/ll:wire-issue`:_
- **`oracles/code-run-gate.yaml` reuse is whole-loop, not single-state.** A
  `loop: oracles/code-run-gate` reference always enters at that loop's
  `initial: resolve_commands`, which runs the **full**
  `resolve_commands → run_build → run_test → run_typecheck → run_lint →
  service_health → aggregate` chain — not just `service_health` in isolation.
  `run_acceptance` will therefore re-run build/test/lint gates that likely
  already passed earlier in `cluster_execute`/`eval_gate`. **The delegating
  `with:` bindings cannot suppress them today**: `resolve_commands` applies
  caller overrides via `[ -n "$override" ] && CMD="$override"`
  (code-run-gate.yaml lines 149–154), so an empty/omitted binding *falls back
  to the target project's config-derived command* rather than disabling it —
  the `run_*` self-skip only fires when the command resolves to null from
  every source. **Pre-requisite (small, backward-compatible):** teach
  `resolve_commands` a skip sentinel (`with: {build_cmd: "skip", ...}` →
  treated as null in `commands.json`) or a `health_only: true` parameter, so
  the acceptance delegation runs only `service_health`. (Fallback if the
  pre-req is dropped: accept the redundant full re-run — wasteful but
  harmless since each gate already passed.) `code-run-gate.yaml` declares
  `run_dir`/`issue_id` as `required: true` parameters — both must be supplied
  via `with:`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Insertion point** (`scripts/little_loops/loops/rn-build.yaml`): today
  `check_build_outcome` (lines 582–610, `shell`/`exit_code` state reading
  `${context.run_dir}/cluster-state.json`) routes `on_yes → check_harness_name` →
  `eval_gate` (lines 639–645) → `synthesize_result` (lines 759–809, only reached from
  `eval_gate.on_yes`). The new `derive_acceptance_checks` → `run_acceptance` →
  `score_acceptance` phase should sit between `eval_gate.on_yes` and
  `synthesize_result` (after the harness passes, before synthesis) — `eval_gate` never
  reads the spec's `## Acceptance Criteria` section directly today; it only receives
  `${captured.design_artifacts.output}` (design artifacts, not the spec's acceptance
  criteria prose) via the earlier `eval_harness` prompt state (line ~484), so the
  harness an LLM authors may or may not enumerate each criterion as a discrete check.
- **Terminal-state shape to follow** (MR-13 / BUG-2813 pattern, already used 4x in this
  file): a non-terminal `finalize_*` shell state that emits the resume-JSON payload and
  `exit 1`, then `next:` a bare `terminal: true, failure: true` state with no action —
  see `finalize_build_failed` (lines 821–846) → `build_failed` (848–850),
  `finalize_harness_missing` (684–710), `finalize_eval_skipped` (712–739). The new
  `acceptance_failed` terminal should be `finalize_acceptance_failed` (action state,
  JSON payload + `resume_command` + `exit 1`) → `next: acceptance_failed` → bare
  `acceptance_failed: {terminal: true, failure: true}`.
- **Bounded remediation re-entry pattern to reuse**: `check_eval_retry_budget` (lines
  647–662) is the exact template for "route `on_no` to a bounded remediation
  re-entry" — a shell state reads/increments a counter file under `${context.run_dir}`
  (e.g. `eval-retry-count.txt`), evaluated with `output_numeric operator: le target:
  "${context.max_eval_retries}"`; `on_yes` loops back into remediation
  (`capture_eval_failures` → `next: cluster_execute`), `on_no` dead-ends to
  `harness_missing`. `score_acceptance` should mirror this shape with its own counter
  (e.g. `acceptance-retry-count.txt`) rather than reusing `eval-retry-count.txt`.
- **`oracles/code-run-gate.yaml` reuse shape**: invoked via `loop: oracles/code-run-gate`
  with `with: {run_dir: ..., issue_id: ..., run_cmd: ..., health_url: ...}` (its
  `parameters:` block, required: `run_dir`, `issue_id`; optional `min_pass_rate`,
  `health_bound_seconds`, `build_cmd`, `test_cmd`, `typecheck_cmd`, `lint_cmd`,
  `run_cmd`, `health_url`). Its `service_health` state (lines 308–364) already does
  "stand up the assembled project": launches `run_cmd` in the background, writes
  `${run_dir}/service.pid`, polls `health_url` via `curl --fail --max-time
  ${context.health_bound_seconds}`, tears down via a `trap cleanup EXIT`. Its terminals
  are `done`/`failed` (unlike `goal-cluster`, which has no `done` terminal and forces a
  content-based follow-up gate) — `on_yes`/`on_no` are directly usable without a
  `check_build_outcome`-style wrapper.
- **`output_numeric` evaluator shape for `score_acceptance`**: two existing forms —
  bare numeric stdout (`check_eval_retry_budget`, no `key:`) or `key: <name>`
  extracting a `name=value` line from multi-line output (`run_test` in
  `oracles/code-run-gate.yaml`, lines 201–249, `key: pass_rate` against a
  `pass_rate=$RATE` line). "pass count / total" scoring should follow the `key:` form.
- **Checks-JSON → shell-exec → aggregate template**: `oracles/code-run-gate.yaml`'s
  full chain (`resolve_commands` → `run_build`/`run_test`/`run_typecheck`/`run_lint` →
  `aggregate`, lines 85–428) is the closest existing precedent for
  `derive_acceptance_checks → run_acceptance → score_acceptance`: a sidecar JSON
  describes what to run, each `run_*` state self-skips when its command is
  null/absent, executes via `bash -c "$CMD" > sidecar 2>&1`, appends `exit_code=$RC`,
  and routes all outcomes to one `aggregate` state that classifies
  SKIP/pass/fail per check and reduces to a single verdict via `classify` + `route:`.
- **`${run_dir}`/`artifact_versioning` convention**: `rn-build.yaml` sets no
  `artifact_versioning: true` (its phases are one-shot); a new
  `${context.run_dir}/acceptance/checks.json` and `.../results.json` can write
  directly without the case-absolute-path idiom `oracles/code-run-gate.yaml` uses
  internally (rn-build's own `run_dir` is already resolved before interpolation).
- **Existing E2E test to extend**: `scripts/tests/test_rn_build.py`, class `TestE2E`,
  method `test_rn_build_smoke` (lines 531–641) — guarded by
  `if not os.environ.get("PYTEST_INTEGRATION"): pytest.skip(...)` as the first line of
  the test body (not a decorator), `@pytest.mark.integration` + `@pytest.mark.slow`.
  It shells out `ll-loop run rn-build --context spec=specs/sample.md --context
  max_eval_retries=0`, diffs `.loops/runs/rn-build-*` before/after to find the new run
  dir, and asserts on files/stdout content (e.g. `(run_dir /
  "epic-id.txt").exists()`). The acceptance-results extension should add an analogous
  `(run_dir / "acceptance" / "results.json").exists()` assertion in this same method.
- **Structural coverage gap**: `REQUIRED_STATES` in `test_rn_build.py` (lines 22–48) is
  a fixed-state-set structural test (`test_has_required_states`) — it will need the new
  state names (`derive_acceptance_checks`, `run_acceptance`, `score_acceptance`,
  `acceptance_failed`, and the `finalize_acceptance_failed` pair) added, or the new
  states won't be enforced as required by the existing suite.

## Impact

- **Priority**: P2 - Turns the spec's acceptance criteria into an executable contract,
  closing the cross-feature integration gap that currently escapes all automated gates.
- **Effort**: Large - Three new states plus a new terminal in `rn-build.yaml`, wired
  into the existing eval-retry loop; built on FEAT-2413's run-gate primitives.
- **Risk**: Medium - Adds a new failure terminal to the core build path; generic
  (non-archetype) check derivation limits false negatives.
- **Breaking Change**: No

## Resolution

Implemented in `scripts/little_loops/loops/rn-build.yaml`. `eval_gate.on_yes` now enters
a five-state integration phase before `synthesize_result`:

1. `derive_acceptance_checks` (prompt) — converts each `## Acceptance Criteria` bullet
   into a runnable check in `${run_dir}/acceptance/checks.json`, quoting each criterion
   verbatim. All three edges route to `run_acceptance` (MR-4).
2. `run_acceptance` (shell) — stands up the assembled project (background process +
   `service.pid` + health poll + `trap cleanup EXIT`, the `code-run-gate service_health`
   pattern), then **executes** each check via `subprocess.run(["bash", "-c", …])` with a
   per-check timeout, writing a per-criterion breakdown to `acceptance/results.json`.
3. `score_acceptance` (shell, non-LLM) — scores `passed / executed` via `output_numeric`
   against `min_acceptance_pass_rate`; the human-readable breakdown goes to
   `acceptance/score.txt`.
4. `check_acceptance_retry_budget` → `capture_acceptance_failures` → `cluster_execute` —
   bounded remediation re-entry with its own `acceptance-retry-count.txt` counter.
5. `finalize_acceptance_failed` → `acceptance_failed` (`terminal: true, failure: true`,
   declared explicitly since the name is absent from `FAILURE_TERMINAL_NAMES`).

`synthesize_result` now reads `acceptance/results.json` and emits `acceptance_passed`
plus a per-criterion `acceptance` array. `max_steps` raised 30 → 40 to cover the longer
happy path plus a second remediation cycle.

### Deviations from the proposed solution

- **`oracles/code-run-gate.yaml` is not delegated to.** The issue (and the wiring pass's
  "Correction to Proposed Solution") proposed invoking it via `loop:
  oracles/code-run-gate` to stand up the service. That cannot work regardless of the
  proposed skip-sentinel pre-requisite: `service_health` tears the service down through
  its own `trap cleanup EXIT` before the state returns, so a delegated call always hands
  back a **stopped** project — the acceptance checks would have nothing to run against.
  Service startup and check execution must share one shell state. `run_acceptance`
  therefore reuses the *pattern* (background launch, PID file, bounded health poll, trap
  teardown) rather than the loop. This also sidesteps the redundant
  build/test/typecheck/lint re-run the wiring pass flagged, so the proposed
  `health_only:`/skip-sentinel change to `code-run-gate.yaml` was not needed and that
  file is untouched.
- **`output_numeric` uses a bare-numeric stdout, not `key: pass_rate`.** The research
  findings cited `code-run-gate.yaml`'s `run_test` (`key: pass_rate`) as the precedent
  for keyed extraction. `EvaluateConfig` (`fsm/schema.py`) has **no `key` field**, and
  `evaluate_output_numeric` does `float(output.strip())` on the whole stdout — so that
  form is inert and `run_test`'s evaluator actually returns `verdict="error"` today
  (benign there only because its `on_no`/`on_error` share a target). `score_acceptance`
  echoes a bare number and routes its breakdown to a sidecar file instead. Filed
  separately rather than fixed here — out of this issue's scope.
- **All-skipped backstop added** (not in the original plan): the derivation may mark a
  criterion unrunnable via `skip_reason`, which excludes it from the denominator. To stop
  the LLM clearing the gate by declining to write checks, an `executed == 0`
  `results.json` scores `0.0` rather than a vacuous `1.0`.

### Verification

- Full suite green: `16927 passed, 42 skipped`.
- `ll-loop validate rn-build` passes; no new warnings (MR-1 satisfied — the LLM
  derivation is backstopped by `run_acceptance`'s `exit_code` and `score_acceptance`'s
  `output_numeric`; no MR-13 abandonment warning).
- 23 new structural tests in `TestRnBuildAcceptanceGate`, plus the new state names in
  `REQUIRED_STATES`; `test_eval_gate_routes_to_synthesize_on_success` was rewritten as
  `test_eval_gate_routes_to_acceptance_phase_on_success` for the moved success edge.
- All four new shell states were **executed for real** against fixtures through the FSM
  interpolator, covering: all-pass, partial-fail, every-criterion-skipped, check timeout,
  service start/teardown, and missing `checks.json`. Confirmed stdout is always
  `float()`-parseable and that only a genuine full pass scores `1.0`.
- `TestE2E::test_rn_build_smoke` extended to assert `acceptance/results.json` exists and
  carries a per-criterion breakdown (still gated on `PYTEST_INTEGRATION=1`; not run here
  — it spawns real Claude Code sessions with 30–120 min wall time).

## Status

**Done** | Created: 2026-06-30 | Completed: 2026-07-28 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-07-28T21:27:28Z - `12aaba7f-eb2b-4c8d-a1c6-e3e26608a49c.jsonl`
- `/ll:ready-issue` - 2026-07-28T20:58:44 - `948ce6d9-05ea-4e2e-85b3-4d6a2b1c744a.jsonl`
- `/ll:confidence-check` - 2026-07-28T00:00:00Z - `0344e746-9325-4a7a-80a6-c1bae9d5e0c8.jsonl`
- `/ll:confidence-check` - 2026-07-28T21:00:00Z - `43e8e3ff-2fac-432e-9bf5-0b9e85b1153e.jsonl`
- `/ll:wire-issue` - 2026-07-28T20:26:57 - `0089c154-b986-4f04-8c25-38216208d9ae.jsonl`
- `/ll:refine-issue` - 2026-07-28T20:15:17 - `2e633055-0343-4374-ac62-1c059b01d283.jsonl`
