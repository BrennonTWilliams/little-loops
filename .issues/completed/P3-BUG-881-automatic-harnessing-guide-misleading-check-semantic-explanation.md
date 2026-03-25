---
id: BUG-881
type: BUG
priority: P3
status: open
discovered_date: 2026-03-24
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 85
testable: false
---

# BUG-881: `AUTOMATIC_HARNESSING_GUIDE` incorrectly describes how `check_semantic` accesses prior output

## Summary

`docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` contains a misleading explanation of how `check_semantic` works:

> **Why `echo` as the action?** The `llm_structured` evaluator judges the *previous* state's output — not the current state's shell output. The `check_semantic` state still requires an `action` field, so a minimal `echo` satisfies the field while doing nothing meaningful. The echo output is ignored; only the `evaluate.prompt` and the captured context from the preceding state matter.

This is incorrect on two counts:

1. **The echo output is NOT ignored** — it is passed as `action_output` to the LLM evaluator (see `executor._evaluate()` + `evaluate_llm_structured()`).
2. **"Captured context from the preceding state"** does not automatically flow into the evaluator. The `source` field would need to be set (e.g. `source: "${prev.output}"`) for prior output to be used as eval input, but the generated YAML does not include this field.

The practical effect is that `check_semantic` does NOT judge the previous state's output — it judges with only the echo string as evidence, which is uninformative.

## Current Behavior

The `AUTOMATIC_HARNESSING_GUIDE.md` "Why `echo` as the action?" blockquote asserts:
- The echo output "is ignored"
- The LLM evaluator judges the "captured context from the preceding state" automatically

In reality (`executor.py:875-881`, `evaluators.py:563`):
- The echo output IS embedded as `<action_output>` in the LLM prompt — it is the primary evidence the evaluator receives
- Prior state output does NOT flow automatically; `source: "${captured.<var>.output}"` must be set explicitly on the `evaluate` block
- `${prev.output}` at `check_semantic` resolves to `check_concrete`'s output (pytest results), not `execute`'s skill output

## Expected Behavior

The guide accurately explains how `check_semantic` evaluation works:
- The echo output is the evidence the LLM receives, embedded in `<action_output>`
- To evaluate a prior state's output, `source: "${captured.<var>.output}"` must be set explicitly (where `<var>` is the `capture` key on the source state)
- `${prev.output}` is not the right pattern for accessing `execute`'s output from `check_semantic`

## Steps to Reproduce

1. Open `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`
2. Locate the "Why `echo` as the action?" blockquote (around line 219–223)
3. Read the claim: "The echo output is ignored; only the `evaluate.prompt` and the captured context from the preceding state matter"
4. Open `scripts/little_loops/fsm/executor.py` and inspect `_evaluate()` at lines 875–881
5. Observe: the `else` branch sets `eval_input = raw_output` — the echo string is what the evaluator receives, not the prior state's output
6. Open `scripts/little_loops/fsm/evaluators.py:563` — confirm the echo string is embedded in `<action_output>` in the LLM prompt

## Root Cause

Documentation written before or without verification against the actual `executor.py` evaluation path.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The echo output flows through this path:

1. `executor.py:662` — `action_result = self._run_action(state.action, ...)` captures echo stdout
2. `executor.py:875-881` — with no `source` field, the `else` branch runs: `eval_input = raw_output` (the echo string)
3. `evaluators.py:563` — `user_prompt = f"{effective_prompt}\n\n<action_output>\n{truncated}\n</action_output>"` — echo string embedded verbatim in the LLM prompt

**`${prev.output}` nuance**: even if `source: "${prev.output}"` were set on `check_semantic`, in the standard harness chain (`execute → check_concrete → check_semantic`), `prev.output` at `check_semantic` holds `check_concrete`'s output (pytest results) — not `execute`'s skill output (`executor.py:666-670` sets `prev_result` after each state completes). To access `execute`'s output, `execute` would need to `capture` its output and `check_semantic` would use `source: "${captured.<var>.output}"` — the pattern used in production loops.

## Proposed Solution

Fix `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:219-223` — replace the inaccurate "Why `echo`?" blockquote with an accurate explanation:

> **Why `echo` as the action?** `check_semantic` receives the echo string as `<action_output>` in the LLM prompt — an empty `echo` provides minimal evidence. To evaluate a prior state's output, set `source: "${captured.<var>.output}"` on the `evaluate` block, where `<var>` is the `capture` key on the source state. Note: `${prev.output}` at `check_semantic` resolves to `check_concrete`'s output (pytest results), not `execute`'s skill output — use the `capture` + `source` pattern instead (see production examples in `loops/issue-staleness-review.yaml:36-47`).

Also update the same incorrect claim in:
- `loops/harness-single-shot.yaml:112-114` — YAML comment: "shell output is ignored"
- `loops/harness-multi-item.yaml:137-139` — YAML comment: same incorrect claim

If BUG-880 is fixed first, additionally update:
- `skills/create-loop/loop-types.md:713-720` and `:775-782` — `check_semantic` templates to include the `source` field

## Integration Map

### Files to Modify

