---
id: BUG-2011
type: BUG
priority: P2
status: open
captured_at: '2026-06-07T22:42:29Z'
discovered_date: 2026-06-07
discovered_by: capture-issue
labels:
- fsm
- loop-runner
- dx
- footgun
decision_needed: false
confidence_score: 100
outcome_confidence: 56
decomposed_into:
- BUG-2204
- BUG-2205
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 0
---

# BUG-2011: FSM max_iterations counts steps, not loop iterations

## Summary

The FSM loop runner's `max_iterations` / `--max-iterations` (`-n`) caps the
number of **steps** (individual state executions), but the name strongly implies
a full loop **iteration** (e.g. one complete `generate → evaluate → score →
refine` pass back to initial). Loop authors and CLI users expect `max_iterations`
to cap full loop iterations, under-budget the cap, and get **silent premature
termination** that looks like a loop defect rather than an exhausted budget.

## Current Behavior

Each step (state execution) increments the counter once. `ll-loop run <loop> -n 2`
therefore allows only two *steps* to execute, not two full *iterations*.

Observed during a smoke run of `canvas-sketch-generator` with `-n 2`:

- `init` executed (counter → 1)
- `plan` executed (counter → 2), `usage.jsonl` recorded
  `{"iteration": 2, "state": "plan"}`
- the cap fired before `generate` ever ran
- the run ended without reaching a terminal state and exited `1`

The user expected `-n 2` to permit ~2 full generate/score iterations.

## Expected Behavior

Either:
- `max_iterations` counts **iterations** (returns to the initial state, or
  completions of a designated anchor state), matching the intuitive reading; or
- the per-step semantics are made explicit (clear name + docs) so authors
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

- **`executor.py:403`** — `self.iteration += 1` runs once per step (state
  execution), right before each `state_enter` emit.
- **`executor.py:296`** — `if self.iteration >= self.fsm.max_iterations:` gates
  on that per-step counter.

So `max_iterations` is a cap on total steps. There is no separate notion of an
"iteration" (full loop pass back to initial) anywhere in the increment/cap path.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Three increment sites** (not one): `executor.py:403` (primary, before every non-terminal `state_enter`), `executor.py:355` (maintain-mode restart — fires when `self.fsm.maintain=True` and the FSM reaches a terminal state, then routes back to `initial`), and `executor.py:1372` (flush path in `_flush_pending_shell_state`, emits `state_enter` with `"flushed": True`). Option 1 (iteration-based counting) must update all three sites consistently.
- **`max_edge_revisits`** (`schema.py:953`, default 100) is the existing separate runaway backstop — fires `terminated_by="cycle_detected"` when any single directed edge (`from→to`) is traversed more than 100 times. This is tracked via `self._edge_revisit_counts` at `executor.py:462-481`. It is distinct from `max_iterations` and must be retained under any option.
- **`on_max_steps`** (will be renamed from `on_max_iterations`, `schema.py:952`, default `None`) — allows a loop YAML to declare a summary state that executes when the step cap fires (path A in the cap check at `executor.py:296-306`). Loops without it get bare `exit 1` with no console message. This is the "silent termination" gap; `on_max_steps` is the existing partial fix for loops that set it.
- **Maintain mode** (`self.fsm.maintain`) is the closest existing "iteration" concept — on terminal, routes back to `initial`. But `self.iteration` still increments once per step during maintain restarts (line 355). There is no "back to initial" iteration counter anywhere.
- **Default**: `max_iterations=50` steps (to be renamed `max_steps=50`). 81+ loop YAML files declare `max_iterations`; many use values like 20 to obtain ~5–6 real refine iterations, encoding the confusion as a magic-number offset. `canvas-sketch-generator.yaml:22` already has an explicit comment referencing BUG-2011.
- **Exit code**: `_helpers.py:29-37` `EXIT_CODES` maps `"max_iterations" → 1` (same as `timeout`, `cycle_detected`, `stall_detected`). No console message currently distinguishes cap-before-terminal from other `exit 1` causes.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor.run()` increment
  (`self.iteration += 1`, `:403`) and cap check
  (`self.iteration >= self.fsm.max_iterations`, `:296`); the `state_enter` and
  `max_iterations_summary` event payloads.

### Codebase Research Findings — Additional Files to Modify

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/schema.py` — `FSMLoop` dataclass: `max_iterations: int = 50` (line 951), `on_max_iterations: str | None = None` (line 952), `max_edge_revisits: int = 100` (line 953). Serialization guard (lines 992-993 only writes `max_iterations` when != 50). Deserialization at line 1081. Under Option 2: rename `max_iterations` → `max_steps` (step cap, default 50) and `on_max_iterations` → `on_max_steps`; add `max_iterations: int | None = None` (iteration cap, new) and `on_max_iterations: str | None = None` (iteration-cap summary state); use `from_dict()` alias to read legacy YAML key `max_iterations` → `max_steps` for backwards compat.
- `scripts/little_loops/cli/loop/_helpers.py` — `EXIT_CODES` dict (lines 29-37): `"max_iterations": 1`; `run_foreground()` return at line 1275. To surface a clearer "cap hit before terminal state" message, add console output here before returning exit code 1.
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON schema definition for `max_iterations` (lines 37-41, description "Safety limit for loop iterations"). Must be updated if field is renamed or new fields are added (Option 2).

