---
id: BUG-3477
type: BUG
title: ll-harness _grade() folds a grader-internal error verdict into a semantic fail
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-14'
captured_at: '2026-09-14T21:36:04Z'
---

# BUG-3477: ll-harness _grade() folds a grader-internal error verdict into a semantic fail

## Summary

`_grade()` in `scripts/little_loops/cli/harness.py` folds an internal grader error (`EvaluationResult(verdict="error", ...)`) into the same `passed = False` outcome as a legitimate semantic `"no"`. A judge that crashed, timed out, or returned unparseable JSON is reported as the subject failing the criteria.

## Context

Surfaced during `/ll:refine-issue` research for ENH-3463 (deterministic grader tests). Split out because it changes grading behavior, which ENH-3463's Impact section explicitly excludes. See ENH-3463.

## Current Behavior

`_grade()` (`harness.py:~1311`) handles the semantic verdict as:

```python
if is_abstention_verdict(eval_result.verdict):
    abstained = True
elif eval_result.verdict != "yes":
    passed = False
```

`is_abstention_verdict()` (`fsm/verdicts.py:25`) recognizes only `cannot_judge`. So `verdict="error"` — produced for example by the `BlockingJsonError` catch at `fsm/evaluators.py:~1123` — falls through to `passed = False` and is indistinguishable from a semantic `"no"` in `HarnessEvalOutcome.passed`.

## Expected Behavior

A grader-internal error is neither a pass nor a fail of the subject. `_grade()` should report it distinctly (a third outcome alongside pass/abstain, or an explicit `grader_error` flag on `HarnessEvalOutcome`) so n-sample tallies and `harness_events` do not count judge failures as subject failures. Precedence stays fail > abstain > pass; error should not silently become fail.

## Steps to Reproduce

1. In `scripts/tests/test_cli_harness.py::TestGradeEvidenceChannels`, patch `little_loops.cli.harness.evaluate_llm_structured` to return `EvaluationResult(verdict="error", details={"error": "BlockingJsonError"})`.
2. Call `_grade()` with `args.semantic` set and `args.exit_code` unset against a synthetic `RunnerResult` with exit code 0.
3. Observe `HarnessEvalOutcome.passed is False` and `abstained is False` — identical to a semantic `"no"`.

## Program Design

### Types

- `HarnessEvalOutcome` (`scripts/little_loops/cli/harness.py:863`): add `grader_error: bool = False` (or widen `abstained` into a tri-state outcome enum; decide at implementation).
- `EvaluationResult` (`scripts/little_loops/fsm/evaluators.py:56`): unchanged; `verdict="error"` is already the signal.

### Signatures

- `_grade(runner_label, result, args, *, expected_grade=None, side_effects=None) -> tuple[int, HarnessEvalOutcome]` (`harness.py:1224`): unchanged signature; new branch `elif eval_result.verdict == "error": grader_error = True` placed before the `!= "yes"` fall-through.
- `is_abstention_verdict(verdict: str) -> bool` (`fsm/verdicts.py:25`): unchanged; `"error"` is not an abstention.

### Call Path

`_run_sample_loop()`/`_evaluate_and_report()` (`harness.py:1913`/`:1965`) -> `_grade()` -> `evaluate_llm_structured()` returns `verdict="error"` -> `is_abstention_verdict()` returns False -> new `grader_error` on the outcome -> sample tally and `harness_events` writer report it as a distinct bucket; `history_reader/harness.py:_rc_from_event` (`:299-312`) mirrors the banding and must gain the same bucket.

## Impact

- **Priority**: P3 - judge infrastructure failures are miscounted as subject failures, skewing n-sample pass rates; no incident traced yet.
- **Effort**: Small - one branch in `_grade()`, a field on `HarnessEvalOutcome`, reporting/tally updates, tests in `test_cli_harness.py::TestGradeEvidenceChannels`.
- **Risk**: Medium - changes grading semantics; `history_reader/harness.py:_rc_from_event` mirrors the banding and must be reconciled.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-14 | Priority: P3
