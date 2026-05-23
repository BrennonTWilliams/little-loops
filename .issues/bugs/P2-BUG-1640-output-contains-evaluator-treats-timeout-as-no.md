---
id: BUG-1640
type: BUG
priority: P2
status: done
captured_at: 2026-05-23 12:00:00+00:00
completed_at: 2026-05-23T21:32:06Z
discovered_date: 2026-05-23
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1640: `output_contains` evaluator silently treats action timeouts as "no" verdict

## Summary

When a `prompt`/`mcp`/`shell` action is killed at its timeout (exit_code=124, partial stdout), the generic `evaluate()` dispatcher delegates to type-specific evaluators that only inspect the output string. `evaluate_output_contains` (and its peers `output_numeric`, `output_json`, `convergence`, `diff_stall`) cannot find the success pattern in truncated output and return `verdict="no"`, routing through `on_no` — the loop's `on_error:` branch is never reached. `evaluate_mcp_result` explicitly checks `if exit_code == 124` and returns `verdict="error"`, so the FSM has inconsistent timeout semantics across evaluator types.

## Motivation

- A timeout is operationally different from a deliberate NO verdict: timeouts should retry/fall-back via `on_error`, not route through `on_no` as if the action completed and returned a negative result.
- Observed in production: a 24-iteration trace (`harness-exploratory-user-eval`) where every `check_semantic_vision` invocation hit `(12m 0s) timed out` and was routed via `✗ no -> check_semantic_retry_count` instead of the YAML-defined `on_error: check_semantic` LM Studio fallback.
- Burns wall-clock and API budget re-running `execute` against a deterministic gate failure that the author intended to recover from.

## Root Cause

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Anchor**: `evaluate_output_contains` (around line 274), generic dispatcher `evaluate(...)` (around line 743)
- **Contrast**: `evaluate_mcp_result` (around line 501) does check `exit_code == 124` and returns `verdict="error"`.

The runner contract is fine: `runners.py` (around lines 111, 151) returns `exit_code=124` on timeout with partial stdout. The break is that the generic `evaluate(...)` dispatcher does not short-circuit on that exit code before delegating.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correction — `evaluate_mcp_result` returns `verdict="timeout"`, not `verdict="error"`** (`scripts/little_loops/fsm/evaluators.py:473-530`):

```python
if exit_code == 127:
    return EvaluationResult(
        verdict="not_found",
        details={"exit_code": exit_code, "error": "Server or tool not found in .mcp.json"},
    )
if exit_code == 124:
    return EvaluationResult(
        verdict="timeout",
        details={"exit_code": exit_code, "error": "MCP tool call timed out"},
    )
```