**Primary (documentation):**
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:219-223` — the inaccurate "Why `echo` as the action?" blockquote; main fix
- `loops/harness-single-shot.yaml:112-114` — YAML comment repeats the same incorrect claim ("shell output is ignored")
- `loops/harness-multi-item.yaml:137-139` — YAML comment repeats the same incorrect claim

**If BUG-880 is fixed first (preferred path per step 3):**
- `skills/create-loop/loop-types.md:713-720` — Variant A `check_semantic` template (no `source` field); update after BUG-880 adds `source`
- `skills/create-loop/loop-types.md:775-782` — Variant B `check_semantic` template (no `source` field); same

### Reference Files (Do Not Modify)

Explain the actual behavior for writing accurate replacement text:
- `scripts/little_loops/fsm/executor.py:875-882` — `_evaluate()`: no `source` → `else: eval_input = raw_output`
- `scripts/little_loops/fsm/evaluators.py:557-563` — `evaluate_llm_structured()`: echo output in `<action_output>` tag
- `scripts/little_loops/fsm/executor.py:666-670` — `prev_result` set after evaluation; `prev.output` = immediately preceding state only
- `scripts/little_loops/fsm/schema.py:76` — `source: str | None = None` on `EvaluateConfig`
- `docs/generalized-fsm-loop.md:784-807` — "Evaluation Source" section shows correct `source: "${captured.<var>.output}"` pattern

### Similar Correct Patterns (Model After)

Production loops using `llm_structured` with `source` correctly:
- `loops/issue-staleness-review.yaml:36-47` — `source: "${captured.review_result.output}"`
- `loops/sprint-build-and-validate.yaml:57-65` — `source: "${captured.validation_result.output}"`
- `loops/issue-size-split.yaml:20-28` — `source: "${captured.size_report.output}"`

### Tests
- `scripts/tests/test_fsm_evaluators.py:584-885` — `evaluate_llm_structured` coverage
- `scripts/tests/test_fsm_executor.py` — executor integration tests

## Implementation Steps

1. Correct the "Why `echo`?" note to accurately describe what happens: the echo output IS what the LLM receives; the claim about "previous state's output" is only true if `source: "${prev.output}"` is set
2. Either: (a) fix the generated YAML to add `source: "${prev.output}"` (BUG-880), making the documentation accurate after the fix, or (b) update the docs to reflect current behavior and document the `source` field as an opt-in improvement
3. The preferred path is (a): fix BUG-880 first, then update the docs to match

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Concrete changes needed:**

**Step 1 — Fix `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:219-223`**: Replace the inaccurate blockquote. The corrected explanation: the echo output IS the evidence the LLM receives (embedded in `<action_output>` by `evaluators.py:563`); to judge a prior state's output, `source: "${captured.<var>.output}"` must be set explicitly (`executor.py:875-882`).

**Step 1b — Fix YAML comments**: `loops/harness-single-shot.yaml:112-114` and `loops/harness-multi-item.yaml:137-139` repeat the same incorrect claim and should be updated alongside the guide.

**Step 3 — After BUG-880**: When updating the guide to reflect the BUG-880 fix, note that `source: "${captured.<execute_capture>.output}"` is the correct form (not `${prev.output}`), because `${prev.output}` at `check_semantic` resolves to `check_concrete`'s pytest output — not `execute`'s skill output. Model the explanation on `loops/issue-staleness-review.yaml:36-47`.

## Impact

- **Priority**: P3 — Misleads users building harness loops; `check_semantic` silently receives empty echo evidence instead of meaningful prior output, causing non-obvious evaluation failures
- **Effort**: Small — Text-only changes to documentation and YAML comments; no executable code changes
- **Risk**: Low — Documentation fix only; no behavioral changes to runtime code
- **Breaking Change**: No

## Labels

`bug`, `documentation`

## Resolution

Fixed by correcting the "Why `echo` as the action?" blockquote in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` and the corresponding YAML comments in `loops/harness-single-shot.yaml` and `loops/harness-multi-item.yaml`. All three locations now accurately describe that the echo string IS the `<action_output>` the LLM evaluator receives, and explain that `source: "${captured.<var>.output}"` must be set explicitly to pass prior state output.

## Status

**Completed** | Created: 2026-03-24 | Resolved: 2026-03-24 | Priority: P3

## Session Log
- `hook:posttooluse-git-mv` - 2026-03-25T02:08:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3312899e-fea8-40b9-9b4d-4853684c46c5.jsonl`
- `/ll:manage-issue` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-03-25T02:05:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b232923-7aab-40cc-95d9-2f5442836380.jsonl`
- `/ll:format-issue` - 2026-03-25T00:53:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4305bbc5-4892-4b4e-80f3-917b53ab0916.jsonl`
- `/ll:confidence-check` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/556f7371-7835-47ca-a34d-204ed0fd9aed.jsonl`
- `/ll:refine-issue` - 2026-03-25T00:47:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07c03e86-2f17-4650-a7f9-2d45a82edcd4.jsonl`
- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3df6195-41d1-442e-a5ec-89e21c18fa59.jsonl`
