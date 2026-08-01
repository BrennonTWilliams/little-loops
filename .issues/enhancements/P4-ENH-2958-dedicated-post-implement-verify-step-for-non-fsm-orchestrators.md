---
id: ENH-2958
title: Dedicated post-implement verify step for non-FSM orchestrators
type: ENH
priority: P4
status: open
captured_at: '2026-08-01T01:25:49Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- ENH-2854
- ENH-2935
- BUG-2954
confidence_score: 96
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
decision_needed: false
---

# ENH-2958: Dedicated post-implement verify step for non-FSM orchestrators

## Summary

`ll-auto`, `ll-parallel`, and `ll-sprint` have exactly one agent-executing
phase (Phase 2, implement). Phase 3 "verify" runs no agent — it is a sequence
of local checks. That means any guard needing a *post-implementation* window
to bracket has nothing to bracket, and ENH-2854's stated design constraint
cannot be satisfied on these paths. Give the non-FSM orchestrators a real
post-implement verification step, matching the FSM adapter's structure.

## Current Behavior

`issue_manager.py:1049-1136` (Phase 3) calls `verify_issue_completed`,
`check_content_markers`, `verify_work_was_done`, and
`complete_issue_lifecycle` — no `run_claude_command`, no
`run_with_continuation`, no subprocess capable of modifying a file.

The FSM adapter, by contrast, brackets a separate verify **state's own action
dispatch** (`fsm/executor.py:1407-1420`), which is a genuine agent
invocation. Its inline comment states the intent:

> "Bracket the action dispatch below (not the whole state) so the snapshot
> reflects test-file state immediately before this guarded state's own action
> runs — a TDD implement phase that legitimately wrote tests earlier in the
> run must not trip a later, separate verify state's guard."

ENH-2854 specifies the same requirement for all orchestrators:

> "Scope the guard to the verification step, not the whole issue run. ... The
> snapshot is taken at verify-step start, never at issue start."

On the non-FSM path there is no such step, so the requirement is
structurally unmeetable, not merely unimplemented.

## Expected Behavior

The non-FSM orchestrators run an actual post-implementation verification step
— an agent invocation distinct from Phase 2 — that guards can bracket the way
the FSM adapter does. ENH-2854's constraint then holds uniformly across all
four orchestrators instead of holding only for FSM loops.

## Motivation

BUG-2954 works around this gap rather than closing it. Because no window can
separate legitimate TDD test writes from tampering on these paths, BUG-2954
replaces the window with a content-based weakening heuristic (assertion
counts, test-function counts, skip markers). That is a reasonable mitigation,
but it is strictly weaker than the FSM path's byte-level strictness: a
tampering edit that preserves assertion and test counts — inverting a
comparison, loosening a bound, swapping an expected value — is invisible to
it, while the FSM path catches any byte change.

Capturing this keeps the divergence visible. Without it, the gap survives
only as a bullet inside a bug that is about to close, and the two paths
quietly enforce different standards.

## Proposed Solution

Introduce a post-implement verification invocation in the non-FSM
orchestrators and bracket the tamper guard around it:

- Add a Phase 2.5 agent step between implement and the existing local
  verification — the natural content is running the project's test command
  and reporting results, which is work the orchestrators already want.
- Capture `snapshot_test_paths(...)` immediately before that step and compare
  immediately after, exactly as `fsm/executor.py:1407-1474` does.
- Once that window exists, the non-FSM path can adopt full byte-level
  strictness and BUG-2954's weakening heuristic becomes a fallback for
  configurations that opt out of the extra step.

### Open questions

- **Cost.** This adds an agent invocation per issue across all three
  orchestrators — a real increase in wall-clock and token spend on every
  run. Whether that is worth uniform guard strictness is the central
  trade-off, and a legitimate reason to decline this issue.
- **Opt-in vs default.** A config key gating the extra step would bound the
  cost, at the price of two enforcement tiers to reason about.
