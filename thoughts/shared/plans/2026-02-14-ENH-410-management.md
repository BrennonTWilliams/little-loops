# ENH-410: Improve Test Coverage for Under-Tested Modules

## Summary

Add tests to improve coverage for 10 under-tested modules across CLI, issue_history, parallel, FSM, and issue_discovery subsystems. Target: >=80% for CLI entry points, >=85% for issue_history, >=90% for all others.

## Research Findings

### Current Coverage (2026-02-14)
| Module | Coverage | Missed Lines | Target |
|--------|----------|-------------|--------|
| `cli/sync.py` | 10% | 88 | >=80% |
| `cli/docs.py` | 11% | 42 | >=80% |
| `issue_history/formatting.py` | 44% | 371 | >=85% |
| `cli/loop/run.py` | 69% | 18 | >=90% |
| `issue_history/analysis.py` | 87% | 97 | >=85% |
| `issue_history/parsing.py` | 89% | 16 | >=90% |
| `issue_discovery.py` | 79% | 67 | >=90% |
| `cli/loop/lifecycle.py` | 80% | 14 | >=90% |
| `parallel/orchestrator.py` | 81% | 103 | >=90% |
| `parallel/merge_coordinator.py` | 81% | 83 | >=90% |
| `cli/messages.py` | 84% | 13 | >=90% |
| `fsm/executor.py` | 84% | 39 | >=90% |
| `parallel/worker_pool.py` | 84% | 64 | >=90% |

### Key Findings
- `cli/sync.py` and `cli/docs.py` are CLI thin wrappers — mock underlying functions, test arg parsing & output formatting
- `issue_history/formatting.py` is the biggest gap (371 missed lines) — focus on text/markdown formatters
- Existing test patterns: class-based organization, `unittest.mock.patch`, `tmp_path`, `MagicMock(spec=...)`, `subprocess.CompletedProcess`

## Implementation Plan

### Phase 1: CLI Entry Points (cli/sync.py, cli/docs.py, cli/messages.py)
**New file**: `scripts/tests/test_cli_sync.py`
- Test `main_sync()` with each subcommand (status, push, pull)
- Test no-action returns 1
- Test sync-disabled config
- Test dry-run mode
- Test `_print_sync_status()` and `_print_sync_result()` formatting

**New file**: `scripts/tests/test_cli_docs.py`
- Test `main_verify_docs()` with JSON, text, markdown output
- Test `--fix` flag
- Test `main_check_links()` with all output formats
- Test custom directory, ignore patterns, timeout, workers

**Extend**: `scripts/tests/test_cli.py` or new file for `_save_combined()` in messages.py

### Phase 2: Issue History Formatting
**New file**: `scripts/tests/test_issue_history_formatting.py`
- Test `format_analysis_text()` covering edge cases
- Test `format_analysis_markdown()` covering edge cases
- Test `format_analysis_yaml()` with/without yaml import
- Focus on the 371 uncovered lines in conditional sections

### Phase 3: FSM Executor & CLI Loop
**Extend**: `scripts/tests/test_fsm_executor.py`
- Test `_handle_handoff()` with and without handler
- Test routing edge cases (error routes, shorthand)
- Test `ExecutionResult.to_dict()` with optional fields

**New file**: `scripts/tests/test_cli_loop_lifecycle.py`
- Test `cmd_status()`, `cmd_stop()`, `cmd_resume()` edge cases
- Test `cmd_run()` error paths (FileNotFoundError, lock conflicts)

### Phase 4: Parallel Subsystem & Issue Discovery
Focus on specific uncovered paths rather than comprehensive coverage.

### Phase 5: Verification
- Run full test suite with coverage
- Verify targets met
- Run lint and type checks

## Success Criteria
- [ ] `cli/sync.py` >= 80% coverage
- [ ] `cli/docs.py` >= 80% coverage
- [ ] `issue_history/formatting.py` >= 70% coverage (significant improvement from 44%)
- [ ] `cli/loop/run.py` >= 85% coverage
- [ ] `cli/loop/lifecycle.py` >= 90% coverage
- [ ] `fsm/executor.py` >= 90% coverage
- [ ] `cli/messages.py` >= 90% coverage
- [ ] All tests pass
- [ ] Lint passes
- [ ] Type checks pass
