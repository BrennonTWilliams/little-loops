---
id: BUG-2205
type: BUG
priority: P2
status: open
captured_at: '2026-06-17T00:00:00Z'
discovered_date: 2026-06-17
discovered_by: finalize-decomposition
labels:
- fsm
- loop-runner
- dx
- footgun
parent: BUG-2011
relates_to:
- BUG-2204
decision_needed: false
confidence_score: 96
outcome_confidence: 79
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 20
---

# BUG-2205: FSM max_iterations — rename sweep (CLI, tests, skills, docs)

## Summary

Split from BUG-2011 (rename-sweep-only scope). After BUG-2204 lands the dual-counter
implementation in `executor.py`/`schema.py`, this issue propagates the terminology rename
across all CLI commands, display strings, argparse plumbing, test string literals, skill
files, documentation, and loop templates. Every change here is a mechanical string or
symbol rename; no new logic is introduced.

**Depends on BUG-2204** — do not start until BUG-2204 is merged.

## Current Behavior

The FSM runner exposes a single `max_iterations` field that counts individual state
transitions (steps). The CLI flag `--max-iterations`/`-n`, display strings, argparse
plumbing, test fixtures, skill files, and all documentation use `max_iterations` to mean
"maximum number of FSM state transitions before forced termination." There is no separate
concept of "maximum number of complete loop passes (full iterations)." The name misleads
loop authors who expect `max_iterations` to count full end-to-end loop cycles, not
individual state steps — a terminology footgun tracked as the root cause in BUG-2011.

## Expected Behavior

After this rename sweep (building on the dual-counter logic from BUG-2204):
- `max_steps`/`--max-steps` is the per-state-transition safety backstop (step cap)
- `max_iterations`/`--max-iterations` is the full-pass (complete-loop-cycle) cap
- All CLI flags, display strings, argparse plumbing, skill files, docs, and test fixtures
  consistently use `max_steps` for step counting and `max_iterations` for pass counting

## Steps to Reproduce

1. Run `ll-loop run <any-loop> --help` — observe the `--max-iterations` flag
2. Note the flag description: it counts individual FSM state transitions, not full loop passes
3. Run `ll-loop info <loop>` — the header shows `Max iterations: N`, which actually means max steps
4. Open `skills/review-loop/reference.md` — `terminated_by: max_iterations` signals step-cap
   exhaustion, not a full-pass limit
5. Open any loop YAML template (e.g., `lib/task-templates/data-lib-task.yaml.tmpl`) —
   `max_iterations: 5` controls per-step safety, not per-pass control
6. The name `max_iterations` conflicts with the natural reading: "how many times the loop
   runs end-to-end"

## Integration Map

### CLI argparse and plumbing

- `scripts/little_loops/cli/loop/__init__.py:127`
  - Rename `--max-iterations`/`-n` → `--max-steps`/`-n` (step cap)
  - Add `--max-iterations` as new iteration-cap flag
  - Same changes to `simulate` subcommand at line 468

- `scripts/little_loops/cli/loop/run.py:118-119`
  - Route `--max-steps` → `fsm.max_steps`; route `--max-iterations` → `fsm.max_iterations` (iteration cap)

- `scripts/little_loops/cli/loop/_helpers.py`
  - `EXIT_CODES` (`:29-37`): rename key `"max_iterations"` → `"max_steps"` (step-cap termination string)
  - `_print_loop_plan()` (`:949`): `f"Max iterations: {fsm.max_iterations}"` → `"Max steps: ..."` and `"Max iterations: ..."` (when set)
  - Pinned-pane counter (`:516`, `:657`): `[{iteration}/{fsm.max_iterations}]` → show step count vs `max_steps`
  - `run_foreground()` (`:1168`): update display string
  - `run_foreground()` (`:1275`): add console message distinguishing "step cap hit before terminal" from other `exit 1` causes
  - `_build_background_cmd()` (`:1033`): `["--max-iterations", ...]` → `["--max-steps", ...]`; add forwarding for `["--max-iterations", ...]` (iteration cap)
  - `EventFeedRenderer.render_event()` (`:794-799`): rename `"max_iterations_summary"` branch → `"max_steps_summary"`; add elif for `"max_iterations_reached_summary"`

