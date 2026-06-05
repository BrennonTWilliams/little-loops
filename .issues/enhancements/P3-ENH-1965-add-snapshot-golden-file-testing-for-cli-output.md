---
id: ENH-1965
type: ENH
priority: P3
status: open
captured_at: "2026-06-05T21:16:36Z"
discovered_date: 2026-06-05
discovered_by: capture-issue
labels:
  - test-infrastructure
  - captured
parent: EPIC-1967
---

# ENH-1965: Add Snapshot/Golden-File Testing for CLI Output

## Summary

The project has no snapshot or golden-file testing for CLI output. Integrate a snapshot testing library (e.g., `syrupy` or `pytest-snapshot`) to enable regression testing of CLI output, TUI rendering, and formatted text. This is a prerequisite for safely testing the TUI rendering engine (`cli/loop/layout.py`, 1,981 lines).

## Context

Identified during a comprehensive test suite audit. The audit found zero snapshot/golden-file tests despite a large CLI surface area with formatted output. This gap makes it impossible to write regression tests for the TUI rendering engine without fragile string-matching assertions.

## Current Behavior

- CLI output testing relies on ad-hoc `assert "substring" in captured.stdout` patterns
- TUI rendering (`layout.py`, 1,981 lines) has zero tests — partially because there's no snapshot infrastructure
- No snapshot testing library is installed or configured
- The single E2E test file (`test_cli_e2e.py`, 533 lines) uses basic dry-run scenarios without output verification

## Expected Behavior

- `syrupy` or `pytest-snapshot` is installed and configured as a dev dependency
- Snapshot tests exist for key CLI output formats: sprint status tables, loop info displays, diagram rendering
- TUI rendering tests can snapshot rendered output for regression detection
- Snapshots are version-controlled and reviewed in PRs like any other test artifact
- Snapshot update workflow is documented in CONTRIBUTING.md

## Motivation

- **Unblocks TUI testing**: ENH-1964 (CLI layer tests) Phase 3 depends on snapshot infrastructure to test `layout.py`
- **Catches formatting regressions**: A refactor that changes CLI table formatting or diagram output will be caught
- **Industry standard**: Snapshot testing is the established pattern for testing rendered output in CLI tools, React components, and API responses
- **Low-effort, high-value tests**: Snapshot tests are quick to write once infrastructure is in place

## Current Pain Point

Without snapshot testing, verifying CLI output correctness requires either (a) fragile substring assertions that break on any formatting change, or (b) manual visual inspection that doesn't scale. This is the primary reason `layout.py` (1,981 lines) has zero tests — there's no practical way to test TUI output without snapshot infrastructure.

## Proposed Solution

**Recommended: `syrupy`**
- Mature pytest plugin with snapshot file management
- Supports binary snapshots (useful for diagram/image output)
- Built-in snapshot update workflow (`pytest --snapshot-update`)
- Active maintenance and community

**Alternative: `pytest-snapshot`**
- Simpler API, fewer features
- May suffice if only text snapshots are needed

Implementation:
1. Add chosen library to `pyproject.toml` dev dependencies
2. Create a `conftest.py` fixture for snapshot testing
3. Write initial snapshot tests for 3-5 high-value CLI outputs
4. Document the snapshot workflow in CONTRIBUTING.md

## Success Metrics

- **Infrastructure**: Snapshot library installed and configured
- **Initial coverage**: ≥5 CLI commands have snapshot tests
- **Workflow documented**: Snapshot update process in CONTRIBUTING.md
- **Adoption**: Used by at least one subsequent issue (ENH-1964 Phase 3) within 30 days

## Scope Boundaries

- **In scope**: Library selection, installation, configuration, documentation
- **In scope**: Initial snapshot tests for 3-5 CLI outputs (sprint status, loop info, diagram preview)
- **Out of scope**: Comprehensive snapshot coverage of all CLI commands (follow-up work)
- **Out of scope**: Snapshot testing for non-CLI output (API responses, file output — deferred)

## API/Interface

New test fixtures and conventions:
```python
# Proposed fixture pattern
def test_sprint_status_output(snapshot):
    """Snapshot test for ll-sprint show output."""
    result = runner.invoke(sprint_cli, ["show", "my-sprint"])
    assert result.exit_code == 0
    assert snapshot == result.stdout

# Snapshot update workflow
# $ pytest --snapshot-update
```

## Integration Map

### Files to Modify
- `pyproject.toml` — add snapshot library to dev dependencies
- `scripts/tests/conftest.py` — add snapshot fixture if needed
- `scripts/tests/` — new snapshot test files

### Dependent Files (Callers/Importers)
- ENH-1964 Phase 3 — TUI rendering tests will use snapshot infrastructure
- Future CLI tests — all will benefit from snapshot capability

### Similar Patterns
- `test_cli_e2e.py` — existing CLI test patterns to extend with snapshots

### Tests
- New snapshot test files are the deliverable

### Documentation
- `CONTRIBUTING.md` — add "Snapshot Testing" section with update workflow
- `.claude/CLAUDE.md` — note snapshot testing convention

### Configuration
- `pyproject.toml` — dev dependency + pytest configuration

## Implementation Steps

1. Evaluate `syrupy` vs `pytest-snapshot` — check compatibility with existing pytest stack
2. Install chosen library and configure in `pyproject.toml`
3. Create conftest fixture and document snapshot directory structure
4. Write 3-5 initial snapshot tests for high-value CLI outputs
5. Document snapshot workflow in CONTRIBUTING.md (how to create, update, review snapshots)
6. Verify snapshot tests pass in CI

## Backwards Compatibility

- No breaking changes — purely additive (new dev dependency + new tests)
- Existing assertion-based CLI tests continue to work unchanged

## Impact

- **Priority**: P3 — Important infrastructure, unblocks other work, but not blocking current development
- **Effort**: Medium — Library evaluation, configuration, initial tests, documentation
- **Risk**: Low — Dev-only dependency; no production impact
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Development practices and testing guidelines |

## Labels

`test-infrastructure`, `captured`

## Session Log
- `/ll:format-issue` - 2026-06-05T22:11:41 - `f7a66d88-a8bc-4214-b6ed-218118867b50.jsonl`
- `/ll:capture-issue` - 2026-06-05T21:16:36Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5cc001a-5129-4d2d-807d-39a428af0331.jsonl`

## Status

**Open** | Created: 2026-06-05 | Priority: P3