### Wiring Pass — Additional Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation.py` — `known_top_level_keys` set at line 131 includes `max_iterations`; `_validate_numeric_fields()` at line 936 asserts `max_iterations > 0`; `_validate_on_max_iterations()` at line 1470 checks the named summary state exists. Under Option 2: add `max_steps` and `max_iterations` to `known_top_level_keys`; add `max_steps > 0` range check in `_validate_numeric_fields()`; rename `_validate_on_max_iterations()` to `_validate_on_max_steps()` and add a new `_validate_on_max_iterations()` for the iteration-cap summary state if `on_max_iterations` is added.
- `scripts/little_loops/cli/loop/_helpers.py:949,516,657` — beyond `EXIT_CODES` (lines 29-37) and `run_foreground()` (line 1275), also: `print(f"Max iterations: {fsm.max_iterations}")` at line 949 (header display, tested by `TestLoopInfo.test_metadata_shown`); pinned-pane counter `f"[{self.current_iteration[0]}/{self.fsm.max_iterations}]"` at lines 516 and 657. Update these to show `max_steps` (the step cap) and `max_iterations` (the iteration cap) when set.
- `scripts/little_loops/generate_schemas.py:397-399` — generates `max_iterations_summary` and other event schemas from Python dataclasses. If `state_enter` event gains an `iteration_count` field, re-run this tool after `executor.py`/`schema.py` changes to regenerate `docs/reference/schemas/state_enter.json`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/*.yaml` — every loop declaring `max_iterations`
  (e.g. visual loops at `max_iterations: 20`) — existing values are read as
  `max_steps` via `from_dict()` alias with no YAML migration required.
- `ll-loop run` CLI (`--max-iterations` / `-n`) — rename to `--max-steps`/`-n`
  (step cap); add `--max-iterations` for the new iteration cap; update help text
  and termination-reason surfacing when the cap fires before a terminal state.

### Codebase Research Findings — Additional Dependent Files

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/loop/__init__.py:127` — argparse: `run_parser.add_argument("--max-iterations", "-n", type=int, help="Override iteration limit")`. Rename to `--max-steps`/`-n` (step cap); add `--max-iterations` as the new iteration-cap flag. Same changes apply to `simulate` subcommand at line 468.
- `scripts/little_loops/cli/loop/run.py:118-119` — applies CLI override: `if args.max_iterations: fsm.max_iterations = args.max_iterations`. Update to route `--max-steps` → `fsm.max_steps` and `--max-iterations` → `fsm.max_iterations` (iteration cap).
- `scripts/little_loops/fsm/persistence.py:190,810` — `LoopState.iteration: int` persists the per-step counter; `PersistentExecutor.resume()` restores it via `self._executor.iteration = state.iteration` at line 810. Under Option 2, add `iteration_count: int = 0` to `LoopState` and restore alongside `self._executor.iteration`.

### Wiring Pass 4 — Additional Files (2026-06-17)

_Added by `/ll:refine-issue` — new touchpoints not captured in prior wiring passes:_

- `scripts/little_loops/fsm/types.py:24,34` — `ExecutionResult` docstring enumerates `terminated_by` reason strings: `"terminal", "max_iterations", "timeout", "signal", "error", "handoff", "cycle_detected"`. Under Option 2, `"max_iterations"` as a reason string is replaced by `"max_steps"` (step cap) and `"max_iterations_reached"` (iteration cap). Update both the one-line attribute docstring (line 24) and the inline comment (line 34).
- `scripts/tests/helpers.py:56,73` — Test helper `FSMLoop(max_iterations=max_iterations)` passes `max_iterations` as a step cap today (same pattern as `test_cli.py` in step 27). Under Option 2, the Python field `FSMLoop.max_iterations` becomes the iteration cap; step cap is `FSMLoop.max_steps`. Rename parameter `max_iterations: int = 50` → `max_steps: int = 50` (line 56) and update constructor call at line 73 to `FSMLoop(max_steps=max_steps)`.

### Wiring Pass — Additional Dependent Files (Callers/Consumers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py:999` — `_format_loop_config_line()` builds `f"max: {fsm.max_iterations} iter"` and reads `fsm.on_max_iterations` at lines 1001-1002. Update to display `max_steps` (step cap) and `max_iterations` (iteration cap) when set.
- `scripts/little_loops/cli/loop/testing.py:203-211` — `cmd_simulate()` reads and mutates `fsm.max_iterations` directly; informational log string `f"max_iterations: {fsm.max_iterations}"` at line 209. Under Option 2, update to `fsm.max_steps` for the step cap and add parallel `fsm.max_iterations` handling for `--max-iterations` (iteration cap).
- `scripts/little_loops/cli/loop/config_cmds.py:25` — `cmd_config_show()` prints `f"  Max iterations: {fsm.max_iterations}"`. Update to print `max_steps` and `max_iterations` when set.
- `scripts/little_loops/cli/loop/next_loop.py:308` — `cmd_next_loop()` constructs `argparse.Namespace(max_iterations=None, …)` for `cmd_run`. Rename to `max_steps=None`; add `max_iterations=None` for the iteration-cap flag.
- `scripts/little_loops/cli/loop/_helpers.py:1033` — `_build_background_cmd()` appends `["--max-iterations", str(max_iter)]` to subprocess command. Rename to `["--max-steps", ...]`; add parallel forwarding for `["--max-iterations", ...]` (iteration cap).
- `scripts/little_loops/cli/loop/_helpers.py:1168` — `run_foreground()` prints `f"Max iterations: {colorize(str(fsm.max_iterations), '2')}"`. Update to display `Max steps:` and `Max iterations:` separately when set.
- `skills/review-loop/reference.md` — `QC-1` check reads `max_iterations` from the YAML dict by key name; SIM-1/SIM-2/SIM-3 checks parse `"Terminated by: max_iterations"` from `ll-loop simulate` stdout; exit-code table references the `"max_iterations"` string key. These are executable skill parsing targets — update if the displayed termination string changes.
- `skills/audit-loop-run/SKILL.md:168` — `partial` verdict rule checks `terminated_by == "max_iterations"` AND `max_iterations_summary` event present in JSONL. Update if the termination reason string or event type name changes.

### Wiring Pass 3 — Additional Dependent Files (2026-06-13)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/vega-viz.yaml:33` — **3rd loop YAML using `on_max_iterations:`** (`on_max_iterations: max_iterations_summary`); requires explicit migration to `on_max_steps: max_iterations_summary` for the same reason as `general-task.yaml` and `canvas-sketch-generator.yaml` — the alias cannot cover it because the new Python field `on_max_iterations` is the iteration-cap summary state. Counts as 3 total explicit migrations, not 2 as previously stated in the issue.
- `scripts/little_loops/loops/lib/task-templates/data-lib-task.yaml.tmpl:15` — `max_iterations: 5`; runtime-safe via `from_dict()` alias but documents old key; update to `max_steps: 5` so template-generated loops use new terminology.
- `scripts/little_loops/loops/lib/task-templates/stateful-service-task.yaml.tmpl:14` — `max_iterations: 8`; same; update to `max_steps: 8`.
- `scripts/little_loops/loops/lib/task-templates/desktop-gui-task.yaml.tmpl:14` — `max_iterations: 8`; same; update to `max_steps: 8`.
- `skills/review-loop/SKILL.md:215-226` — contains its own copy of SIM-1/SIM-2/SIM-3 patterns and `"Terminated by: max_iterations"` string matching separate from `skills/review-loop/reference.md` (already in the issue); update `"Terminated by: max_iterations"` → `"Terminated by: max_steps"` here independently.
- `skills/cleanup-loops/SKILL.md:343` — `terminated_by` value enumeration (`"Any terminated_by values in loop_complete events"`); update example values if `"max_iterations"` → `"max_steps"` as a termination string.
- `skills/create-eval-from-issues/SKILL.md:253,293` — `max_iterations: 5` and `max_iterations: 50` in inline YAML examples; update to `max_steps:` so generated eval loops use new terminology.
- `skills/workflow-automation-proposer/SKILL.md:144` — `max_iterations: 10` in inline YAML example; update to `max_steps: 10`.
- `skills/verify-issue-loop/SKILL.md:154` — `max_iterations: 20` in inline YAML; update to `max_steps: 20`.
- `docs/reference/COMMANDS.md:820,828` — `max_iterations` in `ll-loop calibrate-budget` description ("increasing `max_iterations` will improve outcomes"); update to `max_steps` / `max_iterations` (iteration-cap) terminology (separate from lines 646-673 already noted in the issue).

### Similar Patterns
- Any other budget/limit counter in the executor (runaway step backstop) —
  keep increment semantics consistent if a step ceiling is retained.

### Tests

### Codebase Research Findings — Specific Test Files and Functions

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_fsm_executor.py` — primary file:
  - `test_max_iterations_respected` (line 159) — existing test validates per-step cap with `max_iterations=3`; rename to `test_max_steps_respected` and update to use `max_steps=3`; add sibling `test_max_iterations_respected` asserting iteration-based semantics.
  - `TestMaxIterationsSummaryHook` class (lines 7184-7215) — covers `on_max_iterations` behavior (step cap); rename to `TestMaxStepsSummaryHook`; model new `TestMaxIterationsSummaryHook` after it for the iteration cap.
  - `test_cycle_detection_terminates_loop` (line 183) — covers `max_edge_revisits` backstop; verify it still passes after executor changes.
  - `test_fix_retry_loop` — demonstrates `result.iterations == 3` for a 2-step `check→fix→check→done` sequence; will need updating when `result.iterations` semantics change to full-loop count.
- `scripts/tests/test_ll_loop_execution.py` — `test_exits_on_max_iterations` exercises CLI end-to-end; update for `--max-steps` flag rename and new message text.
- `scripts/tests/test_fsm_persistence.py` — `test_final_status_interrupted_on_max_iterations` covers persistence layer; update when `LoopState` gains `iteration_count` field.
- **New regression to add**: a multi-state loop with N steps per iteration and `max_iterations=1` should execute all N steps in the first iteration before terminating — not stop after 1 step.

### Wiring Pass — Additional Tests

_Wiring pass added by `/ll:wire-issue`:_

**Tests that may BREAK (assert on step-count semantics):**
- `scripts/tests/test_fsm_executor.py` — 11 `result.iterations == N` assertions across `test_simple_success_path` (line 124), `test_fix_retry_loop` (line 156), `test_max_iterations_respected` (line 180), `test_unconditional_next_transition` (line 227), `test_no_action_state` (line 267), `test_on_fail_retry_reaches_max` (~line 1210), `TestMaintainMode.test_maintain_hits_max_iterations` (~line 1563), multiple convergence/signal tests. These will need to change to `result.steps == N` once `result.iterations` means full-loop iteration count. Also `TestMaxIterationsSummaryHook.test_max_iterations_summary_event_emitted` at line 7184 asserts `evt["iterations"] == 3` (step-count payload field).
- `scripts/tests/test_ll_loop_execution.py` — `test_exits_on_max_iterations` at lines 137 and 142: `mock_popen.call_count == 2` and `"Max iterations: 2" in captured.out`; update to `--max-steps` flag and `"Max steps: 2"` message. `test_runs_with_header` at line 97: `"Max iterations: 3" in captured.out` → `"Max steps: 3"`.
- `scripts/tests/test_ll_loop_display.py` — `TestLoopInfo.test_metadata_shown` at line 497: `"Max iterations: 25" in captured.out` → `"Max steps: 25"`; `TestRunForegroundExitCodes.test_exit_codes_dict_matches_expected_mapping` at line 2715: `EXIT_CODES["max_iterations"] == 1` → update key if termination string changes; `test_show_header_with_metadata` at line 628.
- `scripts/tests/test_ll_loop_commands.py` — `data[0]["iteration"] == 3` at line 1577; `data["iteration"] == 5` at line 3040 (asserts on `LoopState.iteration` / step-counter value in `.state.json`) → update to `data["step"]` or equivalent.
- `scripts/tests/test_ll_loop_state.py` — `resume_event["iteration"] == 2` at line 355 (asserts on `state_enter` event payload step-counter field) → update to `resume_event["step"] == 2`.

**Tests to UPDATE:**
- `scripts/tests/test_fsm_schema.py` — `test_max_iterations_zero_rejected` (line 1472) and `test_max_iterations_negative_rejected` (line 1488) assert on string `"max_iterations must be > 0"`; rename to `test_max_steps_*` and update error message. `test_roundtrip_serialization` (line 795) covers `max_iterations` roundtrip; add `max_steps` and `max_iterations` (iteration cap) siblings.
- `scripts/tests/test_ll_loop_integration.py` — `test_run_with_max_iterations_shows_in_plan` at line 91 asserts plan output contains `max_iterations` value; update to `max_steps` header.
- `scripts/tests/test_ll_loop_parsing.py` — `test_run_with_max_iterations` at line 95 asserts `args.max_iterations == 10`; rename to `test_run_with_max_steps` and update argparse dest.

**New tests to WRITE (no existing coverage for `max_iterations` iteration cap):**
- `scripts/tests/test_fsm_schema.py` — add `TestFSMLoopMaxIterations` class modeled after `TestFSMLoopArtifactVersioning` (line 3282): default `None`, `from_dict()` parses, `to_dict()` omits when None, roundtrip. Also test that legacy YAML `max_iterations` key → `max_steps` via `from_dict()` alias.
- `scripts/tests/test_fsm_validation.py` — add `TestMaxIterationsValidation` class modeled after `TestOnMaxIterationsValidation` (line 1421): `test_max_iterations_recognized_as_top_level_key` (YAML with `max_iterations:` as iteration cap produces no "Unknown-top-level" warning), `test_max_iterations_must_be_positive`; add `TestMaxStepsValidation` for `max_steps`.
- `scripts/tests/test_cli_loop_dispatch.py` — rename existing `test_max_iterations_forwarded` (line 533) to `test_max_steps_forwarded`; add new `test_max_iterations_forwarded` for the iteration-cap flag. Same for `test_simulate_max_iterations_forwarded` (line 818).
- `scripts/tests/test_ll_loop_display.py` — add test for `max_iterations` (iteration cap) and `max_steps` (step cap) display in header when set.

### Wiring Pass 2 — Additional Tests (2026-06-07)

_Wiring pass added by `/ll:wire-issue`:_

**Tests to UPDATE (string literals that break on rename):**
- `scripts/tests/test_state_feed_renderer.py:test_max_iterations_summary` (line ~244) — hardcoded `"max_iterations_summary"` event string sent to `EventFeedRenderer.handle_event()`; update to `"max_steps_summary"` in tandem with the `render_event()` dispatch update.
- `scripts/tests/test_general_task_loop.py:TestENH1631SummarizePartial.test_on_max_iterations_set_to_summarize_partial` (line 1073) — asserts `raw_data.get("on_max_iterations") == "summarize_partial"`; rename test to `test_on_max_steps_set_to_summarize_partial` and update key to `"on_max_steps"` after `general-task.yaml` is updated.
- `scripts/tests/test_generate_schemas.py` (line 60, `expected` set) — `"max_iterations_summary"` in the set of expected `SCHEMA_DEFINITIONS` keys; update to `"max_steps_summary"` and add `"max_iterations_reached_summary"`.
- `scripts/tests/test_cli_loop_lifecycle.py` (lines 493, 978) — `mock_result.terminated_by = "max_iterations"` (line 493); `@pytest.mark.parametrize("terminated_by", ["max_iterations", "timeout"])` (line 978). Update `"max_iterations"` → `"max_steps"` (step-cap termination reason string).
- `scripts/tests/test_review_loop.py` (lines 1024, 1058, 1074) — string searches for `"max_iterations"` and `"terminated_by_max"` pattern; update to `"max_steps"`.

**New tests to WRITE:**
- `scripts/tests/test_session_store.py` — add test class (model after `test_ignores_unrecognized_event` at line 230) that imports `_LOOP_EVENT_TYPES` from `little_loops.session_store` and asserts: (a) `"max_steps_summary"` is a member (post-rename); (b) `"max_iterations_reached_summary"` is a member (new iteration-cap event); (c) stable members (`"loop_start"`, `"loop_complete"`, `"state_enter"`) remain present.
- `scripts/tests/test_canvas_sketch_generator.py` (does not exist — new file) — following the `TestENH1631SummarizePartial` pattern from `test_general_task_loop.py`: load `canvas-sketch-generator.yaml`, assert `raw_data.get("on_max_steps") == "finalize"` (post-rename), assert `ll-loop validate canvas-sketch-generator` passes with no new errors.

### Wiring Pass 3 — Additional Tests (2026-06-13)

_Wiring pass added by `/ll:wire-issue`:_

**Tests that BREAK on CLI argparse dest rename (`max_iterations` → `max_steps`):**
- `scripts/tests/test_cli_loop_testing.py` — `TestCmdSimulateMaxIterations.test_max_iterations_applied` (line ~202): uses `_make_args(max_iterations=3)` and verifies `cmd_simulate()` respects the cap; `_make_args()` at line 63 sets `"max_iterations": None` in `argparse.Namespace`; rename to `max_steps` throughout and add `max_iterations=None` for the iteration-cap flag.
- `scripts/tests/test_cli_loop_background.py:210` — `test_forwards_max_iterations` explicitly asserts `--max-iterations` flag is forwarded in the background subprocess command; rename to `test_forwards_max_steps` and update the flag assertion.
- `scripts/tests/test_cli_loop_queue.py` — `argparse.Namespace(max_iterations=None)` in fixtures; rename to `max_steps=None`; add `max_iterations=None` for iteration-cap flag.
- `scripts/tests/test_cli_loop_worktree.py` — `argparse.Namespace(max_iterations=None)` in fixtures; same rename.
- `scripts/tests/test_ll_loop_program_md.py:150` — `max_iterations=None` in argparse defaults fixture; rename to `max_steps=None`.
- `scripts/tests/test_cross_host_baseline.py:132,246,308` — `argparse.Namespace(max_iterations=None)` in fixtures; rename to `max_steps=None`.

**Tests that BREAK due to `FSMLoop(max_iterations=N)` Python constructor semantics shift:**
- `scripts/tests/test_cli.py` — multiple `FSMLoop(max_iterations=50)` constructor calls used as step-cap (e.g. `test_max_iterations_override`); under Option 2 `max_iterations=N` sets the iteration cap (new field), not the step cap — update to `FSMLoop(max_steps=50)`.
- `scripts/tests/test_fsm_schema_fuzz.py:264-268` — Hypothesis strategy sets `fsm["max_iterations"]` via dict; `from_dict()` aliases this to `max_steps` (step cap), so no semantic shift for dict-based construction — but verify direct `FSMLoop(max_iterations=...)` constructor calls in the same file.

**Tests that BREAK when generated/template YAML output switches from `max_iterations:` to `max_steps:` (coordinate with step 19):**
- `scripts/tests/test_create_loop.py` — inline YAML fixture strings asserting `max_iterations: 50`; update to `max_steps: 50` once template generation changes.
- `scripts/tests/test_loop_suggester.py:354-640` — multiple inline YAML fixtures with `max_iterations:`; update to `max_steps:` in generated-output assertions.
- `scripts/tests/test_create_eval_from_issues.py:30,72` — inline YAML asserts `max_iterations: 5` / `max_iterations: 50`; update to `max_steps:` once eval-loop templates change.
- `scripts/tests/test_verify_issue_loop.py:34` — inline YAML with `max_iterations: 20`; update to `max_steps: 20`.

**Tests that BREAK only if `state_enter` event payload field is renamed from `"iteration"` to `"step"` (conditional — see sub-decision note in Confidence Check Notes):**
- `scripts/tests/test_events.py:84-89` — constructs `state_enter` event with `{"iteration": 1}` and asserts equality; update if field renamed.
- `scripts/tests/test_usage_reporter.py:25,51,75,97,131-153,180` — `state_enter` events with `"iteration": N`; same condition.
- `scripts/tests/test_loop_run_analytics.py:88-350` — many `state_enter` event dicts with `"iteration": N`; same condition.
- `scripts/tests/test_fsm_interpolation.py:94` — `ctx.resolve("state", "iteration") == 5`; update if `InterpolationContext.iteration` attribute is renamed.
- `scripts/tests/test_usage_journal.py:106` — `assert "iteration" in row`; update if the column is renamed in the usage journal.

### Documentation
- `ll-loop run --help`, the loop README, and the loop-authoring guide
  (`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`).

### Codebase Research Findings — Specific Doc Files

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — loop budgeting guidance; update `max_iterations` semantics section.
- `docs/guides/LOOPS_GUIDE.md` — general loop authoring guide; update budgeting examples.
- `docs/reference/loops.md` — loop reference documentation; update `max_iterations` field description.
- `docs/reference/EVENT-SCHEMA.md` — covers `state_enter` and `max_iterations_summary` event payloads; update if payload fields change.

### Wiring Pass — Additional Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4147-4613` — `FSMLoop` dataclass signature (line 4147: `max_iterations: int = 50`, `on_max_iterations`), inline YAML examples (lines 4199, 4222, 4248), and `LoopResult.terminated_by` enum values (line 4613). Document `max_iterations` (iteration cap, `None` default) and `max_steps` (step cap, `50` default, backwards-compat alias for legacy `max_iterations` YAML key); update `terminated_by` values list.
- `docs/generalized-fsm-loop.md:357` — Comprehensive `max_iterations` coverage: field definition at line 357, ~17 code examples throughout, prose at line 1508 ("Iteration limits: `max_iterations` prevents runaway loops"), and pseudo-test at line 1864 asserting `result.terminated_by == "max_iterations"`. Update field definition, examples, and the behavioral prose section.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:581` — Budgeting table with `max_iterations` column (line 581), `max_iterations: 5` / `max_iterations: 200` examples (lines 599, 653, 814). Update to clarify `max_iterations` as the iteration cap (full loop passes) and `max_steps` as the per-step safety backstop.
- `docs/reference/COMMANDS.md:671-673` — SIM-1/SIM-2/SIM-3 check descriptions reference `max_iterations` in review-loop context; `ll-loop run --max-iterations 1` example at line 646. Update to reflect `--max-steps` rename and new `--max-iterations` iteration-cap flag.
- `skills/create-loop/SKILL.md` — Loop creation wizard generates `max_iterations:` fields in new loops. Update to generate `max_steps:` as the per-step safety backstop and `max_iterations:` as the optional iteration cap with guidance on when each applies.
- `docs/reference/schemas/max_iterations_summary.json` — auto-generated event schema; if `iteration_count` is added to the cap-fire event payload, regenerate via `generate_schemas.py`.
- `docs/reference/schemas/state_enter.json` — auto-generated; if `iteration_count` is added to `state_enter` payload (line 94-99 of `generate_schemas.py`), regenerate and update `required` list.
- `docs/reference/schemas/loop_complete.json` — `terminated_by` description example references `"max_iterations"`; update example if new reason strings are added.

### Wiring Pass 2 — Additional Documentation (2026-06-07)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/create-loop/loop-types.md:942` — "Iteration-Cap Summary Hook (`on_max_iterations` — ENH-1631)" section with live `on_max_iterations: summarize_partial` YAML example (update to `on_max_steps:`); step-count budgeting formula at line 694 (`max_iterations = estimated_items * per_item_retries * evaluation_states + buffer`); 27+ additional `max_iterations` references in templates and category table (lines 158, 185, 273, 301, 387, 412, 496, 527, 694, 709, 775, 855, 875, 897, 902, 1029, 1166, 1395, 1527, 1792, 1830, 1913, 1946, 2027, 2069). Update all to `max_steps` terminology.
- `skills/create-loop/reference.md:743` — `"terminated by max_iterations"` routing description; 20+ `max_iterations` references in canonical YAML snippets and guidance prose (lines 323, 341, 372, 431, 450, 531, 550, 588, 608, 721, 743, 849, 882, 920, 935, 983, 1000, 1013, 1060). Update to `max_steps` / `max_iterations` (iteration-cap) terminology throughout.
- `scripts/little_loops/cli/loop/_helpers.py:EventFeedRenderer.render_event():794-799` — `elif event_type == "max_iterations_summary":` branch in the event feed renderer. This file is already in the Integration Map but this specific dispatch and string literal are not called out. Update the matched string to `"max_steps_summary"`; add a new elif handler for `"max_iterations_reached_summary"`.
- `scripts/little_loops/generate_schemas.py:SCHEMA_DEFINITIONS` — `generate_schemas.py` does NOT auto-discover new event types; the `SCHEMA_DEFINITIONS` dict (starting at line 82) must be manually edited: rename the `"max_iterations_summary"` entry (lines 397–407) to `"max_steps_summary"` (update description to "Emitted when the step cap fires and on_max_steps is set") and add a new `"max_iterations_reached_summary"` entry alongside it. Then re-run `ll-generate-schemas` to produce `docs/reference/schemas/max_steps_summary.json` (renamed) and `docs/reference/schemas/max_iterations_reached_summary.json` (new; does not yet exist).

### Wiring Pass 3 — Additional Documentation (2026-06-13)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/review-loop/SKILL.md:215-226` — contains its own SIM-1/SIM-2/SIM-3 `"Terminated by: max_iterations"` string patterns, independent of `skills/review-loop/reference.md` (already in the issue); must be updated alongside reference.md.
- `skills/cleanup-loops/SKILL.md:343` — `terminated_by` value enumeration mentions `max_iterations`; update example values to `max_steps` if the termination reason string changes.
- `skills/create-eval-from-issues/SKILL.md:253,293` — `max_iterations:` in inline YAML examples; update to `max_steps:` for consistency with new terminology in generated output.
- `skills/workflow-automation-proposer/SKILL.md:144` — `max_iterations: 10` in inline YAML example; update to `max_steps: 10`.
- `skills/verify-issue-loop/SKILL.md:154` — `max_iterations: 20` in inline YAML; update to `max_steps: 20`.
- `docs/reference/COMMANDS.md:820,828` — `ll-loop calibrate-budget` description references `max_iterations`; update to clarify `max_steps` (per-step safety backstop, governs `calibrate-budget` advice) vs. `max_iterations` (full-iteration cap). This is distinct from lines 646-673 already in the issue.

### Configuration
- Loop YAML schema: `max_iterations` (iteration cap, new semantics) and `max_steps`
  (step cap, old `max_iterations` behavior) in the loop YAML schema and
  `fsm-loop-schema.json`.

### Codebase Research Findings — Schema File

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/fsm-loop-schema.json:37-41` — JSON schema for `max_iterations` with description "Safety limit for loop iterations". Update description or add new field entries (Option 2) here.

### Refine Pass — Additional Files (2026-06-07)

_Added by `/ll:refine-issue` — based on second research pass:_

- `scripts/little_loops/session_store.py:55-65` — `_LOOP_EVENT_TYPES` frozenset must include the new iteration-cap event type name `"max_iterations_reached_summary"`; the existing `"max_iterations_summary"` entry will be renamed to `"max_steps_summary"`. Without this update, iteration-cap cap-fire events are not persisted in the SQLite `loop_events` table.
- `skills/debug-loop-run/reference.md` — event-payload table references `"max_iterations_summary"` event format; update event name to `"max_steps_summary"` and add `"max_iterations_reached_summary"` entry for the iteration cap.
- `scripts/little_loops/loops/general-task.yaml:9` — `on_max_iterations: summarize_partial` → must be updated to `on_max_steps: summarize_partial`. Only 2 loop YAMLs use `on_max_iterations:` (this one and `canvas-sketch-generator`); both must be explicitly migrated because the backward-compat alias for `on_max_iterations` cannot safely map to `on_max_steps` without conflicting with the new `on_max_iterations` Python field (iteration-cap summary state).
- `scripts/little_loops/loops/canvas-sketch-generator.yaml:32` — `on_max_iterations: finalize` → must be updated to `on_max_steps: finalize` (same reason).

## Impact

- **Priority**: P2 — Affects every FSM loop's budgeting and produces confusing
  silent termination, but a workaround exists (over-budget `max_iterations`);
  not a crash or data-loss path.
- **Effort**: Medium — the executor change itself is localized, but option 1
  (iteration-based counting) also requires migrating existing loops' `max_iterations`
  values plus docs and test updates.
- **Risk**: Medium — changing counting semantics silently shifts every existing
  loop's termination point; mitigate with a retained hard step backstop and a
  coordinated migration.
- **Breaking Change**: Yes for option 1 (existing `max_iterations` values need
  re-tuning); No for options 2–3 (backwards-compat alias in `from_dict()`).

### Effects

- **Affects every FSM loop**, not just the new one. Visual loops compensate by
  setting `max_iterations: 20` to obtain only ~5–6 real refine iterations — a magic
  number that encodes the confusion rather than fixing it.
- New loop authors choosing a `max_iterations` default will mis-budget.
- CLI users debugging a loop see silent early termination and misattribute it to
  a broken loop (as happened here).

## Proposed Fix

Evaluate, in order of preference:

1. **Iteration-based counting (preferred):** increment the cap counter only on
   return to `initial` (or a declared anchor state), and rename the per-step
   counter internally. Keep a separate hard step ceiling as a runaway backstop.
   Requires migrating existing loops' `max_iterations` values.
2. **Clarify + dual counter:** expose the current step-cap as `max_steps` (with
   legacy YAML `max_iterations` aliased to `max_steps` via `from_dict()`); add
   `max_iterations` as the new iteration cap (full loop passes), and document
   both. Terminology: **iteration** = full loop pass; **step** = single state
   execution.

   > **Selected:** Option 2 — Clarify + dual counter — The `max_steps`+`max_edge_revisits` dual-counter pattern and the `on_success`→`on_yes` field-alias pattern are both directly established in `FSMLoop`/`schema.py:from_dict()`, making this the highest-consistency option. It delivers the console message and docs improvements of Option 3 as a subset, plus a concrete `max_iterations` API (counting full loop iterations) that eliminates the magic-number budgeting offset in 77+ existing loop YAMLs — all with no breaking changes and no YAML migrations.

3. **Minimum (docs-only):** document the per-step semantics in
   `ll-loop run --help`, the loop README, and the loop-authoring guide, and emit
   a clearer termination reason when the cap fires before any terminal state.

Whichever path: improve the terminal signal so "cap hit before terminal" is
distinguishable from a clean finish.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-07.

**Selected**: Option 2 — Clarify + dual counter

**Reasoning**: The `max_steps`+`max_edge_revisits` pair in `FSMLoop` is the established dual-counter precedent, and the `on_success`→`on_yes` alias in `schema.py:from_dict()` provides a direct template for aliasing the legacy `max_iterations` YAML key to `max_steps` without any YAML migrations. Option 2 is a strict superset of Option 3's improvements (console message, help string, docs) and additionally provides a `max_iterations` field (counting full loop iterations, matching the name's intuitive meaning) that eliminates the manual step-to-iteration math encoded as magic-number comments across 77+ loop YAMLs (`max_iterations: 20` for ~5 real iterations). Option 1 is blocked by a breaking change requiring 80-file YAML migration, a triple-duty `self.iteration` separation across executor/persistence/event-schema, and reworking the `-n 1` single-step debugging idiom (becomes `-n 1` for one full iteration, `--max-steps 1` for one step).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 (iteration-based rewrite) | 1/3 | 0/3 | 1/3 | 0/3 | 2/12 |
| Option 2 (dual counter) | 3/3 | 2/3 | 2/3 | 2/3 | 9/12 |
| Option 3 (docs-only) | 2/3 | 3/3 | 2/3 | 3/3 | 10/12 |

**Key evidence**:
- Option 1: `self.iteration` serves triple duty (cap counter, `state_enter` payload, `LoopState` persistence field) with no iteration-boundary event; 80 YAML files need re-tuning; single-step debugging idiom changes. Reuse score: 1/3.
- Option 2: `max_edge_revisits` coexists as a second cap field in `schema.py:953`; `on_success`/`on_failure` alias at `schema.py:from_dict()` is the backwards-compat rename template; `canvas-sketch-generator.yaml:22-27` BUG-2011 comment confirms the magic-number pattern Option 2 eliminates. Reuse score: 2/3.
- Option 3: All deliverables are string edits or a single conditional print before `_helpers.py:1275`; doesn't prevent future authors from re-encoding the step-to-iteration offset as magic numbers. Reuse score: 3/3.

## Implementation Steps

1. **Terminology settled**: iteration = full loop pass (back to initial); step = single state execution. Option 2 selected: no YAML migrations — `from_dict()` aliases legacy `max_iterations` YAML key → `max_steps`.
2. Update `executor.py` increment/cap logic (`:403`, `:296`) and the
   `state_enter` / `max_steps_summary` event payloads; add iteration counter
   alongside the retained step counter.
3. Update `ll-loop run --help` (`--max-iterations` → iteration cap, `--max-steps` → step cap) and loop-authoring docs.
4. Add a regression test asserting that a 1-iteration loop completes one full
   `initial → … → terminal` pass under the documented budget.

### Codebase Research Findings — Concrete File References

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Counting model (decided)**: consult `schema.py:951-953` for the three related fields (`max_iterations`, `on_max_iterations`, `max_edge_revisits`). `max_edge_revisits` (default 100) already serves as a runaway backstop under all options — retain it. Under Option 2, `FSMLoop` gains a new `iteration_count` field (full loop passes) alongside the retained `step` counter (renamed from `self.iteration`).
2. **Update executor logic**: three increment sites must be updated consistently — `executor.py:403` (primary, every non-terminal state), `executor.py:355` (maintain-mode restart), `executor.py:1372` (flush path in `_flush_pending_shell_state`). Cap check at `executor.py:296`. Under Option 2, add a parallel `max_iterations` (iteration) cap path; retain existing cap path as `max_steps`.
3. **Update CLI and docs**:
   - `cli/loop/__init__.py:127` — rename `--max-iterations`/`-n` to `--max-steps`/`-n` (step cap); add `--max-iterations` as iteration-cap flag
   - `cli/loop/_helpers.py:29-37` — add a console message in the `"max_steps"` exit branch (before `run_foreground()` returns at line 1275) to distinguish cap-before-terminal from other `exit 1` causes
   - `fsm-loop-schema.json:37-41` — update `max_iterations` description (iteration cap) and add `max_steps` field entry
   - `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/reference/loops.md` — update budgeting guidance with iteration/step terminology
4. **Add regression test**: in `scripts/tests/test_fsm_executor.py`, model after `TestMaxStepsSummaryHook` (renamed from `TestMaxIterationsSummaryHook`, line 7184). Assert that a 2-step-per-iteration loop with `max_iterations=1` runs all steps in one iteration before capping. Update `test_max_iterations_respected` → `test_max_steps_respected` (line 159). Verify `test_cycle_detection_terminates_loop` (line 183) still passes. Also check `test_ll_loop_execution.py:test_exits_on_max_iterations` → `test_exits_on_max_steps` for CLI assertions.
5. **Persist iteration counter** (Option 2): update `persistence.py:190` `LoopState` dataclass to add `iteration_count: int = 0`; update `PersistentExecutor.resume()` at line 810 to restore it alongside `self._executor.iteration` (the step counter).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/little_loops/fsm/validation.py` — add `"max_steps"` and `"max_iterations"` (iteration cap) to `known_top_level_keys` set (line 131); add `max_steps > 0` range check in `_validate_numeric_fields()` (line 936); rename `_validate_on_max_iterations()` (line 1470) → `_validate_on_max_steps()`; add new `_validate_on_max_iterations()` for the iteration-cap summary state if `on_max_iterations` is added.
7. Update `scripts/little_loops/cli/loop/testing.py:203-211` — rename `fsm.max_iterations` mutation to `fsm.max_steps`; add `--max-iterations` override path for the iteration cap in `cmd_simulate()`.
8. Update `scripts/little_loops/cli/loop/config_cmds.py:25` — show `max_steps` (step cap) and `max_iterations` (iteration cap) in `cmd_config_show()` display output.
9. Update `scripts/little_loops/cli/loop/next_loop.py:308` — rename `max_iterations=None` → `max_steps=None`; add `max_iterations=None` (iteration cap) to the `argparse.Namespace` constructed for `cmd_run`.
10. Update `scripts/little_loops/cli/loop/_helpers.py:1033` — rename `["--max-iterations", ...]` → `["--max-steps", ...]` in `_build_background_cmd()`; add parallel forwarding for `["--max-iterations", ...]` (iteration cap).
11. Update display strings in `scripts/little_loops/cli/loop/_helpers.py` — `_print_loop_plan()` at line 949, `run_foreground()` at line 1168, `info.py:_format_loop_config_line()` at line 999 — show `Max steps:` for the step cap and `Max iterations:` for the iteration cap when set.
12. Update `skills/review-loop/reference.md` — QC-1 key check (`max_steps`/`max_iterations`) and SIM-1/SIM-2/SIM-3 `"Terminated by:"` parsing; update `skills/audit-loop-run/SKILL.md:168` `partial` verdict rule if termination reason string changes.
13. Regenerate event schemas via `scripts/little_loops/generate_schemas.py` if `state_enter` or `max_steps_summary` payloads gain an `iteration_count` field.
14. Add `TestFSMLoopMaxIterations` to `test_fsm_schema.py` (model after `TestFSMLoopArtifactVersioning` line 3282); add `TestMaxIterationsValidation` and `TestMaxStepsValidation` to `test_fsm_validation.py` (model after `TestOnMaxIterationsValidation` line 1421); rename existing `test_max_iterations_forwarded` (line 533) → `test_max_steps_forwarded`; add new `test_max_iterations_forwarded` to `test_cli_loop_dispatch.py`.
15. Update docs: `docs/reference/API.md:4147`, `docs/generalized-fsm-loop.md:357`, `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:581`, `docs/reference/COMMANDS.md:646-673`, `skills/create-loop/SKILL.md` — use iteration/step terminology throughout.
16. Add `_iteration_summary_executed: bool = False` alongside `_summary_state_executed` at `executor.py:212`; add parallel iteration-cap branch with event name `"max_iterations_reached_summary"` (distinct from `"max_iterations_summary"` → `"max_steps_summary"`) and terminal intercept preserving `terminated_by="max_iterations_reached"`. Add `"on_max_iterations"` and `"on_max_steps"` to `known_top_level_keys` in `validation.py:131`; add `_validate_on_max_iterations()` for the iteration-cap summary state (parallel to renamed `_validate_on_max_steps()`). Update `general-task.yaml:9`, `canvas-sketch-generator.yaml:32`, and `vega-viz.yaml:33` from `on_max_iterations:` → `on_max_steps:` — the backward-compat `from_dict()` alias cannot cover this because the new Python field `on_max_iterations` is the iteration-cap summary state; these 3 YAML files need explicit migration.
17. Update `scripts/little_loops/cli/loop/_helpers.py:EventFeedRenderer.render_event():794-799` — rename `"max_iterations_summary"` branch to `"max_steps_summary"`; add new elif handler for `"max_iterations_reached_summary"`.
18. Edit `scripts/little_loops/generate_schemas.py:SCHEMA_DEFINITIONS` — rename the `"max_iterations_summary"` key (lines 397–407) to `"max_steps_summary"` (description: "Emitted when the step cap fires and on_max_steps is set"); add a new `"max_iterations_reached_summary"` entry. Then re-run `ll-generate-schemas` to produce `docs/reference/schemas/max_steps_summary.json` and `docs/reference/schemas/max_iterations_reached_summary.json` (does not yet exist).
19. Update `skills/create-loop/loop-types.md` — rename `on_max_iterations:` → `on_max_steps:` in the "Iteration-Cap Summary Hook" section (line 942); update the step-count formula label at line 694; update all 27+ remaining `max_iterations` references to `max_steps` terminology.
20. Update `skills/create-loop/reference.md` — update `"terminated by max_iterations"` routing description (line 743) and 20+ `max_iterations` references to `max_steps` / `max_iterations` (iteration-cap) terminology throughout.

### Wiring Phase 3 (added by `/ll:wire-issue` on 2026-06-13)

_Additional touchpoints identified by third wiring pass:_

21. Migrate `scripts/little_loops/loops/vega-viz.yaml:33` — `on_max_iterations: max_iterations_summary` → `on_max_steps: max_iterations_summary`; this is the **3rd** loop YAML requiring explicit migration (step 16 listed 2; now confirmed 3 total). The state name `max_iterations_summary` in the YAML body can remain as-is since it is a user-defined state name, not the event type.
22. Update `skills/review-loop/SKILL.md:215-226` — this file has its own SIM-1/SIM-2/SIM-3 `"Terminated by: max_iterations"` patterns independent of `skills/review-loop/reference.md` (step 12); update both files separately.
23. Update skill YAML examples: `skills/create-eval-from-issues/SKILL.md:253,293`, `skills/workflow-automation-proposer/SKILL.md:144`, `skills/verify-issue-loop/SKILL.md:154` (rename `max_iterations:` → `max_steps:` in inline YAML examples); `skills/cleanup-loops/SKILL.md:343` (update `terminated_by` enumeration from `"max_iterations"` → `"max_steps"`).
24. Update task templates: `scripts/little_loops/loops/lib/task-templates/data-lib-task.yaml.tmpl:15`, `stateful-service-task.yaml.tmpl:14`, `desktop-gui-task.yaml.tmpl:14` — rename `max_iterations:` → `max_steps:` so new loops generated from these templates use new terminology.
25. Update argparse-plumbing tests (coordinate with CLI changes in steps 3, 10): `scripts/tests/test_cli_loop_testing.py` (`_make_args(max_iterations=3)` → `_make_args(max_steps=3)`, rename `test_max_iterations_applied` → `test_max_steps_applied`); `test_cli_loop_background.py:210` (`test_forwards_max_iterations` → `test_forwards_max_steps`); `test_cli_loop_queue.py`, `test_cli_loop_worktree.py`, `test_ll_loop_program_md.py:150`, `test_cross_host_baseline.py:132,246,308` — all `Namespace(max_iterations=None)` → `Namespace(max_steps=None)`; add `max_iterations=None` for iteration-cap flag.
26. Update generated/template YAML assertions (do after step 19): `test_create_loop.py` (inline `max_iterations: 50` → `max_steps: 50`), `test_loop_suggester.py` (fixture YAML strings), `test_create_eval_from_issues.py:30,72`, `test_verify_issue_loop.py:34`.
27. Update `scripts/tests/test_cli.py` — `FSMLoop(max_iterations=50)` calls used as step-cap; rename to `FSMLoop(max_steps=50)` (under Option 2, `max_iterations=N` in the Python constructor sets the iteration cap, not the step cap).
28. Update `docs/reference/COMMANDS.md:820,828` — `max_iterations` references in `ll-loop calibrate-budget` description (separate from lines 646-673 in step 15); clarify `max_steps` as the step budget that `calibrate-budget` advises on.
29. (Conditional — only if `state_enter` payload field `"iteration"` is renamed to `"step"`) Update: `test_events.py:84-89`, `test_usage_reporter.py`, `test_loop_run_analytics.py`, `test_fsm_interpolation.py:94` (`ctx.resolve("state", "iteration")`), `test_usage_journal.py:106` (`assert "iteration" in row`). Recommend keeping `"iteration"` as the field name for backwards compatibility and only adding `"iteration_count"` as a new parallel field if observability parity is needed.

## Acceptance Criteria

- [ ] `ll-loop run <loop> --max-steps N` (and its `-n N` alias) terminates after at most N state executions with a console message distinguishing "step cap hit" from other `exit 1` causes.
- [ ] `ll-loop run <loop> --max-iterations N` terminates after at most N full loop passes (returns to initial state), with `terminated_by="max_iterations_reached"` in the `ExecutionResult`.
- [ ] A loop YAML with only `max_iterations: 50` (no `max_steps:`) is read by `FSMLoop.from_dict()` as `max_steps = 50` with no YAML migration required; `max_iterations` (iteration cap) remains `None`.
- [ ] A loop YAML with both `max_steps: 50` and `max_iterations: 3` applies both caps independently.
- [ ] `on_max_steps: <state>` executes the named summary state when the step cap fires; `terminated_by="max_steps"` is preserved in `ExecutionResult` and the `loop_complete` event.
- [ ] `on_max_iterations: <state>` executes the named summary state when the iteration cap fires; `terminated_by="max_iterations_reached"` is preserved.
- [ ] `general-task.yaml`, `canvas-sketch-generator.yaml`, and `vega-viz.yaml` are updated from `on_max_iterations:` → `on_max_steps:` (the 3 existing loop YAMLs using the step-cap summary hook).
- [ ] `ll-loop validate` recognizes `max_steps`, `on_max_steps`, `max_iterations` (iteration cap), and `on_max_iterations` as valid top-level keys; legacy `max_iterations:` YAML key (step cap) no longer emits an unknown-key warning.
- [ ] `ll-loop validate` confirms `on_max_steps` and `on_max_iterations` each name an existing state in the loop definition.
- [ ] All existing built-in loops pass `ll-loop validate` with no new warnings after implementation (`test_builtin_loops.py:test_all_validate_as_valid_fsm` passes unchanged).
- [ ] `TestMaxStepsSummaryHook` (renamed from `TestMaxIterationsSummaryHook`) and new `TestMaxIterationsSummaryHook` (iteration-cap) both pass with their 5-method structure.
- [ ] `ll-loop info <loop>` and `ll-loop run` header display `Max steps: N` and `Max iterations: N` (when set) as separate lines.

## Status

- **State**: open
- **Discovered**: 2026-06-07 (smoke run of canvas-sketch-generator)
- **Decomposed**: 2026-06-17 into BUG-2204 (core dual-counter implementation) and BUG-2205 (rename sweep — CLI, tests, skills, docs). Implement BUG-2204 first; BUG-2205 depends on it.

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-17 (re-check post-verification pass; scores unchanged)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 56/100 → LOW

### Outcome Risk Factors
- **Very wide blast radius**: 50+ distinct change sites across 6+ subsystems (fsm core, CLI commands, persistence, session store, test suite, skills, documentation, loop YAMLs). Wiring Pass 3 added 10+ more test files and 5+ skill/doc files; scores unchanged (breadth was already at the sweeping floor). Work through Implementation Steps 1–29 sequentially; each step is mechanical once tracked systematically.
- **Conditional payload field**: `iteration_count` in `state_enter` event is mentioned as "if added" in docs/schema sections — resolve at session start whether to add it (recommended: yes, for observability parity with the existing `iteration` field; keep `"iteration"` as the field name and add `"iteration_count"` as a new parallel field per step 29 guidance) to avoid revisiting docs and schema steps mid-way.

### Sub-Decision Resolved (2026-06-07 Refine Pass)

**`on_max_iterations` iteration-cap summary state: YES, add it.**

The existing `_summary_state_executed` flag at `executor.py:212` and the `TestMaxIterationsSummaryHook` class (line 7184 `test_fsm_executor.py`) provide a direct template. The iteration-cap hook requires the same 4-part structure:
1. Add `_iteration_summary_executed: bool = False` alongside `_summary_state_executed` at `executor.py:212`.
2. Add parallel cap-check branch keyed on `fsm.max_iterations is not None and iteration_count >= fsm.max_iterations` (where `iteration_count` is the new full-pass counter, distinct from `self.iteration` / step counter).
3. Use event name `"max_iterations_reached_summary"` (distinct from `"max_iterations_summary"` which becomes `"max_steps_summary"`).
4. Add parallel terminal intercept preserving `terminated_by="max_iterations_reached"` even after the summary state executes to completion.

**Implementation template**: ENH-1631 (`.issues/enhancements/P3-ENH-1631-fsm-runtime-on-max-iterations-summary-hook.md`) added the step-cap summary hook; use it as the pattern for the iteration-cap hook. The 5 test scenarios in `TestMaxIterationsSummaryHook` (`test_summary_state_runs_on_cap`, `test_max_iterations_summary_event_emitted`, `test_terminated_by_max_iterations_after_summary`, `test_no_summary_state_without_on_max_iterations`, `test_summary_state_executes_only_once`) must be replicated in the new `TestMaxIterationsSummaryHook` (iteration-cap).

**YAML alias conflict**: `from_dict()` cannot alias `on_max_iterations` YAML key → `on_max_steps` Python field because the new `on_max_iterations` Python field is the iteration-cap summary state. The 2 existing loops (`general-task.yaml:9`, `canvas-sketch-generator.yaml:32`) must be explicitly updated to `on_max_steps:` as part of this implementation — there is no non-breaking alias path.

## Verification Notes (2026-06-17)

- **Current line numbers** (verified 2026-06-17): primary increment `executor.py:400`; cap check `:310`; maintain-mode restart `:456`; flush path `:1490`. `schema.py` fields: `max_iterations` `:961`, `on_max_iterations` `:962`, `max_edge_revisits` `:963`. `TestMaxIterationsSummaryHook` at line `7663`.
- Bug is unimplemented: `max_steps`/`max_iterations` dual-counter fix not yet in `executor.py` or `schema.py`. Three YAML files (`canvas-sketch-generator.yaml`, `vega-viz.yaml`, `general-task.yaml`) still use `on_max_iterations:` as described.

## Session Log
- `/ll:confidence-check` - 2026-06-17T00:00:00Z - `61080daf-c8b4-4a7f-bca8-e81a09d0e829.jsonl`
- `/ll:refine-issue` - 2026-06-17T18:18:12 - `a975220c-f204-4a44-bba9-d07f395df4f0.jsonl`
- `/ll:verify-issues` - 2026-06-13T21:13:57 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:confidence-check` - 2026-06-13T18:30:00Z - `b2d4feeb-e222-4a6a-8608-9774ec172c24.jsonl`
- `/ll:wire-issue` - 2026-06-13T18:05:54Z - `ecae74c3-ea98-4133-b95f-77f464d27531.jsonl`
- `/ll:confidence-check` - 2026-06-13T00:00:00Z - `71b001de-828d-4dd5-bf66-25c9d0924c2d.jsonl`
- `/ll:verify-issues` - 2026-06-09T18:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:wire-issue` - 2026-06-08T01:30:54 - `bd674972-d40a-41d7-8755-4b2991056e84.jsonl`
- `/ll:refine-issue` - 2026-06-08T01:21:46 - `bd674972-d40a-41d7-8755-4b2991056e84.jsonl`
- `/ll:decide-issue` - 2026-06-08T00:32:10 - `f4c7bf77-d0d5-4c99-aeeb-85249c64bdfe.jsonl`
- `/ll:refine-issue` - 2026-06-08T00:18:43 - `828a4616-25c3-4af4-bb64-459468e94960.jsonl`
- `/ll:format-issue` - 2026-06-07T23:31:25 - `28dd97b0-82a8-4f71-a133-64fc6f2c6a75.jsonl`
- `/ll:capture-issue` - 2026-06-07T22:42:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/94001b17-192e-4675-8b12-449cc4ed8e69.jsonl`
- `/ll:wire-issue` - 2026-06-08T00:42:56 - `bfc250e0-8433-4ef4-b8c1-639b534afb66.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:00:00Z - `fb61b340-4c04-4610-99f5-70ff355a9eee.jsonl`
- `/ll:confidence-check` - 2026-06-08T00:00:00Z - `30bc6534-43a0-4c33-8689-74a4abb980cd.jsonl`
