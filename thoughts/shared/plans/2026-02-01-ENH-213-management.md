# ENH-213: Split large test files into focused modules - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-213-split-large-test-files-into-focused-modules.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

### Large Test Files Identified
1. **test_issue_history.py**: 3,586 lines with 50 test classes
2. **test_ll_loop.py**: 3,580 lines with 19 test classes (136 test methods)

### Key Discoveries

**From Research - test_issue_history.py** (`scripts/tests/test_issue_history.py`):
- Tests organized by functionality but all in single file
- No custom fixtures (uses built-in `tmp_path`, `capsys`)
- Imports 54 items from `little_loops.issue_history`
- Test classes cover: parsing, summary, analysis, CLI integration, and 11 types of advanced analytics

**From Research - test_ll_loop.py** (`scripts/tests/test_ll_loop.py`):
- Contains 2 helper functions: `make_test_state()`, `make_test_fsm()` (lines 29-77)
- Contains 6 local fixtures that should move to conftest.py before splitting
- Tests cover: argument parsing, commands, display formatting, integration, errors, compilation, execution

**Existing Split Patterns** (from codebase):
- FSM tests already split into 7 focused files: `test_fsm_compilers.py`, `test_fsm_evaluators.py`, `test_fsm_executor.py`, `test_fsm_interpolation.py`, `test_fsm_persistence.py`, `test_fsm_schema.py`, `test_fsm_compiler_properties.py`
- conftest.py already has shared fixtures with path helpers and temp directory fixtures
- Test helper functions are commonly defined in test files (e.g., `make_state()` in test_fsm_schema.py:38-76)

## Desired End State

### test_issue_history.py Split Into:

1. **test_issue_history_dataclasses.py** - Dataclass serialization tests
2. **test_issue_history_parsing.py** - Issue parsing and scanning
3. **test_issue_history_summary.py** - Summary calculation and formatting
4. **test_issue_history_analysis.py** - Core analysis functionality
5. **test_issue_history_advanced_analytics.py** - Hotspot, coupling, regression, test gaps, rejection, manual patterns, agent effectiveness, complexity, config gaps, cross-cutting smells
6. **test_issue_history_cli.py** - CLI integration tests

### test_ll_loop.py Split Into:

1. **test_ll_loop_parsing.py** - Argument parsing and path resolution
2. **test_ll_loop_commands.py** - Basic command unit tests (validate, list, history, tail)
3. **test_ll_loop_display.py** - Display formatting and serialization
4. **test_ll_loop_integration.py** - CLI integration tests
5. **test_ll_loop_state.py** - State management (stop, resume)
6. **test_ll_loop_errors.py** - Error handling and messages
7. **test_ll_loop_execution.py** - Compilation, execution, LLM flags, test, simulate

### How to Verify
- All tests pass: `python -m pytest scripts/tests/`
- No test name collisions
- Import references work correctly
- Test discovery still finds all tests

## What We're NOT Doing

- Not changing test logic or behavior - only moving code
- Not modifying conftest.py structure (only adding fixtures from test_ll_loop.py)
- Not refactoring test implementations
- Not changing test class or method names
- Not modifying source code being tested

## Problem Analysis

Large test files are difficult to navigate and maintain. The codebase already has examples of well-organized test splits (FSM tests split into 7 files). Following existing patterns will improve maintainability.

## Solution Approach

1. Move local fixtures from test_ll_loop.py to conftest.py
2. Split test_issue_history.py into 6 focused modules
3. Split test_ll_loop.py into 7 focused modules
4. Verify all tests still pass
5. Remove original large test files

## Implementation Phases

### Phase 1: Move Fixtures from test_ll_loop.py to conftest.py

#### Overview
Extract 6 local fixtures from test_ll_loop.py to conftest.py so they can be shared across split modules.

#### Changes Required

**File**: `scripts/tests/conftest.py`
**Changes**: Add 6 fixtures from test_ll_loop.py lines 235-433

