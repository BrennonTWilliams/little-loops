---
id: ENH-1636
type: ENH
priority: P4
status: done
captured_at: 2026-05-23 12:00:00+00:00
completed_at: 2026-05-29 01:59:33+00:00
discovered_date: 2026-05-23
discovered_by: capture-issue
parent: EPIC-1663
confidence_score: 96
outcome_confidence: 91
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 25
---

# ENH-1636: `ll-loop validate` lint for zero-retry counter pattern

## Summary

A common loop-authoring footgun: a state that increments a `printf > file` counter and then evaluates `output_numeric` with `operator: lt, target: 1` against itself. After the first increment the counter is `1`, `1 < 1 == false`, so `on_no` fires — i.e. the "retry" budget is 0 by construction. Author almost always intended `target: 2` or `target: 3`. The little-loops static validator does not catch this.

## Motivation

- Observed in `harness-exploratory-user-eval` YAML (lines 787–804 of that loop), where `check_semantic_retry_count` had `target: 1` and never actually allowed a retry.
- This exact pattern is going to show up again in user-written loops — it's a single off-by-one between intent ("up to N retries") and the literal arithmetic.
- A focused lint is cheap and pays for itself the first time a loop author saves debugging time.

## Current Behavior

`ll-loop validate` accepts any `output_numeric` evaluator that parses, regardless of whether the threshold against an obvious-counter pattern yields zero usable iterations.

## Expected Behavior

`ll-loop validate` (or a new `ll-loop lint` subcommand) emits a warning when:

1. A state's action writes to a file via `printf NNN > path` where `NNN` is `${VAR}+1` or similar increment, AND
2. The same state evaluates `output_numeric` reading that file, AND
3. The threshold `target:` value, combined with `operator:`, yields zero successful retries given the counter increments from 0 by 1.

Warning message should suggest the likely intended `target:` value.

## Proposed Solution

Add a `_validate_zero_retry_counter()` function in `scripts/little_loops/fsm/validation.py` following the `_validate_meta_loop_evaluation()` pattern — a private function that takes `FSMLoop`, iterates `fsm.states.values()`, inspects `state.action` + `state.evaluate` for the counter pattern, and returns `list[ValidationError]` with `severity=ValidationSeverity.WARNING`. Wire into `validate_fsm()` via `errors.extend(_validate_zero_retry_counter(fsm))`.

No new dataclass or module is needed — reuse the existing `ValidationError` / `ValidationSeverity` infrastructure (validation.py:33-58). No CLI changes needed either; `cmd_validate()` in `config_cmds.py` already prints warnings returned by `load_and_validate()`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Integration point**: `validate_fsm()` at `validation.py:710` orchestrates all `_validate_*()` calls. Add `errors.extend(_validate_zero_retry_counter(fsm))` alongside the existing `_validate_meta_loop_evaluation()` call (line 849).
- **Pattern to follow**: `_validate_meta_loop_evaluation()` at `validation.py:883-935` — cross-state heuristic that iterates `fsm.states.values()`, inspects evaluator configs, returns `list[ValidationError]`.
- **Counter pattern in the wild**: The canonical `retry_counter` fragment lives at `scripts/little_loops/loops/lib/common.yaml:23-38` — reads counter file (default 0), increments (`N=$((N + 1))`), writes back, echoes. States using this fragment with `target: 1` and `operator: lt` have zero effective retries.
- **Detection heuristic**: The action string must contain a `printf`/`echo` writing to a file AND an increment pattern (`$((... + 1))`, `++`, `+=1`). The evaluator must be `output_numeric` with an operator/target combo where the first post-increment value fails the condition. Specifically:
  - `operator: lt, target: 0` → counter 0→1, `1 < 0 == false` → zero retries
  - `operator: lt, target: 1` → counter 0→1, `1 < 1 == false` → zero retries
  - `operator: le, target: 0` → counter 0→1, `1 <= 0 == false` → zero retries
  - `operator: eq, target: 0` → counter 0→1, `1 == 0 == false` → zero retries (counter never matches)
- **Operator semantics**: `_NUMERIC_OPERATORS` at `evaluators.py:88-95` defines all six operators. `evaluate_output_numeric()` at `evaluators.py:120-156` parses stdout as float and applies the operator lambda.
- **Warning emission**: `ValidationError.__str__()` at `validation.py:54-58` formats as `[WARNING] states.<name>.evaluate: <message>`. Use `path=f"states.{state_name}.evaluate"` for consistency with existing evaluator warnings.
- **No new module needed**: Reuse `ValidationError` with `severity=ValidationSeverity.WARNING`. No `lints/` directory exists — convention is private `_validate_*()` functions within `validation.py`. No CLI changes needed — `cmd_validate()` in `config_cmds.py:11-34` already prints warnings returned by `load_and_validate()`.
- **Test location**: Existing validation tests live in `scripts/tests/test_fsm_validation.py` (programmatic FSM construction). Use `make_state()` helper (line 33) and `validate_fsm()` for unit tests. The `test_fsm_schema.py:1085` `TestEvaluatorValidation` class is the reference for evaluator-specific tests.
- **Evaluator internals**: `evaluate_output_numeric()` at `evaluators.py:120-156` parses stdout as float, looks up operator in `_NUMERIC_OPERATORS` dict (line 88), applies lambda. The operator set is validated statically at `validation.py:97` (`VALID_OPERATORS`).