- `scripts/little_loops/cli/loop/testing.py:203-211`
  - Rename `fsm.max_iterations` → `fsm.max_steps`; add `--max-iterations` override path for iteration cap

- `scripts/little_loops/cli/loop/config_cmds.py:25`
  - Show `max_steps` and `max_iterations` (when set) separately in `cmd_config_show()`

- `scripts/little_loops/cli/loop/next_loop.py:308`
  - `argparse.Namespace(max_iterations=None)` → `Namespace(max_steps=None, max_iterations=None)`

- `scripts/little_loops/cli/loop/info.py:999`
  - `_format_loop_config_line()`: rename display string; show `max_steps` and `max_iterations` separately

- `scripts/little_loops/fsm/validation.py`
  - `known_top_level_keys` (`:131`): add `"max_steps"`, `"on_max_steps"`, `"max_iterations"` (iteration cap), `"on_max_iterations"`
  - `_validate_numeric_fields()` (`:936`): add `max_steps > 0` range check
  - Rename `_validate_on_max_iterations()` (`:1470`) → `_validate_on_max_steps()`
  - Add new `_validate_on_max_iterations()` for iteration-cap summary state

### Loop YAML templates

- `scripts/little_loops/loops/lib/task-templates/data-lib-task.yaml.tmpl:15` — `max_iterations: 5` → `max_steps: 5`
- `scripts/little_loops/loops/lib/task-templates/stateful-service-task.yaml.tmpl:14` — `max_iterations: 8` → `max_steps: 8`
- `scripts/little_loops/loops/lib/task-templates/desktop-gui-task.yaml.tmpl:14` — `max_iterations: 8` → `max_steps: 8`

### Skills

- `skills/review-loop/reference.md` — QC-1 key check and SIM-1/SIM-2/SIM-3 `"Terminated by: max_iterations"` → `"Terminated by: max_steps"`; update exit-code table
- `skills/review-loop/SKILL.md:215-226` — independent copy of SIM-1/SIM-2/SIM-3 patterns; update separately
- `skills/audit-loop-run/SKILL.md:168` — `terminated_by == "max_iterations"` → `"max_steps"`
- `skills/cleanup-loops/SKILL.md:343` — update `terminated_by` enumeration
- `skills/create-eval-from-issues/SKILL.md:253,293` — `max_iterations:` → `max_steps:` in inline YAML
- `skills/workflow-automation-proposer/SKILL.md:144` — `max_iterations: 10` → `max_steps: 10`
- `skills/verify-issue-loop/SKILL.md:154` — `max_iterations: 20` → `max_steps: 20`
- `skills/debug-loop-run/reference.md` — update `"max_iterations_summary"` → `"max_steps_summary"`; add `"max_iterations_reached_summary"` entry
- `skills/create-loop/SKILL.md` — generate `max_steps:` (step cap) and `max_iterations:` (iteration cap, optional) in new loop wizard; update guidance on when each applies
- `skills/create-loop/loop-types.md` — rename `on_max_iterations:` → `on_max_steps:` (`:942`); update step-count formula label (`:694`); update 27+ remaining `max_iterations` references to `max_steps` terminology
- `skills/create-loop/reference.md` — update `"terminated by max_iterations"` (`:743`) and 20+ references throughout

### Additional Skills

_Added by `/ll:refine-issue` — missing from original list:_

- `skills/adversarial-verify-loop/SKILL.md:225` — `max_iterations: 20` → `max_steps: 20` in inline YAML example

### Built-in Loop YAML Files

_Wiring pass added by `/ll:wire-issue`:_

All 84 built-in loop YAML files in `scripts/little_loops/loops/` (excluding `lib/task-templates/`) carry `max_iterations: N` as the step-cap field. After BUG-2204's `from_dict()` alias, these files remain parseable but `max_iterations` shifts meaning to the full-pass cap — any loop YAML that intends step-cap behavior must be renamed to `max_steps: N`.

- `scripts/little_loops/loops/*.yaml` (84 files) — rename `max_iterations: N` → `max_steps: N` at the top level. Enumerate with: `grep -r "^max_iterations:" scripts/little_loops/loops/ --include="*.yaml" -l`
- `scripts/little_loops/loops/cua-agent-desktop.yaml:17` — additionally rename `on_max_iterations: max_iterations_summary` → `on_max_steps: max_steps_summary` (only operational loop file with this field; `vega-viz.yaml` already uses `on_max_steps:`)

