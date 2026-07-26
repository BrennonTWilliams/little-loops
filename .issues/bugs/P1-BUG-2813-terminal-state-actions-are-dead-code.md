---
id: BUG-2813
type: BUG
priority: P1
status: open
captured_at: '2026-07-25T22:08:07Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels: [fsm, loops, validator, executor]
relates_to: [ENH-2814]
---

# BUG-2813: ~40 terminal-state actions never execute (dead code) and no validator rule catches it

## Summary

The FSM executor finishes a run *before* running a terminal state's `action:`,
so every `action` on a `terminal: true` state is dead code. A corpus sweep found
**~40 terminal states carrying dead actions** (22 shell + 18 prompt), including
`recursive-refine::done` (6.5 KB) and `hitl-md::done` (1.9 KB). Only 2 terminal
actions in the corpus are live. Audit §1.1 /
`thoughts/builtin-loops-audit-2026-07-24.md`.

## Current Behavior

`fsm/executor.py:569-603`: on entering a `terminal: true` state the executor
returns `self._finish("terminal")` (`:603`) — or restarts under maintain mode —
**before** the action-execution path and step increment at `:632`. Verified
there is no other path that executes a plain terminal's action: the pending-state
flush guards exclude terminals (`:482`, `:540`), and the maintain-mode restart
(`:571-586`) reroutes *without* executing the action.

Sole exception (BUG-158, `:590-601`): a terminal doubling as the
`on_max_steps`/`on_max_iterations` handler executes its action once — keeping
exactly two states live: `cua-agent-desktop::max_steps_summary` (1,264 B) and
`vega-viz::max_steps_summary` (538 B).

**Largest dead shell actions:**

| State | Action size |
|---|---|
| `recursive-refine::done` | 6,467 B (also carries the MR-10 parse-swallow warning — on dead code) |
| `autodev::done` | 2,567 B |
| `loop-router::present_result` | 1,966 B |
| `goal-cluster::present_result` | 1,657 B |
| `loop-composer-adaptive::present_result` | 1,629 B |
| `rn-refine::finalize_aborted` | 1,547 B |
| `loop-composer::present_result` | 1,471 B |
| `apply-research::report` | 1,024 B |

**Additional shell terminals (14):** `rn-build::build_failed` (739 B),
`::abort_normalize` (304 B), `::failed` (292 B);
`auto-refine-and-implement::incomplete` (393 B);
`goal-cluster::failed`/`::abort_cluster` (284/270 B);
`loop-composer-adaptive::failed`/`::abort_composer` (258/252 B);
`loop-composer::failed` (229 B); `loop-router::failed` (196 B);
`apply-research::failed` (69 B);
`outer-loop-eval::handle_sub_loop_failed`/`::fail_missing_input`/`::handle_sub_loop_error` (78/75/67 B).

**Plus 18 prompt-action terminals**, largest: `hitl-md::done` (1,859 B — bigger
than five of the eight shell blocks above), `hitl-compare::done` (1,246 B),
`svg-textgrad::done` (914 B), `openscad-model-generator::done` (859 B),
`brainstorm::failed` (831 B), `oracles/research-coverage::done` (650 B), plus
done/failed terminals in vega-viz, html-anything,
interactive-component-generator, cli-anything-bootstrap,
canvas-sketch-generator, rn-plan, pixi-data-viz, generative-art,
pixi-generative-art, svg-image-generator, and
`workflow-generator::await_confirmation`.

No `lib/` fragment defines a terminal-with-action, so none of this arrives via
inheritance.

**Why the validator misses it:** `_validate_failure_terminal_action`
(`fsm/validation.py:1086-1131`) checks only that *failure-named* terminals have
a diagnostic **predecessor**. It never flags a non-empty action **on** a
terminal state, and ignores success-named terminals (`done`, `present_result`,
`report`) entirely. The needed rule is the exact complement of the one that
exists.

## Expected Behavior

- Every summary/artifact/cleanup block a loop author writes actually runs.
- Terminal states are bare; their work lives in a penultimate non-terminal state
  with `next: <terminal>` and `on_error` routing.
