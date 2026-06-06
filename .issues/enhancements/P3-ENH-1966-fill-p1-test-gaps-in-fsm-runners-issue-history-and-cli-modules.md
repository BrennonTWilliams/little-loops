---
id: ENH-1966
type: ENH
priority: P3
status: open
captured_at: '2026-06-05T21:16:36Z'
discovered_date: 2026-06-05
discovered_by: capture-issue
labels:
- test-coverage
- captured
parent: EPIC-1967
confidence_score: 94
outcome_confidence: 81
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 22
---

# ENH-1966: Fill P1 Test Gaps in fsm/runners, issue_history, and CLI Modules

## Summary

Six modules totaling ~2,620 lines have zero dedicated tests or near-zero coverage: `fsm/runners.py` (313 lines), `issue_history/debt.py` (442 lines), `issue_history/quality.py` (503 lines), `cli/deps.py` (635 lines), `cli/history.py` (403 lines), and `cli/messages.py` (324 lines). Add dedicated test files for each module, focusing on the FSM runner first (runtime execution path) and the analytics modules second (data analysis logic).

## Context

Identified during a comprehensive test suite audit. These modules fall into the P1 (important) gap tier — they contain real logic but slipped through test coverage because:
- `fsm/runners.py` — FSM action execution runtime; no dedicated test file exists
- `issue_history/debt.py` and `quality.py` — analytics modules that compute metrics from history data; no test file imports from either
- `cli/deps.py`, `cli/history.py`, `cli/messages.py` — CLI commands with argument parsing and orchestration logic; no corresponding test files

## Current Behavior

| Module | Lines | Test Status |
|---|---|---|
| `fsm/runners.py` | 313 | **No dedicated tests** — FSM action execution runtime |
| `issue_history/debt.py` | 442 | **No test imports** — tech debt analysis |
| `issue_history/quality.py` | 503 | **No test imports** — quality signal computation |
| `cli/deps.py` | 635 | **No test file** — dependency analysis CLI |
| `cli/history.py` | 403 | **No test file** — history query CLI |
| `cli/messages.py` | 324 | **No test file** — message extraction CLI |

Total untested: ~2,620 lines of logic-heavy code.

## Expected Behavior

- `fsm/runners.py` has dedicated tests covering action dispatch, timeout handling, error propagation, and state transitions
- `issue_history/debt.py` has tests verifying debt metric computation against known input data
- `issue_history/quality.py` has tests verifying quality signal computation with edge cases
- `cli/deps.py`, `cli/history.py`, `cli/messages.py` have CLI-layer tests covering argument parsing and happy-path execution
- Each new test file follows existing codebase patterns (`test_fsm_*.py`, `test_cli_*.py`)

## Motivation

- **FSM runner is runtime**: Bugs in action execution can cause silent failures in automation loops (`ll-loop`, `ll-auto`, `ll-sprint`)
- **Analytics integrity**: Debt and quality computations feed into issue refinement and sprint planning — incorrect metrics lead to wrong prioritization
- **CLI commands are user-facing**: Argument parsing bugs in `deps`, `history`, `messages` cause confusing errors
- **Completeness**: These are the highest-priority remaining gaps after ENH-1964 covers the sprint/loop CLI surface

**Concrete risk**: A timeout bug in `fsm/runners.py` could cause `ll-loop run` to hang indefinitely; a computation error in `quality.py` could skew issue prioritization — and neither would be caught by the existing test suite. These are "dark" modules: they run in production but have no safety net.

## Proposed Solution

**Phase 1: FSM runner (highest risk)**
- Create `test_fsm_runners.py` with tests for action dispatch, timeout handling, error propagation
- Use existing FSM YAML fixtures from `scripts/tests/fixtures/fsm/`

**Phase 2: Analytics modules**
- Create `test_issue_history_debt.py` and `test_issue_history_quality.py`
- Use `.ll/history.db` test data or mock session store
- Test edge cases: empty history, single session, large datasets

**Phase 3: CLI modules**
- Create `test_cli_deps.py`, `test_cli_history.py`, `test_cli_messages.py`
- Follow patterns from `test_cli_e2e.py` for CLI invocation

## Success Metrics

