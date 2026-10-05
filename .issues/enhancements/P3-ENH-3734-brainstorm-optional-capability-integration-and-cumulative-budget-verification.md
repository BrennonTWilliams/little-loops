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

- Deterministic executor fixtures exercise all eight combinations of the three built capability knobs, including explicit mixed-mode overrides. No fixture requires a live LLM or Playwright.
- Grounding runs before shortlisting; materialize only receives surviving finalists; the pre-tournament floor prevents judging an empty or one-player field. Candidates without valid mockup source never enter HTML fallback judging.
- Pre-mortem malformed output, host error, and timeout preserve idea bodies, ranking, slots and winners.md, mark the skip, and continue to render/validate/sinks. A deterministic engine I/O error remains a run failure.
- The cumulative parent step/time budget includes the auto classifier, the maximum nine lenses, materialize's preparation/render bounds, bounded retries, tournament salvage, both pre-mortem calls, every sink branch, and finalization. Engine time-guard values agree with shipped YAML.
- A documented mixed-capability reference run proves the interaction; record actual calls (including retries), input/output/cache tokens, elapsed time, selected judge mode, degradation reasons and import origin. This is separate from the individual capability runs owned by FEAT-3584/3585/3586.
- Web grounding, reserve promotion, and reframe remain deferred and do not gate closure.

## Motivation

Independent feature fixtures cannot show that one capability's filtering, fallback or timeout leaves valid inputs and enough budget for the next capability. An explicit integration child gives this promised closing work an owner without holding up the core engine.

## Proposed Solution

Use the real FSM executor with MockActionRunner outputs and temporary run artifacts. Extend scripts/tests/test_brainstorm.py for orchestration and scripts/tests/test_brainstorm_engine.py for artifact invariants. Derive budget assertions from the actual built state paths, rather than each child adding to a stale max_steps == 60 assertion.

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

### Documentation
- scripts/little_loops/loops/README.md — measured combined cost/fallback behavior, if clarification is needed.

## Program Design

### Types

- CapabilityCase: {ground: str, materialize: str, premortem: bool, expected_judge_mode: str, expected_terminal: str}
- BudgetCase: {state_visits: list[str], elapsed_ms: int, expected_terminal: str}

### Signatures

- `run_capability_case(case: CapabilityCase, tmp_path: Path) -> ExecutionResult` — test helper driving FSMExecutor with MockActionRunner (existing little_loops.fsm.executor.ExecutionResult).
- `assert_portfolio_invariants(run_dir: Path) -> None` — test helper asserting eligible-only distinct slots, immutable sink bodies, and recorded skip/degradation flags.

### Call Path

FSMExecutor.run -> ground_codebase -> shortlist_apply -> materialize_check -> check_floors_pre_tournament -> tournament -> portfolio -> annotate -> render_report -> validate_portfolio -> route_sink

## Scope Boundaries

Owns optional-capability combinations and cumulative step/time verification only. Individual feature implementation, enablement and reference runs remain in FEAT-3584/3585/3586; core evaluation remains in FEAT-3596. Deferred web/reframe/reserve promotion and a new evaluator/model are out of scope.

## Implementation Steps

1. Read the landed optional implementations and enumerate each combined success, skip, degradation and salvage path.
2. Add the combination matrix and targeted interaction failure fixtures using MockActionRunner.
3. Derive cumulative step/time bounds; correct shipped budget constants and assertions if needed.
4. Record the mixed-capability reference run under postmortems/ and verify the full local suite.

## Impact

- **Priority**: P3 — required optional-epic closing coverage with no core-engine dependency reversal.
- **Effort**: Medium — executor fixtures, budget arithmetic, and one reference run.
- **Risk**: Low — largely verification of already-built capabilities.
- **Breaking Change**: No.

## Acceptance Criteria

- All eight knob combinations and mixed-mode overrides have deterministic passing fixtures; ground-false ideas never reach materialize or judging.
- Targeted fixtures cover grounding reducing eligible ideas below the generation floor, materialize reducing valid-source finalists below two, HTML fallback with at least two valid sources, and pre-mortem error/timeout preserving ranked results and sink bodies.
- The longest success and salvage paths fit the cumulative max_steps/timeout values with the required tail reserve; engine/YAML budget agreement is asserted.
- One mixed-capability reference run and its actual resource usage/import origin are recorded; it does not replace the individual feature runs.
- python -m pytest scripts/tests/ exits 0 and both brainstorm loops validate.
- EPIC-3687 can close on the three capabilities plus this verification; deferred web/reframe work is not a closing requirement.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-05 | Priority: P3
