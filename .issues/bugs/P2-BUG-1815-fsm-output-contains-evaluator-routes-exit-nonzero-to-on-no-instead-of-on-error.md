---
id: BUG-1815
captured_at: '2026-05-30T22:06:48Z'
discovered_date: 2026-05-30
discovered_by: capture-issue
status: open
decision_needed: false
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-1815: FSM `output_contains` evaluator routes shell exit-nonzero to `on_no` instead of `on_error`

## Summary

When a `shell` action's command exits with a non-zero status AND its stdout does not contain the `output_contains` pattern, the FSM routes to `on_no` (retry) instead of `on_error` (terminal fail). This defeats the explicit failure-routing intent of loops that declare both `on_no` and `on_error`, causing them to burn iterations retrying a hard-broken command instead of bailing cleanly to a `failed` terminal.

## Current Behavior

`evaluate: type: output_contains` only checks whether the pattern is in the captured output. A non-zero exit code is silently ignored — the action is treated as "ran but didn't match." Routing then picks `on_yes` if matched, `on_no` if not. `on_error` only fires for evaluator-internal exceptions (e.g. malformed pattern), never for shell-action exit code.

Reproduced this session in `pixi-generative-art.yaml`:

```yaml
evaluate:
  action_type: shell
  action: |
    python3 -c "subprocess.run([...], check=True)" && echo "CAPTURED"
  evaluate:
    type: output_contains
    pattern: "CAPTURED"
  on_yes: score
  on_no: generate     # ← evaluate exited 1, FSM went here
  on_error: failed    # ← was supposed to go here
```

The python wrapper crashed (`playwright` flag was nonexistent), exited 1 in 0.3s, never printed "CAPTURED". The FSM log shows:

```
[4/5] evaluate (5m 55s) -> python3 -c "..."
       (0.3s)  exit: 1
       ✗ no
       -> generate
```

So a missing dependency burns the next 4 iterations of LLM-generated retries instead of failing fast.

## Expected Behavior

When the underlying shell action exits non-zero, the evaluator should route to `on_error` regardless of pattern match. Pattern-based decisions (`on_yes`/`on_no`) should only apply when the action ran successfully.

Either:
- The `output_contains` evaluator itself returns `verdict="error"` when exit code != 0, OR
- The FSM dispatcher short-circuits and checks exit code before invoking the pattern evaluator for shell actions.

## Motivation

Loops that declare `on_error: failed` as a terminal bail-out are silently broken — a hard command error (missing binary, broken dependency) burns iterations retrying via `on_no` instead of failing fast. This wastes LLM tokens on doomed retries and masks infrastructure failures as "pattern not matched" noise. At least 3 production loops (`p5js-sketch-generator`, `pixi-generative-art`, `pixi-data-viz`) have `on_error: failed` comments claiming clean bail-out behavior that is currently false.

## Steps to Reproduce

1. Create a loop with a shell action that calls a missing binary, e.g. `nonexistent-cmd && echo "OK"`.
2. Declare `evaluate: type: output_contains, pattern: "OK"`, `on_yes: done`, `on_no: retry`, `on_error: failed`.
3. Run the loop. Observe the FSM transitions to `retry` and burns iterations, never reaching `failed`.

## Root Cause

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Anchor**: `evaluate_output_contains()` at line 274 and the `evaluate()` dispatch at line 743
- **Cause**: Two-layer blindness to exit codes:
  1. `evaluate_output_contains()` (line 274) accepts only `output`, `pattern`, `negate` — its signature has no `exit_code` parameter. It returns only `"yes"` or `"no"`, never `"error"`.
  2. The `evaluate()` dispatch (line 743) receives `exit_code: int` but does not pass it to the `output_contains` branch (line 805). The `exit_code` variable is in scope but discarded.
  
  Meanwhile, `FSMExecutor._evaluate()` at `executor.py:1197` DOES pass `exit_code` to `evaluate()` — the value is available but unused. The existing BUG-1640 timeout guard at `evaluators.py:769` already short-circuits `exit_code == 124` to `"error"` before type dispatch, proving the pattern exists; it just wasn't generalized to all non-zero exits.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The `_route()` method at `executor.py:1215` resolves verdict strings to next states. The `verdict == "error"` branch (line 1256) is unreachable for states using `output_contains` because that evaluator only ever returns `"yes"` or `"no"`.