This materially changes the bug analysis: `"timeout"` is **not** one of the shorthand-routed verdicts (`yes`/`no`/`error`/`partial`/`blocked`) handled by `_route()` in `executor.py:1069-1118`. An MCP timeout today only routes if the loop YAML defines `extra_routes: {timeout: ...}` or a `route.routes.timeout` entry — otherwise `_route()` returns `None` and the loop dead-ends. The "MCP works, output_contains doesn't" claim is partially true (MCP's verdict is *different*) but neither evaluator routes through plain `on_error:` on its own.

**Correction — dataclass is `EvaluationResult`, not `EvalResult`**, with no `reason` field (`scripts/little_loops/fsm/evaluators.py` `EvaluationResult`):

```python
@dataclass
class EvaluationResult:
    verdict: str
    details: dict[str, Any]
```

Error messages live under `details["error"]`; raw exit code lives under `details["exit_code"]`. The Proposed Solution code snippet must be rewritten to use this shape.

**Two evaluator paths in `_evaluate()` (`scripts/little_loops/fsm/executor.py:975-1067`)**:
- **Path A (no explicit `evaluate` config)** — routes by `action_mode`: `mcp_tool` → `evaluate_mcp_result`, `shell` → `evaluate_exit_code` (which already maps 124 → `"error"` because 124 ≥ 2), `prompt` → `evaluate_llm_structured`.
- **Path B (explicit `evaluate` config)** — calls `evaluate(config, output, exit_code, ctx)`. **The bug only affects Path B for non-`mcp_result` evaluator types.** `output_contains`, `output_numeric`, `output_json`, `convergence`, and `llm_structured` all receive the raw `exit_code=124` and ignore it.

**Runner asymmetry on stdout**: the prompt/slash-command timeout path returns `output=""` (`runners.py:114`), but shell and MCP subprocess paths return whatever partial stdout was accumulated (`runners.py:157`, `executor.py:_run_subprocess` ~line 962). All three set `exit_code=124`, so the fix is correct to key off `exit_code` (not `output`).

## Steps to Reproduce

1. Define an FSM YAML with an action using `evaluate: output_contains` and an explicit `on_error:` target distinct from `on_no:` (e.g., `harness-exploratory-user-eval.yaml`).
2. Configure an `action_type: prompt` (or `mcp`/`shell`) whose execution will exceed its `timeout:`.
3. Run the loop via `ll-loop run <name>` so the action hits the timeout (runner returns `exit_code=124`, truncated stdout).
4. Observe: the FSM routes through `on_no` (the success-pattern is absent in the truncated output) rather than the `on_error:` branch the author defined.

## Current Behavior

1. Action runs, hits timeout, runner returns `exit_code=124` with truncated stdout.
2. `_evaluate` in `executor.py` (around lines 975–1054) calls `evaluate(...)`.
3. For `output_contains`/`output_numeric`/`output_json`/`convergence`/`diff_stall`, the dispatcher hands the output string to the type-specific evaluator with no exit-code inspection.
4. Pattern is absent in truncated output → verdict `no` → `on_no` fires.
5. `on_error:` target defined by the loop author is unreachable for action-level timeouts.

## Expected Behavior

Action-level timeout (`exit_code == 124`) routes via `on_error:` consistently across all evaluator types, matching the behavior of `evaluate_mcp_result`.

## Proposed Solution

In `scripts/little_loops/fsm/evaluators.py`, have the generic `evaluate(...)` dispatcher short-circuit:

```python
def evaluate(config, output, exit_code, ...):
    if exit_code == 124:
        return EvalResult(verdict="error", reason="action timed out (exit_code=124)")
    # ...existing dispatch
```

Document in `SCHEMA.md` that `on_error` is the canonical branch for action-level timeouts.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The original snippet above references a non-existent `EvalResult` dataclass and `reason=` field. The real type is `EvaluationResult(verdict: str, details: dict[str, Any])`. Once corrected, three real implementation options emerge — the choice depends on whether we accept asymmetry with `evaluate_mcp_result` (which returns `verdict="timeout"`, not `"error"`) and whether we want timeouts to route through existing `on_error:` shorthand or a new `on_timeout:` shorthand.

### Option A — Short-circuit with `verdict="error"` (route via existing `on_error:`)

> **Selected:** Option A — 5-line dispatcher guard unblocks all 166 existing `on_error:` branches immediately, with no schema or routing changes required.

```python
# scripts/little_loops/fsm/evaluators.py, top of evaluate(...) ~line 743
def evaluate(config, output, exit_code, context):
    if exit_code == 124:
        return EvaluationResult(
            verdict="error",
            details={"exit_code": exit_code, "error": "action timed out"},
        )
    # ...existing dispatch
```

- **Pro**: Loop authors' existing `on_error:` branches start firing immediately (the bug's stated user-visible intent).
- **Pro**: No FSM schema change; no new shorthand to document.
- **Con**: Creates asymmetry with `evaluate_mcp_result`, which returns `"timeout"`. Either (a) update `evaluate_mcp_result` to also return `"error"` (breaking change for any loop using `route.routes.timeout` against MCP), or (b) accept that the new short-circuit collapses 124 to `"error"` for non-MCP evaluators while MCP keeps `"timeout"`.
- **Con**: Hides timeout signal from any loop YAML that would want to handle timeouts differently from generic errors.

### Option B — Short-circuit with `verdict="timeout"` (match `evaluate_mcp_result`)

```python
def evaluate(config, output, exit_code, context):
    if exit_code == 124:
        return EvaluationResult(
            verdict="timeout",
            details={"exit_code": exit_code, "error": "action timed out"},
        )
    # ...existing dispatch
```

- **Pro**: Consistent with `evaluate_mcp_result`. Loop authors get a distinct `"timeout"` signal they can route explicitly.
- **Con**: **Does not fix the bug as stated** — `"timeout"` is not a shorthand verdict, so `on_error:` branches still won't fire. Loop authors must define `extra_routes: {timeout: ...}` or use a full `route:` table. `harness-exploratory-user-eval.yaml` and other loops with `on_error:` would still bypass that branch.
- **Compromise**: Combine with documenting that loop authors must add an explicit `timeout` route — partial fix, but more explicit.