The 3 `lib/task-templates/*.yaml.tmpl` files are already listed above; this group covers all remaining operational loop YAML files.

### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — update `max_iterations` semantics section; clarify `max_steps` vs `max_iterations`
- `docs/guides/LOOPS_GUIDE.md` — update budgeting examples
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:581` — update budgeting table (`max_iterations` column → `max_steps`/`max_iterations`); update inline examples (`:599`, `:653`, `:814`)
- `docs/reference/loops.md` — update `max_iterations` field description
- `docs/reference/EVENT-SCHEMA.md` — update `state_enter` and `max_iterations_summary` event payload docs
- `docs/reference/API.md:4147-4613` — `FSMLoop` dataclass signature, inline YAML examples, `LoopResult.terminated_by` enum values
- `docs/generalized-fsm-loop.md:357` — field definition, ~17 code examples, prose at `:1508`, pseudo-test at `:1864`
- `docs/reference/COMMANDS.md:646-673` — SIM-1/SIM-2/SIM-3 references; `ll-loop run --max-iterations 1` example → `--max-steps`
- `docs/reference/COMMANDS.md:820,828` — `ll-loop calibrate-budget` description; clarify `max_steps` vs `max_iterations`
- `docs/reference/schemas/max_iterations_summary.json` — renamed to `max_steps_summary.json` (auto-generated by BUG-2204 step 6; verify file exists)
- `docs/reference/schemas/max_iterations_reached_summary.json` — new file (auto-generated by BUG-2204 step 6; verify file exists) **[confirmed missing on disk as of 2026-06-17 — expected until BUG-2204 lands]**
- `docs/reference/schemas/loop_complete.json` — update `terminated_by` description example

### Additional Documentation

_Added by `/ll:refine-issue` — missing from original list:_

- `docs/reference/CLI.md:829,837` — `calibrate-budget` subcommand description mentions `max_iterations` twice: `"guide max_iterations calibration"` and `"fix before increasing max_iterations"` → update to `max_steps`
- `docs/guides/LOOPS_REFERENCE.md` — multiple loop catalog entries describe `max_iterations: N` config values inline (e.g., `:229`, `:417`, `:474`, `:558`, `:729`, `:768`); prose like `"until … max_iterations is exhausted"` should become `"max_steps is exhausted"` where applicable; `on_max_iterations:` references at `:1227` → `on_max_steps:`

### Additional Files to Modify

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/fsm/fsm-loop-schema.json:47` — JSON Schema property `"max_iterations"` (`:47-51`) and `"on_max_iterations"` (`:52`); add `"max_steps"` sibling property and `"on_max_steps"`; `"max_iterations"` stays as the new full-pass cap field definition
- `skills/create-loop/templates.md` — 6 YAML template instances of `max_iterations: {{max_iterations}}` (`:38`, `:57`, `:89`, `:112`, `:212`, `:275`) plus 5 placeholder list/substitution entries referencing `{{max_iterations}}`; rename all to `max_steps: {{max_steps}}`
- `.claude/CLAUDE.md:169` — prose in Loop Authoring section: 3 occurrences of `max_iterations` in calibrate-budget guidance (`:169`, `:175`, `:184`) → update to `max_steps`

### BUG-2204 Boundary (files to verify are covered by BUG-2204, not BUG-2205)

_Added by `/ll:refine-issue` — these files contain `max_iterations` but belong to BUG-2204's core-logic scope:_

- `scripts/little_loops/fsm/persistence.py:766` — `if result.terminated_by in ("max_iterations", "signal")`: after BUG-2204, step-cap termination becomes `"max_steps"` → update to `in ("max_steps", "signal")`. Confirm this is in BUG-2204's file list.
- `scripts/little_loops/fsm/types.py:24,34` — `LoopResult` docstring enumerates `terminated_by` values; `"max_iterations"` shifts meaning to full-pass cap. Update docstring comment to list `"max_steps"` (step-cap) and `"max_iterations"` (pass-cap) with descriptions. Confirm BUG-2204 covers this.
- `scripts/little_loops/generate_schemas.py:397-407` — `"max_iterations_summary"` schema definition must be renamed to `"max_steps_summary"`; new `"max_iterations_reached_summary"` entry must be added. BUG-2204 step 6 owns this.
- `scripts/little_loops/session_store.py:119` — `"max_iterations_summary"` event type string in `_LOOP_EVENT_TYPES`. BUG-2204 owns this.

