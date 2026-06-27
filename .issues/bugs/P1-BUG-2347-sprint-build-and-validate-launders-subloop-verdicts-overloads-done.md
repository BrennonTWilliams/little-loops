---
id: BUG-2347
title: "sprint-build-and-validate launders sub-loop verdicts and overloads 'done' with sprint-never-ran"
type: BUG
status: open
priority: P1
captured_at: "2026-06-27T21:16:24Z"
discovered_date: "2026-06-27"
discovered_by: capture-issue
labels:
- loops
- fsm
- sprint
- meta-loop
relates_to:
- BUG-2346
- ENH-2349
---

# BUG-2347: sprint-build-and-validate launders sub-loop verdicts and overloads 'done'

## Summary

The `sprint-build-and-validate` builtin loop has two structural defects that make its
terminal `done` state untrustworthy:

1. **Sub-loop verdict laundering.** Both sub-loop states route every outcome to the same
   next state, discarding the child's pass/fail signal:
   - `refine_issues` (`sprint-build-and-validate.yaml:78-83`):
     `on_success` / `on_failure` / `on_error` all → `map_dependencies`.
   - `refine_unresolved` (`:136-141`): `on_success` / `on_failure` / `on_error` all → `done`.
2. **`done` overloaded with "sprint never ran".** `run_sprint` (`:111-118`) routes both
   `on_no` and `on_error` to `extract_unresolved`, which routes `on_no` / `on_error` to
   `done`. So an `ll-sprint run` that exits non-zero (or crashes) — producing no
   `.sprint-state.json` — lands in `done` indistinguishably from a real success.

In the audited run (`audit-sprint-build-and-validate-2026-06-27.md`), the recursive-refine
child crashed (see BUG-2346) and ended in `failed`, but the parent continued to
`map_dependencies` as if refine succeeded; later `ll-sprint run` exited 1, no
`.sprint-state.json` was produced, and the loop still terminated at `done` — the `phantom`
verdict.

## Steps to Reproduce

1. Trigger `ll-loop run sprint-build-and-validate` with a sprint where the `recursive-refine` child exits non-zero or crashes (e.g., as caused by BUG-2346).
2. Observe that `refine_issues` routes to `map_dependencies` regardless of child outcome — the parent continues as if refine succeeded.
3. `ll-sprint run` exits non-zero and produces no `.sprint-state.json`.
4. Observe that `extract_unresolved` routes `on_no` / `on_error` to `done`.
5. The loop terminates at `done` — indistinguishable from a successful sprint execution.

Alternatively, inspect the YAML directly:

```bash
grep -A5 'refine_issues:\|run_sprint:\|refine_unresolved:\|extract_unresolved:' \
  loops/sprint-build-and-validate.yaml
```

All `on_failure` / `on_error` branches for the sub-loop states map to the same destination as `on_success`.

## Motivation

This is a meta-loop (it orchestrates other loops). Per `.claude/CLAUDE.md` § Loop Authoring,
laundering a sub-loop verdict defeats the parent's primary measurement: downstream
automation that keys on the terminal state misclassifies a non-run as a success. The
laundering also masks BUG-2346 entirely.

## Current Behavior

```yaml
refine_issues:
  loop: recursive-refine
  context_passthrough: true
  on_success: map_dependencies
  on_failure: map_dependencies   # laundered
  on_error: map_dependencies     # laundered

run_sprint:
  action: "ll-sprint run ${captured.sprint_name.output}"
  fragment: shell_exit
  on_yes: done
  on_no: extract_unresolved      # "sprint never ran" path
  on_error: extract_unresolved   # crash funneled the same way
# extract_unresolved on_no/on_error → done

refine_unresolved:
  loop: recursive-refine
  on_success: done
  on_failure: done               # laundered
  on_error: done                 # laundered
```

## Root Cause

- **File**: `loops/sprint-build-and-validate.yaml`
- **Anchors**: `refine_issues` state (line ~78), `run_sprint` state (line ~111), `extract_unresolved` state, `refine_unresolved` state (line ~136)
- **Cause**: All outcome branches (`on_success`, `on_failure`, `on_error`) of each sub-loop call state are wired to the same next state. FSM routing tables that collapse every verdict to the same destination discard the child's pass/fail signal entirely. The `run_sprint` → `extract_unresolved` → `done` path adds a second defect: a non-zero exit from `ll-sprint run` is treated as "nothing unresolved" rather than "sprint never ran", so the absence of `.sprint-state.json` is never detected as a failure.

## Expected Behavior

The parent distinguishes "refine succeeded", "refine failed", "sprint executed", and
"sprint never ran", with distinct terminal states for the failure paths.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — YAML routing table changes only; no Python code changes required

