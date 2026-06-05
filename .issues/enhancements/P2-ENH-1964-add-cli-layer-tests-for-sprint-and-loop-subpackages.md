---
id: ENH-1964
type: ENH
priority: P2
status: open
captured_at: "2026-06-05T21:16:36Z"
discovered_date: 2026-06-05
discovered_by: capture-issue
labels:
  - test-coverage
  - captured
parent: EPIC-1967
---

# ENH-1964: Add CLI Layer Tests for Sprint and Loop Subpackages

## Summary

The user-facing CLI layer for sprint and loop commands has zero or near-zero test coverage despite containing the highest-risk code in the project. `cli/loop/layout.py` alone is 1,981 lines of TUI rendering with no tests. Add CLI-layer tests starting with the sprint CLI (highest risk/effort ratio), then loop TUI, then loop dispatch.

## Context

Identified during a comprehensive test suite audit. While the domain model for sprints and loops is well-tested (92 tests in `test_sprint.py`, 26 integration tests in `test_sprint_integration.py`), the CLI layer that users invoke has zero coverage. If someone refactors the TUI rendering engine, no test catches a regression.

## Current Behavior

| Module | Lines | Test Status |
|---|---|---|
| `cli/loop/layout.py` | 1,981 | **Zero tests** — TUI rendering engine |
| `cli/loop/info.py` | 1,253 | **Zero tests** — loop info/status display |
| `cli/loop/__init__.py` | 722 | **Zero tests** — main_loop() dispatcher |
| `cli/loop/next_loop.py` | 334 | **Zero tests** |
| `cli/loop/config_cmds.py` | 66 | **Zero tests** |
| `cli/loop/testing.py` | 268 | **Zero tests** |
| `cli/loop/diagram_modes.py` | 123 | **Zero tests** — diagram rendering |
| `cli/sprint/create.py` | — | **Zero tests** |
| `cli/sprint/edit.py` | — | **Zero tests** |
| `cli/sprint/manage.py` | — | **Zero tests** |
| `cli/sprint/run.py` | — | **Zero tests** |
| `cli/sprint/show.py` | — | **Zero tests** |
| `cli/sprint/_helpers.py` | — | **Zero tests** |
| `cli/sprint/__init__.py` | — | **Zero tests** |

Total untested CLI surface: ~6,500+ lines across the loop and sprint subpackages.

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

**Phase 1: Sprint CLI (highest ROI)**
- Test `ll-sprint create/edit/manage/run/show` argument parsing
- Test error handling for invalid inputs, missing files, conflicting flags
- Leverage existing `test_sprint.py` domain fixtures

**Phase 2: Loop CLI (non-TUI)**
- Test `main_loop()` dispatch for known subcommands
- Test `info.py` output formatting with captured stdout
- Test `next_loop.py`, `config_cmds.py`

**Phase 3: TUI rendering**
- Extract pure functions from `layout.py` for unit testing
- Add snapshot/golden-file tests for rendered output (see ENH-1965)
- Test `diagram_modes.py` rendering paths

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

### Files to Modify
- `scripts/tests/` — new test files: `test_cli_sprint.py`, `test_cli_loop.py`, `test_cli_loop_layout.py`, etc.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/` — the modules under test
- `scripts/little_loops/cli/loop/` — the modules under test

### Similar Patterns
- `scripts/tests/test_sprint.py` — domain model tests; use same fixtures
- `scripts/tests/test_cli_e2e.py` — existing CLI E2E patterns to follow

### Tests
- New test files are the deliverable; no existing tests to update

### Documentation
- `CONTRIBUTING.md` — update test guidelines with CLI testing patterns

### Configuration
- `pyproject.toml` — may need `cli` marker for CLI-specific tests

## Implementation Steps

1. Audit existing CLI test patterns in `test_cli_e2e.py` and `test_sprint.py` for fixture reuse
2. Phase 1: Create `test_cli_sprint.py` covering create/edit/manage/run/show argument handling
3. Phase 2: Create `test_cli_loop.py` covering dispatch, info, next_loop, config_cmds
4. Phase 3: Extract pure functions from `layout.py`; create `test_cli_loop_layout.py`
5. Run full test suite and measure coverage improvement
6. Document CLI testing patterns in CONTRIBUTING.md

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

## Session Log
- `/ll:format-issue` - 2026-06-05T22:10:47 - `6358220c-068a-48b5-be3c-15d795343473.jsonl`
- `/ll:capture-issue` - 2026-06-05T21:16:36Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5cc001a-5129-4d2d-807d-39a428af0331.jsonl`

## Status

**Open** | Created: 2026-06-05 | Priority: P2