**Do not duplicate these changes in BUG-2205** — verify they are in BUG-2204's implementation steps before starting BUG-2205.

### Integration Map Corrections (Line Numbers)

_Added by `/ll:refine-issue` — verified against current code (2026-06-17):_

| Issue Citation | Actual Location | Note |
|---|---|---|
| `__init__.py:127` | `:129` (run), `:516` (simulate) | Both confirmed |
| `validation.py:131` (KNOWN_TOP_LEVEL_KEYS) | `:151` (frozenset), `"max_iterations"` at `:158-159` | Off by ~20 lines |
| `validation.py:936` (`_validate_numeric_fields()`) | No such function — inline check at `:975` inside `validate_fsm()` | Function does not exist; cite the inline check |
| `validation.py:1470` (`_validate_on_max_iterations`) | `:1615` | Off by ~145 lines |
| `info.py:999` (`_format_loop_config_line()`) | No such function — config display is in `cmd_show()` at `:1119-1122` | Function does not exist |
| `run.py:118-119` | `:118-119` ✓ confirmed | Also: `:175-176` injects `fsm.context["max_iterations"] = fsm.max_iterations` — missing from map; needs update to inject `max_steps` context after BUG-2204 |

### Tests — argparse plumbing (break on `max_iterations` → `max_steps` dest rename)

- `scripts/tests/test_cli_loop_testing.py` — `_make_args(max_iterations=3)` → `_make_args(max_steps=3)`; rename `test_max_iterations_applied` → `test_max_steps_applied`
- `scripts/tests/test_cli_loop_background.py:210` — `test_forwards_max_iterations` → `test_forwards_max_steps`; update flag assertion
- `scripts/tests/test_cli_loop_queue.py` — `Namespace(max_iterations=None)` → `Namespace(max_steps=None, max_iterations=None)`
- `scripts/tests/test_cli_loop_worktree.py` — same Namespace rename
- `scripts/tests/test_ll_loop_program_md.py:150` — `max_iterations=None` → `max_steps=None` in fixture
- `scripts/tests/test_cross_host_baseline.py:132,246,308` — `Namespace(max_iterations=None)` → `Namespace(max_steps=None)`
- `scripts/tests/test_cli_loop_dispatch.py` — rename `test_max_iterations_forwarded` (`:533`) → `test_max_steps_forwarded`; add `test_max_iterations_forwarded` for iteration-cap flag; same for `test_simulate_max_iterations_forwarded` (`:818`)

### Tests — FSMLoop Python constructor (break when `FSMLoop.max_iterations` shifts meaning)

- `scripts/tests/test_cli.py` — `FSMLoop(max_iterations=50)` used as step cap → `FSMLoop(max_steps=50)`
- `scripts/tests/helpers.py:56,73` — `FSMLoop(max_iterations=max_iterations)` → `FSMLoop(max_steps=max_steps)`

### Tests — display string assertions

- `scripts/tests/test_ll_loop_execution.py`
  - `test_exits_on_max_iterations` (`:137`, `:142`): `--max-iterations` flag → `--max-steps`; `"Max iterations: 2"` → `"Max steps: 2"`
  - `test_runs_with_header` (`:97`): `"Max iterations: 3"` → `"Max steps: 3"`
- `scripts/tests/test_ll_loop_display.py`
  - `TestLoopInfo.test_metadata_shown` (`:497`): `"Max iterations: 25"` → `"Max steps: 25"`
  - `TestRunForegroundExitCodes.test_exit_codes_dict_matches_expected_mapping` (`:2715`): `EXIT_CODES["max_iterations"]` → `EXIT_CODES["max_steps"]`
  - `test_show_header_with_metadata` (`:628`)
