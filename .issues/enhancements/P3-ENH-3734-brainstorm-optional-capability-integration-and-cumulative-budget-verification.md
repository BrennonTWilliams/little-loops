---
id: ENH-3734
type: ENH
title: Brainstorm optional capability integration and cumulative budget verification
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T17:25:13Z'
parent: EPIC-3687
labels:
- loops
- brainstorm
blocked_by:
- FEAT-3584
- FEAT-3585
- FEAT-3586
- FEAT-3596
---

# ENH-3734: Brainstorm optional capability integration and cumulative budget verification

## Summary

Close EPIC-3687 with executable coverage of combinations of the built codebase grounding, visual materialize, and annotate-only pre-mortem capabilities. Each optional feature already owns its own enablement, failure fixtures, budget increment, and reference run; this child owns their interactions and the cumulative budget. It does not gate EPIC-3581.

## Current Behavior

The pre-review EPIC-3687 Scope Boundary promised cross-capability fixtures and the all-features worst-case budget, but none of its three feature children owned that work; this issue is the assigned closing owner. FEAT-3596 closes on the core engine and explicitly excludes it. Earlier reserve-promotion fixtures require deferred web grounding and cannot be a v1 closing gate.

## Expected Behavior

- Deterministic executor fixtures exercise all eight combinations of the three built capability knobs, including explicit mixed-mode overrides. Set all three knobs explicitly in every case so preset defaults cannot change the matrix. Artifact-invariant fixtures execute real deterministic engine shell actions while stubbing prompt/browser responses; fully mocked actions are suitable for additional route-only checks, not evidence of file publication/recovery. Add interrupted materialize publication and tournament restart after committed image verdicts: reuse the manifest/probe plan without new calls; changed assets/inputs must fail without overwriting results. Persistent materialize/finisher snapshots are checked across resume/error routes rather than replaced with current mutated inputs. No fixture requires a live LLM or Playwright.
- Grounding runs before shortlisting; materialize only receives surviving finalists; the pre-tournament floor prevents judging an empty or one-player field. Candidates without valid mockup source never enter HTML fallback judging.
- Pre-mortem malformed output, host error, and timeout preserve idea bodies, ranking, slots and winners.md, mark the skip, and continue to render/validate/sinks. A deterministic engine I/O error remains a run failure.
- The cumulative parent step/time budget includes the auto classifier, the maximum nine lenses with bounded ingestion and each bounded grounding inventory, grounding's complete 60 s deadline/publication/state-timeout cost before shortlisting, materialize's preparation/render/compositing bounds, bounded retries, tournament salvage, both pre-mortem calls, every sink branch, and finalization. Grounding/materialize extend pre-tournament work; pre-mortem extends the post-tournament tail. Engine time-guard values agree with shipped YAML. All rate-limited prompt states explicitly disable both tiers, including rate_limit_long_wait_ladder:[0]. API/infra retries still count as dispatches and state visits.
- A documented all-three-enabled reference run proves the interaction (for example functional mode with materialize=render). Record true/false/unknown grounding counts, at least one verified true anchor, source-valid/rendered counts, image judge mode, successful winner/runner-up annotations, actual calls/retries, input/output/cache tokens, elapsed time, degradation reasons and import origin. A degraded/skipped run remains honest failure-path evidence and does not satisfy the all-three happy-path criterion. This is separate from the individual capability runs owned by FEAT-3584/3585/3586.
- Web grounding, reserve promotion, and reframe remain deferred and do not gate closure.

## Motivation

Independent feature fixtures cannot show that one capability's filtering, fallback or timeout leaves valid inputs and enough budget for the next capability. An explicit integration child gives this promised closing work an owner without holding up the core engine.

## Proposed Solution

Use the real FSM executor with a hybrid test runner and temporary run artifacts: execute deterministic engine actions with LL_PYTHON=sys.executable from a consuming-project cwd, and return stubbed outputs only for prompt/browser actions. MockActionRunner.run returns ActionResult metadata and performs no shell commands or artifact writes. Extend scripts/tests/test_brainstorm.py for orchestration and scripts/tests/test_brainstorm_engine.py for direct artifact invariants. Each feature that lands extends the assertion derived from built paths; this final child verifies it rather than owning the first replacement of max_steps == 60.

## Integration Map

### Files to Modify
- scripts/tests/test_brainstorm.py — combination fixtures and derived path/budget checks.
- scripts/tests/test_brainstorm_engine.py — combined artifact invariants.
- scripts/little_loops/loops/brainstorm.yaml and scripts/little_loops/brainstorm_engine.py — only budget/guard corrections demonstrated necessary by the fixtures.

### Behavior Parity

| Artifact | Behavior | Disposition |
|---|---|---|
| brainstorm.yaml | Capability routing, sink contract, and ranked portfolio | Preserved; tests cover combinations |
| brainstorm.yaml / brainstorm_engine.py | Per-feature budget increments | Changed only if the cumulative bound is insufficient; keep guard and YAML consistent |

### Dependent Files
- EPIC-3687; FEAT-3584/3585/3586; core evaluation evidence in FEAT-3596.

### Tests
- The existing local pytest suite enforces these fixtures, without live services or browser dependencies.
- `scripts/tests/test_fsm_executor.py::MockActionRunner.run` is a route-test convention, not an artifact integration runner. `scripts/little_loops/fsm/executor.py::FSMExecutor.run` and `_build_context` use the executor clock; fake-duration metadata alone does not advance elapsed time. Budget fixtures inject/advance that clock and transient-handler sleep, while direct engine deadline fixtures inject their own monotonic clock. Pytest never waits for live retry backoff.

