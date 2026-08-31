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

## Current Behavior

Shell-action Python heredocs invoke bare `python3` (e.g. `python3 << 'PYEOF'
... PYEOF`), which PATH-resolves to whatever interpreter is first on the
child process's `PATH` at that moment — not necessarily the interpreter the
FSM executor itself is running under, and not necessarily one with
`little_loops` importable.

## Expected Behavior

Shell-action heredocs invoke `${LL_PYTHON:-python3}`, where `LL_PYTHON` is
set by the executor to `sys.executable` — the exact interpreter running the
loop — so a heredoc that needs `little_loops` always resolves to an
interpreter that has it installed, regardless of what a bare `python3` on
`PATH` would resolve to.

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

## Scope Boundaries

- Does not change how `python3` is resolved for anything outside FSM shell
  actions (CLI entry points, hooks, `ll-*` scripts) — those already run under
  whatever interpreter invoked them directly.
- Does not attempt to fix or normalize `PATH` itself; `LL_PYTHON` is an
  additive, opt-in override loop YAMLs must reference explicitly
  (`${LL_PYTHON:-python3}`), not a `PATH` rewrite.
- Does not migrate existing heredocs automatically — updating loop YAMLs to
  use `${LL_PYTHON:-python3}` is a mechanical follow-up once the executor
  exports the variable.

## Program Design

### Signatures

- `project_child_env(invocation=None, *, extra=None)` (`host_runner.py:1853`) — the single chokepoint every task-path shell-action `subprocess.*` spawn already routes through.
- `run(action, timeout, is_slash_command, on_output_line=None)` (`runners.py:117`, `DefaultActionRunner`) — its shell branch (`runners.py:305`) is where `project_child_env()` is called and where `LL_PYTHON` must be merged into `extra`.

### Call Path

`DefaultActionRunner.run` -> `project_child_env` (`extra={"LL_PYTHON": sys.executable}`) -> subprocess `env=` -> loop YAML heredoc `${LL_PYTHON:-python3}`.

## Impact

- **Priority**: P2 — this is the root cause behind [[BUG-3364]]'s specific
  crash and is not scoped to one state; every `python3`-invoking shell
  action in every loop YAML shares the same hazard.
- **Effort**: Small — one executor-side env var plus a mechanical
  find/replace across loop YAMLs.

## Status

**Open** | Created: 2026-08-30 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-08-31T02:10:25 - `816b6544-6e69-4192-a4ac-f797f3d82975.jsonl`
