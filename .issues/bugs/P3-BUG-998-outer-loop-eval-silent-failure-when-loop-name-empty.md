---
discovered_date: "2026-04-08"
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 93
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exit code correction**: The issue summary says "exit code 2" but `ll-loop run ""` actually returns exit code **1**. `resolve_loop_path("")` raises `FileNotFoundError` which is caught at `scripts/little_loops/cli/loop/run.py:42-44` and returns `1`. Both exit codes produce identical routing (any nonzero exit fires `on_error` in the `next:` branch at `scripts/little_loops/fsm/executor.py:411-412`), so the fix is unaffected.

**Second fix point**: The pre-run validation at `scripts/little_loops/cli/loop/run.py:94` checks only key presence (`if key not in fsm.context`), not emptiness. An empty-string `loop_name` passes this check silently. Adding the `validate_input` state is sufficient; fixing the pre-run check is a separate, optional hardening (tracked by ENH-999).

**Shell fragment alternative**: The closest codebase pattern (`prompt-across-issues.yaml:22`) uses `fragment: shell_exit` instead of `action_type: shell`. Both evaluate exit codes the same way for routing purposes; `action_type: shell` is consistent with the proposed YAML and with `refine-to-ready-issue.yaml`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/outer-loop-eval.yaml` — add validation state, update `initial`

### Dependent Files (Callers/Importers)
- Any invocation of `ll-loop run outer-loop-eval` — callers passing JSON as positional input will need to switch to `--context` flags

_Wiring pass added by `/ll:wire-issue`:_
- `skills/analyze-loop/SKILL.md` — invokes `ll-loop run` and drives outer-loop-eval usage; no code change needed (correct `--context` pattern already documented)
- `skills/review-loop/SKILL.md` — references `ll-loop run`; no code change needed
- `skills/create-eval-from-issues/SKILL.md` — generates eval harness invocations using `ll-loop run outer-loop-eval`; no code change needed, but verify generated invocations use `--context loop_name=X` pattern
- `commands/loop-suggester.md` — references `ll-loop run <name>` as execution step; no code change needed

### Similar Patterns
- `scripts/little_loops/loops/prompt-across-issues.yaml:22-42` — `init` state guards `context.input` with `[ -z "${context.input}" ]`; uses `fragment: shell_exit` (not `action_type: shell`) and routes `on_error: error` to a dedicated terminal `error` state
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:15-25` — `resolve_issue` state uses `[ -n "${context.input}" ]` non-empty check; `action_type: shell` with `on_error: failed` → terminal `failed` state
- `scripts/little_loops/loops/general-task.yaml:25,45,58,78,91` — all shell/prompt states route `on_error: failed`; establishes a named terminal failure state as the preferred pattern over routing to `done`

### Tests
- `scripts/tests/test_outer_loop_eval.py` — existing structural tests for outer-loop-eval; add: (1) assert `loop_data["initial"] == "validate_input"`, (2) assert `validate_input` state exists with `action_type: shell`, `on_error: done`, `next: analyze_definition`
- `scripts/tests/test_builtin_loops.py:36-44` — FSM validation sweep runs automatically on all loop YAMLs; the new state is covered if it validates as a valid FSM

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_outer_loop_eval.py:43` — **WILL BREAK**: `test_initial_state` asserts `initial == "analyze_definition"`; must be updated to `"validate_input"` (not just adding a new assertion)
- `scripts/tests/test_outer_loop_eval.py:64-72` — `REQUIRED_STATES` set is missing `"validate_input"`; add it so `test_has_all_required_states` covers the new state
- New test methods to write in `TestOuterLoopEvalStates` (follow pattern at `test_builtin_loops.py:764-768`):
  - `test_validate_input_checks_loop_name` — assert `"context.loop_name"` appears in the state's `action`
  - `test_validate_input_routes_error_to_done` — assert `state.get("on_error") == "done"` (fast-exit path)
  - `test_validate_input_routes_next_to_analyze_definition` — assert `state.get("next") == "analyze_definition"` (happy path)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:1154-1159` — FSM flow diagram shows `analyze_definition` as the entry node; update to show `validate_input` as the entry with `on_error: done` fast-exit branch
- `docs/guides/LOOPS_GUIDE.md:1161` — "Execution failure handling" paragraph describes routing to `analyze_execution` when a loop fails to start; this masking behavior is what BUG-998 fixes for the empty-`loop_name` case — update to reflect that empty `loop_name` now fails fast before `run_sub_loop`

### Configuration
- N/A — no configuration files affected

## Implementation Steps

1. Add `validate_input` shell state to `outer-loop-eval.yaml`
2. Change `initial: analyze_definition` to `initial: validate_input`
3. Verify: `ll-loop run outer-loop-eval ""` exits immediately with a clear error message
4. Verify: `ll-loop run outer-loop-eval --context loop_name=general-task` proceeds normally

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `scripts/tests/test_outer_loop_eval.py:43` — change `test_initial_state` to assert `initial == "validate_input"` (not `"analyze_definition"`)
6. Update `scripts/tests/test_outer_loop_eval.py:64-72` — add `"validate_input"` to the `REQUIRED_STATES` set
7. Add 3 new test methods to `TestOuterLoopEvalStates` covering: `context.loop_name` in action, `on_error: done`, `next: analyze_definition`
8. Update `docs/guides/LOOPS_GUIDE.md:1154-1159` — update FSM flow diagram to show `validate_input` as entry node with `on_error: done` fast-exit
9. Update `docs/guides/LOOPS_GUIDE.md:1161` — update execution failure paragraph to reflect empty `loop_name` now fails fast instead of routing to `analyze_execution`

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
- `/ll:confidence-check` - 2026-04-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/099e75da-a1a5-40c7-a589-3871b7902a35.jsonl`
- `/ll:wire-issue` - 2026-04-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:refine-issue` - 2026-04-08T18:35:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29500f71-5c9a-408d-a706-2f171a54f6dc.jsonl`
- `/ll:format-issue` - 2026-04-08T18:31:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fc203fc7-0ff3-4083-ad37-4f7804f33e8d.jsonl`

- `/ll:capture-issue` - 2026-04-08T18:24:52Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8163e06d-ba51-4c89-ad08-3b2526018e0f.jsonl`

---

## Status

**Open** | Created: 2026-04-08 | Priority: P3
