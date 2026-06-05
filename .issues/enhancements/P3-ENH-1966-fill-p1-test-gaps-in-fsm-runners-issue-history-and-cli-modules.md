---
id: ENH-1966
type: ENH
priority: P3
status: open
captured_at: "2026-06-05T21:16:36Z"
discovered_date: 2026-06-05
discovered_by: capture-issue
labels:
  - test-coverage
  - captured
parent: EPIC-1967
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

### Similar Patterns
- `scripts/tests/test_fsm_executor.py` — FSM test patterns to follow for runners
- `scripts/tests/test_session_store.py` — history DB test patterns for debt/quality
- `scripts/tests/test_cli_e2e.py` — CLI test patterns for deps/history/messages

### Tests
- All new test files are the deliverable

### Documentation
- No documentation changes expected

### Configuration
- No configuration changes expected

## Implementation Steps

1. Phase 1: Create `test_fsm_runners.py` — action dispatch, timeout, error propagation, state transitions
2. Phase 2: Create `test_issue_history_debt.py` — debt metrics with known test data
3. Phase 2: Create `test_issue_history_quality.py` — quality signals with edge cases
4. Phase 3: Create `test_cli_deps.py`, `test_cli_history.py`, `test_cli_messages.py` — argument parsing, happy paths
5. Run full test suite to confirm no regressions and measure coverage improvement

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
- `/ll:format-issue` - 2026-06-05T22:11:47 - `cb36cb81-33d2-4de4-bdf7-afd916199a11.jsonl`
- `/ll:capture-issue` - 2026-06-05T21:16:36Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5cc001a-5129-4d2d-807d-39a428af0331.jsonl`

## Status

**Open** | Created: 2026-06-05 | Priority: P3