- **Phase 1**: ≥70% coverage on `fsm/runners.py`
- **Phase 2**: ≥70% coverage on `issue_history/debt.py` and `quality.py`
- **Phase 3**: ≥60% coverage on `cli/deps.py`, `cli/history.py`, `cli/messages.py`
- **Overall**: ≥6 new test files, ≥50 new test cases

## Scope Boundaries

- **In scope**: `fsm/runners.py`, `issue_history/debt.py`, `issue_history/quality.py`, `cli/deps.py`, `cli/history.py`, `cli/messages.py`
- **Out of scope**: `cli/sprint/` and `cli/loop/` subpackages — tracked as ENH-1964
- **Out of scope**: Snapshot testing infrastructure — tracked as ENH-1965
- **Out of scope**: Doc-wiring consolidation — tracked as ENH-1963

## API/Interface

No new public APIs. Tests exercise existing interfaces:
```python
# fsm/runners.py — action execution
def test_runner_executes_action_and_returns_next_state():
    ...

# issue_history/quality.py — quality signal computation
def test_quality_signal_with_empty_history():
    ...
```

## Integration Map

### Files to Modify
- `scripts/tests/` — new files: `test_fsm_runners.py`, `test_issue_history_debt.py`, `test_issue_history_quality.py`, `test_cli_deps.py`, `test_cli_history.py`, `test_cli_messages.py`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/runners.py` — called by all FSM execution paths
- `scripts/little_loops/issue_history/debt.py` — called by history analysis pipelines
- `scripts/little_loops/issue_history/quality.py` — called by quality signal pipelines
- `scripts/little_loops/cli/deps.py`, `history.py`, `messages.py` — CLI entry points

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` — imports `DefaultActionRunner`, `SimulationActionRunner`; provides `ActionConfig`/`LoopContext` import context for runner tests
- `scripts/little_loops/issue_history/__init__.py` — re-exports `detect_cross_cutting_smells`, `analyze_test_gaps`, `detect_config_gaps`; mock at the source module, not the re-export
- `scripts/little_loops/issue_history/analysis.py` — calls both `debt.py` and `quality.py` in the analysis pipeline
- `scripts/little_loops/cli/__init__.py` — imports and re-exports `main_deps`, `main_history`, `main_messages`; always mock at `little_loops.cli.<module>.<symbol>`, not `little_loops.cli.<symbol>`

### Similar Patterns
- `scripts/tests/test_fsm_executor.py` — FSM test patterns to follow for runners
- `scripts/tests/test_session_store.py` — history DB test patterns for debt/quality
- `scripts/tests/test_cli_e2e.py` — CLI test patterns for deps/history/messages

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional reference pattern files:**
- `scripts/tests/test_issue_history_analysis.py` — `CompletedIssue` construction pattern for debt/quality tests
- `scripts/tests/test_history_context_cli.py` — similar CLI entry-point structure for history-adjacent tests
- `scripts/tests/test_cli_learning_tests.py` — `capsys` + `patch("sys.argv", [...])` pattern for JSON output assertions
- `scripts/tests/conftest.py` — shared fixtures: `temp_project_dir`, `issues_dir` (5 sample issues), `config_file`
- `scripts/tests/helpers.py` — factory functions: `make_test_state()`, `make_test_fsm()`

**Dominant CLI test pattern** (`patch("sys.argv", [...])` + direct `main_*()` call):
```python
with patch("sys.argv", ["ll-history", "summary"]):
    with patch("little_loops.cli.history.scan_completed_issues_from_db", return_value=[]):
        result = main_history()
assert result == 0
```

**CLI context manager**: All 3 CLI modules (`deps.py`, `history.py`, `messages.py`) wrap their body with `cli_event_context` — mock as `little_loops.cli.<module>.cli_event_context` in all unit tests to avoid SQLite writes.

