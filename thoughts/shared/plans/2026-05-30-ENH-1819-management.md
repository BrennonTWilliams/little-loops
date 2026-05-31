# Implementation Plan: ENH-1819 — Multimodal Evaluator Blind Spot Validation

## Issue Summary

Add `_validate_harness_multimodal_evaluator_blind_spot` to `validation.py` that warns when harness-category loops use LLM multimodal evaluation (screenshot reading + text verdict) as the sole gate to a terminal state.

## Confidence Gate

- `confidence_score: 100` >= threshold 85 → PASS
- `decision_needed`: absent → skip decision gate

## Phase 3a: Write Tests (Red)

TDD mode is enabled. Write these test cases in `scripts/tests/test_fsm_validation.py`:

1. **fires on matching pattern** — harness loop with action_type=prompt, screenshot-reading action, output_contains eval, on_yes→terminal
2. **does not fire on non-harness loops** — same pattern but category != harness
3. **does not fire when on_yes goes to non-terminal** — screenshot-reading prompt but on_yes→intermediate state
4. **does not fire when shell-action state intervenes** — non-LLM shell state between prompt and terminal
5. **suppressed by meta_self_eval_ok** — escape hatch works
6. **integration test** — confirm wired into validate_fsm()

## Phase 3b: Implementation

### File: `scripts/little_loops/fsm/validation.py`

1. Add `_MULTIMODAL_EVAL_PATTERNS` (module-level, after `_SHARED_TMP_PATH_RE` at line ~100)
2. Implement `_validate_harness_multimodal_evaluator_blind_spot(fsm)` (after `_validate_zero_retry_counter`, ~line 1031)
3. Wire into `validate_fsm()` at line ~882: `errors.extend(_validate_harness_multimodal_evaluator_blind_spot(fsm))`

## Phase 4: Verify

- Run tests: `python -m pytest scripts/tests/test_fsm_validation.py -v`
- Run lint: `ruff check scripts/`
- Manual: `ll-loop validate svg-image-generator` should emit WARNING

## Phase 5: Complete

- Update issue status to `done`
- Commit changes
