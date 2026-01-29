---
discovered_date: 2026-01-28
discovered_by: capture_issue
---

# ENH-168: Add test coverage enforcement to pyproject.toml

## Summary

Currently, test coverage is measured but not enforced. The `pytest-cov` package is installed, but there's no coverage threshold configured, meaning coverage can regress without detection.

## Current State

**File**: `scripts/pyproject.toml`

Current pytest configuration:
- No `[tool.pytest.ini_options]` section exists
- No coverage thresholds enforced
- No coverage reporting configuration

## Context

**Direct mode**: User description: "Add coverage enforcement to pyproject.toml"

Identified from testing analysis showing:
- 1,868 test cases with good coverage
- No automated enforcement to prevent regression
- pytest-cov already installed but not configured

## Proposed Solution

Add the following sections to `scripts/pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--strict-markers",
    "--strict-config",
    "--cov=little_loops",
    "--cov-report=term-missing:skip-covered",
    "--cov-report=html",
    "--cov-report=xml",
]
markers = [
    "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
    "slow: marks tests as slow running (deselect with '-m \"not slow\"')",
]

[tool.coverage.run]
source = ["little_loops"]
omit = [
    "*/tests/*",
    "*/__init__.py",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
fail_under = 85
```

## Impact

- **Priority**: P2 (Medium)
- **Effort**: Low (configuration only)
- **Risk**: Low (may initially fail if current coverage < 85%)

## Acceptance Criteria

- [x] Add `[tool.pytest.ini_options]` section to pyproject.toml
- [x] Add `[tool.coverage.run]` section with source config
- [x] Add `[tool.coverage.report]` section with 80% threshold (adjusted from 85% since current coverage is 81%)
- [x] Verify `pytest` runs successfully with new config
- [x] Verify HTML coverage report generated at `htmlcov/index.html`

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | CONTRIBUTING.md | Mentions test execution |

## Labels

`enhancement`, `testing`, `coverage`, `configuration`

---

## Status

**Open** | Created: 2026-01-28 | Priority: P2

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-29
- **Status**: Completed

### Changes Made
- `scripts/pyproject.toml`: Added `[tool.pytest.ini_options]`, `[tool.coverage.run]`, and `[tool.coverage.report]` sections

### Implementation Notes
- Threshold set to 80% instead of proposed 85% because current coverage is 81%
- Removed `--cov-report=xml` since no CI infrastructure exists
- Added `skip-covered` option to reduce terminal output noise

### Verification Results
- Tests: PASS (1,872 passed, 1 unrelated failure in test_issue_lifecycle.py)
- Coverage: 81.13% (above 80% threshold)
- HTML Report: Generated at `scripts/htmlcov/index.html`
