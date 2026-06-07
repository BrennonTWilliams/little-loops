---
id: BUG-2011
type: BUG
priority: P2
status: open
captured_at: "2026-06-07T22:42:29Z"
discovered_date: 2026-06-07
discovered_by: capture-issue
labels: [fsm, loop-runner, dx, footgun]
---

# BUG-2011: FSM max_iterations counts state-steps, not loop cycles

## Summary

The FSM loop runner's `max_iterations` / `--max-iterations` (`-n`) caps the
number of **state executions**, but the name strongly implies a full loop
**cycle** (e.g. one `generate → evaluate → score → refine` pass). Loop authors
and CLI users naturally read "iterations" as cycles, under-budget the cap, and
get **silent premature termination** that looks like a loop defect rather than
an exhausted budget.

## Current Behavior

Each state execution increments the counter once. `ll-loop run <loop> -n 2`
therefore allows only two *states* to run total, not two cycles.

Observed during a smoke run of `canvas-sketch-generator` with `-n 2`:

- `init` executed (counter → 1)
- `plan` executed (counter → 2), `usage.jsonl` recorded
  `{"iteration": 2, "state": "plan"}`
- the cap fired before `generate` ever ran
- the run ended without reaching a terminal state and exited `1`

The user expected `-n 2` to permit ~2 full generate/score cycles.

## Expected Behavior

Either:
- `max_iterations` counts **cycles** (returns to the initial state, or
  completions of a designated anchor state), matching the intuitive reading; or
- the per-state-step semantics are made explicit (clear name + docs) so authors
  budget correctly.

A budget that is too small should also surface a clearer signal than a bare
`exit 1` with no terminal state (e.g. an explicit "max_iterations reached before
any terminal state" message).

## Steps to Reproduce

1. `ll-loop run canvas-sketch-generator "<any description>" -n 2`
2. Observe `.loops/runs/<loop>-<ts>/usage.jsonl` — only `init` and `plan`
   recorded; no `generate`.
3. Process exits `1`; no `index.html` / terminal state produced.

## Root Cause

`scripts/little_loops/fsm/executor.py`, `FSMExecutor.run()` main loop:

- **`executor.py:403`** — `self.iteration += 1` runs once per state execution,
  right before each `state_enter` emit.
- **`executor.py:296`** — `if self.iteration >= self.fsm.max_iterations:` gates
  on that per-state counter.

So `max_iterations` is a cap on total state executions. There is no separate
notion of a "cycle" anywhere in the increment/cap path.

## Impact

- **Affects every FSM loop**, not just the new one. Visual loops compensate by
  setting `max_iterations: 20` to obtain only ~5–6 real refine cycles — a magic
  number that encodes the confusion rather than fixing it.
- New loop authors choosing a `max_iterations` default will mis-budget.
- CLI users debugging a loop see silent early termination and misattribute it to
  a broken loop (as happened here).

## Proposed Fix

Evaluate, in order of preference:

1. **Cycle-based counting (preferred):** increment the cap counter only on
   return to `initial` (or a declared cycle-anchor state), and rename the
   per-step counter internally. Keep a separate hard step ceiling as a runaway
   backstop. Requires migrating existing loops' `max_iterations` values.
2. **Clarify + dual counter:** keep `max_iterations` as the step cap but expose
   it as `max_steps`, add an optional `max_cycles`, and document both.
3. **Minimum (docs-only):** document the per-state-step semantics in
   `ll-loop run --help`, the loop README, and the loop-authoring guide, and emit
   a clearer termination reason when the cap fires before any terminal state.

Whichever path: improve the terminal signal so "cap hit before terminal" is
distinguishable from a clean finish.

## Implementation Steps

1. Decide counting model (cycle vs step) — affects all existing loop YAML
   `max_iterations` values, so coordinate a migration if option 1.
2. Update `executor.py` increment/cap logic (`:403`, `:296`) and the
   `state_enter` / `max_iterations_summary` event payloads accordingly.
3. Update `ll-loop run --help` and loop-authoring docs.
4. Add a regression test asserting that a 1-cycle loop completes one full
   `initial → … → terminal` pass under the documented budget.

## Status

- **State**: open
- **Discovered**: 2026-06-07 (smoke run of canvas-sketch-generator)

## Session Log
- `/ll:capture-issue` - 2026-06-07T22:42:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/94001b17-192e-4675-8b12-449cc4ed8e69.jsonl`
