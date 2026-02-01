# P0-ENH-206: Improve cli.py test coverage from 62% to 80%+

## Summary
The CLI module (scripts/little_loops/cli.py) has only 62% test coverage with 394 missing statements out of 635 total. This is a critical gap since the CLI is the primary user-facing interface.

## Current State
- Coverage: 62% (394 missing statements)
- Location: scripts/little_loops/cli.py
- Impact: User-facing commands may have untested edge cases

## Targets for Improvement
1. **main_parallel()** - Parallel execution command entry point
2. **main_sprint()** - Sprint-based execution entry point
3. **main_loop()** - FSM-based automation loop entry point
4. **main_messages()** - Message extraction command entry point
5. **Error handling paths** - User-facing error messages and recovery
6. **Argument validation** - CLI argument parsing edge cases

## Acceptance Criteria
- [ ] Coverage increased from 62% to at least 80%
- [ ] Integration tests for actual CLI command flows (not just unit tests)
- [ ] Tests for error messages displayed to users
- [ ] Tests for argument validation edge cases
- [ ] Tests for signal handling (SIGINT/SIGTERM) in CLI context
- [ ] All existing tests continue to pass

## Implementation Notes
- Reference: scripts/tests/test_cli.py (existing tests)
- Consider using CliRunner from Click for integration-style testing
- Test with temporary directories and git repos for realistic scenarios
- Focus on user-facing behavior, not just internal function calls

## Priority
P0 - Critical: CLI is the primary user interface; low coverage means users may encounter untested failure modes.

## Related Files
- scripts/little_loops/cli.py (source)
- scripts/tests/test_cli.py (existing tests)
- scripts/pyproject.toml (coverage threshold: 80%)

## Audit Source
Test Coverage Audit - 2026-02-01