- **Overlap with existing verification.** `/ll:run-tests` and the learning-
  test gate already invoke agents in adjacent contexts; this step may be
  better folded into one of them than added alongside.

See Option A/B/C decision under Proposed Solution → Codebase Research Findings.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Option A**: Default-on new post-implement verify step — every `ll-auto`/
`ll-parallel`/`ll-sprint` issue run pays the extra agent invocation
unconditionally, no config key.

> **Selected:** Option B — config-gated opt-in, matching the codebase's
> established convention for features that add per-issue agent-invocation cost.

**Option B**: Config-gated opt-in new step — add
`TamperGuardConfig.post_implement_verify_step: bool = False`
(`config/features.py:852-860`), mirroring the established convention for
any feature that adds a new invocation/runtime cost: `LearningTestsConfig.enabled:
bool = False` (`config/features.py:484`) and its call-site gate at
`issue_manager.py:874` (`if config.learning_tests.enabled is True and not
dry_run:` — deliberately `is True`, not truthy, so mocks can't
accidentally enable it) and `worker_pool.py:62`
(`if not br_config.learning_tests.enabled: return True`, commented
"disabled / skipped runs incur no JIT extraction cost"). Every other
cost-adding boolean in `config/features.py` follows the same default-off
shape (`PreCompactRubricConfig.enabled = False`, `DecisionsConfig.enabled =
False`, `SyncConfig.enabled = False`); default-`True` booleans in this file
are reserved for passive toggles on already-present machinery
(`ScanConfig.enabled = True`, `AnalyticsCaptureConfig.corrections = True`),
not new agent invocations.

**Option C**: Fold the new verification into the existing Phase 3 "verify"
step instead of adding a separate one. Ruled out by research: Phase 3's
`verify_issue_completed()` (`issue_lifecycle.py:501-535`) is a pure
frontmatter read (checks `status in ("done", "cancelled")`) with no
subprocess or agent call anywhere in it, and `rn-implement.yaml` has no
`run-tests`/`check-code`/`confidence-check` states either — there is no
existing agent-invoking verify step to fold into on either the non-FSM or
FSM-adjacent path. Folding in would still mean writing a new invocation, just
inside an existing function name rather than a new one — no cost savings,
only lost clarity (a "zero-cost verify" function silently gaining a real
one).

**Recommended**: Option B — matches the codebase's own established
convention for exactly this kind of change (new per-issue agent
invocation), and Option C has no ready host to fold into.

### Decision Rationale

**Selected: Option B** — config-gated opt-in (`TamperGuardConfig.post_implement_verify_step: bool = False`).

Option B is the only option consistent with how this codebase already
gates every other feature that adds a new per-issue agent invocation or
runtime cost: `LearningTestsConfig.enabled: bool = False`
(`config/features.py:484`), guarded `is True` (not truthy) at
`issue_manager.py:874` and short-circuited before target resolution at
`worker_pool.py:62` specifically so disabled runs incur zero cost. Every
other cost-adding boolean in `config/features.py`
(`PreCompactRubricConfig`, `DecisionsConfig`, `SyncConfig`) follows the
same default-off shape; default-`True` booleans in that file are reserved
for passive toggles on already-present machinery, not new invocations.
Option C (fold into existing Phase 3 verification) has no real host:
`verify_issue_completed()` (`issue_lifecycle.py:501-535`) is a pure
frontmatter read today, and `rn-implement.yaml` has no
test/check-code/confidence-check states either — "folding in" would still
mean writing a new invocation, just inside a function callers currently
assume is free, which is worse than a clearly-named new gated step.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-----------:|:----------:|:------------:|:----:|:-----:|
| A — default-on | 0 | 3 | 2 | 1 | 6/12 |
| **B — config-gated opt-in** | **3** | 2 | 3 | 3 | **11/12** |
| C — fold into existing verify | 0 | 1 | 1 | 1 | 3/12 |

