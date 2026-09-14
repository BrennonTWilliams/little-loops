---
id: ENH-3463
title: Unit-test an eval's grading logic deterministically before it is allowed to
  grade a live-model run
type: ENH
priority: P3
status: open
discovered_date: '2026-09-13'
labels: []
blocked_by:
- 'ENH-3462'
parent: EPIC-3475
epic: EPIC-3475
---

## Summary

`ll-harness` grading code decides pass/fail for every stochastic subject it evaluates, but nothing currently requires that the grading logic itself be tested. A scorer with an inverted comparison, an off-by-one threshold, or a regex that never matches will report confident verdicts on real runs, and because the subject is stochastic the wrong verdicts look like ordinary model variance rather than a bug in the harness.

Require that any grading or scoring function used by a live-model probe have deterministic unit tests over fixed synthetic inputs — zero API calls — covering at minimum a clear pass, a clear fail, and the boundary the threshold sits on. The tests exercise the grader as a pure function of (output, criteria) so they run in CI at no cost and fail loudly when scoring logic changes.

## Current Behavior

`ll-harness` grading logic decides pass/fail for every stochastic subject it evaluates, but nothing requires the grading logic itself to be tested. A scorer with an inverted comparison, an off-by-one threshold, or a regex that never matches reports confident verdicts on real runs; because the subject is stochastic, a wrong verdict is indistinguishable from ordinary model variance rather than a bug in the harness.

## Expected Behavior

Any grading or scoring function used by a live-model probe has deterministic unit tests over fixed synthetic inputs — zero API calls — covering at minimum a clear pass, a clear fail, and the boundary the threshold sits on. Grading logic is exercised as a pure function of (output, criteria), and a grader with a deliberately inverted comparison is caught by its own unit tests before any live run is dispatched.

## Design

The pattern is proven in a cross-host ruleset project whose eval strategy separates three tiers — deterministic unit tests, a live-model behavior gate, and an agentic benchmark — and whose load-bearing property is that **the graders of the live-model tier are themselves unit-tested** ("RED/GREEN, no API key"): the deterministic tier verifies the live-eval tier's grading logic before that logic is trusted to grade a real model. That is the exact discipline to import: a grader is not allowed to grade until its own logic passes its own deterministic tests.

Distinct from the adjacent verdict work: n-run redundancy (ENH-3415, shipped) governs how many runs a verdict needs before it counts; score-splitting work governs what gets scored; information-isolation work governs flow between builder and validator roles. None of the three tests the grader's own code.

## Acceptance

A grader with a deliberately inverted comparison is caught by its unit tests before any live run is dispatched.

## Program Design

### Types

- `EvaluationResult`: `verdict: str`, `details: dict[str, Any]` (`scripts/little_loops/fsm/evaluators.py:56`)
- `HarnessEvalOutcome`: `passed: bool`, `verdict: str | None`, `eval_result: EvaluationResult | None` (`scripts/little_loops/cli/harness.py:863`)

### Signatures

- `_grade(runner_label, result: RunnerResult, args, *, expected_grade=None, side_effects=None) -> tuple[int, HarnessEvalOutcome]` (`scripts/little_loops/cli/harness.py:1224`)
- `evaluate_llm_structured(output, prompt, model, max_output_chars=None) -> EvaluationResult` (`scripts/little_loops/fsm/evaluators.py:1067`)
- Sibling graders sharing the same `(output, ...) -> EvaluationResult` shape: `evaluate_exit_code`, `evaluate_output_numeric`, `evaluate_output_json`, `evaluate_output_contains`, `evaluate_classify`, `evaluate_harbor_scorer`, `evaluate_mcp_result`, `evaluate_blind_comparator`, `evaluate_contract` (all `scripts/little_loops/fsm/evaluators.py`) — none currently have deterministic unit tests over fixed synthetic inputs.

### Call Path

`_grade()` (`harness.py:1224`) -> `evaluate_llm_structured()` / other `evaluate_*` graders (`fsm/evaluators.py`) -> new deterministic unit-test suite exercising each `evaluate_*` function directly against fixed synthetic `(output, criteria)` fixtures, independent of `_grade()` and any live subject.

## Impact

- **Priority**: P3 — grading bugs currently masquerade as ordinary model variance, which erodes trust in every verdict `ll-harness` produces; no live incident has yet been traced to this gap.
- **Effort**: Medium — requires enumerating existing graders, writing synthetic fixture cases per grader (clear pass, clear fail, threshold boundary), and wiring a check that blocks live dispatch when a grader's tests are absent or failing.
- **Risk**: Low — additive testing requirement; does not change grading behavior itself.
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: deterministic unit tests for grading/scoring functions used by live-model probes, covering pass/fail/boundary cases; a check that these tests exist and pass before a grader is used against a live run.
- **Out of scope**: n-run redundancy for verdict counting (ENH-3415, shipped); score-splitting (what gets scored); information-isolation between builder/validator roles — per this issue's Design section, none of these test the grader's own code.

## Status

**Open** | Created: 2026-09-13 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-09-14T20:15:11 - `94434fad-8258-433c-9701-ead707bb03a6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-13T21:28:47 - `23df08cc-836b-4f77-a1e2-bfb5aedb0f55.jsonl`