Other evaluators that have the same blind spot: `output_numeric` (`evaluators.py:120`), `output_json` (`evaluators.py:217`), `convergence` (`evaluators.py:313`). However, these three CAN return `"error"` for parse failures — `output_contains` is unique in NEVER returning `"error"` at all.

Evaluators that DO check exit codes: `evaluate_mcp_result` (`evaluators.py:495`), `evaluate_harbor_scorer` (`evaluators.py:549`), `evaluate_diff_stall` (`evaluators.py:378`), `evaluate_llm_structured` (`evaluators.py:638`).

The `next:` state path at `executor.py:825-837` already routes non-zero exits to `on_error` for unconditional transitions — the bug is specifically in the explicit-evaluator path.

## Affected Loops Today

Every loop using the `shell-action + output_contains + on_error: failed` pattern is silently miswired. The `on_error` route is unreachable because `evaluate_output_contains()` only returns `"yes"` or `"no"`, never `"error"`.

### Loops with `shell + output_contains + on_error: failed` (exit code silently ignored)

- `scripts/little_loops/loops/p5js-sketch-generator.yaml` — `evaluate` state (line 149), `score` state (line 213)
- `scripts/little_loops/loops/pixi-generative-art.yaml` — `evaluate` state (line 190), `score` state (line 267)
- `scripts/little_loops/loops/pixi-data-viz.yaml` — `evaluate` state (line 206), `score` state (line 282)
- `scripts/little_loops/loops/html-website-generator.yaml` — `evaluate` state (line 86), `score` state (line 133)
- `scripts/little_loops/loops/html-anything.yaml` — `evaluate` state (line 152), `score` state (line 201)
- `scripts/little_loops/loops/svg-image-generator.yaml` — `evaluate` state (line 101), `score` state (line 148)
- `scripts/little_loops/loops/svg-textgrad.yaml` — `evaluate` state (line 96), `verify_score` state (line 185)

### Loops with `shell + output_contains` but different `on_error` target

- `scripts/little_loops/loops/general-task.yaml` — `check_done` state (line 110, `on_error: diagnose`), `select_step` state (line 132, `on_error: diagnose`), `verify_step` state (line 175, `on_error: diagnose`)

### Loops with `shell + output_contains` without `on_error` defined

- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — `explore_learned` state (line 79)
- `scripts/little_loops/loops/hitl-compare.yaml` — `evaluate` state (line 213), `score` state (line 269)

### Loops NOT affected (prompt-action evaluators)

- `deep-research.yaml`, `deep-research-arxiv.yaml`, `evaluation-quality.yaml`, `backlog-flow-optimizer.yaml`, `prompt-regression-test.yaml`, `apo-contrastive.yaml`, `rn-plan-apo.yaml` — all use `prompt` actions where exit codes are non-meaningful

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Total loops using `output_contains`: 15 loops. Of those, 9 use shell actions (affected), 6 use prompt actions (not affected). Of the 9 shell-action loops, 7 have `on_error` routing defined that is currently unreachable via `output_contains`.

## Proposed Solution

### Option A: Dispatch-level short-circuit (follow BUG-1640 precedent)

> **Selected:** Option A — dispatch-level short-circuit; follows BUG-1640 precedent, minimal change (2 lines), covers all affected evaluator types

In `evaluate()` at `evaluators.py:769`, extend the existing `exit_code == 124` guard to cover all non-zero exit codes for evaluator types that don't already handle them:

