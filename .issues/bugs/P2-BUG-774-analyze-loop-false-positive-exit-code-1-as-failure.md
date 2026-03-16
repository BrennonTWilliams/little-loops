---
discovered_date: 2026-03-16
discovered_by: scan-codebase
source_loop: issue-refinement
source_state: evaluate
---

# BUG-774: analyze-loop falsely flags exit_code=1 as failure in exit_code evaluators

## Summary

The `analyze-loop` skill contains a flawed heuristic: when a state uses `evaluate: type: exit_code`, the skill flags repeated `exit_code=1` outcomes as "action failed Nx", generating a false P2 bug signal. In the `issue-refinement` loop this produced a spurious signal claiming the `evaluate` state "failed 8 times" — when in fact `exit_code=1` is the **intended success path** meaning "work found, proceed to parse_id". The evaluator mapping (`exit_code: 0=yes, 1=no, 2+=error`) is well-defined; `exit_code=1` means "no", not "failure".

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

## Proposed Fix

Update `skills/analyze-loop/SKILL.md`, Signal Rules, "BUG — Action failure (exit_code ≠ 0)" section:

**Current rule**: Trigger when `exit_code != 0` AND `is_prompt == false`, grouped by state — 3 or more occurrences.

**Updated rule**: For states that use `evaluate: type: exit_code`:
- Only flag `exit_code=1` as a failure if the state has **no `on_no` branch** OR `on_no` routes to an error/done/terminal state.
- If `on_no` routes to a continuing pipeline state (non-terminal, non-error), treat repeated `exit_code=1` as **intentional routing** — do not flag as a bug.
- Continue to flag `exit_code >= 2` as failures regardless of routing configuration.

## Files to Modify

- `skills/analyze-loop/SKILL.md` — update "BUG — Action failure (exit_code ≠ 0)" signal rule to account for `evaluate: type: exit_code` states and their `on_no` routing

## Acceptance Criteria

- [ ] `analyze-loop` does not flag `exit_code=1` as a failure when the state has an `on_no` transition to a continuing pipeline state
- [ ] `analyze-loop` still correctly flags `exit_code=1` when the state has no `on_no` branch (unhandled "no" outcome)
- [ ] `analyze-loop` still correctly flags `exit_code >= 2` (true error codes) regardless of routing
- [ ] Re-running `analyze-loop` over `issue-refinement` history does not produce a false positive on the `evaluate` state

## Labels

`bug`, `loops`, `analyze-loop`, `captured`

## Status

**Open** | Created: 2026-03-16 | Priority: P2
