# P1-FEAT-210: Add end-to-end CLI workflow tests

## Summary
While unit tests exist for individual components, there are no true end-to-end tests that exercise complete CLI workflows from invocation to completion. E2E tests would validate the entire user journey.

## Current State
- Unit tests: 2,279 tests across 44 test files
- E2E tests: None (only unit tests with @pytest.mark.integration on one file)
- Gap: No validation of complete user workflows

## Proposed Workflows to Test
1. **Issue creation workflow**
   - User invokes CLI to create an issue
   - Issue file is created with proper format
   - Issue appears in listings

2. **Sprint planning workflow**
   - User creates a sprint from multiple issues
   - Sprint configuration is validated
   - Sprint can be executed

3. **Parallel execution workflow**
   - User runs ll-parallel on a sprint
   - Workers are spawned and process issues
   - Results are merged back to main branch

4. **Sequential execution workflow**
   - User runs ll-auto on issues
   - Issues are processed sequentially
   - State is properly managed

5. **Loop execution workflow**
   - User runs ll-loop with a configuration
   - FSM executes with state persistence
   - Loop can be resumed after interruption

## Acceptance Criteria
- [x] At least 5 end-to-end workflow tests covering the above scenarios
- [x] Tests use temporary git repositories for isolation
- [x] Tests exercise actual CLI entry points (not just Python APIs)
- [x] Tests validate both success and failure paths
- [x] Tests are marked with @pytest.mark.integration
- [x] Documentation added for running E2E tests

## Implementation Notes
- Use pytest's tmpdir fixture for temporary test directories
- Consider using subprocess to invoke actual CLI commands
- Use CliRunner from Click for Click command testing
- E2E tests should be in scripts/tests/integration/ or marked separately

## Labels
testing, cli, integration, quality

## Status
Ready

## Priority
P1 - High: E2E tests catch integration issues that unit tests miss; critical for user-facing reliability.

## Related Files
- scripts/little_loops/cli.py (CLI entry points)
- scripts/tests/ (existing test structure)
- scripts/pyproject.toml (test configuration)

## Audit Source
Test Coverage Audit - 2026-02-01

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-01
- **Status**: Completed

### Changes Made
- **scripts/tests/test_cli_e2e.py** (NEW): Created end-to-end CLI workflow tests with 11 test cases
  - `TestIssueCreationWorkflow`: Tests issue file format and listing (2 tests)
  - `TestSprintPlanningWorkflow`: Tests sprint creation and validation (2 tests)
  - `TestSequentialExecutionWorkflow`: Tests ll-auto command (3 tests)
  - `TestParallelExecutionWorkflow`: Tests ll-parallel command (2 tests)
  - `TestLoopExecutionWorkflow`: Tests ll-loop command (2 tests)
- **docs/E2E_TESTING.md** (NEW): Documentation for running E2E tests
- **thoughts/shared/plans/2026-02-01-FEAT-210-management.md** (NEW): Implementation plan

### Key Features
- Tests use temporary git repositories for complete isolation
- Tests invoke actual CLI entry point functions (main_auto, main_parallel, main_loop)
- Tests are marked with `@pytest.mark.integration` marker
- Base fixture class `E2ETestFixture` provides reusable test infrastructure
- Subprocess calls are mocked to prevent actual Claude CLI execution

### Verification Results
- Tests: 11 passed
- Lint: PASS
- Types: Not run (test files excluded from type checking)