### Option C — Add `on_timeout:` shorthand + short-circuit with `verdict="timeout"`

Combine Option B's dispatcher short-circuit with a new `on_timeout:` field in `StateConfig`, added to the verdict→transition mapping in `_route()` (`executor.py:1069-1118`). Falls back to `on_error:` when `on_timeout:` is not set, so existing loops automatically get the bug fix.

```python
# In _route() shorthand resolution
if verdict == "timeout":
    return state.on_timeout or state.on_error  # graceful fallback
```

- **Pro**: Fixes the bug for existing loops (fallback to `on_error:`) AND gives authors a dedicated timeout branch.
- **Pro**: Brings `evaluate_mcp_result`'s existing `"timeout"` verdict into the shorthand routing system, fixing a latent gap.
- **Con**: Largest scope change — touches `StateConfig`, `_route()`, schema validation, and docs.
- **Con**: New shorthand field needs schema/docs/validation updates.

### Recommendation

Option C — it is the only option that fixes the stated bug *and* unifies the timeout signal across evaluator types *and* gives loop authors a dedicated branch. The `on_timeout → on_error` fallback makes the change backward-compatible for loops that already use `on_error:` to mean "anything went wrong."

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-23.

**Selected**: Option A — Short-circuit with `verdict="error"` (route via existing `on_error:`)

**Reasoning**: Evidence from `evaluate_exit_code` (which already maps exit 124 → `"error"` via its `≥2` branch) and from `evaluate_diff_stall`/`evaluate_llm_structured` (which both use `verdict="error"` for internal timeout-like conditions) shows that `"error"` is the established convention for non-MCP action failures in this codebase. All 166 production `on_error:` occurrences across 44 loop YAMLs immediately route correctly without any YAML or schema changes. Option C scored second (10/12) and is architecturally superior, but its 8-file scope exceeds what is needed to fix the stated bug efficiently.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 2/3 | 3/3 | 3/3 | 3/3 | 11/12 |
| Option B | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |
| Option C | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: `evaluate_exit_code` (`evaluators.py:114`) already maps exit 124 → `"error"` via `else` branch; `evaluate_diff_stall` (`evaluators.py:411`) and `evaluate_llm_structured` (`evaluators.py:623`) both use `verdict="error"` for timeout-like conditions; reuse score 3/3.
- Option B: `"timeout"` absent from `_route()` shorthand table (`executor.py:1103-1116`); zero production loops have `extra_routes: {timeout: ...}`; bug is not fixed as stated; reuse score 1/3.
- Option C: Every touchpoint has 2–5 prior instances (`on_partial`, `on_blocked`, `on_throttle_hard`); `on_throttle_hard or on_error` fallback at `executor.py:673` is the direct model; but 8-file coordinated change is larger scope than the bug fix requires; reuse score 3/3.

## Implementation Steps

1. Add early `exit_code == 124` check in `evaluate(...)` dispatcher in `evaluators.py`.
2. Update the schema/docs note about `on_error` semantics for timeouts.
3. Audit any evaluators that currently special-case 124 (e.g., `evaluate_mcp_result`) and remove duplicate checks now handled upstream — or leave them as defense-in-depth.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete steps; final shape depends on the option selected in Proposed Solution:_

**Path A/B (verdict="error" or "timeout" without new shorthand)**:

1. Add `exit_code == 124` short-circuit at the top of `evaluate()` in `scripts/little_loops/fsm/evaluators.py:743` (before the `config.type` if/elif chain). Use `EvaluationResult(verdict=..., details={"exit_code": exit_code, "error": "action timed out"})`. Match the existing `evaluate_mcp_result` reason-string convention.
2. Decide on `evaluate_mcp_result` (`evaluators.py:473-530`): either (a) keep the inner `exit_code == 124` guard as defense-in-depth, or (b) remove it and let the dispatcher handle 124 uniformly. Recommend (a) — the function is also callable directly by Path A in `executor.py:_evaluate()`.
3. Add unit tests in `scripts/tests/test_fsm_evaluators.py` under `TestEvaluateDispatcher` — one parametrized test sweeping `exit_code=124` across `EvaluateConfig.type` values: `exit_code`, `output_contains`, `output_numeric`, `output_json`, `convergence`, `diff_stall`, `llm_structured`. Assert the new uniform verdict for each.
4. Update `scripts/tests/test_fsm_executor.py:TestTimeoutHandling.test_action_timeout_exit_code_124_routes_to_error` (line ~1947) — currently passes because the test uses `EvaluateConfig(type="exit_code")`, which already returns `"error"` for 124. Add a sibling test using `EvaluateConfig(type="output_contains")` that today asserts the bug (`final_state == "fail"`) and after fix asserts `final_state == "error"`.
5. Update docs: `docs/reference/loops.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/generalized-fsm-loop.md` — describe timeout routing semantics.