```python
# Add after line ~215 (end of existing fixtures)

# =============================================================================
# FSM Loop Test Fixtures
# =============================================================================

@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory for loop tests."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    (project_dir / ".loops").mkdir()
    return project_dir


@pytest.fixture
def valid_loop_file(temp_project: Path) -> Path:
    """Create a valid loop YAML file for testing."""
    loop_file = temp_project / ".loops" / "valid-loop.yaml"
    loop_content = """
name: test-loop
initial: start
states:
  start:
    action: echo "hello"
    on_success: done
  done:
    terminal: true
"""
    loop_file.write_text(loop_content)
    return loop_file


@pytest.fixture
def invalid_loop_file(temp_project: Path) -> Path:
    """Create an invalid loop YAML file for testing."""
    loop_file = temp_project / ".loops" / "invalid-loop.yaml"
    loop_content = """
name: test-loop
initial: nonexistent
states:
  start:
    action: echo "hello"
    on_success: done
  done:
    terminal: true
"""
    loop_file.write_text(loop_content)
    return loop_file


@pytest.fixture
def loops_dir(tmp_path: Path) -> Path:
    """Create a .loops directory with test loop files."""
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    (loops_dir / "loop1.yaml").write_text("name: loop1\ninitial: start\nstates:\n  start:\n    terminal: true")
    (loops_dir / "loop2.yaml").write_text("name: loop2\ninitial: start\nstates:\n  start:\n    terminal: true")
    return loops_dir


@pytest.fixture
def events_file(tmp_path: Path) -> Path:
    """Create an events JSONL file for history tests."""
    events_path = tmp_path / "events.jsonl"
    events = [
        '{"timestamp": "2025-01-01T00:00:00", "state": "start", "action": "echo test"}',
        '{"timestamp": "2025-01-01T00:01:00", "state": "done", "action": ""}',
    ]
    events_path.write_text("\n".join(events))
    return events_path


@pytest.fixture
def many_events_file(tmp_path: Path) -> Path:
    """Create an events JSONL file with 10 events for tail tests."""
    events_path = tmp_path / "events.jsonl"
    events = [f'{{"timestamp": "2025-01-01T00:0{i}:00", "state": "state{i}", "action": "action{i}"}}' for i in range(10)]
    events_path.write_text("\n".join(events))
    return events_path
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py -v`

---

### Phase 2: Split test_issue_history.py into Focused Modules

#### Overview
Split test_issue_history.py (3,586 lines) into 6 focused test modules based on functionality.

#### Changes Required

**Step 2.1: Create test_issue_history_dataclasses.py**

Test classes to include:
- TestCompletedIssue (lines 58-92)
- TestHistorySummary (lines 94-141)
- TestPeriodMetrics (lines 502-558)
- TestSubsystemHealth (lines 560-577)
- TestTechnicalDebtMetrics (lines 590-617)
- TestHistoryAnalysis (lines 620-654)
- TestHotspot (lines 1026-1057)
- TestHotspotAnalysis (lines 1059-1079)
- TestExtractPathsFromIssue (lines 1081-1122)
- TestCouplingPair (lines 1271-1302)
- TestCouplingAnalysis (lines 1304-1336)
- TestRegressionCluster (lines 1555-1592)
- TestRegressionAnalysis (lines 1594-1620)
- TestTestGap (lines 1832-1879)
- TestTestGapAnalysis (lines 1882-1918)
- TestParseResolutionAction (lines 2096-2163)
- TestRejectionMetrics (lines 2165-2196)
- TestRejectionAnalysis (lines 2198-2223)
- TestManualPattern (lines 2383-2418)
- TestManualPatternAnalysis (lines 2420-2467)
- TestAgentOutcome (lines 2645-2679)
- TestAgentEffectivenessAnalysis (lines 2681-2704)
- TestComplexityProxy (lines 2904-2928)
- TestComplexityProxyAnalysis (lines 2930-2964)
- TestConfigGap (lines 3118-3166)
- TestConfigGapsAnalysis (lines 3168-3214)
- TestCrossCuttingSmell (lines 3378-3410)
- TestCrossCuttingAnalysis (lines 3412-3441)