```python
# Generalize BUG-1640: non-zero exit codes short-circuit to "error"
# for evaluator types that don't intrinsically check exit_code.
EXIT_CODE_AWARE_EVALUATORS = {"exit_code", "mcp_result", "harbor_scorer", "diff_stall", "llm_structured"}
if exit_code != 0 and eval_type not in EXIT_CODE_AWARE_EVALUATORS:
    return EvaluationResult(
        verdict="error",
        details={"exit_code": exit_code, "error": f"action exited with code {exit_code}"},
    )
```

**Pros**: Minimal change (2 lines added near line 769), consistent with BUG-1640 fix pattern, covers all evaluator types with the blind spot in one place, no signature changes.  
**Cons**: Changes routing behavior for all shell-action loops using `output_contains`, `output_numeric`, `output_json`, or `convergence` — loops without `on_error` defined would need `on_error` added or their routing updated.

### Option B: Add exit_code parameter to `evaluate_output_contains()`

Modify `evaluate_output_contains()` signature to accept `exit_code`, check it before pattern matching:

```python
def evaluate_output_contains(
    output: str,
    pattern: str,
    negate: bool = False,
    exit_code: int = 0,
) -> EvaluationResult:
    if exit_code != 0:
        return EvaluationResult(verdict="error", details={"exit_code": exit_code})
    # ... existing pattern matching logic
```

**Pros**: Targeted fix only for `output_contains`, no risk to other evaluator types.  
**Cons**: Requires signature changes, updating all callers including tests, and doesn't fix the same blind spot in `output_numeric`/`output_json`/`convergence`.

### Option C: New evaluator type (`exit_code_and_contains`)

Introduce a new evaluator type that checks both exit code and output pattern. Keep `output_contains` unchanged for backward compatibility. Update affected loops to use the new evaluator.

**Pros**: Zero backward-compatibility risk; loops opt in explicitly.  
**Cons**: Adds a new evaluator type to maintain, schema updates, documentation, and requires manually updating all 7+ affected loops. Leaves the footgun in place for future loop authors who pick `output_contains` unaware of the blind spot.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The BUG-1640 fix (`evaluators.py:769-773`) is the direct precedent. It added a short-circuit in the `evaluate()` dispatch function rather than modifying individual evaluator functions. The same approach (Option A) is the least invasive and most consistent with existing code.

The `evaluate()` dispatch function already receives `exit_code: int` (line 746), and `FSMExecutor._evaluate()` already passes it (`executor.py:1197`). The infrastructure is in place; only the guard clause is missing.

Related issue: `.issues/bugs/P2-BUG-1640-output-contains-evaluator-treats-timeout-as-no.md` — the previously fixed sibling bug where timeout (exit 124) was also misrouted to `on_no`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-30.

**Selected**: Option A — Dispatch-level short-circuit

**Reasoning**: Option A follows the BUG-1640 precedent exactly — the same file, same function, and same short-circuit pattern that already handles `exit_code == 124` (timeout). It requires only 2 lines of code with no signature changes, covers all four evaluator types with the exit-code blind spot (`output_contains`, `output_numeric`, `output_json`, `convergence`), and the infrastructure already passes `exit_code` to `evaluate()`. Options B and C both leave the footgun in place for future usage or require significantly more maintenance burden.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A: Dispatch short-circuit | 3/3 | 3/3 | 2/3 | 2/3 | **10/12** |
| B: Add exit_code param | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |
| C: New evaluator type | 0/3 | 0/3 | 2/3 | 1/3 | 3/12 |

**Key evidence**:
- **Option A**: Directly extends the BUG-1640 `exit_code == 124` guard at `evaluators.py:769` to cover all non-zero exits for evaluator types that don't intrinsically check `exit_code`. Precedent is in place, `exit_code` is already wired through the call chain.
- **Option B**: Departs from the dispatch-level pattern established by BUG-1640; requires signature changes and updating 3+ direct-caller test files (`test_deep_research.py`, `test_deep_research_arxiv.py`, `test_rn_plan.py`); doesn't fix the same blind spot in `output_numeric`, `output_json`, or `convergence`.
- **Option C**: Adds a new evaluator type, schema, docs, and requires migrating all 7+ affected loops; highest maintenance burden and permanently leaves the footgun for future loop authors who pick `output_contains` unaware of the blind spot.