**Path C (verdict="timeout" + new `on_timeout:` shorthand with `on_error:` fallback)**:

Adds to the above:

6. Add `on_timeout: str | None = None` field to `StateConfig` in `scripts/little_loops/fsm/types.py`.
7. Update `_route()` in `scripts/little_loops/fsm/executor.py:1069-1118` to resolve `"timeout"` verdict via `state.on_timeout or state.on_error`.
8. Update FSM YAML schema validation in `scripts/little_loops/fsm/schema.py` and `scripts/little_loops/fsm/validation.py` to accept `on_timeout:`.
9. Add executor-level test in `TestTimeoutHandling`: assert `on_timeout:` is preferred when set, `on_error:` is used as fallback when not set.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation (most are Option C only):_

10. Update `scripts/little_loops/cli/loop/testing.py:cmd_test()` — add `"timeout"` verdict handling to the local routing preview table so `ll-loop test` correctly shows where a timed-out action would route (Option C only)
11. Update `scripts/little_loops/cli/loop/_helpers.py:print_execution_plan()` — add `on_timeout:` display line (like the existing `on_error:` line) so loop execution plans show the timeout branch (Option C only)
12. Update `scripts/little_loops/cli/loop/layout.py:_collect_edges()` — add `("name", state.on_timeout, "timeout")` edge so `--show-diagrams` renders `on_timeout:` transitions (Option C only)
13. Note for extension authors: `_evaluate()` in `executor.py` calls extension-contributed evaluators directly — they bypass the new dispatcher short-circuit and must handle `exit_code=124` themselves; document in `extension.py` docstring or `docs/reference/API.md`
14. Add `"on_timeout"` to `StateConfig._known_on_keys` in `schema.py` to prevent `on_timeout: target` from silently parsing into `extra_routes` (Option C only, critical correctness coupling)
15. Update `StateConfig.get_referenced_states()`, `to_dict()`, and `from_dict()` in `schema.py` for the new `on_timeout:` field (Option C only)
16. Update `_validate_state_routing():has_shorthand` in `validation.py` to include `state.on_timeout is not None` (Option C only)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — add `exit_code == 124` short-circuit in `evaluate(...)` dispatcher

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `_evaluate` calls `evaluate(...)`; verdict→route mapping must continue to honor `error → on_error`
- `scripts/little_loops/fsm/runners.py` — defines the `exit_code=124` timeout contract this fix relies on

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/testing.py` — `cmd_test()` calls `evaluate(config, output, exit_code, ctx)` directly; its local routing preview table only checks `yes`/`no`/`error`/`extra_routes` — under Option C, `on_timeout:` would render as `(no route for 'timeout')` unless updated [Agent 1 + Agent 2 finding]
- `scripts/little_loops/cli/loop/_helpers.py` — `print_execution_plan()` renders `on_error` transition lines; a new `on_timeout:` field (Option C) needs a display line here; `display_progress()` renders `evaluate` event verdict — `"timeout"` falls into the else-branch (plain orange ✗) rather than the `error` branch [Agent 2 finding]
- `scripts/little_loops/cli/loop/layout.py` — `_collect_edges()` adds `("name", state.on_error, "error")` for diagrams; a new `on_timeout:` field (Option C) needs its own edge entry here or it is invisible in `--show-diagrams` output [Agent 2 finding]
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor` wraps `FSMExecutor` and saves `LoopState`; verify timeout events are logged with the new verdict so loop history reflects the corrected routing [Agent 1 finding]
- `scripts/little_loops/extension.py` — `EvaluatorProviderExtension.provided_evaluators()` registers contributed evaluators; `_evaluate()` in `executor.py` calls them directly, bypassing the new dispatcher short-circuit — extension-contributed evaluators would still see `exit_code=124` without the fix applied [Agent 2 finding]

