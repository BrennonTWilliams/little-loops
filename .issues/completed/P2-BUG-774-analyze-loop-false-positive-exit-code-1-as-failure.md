---
discovered_date: 2026-03-16
discovered_by: scan-codebase
source_loop: issue-refinement
source_state: evaluate
confidence_score: 100
outcome_confidence: 78
---

# BUG-774: analyze-loop falsely flags exit_code=1 as failure in exit_code evaluators

## Summary

The `analyze-loop` skill contains a flawed heuristic: when a state uses `evaluate: type: exit_code`, the skill flags repeated `exit_code=1` outcomes as "action failed Nx", generating a false P2 bug signal. In the `issue-refinement` loop this produced a spurious signal claiming the `evaluate` state "failed 8 times" — when in fact `exit_code=1` is the **intended success path** meaning "work found, proceed to parse_id". The evaluator mapping (`exit_code: 0=yes, 1=no, 2+=error`) is well-defined; `exit_code=1` means "no", not "failure".

## Current Behavior

When `analyze-loop` processes a loop with states using `evaluate: type: exit_code`, it applies a blanket rule: any `action_complete` event with `exit_code != 0` is treated as a failure. When such events repeat 3+ times for the same state, a P2 bug signal is generated.

In the `issue-refinement` loop, the `evaluate` state uses `exit_code=1` to signal "work found, continue pipeline" — the intended `on_no` routing path. Running `analyze-loop` over this loop's history falsely generates: `"evaluate action failed 8x (exit_code=1) in issue-refinement loop"`.

## Steps to Reproduce

1. Define a loop with a state using `evaluate: type: exit_code` where `on_no` routes to a continuing pipeline state (e.g., `issue-refinement.yaml`, `evaluate` state)
2. Run the loop multiple times so the evaluator state exits with `exit_code=1` (normal "work found" signal) 3+ times
3. Run `/ll:analyze-loop` over the loop's execution history
4. Observe: `analyze-loop` generates a false P2 bug signal — `"[state-name] action failed Nx (exit_code=1)"` — when all occurrences represent normal `on_no` routing

## Root Cause

- **File**: `skills/analyze-loop/SKILL.md` — Signal Rules, "BUG — Action failure (exit_code ≠ 0)" section
- **Cause**: The rule triggers on `action_complete` events where `exit_code != 0`. It does not inspect the state's `evaluate: type` or routing configuration before flagging. When a state uses `evaluate: type: exit_code` and has an `on_no:` transition that continues the pipeline, `exit_code=1` is the normal "work to do" signal, not an error. The heuristic conflates "non-zero exit" with "failure" without accounting for evaluator semantics.

## Evaluator Semantics (from evaluators.py:93-112)

| Exit code | Meaning | Routes to |
|-----------|---------|-----------|
| 0 | yes / done | `on_yes` |
| 1 | no / not done | `on_no` |
| 2+ | error | `on_error` |

In `issue-refinement.yaml`, the `evaluate` state's shell script exits 1 when it finds an issue that needs work and prints `NEEDS_FORMAT <id>` — this is the intended "pipeline should continue" signal, not a failure.

## False Signal Generated

The `analyze-loop` run over `issue-refinement` history produced:

> **[Signal 2] BUG P2 — "evaluate action failed 8x (exit_code=1) in issue-refinement loop"**

This is a false positive. All 8 occurrences represent the loop correctly identifying work to do and routing to `parse_id → route_format → format_issues`.

## Expected Behavior

`analyze-loop` should only flag `exit_code=1` as a failure when the state has no `on_no` branch, or when `on_no` routes to an error or terminal state. An `on_no` that continues the normal pipeline is intentional routing, not a failure.

## Proposed Solution

Update `skills/analyze-loop/SKILL.md`, Signal Rules, "BUG — Action failure (exit_code ≠ 0)" section:

**Current rule**: Trigger when `exit_code != 0` AND `is_prompt == false`, grouped by state — 3 or more occurrences.

**Updated rule**: For states that use `evaluate: type: exit_code`:
- Only flag `exit_code=1` as a failure if the state has **no `on_no` branch** OR `on_no` routes to an error/done/terminal state.
- If `on_no` routes to a continuing pipeline state (non-terminal, non-error), treat repeated `exit_code=1` as **intentional routing** — do not flag as a bug.
- Continue to flag `exit_code >= 2` as failures regardless of routing configuration.

## Integration Map

### Files to Modify
- `skills/analyze-loop/SKILL.md:93-97` — the "BUG — Action failure (exit_code ≠ 0)" signal rule; only the trigger condition at line 94 needs updating

