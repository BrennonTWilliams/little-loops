---
id: ENH-1964
type: ENH
priority: P2
status: open
captured_at: '2026-06-05T21:16:36Z'
discovered_date: 2026-06-05
discovered_by: capture-issue
labels:
- test-coverage
- captured
parent: EPIC-1967
decision_needed: false
confidence_score: 90
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1964: Add CLI Layer Tests for Sprint and Loop Subpackages

## Summary

The user-facing CLI layer for sprint and loop commands has zero or near-zero test coverage despite containing the highest-risk code in the project. `cli/loop/layout.py` alone is 1,981 lines of TUI rendering with no tests. Add CLI-layer tests starting with the sprint CLI (highest risk/effort ratio), then loop TUI, then loop dispatch.

## Context

Identified during a comprehensive test suite audit. While the domain model for sprints and loops is well-tested (92 tests in `test_sprint.py`, 26 integration tests in `test_sprint_integration.py`), the CLI layer that users invoke has zero coverage. If someone refactors the TUI rendering engine, no test catches a regression.

## Current Behavior

### Loop CLI (`cli/loop/`) — 11 files, ~7,274 lines total

| Module | Lines | Test Status |
|---|---|---|
| `cli/loop/layout.py` | 1,981 | **Zero tests** — TUI rendering engine (Sugiyama pipeline, character-grid diagram rendering) |
| `cli/loop/_helpers.py` | 1,420 | **Zero tests** — `StateFeedRenderer`, pinned-pane layout, `run_foreground()`, `run_background()` |
| `cli/loop/info.py` | 1,253 | **Minimal tests** — `cmd_show()`, `cmd_list()`, `cmd_history()`, `cmd_fragments()` dispatch untested |
| `cli/loop/__init__.py` | 722 | **Zero tests** — `main_loop()` dispatcher with 12 subcommands + shorthand |
| `cli/loop/lifecycle.py` | 664 | **Partially tested** — `cmd_status()`, `cmd_stop()`, `cmd_resume()`, `cmd_monitor()` tested in `test_cli_loop_lifecycle.py` |
| `cli/loop/run.py` | 437 | **Zero tests** — `cmd_run()` foreground/background/dry-run orchestration |
| `cli/loop/next_loop.py` | 334 | **Partially tested** — `cmd_next_loop()` tested in `test_loop_suggester.py`; `LoopCandidate`, scoring functions untested |
| `cli/loop/testing.py` | 268 | **Zero tests** — `cmd_test()`, `cmd_simulate()` |
| `cli/loop/diagram_modes.py` | 123 | **Zero tests** — `DiagramFacets`, `resolve_facets()`, preset expansions |
| `cli/loop/config_cmds.py` | 66 | **Zero tests** — `cmd_validate()`, `cmd_install()` |
| `cli/loop/__main__.py` | 6 | **Trivial** — `python -m` entry point |

### Sprint CLI (`cli/sprint/`) — 7 files, ~1,869 lines total

| Module | Lines | Test Status |
|---|---|---|
| `cli/sprint/run.py` | 560 | **Zero tests** — `_cmd_sprint_run()` with signal handling, wave execution, `ParallelOrchestrator` |
| `cli/sprint/show.py` | 384 | **Zero tests** — `_cmd_sprint_show()`, dependency graph rendering, health summary |
| `cli/sprint/_helpers.py` | 271 | **Zero tests** — `_render_execution_plan()`, `_score_suffix()`, dependency analysis rendering |
| `cli/sprint/__init__.py` | 247 | **Zero tests** — `main_sprint()` with 7 subcommands + aliases |
| `cli/sprint/manage.py` | 215 | **Zero tests** — `_cmd_sprint_list()`, `_cmd_sprint_delete()`, `_cmd_sprint_analyze()` |
| `cli/sprint/edit.py` | 127 | **Zero tests** — `_cmd_sprint_edit()` |
| `cli/sprint/create.py` | 65 | **Zero tests** — `_cmd_sprint_create()` |

Total untested CLI surface: ~9,100 lines (sprint + loop). Sprint CLI has **zero CLI-layer test coverage**; loop CLI has partial coverage for lifecycle and suggester modules only.

## Expected Behavior

- Sprint CLI commands (`create`, `edit`, `manage`, `run`, `show`) have tests covering argument parsing, error handling, and happy-path execution
- Loop CLI has tests for `main_loop()` dispatch, info display, and non-TUI commands
- TUI rendering (`layout.py`) has snapshot tests or pure-function extraction with unit tests
- CLI-layer tests follow `argparse` testing patterns already established in the codebase
- Test coverage for `cli/` rises from near-zero to ≥60%

## Motivation

- **Highest risk gap**: `layout.py` at 1,981 lines with zero tests — any refactor is a blind change
- **User-facing**: CLI bugs directly impact user experience; domain tests don't catch arg-parsing or output formatting regressions
- **Blocking refactoring**: ENH-839 (split `layout.py` into focused modules) is high-risk without test coverage
- **Quality signal**: A green test suite that doesn't test the primary user interface is misleading