Key evidence: `config/features.py:484` (`LearningTestsConfig.enabled`),
`issue_manager.py:874`, `worker_pool.py:62`, `issue_lifecycle.py:501-535`
(Phase 3 is a frontmatter-only check today, no agent invocation to fold
into).

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — new phase between Phase 2
  (~L927-964) and Phase 3 (~L1049).
- `scripts/little_loops/parallel/worker_pool.py` — same step between Step 5
  (`_run_with_continuation`, ~L537) and Step 7 (`_verify_work_was_done`).
- `scripts/little_loops/work_verification.py` — accept a live pre-step
  snapshot once one genuinely exists, rather than reconstructing "before"
  from git history.
- `scripts/little_loops/config/features.py:851-860` — `TamperGuardConfig`
  dataclass needs the new gating field (e.g. `post_implement_verify_step`)
  and a `from_dict` default, if the cost/opt-in question resolves to a config
  gate. Named in this issue's own Codebase Research Findings as the natural
  home for the field, but not previously listed here as a file to modify.
  _Wiring pass added by `/ll:wire-issue`._
- `scripts/little_loops/config-schema.json:1316-1328` — the `tamper_guard`
  object schema has `"additionalProperties": false`; a new
  `TamperGuardConfig` field silently fails config validation unless a
  matching `"properties"` entry is added here alongside the dataclass
  change. _Wiring pass added by `/ll:wire-issue`._
- `scripts/little_loops/config/core.py` — `BRConfig.to_dict()`'s
  `tamper_guard` block (`L883-885`) hardcodes
  `{"policy": self._tamper_guard.policy}`; a new
  `TamperGuardConfig.post_implement_verify_step` field must be added to
  this block or `ll-config get tamper_guard.post_implement_verify_step`
  (via `resolve_variable()`, `L924-946`, which walks `to_dict()`) silently
  resolves to `None` even though the dataclass field exists and is
  readable directly via `config.tamper_guard.post_implement_verify_step`.
  _Wiring pass added by `/ll:wire-issue` (2nd pass)._

### Similar Patterns
- `scripts/little_loops/fsm/executor.py:1407-1474` — the snapshot-on-entry /
  compare-on-exit bracket to model this on.
- `scripts/tests/test_fsm_executor.py:10702` `TestTamperGuardExecutorHook`,
  specifically `test_tdd_mode_does_not_trip_guard_on_separate_verify_state`
  (`L10865`) — the closest existing analog to this issue's core requirement
  ("Phase 2.5 must not trip on Phase 2's own legitimate test writes"); uses a
  two-step FSM (`implement` → `verify`) with a runner that writes a new test
  file during `implement`, then asserts the later `verify` state is
  unaffected. New non-FSM tests should mirror this shape. _Wiring pass added
  by `/ll:wire-issue`._

### Configuration
- Likely a new key gating the step (see Open questions); to be settled during
  refinement.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:2339-2387` — the `verify_work_was_done()` doc block;
  `L2360-2367` explicitly states *"Unlike the FSM adapter, this path has no
  live pre-step snapshot... so 'before' is reconstructed from git
  history"* — this sentence becomes false once the live-snapshot branch
  exists and must be rewritten to describe both paths (live snapshot when
  the new step ran, git-reconstruction fallback otherwise). `L139`'s
  `BRConfig` field table also needs a row if a new `TamperGuardConfig` field
  is added.
- `docs/reference/CONFIGURATION.md:1029-1041` — the `### tamper_guard`
  section documents `TamperGuardConfig` as single-key (`policy`); a new
  field needs its own table row, and the framing sentence needs a clause
  acknowledging the step it now gates.