**File**: `scripts/tests/test_issue_history_dataclasses.py`

**Step 2.2: Create test_issue_history_parsing.py**

Test classes to include:
- TestParseCompletedIssue (lines 143-215)
- TestScanCompletedIssues (lines 217-265)
- TestScanActiveIssues (lines 740-773)

**File**: `scripts/tests/test_issue_history_parsing.py`

**Step 2.3: Create test_issue_history_summary.py**

Test classes to include:
- TestCalculateSummary (lines 267-328)
- TestFormatSummary (lines 330-391)

**File**: `scripts/tests/test_issue_history_summary.py`

**Step 2.4: Create test_issue_history_analysis.py**

Test classes to include:
- TestCalculateAnalysis (lines 656-738)
- TestFormatAnalysis (lines 775-847)

**File**: `scripts/tests/test_issue_history_analysis.py`

**Step 2.5: Create test_issue_history_advanced_analytics.py**

Test classes to include:
- TestAnalyzeHotspots (lines 1124-1269)
- TestAnalyzeCoupling (lines 1337-1553)
- TestAnalyzeRegressionClustering (lines 1621-1829)
- TestAnalyzeTestGaps (lines 1920-2088)
- TestAnalyzeRejectionRates (lines 2224-2380)
- TestDetectManualPatterns (lines 2469-2642)
- TestAnalyzeAgentEffectiveness (lines 2743-2901)
- TestAnalyzeComplexityProxy (lines 2966-3115)
- TestDetectConfigGaps (lines 3216-3375)
- TestDetectCrossCuttingSmells (lines 3443-3586)

**File**: `scripts/tests/test_issue_history_advanced_analytics.py`

**Step 2.6: Create test_issue_history_cli.py**

Test classes to include:
- TestHistoryArgumentParsing (lines 393-427)
- TestMainHistoryIntegration (lines 429-495)
- TestAnalyzeArgumentParsing (lines 849-917)
- TestMainHistoryAnalyze (lines 919-1023)

**File**: `scripts/tests/test_issue_history_cli.py`

**Step 2.7: Delete original test_issue_history.py**

After all new files are created and verified, remove the original file.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history_*.py -v`
- [ ] All tests discovered: `python -m pytest scripts/tests/test_issue_history_*.py --collect-only | grep "test_" | wc -l` should equal original count

---

### Phase 3: Split test_ll_loop.py into Focused Modules

#### Overview
Split test_ll_loop.py (3,580 lines) into 7 focused test modules based on functionality.

#### Changes Required

**Step 3.1: Create test_ll_loop_helpers.py**

Create a helper module with the shared functions from lines 29-77:

**File**: `scripts/tests/test_ll_loop_helpers.py`

```python
"""Helper functions for ll_loop tests."""

from little_loops.fsm.schema import EvaluateConfig, FSMLoop, RouteConfig, StateConfig


def make_test_state(
    action: str | None = None,
    on_success: str | None = None,
    on_failure: str | None = None,
    on_error: str | None = None,
    next: str | None = None,
    terminal: bool = False,
    evaluate: EvaluateConfig | None = None,
    route: RouteConfig | None = None,
    capture: bool = False,
    timeout: int = 300,
    on_maintain: str | None = None,
) -> StateConfig:
    """Helper to create test StateConfig objects."""
    return StateConfig(
        action=action,
        on_success=on_success,
        on_failure=on_failure,
        on_error=on_error,
        next=next,
        terminal=terminal,
        evaluate=evaluate,
        route=route,
        capture=capture,
        timeout=timeout,
        on_maintain=on_maintain,
    )


def make_test_fsm(
    name: str = "test-loop",
    initial: str = "start",
    states: dict[str, StateConfig] | None = None,
    max_iterations: int = 50,
    timeout: int = 600,
) -> FSMLoop:
    """Helper to create test FSMLoop objects."""
    if states is None:
        states = {
            "start": make_test_state(action="echo start", on_success="done", on_failure="done"),
            "done": make_test_state(terminal=True),
        }
    return FSMLoop(
        name=name,
        initial=initial,
        states=states,
        max_iterations=max_iterations,
        timeout=timeout,
    )