- `scripts/tests/test_ll_loop_integration.py`
  - `test_run_with_max_iterations_shows_in_plan` (`:91`): update to `max_steps` header
- `scripts/tests/test_ll_loop_parsing.py`
  - `test_run_with_max_iterations` (`:95`): rename; update `args.max_iterations` → `args.max_steps`
- `scripts/tests/test_cli_loop_lifecycle.py`
  - `mock_result.terminated_by = "max_iterations"` (`:493`) → `"max_steps"`
  - `@pytest.mark.parametrize("terminated_by", ["max_iterations", ...])` (`:978`) → `"max_steps"`
- `scripts/tests/test_review_loop.py:1024,1058,1074` — `"max_iterations"` / `"terminated_by_max"` → `"max_steps"`
- `scripts/tests/test_fsm_schema.py`
  - `test_max_iterations_zero_rejected` (`:1472`), `test_max_iterations_negative_rejected` (`:1488`) → rename to `test_max_steps_*`; update error message string

### Tests — generated/template YAML output assertions

- `scripts/tests/test_create_loop.py` — `max_iterations: 50` → `max_steps: 50` in inline fixtures
- `scripts/tests/test_loop_suggester.py:354-640` — multiple inline YAML fixtures
- `scripts/tests/test_create_eval_from_issues.py:30,72` — `max_iterations: 5` / `max_iterations: 50`
- `scripts/tests/test_verify_issue_loop.py:34` — `max_iterations: 20`

### Tests — FSM executor and persistence

_Added by `/ll:refine-issue` — missing from original Integration Map:_

- `scripts/tests/test_fsm_executor.py` — **81 `max_iterations` references**; not in the original list. Uses `FSMLoop(max_iterations=N)` as the step cap across many fixtures, and `assert result.terminated_by == "max_iterations"` in multiple places. After BUG-2204:
  - All `FSMLoop(max_iterations=N)` constructs → `FSMLoop(max_steps=N)` (step cap)
  - All `result.terminated_by == "max_iterations"` → `"max_steps"` (step-cap termination string)
  - Test method `test_max_iterations_respected` (`:169`) → `test_max_steps_respected`; `TestMaxIterationsSummaryHook` (`:7663`) → `TestMaxStepsSummaryHook`

- `scripts/tests/test_fsm_persistence.py:944-996` — `TestFinalStatus.test_final_status_interrupted_on_max_iterations` and `test_final_status_interrupted_with_on_max_iterations_summary`. Uses `FSMLoop(max_iterations=2, on_max_iterations="summarize")` in fixture and asserts `result.terminated_by == "max_iterations"`. After BUG-2204:
  - `max_iterations=2` → `max_steps=2`
  - `on_max_iterations="summarize"` → `on_max_steps="summarize"`
  - `terminated_by == "max_iterations"` → `"max_steps"`
  - Rename both test methods to `test_final_status_interrupted_on_max_steps` and `test_final_status_interrupted_with_on_max_steps_summary`

- `scripts/tests/test_fsm_validation.py:1533-1585` — `TestOnMaxIterationsValidation` class (3 tests). Tests `on_max_iterations` as a recognized top-level key and valid/invalid state references. After BUG-2204 renames `on_max_iterations` → `on_max_steps`, these tests must be updated:
  - Rename class → `TestOnMaxStepsValidation`
  - Update `loop_yaml.write_text(... + "on_max_iterations: summarize\n")` → `on_max_steps: summarize`
  - Update `FSMLoop(..., on_max_iterations="ghost_state")` and `on_max_iterations="summarize"` → `on_max_steps=...`
  - Update error path assertion (`"on_max_iterations" in e.path` → `"on_max_steps"`)
  - Add a new `TestOnMaxIterationsValidation` class for the iteration-cap field (new semantics)

- `scripts/tests/test_general_task_loop.py:1073-1074` — `test_on_max_iterations_set_to_summarize_partial` asserts `raw_data.get("on_max_iterations") == "summarize_partial"`. After BUG-2204 migrates `general-task.yaml`'s `on_max_iterations:` → `on_max_steps:`, this test must assert `raw_data.get("on_max_steps") == "summarize_partial"`.