## Implementation Steps

1. **Add exit-code guard in `evaluate()` dispatch** at `scripts/little_loops/fsm/evaluators.py:769` — extend the BUG-1640 `exit_code == 124` check to cover all non-zero exit codes for evaluator types that don't intrinsically handle exit codes (`output_contains`, `output_numeric`, `output_json`, `convergence`)
2. **Add unit test** in `scripts/tests/test_fsm_evaluators.py:TestEvaluateDispatcher` — model after `test_dispatch_exit_code_124_short_circuits_to_error` (line 562) but test exit codes 1 and 127 with `output_contains`
3. **Add integration test** in `scripts/tests/test_fsm_executor.py` — model after `test_action_timeout_with_output_contains_routes_to_on_error` (line 2030) but test a generic non-zero exit code (e.g., 1)
4. **Update existing test** at `scripts/tests/test_fsm_evaluators.py:581` — `test_dispatch_exit_code_124_does_not_affect_success_cases` currently asserts exit 1 + `output_contains` routes to `no` (the buggy behavior); update to assert routes to `error`
5. **Audit all shell-action loops** that use `output_contains` without `on_error` defined (`ready-to-implement-gate.yaml`, `hitl-compare.yaml`) — ensure they won't break with the new routing behavior
6. **Run affected loops** in simulate mode to confirm `on_error: failed` fires correctly on hard errors (verify `p5js-sketch-generator`, `pixi-generative-art`, `pixi-data-viz`, `html-website-generator`, `html-anything`, `svg-image-generator`, `svg-textgrad`)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Update breaking test** at `scripts/tests/test_fsm_evaluators.py:581-590` — `test_dispatch_exit_code_124_does_not_affect_success_cases` line 590 asserts `verdict == "no"` for `exit_code=1` + `output_contains`; change to `assert result_no.verdict == "error"` and update docstring/comment to reflect generalized non-zero exit short-circuit [Agent 3]
8. **Verify contributed evaluator path** at `scripts/little_loops/fsm/executor.py:1184-1190` — contributed evaluators from `EvaluatorProviderExtension` are called directly, bypassing the `evaluate()` dispatch guard; the exit-code blind spot PERSISTS for these. Document this as a known limitation or add a separate guard in `_evaluate()` before the contributed-evaluator branch [Agent 2]
9. **Verify direct evaluator callers** at `scripts/tests/test_deep_research.py:160-168`, `scripts/tests/test_deep_research_arxiv.py:209-217`, `scripts/tests/test_rn_plan.py:228-231` — these call `evaluate_output_contains()` directly (bypassing `evaluate()` dispatch), so they are unaffected by the fix; confirm no other direct callers exist that might need updating [Agent 3]
10. **Check CLI test-state output** at `scripts/little_loops/cli/loop/testing.py:118,149-153` — `cmd_test()` calls `evaluate()` directly and resolves routing; verify the changed verdict does not break test-state display or exit code mapping in `_helpers.py:712` [Agent 1]
11. **Update docs** — `docs/reference/EVENT-SCHEMA.md` (verdict field now shows `"error"` for more cases), `skills/review-loop/reference.md:70-80` (QC-2 warning is vindicated), `skills/review-loop/SKILL.md:142` (QC-2 check becomes more actionable), and add `CHANGELOG.md` entry for BUG-1815 [Agent 2]
12. **Export new constants** — if `EXIT_CODE_AWARE_EVALUATORS` or similar constants are added to `evaluators.py`, export them from `scripts/little_loops/fsm/__init__.py:89` [Agent 1]

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — add exit-code check to `output_contains` evaluator

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:1197` — `FSMExecutor._evaluate()` passes `exit_code` to `evaluate()` dispatch
- `scripts/little_loops/fsm/executor.py:1121` — `FSMExecutor._evaluate()` method that orchestrates evaluation
- `scripts/little_loops/fsm/executor.py:1215` — `FSMExecutor._route()` maps verdict strings to next states
- `scripts/little_loops/fsm/runners.py:165` — `DefaultActionRunner.run()` constructs `ActionResult` with captured `exit_code`
- `scripts/little_loops/fsm/types.py:57` — `ActionResult` dataclass carries `exit_code: int`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py:89,221` — re-exports `evaluate()` dispatch and all evaluator functions as public API; if new constants (e.g. `EXIT_CODE_AWARE_EVALUATORS`) are added, they must be exported here [Agent 1]
- `scripts/little_loops/cli/loop/testing.py:118` — `cmd_test()` calls `evaluate()` dispatch directly, then resolves routing at lines 149-153; will produce different verdicts for non-zero exits on affected evaluator types [Agent 1]
- `scripts/little_loops/cli/loop/_helpers.py:712` — `show_state()` renders evaluate event verdicts in CLI output; changed verdict strings may affect display [Agent 1]
- `scripts/little_loops/extension.py:238` — `EvaluatorProviderExtension` contributed evaluators are called directly at `executor.py:1184-1190`, bypassing the `evaluate()` dispatch guard; exit-code blind spot PERSISTS for contributed evaluators [Agent 2]

