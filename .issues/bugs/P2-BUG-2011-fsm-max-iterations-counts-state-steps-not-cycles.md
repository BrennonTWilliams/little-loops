---
id: BUG-2011
type: BUG
priority: P2
status: open
captured_at: "2026-06-07T22:42:29Z"
discovered_date: 2026-06-07
discovered_by: capture-issue
labels: [fsm, loop-runner, dx, footgun]
decision_needed: false
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Three increment sites** (not one): `executor.py:403` (primary, before every non-terminal `state_enter`), `executor.py:355` (maintain-mode restart — fires when `self.fsm.maintain=True` and the FSM reaches a terminal state, then routes back to `initial`), and `executor.py:1372` (flush path in `_flush_pending_shell_state`, emits `state_enter` with `"flushed": True`). Option 1 (cycle-based) must update all three sites consistently.
- **`max_edge_revisits`** (`schema.py:953`, default 100) is the existing separate runaway backstop — fires `terminated_by="cycle_detected"` when any single directed edge (`from→to`) is traversed more than 100 times. This is tracked via `self._edge_revisit_counts` at `executor.py:462-481`. It is distinct from `max_iterations` and must be retained under any option.
- **`on_max_iterations`** field already exists (`schema.py:952`, default `None`) — allows a loop YAML to declare a summary state that executes when the cap fires (path A in the cap check at `executor.py:296-306`). Loops without it get bare `exit 1` with no console message. This is the "silent termination" gap; `on_max_iterations` is the existing partial fix for loops that set it.
- **Maintain mode** (`self.fsm.maintain`) is the closest existing "cycle" concept — on terminal, routes back to `initial`. But `self.iteration` still increments once per state-step during maintain restarts (line 355). There is no "back to initial" cycle counter anywhere.
- **Default**: `max_iterations=50` state-steps. 81+ loop YAML files declare `max_iterations`; many use values like 20 to obtain ~5–6 real refine cycles, encoding the confusion as a magic-number offset. `canvas-sketch-generator.yaml:22` already has an explicit comment referencing BUG-2011.
- **Exit code**: `_helpers.py:29-37` `EXIT_CODES` maps `"max_iterations" → 1` (same as `timeout`, `cycle_detected`, `stall_detected`). No console message currently distinguishes cap-before-terminal from other `exit 1` causes.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor.run()` increment
  (`self.iteration += 1`, `:403`) and cap check
  (`self.iteration >= self.fsm.max_iterations`, `:296`); the `state_enter` and
  `max_iterations_summary` event payloads.

### Codebase Research Findings — Additional Files to Modify

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/schema.py` — `FSMLoop` dataclass: `max_iterations: int = 50` (line 951), `on_max_iterations: str | None = None` (line 952), `max_edge_revisits: int = 100` (line 953). Serialization guard (lines 992-993 only writes `max_iterations` when != 50). Deserialization at line 1081. Under Option 2, add `max_cycles` field here. Under Option 1, rename or retain `max_iterations` for backwards compat with existing YAMLs.
- `scripts/little_loops/cli/loop/_helpers.py` — `EXIT_CODES` dict (lines 29-37): `"max_iterations": 1`; `run_foreground()` return at line 1275. To surface a clearer "cap hit before terminal state" message, add console output here before returning exit code 1.
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON schema definition for `max_iterations` (lines 37-41, description "Safety limit for loop iterations"). Must be updated if field is renamed or new fields are added (Option 2).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/*.yaml` — every loop declaring `max_iterations`
  (e.g. visual loops at `max_iterations: 20`) would need re-tuning under
  cycle-based counting.
- `ll-loop run` CLI (`--max-iterations` / `-n`) — help text and the
  termination-reason surfacing when the cap fires before a terminal state.

### Codebase Research Findings — Additional Dependent Files

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/loop/__init__.py:127` — argparse: `run_parser.add_argument("--max-iterations", "-n", type=int, help="Override iteration limit")`. Help text string needs updating. Same flag exists for `simulate` subcommand at line 468.
- `scripts/little_loops/cli/loop/run.py:118-119` — applies CLI override: `if args.max_iterations: fsm.max_iterations = args.max_iterations`. Under Option 2, if `--max-cycles` is added, this is where it maps to the new `FSMLoop` field.
- `scripts/little_loops/fsm/persistence.py:190,810` — `LoopState.iteration: int` persists the per-step counter; `PersistentExecutor.resume()` restores it via `self._executor.iteration = state.iteration` at line 810. Under Option 1, a `cycle_count` field must also be serialized/restored here.

### Similar Patterns
- Any other budget/limit counter in the executor (runaway step backstop) —
  keep increment semantics consistent if a step ceiling is retained.

### Tests

### Codebase Research Findings — Specific Test Files and Functions

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_fsm_executor.py` — primary file:
  - `test_max_iterations_respected` (line 159) — existing test that validates per-step cap with `max_iterations=3`; update or add sibling to assert cycle-based semantics under the chosen option.
  - `TestMaxIterationsSummaryHook` class (lines 7184-7215) — covers `on_max_iterations` behavior; includes `test_max_iterations_summary_event_emitted`, `test_terminated_by_max_iterations_after_summary`, `test_no_summary_state_without_on_max_iterations`. Model new tests after this class.
  - `test_cycle_detection_terminates_loop` (line 183) — covers `max_edge_revisits` backstop; verify it still passes after executor changes.
  - `test_fix_retry_loop` — demonstrates `result.iterations == 3` for a 2-cycle `check→fix→check→done` sequence; useful as before/after reference for cycle-count behavior.
- `scripts/tests/test_ll_loop_execution.py` — `test_exits_on_max_iterations` exercises CLI end-to-end with `mock_popen.call_count` assertions; may need updating for renamed flags or new message text.
- `scripts/tests/test_fsm_persistence.py` — `test_final_status_interrupted_on_max_iterations` covers persistence layer; update if `LoopState` gains a `cycle_count` field (Option 1).
- **New regression to add**: a multi-state loop with N states per cycle and `max_iterations=1` (cycle-based) should execute all N states in the first cycle before terminating — not stop after 1 state-step.

### Documentation
- `ll-loop run --help`, the loop README, and the loop-authoring guide
  (`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`).

### Codebase Research Findings — Specific Doc Files

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — loop budgeting guidance; update `max_iterations` semantics section.
- `docs/guides/LOOPS_GUIDE.md` — general loop authoring guide; update budgeting examples.
- `docs/reference/loops.md` — loop reference documentation; update `max_iterations` field description.
- `docs/reference/EVENT-SCHEMA.md` — covers `state_enter` and `max_iterations_summary` event payloads; update if payload fields change.

### Configuration
- `max_iterations` field semantics in the loop YAML schema (plus any
  `max_steps` / `max_cycles` additions for option 2).

### Codebase Research Findings — Schema File

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/fsm-loop-schema.json:37-41` — JSON schema for `max_iterations` with description "Safety limit for loop iterations". Update description or add new field entries (Option 2) here.

## Impact

- **Priority**: P2 — Affects every FSM loop's budgeting and produces confusing
  silent termination, but a workaround exists (over-budget `max_iterations`);
  not a crash or data-loss path.
- **Effort**: Medium — the executor change itself is localized, but option 1
  (cycle-based counting) also requires migrating existing loops' `max_iterations`
  values plus docs and test updates.
- **Risk**: Medium — changing counting semantics silently shifts every existing
  loop's termination point; mitigate with a retained hard step backstop and a
  coordinated migration.
- **Breaking Change**: Yes for option 1 (existing `max_iterations` values need
  re-tuning); No for options 2–3.

### Effects

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

   > **Selected:** Option 2 — Clarify + dual counter — The `max_iterations`+`max_edge_revisits` dual-counter pattern and the `on_success`→`on_yes` field-alias pattern are both directly established in `FSMLoop`/`schema.py:from_dict()`, making this the highest-consistency option. It delivers the console message and docs improvements of Option 3 as a subset, plus a concrete `max_cycles` API that eliminates the magic-number budgeting offset in 77+ existing loop YAMLs — all with no breaking changes and no YAML migrations.

3. **Minimum (docs-only):** document the per-state-step semantics in
   `ll-loop run --help`, the loop README, and the loop-authoring guide, and emit
   a clearer termination reason when the cap fires before any terminal state.

Whichever path: improve the terminal signal so "cap hit before terminal" is
distinguishable from a clean finish.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-07.

**Selected**: Option 2 — Clarify + dual counter

**Reasoning**: The `max_iterations`+`max_edge_revisits` pair in `FSMLoop` is the established dual-counter precedent, and the `on_success`→`on_yes` alias in `schema.py:from_dict()` provides a direct template for exposing `max_iterations` as `max_steps` without any YAML migrations. Option 2 is a strict superset of Option 3's improvements (console message, help string, docs) and additionally provides a `max_cycles` field that eliminates the manual step-to-cycle math encoded as magic-number comments across 77+ loop YAMLs (`max_iterations: 20` for ~5 real cycles). Option 1 is blocked by a breaking change requiring 80-file YAML migration, a triple-duty `self.iteration` separation across executor/persistence/event-schema, and the loss of the `-n 1` single-step debugging idiom.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 (cycle-based rewrite) | 1/3 | 0/3 | 1/3 | 0/3 | 2/12 |
| Option 2 (dual counter) | 3/3 | 2/3 | 2/3 | 2/3 | 9/12 |
| Option 3 (docs-only) | 2/3 | 3/3 | 2/3 | 3/3 | 10/12 |

**Key evidence**:
- Option 1: `self.iteration` serves triple duty (cap counter, `state_enter` payload, `LoopState` persistence field) with no cycle-boundary event; 80 YAML files need re-tuning; `-n 1` debugging idiom breaks. Reuse score: 1/3.
- Option 2: `max_edge_revisits` coexists as a second cap field in `schema.py:953`; `on_success`/`on_failure` alias at `schema.py:from_dict()` is the backwards-compat rename template; `canvas-sketch-generator.yaml:22-27` BUG-2011 comment confirms the magic-number pattern Option 2 eliminates. Reuse score: 2/3.
- Option 3: All deliverables are string edits or a single conditional print before `_helpers.py:1275`; doesn't prevent future authors from re-encoding the step-to-cycle offset as magic numbers. Reuse score: 3/3.

## Implementation Steps

1. Decide counting model (cycle vs step) — affects all existing loop YAML
   `max_iterations` values, so coordinate a migration if option 1.
2. Update `executor.py` increment/cap logic (`:403`, `:296`) and the
   `state_enter` / `max_iterations_summary` event payloads accordingly.
3. Update `ll-loop run --help` and loop-authoring docs.
4. Add a regression test asserting that a 1-cycle loop completes one full
   `initial → … → terminal` pass under the documented budget.

### Codebase Research Findings — Concrete File References

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Decide counting model**: consult `schema.py:951-953` for the three related fields (`max_iterations`, `on_max_iterations`, `max_edge_revisits`). `max_edge_revisits` (default 100) already serves as a runaway backstop under all options — retain it. Under Option 1, `FSMLoop` needs a new `cycle_count` field separate from the retained step counter.
2. **Update executor logic**: three increment sites must be updated consistently — `executor.py:403` (primary, every non-terminal state), `executor.py:355` (maintain-mode restart), `executor.py:1372` (flush path in `_flush_pending_shell_state`). Cap check at `executor.py:296`. Under Option 2, add a parallel `max_cycles` cap path alongside the existing `max_iterations` check.
3. **Update CLI and docs**:
   - `cli/loop/__init__.py:127` — update `help="Override iteration limit"` string; consider adding `--max-cycles` arg (Option 2)
   - `cli/loop/_helpers.py:29-37` — add a console message in the `"max_iterations"` exit branch (before `run_foreground()` returns at line 1275) to distinguish cap-before-terminal from other `exit 1` causes
   - `fsm-loop-schema.json:37-41` — update `max_iterations` description or add new field entries
   - `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/reference/loops.md` — update budgeting guidance
4. **Add regression test**: in `scripts/tests/test_fsm_executor.py`, model after `TestMaxIterationsSummaryHook` (line 7184). Assert that a 2-state cycle loop with `max_iterations=1` (cycle-based) runs all states in one cycle before capping. Update `test_max_iterations_respected` (line 159). Verify `test_cycle_detection_terminates_loop` (line 183) still passes. Also check `test_ll_loop_execution.py:test_exits_on_max_iterations` for CLI assertions.
5. **Persist cycle counter** (Option 1 only): update `persistence.py:190` `LoopState` dataclass to add `cycle_count: int = 0`; update `PersistentExecutor.resume()` at line 810 to restore it alongside `self._executor.iteration`.

## Status

- **State**: open
- **Discovered**: 2026-06-07 (smoke run of canvas-sketch-generator)

## Session Log
- `/ll:decide-issue` - 2026-06-08T00:32:10 - `f4c7bf77-d0d5-4c99-aeeb-85249c64bdfe.jsonl`
- `/ll:refine-issue` - 2026-06-08T00:18:43 - `828a4616-25c3-4af4-bb64-459468e94960.jsonl`
- `/ll:format-issue` - 2026-06-07T23:31:25 - `28dd97b0-82a8-4f71-a133-64fc6f2c6a75.jsonl`
- `/ll:capture-issue` - 2026-06-07T22:42:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/94001b17-192e-4675-8b12-449cc4ed8e69.jsonl`