### Documentation
- scripts/little_loops/loops/README.md — measured combined cost/fallback behavior, if clarification is needed.

## Program Design

### Types

- CapabilityCase: {ground: str, materialize: str, premortem: bool, expected_judge_mode: str, expected_terminal: str}
- BudgetCase: {state_visits: list[str], elapsed_ms: int, expected_terminal: str}

### Signatures

- `run_capability_case(case: CapabilityCase, tmp_path: Path) -> ExecutionResult` — test helper driving FSMExecutor with real deterministic actions and stub prompt/browser actions (existing little_loops.fsm.executor.ExecutionResult).
- `assert_portfolio_invariants(run_dir: Path) -> None` — test helper asserting eligible-only distinct slots, immutable sink bodies, and recorded skip/degradation flags.

### Call Path

FSMExecutor.run -> ground_codebase -> shortlist_apply -> materialize_check -> check_floors_pre_tournament -> tournament -> portfolio -> annotate -> render_report -> validate_portfolio -> route_sink

## Scope Boundaries

Owns optional-capability combinations and cumulative step/time verification only. Individual feature implementation, enablement and reference runs remain in FEAT-3584/3585/3586; core evaluation remains in FEAT-3596. Deferred web/reframe/reserve promotion and a new evaluator/model are out of scope.

## Implementation Steps

1. Read the landed optional implementations and enumerate each combined success, skip, degradation and salvage path.
2. Add the combination matrix and targeted interaction failure fixtures using the hybrid runner with real deterministic engine actions and stubbed prompt/browser responses.
3. Derive cumulative step/time bounds; correct shipped budget constants and assertions if needed.
4. Record the mixed-capability reference run under postmortems/ and verify the full local suite.

## Impact

- **Priority**: P3 — required optional-epic closing coverage with no core-engine dependency reversal.
- **Effort**: Medium — executor fixtures, budget arithmetic, and one reference run.
- **Risk**: Low — largely verification of already-built capabilities.
- **Breaking Change**: No.

## Acceptance Criteria

- All eight knob combinations and mixed-mode overrides have deterministic passing fixtures; ground-false ideas never reach materialize or judging.
- Targeted fixtures cover grounding reducing eligible ideas below the generation floor, non-Git/deadline unknown evidence remaining eligible, materialize reducing valid-source finalists below two, HTML fallback restoring only source-valid render failures, interrupted manifest publication, stale staging after a new render failure, image-tournament replay/asset conflict, stale pre-mortem/canary captures after runner exception/resume, and pre-mortem error/timeout preserving ranked results and sink bodies. Real engine actions establish the artifact outcomes, not pre-seeded expected end-state files.
- Nominal nine-lens success and recoverable salvage paths fit the cumulative max_steps/timeout values with the required tail reserve; engine/YAML budget agreement is asserted. API/infra/rate-limit error fixtures advance the executor clock and assert dispatch/visit/backoff counts. Retry-triggered step exhaustion follows finalize_failed; do not promise every retry pattern completes within the nominal cap. The guard reserves child timeout + final judge action + final maximum backoff + the derived post-tournament tail. Outer timeout termination is distinct from recoverable child-timeout salvage and cannot promise later finalization.
- One all-three-enabled successful mixed-capability reference run and its actual resource usage/import origin are recorded; it does not replace individual feature runs or count all-unknown/HTML-only/skipped execution as image/annotation success.
- python -m pytest scripts/tests/ exits 0 and both brainstorm loops validate.
- EPIC-3687 can close on the three capabilities plus this verification; deferred web/reframe work is not a closing requirement.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Review Notes

_2026-10-07 pre-implementation review, `/ll:advise` with claude-opus-5-5 (confidence 0.78):_ provisional until the optional children land (EPIC-3687 § Provisional). The matrix is 2^k over the capabilities actually built (a cancelled child shrinks it), and must report the remaining step slack (the core has about 9-11 visits before optional capabilities; all three add about 8; retries consume visits). Cumulative time follows EPIC-3581 § Budget sizing rule. No contract change.

_2026-10-05 executor review and `/ll:advise` with Opus (confidence 0.70):_ all four existing children suffice. Adopted real deterministic shell integration, fresh-attempt/render-source matching, bounded annotation/source validation, explicit retry/clock accounting and an all-three-enabled evidence run. Retained the eight-combination matrix with real artifact effects. Dissent: per-verdict stamp/compositing remains the heaviest P3 mechanism; no reversal of its existing capability-sanity purpose is warranted. Bounds are design choices, not live measurements.

_2026-10-05 follow-up, `/ll:advise` with Opus (confidence 0.72):_ added manifest/verdict restart and grounding-deadline combinations. Count grounding in pre-tournament elapsed time, not the post-tournament tail suggested by the advisor. No new live measurements; scope/ownership and deferred capabilities are unchanged.

## Status

**Open** | Created: 2026-10-05 | Priority: P3

## Session Log
- Pre-implementation review (`/ll:advise` with claude-opus-5-5, confidence 0.78; issue edits only) - 2026-10-07
- Implementation-readiness review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.74; issue revisions only) - 2026-10-06
- `/ll:refine-issue` - 2026-10-05T17:31:36-06:00 - `EPIC-3687 pre-implementation review`
