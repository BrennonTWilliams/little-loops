---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# ENH-426: Missing test coverage for core modules

## Summary

Several core modules have no or minimal test coverage: `state.py` (204 lines, state persistence for automation), `issue_lifecycle.py` (issue completion/closure), and `logo.py` (display utilities). These modules contain business logic critical to automation workflows.

## Current Behavior

Core modules like `state.py`, `issue_lifecycle.py`, and `logo.py` lack dedicated test files or have only minimal coverage. Bugs in these modules (like the TOCTOU race in BUG-421) go undetected until they manifest in production.

## Expected Behavior

All modules containing business logic should have test coverage, especially those involved in automation (state persistence, issue lifecycle) where failures can cause data loss or stuck workflows.

## Motivation

State persistence and issue lifecycle are critical paths in automation. Untested code in these modules increases the risk of regressions when making changes. Adding tests also documents expected behavior and makes the codebase safer to refactor.

## Scope Boundaries

- **In scope**: Adding tests for `state.py`, `issue_lifecycle.py`, `logo.py`
- **Out of scope**: Achieving 100% coverage; testing purely cosmetic/display code in depth

## Success Metrics

- Test files exist for `state.py`, `issue_lifecycle.py`, `logo.py`
- Critical paths (state save/load, issue move/complete/close) have at least basic happy-path and error-path tests

## Proposed Solution

Create test files:
- `scripts/tests/test_state.py` — test state save, load, corruption recovery
- `scripts/tests/test_issue_lifecycle.py` — test move to completed, stale cleanup, edge cases
- `scripts/tests/test_logo.py` — basic smoke test for logo display

Use `pytest` with `tmp_path` fixture for filesystem operations. Mock `subprocess.run` for git operations in lifecycle tests.

## Integration Map

### Files to Modify
- N/A (new files)

### Dependent Files (Callers/Importers)
- N/A

### Similar Patterns
- `scripts/tests/test_issue_parser.py` — follow existing test patterns
- `scripts/tests/test_config.py` — follow fixture patterns

### Tests
- New: `scripts/tests/test_state.py`
- New: `scripts/tests/test_issue_lifecycle.py`
- New: `scripts/tests/test_logo.py`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Create test files following existing test patterns
2. Write tests for critical paths in each module
3. Verify all tests pass with `python -m pytest scripts/tests/`

## Impact

- **Priority**: P3 - Foundational improvement for code quality and refactoring safety
- **Effort**: Medium - Multiple test files with mocking needed
- **Risk**: Low - Additive only, no production code changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `testing`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P3