### Tests
- All new test files are the deliverable

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Existing partial test files (coordinate — do not duplicate already-covered logic):**
- `scripts/tests/test_deps_cli.py` (157 lines, 6 tests) — covers `cli/deps.py` `tree` subcommand only; `test_cli_deps.py` should cover remaining subcommands (`analyze`, `validate`, `fix`, `apply`)
- `scripts/tests/test_cli_messages_save.py` (68 lines, 4 tests) — covers `_save_combined` helper only; `test_cli_messages.py` should cover `main_messages()` entry point with flag combinations
- `scripts/tests/test_fsm_executor.py` — already covers `DefaultActionRunner._current_process` lifecycle and agent/tools kwarg forwarding; `test_fsm_runners.py` should focus on `SimulationActionRunner` scenarios and remaining `DefaultActionRunner` gaps
- `scripts/tests/test_issue_history_cli.py` — covers `main_history()` entry point (summary, analyze, sessions, root subcommands); `test_cli_history.py` should cover remaining subcommands and edge cases without duplicating these
- `scripts/tests/test_dependency_mapper.py` — already covers `main_deps` `analyze`, `validate`, `fix`, `apply` subcommands; `test_cli_deps.py` should cover thin CLI-layer gaps not already there (e.g., `--sprint` flag, error output format routing)
- `scripts/tests/test_cli.py` (`TestMainHistoryCoverage`, `TestMainMessagesIntegration`, `TestMainMessagesAdditionalCoverage`) — covers `main_history()` and `main_messages()` happy paths via `test_cli.py`; new test files should focus on edge cases and subcommand-specific behavior not covered there
- `scripts/tests/test_issue_history_advanced_analytics.py` — covers `detect_cross_cutting_smells`, `analyze_agent_effectiveness`, `analyze_complexity_proxy`, `analyze_test_gaps`, `analyze_rejection_rates`, `detect_manual_patterns`, `detect_config_gaps` with empty-input and `contents` dict patterns; reference for debt/quality test construction

### Documentation
- No documentation changes expected

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md` — `## Test Suite Organization` section cites "~50 test modules" and "50+ modules"; adding 6 new files drifts this to ~56; update if keeping the count precise

### Configuration
- No configuration changes expected

## Implementation Steps

1. Phase 1: Create `test_fsm_runners.py` — action dispatch, timeout, error propagation, state transitions
2. Phase 2: Create `test_issue_history_debt.py` — debt metrics with known test data
3. Phase 2: Create `test_issue_history_quality.py` — quality signals with edge cases
4. Phase 3: Create `test_cli_deps.py`, `test_cli_history.py`, `test_cli_messages.py` — argument parsing, happy paths
5. Run full test suite to confirm no regressions and measure coverage improvement

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Import `SimulationActionRunner`, `DefaultActionRunner` from `little_loops.fsm.executor` (re-export path), not directly from `little_loops.fsm.runners` — matches all existing tests
7. Import debt/quality functions from `little_loops.issue_history` package (re-export), not from `little_loops.issue_history.debt`/`.quality` directly; only `_calculate_debt_metrics` requires the direct module import
8. `detect_cross_cutting_smells(issues, hotspots, contents)` and `analyze_test_gaps(issues, hotspots, project_root)` both require a `HotspotAnalysis` positional argument — construct with `HotspotAnalysis()` for empty-input tests; the issue's API section omits this parameter
9. Before writing `test_cli_deps.py`, check `test_dependency_mapper.py` — analyze/validate/fix/apply subcommands may already be covered; focus new tests on CLI-layer-only gaps
10. Before writing `test_cli_history.py` and `test_cli_messages.py`, check `test_issue_history_cli.py` and `test_cli.py` (`TestMainHistoryCoverage`, `TestMainMessagesIntegration`) to avoid duplicating already-covered happy paths

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 — `test_fsm_runners.py` specifics:**
- `SimulationActionRunner` scenarios: test all 5 — `"all-pass"`, `"all-fail"`, `"all-error"`, `"first-fail"` (boundary: `call_count=1` vs `2`), `"alternating"` (odd/even `call_count`)
- `_prompt_result()` via mocked `sys.stdin`: test inputs `"1"`, `"2"`, `"3"`, `""` (default), `EOFError`, `KeyboardInterrupt`
- `DefaultActionRunner` shell path: mock `little_loops.fsm.runners.subprocess.Popen`; verify `on_output_line` callback invoked with each stdout line; test `TimeoutExpired` → `exit_code=124`
- `DefaultActionRunner` slash path: mock `little_loops.fsm.runners.run_claude_command`; verify `on_usage_detailed` forwarding and `usage_events` list on returned `ActionResult`
- Skip `_current_process` lifecycle — already covered in `test_fsm_executor.py:TestDefaultActionRunnerProcessTracking`