- `docs/guides/LOOPS_GUIDE.md:695-700` — the `### Tamper Guard` section
  states *"This `tamper_guard:` key is FSM-only. `ll-auto`, `ll-parallel`,
  and `ll-sprint` verify completed work in plain Python... never entering the
  FSM"* — a direct claim of the exact asymmetry this issue exists to close.
  Needs rewriting once the bracket is symmetric, while still distinguishing
  the two independent `tamper_guard` config keys (FSM state key vs. project
  `tamper_guard.policy` key).
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — appears in tamper-guard
  grep hits; worth a scan pass for FSM-vs-non-FSM asymmetry claims during
  implementation (not confirmed to need edits).
- `scripts/little_loops/__init__.py:67,124` — re-exports
  `verify_work_was_done` as public API; signature drift here is invisible
  unless checked against `docs/reference/API.md` when the new
  `pre_step_snapshot` param is added.

_Wiring pass added by `/ll:wire-issue` (2nd pass):_
- `docs/ARCHITECTURE.md` § "Sequential Mode (ll-auto)" — the `mermaid
  sequenceDiagram` (~`L411-450`) has explicit `Note over Manager,Claude:
  Phase 2: Implementation` (`L431`) and `Note over Manager,Git: Phase 3:
  Verification` (`L437`) annotations documenting the exact boundary this
  issue inserts a new phase into; goes stale (missing Phase 2.5) unless
  updated alongside the code change.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`issue_manager.py` Phase 2/3 seam is a literal empty gap, not busy code.**
  `_baseline_sha` is captured at `L921-926` (`git rev-parse HEAD`, before the
  implement call) — this is the exact point a live
  `test_tamper_guard.snapshot_test_paths(...)` call would replace/augment.
  The sole agent invocation is `run_with_continuation(...)` at `L946-960`.
  Between the failure-handling block resolving (`~L1049`) and the
  `# Phase 3: Verify completion` comment, nothing runs — no agent call, no
  local check — confirming this is the seam to insert the new step into.
- **`worker_pool.py`'s current tamper-guard call already drops `baseline_sha`.**
  Step 7's `_verify_work_was_done` call site (`L593-598`) calls
  `verify_work_was_done(self.logger, changed_files, config=self.br_config,
  repo_root=worktree_path)` — it omits `baseline_sha` entirely, so
  `_run_non_fsm_tamper_guard`'s reconstruction falls back to `"HEAD"` (current
  HEAD at verify time, not the pre-implement point). This is a second,
  narrower gap on the parallel path beyond the one this issue already
  describes: even the git-reconstruction fallback is weaker here than on the
  `ll-auto` path, which does thread `_baseline_sha`. The natural seam for the
  new step is between Step 5's agent call (`L533-541`) and Step 6
  (`L562-563`), with the live snapshot captured just before `L533`.
- **`ll-sprint` needs no separate change.** `cli/sprint/run.py` has no
  independent implement/verify phase logic — single-issue dispatch calls
  `issue_manager.process_issue_inplace(...)` directly (`L58-80`, `L802-812`),
  and multi-issue waves go through `ParallelOrchestrator(...).run()`
  (`L764-773`), which drives `WorkerPool` under the hood. A change to
  `issue_manager.py` and `worker_pool.py` alone is inherited by `ll-sprint`
  through both delegation paths — no `cli/sprint/run.py` edit is structurally
  required.
- **`work_verification.py`'s git-reconstruction call is explicitly marked as
  the gap this issue closes.** `_run_non_fsm_tamper_guard` (`L63-106`) calls
  `snapshot_test_paths_at_ref(repo_root, baseline_sha or "HEAD",
  candidate_paths)` at `L92`; its docstring (`L69-75`) already states: "Unlike
  the FSM adapter (ENH-2934), this path never captured a live pre-step
  snapshot... so 'before' is reconstructed from git history... instead." The
  minimal signature change is adding an optional
  `pre_step_snapshot: TamperSnapshot | None = None` param to
  `verify_work_was_done()`, threaded into `_run_non_fsm_tamper_guard`, which
  would branch to use it directly (skipping the git-history call) when
  present, falling back to today's reconstruction otherwise — preserving
  compatibility for any caller without a live snapshot.
