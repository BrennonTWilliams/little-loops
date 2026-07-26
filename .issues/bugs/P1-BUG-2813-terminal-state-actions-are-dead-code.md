---
id: BUG-2813
type: BUG
priority: P1
status: done
captured_at: '2026-07-25T22:08:07Z'
completed_at: '2026-07-26T03:13:45Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels:
- fsm
- loops
- validator
- executor
relates_to:
- ENH-2814
confidence_score: 100
outcome_confidence: 80
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 20
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
- `scripts/little_loops/fsm/schema.py` (new `terminal_action_ok` field)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — hand-maintained JSON Schema (not
  auto-generated from `FSMLoop`); needs a new `terminal_action_ok` boolean property
  entry near the existing `pruning_profile_ok` entry (~line 358-362), following that
  entry's `type: boolean` / `default: false` / description shape. Will silently drift
  if not updated in lockstep with `schema.py`. [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:569-603` (behavior being enforced — read-only)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/edit_routes.py` — imports `load_and_validate`;
  `ll-loop edit-routes` surfaces validator findings, will start surfacing the new
  rule once wired [Agent 1 finding]
- `scripts/little_loops/cli/doctor.py` — imports validation functions for
  `ll-doctor`'s default loop-validity check; will start surfacing the new rule
  corpus-wide once loops are migrated [Agent 1 finding]

### Similar Patterns
- `rn-implement::report` (`:1427`) — canonical non-terminal report state

### Tests
- `scripts/tests/test_builtin_loops.py` — assert no runnable loop has an action on a plain terminal
- Validator unit tests for the new rule, incl. the `on_max_steps` exemption

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_validation.py` — new `TestTerminalActionOk` class mirroring
  the 5-test `TestBashDefaultInterpolation` skeleton (`:3555-3623`): fires_for_X,
  does_not_fire_for_Y, suppressed_by_terminal_action_ok, wired_into_validate_fsm,
  terminal_action_ok_recognized_as_top_level_key — plus an exemption-specific test
  modeled on `test_on_max_iterations_valid_state_passes` (`:1895-1947`) [Agent 3
  finding]
- `scripts/tests/test_fsm_schema.py` — new round-trip test pair (default-omitted-
  from-`to_dict()` + from_dict round-trip) for the `terminal_action_ok` field,
  following the repeating per-flag pattern at `:3372/3410/3448/3715/3753/3791`
  (`bash_default_ok`, `generator_fix_ok`, `unsafe_context_interpolation_ok`, etc.)
  [Agent 2 + Agent 3 finding]
- At-risk, verify post-migration (survive only if terminal state **names** are
  preserved during migration — none currently assert action-absence, only
  `terminal`/`next`): `scripts/tests/test_loop_router.py::test_present_result_is_terminal`
  / `::test_failed_is_terminal`, `scripts/tests/test_rn_implement.py::test_failed_state_is_terminal`
  / `::test_done_state_is_terminal`, `scripts/tests/test_goal_cluster.py::test_present_result_is_terminal`
  / `::test_failed_is_terminal` [Agent 3 finding]
- Once `terminal_action_ok` is wired into `validate_fsm()`, any of the ~25 loops'
  existing "no MR-1/validation-error" assertions (e.g. `test_goal_cluster.py:103`,
  `test_rn_refine.py:57-62`) will fail until that loop's migration lands — sequence
  validator-rule PR after (or atomically with) the loop migrations, not before, for
  loops with such assertions [Agent 3 finding]

### Documentation
- `docs/generalized-fsm-loop.md` § Authoring Conventions — state the rule and the enforcement
- `.claude/CLAUDE.md` § Loop Authoring rule table — add the new rule row

_Wiring pass added by `/ll:wire-issue`:_
- The MR rule table is copy-maintained (not templated) across **four more files**
  beyond `.claude/CLAUDE.md`, each needing an independent new-rule entry or they'll
  drift stale [Agent 2 finding]:
  - `docs/reference/CLI.md` (`ll-loop validate` section, ~line 731-754) — full prose
    bullet per rule plus a suppression-flag summary sentence at ~line 749
  - `docs/reference/API.md` (~line 5609-5614) — same rule bullets, plus a separate
    `FSMLoop` dataclass field-comment listing (~line 4919-4924) documenting each
    suppression flag as a Python-style comment
  - `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` § "The Design Rules (MR-1…MR-12)"
    (table at ~line 92) — the canonical table `.claude/CLAUDE.md` points to; the
    section heading (~line 85) and TOC entry (~line 26) hardcode the rule count
    range in the heading text and will go stale
  - `skills/review-loop/reference.md` (~line 45-50) — a third independent MR-table
    copy used by the `review-loop` skill

### Configuration
- Suppression flag name for the new rule (follow existing `*_ok` convention)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Executor exact anchors** (line numbers refined from research vs. the issue's
  original `:569-603`/`:632`): the general-case short-circuit is
  `return self._finish("terminal")` at `fsm/executor.py:605` (inside
  `if state_config.terminal:` at `:571`); the BUG-158 fallthrough exception for
  `on_max_steps`/`on_max_iterations` handler terminals lives at `:589-603`
  (guarded by `self._summary_state_executed`/`self._iteration_summary_executed`);
  the unreached action/step-increment path begins at `self.iteration += 1`
  around `:634`. `_finish` itself is defined at `:2819`.
- **New rule's three required wiring touch points** (all needed, not just the
  function body):
  1. Declare `terminal_action_ok: bool` as an `FSMLoop` dataclass field in
     `fsm/schema.py` (alongside `on_max_steps`/`on_max_iterations` at
     `:1182-1185`), with matching `from_dict()`/`to_dict()` entries
     (pattern at `:1277-1280`, `:1419-1421`).
  2. Add the flag name to the `KNOWN_TOP_LEVEL_KEYS` frozenset in
     `fsm/validation.py:214-266` — omitting this produces a spurious
     "Unknown top-level key" warning (existing per-flag test:
     `test_bash_default_ok_recognized_as_top_level_key` pattern in
     `test_fsm_validation.py`).
  3. Guard the rule function body with `if fsm.terminal_action_ok: return []`
     as its first line (pattern: `_validate_bash_default_interpolation`,
     `fsm/validation.py:1868`), and append the new rule's call to the flat
     `errors.extend(...)` sequence inside `validate_fsm()` (`:1296-1315`).
- **Exemption set construction**: build
  `{fsm.on_max_steps, fsm.on_max_iterations} - {None}` and skip terminal
  states whose name is in that set — mirrors how
  `_validate_failure_terminal_action` builds `FAILURE_TERMINAL_NAMES` before
  iterating `fsm.get_terminal_states()` (`fsm/schema.py:1470`).
- **Test class to model after**: `TestBashDefaultInterpolation` in
  `test_fsm_validation.py:3555-3619` — a 5-test skeleton (`fires_for_X`,
  `does_not_fire_for_Y`, `suppressed_by_<flag>_ok`, `wired_into_validate_fsm`,
  `<flag>_ok_recognized_as_top_level_key`). Add a parallel
  `test_does_not_fire_for_on_max_steps_terminal` exercising the exemption path
  (construct an `FSMLoop` with `on_max_steps="capped"` and a terminal state
  named `capped` carrying a non-empty `action`, assert no finding). Alternate
  reference: `TestGeneratorFixDiscipline` (MR-6) nearby, same 4/5-test shape.
- **Existing test coverage already partially exists** in
  `test_builtin_loops.py`: `test_all_failure_terminals_have_diagnostic_action`
  (`:258`) and `test_terminal_routing_states_write_sidecar` (`:363`) — the new
  corpus-wide "no runnable loop has an action on a plain terminal" assertion
  should live alongside these, not as a wholly new test module.
- **CLI entry point for `ll-loop validate`**: dispatches through
  `cmd_validate()` in `scripts/little_loops/cli/loop/config_cmds.py`, which
  imports `load_and_validate` from `fsm/validation.py`; no changes needed there
  beyond the new rule being included in `validate_fsm()`'s existing sequence.

## Implementation Steps

1. Add the validator rule first (fails loudly across the corpus).
2. Migrate loops in batches, largest actions first (`recursive-refine`,
   `autodev`, `loop-router`, `goal-cluster`, both composers, `rn-refine`,
   `apply-research`).
3. Migrate the 14 small shell terminals and 18 prompt terminals.
4. Re-run `ll-loop validate` corpus-wide → clean.
5. Note: `recursive-refine::done`'s MR-10 parse-swallow warning becomes live once
   its action executes — fix the `on_error:` route in the same change.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add `terminal_action_ok` boolean property to `scripts/little_loops/fsm/fsm-loop-schema.json`
   in lockstep with the `schema.py` field (hand-maintained, not auto-generated).
7. Sequence the validator-rule change relative to loop migrations so existing
   "no MR-1/validation-error" assertions (`test_goal_cluster.py:103`,
   `test_rn_refine.py:57-62`, etc.) don't fail mid-migration.
8. Update all four additional MR-table doc copies (`docs/reference/CLI.md`,
   `docs/reference/API.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` incl. its
   heading/TOC rule-count text, `skills/review-loop/reference.md`) alongside
   `.claude/CLAUDE.md`.
9. Add `test_fsm_schema.py` round-trip tests and `test_fsm_validation.py`
   `TestTerminalActionOk` class per the Tests section above.
10. Verify the post-migration at-risk tests (`test_loop_router.py`,
    `test_rn_implement.py`, `test_goal_cluster.py` terminal-name assertions) still
    pass once terminal states are emptied of `action`.

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

## Resolution

Added a new validator rule (`terminal_action_ok` suppression flag) that flags
any `terminal: true` state with a non-empty `action`, exempting
`on_max_steps`/`on_max_iterations` handler terminals. Migrated all 29 affected
loop YAMLs (44 terminal states) so each dead action moved to a new penultimate
non-terminal state (`finalize_<terminal>` / `record_<terminal>`) with
`next: <terminal>` and an `on_error:` route, following the canonical
`rn-implement::report` shape. All predecessor routing (`next`/`on_yes`/`on_no`/
`on_error`/`route`) was rewired to the new states. Schema (`schema.py`,
`fsm-loop-schema.json`) and five doc copies of the MR rule table were updated
in lockstep. Full suite: 16311 passed, 38 skipped.

## Session Log
- `/ll:manage-issue` - 2026-07-26T03:13:21Z - see current session JSONL
- `/ll:confidence-check` - 2026-07-26T02:30:59Z - `59382d24-5a11-4269-860f-2b6e7efd95ca.jsonl`
- `/ll:wire-issue` - 2026-07-26T02:29:37 - `9574bbe4-63ee-467d-9881-186c13321b22.jsonl`
- `/ll:refine-issue` - 2026-07-26T02:23:45 - `dd08cadb-b03e-41b2-8ba4-6362df15c841.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-26T00:54:33 - `1286c2b1-65d4-4230-b501-25c3ae70b53c.jsonl`
- `/ll:capture-issue` - 2026-07-25T22:08:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a36a68e-d365-4ea1-9394-a9e5904b5739.jsonl`

---

## Status

- **Current**: open
