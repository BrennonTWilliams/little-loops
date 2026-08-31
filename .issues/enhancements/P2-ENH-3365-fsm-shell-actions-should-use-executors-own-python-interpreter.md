---
id: ENH-3365
type: ENH
priority: P2
status: open
captured_at: '2026-08-30T23:30:00Z'
discovered_date: 2026-08-30
discovered_by: audit-loop-run
relates_to:
- BUG-3364
decision_needed: false
---

# ENH-3365: FSM shell actions should invoke the executor's own Python interpreter, not bare `python3`

## Summary

Shell-action Python heredocs across `scripts/little_loops/loops/*.yaml`
(e.g. `verify` at line 392, `merge_epic_branch` at line 543, `recheck_set`
at line 324 in `auto-refine-and-implement.yaml`) invoke `python3` bare,
relying on whatever interpreter is first on `PATH` at execution time to have
`little_loops` importable. That's not guaranteed to be the same interpreter
the FSM executor itself is running under — a machine can easily have
multiple Python installs on `PATH` (e.g. a pyenv-managed one with
`little_loops` installed editable, and an unrelated system/conda one
without it) — if `PATH` resolves `python3` to the wrong interpreter partway
through a long run, every subsequent heredoc in that run silently crashes
with `ModuleNotFoundError`.

## Evidence

During the `2026-08-30T222734-sprint-refine-and-implement` run, `recheck_set`,
`verify`, and `merge_epic_branch` all crashed with
`ModuleNotFoundError: No module named 'little_loops.config'` /
`'little_loops.worktree_utils'` roughly 2.5 hours in — after `checkout_epic_branch`
had run successfully earlier in the same run using presumably the same shell
environment. This audit independently reproduced the identical failure class
invoking the `ll-loop` CLI itself: one installed entry point on this
machine's `PATH` resolved to a Python without `little_loops` installed
(`ModuleNotFoundError: No module named 'little_loops.cli'`), while a
different entry point on the same `PATH` worked correctly — confirming the
split is a real, reproducible environment hazard, not a one-off fluke. See
[[BUG-3364]] for the specific downstream symptom (crash swallowed as an
empty verdict).

## Proposed Solution

Have the FSM executor (`scripts/little_loops/fsm/executor.py`) export
`sys.executable` as an environment variable (e.g. `LL_PYTHON`) into every
shell action's environment, and update loop YAML heredocs to invoke
`${LL_PYTHON:-python3}` instead of bare `python3`. This guarantees any
Python heredoc a loop runs uses the exact interpreter running the loop
itself — the one guaranteed to have `little_loops` importable — regardless
of what a bare `python3` on `PATH` resolves to at that moment.

## Impact

- **Priority**: P2 — this is the root cause behind [[BUG-3364]]'s specific
  crash and is not scoped to one state; every `python3`-invoking shell
  action in every loop YAML shares the same hazard.
- **Effort**: Small — one executor-side env var plus a mechanical
  find/replace across loop YAMLs.