```

**Step 3.2: Create test_ll_loop_parsing.py**

Test classes to include:
- TestLoopArgumentParsing (lines 80-231)
- TestResolveLoopPath (lines 232-275)

**File**: `scripts/tests/test_ll_loop_parsing.py`

**Step 3.3: Create test_ll_loop_commands.py**

Test classes to include:
- TestCmdValidate (lines 276-334)
- TestCmdList (lines 335-360)
- TestCmdHistory (lines 361-407)
- TestHistoryTail (lines 408-571)

**File**: `scripts/tests/test_ll_loop_commands.py`

**Step 3.4: Create test_ll_loop_display.py**

Test classes to include:
- TestStateToDict (lines 572-794)
- TestPrintExecutionPlan (lines 795-990)
- TestProgressDisplay (lines 991-1079)

**File**: `scripts/tests/test_ll_loop_display.py`

**Step 3.5: Create test_ll_loop_integration.py**

Test classes to include:
- TestMainLoopIntegration (lines 1080-1536)

**File**: `scripts/tests/test_ll_loop_integration.py`

**Step 3.6: Create test_ll_loop_state.py**

Test classes to include:
- TestCmdStop (lines 1537-1662)
- TestCmdResume (lines 1663-1876)

**File**: `scripts/tests/test_ll_loop_state.py`

**Step 3.7: Create test_ll_loop_errors.py**

Test classes to include:
- TestErrorHandling (lines 1877-1998)
- TestErrorMessages (lines 1999-2197)

**File**: `scripts/tests/test_ll_loop_errors.py`

**Step 3.8: Create test_ll_loop_execution.py**

Test classes to include:
- TestCompileEndToEnd (lines 2198-2413)
- TestEndToEndExecution (lines 2414-2773)
- TestLLMFlags (lines 2774-3101)
- TestCmdTest (lines 3102-3320)
- TestCmdSimulate (lines 3321-3580)

**File**: `scripts/tests/test_ll_loop_execution.py`

**Step 3.9: Delete original test_ll_loop.py**

After all new files are created and verified, remove the original file.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop*.py -v`
- [ ] All tests discovered: `python -m pytest scripts/tests/test_ll_loop*.py --collect-only | grep "test_" | wc -l` should equal original count (136)

---

### Phase 4: Final Verification

#### Overview
Run full test suite to ensure all tests pass after the split.

#### Changes Required
No code changes - just verification.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Format check passes: `ruff format --check scripts/`

---

## Testing Strategy

### Verification Commands

```bash
# Count tests before split (baseline)
python -m pytest scripts/tests/test_issue_history.py --collect-only | grep "test_" | wc -l
python -m pytest scripts/tests/test_ll_loop.py --collect-only | grep "test_" | wc -l

# Count tests after split (should match)
python -m pytest scripts/tests/test_issue_history_*.py --collect-only | grep "test_" | wc -l
python -m pytest scripts/tests/test_ll_loop*.py --collect-only | grep "test_" | wc -l

# Run all tests
python -m pytest scripts/tests/ -v
```

### Import Management

Each new file will need:
- Standard imports: `from __future__ import annotations`, `import pytest`
- Source module imports for what that file tests
- Helper imports (e.g., `from test_ll_loop_helpers import make_test_state, make_test_fsm`)

## References

- Original issue: `.issues/enhancements/P2-ENH-213-split-large-test-files-into-focused-modules.md`
- Primary target: `scripts/tests/test_issue_history.py` (3,586 lines)
- Secondary target: `scripts/tests/test_ll_loop.py` (3,580 lines)
- Existing split pattern: `scripts/tests/test_fsm_*.py` (7 files)
- Shared fixtures: `scripts/tests/conftest.py`
- Test helpers pattern: `scripts/tests/test_fsm_schema.py:38-76`