### Similar Patterns
- `evaluate_mcp_result` (evaluators.py ~line 501) already special-cases `exit_code == 124`; once dispatcher handles it upstream, this can stay as defense-in-depth or be removed for consistency

### Tests
- `scripts/tests/fsm/test_evaluators.py` — add cases for each evaluator type (`output_contains`, `output_numeric`, `output_json`, `convergence`, `diff_stall`) asserting `verdict="error"` on `exit_code=124`
- New integration test under `scripts/tests/fsm/` exercising the FSM `on_error` branch on action timeout

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py` — covers `StateConfig` and `EvaluateConfig` parsing; if Option C adds `on_timeout:` to `StateConfig`, add round-trip serialization test for `from_dict`/`to_dict` and verify `_known_on_keys` includes `"on_timeout"` (prevents it silently falling into `extra_routes`) [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py` — FSM validation tests; if Option C, add test that `on_timeout: some_state` passes `_validate_state_routing()` `has_shorthand` check and that the target appears in `get_referenced_states()` [Agent 3 finding]
- `scripts/tests/test_extension.py` — extension system tests; add a case asserting that a contributed evaluator receiving `exit_code=124` is **not** short-circuited by the dispatcher (since `_evaluate()` calls them directly), so extension authors are aware they must handle 124 themselves [Agent 1 + Agent 2 finding]
- `scripts/tests/test_mcp_result_routing` parametrize row `("", 124, "timeout")` — will **break** if `evaluate_mcp_result`'s inner `exit_code==124` guard is removed; keep as defense-in-depth to avoid this [Agent 3 finding]