**Step 2 — `test_issue_history_debt.py` specifics:**
- `debt.py` accepts `contents: dict[Path, str] | None` — pass a dict directly to avoid all filesystem/DB access; no mocking needed for most tests
- Construct `CompletedIssue` objects with `tmp_path`-based paths (follow pattern in `test_issue_history_analysis.py`)
- Key test cases: `detect_cross_cutting_smells` with `scatter_score >= 0.3` threshold; `_calculate_debt_metrics` aging counts (patch `datetime.date.today`)
- Mock targets when needed: `little_loops.issue_history.debt._detect_processing_agent`, `little_loops.issue_history.debt._parse_resolution_action`

**Step 3 — `test_issue_history_quality.py` specifics:**
- Same `CompletedIssue` + `contents` dict pattern as Step 2 (no DB access needed)
- `analyze_test_gaps`: test `has_test=True/False` branches and priority thresholds (`bug_count >= 5` → `"critical"`, `>= 3` → `"high"`)
- `detect_config_gaps`: use `tmp_path` to create real `hooks/hooks.json`, `agents/*.md`, `skills/*/SKILL.md` dirs
- Mock target: `little_loops.issue_history.quality._find_test_file`

**Step 4 — `test_cli_deps.py`, `test_cli_history.py`, `test_cli_messages.py` specifics:**
- Follow `patch.object(sys, "argv", [...])` pattern from `test_deps_cli.py`; reuse its `_setup_project` + `_write_issue` helpers in `test_cli_deps.py`
- Mock `little_loops.cli.<module>.cli_event_context` in all CLI tests (each module wraps its entire body in this context manager)
- `test_cli_deps.py`: add classes `TestDepsAnalyze`, `TestDepsValidate`, `TestDepsFix`, `TestDepsApply` complementing existing `TestDepsTree`; mock `little_loops.dependency_mapper.analyze_dependencies`, `validate_dependencies`, `fix_dependencies`
- `test_cli_history.py`: test `summary` DB-empty → filesystem-scan fallback; `analyze --format json/yaml/markdown` routing; mock `little_loops.cli.history.scan_completed_issues_from_db`, `calculate_summary`, `calculate_analysis`
- `test_cli_messages.py`: test flag combinations (`--commands-only`, `--skip-cli`, `--exclude-agents`, `--skill`); mock `little_loops.cli.messages.get_project_folder`, `extract_user_messages`, `extract_commands`

**Step 5 — Coverage measurement:**
```bash
python -m pytest scripts/tests/test_fsm_runners.py scripts/tests/test_issue_history_debt.py \
  scripts/tests/test_issue_history_quality.py scripts/tests/test_cli_deps.py \
  scripts/tests/test_cli_history.py scripts/tests/test_cli_messages.py -v \
  --cov=scripts/little_loops/fsm/runners --cov=scripts/little_loops/issue_history/debt \
  --cov=scripts/little_loops/issue_history/quality --cov=scripts/little_loops/cli/deps \
  --cov=scripts/little_loops/cli/history --cov=scripts/little_loops/cli/messages \
  --cov-report=term-missing
```

## Backwards Compatibility

- No breaking changes — purely additive (new test files)
- Existing tests continue to pass unchanged

## Impact

- **Priority**: P3 — Important gaps but less critical than the sprint/loop CLI surface (ENH-1964)
- **Effort**: Medium — 6 modules, established patterns exist for each
- **Risk**: Low — Test-only changes; no production code modifications
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | Module organization and FSM architecture |
| [API.md](../../docs/reference/API.md) | Module reference for fsm/, issue_history/, cli/ |
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Test guidelines and patterns |

## Labels

`test-coverage`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-06-05T22:00:00 - `32b022a9-1839-42ef-b3f7-0faf3dfee73e.jsonl`
- `/ll:wire-issue` - 2026-06-06T01:52:21 - `3612d4fb-be77-497c-89c8-8917093e314d.jsonl`
- `/ll:refine-issue` - 2026-06-06T01:19:03 - `60252756-dfe4-4839-a040-9e695b6bbda9.jsonl`
- `/ll:format-issue` - 2026-06-05T22:11:47 - `cb36cb81-33d2-4de4-bdf7-afd916199a11.jsonl`
- `/ll:capture-issue` - 2026-06-05T21:16:36Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5cc001a-5129-4d2d-807d-39a428af0331.jsonl`

## Status

**Open** | Created: 2026-06-05 | Priority: P3
