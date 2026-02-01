# P1-FEAT-210: Add end-to-end CLI workflow tests

## Summary
While unit tests exist for individual components, there are no true end-to-end tests that exercise complete CLI workflows from invocation to completion. E2E tests would validate the entire user journey.

## Current State
- Unit tests: ~2,156 tests across 45 test files
- E2E tests: None
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
- [ ] At least 5 end-to-end workflow tests covering the above scenarios
- [ ] Tests use temporary git repositories for isolation
- [ ] Tests exercise actual CLI entry points (not just Python APIs)
- [ ] Tests validate both success and failure paths
- [ ] Tests are marked with @pytest.mark.integration
- [ ] Documentation added for running E2E tests

## Implementation Notes
- Use pytest's tmpdir fixture for temporary test directories
- Consider using subprocess to invoke actual CLI commands
- Use CliRunner from Click for Click command testing
- E2E tests should be in scripts/tests/integration/ or marked separately

## Priority
P1 - High: E2E tests catch integration issues that unit tests miss; critical for user-facing reliability.

## Related Files
- scripts/little_loops/cli.py (CLI entry points)
- scripts/tests/ (existing test structure)
- scripts/pyproject.toml (test configuration)

## Audit Source
Test Coverage Audit - 2026-02-01