## Current Pain Point

Developers can refactor the TUI rendering engine, break the main loop dispatcher, or mishandle CLI arguments — and the 9,968-test suite stays green because none of it touches the CLI layer. The only way to catch regressions is manual testing, which doesn't scale.

## Proposed Solution

### Phase 1: Sprint CLI (highest ROI — zero coverage, user-facing, 7 files / ~1,869 lines)

**Argument parsing tests** using Pattern 3 (inline parser construction):
- `main_sprint()` at `__init__.py:48` — test all 7 subcommands route correctly (create, run, list, show, edit, delete, analyze) and their aliases (`r`, `l`, `s`, `e`, `del`, `a`)
- `--handoff-threshold` range validation at `__init__.py:240` — test `parser.error()` for values <1 or >100
- Shared args from `cli_args.py`: `--dry-run`/`-n`, `--resume`/`-r`, `--max-workers`/`-w`, `--timeout`, `--skip`, `--only`, `--type`, `--label`, `--skip-analysis`, `--quiet`

**Command handler tests** using Pattern 2 (direct `argparse.Namespace` + `capsys`):
- `_cmd_sprint_create()` at `create.py:12` — test issue ID parsing (comma-separated, uppercased), `--skip` filter, `--type` filter, invalid ID warnings, `SprintOptions` construction
- `_cmd_sprint_edit()` at `edit.py:14` — test `--add` (validates new IDs, skips duplicates), `--remove`, `--prune` (detects `status: done`/`cancelled`), `--revalidate`
- `_cmd_sprint_list()` at `manage.py:16` — test `--verbose` and `--json` output modes via `capsys`
- `_cmd_sprint_delete()` at `manage.py:55` — test not-found returns 1
- `_cmd_sprint_analyze()` at `manage.py:66` — test cycle detection, wave computation, `--json` output

**Rendering function tests** (pure functions, deterministic output):
- `_score_suffix()` at `_helpers.py:15` — pure function, takes issue dict, returns str
- `_render_execution_plan()` at `_helpers.py:29` — deterministic rendering given waves+deps
- `_render_dependency_graph()` at `show.py:23` — ASCII dependency graph with unicode box-drawing
- `_render_health_summary()` at `show.py:95` — color-coded status line

