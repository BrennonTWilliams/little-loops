# ENH-168: Add test coverage enforcement to pyproject.toml - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-168-test-coverage-enforcement-in-pyproject.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

### Key Discoveries
- `scripts/pyproject.toml:56-62` has `pytest>=7.0` and `pytest-cov>=4.0` in dev dependencies
- `scripts/pyproject.toml:71-83` has `[tool.ruff]` and `[tool.mypy]` sections configured
- No `[tool.pytest.ini_options]` section exists
- No `[tool.coverage.run]` or `[tool.coverage.report]` sections exist
- No standalone `pytest.ini`, `.coveragerc`, or `setup.cfg` files
- Current coverage is **81%** (8042 statements, 1514 missing)
- 1,872 tests pass (1 unrelated failure in `test_issue_lifecycle.py`)

### Current Test Execution
- Tests run via `python -m pytest scripts/tests/`
- Coverage is optional via `--cov=little_loops --cov-report=html` flags
- No enforcement mechanism prevents coverage regression

## Desired End State

After implementation:
1. Running `pytest` automatically tracks coverage for `little_loops` package
2. Coverage reports generated in terminal (missing lines) and HTML format
3. Coverage threshold enforced at **80%** (adjusted from proposed 85% since current coverage is 81%)
4. Test markers `integration` and `slow` defined for selective test execution

### How to Verify
- `pytest scripts/tests/` runs successfully with coverage output
- `htmlcov/index.html` generated after test run
- Coverage at least 80% (tests fail if below threshold)

## What We're NOT Doing

- Not fixing the unrelated test failure in `test_issue_lifecycle.py` - separate issue
- Not increasing coverage to reach 85% - current code at 81%, threshold set to 80%
- Not adding CI/CD configuration - no existing CI infrastructure
- Not modifying test files - configuration only

## Problem Analysis

The project has excellent test coverage infrastructure (pytest-cov installed, 1,872 tests) but lacks configuration to enforce coverage thresholds. This means coverage can silently regress without detection.

## Solution Approach

Add three configuration sections to `scripts/pyproject.toml`:
1. `[tool.pytest.ini_options]` - pytest configuration with coverage enabled by default
2. `[tool.coverage.run]` - coverage source and omit patterns
3. `[tool.coverage.report]` - reporting format and 80% threshold

**Threshold Adjustment**: The issue proposes 85%, but current coverage is 81%. Setting threshold to 80% provides a safety margin while still enforcing the standard.

## Implementation Phases

### Phase 1: Add pytest configuration section

#### Overview
Add `[tool.pytest.ini_options]` section after existing `[tool.mypy]` section.

#### Changes Required

**File**: `scripts/pyproject.toml`
**Location**: After line 83 (end of `[tool.mypy]` section)

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
]
markers = [
    "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
    "slow: marks tests as slow running (deselect with '-m \"not slow\"')",
]
```

**Notes**:
- Removed `--cov-report=xml` from proposed config (not needed without CI)
- Using `skip-covered` to reduce terminal output noise

#### Success Criteria

**Automated Verification**:
- [ ] `cd scripts && python -m pytest tests/ --co` shows test collection works

---

### Phase 2: Add coverage.run section

#### Overview
Add `[tool.coverage.run]` section to configure coverage source and omit patterns.

#### Changes Required

**File**: `scripts/pyproject.toml`
**Location**: After `[tool.pytest.ini_options]` section

```toml
[tool.coverage.run]
source = ["little_loops"]
omit = [
    "*/tests/*",
    "*/__init__.py",
]
```

#### Success Criteria

**Automated Verification**:
- [ ] Configuration syntax valid (no parse errors)

---

### Phase 3: Add coverage.report section

#### Overview
Add `[tool.coverage.report]` section with exclusion patterns and 80% threshold.

#### Changes Required

**File**: `scripts/pyproject.toml`
**Location**: After `[tool.coverage.run]` section

```toml
[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
fail_under = 80
```

**Note**: Using 80% threshold instead of proposed 85% since current coverage is 81%.

#### Success Criteria

**Automated Verification**:
- [ ] Configuration syntax valid

---

### Phase 4: Verify full configuration

#### Overview
Run complete test suite to verify all configuration works together.

#### Success Criteria

**Automated Verification**:
- [ ] `cd scripts && python -m pytest tests/` passes with coverage output
- [ ] Coverage percentage displayed in terminal
- [ ] `htmlcov/index.html` file exists after test run
- [ ] Tests don't fail due to coverage threshold (currently 81% > 80% threshold)

---

## Testing Strategy

### Verification Steps
1. Run `python -m pytest tests/ --co` to verify test collection with new config
2. Run `python -m pytest tests/` to verify full test suite with coverage
3. Verify HTML report generated at `scripts/htmlcov/index.html`
4. Verify coverage threshold enforced (manually lower `fail_under` to 90 and confirm failure)

### Edge Cases
- Ensure `--cov` flags in addopts don't conflict with manual `--cov` usage
- Verify markers don't cause issues with existing tests

## References

- Original issue: `.issues/enhancements/P2-ENH-168-test-coverage-enforcement-in-pyproject.md`
- Target file: `scripts/pyproject.toml:84` (append after mypy section)
- Similar pattern: `scripts/pyproject.toml:71-83` (existing tool configuration)