- **Tamper-guard primitives to call directly** (`test_tamper_guard.py`):
  `snapshot_test_paths(paths, repo_root) -> TamperSnapshot` (`L60-65`, the
  live/on-disk primitive the new step needs, vs. `snapshot_test_paths_at_ref`
  at `L68-83`, the git-history fallback), `tamper_guard_candidate_paths(...)`
  (`L86-106`), `tamper_guard_changed_files(...)` (`L109-124`), and
  `run_tamper_guard(before, changed_files, config, policy, repo_root) ->
  TamperReport` (`L252-279`) — the same functions `fsm/executor.py` calls at
  `L1407-1474` and `work_verification.py` already imports.
- **Config-gate naming precedent**: `TamperGuardConfig` dataclass
  (`config/features.py:852-860`, currently just `policy: str = "fail"`) is
  wired into `BRConfig` at `config/core.py:289-290` (construction) and
  `L384-386` (`@property tamper_guard`). A new opt-in key for this step's
  cost/opt-in question would most consistently live as a second field on that
  same dataclass (e.g. `TamperGuardConfig.post_implement_verify_step: bool`)
  rather than a new top-level config object.

### Tests
- `scripts/tests/test_issue_manager.py` — existing Phase-boundary tests name
  the phase and issue ID directly in their docstrings rather than asserting
  on log strings (e.g. `L2800`: `"""baseline_sha captured before Phase 2 is
  forwarded to verify_work_was_done."""`) — the convention new "Phase 2.5"
  tests should follow, asserting on `IssueProcessingResult` fields / mocked
  `run_with_continuation` call args.
- `scripts/tests/test_worker_pool.py` — equivalent phase-boundary coverage
  for the `ll-parallel` path; no existing test currently asserts on
  `_verify_work_was_done`'s missing `baseline_sha` kwarg at the Step 7 call
  site.
- `scripts/tests/test_work_verification.py` — currently has no test
  exercising `_run_non_fsm_tamper_guard` by name (grepped, no matches); a new
  `pre_step_snapshot` param would need coverage here, including the
  count-preserving tamper case (Implementation Step 5) that BUG-2954's
  heuristic cannot catch.
- `scripts/tests/test_test_tamper_guard.py` — existing core coverage for
  `TamperReport`/`run_tamper_guard`; the live `snapshot_test_paths` call this
  issue reuses is already exercised here, so no core-logic change is implied.

_Wiring pass added by `/ll:wire-issue` — tests that will break, not just gain
coverage:_
- `scripts/tests/test_issue_manager.py:2797`
  `test_baseline_sha_passed_to_verify_work_was_done` — asserts
  `mock_verify.assert_called_once_with(mock_logger, baseline_sha=test_sha,
  config=mock_config)`, an exact-kwargs match on the
  `verify_work_was_done` call site at `issue_manager.py:1109`. If Phase 2.5
  passes `pre_step_snapshot=...` at that same call site, this assertion
  breaks and must be updated to include the new kwarg.
- `scripts/tests/test_config.py:2434-2466` `TestTamperGuardConfig`,
  specifically `test_tamper_guard_in_to_dict` (`L2459-2462`) — hardcodes
  `assert result["tamper_guard"] == {"policy": "fail"}`, a dict-equality
  assertion that breaks the moment `TamperGuardConfig.to_dict()` emits a
  second key. Update alongside the dataclass change; the same test class's
  `test_from_dict_with_defaults`/`test_from_dict_with_all_fields`/
  `test_brconfig_defaults`/`test_resolve_variable_tamper_guard` are the
  pattern to extend for the new field (per-field default + explicit-value
  cases).
- `scripts/tests/test_config_schema.py:359-371`
  `test_tamper_guard_in_schema` — asserts `additionalProperties is False`
  and inspects `properties["policy"]` specifically; needs a companion
  assertion for the new field once it's added to `config-schema.json`.