**Integration tests** using Pattern 1 (sys.argv mock + monkeypatch.chdir):
- `_cmd_sprint_run()` at `run.py:95` — test dry-run path (outputs execution plan, doesn't execute), signal handling (KeyboardInterrupt → exit 130), state save/load/cleanup
- `_cmd_sprint_show()` at `show.py:154` — test full output, `--skip-analysis`, `--json` early-exit

**Domain fixtures to reuse**: `SprintManager(tmp_path)`, `BRConfig(tmp_path)`, `SprintOptions`, `SprintState.from_dict()`/`to_dict()`

### Phase 2: Loop CLI non-TUI (partial coverage exists, fill remaining gaps)

**Note**: `test_cli_loop_lifecycle.py` (2,568 lines) and `test_ll_loop_commands.py` (4,379 lines) already cover `lifecycle.py` commands and some command-level tests. Focus new tests on uncovered modules.

**Dispatcher tests** (Pattern 1 — sys.argv mock):
- `main_loop()` at `__init__.py:82` — test shorthand insertion (`ll-loop fix-types` → `ll-loop run fix-types`), all 12 subcommands route correctly, aliases (`r`, `c`, `val`, `l`, `st`, `res`, `h`, `t`, `sim`, `s`)

**config_cmds.py tests** (Pattern 2 — direct call):
- `cmd_validate()` at `config_cmds.py:11` — test valid/invalid loop YAML, returns 0/1
- `cmd_install()` at `config_cmds.py:37` — test copies built-in loop to `.loops/`

**info.py tests** (Pattern 2 + `capsys`):
- `cmd_list()` at `info.py:53` — test `--running`/`--status`/`--json`/`--builtin`/`--category`/`--label` filters, human-readable grouping, JSON output format
- `cmd_show()` at `info.py:936` — test header, state overview table, FSM diagram, verbose state details
- `cmd_history()` at `info.py:512` — test `--tail`/`--full`/`--verbose`/`--json`/`--event`/`--state`/`--since` filters
- `cmd_fragments()` at `info.py:1192` — test fragment listing from YAML library
- `_format_history_event()` at `info.py:266` — pure formatting, test event type dispatch
- `_print_state_overview_table()` at `info.py:855` — deterministic 4-column table

**next_loop.py tests** (Pattern 2):
- `LoopCandidate` dataclass at `next_loop.py:15` — test `to_dict()`, field defaults
- `_recency_score()` at `next_loop.py:86` — pure function, exponential decay with 7-day half-life
- `_score_loop()` at `next_loop.py:101` — weighted scoring: 50% frequency, 30% recency, 20% success rate
- `_scan_history()` at `next_loop.py:45` — filesystem mock, test metadata extraction

**testing.py tests** (Pattern 2):
- `cmd_test()` at `testing.py:13` — test single iteration, `--state`/`--exit-code` flags
- `cmd_simulate()` at `testing.py:175` — test `--scenario` (all-pass, all-fail, all-error, first-fail, alternating), `--max-iterations`

### Phase 3: TUI Rendering (layout.py + diagram_modes.py + StateFeedRenderer)

**Pure function extraction from `layout.py`** — these are deterministic string producers, ideal for unit tests:

| Function | Anchor | What It Does | Test Strategy |
|---|---|---|---|
| `_colorize_label()` | `layout.py:21` | Edge label ANSI colorization | String in → string out |
| `_colorize_diagram_labels()` | `layout.py:78` | Batch label colorization | List in → list out |
| `_get_state_badge()` | `layout.py:104` | Badge lookup by action_type | Dict lookup, pure |
| `_badge_display_width()` | `layout.py:138` | Badge width calculation | Number in → number out |
| `_box_inner_lines()` | `layout.py:148` | Box interior text layout | Text + width → list[str] |
| `_collect_edges()` | `layout.py:201` | Edge collection from FSM | FSM → edge list |
| `_bfs_order()` | `layout.py:233` | BFS node ordering | States + edges → list |
| `_trace_main_path()` | `layout.py:248` | Happy-path tracing | Edges + initial → path |
| `_classify_edges()` | `layout.py:273` | Branch/back-edge split | Edges + path → classified |
| `TopologyDetector.classify()` | `layout.py:300` | linear/tree/general classification | Edge sets → topology enum |
| `LayerAssigner.assign()` | `layout.py:345` | Longest-path layer assignment | Edge sets → layer map |
| `CrossingMinimizer.minimize()` | `layout.py:438` | Barycenter heuristic (3 sweeps) | Layer map → optimized |

**Snapshot/golden-file tests** for rendered diagram output (see ENH-1965 for infra setup):
- `_render_fsm_diagram()` at `layout.py:1581` — main diagram entry; test with fixtures from `scripts/tests/fixtures/fsm/` (~30+ YAML loops)
- `_render_layered_diagram()` at `layout.py:708` — core renderer; test each topology type (linear, tree, general)
- `_render_neighborhood_diagram()` at `layout.py:1712` — 1-hop neighborhood; test with/without prev_state
- `_render_horizontal_simple()` at `layout.py:1885` — single-row fallback
- `_draw_box()` at `layout.py:579` — character-grid box; test with/without highlight, with/without badge

**diagram_modes.py tests** (Pattern 2, all pure):
- `DiagramFacets` at `diagram_modes.py:41` — test frozen dataclass, field defaults
- `resolve_facets()` at `diagram_modes.py:93` — test all 6 presets (detailed, summary, clean, local, slim, oneline), modifier overrides
- `_parse_show_diagrams()` at `diagram_modes.py:75` — test valid topologies/presets, legacy mode rejection with migration hints

**StateFeedRenderer tests** (Pattern 2, mock-able):
- `StateFeedRenderer.handle_event()` at `_helpers.py:463` — test event dispatch (state_enter, action_start, action_complete, evaluate, route, max_iterations_summary, stall_detected)
- `_choose_pinned_layout()` at `_helpers.py:217` — test picks best layout variant that fits terminal height
- `_build_pinned_pane()` at `_helpers.py:460` — test composes header + diagram + state line + separator

## Success Metrics

- **Phase 1**: ≥80% coverage on `cli/sprint/` (from 0%)
- **Phase 2**: ≥60% coverage on `cli/loop/` non-TUI modules (from ~10%)
- **Phase 3**: ≥50% coverage on `cli/loop/layout.py` (from 0%)
- **Regression detection**: At least 1 real bug found per 500 lines of new test coverage

## Scope Boundaries

- **In scope**: `cli/sprint/`, `cli/loop/`, and their integration with domain models
- **In scope**: Snapshot testing setup as a dependency for TUI tests
- **Out of scope**: `cli/deps.py`, `cli/history.py`, `cli/messages.py` — tracked as ENH-1966
- **Out of scope**: E2E workflow tests (separate concern)
- **Out of scope**: Rewriting the TUI — this is about testing what exists

## API/Interface

No new public APIs. Tests will exercise existing CLI interfaces:
```python
# Example test patterns to establish
def test_sprint_create_parses_required_args():
    """Verify ll-sprint create --name X --issues A,B,C works."""
    ...

def test_loop_run_dispatches_to_correct_subcommand():
    """Verify main_loop() routes 'run' to the run handler."""
    ...
```

## Integration Map

### New Test Files to Create

| Test File | Covers | Priority |
|---|---|---|
| `scripts/tests/test_cli_sprint.py` | `main_sprint()`, `_cmd_sprint_create()`, `_cmd_sprint_edit()`, `_cmd_sprint_list()`, `_cmd_sprint_delete()`, `_cmd_sprint_analyze()` | Phase 1 |
| `scripts/tests/test_cli_sprint_run.py` | `_cmd_sprint_run()` signal handling, wave execution, state persistence | Phase 1 |
| `scripts/tests/test_cli_sprint_show.py` | `_cmd_sprint_show()`, `_render_dependency_graph()`, `_render_health_summary()`, `_print_composition()` | Phase 1 |
| `scripts/tests/test_cli_loop_dispatch.py` | `main_loop()` dispatcher, shorthand insertion, subcommand routing, `--handoff-threshold` validation | Phase 2 |
| `scripts/tests/test_cli_loop_info.py` | `cmd_list()`, `cmd_show()`, `cmd_history()`, `cmd_fragments()`, `_format_history_event()`, `_print_state_overview_table()` | Phase 2 |
| `scripts/tests/test_cli_loop_config.py` | `cmd_validate()`, `cmd_install()` from `config_cmds.py` | Phase 2 |
| `scripts/tests/test_cli_loop_next.py` | `LoopCandidate`, `_score_loop()`, `_recency_score()`, `_scan_history()` | Phase 2 |
| `scripts/tests/test_cli_loop_testing.py` | `cmd_test()`, `cmd_simulate()` | Phase 2 |
| `scripts/tests/test_cli_loop_layout.py` | `_render_fsm_diagram()`, `_render_layered_diagram()`, `_render_neighborhood_diagram()`, `_draw_box()`, `TopologyDetector`, `LayerAssigner`, `CrossingMinimizer`, `_box_inner_lines()`, `_colorize_label()` | Phase 3 |
| `scripts/tests/test_cli_loop_diagram_modes.py` | `DiagramFacets`, `resolve_facets()`, `_parse_show_diagrams()`, preset expansions | Phase 3 |
| `scripts/tests/test_cli_loop_renderer.py` | `StateFeedRenderer.handle_event()`, `_build_pinned_pane()`, `_render_pinned_pane()`, `_choose_pinned_layout()` | Phase 3 |

### Modules Under Test (Implementation)

**Sprint CLI** (`scripts/little_loops/cli/sprint/`):
- `__init__.py:48` — `main_sprint()` builds `ArgumentParser` with 7 subparsers, validates `--handoff-threshold`
- `create.py:12` — `_cmd_sprint_create(args, manager)` constructs `SprintOptions`, calls `manager.create()`
- `edit.py:14` — `_cmd_sprint_edit(args, manager)` handles `--add`/`--remove`/`--prune`/`--revalidate`
- `manage.py:16` — `_cmd_sprint_list()` with `--verbose`/`--json` modes; `_cmd_sprint_delete()`; `_cmd_sprint_analyze()` builds `DependencyGraph`, detects cycles, computes waves
- `run.py:95` — `_cmd_sprint_run()` signal handling, wave-by-wave execution, `ParallelOrchestrator`, state persistence
- `show.py:154` — `_cmd_sprint_show()` dependency graph rendering, health summary, `--skip-analysis`
- `_helpers.py:15` — `_score_suffix()`, `_render_execution_plan()`, `_render_dependency_analysis()`

**Loop CLI** (`scripts/little_loops/cli/loop/`):
- `__init__.py:82` — `main_loop()` shorthand insertion, 12 subcommands + aliases
- `run.py:29` — `_parse_program_md()`; `run.py:89` — `cmd_run()` foreground/background/dry-run orchestration
- `layout.py:300` — `TopologyDetector` classifies FSM topology; `layout.py:345` — `LayerAssigner` Sugiyama layer assignment; `layout.py:438` — `CrossingMinimizer` barycenter heuristic; `layout.py:1581` — `_render_fsm_diagram()` main entry; `layout.py:1712` — `_render_neighborhood_diagram()`
- `info.py:53` — `cmd_list()` with `--running`/`--status`/`--category`/`--label` filters; `info.py:512` — `cmd_history()`; `info.py:936` — `cmd_show()` diagram + state table; `info.py:1192` — `cmd_fragments()`
- `lifecycle.py:190` — `cmd_status()`; `lifecycle.py:287` — `cmd_stop()` SIGTERM/SIGKILL escalation; `lifecycle.py:362` — `cmd_resume()`; `lifecycle.py:558` — `cmd_monitor()` live tail
- `config_cmds.py:11` — `cmd_validate()`; `config_cmds.py:37` — `cmd_install()`
- `testing.py:13` — `cmd_test()` single iteration; `testing.py:175` — `cmd_simulate()` with `--scenario`
- `next_loop.py:15` — `LoopCandidate` dataclass; `next_loop.py:101` — `_score_loop()` weighted scoring; `next_loop.py:215` — `cmd_next_loop()`
- `diagram_modes.py:41` — `DiagramFacets` dataclass; `diagram_modes.py:93` — `resolve_facets()` preset resolution
- `_helpers.py:58` — `_TeeWriter`; `_helpers.py:463` — `StateFeedRenderer`; `_helpers.py:960` — `run_background()`; `_helpers.py:1104` — `run_foreground()`

### Shared Dependencies

- `scripts/little_loops/cli_args.py` — `add_dry_run_arg()`, `add_config_arg()`, `add_handoff_threshold_arg()`, `add_context_limit_arg()`, `parse_issue_ids()`, `parse_issue_types()` — used by both sprint and loop CLI
- `scripts/little_loops/cli/output.py` — `print_json()`, `colorize()`, `terminal_width()`, `strip_ansi()`
- `scripts/little_loops/sprint.py:23` — `SprintOptions`, `sprint.py:64` — `SprintState`, `sprint.py:122` — `Sprint`, `sprint.py:210` — `SprintManager`
- `scripts/little_loops/fsm/schema.py` — `FSMLoop`, `StateConfig`, `EvaluateConfig`, `RouteConfig`
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor`, `LoopState`
- `scripts/little_loops/fsm/validation.py` — `load_and_validate()`
- `scripts/little_loops/fsm/concurrency.py` — `LockManager`
- `scripts/little_loops/fsm/rate_limit_circuit.py` — `RateLimitCircuit`
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues()`, `get_execution_waves()`
- `scripts/little_loops/dependency_mapper.py` — `analyze_dependencies()`
- `scripts/little_loops/parallel/orchestrator.py` — `ParallelOrchestrator`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/analytics/variance.py:219` — lazy-imports `load_loop` from `cli.loop._helpers`
- `scripts/little_loops/fsm/validation.py:354` — lazy-imports `resolve_loop_path` from `cli.loop._helpers`
- `scripts/little_loops/fsm/executor.py:516` — lazy-imports `resolve_loop_path` from `cli.loop._helpers`
- `scripts/little_loops/fsm/fragments.py:207` — lazy-imports `resolve_loop_path` from `cli.loop._helpers`
- `scripts/little_loops/cli/logs.py:13` — imports `_print_usage_summary` and symbols from `cli.loop.info`
- `scripts/little_loops/cli/issues/clusters.py:229` — lazy-imports `_draw_box` from `cli.loop.layout`
- `scripts/little_loops/cli/deps.py:321` — lazy-imports `Sprint` from `little_loops.sprint`
- `scripts/little_loops/loops/sprint-build-and-validate.yaml:52,111` — calls `ll-sprint list` / `ll-sprint run`
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:5` — references `ll-loop run sprint-refine-and-implement`
- `scripts/little_loops/loops/lib/cli.yaml:103` — calls `ll-sprint list`
- `scripts/pyproject.toml:55-56` — console_scripts entry points for `ll-loop` and `ll-sprint` (the CLI registration itself)

These are non-test consumers of the sprint/loop CLI modules. If the new tests reveal API issues that prompt signature changes, these callers may need updating.

### Existing Test Patterns to Follow

Four established CLI testing patterns, used consistently across the codebase:

1. **sys.argv mock + main entry point** (`test_ll_loop_integration.py`, `test_cli.py`):
   ```python
   monkeypatch.chdir(tmp_path)
   with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--dry-run"]):
       result = main_loop()
   assert result == 0
   ```

2. **Direct handler call with `argparse.Namespace`** (`test_sprint.py`, `test_ll_loop_commands.py`):
   ```python
   args = argparse.Namespace(sprint="test", dry_run=True, resume=False, ...)
   result = cli._cmd_sprint_run(args, manager, config)
   captured = capsys.readouterr()
   ```

3. **Inline parser construction for arg parsing tests** (`test_cli.py`, `test_cli_args.py`):
   ```python
   parser = argparse.ArgumentParser()
   add_dry_run_arg(parser)
   args = parser.parse_args(["--dry-run"])
   assert args.dry_run is True
   ```

4. **Subprocess E2E** (`test_cli_e2e.py`, marked `@pytest.mark.integration`):
   ```python
   result = subprocess.run(["ll-harness", "cmd", "echo hello"], capture_output=True, text=True)
   ```

### Existing Loop CLI Tests (do not duplicate)

These files already test some `cli/loop/` modules — new tests should fill gaps, not overlap:

| Test File | Lines | What It Covers |
|---|---|---|
| `test_cli_loop_lifecycle.py` | 2,568 | `cmd_status()`, `cmd_stop()`, `cmd_resume()`, `cmd_monitor()` from `lifecycle.py` |
| `test_ll_loop_commands.py` | 4,379 | Loop command-level tests (validate, install, list, show, run, history, test, simulate, next-loop, fragments) |
| `test_ll_loop_display.py` | ~4,000 | `_render_fsm_diagram()`, `_render_neighborhood_diagram()`, `DiagramFacets`, `resolve_facets()`, `_parse_show_diagrams()`, edge colorization, adaptive layout topologies, custom glyphs |
| `test_state_feed_renderer.py` | — | `StateFeedRenderer.handle_event()`, `_artifact_lines()` from `_helpers.py` |
| `test_ll_loop_execution.py` | — | `cmd_run()` execution, loop execution flow |
| `test_ll_loop_errors.py` | — | Loop error handling paths |
| `test_ll_loop_parsing.py` | — | `_parse_program_md()` from `run.py` |
| `test_ll_loop_program_md.py` | — | Program.md parsing from `cli.loop` |
| `test_ll_loop_integration.py` | 577 | Integration tests for loop runs |
| `test_ll_loop_state.py` | — | Loop state management |
| `test_loop_suggester.py` | — | `cmd_next_loop()` logic |
| `test_sprint_integration.py` | — | Sprint integration tests with `SprintManager` |
| `test_cli_loop_worktree.py` | — | Worktree setup/cleanup |
| `test_cli_loop_queue.py` | — | Queue mechanics |
| `test_cli_loop_background.py` | — | Background mode, `run_background()` |
| `test_loop_router.py` | — | FSM routing |
| `test_loop_run_analytics.py` | — | Run analytics |
| `test_cli_output.py` | — | CLI output formatting, imports `cmd_history` from `cli.loop.info` |

_Wiring pass added by `/ll:wire-issue`: test_ll_loop_display.py and test_state_feed_renderer.py already cover significant portions of the Phase 3 scope (layout.py rendering, diagram_modes.py, StateFeedRenderer). The proposed Phase 3 test files (`test_cli_loop_layout.py`, `test_cli_loop_diagram_modes.py`, `test_cli_loop_renderer.py`) must audit these files first to avoid duplicating existing tests._

### Test Fixtures Available (reuse)

- `scripts/tests/conftest.py` — `temp_project_dir`, `sample_config`, `config_file`, `issues_dir`, `temp_project`, `valid_loop_file`, `invalid_loop_file`, `loops_dir`, `events_file`
- `scripts/tests/fixtures/fsm/` — ~30+ YAML loop fixtures
- `scripts/tests/fixtures/issues/` — ~18 issue markdown fixtures
- `make_test_state()` / `make_test_fsm()` — domain object factories (duplicated in 6 test files: `test_ll_loop_state.py`, `test_ll_loop_integration.py`, `test_ll_loop_execution.py`, `test_review_loop.py`, `test_ll_loop_display.py`, `test_ll_loop_errors.py`; candidate for conftest extraction)

### Documentation

- `CONTRIBUTING.md:675` — Test guidelines section; update with CLI testing patterns
- `docs/development/TESTING.md` — Comprehensive testing patterns guide
- `docs/development/E2E_TESTING.md` — E2E CLI testing guide
- `docs/reference/OUTPUT_STYLING.md:161,244,257` — Documents the exact rendering output format for `_render_fsm_diagram()` (line 161), `_print_state_overview_table()` (line 244), and `_render_dependency_graph()` / `_render_health_summary()` (line 257). Tests should verify actual output against code behavior; if discrepancies are found, this doc may need updating alongside the tests. _Wiring pass added by `/ll:wire-issue`._

### Configuration

- `scripts/pyproject.toml:126-141` — pytest config: markers (`integration`, `slow`), `--strict-markers`, `--cov=little_loops`, 80% coverage minimum
- No new markers strictly needed; use existing `integration` marker for subprocess-based tests

## Implementation Steps

### Phase 1: Sprint CLI Tests

1. **Audit existing patterns** — Catalog the 4 CLI testing patterns used in `test_cli.py`, `test_cli_args.py`, `test_sprint.py`, and `test_cli_e2e.py`. Identify which conftest fixtures are reusable (`temp_project_dir`, `sample_config`, `issues_dir`, etc.).

2. **Create `scripts/tests/test_cli_sprint.py`** — Test `main_sprint()` dispatcher:
   - All 7 subcommands route correctly (create, run, list, show, edit, delete, analyze)
   - Aliases work (`r`, `l`, `s`, `e`, `del`, `a`, `delete`)
   - `--handoff-threshold` range validation (1–100, `parser.error()` otherwise)
   - Shared arg forwarding: `--dry-run`, `--resume`, `--config`, `--skip`, `--only`, `--type`, `--label`, `--skip-analysis`

3. **Create `scripts/tests/test_cli_sprint_commands.py`** — Test handler functions directly:
   - `_cmd_sprint_create()` at `create.py:12` — issue parsing, `SprintOptions` construction, invalid ID warnings
   - `_cmd_sprint_edit()` at `edit.py:14` — `--add`/`--remove`/`--prune`/`--revalidate` operations
   - `_cmd_sprint_list()` at `manage.py:16` — `--verbose` and `--json` output
   - `_cmd_sprint_delete()` at `manage.py:55` — not-found returns 1
   - `_cmd_sprint_analyze()` at `manage.py:66` — cycle detection, wave computation

4. **Create `scripts/tests/test_cli_sprint_show.py`** — Test rendering functions (all deterministic):
   - `_render_dependency_graph()` at `show.py:23` — ASCII graph output
   - `_render_health_summary()` at `show.py:95` — status line variants
   - `_render_execution_plan()` at `_helpers.py:29` — wave grouping, contention display
   - `_score_suffix()` at `_helpers.py:15` — score formatting
   - `_cmd_sprint_show()` at `show.py:154` — full output, `--skip-analysis`, `--json`

5. **Create `scripts/tests/test_cli_sprint_run.py`** — Test execution orchestration (integration):
   - Dry-run path outputs execution plan without executing
   - Signal handling: `KeyboardInterrupt` → exit 130
   - State persistence: `_load_sprint_state()` / `_save_sprint_state()` / `_cleanup_sprint_state()`
   - Error handling: `try/except Exception` → exit 1

6. **Measure Phase 1 coverage** — Run `python -m pytest scripts/tests/test_cli_sprint*.py --cov=little_loops.cli.sprint --cov-report=term`. Target: ≥80% on `cli/sprint/`.

### Phase 2: Loop CLI Non-TUI Tests

7. **Audit existing loop CLI test coverage** — Map what `test_ll_loop_commands.py` (4,379 lines), `test_cli_loop_lifecycle.py` (2,568 lines), and other loop test files already cover to avoid duplication.

8. **Create `scripts/tests/test_cli_loop_config.py`** — Test `config_cmds.py`:
   - `cmd_validate()` at `config_cmds.py:11` — valid/invalid loop YAML
   - `cmd_install()` at `config_cmds.py:37` — built-in loop copy to `.loops/`

9. **Create `scripts/tests/test_cli_loop_info.py`** — Test `info.py` display functions:
   - `cmd_list()` at `info.py:53` — filter flags, human-readable vs JSON output
   - `cmd_show()` at `info.py:936` — header, state table, FSM diagram inclusion
   - `cmd_history()` at `info.py:512` — `--tail`/`--full`/`--verbose`/`--json`/`--event`/`--state`/`--since`
   - `_format_history_event()` at `info.py:266` — event type dispatch formatting
   - `_print_state_overview_table()` at `info.py:855` — 4-column table output
   - `cmd_fragments()` at `info.py:1192` — fragment listing

10. **Create `scripts/tests/test_cli_loop_next.py`** — Test `next_loop.py`:
    - `LoopCandidate` at `next_loop.py:15` — `to_dict()`, field defaults
    - `_recency_score()` at `next_loop.py:86` — exponential decay calculation
    - `_score_loop()` at `next_loop.py:101` — weighted scoring (50/30/20)
    - `_scan_history()` at `next_loop.py:45` — filesystem metadata extraction

11. **Create `scripts/tests/test_cli_loop_testing.py`** — Test `testing.py`:
    - `cmd_test()` at `testing.py:13` — single iteration, `--state`/`--exit-code` flags
    - `cmd_simulate()` at `testing.py:175` — scenario variants, `--max-iterations`

12. **Measure Phase 2 coverage** — Target: ≥60% on `cli/loop/` non-TUI modules (from current ~25% partial coverage).

### Phase 3: TUI Rendering Tests

13. **Set up snapshot testing infra** (ENH-1965 dependency) — Install `syrupy` or `pytest-snapshot`, configure in `pyproject.toml`, create snapshot directory.

14. **Extract and test pure layout functions** — Create `scripts/tests/test_cli_loop_layout.py`:
    - `_colorize_label()` at `layout.py:21` — string transformation
    - `_get_state_badge()` at `layout.py:104` — badge lookup
    - `_badge_display_width()` at `layout.py:138` — width calculation
    - `_box_inner_lines()` at `layout.py:148` — text layout
    - `_collect_edges()` at `layout.py:201` — edge extraction from FSM
    - `_bfs_order()` at `layout.py:233` — BFS ordering
    - `_trace_main_path()` at `layout.py:248` — happy-path tracing
    - `_classify_edges()` at `layout.py:273` — edge classification
    - `TopologyDetector.classify()` at `layout.py:300` — topology detection (linear/tree/general)
    - `LayerAssigner.assign()` at `layout.py:345` — layer assignment
    - `CrossingMinimizer.minimize()` at `layout.py:438` — crossing minimization

15. **Add snapshot tests for diagram rendering** — Using FSM fixtures from `scripts/tests/fixtures/fsm/`:
    - `_render_fsm_diagram()` at `layout.py:1581` — each topology type
    - `_render_layered_diagram()` at `layout.py:708` — edge label variants
    - `_render_neighborhood_diagram()` at `layout.py:1712` — with/without prev_state
    - `_render_horizontal_simple()` at `layout.py:1885` — single-state fallback
    - `_draw_box()` at `layout.py:579` — with/without highlight, with/without badge

16. **Create `scripts/tests/test_cli_loop_diagram_modes.py`** — Test `diagram_modes.py`:
    - `DiagramFacets` at `diagram_modes.py:41` — frozen dataclass
    - `resolve_facets()` at `diagram_modes.py:93` — all 6 presets, modifier overrides
    - `_parse_show_diagrams()` at `diagram_modes.py:75` — valid topologies, legacy mode rejection

17. **Create `scripts/tests/test_cli_loop_renderer.py`** — Test `StateFeedRenderer`:
    - `handle_event()` at `_helpers.py:463` — event dispatch for all event types
    - `_build_pinned_pane()` at `_helpers.py:460` — pane composition
    - `_choose_pinned_layout()` at `_helpers.py:217` — layout variant selection

18. **Measure Phase 3 coverage** — Target: ≥50% on `cli/loop/layout.py` (from 0%), ≥80% on `diagram_modes.py`.

### Final

19. Run full test suite: `python -m pytest scripts/tests/ -v --tb=short`
20. Run coverage report: `python -m pytest scripts/tests/ --cov=little_loops.cli --cov-report=term-missing`
21. Update `CONTRIBUTING.md:675` — document CLI testing patterns discovered during implementation

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be accounted for during implementation:_

22. **Audit `test_ll_loop_display.py` and `test_state_feed_renderer.py` before Phase 3** — these files already extensively test `layout.py` rendering functions (`_render_fsm_diagram()`, `_render_neighborhood_diagram()`), `DiagramFacets`, `resolve_facets()`, `_parse_show_diagrams()`, and `StateFeedRenderer`. The proposed Phase 3 test files (`test_cli_loop_layout.py`, `test_cli_loop_diagram_modes.py`, `test_cli_loop_renderer.py`) must only add tests for paths NOT already covered; otherwise they duplicate existing coverage.

23. **Re-scope Phase 2 test files against `test_ll_loop_commands.py`** — this 4,379-line file already covers `cmd_validate`, `cmd_install`, `cmd_list`, `cmd_show`, `cmd_history`, `cmd_fragments`, `cmd_test`, `cmd_simulate`, `cmd_next_loop`, and `cmd_audit_meta`. The proposed `test_cli_loop_info.py`, `test_cli_loop_config.py`, `test_cli_loop_next.py`, and `test_cli_loop_testing.py` should fill only the gaps not covered by `test_ll_loop_commands.py`.

24. **Consider extracting `make_test_state`/`make_test_fsm` to `conftest.py`** — duplicated in 6 test files. Extraction touches `test_ll_loop_state.py`, `test_ll_loop_integration.py`, `test_ll_loop_execution.py`, `test_review_loop.py`, `test_ll_loop_display.py`, `test_ll_loop_errors.py`. This reduces duplication for the new tests too.

25. **Verify `docs/reference/OUTPUT_STYLING.md:161,244,257` against actual rendering output** — if the new tests reveal discrepancies between documented and actual FSM diagram / state table / sprint visualization output, update the doc.

26. **Check non-test callers don't break** — `analytics/variance.py`, `fsm/validation.py`, `fsm/executor.py`, `fsm/fragments.py`, `cli/logs.py`, `cli/issues/clusters.py`, `cli/deps.py` all import from `cli.loop` or `cli.sprint` modules. If the tests discover API issues that prompt signature changes, these callers need updating.

## Backwards Compatibility

- No breaking changes — purely additive (new test files)
- Existing tests continue to pass unchanged

## Impact

- **Priority**: P2 — Critical coverage gap in user-facing code; blocks safe refactoring
- **Effort**: Large — ~6,500 lines of untested code across two subpackages; phased approach needed
- **Risk**: Low — Test-only changes; no production code modifications
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | CLI architecture and module organization |
| [API.md](../../docs/reference/API.md) | CLI command reference and expected behaviors |
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Test guidelines and patterns |

## Labels

`test-coverage`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-05_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- **Broad scope**: 11 test files across 2 CLI subpackages introduce coordination complexity — Phase 1 should complete before Phase 2 begins (Criterion A: 14/25, breadth 5/12)
- **Low existing coverage in targeted modules**: Sprint CLI has zero dedicated CLI test files, loop CLI non-TUI has ~25% partial coverage — test authors must reverse-engineer expected behavior from untested code (Criterion B: 10/25)
- **Existing partial sprint CLI tests**: `test_sprint.py` already contains `_cmd_sprint_run` (signal handling, error wrapping) and `_cmd_sprint_list` tests; `test_cli.py` also tests `_cmd_sprint_list`. The proposed `test_cli_sprint.py` and `test_cli_sprint_run.py` must audit these to avoid duplicating existing coverage.

## Session Log
- `/ll:wire-issue` - 2026-06-05T23:13:33 - `69e4573b-50e5-4f17-8a11-8b70287dd4be.jsonl`
- `/ll:format-issue` - 2026-06-05T22:10:47 - `6358220c-068a-48b5-be3c-15d795343473.jsonl`
- `/ll:capture-issue` - 2026-06-05T21:16:36Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5cc001a-5129-4d2d-807d-39a428af0331.jsonl`
- `/ll:refine-issue` - 2026-06-05T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6192044b-3935-4e42-a3d8-ebccec6a323b.jsonl`
- `/ll:confidence-check` - 2026-06-05T23:59:00Z - `98ad57cd-d1e7-4383-8d4f-aac5f9447a8f.jsonl`

## Status

**Open** | Created: 2026-06-05 | Priority: P2
