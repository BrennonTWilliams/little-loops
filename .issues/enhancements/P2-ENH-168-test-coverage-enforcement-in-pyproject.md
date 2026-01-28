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

- [ ] Add `[tool.pytest.ini_options]` section to pyproject.toml
- [ ] Add `[tool.coverage.run]` section with source config
- [ ] Add `[tool.coverage.report]` section with 85% threshold
- [ ] Verify `pytest` runs successfully with new config
- [ ] Verify HTML coverage report generated at `htmlcov/index.html`

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | CONTRIBUTING.md | Mentions test execution |

## Labels

`enhancement`, `testing`, `coverage`, `configuration`

---

## Status

**Open** | Created: 2026-01-28 | Priority: P2
