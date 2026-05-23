---
id: BUG-1640
type: BUG
priority: P2
status: open
captured_at: 2026-05-23T12:00:00Z
discovered_date: 2026-05-23
discovered_by: capture-issue
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

## Implementation Steps

1. Add early `exit_code == 124` check in `evaluate(...)` dispatcher in `evaluators.py`.
2. Update the schema/docs note about `on_error` semantics for timeouts.
3. Audit any evaluators that currently special-case 124 (e.g., `evaluate_mcp_result`) and remove duplicate checks now handled upstream — or leave them as defense-in-depth.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — add `exit_code == 124` short-circuit in `evaluate(...)` dispatcher

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `_evaluate` calls `evaluate(...)`; verdict→route mapping must continue to honor `error → on_error`
- `scripts/little_loops/fsm/runners.py` — defines the `exit_code=124` timeout contract this fix relies on

### Similar Patterns
- `evaluate_mcp_result` (evaluators.py ~line 501) already special-cases `exit_code == 124`; once dispatcher handles it upstream, this can stay as defense-in-depth or be removed for consistency

### Tests
- `scripts/tests/fsm/test_evaluators.py` — add cases for each evaluator type (`output_contains`, `output_numeric`, `output_json`, `convergence`, `diff_stall`) asserting `verdict="error"` on `exit_code=124`
- New integration test under `scripts/tests/fsm/` exercising the FSM `on_error` branch on action timeout

### Documentation
- `docs/reference/SCHEMA.md` (or equivalent) — document that `on_error:` is the canonical branch for action-level timeouts across all evaluator types

### Configuration
- N/A

## Verification Plan

1. **Unit test**: in `scripts/tests/fsm/test_evaluators.py`, assert `evaluate(config=ContainsConfig(pattern="YES"), output="", exit_code=124)` returns `verdict="error"`, not `"no"`.
2. **Integration test**: tiny FSM YAML with `action_type: prompt`, 1s timeout, `evaluate: output_contains pattern: YES`, `on_error: error_state` + `on_no: no_state`. Run a prompt that sleeps longer than the timeout; assert runner lands on `error_state`.
3. **End-to-end**: re-run a stripped-down `harness-exploratory-user-eval` with a 60s prompt that intentionally sleeps 65s and confirm the `on_error` branch fires.

## Impact

- **Priority**: P2 - Loop authors' `on_error:` branches are silently bypassed, but a workaround exists (route `on_no` through error-recovery state) so it does not block correctness, only wastes budget.
- **Effort**: Small - Single short-circuit check in the dispatcher plus tests; no architectural changes.
- **Risk**: Low - Change is additive and only affects the `exit_code == 124` case; existing successful/no/error paths are untouched. Defense-in-depth check in `evaluate_mcp_result` already validates the pattern.
- **Breaking Change**: No - Loops that route `on_error` to a state previously unreachable will start hitting it; loops that intentionally relied on `on_no` for timeouts (unlikely, as `evaluate_mcp_result` already differs) may need review.

## Source

Findings from `~/.claude/plans/we-are-running-little-loops-glistening-kitten.md` (Finding 1), based on full trace of `harness-exploratory-user-eval` 24-iteration run.

## Labels

`bug`, `fsm`, `evaluators`, `timeout`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-23T19:20:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8e47d6fd-2e6f-44ec-8c88-b058fa9f9b22.jsonl`

- `/ll:capture-issue` — 2026-05-23T12:00:00Z

---

**Open** | Created: 2026-05-23 | Priority: P2