### Similar Patterns
- **BUG-1640 precedent**: `evaluators.py:769-773` — exit_code=124 (timeout) already short-circuits to `verdict="error"` before type dispatch for all evaluator types except `mcp_result`. This is the closest existing fix pattern.
- **Evaluators that DO check exit codes**: `evaluate_mcp_result` (`evaluators.py:495-504`), `evaluate_harbor_scorer` (`evaluators.py:549`), `evaluate_diff_stall` (`evaluators.py:378-470`), `evaluate_llm_structured` (`evaluators.py:638-645`)
- **Evaluators that ignore exit codes** (same blind spot as `output_contains`): `output_numeric` (`evaluators.py:120`), `output_json` (`evaluators.py:217`), `convergence` (`evaluators.py:313`) — all three also lack exit-code awareness in the dispatch path, though they can return `"error"` for parse failures
- **Existing test patterns for BUG-1640 regression**: `test_fsm_evaluators.py:562` (`test_dispatch_exit_code_124_short_circuits_to_error`), `test_fsm_executor.py:2030` (`test_action_timeout_with_output_contains_routes_to_on_error`)
- **`next:` state exit-code guard**: `executor.py:825-837` — for unconditional transitions, non-zero exit already routes to `on_error`; the bug is only in the evaluator path
- **BUG-1640 issue**: `.issues/bugs/P2-BUG-1640-output-contains-evaluator-treats-timeout-as-no.md` — the previously fixed sibling bug

