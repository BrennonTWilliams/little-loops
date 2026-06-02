---
captured_at: '2026-05-28T17:31:20Z'
discovered_date: 2026-05-28
discovered_by: capture-issue
status: done
labels:
- bug
- captured
- loops
- general-task
- fsm
relates_to: [BUG-1628, BUG-1687, ENH-1732, BUG-1767]
---

# BUG-1766: `general-task` loop wastes ~40 iterations re-doing finished work (convergence-efficiency cluster)

## Summary

The post-`ENH-1732` `general-task` loop (`scripts/little_loops/loops/general-task.yaml`,
granular `select_step → do_work → verify_step → mark_done` design) **converges to the
correct result but burns ~40 redundant iterations** doing so. Audited in run
`2026-05-28T145405` (137 iterations, ~2.16h, final state `done`, verdict `met`): the
loop produced correct on-disk output, but iterations 94–135 were a degenerate
`continue_work → select_step → do_work → … → count_done → continue_work` cycle that
re-executed already-completed plan steps via the (expensive) `do_work` LLM prompt while
the actual fix sat unselected at the bottom of the plan file.

This is **not** the old deadlock — `BUG-1628` (plan exhaustion) and `BUG-1687` (stale
capture) are fixed. This is a cost/efficiency defect: four coupled root causes in the
current FSM that make the loop spin instead of progress. None of them block completion,
but together they roughly triple iteration count on tasks with a self-referential or
poorly-covered DoD criterion.

## Current Behavior

Run `2026-05-28T145405` reached `done` correctly, but:
- Iterations 94–135 (~40 cycles, ~40 min) re-executed plan steps 13–18 (already-completed
  duplicates) while remediation steps 20–25 sat unselected at the plan's tail.
- The loop only escaped when a `do_work` agent **disobeyed** the "do not edit the plan"
  instruction at step 19 and struck through the duplicates, finally satisfying the
  self-referential DoD criterion.
- No stall/fault signal fired during the spin (see companion issue BUG-1767).

## Root Cause

**File**: `scripts/little_loops/loops/general-task.yaml`. Four coupled causes:

### (a) `select_step` and `mark_done` disagree on "which step is current"
- `select_step` (line 113) picks the **first** unchecked step via `grep -m1 '^- \[ \]'`
  and writes its text to `general-task-current-step.txt`.
- `mark_done` (line 177) marks the **first** unchecked step via
  `awk 'found==0 && /^- \[ \]/ {...}'` — it **ignores the contents** of
  `current-step.txt` (the file path is referenced only to `rm` it, line 178).

They coincide today **only** because both hardcode "first." This coupling is fragile: any
change to selection order silently corrupts which step gets marked. In particular the
audit's Proposal #1 (change `select_step` to `grep ... | tail -1`) is **wrong as written**
— `select_step` would pick the *last* unchecked step while `mark_done` still marks the
*first*, checking off a step that was never executed.

**Fix**: make `mark_done` mark the line that matches `current-step.txt`, decoupling marking
from selection order. Once decoupled, the selection strategy (first vs. last vs.
prioritized) can be changed safely — but the `tail -1` change is unnecessary if marking is
correctly bound to the selected step.

### (b) `continue_work ↔ mark_done` net-zero equilibrium
Each visit to `continue_work` (lines 355–372) **appends** one remediation step to the plan
(`unchecked_plan + 1`); the next `mark_done` removes one (`unchecked_plan − 1`). Net zero.
Because `count_done.total` includes `unchecked_plan` (line 289), that term never drains
while a DoD criterion stays unchecked — so `count_done` routes back to `continue_work`
indefinitely, and `select_step` keeps re-selecting old top-of-list steps for `do_work` to
redundantly re-execute (the expensive LLM calls).