## Implementation Steps

1. Add `_validate_zero_retry_counter(fsm: FSMLoop) -> list[ValidationError]` in `scripts/little_loops/fsm/validation.py`. The function should:
   - Iterate `fsm.states.items()` to inspect each `(state_name, StateConfig)`
   - Skip states without both `action` and `evaluate` (early continue)
   - Skip states where `evaluate.type != "output_numeric"` or `evaluate.operator`/`evaluate.target` is `None`
   - Regex-match `state.action` for a counter-increment pattern: `printf`/`echo` writing to a file path AND an arithmetic increment (`$((... + 1))`, `++`, `+=1`, `awk ...++`)
   - Compute the zero-retry condition: given counter starts at 0 and increments by 1 before evaluation, check whether `_NUMERIC_OPERATORS[operator](1, target)` is `False` (i.e., the first post-increment value already fails the condition)
   - For each match, yield `ValidationError(message="...", path=f"states.{state_name}.evaluate", severity=ValidationSeverity.WARNING)` with a suggested-fix message (e.g., `"Zero retry budget: operator=lt target=1 means 1 < 1 is already false after one increment. Did you mean target=2?"`)
2. Wire into `validate_fsm()` at `validation.py:849` by adding `errors.extend(_validate_zero_retry_counter(fsm))` alongside the `_validate_meta_loop_evaluation()` call.
3. Add unit tests in `scripts/tests/test_fsm_validation.py` following the existing `TestMetaLoopValidation` class pattern (programmatic FSM construction with `make_state()`):
   - `lt target=1` with counter action → WARNING emitted
   - `lt target=0` with counter action → WARNING emitted
   - `le target=0` with counter action → WARNING emitted
   - `lt target=2` with counter action → no warning (one retry allowed)
   - `lt target=3` with counter action → no warning (two retries allowed)
   - Non-counter action (plain `echo "hello"`) with `lt target=1` → no warning
   - `output_numeric` with counter action but `operator: gt, target: 0` → no warning (valid budget)
4. Run existing test suite to verify no regressions: `python -m pytest scripts/tests/test_fsm_validation.py scripts/tests/test_builtin_loops.py -v`

## Scope Boundaries

In scope:
- Static lint of the specific "counter file + `output_numeric` evaluator" pattern within a single state's action/evaluator pair.
- Suggested-fix message recommending the likely intended `target:` value.

Out of scope:
- General data-flow analysis across multiple states or files.
- Counter patterns expressed in non-`printf`/non-bash actions (e.g. Python helper scripts the loop shells out to).
- Auto-fix / rewriting the YAML in place — warning-only.
- Detecting other off-by-one bugs unrelated to the zero-retry shape.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — add `_validate_zero_retry_counter()` and wire into `validate_fsm()` alongside `_validate_meta_loop_evaluation()`.

### Dependent Files (Callers/Importers)
- None. `cmd_validate()` in `scripts/little_loops/cli/loop/config_cmds.py` already prints warnings returned by `load_and_validate()`. No CLI changes needed.

### Similar Patterns
- `_validate_meta_loop_evaluation()` at `validation.py:883` — cross-state heuristic that iterates `fsm.states.values()`, inspects evaluator configs, returns `list[ValidationError]`. Follow this pattern for the new lint.

### Tests
- `scripts/tests/test_fsm_validation.py` — add test class following `TestMetaLoopValidation` pattern, using `make_state()` helper (line 33). Cover: `lt target=1` (warn), `lt target=0` (warn), `le target=0` (warn), `lt target=2` (no warn), `lt target=3` (no warn), non-counter action with `lt target=1` (no warn), counter action with `gt target=0` (no warn).

### Documentation
- `docs/reference/` lint/validate documentation — add a brief note describing the new warning and its suggested-fix output.

### Configuration
- N/A

## Impact

- **Priority**: P4 — Real footgun observed in the wild, but workaround is trivial once you know the pattern; no production breakage.
- **Effort**: Small — One narrow heuristic plus unit tests; no schema changes required.
- **Risk**: Low — Warning-only output; no behavior change to existing loops, no auto-rewrites.
- **Breaking Change**: No

## Source

Findings from `~/.claude/plans/we-are-running-little-loops-glistening-kitten.md` (Finding 2).

## Labels

`enhancement`, `loops`, `lint`, `validation`, `captured`

## Status

**Open** | Created: 2026-05-23 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-05-29T01:52:36 - `cce34f6e-9852-4b12-8623-89d7007cbbe7.jsonl`
- `/ll:confidence-check` - 2026-05-28T20:44:00 - `013a1bb3-99f0-42ec-9dbf-77c1b3c719e3.jsonl`
- `/ll:refine-issue` - 2026-05-29T01:27:20 - `b0cd0c8c-d567-4316-be67-67df2787e79f.jsonl`
- `/ll:format-issue` - 2026-05-23T19:19:09 - `900e25aa-792d-43a3-87b5-3b2b3c76ada1.jsonl`

- `/ll:capture-issue` — 2026-05-23T12:00:00Z