- `ll-loop validate` emits a finding for any non-empty `action` on a
  `terminal: true` state (exempting `on_max_steps`/`on_max_iterations` handler
  terminals, which are live per BUG-158).

## Root Cause

`fsm/executor.py:603` returns `_finish("terminal")` before the action-execution
path at `:632`. The pre-terminal `diagnose` convention introduced by the
BUG-1603/1606/1607 family (done 2026-05, documented in
`docs/generalized-fsm-loop.md` § Authoring Conventions) exists precisely because
of this behavior — but nothing enforces it, so inline terminal actions kept
being written.

## Proposed Solution

1. For each affected loop, move the terminal's action into a new penultimate
   non-terminal state with `next: <terminal>` and an `on_error:` route; leave
   the terminal bare.
2. Add the complementary validator rule in `fsm/validation.py`: flag any
   `terminal: true` state with a non-empty `action`, exempting states named as
   an `on_max_steps` / `on_max_iterations` handler.
3. The target shape is exactly `rn-implement::report` (non-terminal report state
   with `next:`/`on_error:`) — standardize on it.

## Integration Map

### Files to Modify
- ~25 loop YAMLs under `scripts/little_loops/loops/` (list above)
- `scripts/little_loops/fsm/validation.py` (new rule)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:569-603` (behavior being enforced — read-only)

### Similar Patterns
- `rn-implement::report` (`:1427`) — canonical non-terminal report state

### Tests
- `scripts/tests/test_builtin_loops.py` — assert no runnable loop has an action on a plain terminal
- Validator unit tests for the new rule, incl. the `on_max_steps` exemption

### Documentation
- `docs/generalized-fsm-loop.md` § Authoring Conventions — state the rule and the enforcement
- `.claude/CLAUDE.md` § Loop Authoring rule table — add the new rule row

### Configuration
- Suppression flag name for the new rule (follow existing `*_ok` convention)

## Implementation Steps

1. Add the validator rule first (fails loudly across the corpus).
2. Migrate loops in batches, largest actions first (`recursive-refine`,
   `autodev`, `loop-router`, `goal-cluster`, both composers, `rn-refine`,
   `apply-research`).
3. Migrate the 14 small shell terminals and 18 prompt terminals.
4. Re-run `ll-loop validate` corpus-wide → clean.
5. Note: `recursive-refine::done`'s MR-10 parse-swallow warning becomes live once
   its action executes — fix the `on_error:` route in the same change.

## Impact

- **Severity**: High — whatever summary, artifact, or cleanup these blocks were
  written to produce **has never happened on any run**.
- Failure-named terminals (`rn-build::failed`, `goal-cluster::failed`, …) lose
  precisely the diagnostics the BUG-1603 family added the convention to
  guarantee.
- Compounds BUG-2814: a loop that fails cleanly exits 0, is archived as
  `"completed"`, *and* emits no diagnostic.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `thoughts/builtin-loops-audit-2026-07-24.md` §1.1, rec #2 | Source finding, full state inventory |
| `docs/generalized-fsm-loop.md` § Authoring Conventions | The convention this enforces |
| BUG-1603 / BUG-1606 / BUG-1607 (done 2026-05) | Prior art establishing the convention |

## Steps to Reproduce

1. Pick any loop with a terminal action, e.g. `recursive-refine::done` (6.5 KB
   shell block writing a summary).
2. Run the loop to completion.
3. Observe the action's side effects (files written, summary emitted) are absent
   — the run ends the moment the terminal is entered.
4. Confirm structurally: parse every runnable YAML for states with
   `terminal: true` **and** a non-empty `action`; ~40 match, and only the two
   `max_steps_summary` states (`cua-agent-desktop`, `vega-viz`) are reachable as
   `on_max_steps` handlers.
5. Confirm in source: `fsm/executor.py:603` returns `_finish("terminal")` before
   the action path at `:632`.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-26T00:54:33 - `1286c2b1-65d4-4230-b501-25c3ae70b53c.jsonl`
- `/ll:capture-issue` - 2026-07-25T22:08:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a36a68e-d365-4ea1-9394-a9e5904b5739.jsonl`

---

## Status

- **Current**: open
