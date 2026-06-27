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

## Expected Behavior

The parent distinguishes "refine succeeded", "refine failed", "sprint executed", and
"sprint never ran", with distinct terminal states for the failure paths.

## Implementation Steps

1. Add a `refine_failed` terminal; route `refine_issues.on_failure` / `.on_error` to it
   (emit a message pointing at `${context.run_dir}/recursive-refine-*.txt`).
2. Add a `sprint_failed` terminal; route `run_sprint.on_no` / `.on_error` to it, and
   `extract_unresolved.on_no` / `.on_error` to it (gate `extract_unresolved` on
   `.sprint-state.json` existence so "no state file" means failure, not "nothing unresolved").
3. Route `refine_unresolved.on_failure` / `.on_error` to a `refine_unresolved_failed`
   terminal (or reuse `refine_failed`).
4. Fix BUG-2346 first so these edges can be validated against a real (non-crashing) child.

## Acceptance Criteria

- [ ] A failed `recursive-refine` child routes the parent to a distinct failure terminal,
      not `map_dependencies` / `done`.
- [ ] An `ll-sprint run` non-zero exit or crash terminates in `sprint_failed`, not `done`.
- [ ] `done` is reachable only when the sprint actually executed (`.sprint-state.json` present).
- [ ] `ll-loop validate sprint-build-and-validate` passes (no MR-4 partial-route dead-ends).

## Notes

- Latent sub-finding (P3, optional): the loop sets `input_key: sprint_name` but does not
  declare `required_inputs`, so an empty `sprint_name` silently falls into `create_sprint`
  rather than failing fast. Address here or defer.

## Session Log
- `/ll:capture-issue` - 2026-06-27T21:16:24Z - conversation analysis of audit-sprint-build-and-validate-2026-06-27.md

---

## Status

open