### Dependent Files (Context, No Changes)
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop()` (line 602): routes `final_state == "done"` → `on_yes`, any non-`done` terminal → `on_no`, `terminated_by == "error"` → `on_error`; the fix exploits this correctly
- `scripts/little_loops/fsm/schema.py` — `StateConfig.from_dict()` (lines 589–590): `on_success` maps to `on_yes`, `on_failure` maps to `on_no` — either YAML form is valid in the fix
- `scripts/little_loops/fsm/validation.py` — `_validate_partial_route_dead_end()` (line 1398): MR-4 does NOT catch sub-loop laundering (only flags `prompt`/`slash_command` states); the fix is correct by construction, not by MR-4 enforcement
- `scripts/little_loops/cli/sprint/run.py` — `_save_sprint_state()` (line 145): writes `.sprint-state.json` in `finally` block when `exit_code != 0`; `_cleanup_sprint_state()` (line 156): deletes it on success
- `scripts/little_loops/loops/recursive-refine.yaml` — child loop terminal states: `done` (line 909), `failed` (line 925)

### Similar Patterns (Model)
- `scripts/little_loops/loops/proof-first-task.yaml` — canonical model: bare `impl_failed: terminal: true`, `on_failure: impl_failed`, `on_error: impl_failed`
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — sub-loop routing: `on_failure: skip_and_continue`, `on_error: skip_and_continue` routes away from success path
- `scripts/little_loops/loops/outer-loop-eval.yaml` — `run_sub_loop` state with `on_no: handle_sub_loop_failed`, `on_error: handle_sub_loop_error` (separate named terminals per verdict)

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestSprintBuildAndValidateLoop` class (line 3138+): add new test cases for failure routing here
- `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` — existing fixture demonstrating the laundering anti-pattern; useful reference for mock child loop setup

## Implementation Steps

1. Add a `refine_failed` terminal; route `refine_issues.on_failure` / `.on_error` to it
   (emit a message pointing at `${context.run_dir}/recursive-refine-*.txt`).
2. Add a `sprint_failed` terminal; route `run_sprint.on_no` / `.on_error` to it, and
   `extract_unresolved.on_no` / `.on_error` to it (gate `extract_unresolved` on
   `.sprint-state.json` existence so "no state file" means failure, not "nothing unresolved").
3. Route `refine_unresolved.on_failure` / `.on_error` to a `refine_unresolved_failed`
   terminal (or reuse `refine_failed`).
4. Fix BUG-2346 first so these edges can be validated against a real (non-crashing) child.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`extract_unresolved` already has the `.sprint-state.json` gate** (`if [ ! -f .sprint-state.json ]; then exit 1; fi`) — the defect is only in the routing target: change `on_no → done` to `on_no → sprint_failed`; no new shell check is needed
- **YAML alias**: `on_success`/`on_failure` (used in the current file) are normalized to `on_yes`/`on_no` by `StateConfig.from_dict()` in `schema.py:589–590`; the fix can use either form consistently
- **MR-4 won't catch this class of bug**: `_validate_partial_route_dead_end()` in `validation.py:1398` only inspects `prompt`/`slash_command` states — sub-loop laundering escapes it; the fix must be applied and tested manually
- **Bare terminals are sufficient**: `proof-first-task.yaml` (`impl_failed: terminal: true`, no shell action) is the lightest correct pattern; use `rn-build.yaml`-style shell action only if a diagnostic message is needed at the failure terminal
- **Test pattern**: add cases under `TestSprintBuildAndValidateLoop` (line 3138 in `test_builtin_loops.py`); the `assess-subloop-laundering.yaml` fixture shows how to mock a child loop that exits via a `failed` terminal
- **Verification**: `ll-loop validate sprint-build-and-validate` — run after the fix; MR-4 still won't flag sub-loop laundering (known gap), but structural correctness is verified by inspection and the new test cases

## Acceptance Criteria

- [ ] A failed `recursive-refine` child routes the parent to a distinct failure terminal,
      not `map_dependencies` / `done`.
- [ ] An `ll-sprint run` non-zero exit or crash terminates in `sprint_failed`, not `done`.
- [ ] `done` is reachable only when the sprint actually executed (`.sprint-state.json` present).
- [ ] `ll-loop validate sprint-build-and-validate` passes (no MR-4 partial-route dead-ends).

## Impact

- **Priority**: P1 — downstream automation that keys on the terminal state misclassifies a failed sprint as success; masks the BUG-2346 child crash entirely
- **Effort**: Small — YAML routing table changes in a single loop file; no Python code changes
- **Risk**: Low — only failure paths are changed; the existing success path (`on_success → map_dependencies / done`) is untouched; validated via `ll-loop validate`
- **Breaking Change**: No — adds new terminal states (`refine_failed`, `sprint_failed`, `refine_unresolved_failed`); does not rename existing success terminals

## Notes

- Latent sub-finding (P3, optional): the loop sets `input_key: sprint_name` but does not
  declare `required_inputs`, so an empty `sprint_name` silently falls into `create_sprint`
  rather than failing fast. Address here or defer.

## Session Log
- `/ll:refine-issue` - 2026-06-27T21:30:26 - `896cb5bd-4f64-4827-8a19-5f35ee7764e8.jsonl`
- `/ll:format-issue` - 2026-06-27T21:21:38 - `fb662259-f1c0-459f-aa52-a7924d973eb2.jsonl`
- `/ll:capture-issue` - 2026-06-27T21:16:24Z - conversation analysis of audit-sprint-build-and-validate-2026-06-27.md

---

## Status

**Open** | Created: 2026-06-27 | Priority: P1