_Wiring pass added by `/ll:wire-issue` (2nd pass):_
- `scripts/tests/test_config.py::TestTamperGuardConfig::test_resolve_variable_tamper_guard`
  (`L2464-2466`) — existing round-trip pattern asserting
  `config.resolve_variable("tamper_guard.policy") == "fail"`; the new
  field needs an analogous `resolve_variable("tamper_guard.post_implement_verify_step")`
  case, which only passes once `config/core.py`'s `to_dict()` gap above is
  fixed.
- Test-shape precedent for the new default-`False` gated step:
  `scripts/tests/test_issue_manager.py::TestAutoManagerLearningGate`
  (`L4215-4469`, e.g. `test_gate_not_invoked_when_learning_tests_disabled`
  at `L4451-4469`) and
  `scripts/tests/test_worker_pool.py::TestPerWorktreeProofFirstGate`
  (`L3264-3488+`, e.g. `test_gate_skipped_when_lt_disabled` at
  `L3305-3321`) — both test an existing `enabled: bool = False`-gated
  agent-invocation step the same shape as `post_implement_verify_step`;
  follow this pattern (disabled-config fixture asserts the new call is
  skipped, enabled-config fixture asserts it's invoked once) rather than
  inventing a new test shape.
- `scripts/tests/test_sprint_integration.py`, `scripts/tests/test_cli_sprint.py`,
  `scripts/tests/test_sprint.py` — all call/mock `process_issue_inplace()`
  directly (the function Phase 2.5 is inserted into). Scope Boundaries
  already confirms `cli/sprint/run.py` needs no source edit, but these
  tests exercise `process_issue_inplace()`'s internal call sequence
  through the `ll-sprint` delegation path and should be scanned for
  breakage from the inserted step (mocked call counts/ordering), not just
  the `test_issue_manager.py`/`test_worker_pool.py` suites already listed.

## Program Design

_Sketch only — the cost/opt-in trade-off under Open questions determines
whether a config gate exists and where the boundary sits. Re-run
`/ll:refine-issue` after that decision before implementing._

### Types

New dataclass `VerifyStepResult`, returned by the new step so callers can
distinguish "guard tripped" from "step itself failed":

- `ran: bool`
- `tamper_passed: bool`
- `error: str`

### Signatures

- `run_post_implement_verify(logger: Logger, config: BRConfig, repo_root: Path) -> VerifyStepResult`

Captures `snapshot_test_paths` before dispatching the agent invocation and
calls `run_tamper_guard` immediately after, mirroring the FSM bracket.

### Call Path

`process_issue_inplace` → `run_post_implement_verify` → `snapshot_test_paths`
→ `run_tamper_guard` → `verify_work_was_done`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The FSM bracket to mirror (`fsm/executor.py:1407-1474`) resolves policy via
`self._effective_tamper_guard_policy(state)` (`L1295-1312`), snapshots via
`test_tamper_guard.snapshot_test_paths(self._tamper_guard_candidate_paths(repo_root),
repo_root)` immediately before the action dispatch, then — unconditionally
whenever a `_tamper_before` snapshot exists, regardless of the action's own
exit code — calls `run_tamper_guard(before, changed_files, config, policy,
repo_root)` and only overrides the state's verdict when `policy == "fail"`
and `not tamper_report.passed`. `policy == "revert"` self-heals via
`apply_tamper_policy`'s `git checkout --` and only routes on residual
unresolved findings; `policy == "allow"` never routes. `run_post_implement_verify`
should reproduce this exact routing distinction: `"fail"` blocks completion
(propagates a failure the existing Phase 3 failure path already knows how to
handle), `"revert"` self-heals silently, `"allow"` records only.

For the agent invocation itself, both non-FSM orchestrators already have a
one-shot dispatch convention to reuse: `issue_manager.py`'s Phase 2 calls
`run_with_continuation(_initial_cmd, logger, timeout=..., ...,
resume_command=_slash_cmd, ...)` (`L946-960`), and `worker_pool.py`'s Step 5
calls `self._run_with_continuation(manage_cmd, worktree_path,
issue_id=issue.issue_id)` (`L537-541`) — both wrapping the same
`subprocess_utils.run_claude_command` base dispatcher. `run_post_implement_verify`
should follow the same convention rather than introducing a new dispatch
mechanism, since it needs the same timeout/continuation/error-classification
handling Phase 2 already has for "must not itself block completion" (Risk,
Impact section).

No existing dataclass in the codebase uses the literal `ran`/`tamper_passed`/
`error` field names sketched under Types above — the closest structural
precedent is `TamperReport` itself (`test_tamper_guard.py:39-44`: `policy`,
`findings`, `reverted`, `passed`), which `VerifyStepResult` would presumably
wrap or carry a copy of rather than duplicate.

## Implementation Steps

1. Decide the cost/opt-in question above — this gates everything else.
2. Add the post-implement agent step to `issue_manager.py`, bracketed by
   `snapshot_test_paths` / `run_tamper_guard`.
3. Mirror it in `parallel/worker_pool.py`.
4. Let `work_verification` consume the live snapshot instead of the
   git-reconstructed "before" when the step ran.
5. Add tests proving the non-FSM path now matches the FSM path's strictness,
   including a count-preserving tamper (inverted comparison) that BUG-2954's
   heuristic cannot catch.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

6. If step 1 resolves to a config gate, add the field to
   `TamperGuardConfig` (`config/features.py:851-860`) and a matching
   `"properties"` entry in `config-schema.json`'s `tamper_guard` object
   (`L1316-1328`, `additionalProperties: false` rejects unknown keys
   silently otherwise).
7. Update `test_config.py:2434-2466` (`TestTamperGuardConfig`, esp.
   `test_tamper_guard_in_to_dict`) and `test_config_schema.py:359-371`
   (`test_tamper_guard_in_schema`) for the new field.
8. Update `test_issue_manager.py:2797`
   (`test_baseline_sha_passed_to_verify_work_was_done`) if Phase 2.5 passes
   `pre_step_snapshot` at the same `verify_work_was_done` call site the test
   asserts exact kwargs on.
9. Update `docs/reference/API.md` (`L2360-2367`'s now-false "no live
   pre-step snapshot" claim, `L139`'s `BRConfig` table),
   `docs/reference/CONFIGURATION.md` (`L1029-1041` tamper_guard table), and
   `docs/guides/LOOPS_GUIDE.md` (`L695-700`'s "tamper_guard is FSM-only"
   claim) to reflect the now-symmetric bracket.
10. Add the new field to `BRConfig.to_dict()`'s `tamper_guard` block
    (`config/core.py:883-885`) alongside the `config-schema.json`/dataclass
    changes in step 6 — otherwise `ll-config get
    tamper_guard.post_implement_verify_step` silently resolves to `None`
    via `resolve_variable()` even though the field exists on the dataclass.
11. Update `docs/ARCHITECTURE.md`'s § "Sequential Mode (ll-auto)" sequence
    diagram (`L411-450`) to show the new Phase 2.5 step between the
    existing `Phase 2: Implementation` (`L431`) and `Phase 3: Verification`
    (`L437`) notes.

## Scope Boundaries

**In scope:**
- A post-implement agent verification step in `issue_manager.py` and
  `parallel/worker_pool.py`, with the tamper guard bracketed around it.
- Letting `work_verification` consume a live pre-step snapshot when that step
  ran, instead of reconstructing "before" from git history.

**Out of scope:**
- The FSM adapter (`fsm/executor.py`) — already correct by construction; this
  issue exists to bring the non-FSM paths up to its behavior, not to change
  it.
- BUG-2954's content-based weakening classifier — it stays as the fallback
  for runs where the new step did not execute. This issue does not remove it.
- BUG-2957's config-file section scoping — an orthogonal defect in what
  counts as a config finding, independent of when the snapshot is taken.
- Changing `tamper_guard.policy` semantics or defaults.
- `cli/sprint/run.py` — confirmed by research to need no direct edit: `ll-sprint`
  has no independent implement/verify phase logic and inherits this change
  through its existing delegation to `issue_manager.process_issue_inplace`
  (single-issue path) and `ParallelOrchestrator`/`WorkerPool` (multi-issue
  waves).

## Impact

- **Priority**: P4 — the guard is functional after BUG-2954; this closes a
  strictness gap rather than a live failure. Should be explicitly declined
  rather than silently dropped if the cost is judged too high.
- **Effort**: Medium-Large — a new phase in two orchestrators plus per-issue
  runtime cost across all three entry points.
- **Risk**: Medium — adds an agent invocation to every issue run; a failure
  or timeout in the new step must not itself block completion.
- **Breaking Change**: No — additive, though it changes per-issue runtime.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Added by `/ll:confidence-check` — 2026-07-31:_

**Readiness: 80/100 | Outcome Confidence: 54/100**

### Concerns

- The issue's own Program Design section is explicitly marked "Sketch only"
  and instructs re-running `/ll:refine-issue` after the cost/opt-in decision
  is made — implementation should not start against the current sketch.

### Outcome Risk Factors

- **Open decision blocks scope.** The "Open questions" section leaves the
  central cost/opt-in trade-off unresolved (config gate vs. default-on vs.
  folding into existing verification). This is an open question that must
  resolve before implementing — it determines whether
  `config/features.py`'s `TamperGuardConfig` and `config-schema.json` are in
  scope at all (Implementation Step 6 is conditional on it), so starting
  without a decision risks building the wrong shape.
- **Change surface extends beyond the two orchestrators.**
  `verify_work_was_done()` is re-exported as public API
  (`scripts/little_loops/__init__.py:67,124`); the new `pre_step_snapshot`
  param is a signature change on a symbol outside this issue's primary
  files, and three existing tests are named as breaking
  (`test_issue_manager.py:2797`, `test_config.py:2459-2462`,
  `test_config_schema.py:359-371`), which raises the chance of collateral
  breakage during implementation.
- **Every issue run pays a new runtime cost.** The Impact section itself
  flags this as a legitimate reason to decline the issue — the decision to
  proceed should weigh wall-clock/token cost across `ll-auto`,
  `ll-parallel`, and `ll-sprint` before code is written.

## Session Log
- `/ll:confidence-check` - 2026-07-31T00:00:00Z - `01c8092d-4a0b-4561-9d74-6ed782c0fd00.jsonl`
- `/ll:wire-issue` - 2026-08-01T02:17:07 - `59471451-3cbc-48fe-998a-1caf4de5dce5.jsonl`
- `/ll:decide-issue` - 2026-08-01T02:08:24 - `ed49dcf9-c710-4f44-b8b9-6b8c5b53764c.jsonl`
- `/ll:refine-issue` - 2026-08-01T02:07:35 - `ed49dcf9-c710-4f44-b8b9-6b8c5b53764c.jsonl`
- `/ll:confidence-check` - 2026-07-31T00:00:00Z - `fd12cd94-ca63-46b3-88b0-1f689bfc8357.jsonl`
- `/ll:wire-issue` - 2026-08-01T01:57:31 - `7c54f229-9ea2-4347-bbf8-25da4b88edbd.jsonl`
- `/ll:refine-issue` - 2026-08-01T01:46:20 - `791535d4-3cff-4346-93b9-0e3280b0be01.jsonl`
- `/ll:capture-issue` - 2026-08-01T01:25:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e6bb49e-330c-449c-8327-ffed663d51ae.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P4