### Documentation
- `docs/reference/SCHEMA.md` (or equivalent) — document that `on_error:` is the canonical branch for action-level timeouts across all evaluator types

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — documents `evaluate()`, `EvaluationResult`, and evaluator functions; update signature/behavior description to reflect that `exit_code=124` short-circuits before type dispatch [Agent 1 finding]
- `skills/review-loop/SKILL.md` — QC-2 check ("Missing on_error Routing") only checks for `on_error:` as satisfying error-handling; under Option C, `on_timeout:` without `on_error:` would still trigger the QC-2 warning even though it satisfies timeout recovery — update QC-2 to accept either [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — corrections and additions:_

**Files to Modify (corrections + additions)**:
- `scripts/little_loops/fsm/evaluators.py:743` — `evaluate()` dispatcher (verified; line is correct)
- `scripts/little_loops/fsm/evaluators.py:46` — `EvaluationResult` dataclass is defined here (confirmed by grep); `scripts/little_loops/fsm/types.py` only needed if Option C adds `on_timeout:` to `StateConfig`
- `scripts/little_loops/fsm/executor.py:1069-1118` — `_route()` if Option C adds `on_timeout` shorthand
- `scripts/little_loops/fsm/schema.py` and `scripts/little_loops/fsm/validation.py` — if Option C adds new `on_timeout:` field

**Dependent Files (additions)**:
- `scripts/little_loops/fsm/executor.py:975-1067` — `_evaluate()` has two paths; bug only affects Path B (explicit `evaluate` config). Path A (default-per-action_mode) already handles 124 correctly for `shell`/`mcp_tool`.
- `scripts/little_loops/fsm/handoff_handler.py` — review for any timeout-related logic that might interact
- `scripts/little_loops/cli/loop/run.py` — top-level CLI runner; no changes expected but verify error-path logging

**Tests (corrections)**:
- **Correct test file path**: `scripts/tests/test_fsm_evaluators.py` (NOT `scripts/tests/fsm/test_evaluators.py` — there is no `fsm/` subdirectory under `tests/`)
- `scripts/tests/test_fsm_executor.py:TestTimeoutHandling` (lines 1944-2063) — existing class to extend with new cases
- `scripts/tests/test_fsm_executor.py:TestEvaluators.test_exit_code_evaluator` (line ~1430) — reference pattern for `on_error` assertion
- `scripts/tests/test_ll_loop_errors.py` — `make_test_state()`/`make_test_fsm()` helpers for ad-hoc FSM construction
- No new test files needed — both unit and integration coverage can extend existing files

**Test pattern to follow** (`TestEvaluateDispatcher` style):

```python
@pytest.mark.parametrize(
    "eval_type",
    ["exit_code", "output_contains", "output_numeric", "output_json",
     "convergence", "diff_stall", "llm_structured"],
)
def test_dispatch_exit_code_124_short_circuits(self, eval_type: str) -> None:
    """exit_code=124 short-circuits to error/timeout verdict for all evaluator types."""
    config = EvaluateConfig(type=eval_type, pattern="X")  # pattern only used by some
    ctx = InterpolationContext()
    result = evaluate(config, output="", exit_code=124, context=ctx)
    assert result.verdict == "error"  # or "timeout" per option chosen
    assert "timed out" in result.details["error"].lower()
```

**Documentation (additions/corrections)**:
- `docs/reference/loops.md` — primary FSM/loop docs (no `SCHEMA.md` exists at the suggested path)
- `docs/guides/LOOPS_GUIDE.md` — loop authoring guide; add a "Timeout handling" section
- `docs/generalized-fsm-loop.md` — design doc; cross-reference timeout semantics
- `docs/ARCHITECTURE.md` — evaluators section if it discusses verdict types

**Issue cross-references**:
- `ENH-1168` — wrap `run_action` in `execute` state with `on_error` routing (related)
- `ENH-062` — ll-loop timeout handling tests (related; may have prior test fixtures)
- `BUG-583`, `BUG-946` — earlier timeout/evaluate bugs (look for regressions)
- `ENH-1639` — document prompt/mcp timeout budget guidance (docs companion)

## Verification Plan

1. **Unit test**: in `scripts/tests/fsm/test_evaluators.py`, assert `evaluate(config=ContainsConfig(pattern="YES"), output="", exit_code=124)` returns `verdict="error"`, not `"no"`.
2. **Integration test**: tiny FSM YAML with `action_type: prompt`, 1s timeout, `evaluate: output_contains pattern: YES`, `on_error: error_state` + `on_no: no_state`. Run a prompt that sleeps longer than the timeout; assert runner lands on `error_state`.
3. **End-to-end**: re-run a stripped-down `harness-exploratory-user-eval` with a 60s prompt that intentionally sleeps 65s and confirm the `on_error` branch fires.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete test targets matching the codebase:_

1. **Unit test** (corrected path): in `scripts/tests/test_fsm_evaluators.py`, add to `TestEvaluateDispatcher`:
   ```python
   def test_dispatch_exit_code_124_output_contains_short_circuits(self) -> None:
       config = EvaluateConfig(type="output_contains", pattern="YES")
       ctx = InterpolationContext()
       result = evaluate(config, output="", exit_code=124, context=ctx)
       assert result.verdict == "error"  # was "no" before fix
       assert "timed out" in result.details["error"].lower()
   ```

2. **Integration test**: in `scripts/tests/test_fsm_executor.py:TestTimeoutHandling`, add:
   ```python
   def test_action_timeout_with_output_contains_routes_to_on_error(self) -> None:
       fsm = FSMLoop(
           name="test",
           initial="check",
           states={
               "check": StateConfig(
                   action="slow.sh",
                   evaluate=EvaluateConfig(type="output_contains", pattern="YES"),
                   on_yes="pass", on_no="fail", on_error="error",
               ),
               "pass": StateConfig(terminal=True),
               "fail": StateConfig(terminal=True),
               "error": StateConfig(terminal=True),
           },
       )
       mock_runner = MockActionRunner()
       mock_runner.set_result("slow.sh", output="", exit_code=124, stderr="Action timed out")
       result = FSMExecutor(fsm, action_runner=mock_runner).run()
       assert result.final_state == "error"  # before fix: "fail"
   ```

3. **Regression coverage**: ensure existing `TestMcpResultEvaluator.test_mcp_result_routing` parametrize row `("", 124, "timeout")` still passes (option-dependent — Option A would require changing this assertion to `"error"`).

4. **End-to-end**: keep `harness-exploratory-user-eval` re-run as final validation; capture `ll-loop run --max-iterations 2` event log and grep for `on_error` transition.

5. **Lint/typecheck**: `ruff check scripts/` + `python -m mypy scripts/little_loops/` to catch `EvaluationResult` field-shape errors (the original snippet's `reason=` parameter would have been caught here).

## Impact

- **Priority**: P2 - Loop authors' `on_error:` branches are silently bypassed, but a workaround exists (route `on_no` through error-recovery state) so it does not block correctness, only wastes budget.
- **Effort**: Small - Single short-circuit check in the dispatcher plus tests; no architectural changes.
- **Risk**: Low - Change is additive and only affects the `exit_code == 124` case; existing successful/no/error paths are untouched. Defense-in-depth check in `evaluate_mcp_result` already validates the pattern.
- **Breaking Change**: No - Loops that route `on_error` to a state previously unreachable will start hitting it; loops that intentionally relied on `on_no` for timeouts (unlikely, as `evaluate_mcp_result` already differs) may need review.

## Source

Findings from `~/.claude/plans/we-are-running-little-loops-glistening-kitten.md` (Finding 1), based on full trace of `harness-exploratory-user-eval` 24-iteration run.

## Labels

`bug`, `fsm`, `evaluators`, `timeout`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-23_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 60/100 → MODERATE

### Outcome Risk Factors
- **Open decision between Options A/B/C**: `decision_needed: true` is set; the three options have materially different scopes (Option A: ~2 files; Option C: ~8 files). This open decision should be resolved before implementing — run `/ll:decide-issue BUG-1640` to formally commit to the approach before starting.
- **Option C breadth (8 core files)**: `types.py`, `schema.py`, `validation.py`, `executor.py`, `testing.py`, `_helpers.py`, `layout.py`, and `evaluators.py` all require coordinated updates. Each individual change is mechanical or local, but coordinating across schema, routing, and CLI display layers increases integration risk.

## Resolution

Implemented Option A (per `/ll:decide-issue` 2026-05-23). Added a short-circuit at the top of `evaluate()` in `scripts/little_loops/fsm/evaluators.py:763` that returns `EvaluationResult(verdict="error", details={"exit_code": 124, "error": "action timed out"})` when `exit_code == 124`, exempting `mcp_result` (which keeps its established `"timeout"` verdict for backward compatibility). The dispatcher now ensures `on_error:` is the canonical recovery branch for action-level timeouts across `exit_code`, `output_numeric`, `output_json`, `output_contains`, `convergence`, `diff_stall`, `llm_structured`, and `harbor_scorer` evaluator types.

**Verification**:
- Added `TestEvaluateDispatcher::test_dispatch_exit_code_124_short_circuits_to_error` (parametrized across 8 evaluator types) and two sibling tests covering the `mcp_result` exemption and non-timeout regression paths in `scripts/tests/test_fsm_evaluators.py`.
- Added `TestTimeoutHandling::test_action_timeout_with_output_contains_routes_to_on_error` in `scripts/tests/test_fsm_executor.py` — this is the integration test that fails on the pre-fix codebase (`final_state == "fail"`) and passes after the fix (`final_state == "error"`).
- Full test suite: 7409 passed, 5 skipped. `ruff check` and `mypy` clean on touched files.
- Docs updated: `docs/guides/LOOPS_GUIDE.md` (action-level timeout note in Evaluators section) and `docs/reference/API.md` (`evaluate()` docstring).

## Session Log
- `/ll:manage-issue` - 2026-05-23T21:32:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b7bf8f2-ed0e-41b0-9a32-f47a955af816.jsonl`
- `/ll:ready-issue` - 2026-05-23T21:24:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f2e32ed-99b8-40d1-827b-5060a1f84e94.jsonl`
- `/ll:confidence-check` - 2026-05-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/077320c2-7a5e-4e29-a61a-50f11710e86e.jsonl`
- `/ll:decide-issue` - 2026-05-23T21:20:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/943c1eac-c9ff-40af-a694-b0deef52999a.jsonl`
- `/ll:confidence-check` - 2026-05-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc521ac6-d09c-4bdf-99b3-7717c84f17cb.jsonl`
- `/ll:wire-issue` - 2026-05-23T21:11:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/57f88c46-f1fa-48e9-89ec-3eea2493d247.jsonl`
- `/ll:refine-issue` - 2026-05-23T21:03:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/825ffa4a-0821-4278-a095-ef689f365fce.jsonl`
- `/ll:format-issue` - 2026-05-23T19:20:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8e47d6fd-2e6f-44ec-8c88-b058fa9f9b22.jsonl`

- `/ll:capture-issue` — 2026-05-23T12:00:00Z

---

**Done** | Created: 2026-05-23 | Completed: 2026-05-23 | Priority: P2