**Fix** (audit Proposal #3): add a dedup guard in `continue_work` so it does not append a
near-duplicate remediation step when an equivalent one is already present in the plan.

### (c) Self-referential DoD criterion is unsatisfiable by design
The run's DoD contained a criterion **about the loop's own tracking file** ("duplicate
remediation steps are struck through in the plan file"). But `do_work` is explicitly
forbidden to modify the plan/DoD files (line 139), so this criterion could only ever be
satisfied by the agent disobeying its instructions (which is what eventually happened at
step 19).

**Fix**: harden `define_done` (lines 24–52) to instruct the agent **not to write DoD
criteria that target the loop's internal tracking artifacts** (`general-task-plan.md`,
`general-task-dod.md`). Kill the class of unsatisfiable criteria preventively.

**Rejected alternative** (audit Proposal #4): allowing `do_work` to edit plan/DoD for
"plan-maintenance" steps. This weakens the separation that stops the agent from gaming
completion by editing its own scorecard, and trades a preventable input problem for a
permanent guard erosion.

### (d) Misleading `continue_work` prompt
`continue_work` line 363 asserts "The plan is fully [x] but at least one DoD criterion
remains unchecked." The state is also reachable from `count_done.on_no` when
`unchecked_plan > 0` (plan NOT fully checked), feeding the agent a false premise.

**Fix** (audit Proposal #2): reword to read the plan to determine actual checked/unchecked
state rather than asserting the plan is complete.

## Expected Behavior

- `mark_done` marks the exact step that `select_step` selected (no first/last desync).
- `continue_work` does not append duplicate remediation steps; `unchecked_plan` drains
  monotonically.
- `define_done` does not emit DoD criteria about the loop's own plan/DoD tracking files.
- The `continue_work` prompt reflects the actual plan state on entry.
- A task like run `2026-05-28T145405` converges in materially fewer iterations (target:
  no degenerate re-execution cycle).

## Steps to Reproduce

1. Run `general-task` on a task whose DoD includes a criterion about the plan file itself
   (or whose plan accumulates duplicate steps), e.g. the framework-gap-closure task from
   run `2026-05-28T145405`.
2. Observe `count_done` repeatedly routing to `continue_work`, which appends remediation
   steps to the plan tail while `select_step` keeps picking old top-of-list steps.
3. Observe `do_work` re-executing already-completed steps for dozens of iterations before
   the loop escapes.

## Proposed Solution

Four coordinated edits to `scripts/little_loops/loops/general-task.yaml`:

1. **`mark_done`** — mark the plan line matching `current-step.txt` content instead of the
   first unchecked line (`awk found==0`). Decouples marking from selection order.
2. **`continue_work`** — add a dedup guard before appending a remediation step (skip append
   if a near-equivalent step already exists in the plan).
3. **`define_done`** — add an instruction forbidding DoD criteria that target the loop's
   internal tracking artifacts (`general-task-plan.md` / `general-task-dod.md`).
4. **`continue_work` prompt** — reword the "plan is fully [x]" premise to instruct the
   agent to read the plan and determine actual state.

Do **not** apply audit Proposal #1 (`select_step` → `tail -1`) unless #1 above (mark_done
binding) lands first; and **reject** audit Proposal #4 (relaxing the `do_work` plan/DoD
edit restriction).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — `select_step`/`mark_done`,
  `continue_work`, `define_done` states.

### Dependent Files (Callers/Importers)
- N/A — YAML config; no Python imports.

### Tests
- `scripts/tests/test_general_task_loop.py` (107 tests today) — add structural assertions:
  - `mark_done` action references `current-step.txt` content (not just `awk found==0`).
  - `continue_work` action contains a dedup guard.
  - `define_done` action forbids tracking-file criteria.
  - `continue_work` prompt no longer asserts "plan is fully [x]".

### Similar Patterns
- Re-validate after edits with `ll-loop validate general-task`.

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — the general-task cycle description may reference the
  select/mark behavior; update if the step-selection contract changes.

### Configuration
- N/A

## Implementation Steps

1. Bind `mark_done` to the selected step (`current-step.txt`).
2. Add the `continue_work` dedup guard.
3. Add the `define_done` tracking-file prohibition.
4. Reword the `continue_work` prompt.
5. Add/extend regression tests in `test_general_task_loop.py`.
6. Re-run a self-referential-DoD task end-to-end and confirm the degenerate cycle is gone.

## Impact

- **Priority**: P3 — Efficiency/cost defect, not a deadlock. The loop still converges to a
  correct result; the cost is ~40 wasted iterations (~40 min, dozens of redundant LLM
  calls) on affected tasks. Not data-loss or security.
- **Effort**: Small–Medium — YAML-only edits to four states plus regression tests.
- **Risk**: Low–Medium — `mark_done` binding (1) is a behavior change to plan tracking and
  must be tested carefully; the other three are additive/wording changes.
- **Breaking Change**: No.

## Related Key Documentation

- [[BUG-1628]] — earlier general-task plan-exhaustion deadlock (fixed); predecessor.
- [[BUG-1687]] — stale-capture defect (fixed); resolved structurally by ENH-1732.
- [[ENH-1732]] — split `execute` into `select_step`/`do_work`/`verify_step`/`mark_done`;
  introduced the states this issue refines.
- [[BUG-1767]] — companion: StallDetector blind to this spin because `continue_work`
  mutates a `progress_paths` file every cycle.

## Labels

`bug`, `captured`, `loops`, `general-task`, `fsm`

## Session Log
- `/ll:capture-issue` - 2026-05-28T17:31:20Z - `d72d4842-d084-41b6-af0f-1adf964926ab.jsonl`

---

**Open** | Created: 2026-05-28 | Priority: P3