### Related Implementation (Read-Only Context)
- `scripts/little_loops/fsm/evaluators.py:93-112` — `evaluate_exit_code()`: formal exit code semantics (0=yes, 1=no, 2+=error); the source of truth for evaluator semantics the signal rule must respect
- `scripts/little_loops/fsm/executor.py:648-659` — emits `action_complete` event with `exit_code` and `is_prompt` fields; also emits `evaluate` event at line 821-828 with `verdict: "no"` for exit_code=1 (this subsequent event is what the signal rule should consult)

### Loop YAMLs with Non-Terminal `on_no` (all affected by this false positive)
- `loops/issue-refinement.yaml:41-44` — `evaluate` state: `on_no: parse_id` (continuing pipeline) — the specific case reported
- `loops/sprint-build-and-validate.yaml:39-43` — `route_create` state: `on_no: create_sprint` (continuing pipeline)
- `loops/fix-quality-and-tests.yaml:77-81` — `check-tests` state: `on_no: fix-tests` (continuing pipeline)
- `loops/dead-code-cleanup.yaml:74-78` — `verify_tests` state: `on_no: revert_and_scan` (continuing pipeline)
- `loops/docs-sync.yaml:15-28` — `verify_docs` and `check_links` states: `on_no` same as `on_yes` (intentional, result ignored)

### Tests
- `scripts/tests/test_fsm_evaluators.py:47-70` — covers `evaluate_exit_code()` with exit codes 0/1/2/127/255/-1; use as model for test patterns
- No existing tests for analyze-loop signal generation (the skill has no Python implementation — logic lives entirely in `SKILL.md`)

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — may need minor update if it describes analyze-loop signal behavior

## Implementation Steps

1. Update `skills/analyze-loop/SKILL.md:94` — replace the "BUG — Action failure" trigger condition with the conditional logic from the Proposed Solution:
   - For states with `evaluate: type: exit_code` AND `on_no` routing to a non-terminal/non-error state: skip `exit_code=1` (treat as intentional routing)
   - For states with `evaluate: type: exit_code` AND no `on_no` branch, or `on_no` routes to error/done/terminal: still flag `exit_code=1`
   - Always flag `exit_code >= 2` regardless of evaluator type or routing
   - Cross-reference the loop YAML (available via `ll-loop config <loop_name> --json`) to inspect the state's `evaluate.type` and `on_no` target

2. Verify the fix against the `issue-refinement` loop: re-run `/ll:analyze-loop` over `issue-refinement` history and confirm no false P2 signal on the `evaluate` state

3. Verify true positives are preserved: confirm `exit_code >= 2` and `exit_code=1` with no `on_no` branch (e.g., `parse_id` state in `issue-refinement.yaml:50-53`) still generate signals

4. Update `docs/guides/LOOPS_GUIDE.md` if it documents analyze-loop signal behavior

## Acceptance Criteria

- [ ] `analyze-loop` does not flag `exit_code=1` as a failure when the state has an `on_no` transition to a continuing pipeline state
- [ ] `analyze-loop` still correctly flags `exit_code=1` when the state has no `on_no` branch (unhandled "no" outcome)
- [ ] `analyze-loop` still correctly flags `exit_code >= 2` (true error codes) regardless of routing
- [ ] Re-running `analyze-loop` over `issue-refinement` history does not produce a false positive on the `evaluate` state

## Impact

- **Priority**: P2 - False positive bug signals pollute the issue backlog and erode trust in `analyze-loop` output; users must manually investigate each false positive to dismiss it
- **Effort**: Small - Single signal rule update in `SKILL.md` with conditional logic to inspect `on_no` routing
- **Risk**: Low - Only affects the false-positive detection heuristic; true failures (`exit_code >= 2`) and states without `on_no` branches remain correctly flagged
- **Breaking Change**: No

## Labels

`bug`, `loops`, `analyze-loop`, `captured`

## Resolution

**Fixed** in `skills/analyze-loop/SKILL.md`:

1. **Step 2** now also loads the loop config via `ll-loop show <loop_name> --json` to build a state config map (including `evaluate.type` and `on_no` for each state).
2. **BUG — Action failure signal rule** updated: `exit_code=1` is excluded from the failure count when the state has `evaluate.type == "exit_code"` AND `on_no` is defined — treating it as intentional `on_no` routing. `exit_code >= 2` always counts as failure. If state config is unavailable, falls back to conservative (flag all non-zero).

## Status

**Closed** | Created: 2026-03-16 | Resolved: 2026-03-16 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-03-17T00:01:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c108eca6-a84b-4ace-9850-a9485ab9bdfb.jsonl`
- `/ll:ready-issue` - 2026-03-17T00:01:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c108eca6-a84b-4ace-9850-a9485ab9bdfb.jsonl`
- `/ll:confidence-check` - 2026-03-16T18:49:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:refine-issue` - 2026-03-16T18:47:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:verify-issues` - 2026-03-16T18:40:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:format-issue` - 2026-03-16T18:39:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