- `scripts/tests/test_ll_loop_commands.py:3092,3131,3182,3219` — Four additional `Namespace(max_iterations=None)` constructs not listed in the issue's existing test entries. Rename to `Namespace(max_steps=None, max_iterations=None)`. Also `:4154`: `argparse.Namespace(max_iterations=1, scenario=None)` → `Namespace(max_steps=1, scenario=None)`.

### Tests — `state_enter` payload field (conditional: only if `"iteration"` renamed)

Per BUG-2011 guidance (step 29): keep `"iteration"` as the step-count field name; add `"iteration_count"` as a new parallel field. If this guidance is followed, these tests do NOT need changes:
- `scripts/tests/test_events.py:84-89`
- `scripts/tests/test_usage_reporter.py`
- `scripts/tests/test_loop_run_analytics.py:88-350`
- `scripts/tests/test_fsm_interpolation.py:94`
- `scripts/tests/test_usage_journal.py:106`
- `scripts/tests/test_ll_loop_commands.py:1577,3040`
- `scripts/tests/test_ll_loop_state.py:355`

If the field IS renamed, update all of the above. Confirm the decision before starting.

### New tests to WRITE

- `scripts/tests/test_ll_loop_display.py` — add tests for `Max steps:` and `Max iterations:` header lines when both caps are set
- `scripts/tests/test_cli_loop_dispatch.py` — new `test_max_iterations_forwarded` for iteration-cap flag
- `scripts/tests/test_fsm_schema_fuzz.py:264-268` — verify Hypothesis dict-based `fsm["max_iterations"]` routes to `max_steps` via `from_dict()` alias (no semantic shift for dict construction)

### Tests — built-in loop structure assertions (break when loop YAMLs are renamed)

_Wiring pass added by `/ll:wire-issue` — these test files assert `data.get("max_iterations") > 0` on built-in loop YAML data; they break when loop YAMLs are renamed to `max_steps`:_

- `scripts/tests/test_builtin_loops.py` — 13 `test_max_iterations_and_timeout` methods across loop test classes (`:598`, `:720`, `:3370`, `:3485`, `:3610`, `:3730`, `:3840`, `:3995`, `:4102`, `:4488`, `:4613`, `:4792`, `:6118`): rename to `test_max_steps_and_timeout`; `data.get("max_iterations", 0) > 0` → `data.get("max_steps", 0) > 0`
- `scripts/tests/test_audit_loop_run_skill.py:337` — `spec.get("max_iterations", 0) > 30` → `spec.get("max_steps", 0) > 30`
- `scripts/tests/test_rn_plan.py:118` — `data.get("max_iterations") == 50` → `data.get("max_steps") == 50`
- `scripts/tests/test_rn_plan_apo.py:69` — `resolved_data.get("max_iterations") == 20` → `resolved_data.get("max_steps") == 20`
- `scripts/tests/test_loop_composer_adaptive.py:88` — `loop_data.get("max_iterations", 0) >= 200` → `loop_data.get("max_steps", 0) >= 200`
- `scripts/tests/test_deep_research_arxiv.py:111` — `resolved_data.get("max_iterations") == 30` → `resolved_data.get("max_steps") == 30`
- `scripts/tests/test_deep_research.py:124` — `data.get("max_iterations") == 30` → `data.get("max_steps") == 30`

