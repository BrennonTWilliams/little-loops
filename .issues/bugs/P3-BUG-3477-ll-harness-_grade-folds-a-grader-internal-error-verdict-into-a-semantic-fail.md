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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

Files, callers, conventions, and tests relevant to threading a `grader_error` outcome through `_grade()`, `harness_events`, and `_rc_from_event()`.

### Files to Modify
- `scripts/little_loops/cli/harness.py` — `_grade()` (`:1224-1329`), `HarnessEvalOutcome` (`:862-872`), `SampleTally`/`.record()` (`:800-828`), `_band_samples()` (`:1351-1367`); five DB-recording call sites at `:2144, 2278, 2398, 2517, 2777`
- `scripts/little_loops/history_reader/harness.py` — `_rc_from_event()` (`:299-312`), which independently mirrors the same banding over persisted rows

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/harness.py:1913` — `_run_sample_loop()` calls `_grade()`
- `scripts/little_loops/cli/harness.py:1965` — `_evaluate_and_report()` calls `_grade()`
- `scripts/little_loops/history_reader/harness.py:372` — `baseline_for()` calls `tally.record(_rc_from_event(event))`
- `scripts/little_loops/session_store/writers.py:1116-1171, 1217-1275` — `harness_events` row writer taking `semantic_verdict`/`semantic_passed` params
- `scripts/little_loops/fsm/evaluators.py:1123-1124` — `evaluate_llm_structured()`'s `BlockingJsonError` catch, one of the origins of `verdict="error"`

### Conventions in Force
- A "third outcome" on this dataclass is added as a plain `bool` field with a `False` default (the `abstained` field's own shape), checked in an `if`/`elif` chain ahead of the `passed = False` fallthrough — not as a new enum type — evidence: `HarnessEvalOutcome.abstained` (`harness.py:867`).
- Precedence between outcome buckets is stated as an explicit "A > B > C" comment wherever a state can satisfy more than one bucket — evidence: `_grade()`'s "fail > abstain > pass" comment (`harness.py:1305-1308`), `_band_samples()`'s docstring precedence list (`:1351-1358`).

### Tests
- `scripts/tests/test_cli_harness.py::TestGradeEvidenceChannels` (`:3682-3768`) — direct `_grade()` calls
- `scripts/tests/test_cli_harness.py::TestBandSamples` (`:958-989`) — direct `_band_samples()` unit tests
- `scripts/tests/test_cli_harness.py::TestSampleTallyRecord` (`:1005`) — `SampleTally.record()` per exit code
- `scripts/tests/test_cli_harness.py::TestAbstentionVerdict` (`:863-911`) — `cmd_cmd()` + `capsys` style
- `scripts/tests/test_fsm_verdicts.py:32-34` — locks `is_abstention_verdict("error") is False`
- `scripts/tests/test_history_reader_harness.py` — covers `history_reader/harness.py` (no direct `_rc_from_event` test found — a gap)

### Documentation
- `docs/guides/EVALUATION_GUIDE.md:442-448` — documents `harness_eval_pass_rate` counting rows with non-NULL `semantic_passed` "on every non-abstained run"; will need a note once a grader-error bucket exists that is also non-abstained but not gradeable

## Program Design

### Types

- `HarnessEvalOutcome` (`scripts/little_loops/cli/harness.py:863`): add `grader_error: bool = False` (or widen `abstained` into a tri-state outcome enum; decide at implementation).
- `EvaluationResult` (`scripts/little_loops/fsm/evaluators.py:56`): unchanged; `verdict="error"` is already the signal.

### Signatures

- `_grade(runner_label, result, args, *, expected_grade=None, side_effects=None) -> tuple[int, HarnessEvalOutcome]` (`harness.py:1224`): unchanged signature; new branch `elif eval_result.verdict == "error": grader_error = True` placed before the `!= "yes"` fall-through.
- `is_abstention_verdict(verdict: str) -> bool` (`fsm/verdicts.py:25`): unchanged; `"error"` is not an abstention.

### Call Path

`_run_sample_loop()`/`_evaluate_and_report()` (`harness.py:1913`/`:1965`) -> `_grade()` -> `evaluate_llm_structured()` returns `verdict="error"` -> `is_abstention_verdict()` returns False -> new `grader_error` on the outcome -> sample tally and `harness_events` writer report it as a distinct bucket; `history_reader/harness.py:_rc_from_event` (`:299-312`) mirrors the banding and must gain the same bucket.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `SampleTally` already has a structurally distinct `errored: int = 0` field and `_band_samples()` (`harness.py:800-828`, `:1351-1367`) already has an `ERROR` band — but it is populated only by `rc==2` from the top-of-function infra guard (`_grade()`, `harness.py:1246-1247`: `result.timed_out or result.error is not None`), not by a judge-internal error. A grader error never reaches this existing bucket today.
- `ChannelRecord.passed: bool | None = None` (`harness.py:831-859`) is an existing precedent in this same file for a tri-state "carries no verdict of its own" field on a result dataclass, documented in its own docstring as "internal fold state."
- `is_abstention_verdict()` (`fsm/verdicts.py:25-27`) is a shared predicate also consumed by FSM routing (`fsm/executor.py:2371`) and locked by `test_fsm_verdicts.py:32-34`, which asserts `is_abstention_verdict("error") is False`. Any grader-error handling in `_grade()` must be additive alongside this predicate, not a redefinition of it.
- FSM state routing (`fsm/executor.py:3253-3304`) already treats `verdict == "error"` as a distinct destination (`route.error`/`on_error`), separate from `on_no`. `"error"` is already a first-class, separately-routed verdict elsewhere in this codebase (`evaluate_llm_structured()` returns it from dozens of internal failure sites in `fsm/evaluators.py`); `_grade()` is the one place found that folds it into `passed=False`.
- Every DB-recording call site independently repeats the same expression rather than sharing one: `semantic_passed=None if outcome.abstained else outcome.passed` at `harness.py:2144, 2278, 2398, 2517, 2777` (one per runner subcommand: `cmd_skill`, `cmd_cmd`, `cmd_mcp`, `cmd_prompt`, `cmd_dsl`). Any new outcome dimension (e.g. `grader_error`) must be threaded through all five, not just through `_grade()`.
- `_rc_from_event()` (`history_reader/harness.py:299-312`) is a second, independent re-implementation of the pass/fail/abstain/error banding, operating on persisted `HarnessEvent` rows. Its docstring states it "mirrors the run-time banding," kept in sync by hand-written comment cross-reference (e.g. "ENH-3435") rather than a shared function — the new bucket has to be added here too, by the same convention, not by calling shared code.
- Existing test-style precedents in `test_cli_harness.py`: `TestAbstentionVerdict` (`:863-911`) drives `cmd_cmd()` + `capsys` output assertions; `TestBandSamples` (`:958-989`) unit-tests `_band_samples()` directly via explicit `SampleTally(...)` construction; `TestGradeEvidenceChannels` (`:3682`) calls `_grade()` directly with a mocked `evaluate_llm_structured`. No existing test in this file constructs `EvaluationResult(verdict="error", ...)`.
- Related: sibling issues ENH-3463 and ENH-3464 reference this same `_grade()` / `evaluate_llm_structured()` / `is_abstention_verdict()` call chain; parent epic EPIC-3475 ("harden ll-harness verdicts") covers this bucket of work.

## Impact

- **Priority**: P3 - judge infrastructure failures are miscounted as subject failures, skewing n-sample pass rates; no incident traced yet.
- **Effort**: Small - one branch in `_grade()`, a field on `HarnessEvalOutcome`, reporting/tally updates, tests in `test_cli_harness.py::TestGradeEvidenceChannels`.
- **Risk**: Medium - changes grading semantics; `history_reader/harness.py:_rc_from_event` mirrors the banding and must be reconciled.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-14 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-14T21:57:11 - `76fd614d-af9c-461c-9480-143acb792f32.jsonl`
- `/ll:format-issue` - 2026-09-14T21:47:59 - `b8b46581-a38f-4aa7-a1ba-71f0319e7405.jsonl`
