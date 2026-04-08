---
discovered_date: "2026-04-08"
discovered_by: capture-issue
---

# BUG-998: outer-loop-eval silently proceeds and hallucinates report when loop_name is empty

## Summary

`outer-loop-eval` is designed to receive `loop_name` and `input` as separate named context variables via `--context` flags. When a caller passes both as a JSON dict to the positional `input` argument (a natural but unsupported pattern), `ll-loop` stores the entire JSON string in `context.input` and leaves `context.loop_name` at its default of `""`. The loop silently calls `ll-loop run ""`, fails with exit code 2, then produces a plausible-looking improvement report based on LLM inference rather than actual sub-loop execution — giving a false impression the evaluation ran successfully.

The caller's intent was correct; the runtime has no mechanism to detect and surface this miscall.

## Steps to Reproduce

1. Run: `ll-loop run outer-loop-eval '{"loop_name": "general-task", "input": "some input"}'`
   - **Note**: the JSON dict is passed as the positional `input` arg to `outer-loop-eval`, not as context variable assignments. `ll-loop` does not unpack it.
2. Observe `context.loop_name = ""` — `run_sub_loop` calls `ll-loop run "" '{...}'` (exit code 2)
3. Loop completes via `on_error -> analyze_execution -> generate_report -> done`
4. A full improvement report is emitted with no indication the sub-loop never ran

## Current Behavior

`outer-loop-eval` reaches `done` with a structured improvement report, even though `context.loop_name` is `""` and the sub-loop was never executed. The report is fabricated from the LLM's prior knowledge.

## Expected Behavior

If `context.loop_name` is empty at the start of the loop, fail fast with a clear error: "`loop_name` is required — pass it with `--context loop_name=<name>`." Do not proceed to `run_sub_loop` or generate a report.

## Root Cause

- **File**: `scripts/little_loops/loops/outer-loop-eval.yaml`
- **Anchor**: `analyze_definition` state
- **Cause**: `context.loop_name` defaults to `""`. Neither `analyze_definition` nor `run_sub_loop` validates that it is non-empty. `run_sub_loop`'s `on_error` route masks the failure by routing to `analyze_execution`, which then generates a report anyway. The loop has no input validation layer.

## Location

- **File**: `scripts/little_loops/loops/outer-loop-eval.yaml`
- **Line(s)**: 18-39 (analyze_definition), 41-47 (run_sub_loop)
- **Anchor**: `analyze_definition` state, `run_sub_loop` state

## Proposed Solution

Add a guard to `analyze_definition` that checks whether `context.loop_name` is non-empty and terminates with an error if not. Options:

1. Add a shell pre-check state before `analyze_definition` that validates `context.loop_name` and routes to `done` with an error message if empty.
2. Add explicit instruction to `analyze_definition` to check for empty `loop_name` and set a terminal error capture.
3. Add a `validate_input` state as the new `initial` that runs `test -n "${context.loop_name}"` and routes to `done` on failure.

## Motivation

The silent failure is worse than an outright crash: the user receives a full, confidently-worded report with no indication it was hallucinated. This erodes trust in the eval tooling.

## Proposed Solution

Add a `validate_input` state as the loop's new `initial`:

```yaml
validate_input:
  action_type: shell
  action: |
    test -n "${context.loop_name}" && echo "loop_name: ${context.loop_name}" || (echo "ERROR: loop_name is required. Pass it with --context loop_name=<name>" >&2; exit 1)
  on_error: done
  next: analyze_definition
```

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/outer-loop-eval.yaml` — add validation state, update `initial`

### Dependent Files (Callers/Importers)
- Any invocation of `ll-loop run outer-loop-eval` — callers passing JSON as positional input will need to switch to `--context` flags

### Similar Patterns
- TBD - check other loops that use context variables with empty-string defaults

### Tests
- TBD - add eval test for empty `loop_name` invocation

## Implementation Steps

1. Add `validate_input` shell state to `outer-loop-eval.yaml`
2. Change `initial: analyze_definition` to `initial: validate_input`
3. Verify: `ll-loop run outer-loop-eval ""` exits immediately with a clear error message
4. Verify: `ll-loop run outer-loop-eval --context loop_name=general-task` proceeds normally

## Impact

- **Priority**: P3 - Silent hallucination erodes trust in eval tooling
- **Effort**: Small - single YAML state addition
- **Risk**: Low - additive change, doesn't affect existing correct invocations
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `outer-loop-eval`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-08T18:24:52Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8163e06d-ba51-4c89-ad08-3b2526018e0f.jsonl`

---

## Status

**Open** | Created: 2026-04-08 | Priority: P3