### Tests — FSMLoop constructor and inline YAML in additional test files

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_state_feed_renderer.py:22,380,426` — `FSMLoop(max_iterations=N)` constructions in test helpers → `FSMLoop(max_steps=N)` (after BUG-2204 renames the field)
- `scripts/tests/test_ll_loop_errors.py:261` — inline YAML fixture `max_iterations: 100` → `max_steps: 100`
- `scripts/tests/test_adversarial_verify_loop.py:37,155,230` — inline YAML fixture `max_iterations: 20` → `max_steps: 20`
- `scripts/tests/test_generate_schemas.py:60` — `"max_iterations_summary"` in expected schema names set → `"max_steps_summary"` (once BUG-2204 renames the event type)
- `scripts/tests/test_session_store.py:2991` — `test_max_iterations_reached_summary_in_loop_event_types`: asserts `"max_iterations_reached_summary" in _LOOP_EVENT_TYPES`; verify this passes after BUG-2204 adds the new event type (no change expected — new event type is added, not renamed)

## Acceptance Criteria

- [ ] `ll-loop run <loop> --max-steps N` / `-n N` works; `--max-iterations N` works as full-pass cap
- [ ] `ll-loop info <loop>` and run header show `Max steps: N` and `Max iterations: N` (when set) as separate lines
- [ ] `ll-loop validate` recognizes `max_steps`, `on_max_steps`, `max_iterations` (iteration cap), `on_max_iterations` as valid top-level keys; legacy `max_iterations:` YAML key no longer emits unknown-key warning
- [ ] `ll-loop simulate` respects `--max-steps` and `--max-iterations` flags
- [ ] All skill files and docs consistently use `max_steps` for the per-step safety backstop and `max_iterations` for the full-pass cap
- [ ] All tests pass: `python -m pytest scripts/tests/`

## Implementation Steps

- Work through file groups in order: CLI argparse → validation.py → display strings → loop YAMLs → skills → docs → tests
- Run `python -m pytest scripts/tests/` after each group to isolate breakage
- All changes in this issue are string/symbol renames — if any change requires new logic, it belongs in BUG-2204

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. **Rename 84 built-in loop YAML files** — `scripts/little_loops/loops/*.yaml`: `max_iterations: N` → `max_steps: N`; also rename `on_max_iterations: max_iterations_summary` → `on_max_steps: max_steps_summary` in `cua-agent-desktop.yaml:17`
2. **Update `scripts/little_loops/fsm/fsm-loop-schema.json`** — add `"max_steps"` property alongside `"max_iterations"` (now the pass-cap); add `"on_max_steps"` property
3. **Update `skills/create-loop/templates.md`** — rename 6 template YAML instances and 5 placeholder list entries: `{{max_iterations}}` → `{{max_steps}}`
4. **Update `.claude/CLAUDE.md`** — update 3 prose occurrences of `max_iterations` in Loop Authoring section (`:169`, `:175`, `:184`) to `max_steps`
5. **Update `scripts/tests/test_builtin_loops.py`** — rename 13 `test_max_iterations_and_timeout` → `test_max_steps_and_timeout`; update 13 `data.get("max_iterations", 0) > 0` assertions → `data.get("max_steps", 0) > 0`
6. **Update additional loop-structure assertion tests** — `test_audit_loop_run_skill.py:337`, `test_rn_plan.py:118`, `test_rn_plan_apo.py:69`, `test_loop_composer_adaptive.py:88`, `test_deep_research_arxiv.py:111`, `test_deep_research.py:124`
7. **Update FSMLoop constructor and inline YAML in additional test files** — `test_state_feed_renderer.py:22,380,426`, `test_ll_loop_errors.py:261`, `test_adversarial_verify_loop.py:37,155,230`
8. **Update schema name tests** — `test_generate_schemas.py:60`: `"max_iterations_summary"` → `"max_steps_summary"`

## Impact

- **Priority**: P2 — Terminology footgun affecting all loop authors and users; confusing `max_iterations` semantics have caused mis-configuration across multiple loop files and skills; tracked as part of BUG-2011
- **Effort**: Large — Spans CLI argparse, display strings, 30+ test files, 8+ skill files, 6+ documentation files, and loop YAML templates; work is mechanical but high-volume
- **Risk**: Low — Pure string/symbol renames with no new logic (all logic changes are in BUG-2204); existing test suite detects regressions introduced by missed renames
- **Breaking Change**: Yes — `--max-iterations` CLI flag shifts meaning from step cap to full-pass cap; `FSMLoop.max_iterations` attribute meaning changes; existing loop YAMLs using `max_iterations: N` for step control are aliased via BUG-2204 migration

## Session Log
- `/ll:wire-issue` - 2026-06-17T19:11:24 - `11d130ef-9049-4669-9dc2-1abb1e183783.jsonl`
- `/ll:refine-issue` - 2026-06-17T18:58:23 - `e294ecee-9fd3-4971-b269-55942fc77737.jsonl`
- `/ll:format-issue` - 2026-06-17T18:39:42 - `3f8801e9-530a-4920-9ab4-609f5fbd927c.jsonl`
- Decomposed from BUG-2011 - 2026-06-17