### Tests
- `scripts/tests/test_fsm_evaluators.py:289` — `TestOutputContainsEvaluator` class: unit tests for `evaluate_output_contains()` (lines 291-342); needs new test case for exit_code parameter behavior
- `scripts/tests/test_fsm_evaluators.py:456` — `TestEvaluateDispatcher.test_dispatch_output_contains()`: dispatcher-level test for `output_contains` routing
- `scripts/tests/test_fsm_evaluators.py:562` — `test_dispatch_exit_code_124_short_circuits_to_error()`: BUG-1640 regression test (model new test after this)
- `scripts/tests/test_fsm_evaluators.py:581` — `test_dispatch_exit_code_124_does_not_affect_success_cases()`: **BREAKING** — currently asserts exit 1 with `output_contains` routes `no` (the buggy behavior); line 590 `assert result_no.verdict == "no"` will fail after fix, must change to `assert result_no.verdict == "error"` and update docstring
- `scripts/tests/test_fsm_executor.py:1500` — `test_output_contains_evaluator()`: integration test for `output_contains` routing; does NOT currently test `on_error` path
- `scripts/tests/test_fsm_executor.py:2030` — `test_action_timeout_with_output_contains_routes_to_on_error()`: BUG-1640 integration test (model new test after this)
- `scripts/tests/test_builtin_loops.py:132` — validates builtin loops avoid bare "PASS" as `output_contains` pattern; loops using `on_error: failed` also tested here

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_evaluators.py:581-590` — **CONFIRMED BREAKING**: `test_dispatch_exit_code_124_does_not_affect_success_cases` line 590 asserts `verdict == "no"` for `exit_code=1` + `output_contains`; after fix, verdict will be `"error"`. This is the ONLY test in the suite that encodes the buggy behavior [Agent 3]
- `scripts/tests/test_deep_research.py:11,160-168` — imports and calls `evaluate_output_contains()` directly (bypasses `evaluate()` dispatch); unaffected by fix but confirms the function is consumed outside the evaluator test suite [Agent 3]
- `scripts/tests/test_deep_research_arxiv.py:11,209-217` — same pattern as test_deep_research.py; direct caller, unaffected [Agent 3]
- `scripts/tests/test_rn_plan.py:220,228-231` — same pattern; direct caller, unaffected [Agent 3]
- `scripts/tests/test_ll_loop_execution.py:1015` — `TestEvaluateSource` class tests `output_contains` with `source=` and `exit_code=0`; uses default evaluator, unaffected [Agent 1]
- `scripts/tests/test_outer_loop_eval.py:89-109` — validates `on_error` routing in outer-loop eval fixtures; confirms loops are already configured with `on_error: failed` [Agent 1]

### Documentation
- `docs/generalized-fsm-loop.md:620` — FSM design docs, section on `output_contains` evaluator
- `docs/guides/LOOPS_GUIDE.md:1429` — loop authoring guide, `output_contains` documentation
- `docs/reference/API.md:4319` — Python API reference, `evaluate_output_contains` function docs
- All three docs may need updating to reflect that non-zero exit codes route to `on_error`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md` — documents `evaluate` event schema with `verdict` field; after fix, more events will show `verdict: "error"` where they previously showed `verdict: "no"` [Agent 2]
- `skills/review-loop/reference.md:70-80` — QC-2 detailed guidance already warns about missing `on_error` for `output_contains` states; the fix vindicates this warning and makes QC-2 more actionable [Agent 2]
- `skills/review-loop/SKILL.md:142` — QC-2 "Missing `on_error` Routing" check becomes more important since `on_error` is now reachable for affected evaluator types [Agent 2]
- `CHANGELOG.md` — needs new entry documenting the behavioral change under BUG-1815 [Agent 2]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json:461,554` — JSON Schema defining `output_contains` as valid evaluator type; no structural change needed but should be checked if new evaluator-related constants are added [Agent 1]

## Impact

- **Priority**: P2 — misrouting causes wasted LLM iterations and masks real errors, but has a workaround (manual intervention); affects 3 known loops
- **Effort**: Small — single check addition in one evaluator function plus a test case
- **Risk**: Medium — changing evaluator routing behavior could affect other loops that rely on the current (buggy) behavior; needs audit of all `output_contains` consumers
- **Breaking Change**: Potentially — loops that currently depend on non-zero exit routing to `on_no` would need `on_error` defined or their routing updated

## Labels

`bug`, `fsm`, `evaluator`, `captured`

## Session Log
- `/ll:decide-issue` - 2026-05-30T23:06:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dbda27d0-eb96-41bf-84ef-12db76d68753.jsonl`
- `/ll:format-issue` - 2026-05-30T22:38:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb689b57-45bf-4714-8ea8-266ad6b30908.jsonl`
- `/ll:capture-issue` - 2026-05-30T22:06:48Z - this session
- `/ll:refine-issue` - 2026-05-30T22:52:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e8a5f881-12a5-4d61-b54a-da5f2e99c84f.jsonl`
- `/ll:confidence-check` - 2026-05-30T23:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c0614b9f-d2aa-497b-beeb-c56b629c3c48.jsonl`

**Open** | Created: 2026-05-30 | Priority: P2
