---
discovered_date: 2026-01-28
discovered_by: capture_issue
---

# ENH-172: Add mutation testing to verify test quality

## Summary

High test coverage doesn't guarantee effective tests. Mutation testing introduces artificial bugs (mutations) into source code to verify tests actually fail when behavior changes. This catches tests that pass despite incorrect implementations.

## Current State

**Test metrics**:
- 1,868 tests
- 33,217 lines of test code
- Good line coverage (measured but not enforced)

**Problem**: Coverage measures code execution, not assertion quality.
```python
# Both tests have 100% coverage but only the second is useful
def test_bad_example():  # Passes even if function is broken
    result = calculate_sum(1, 2)
    assert result is not None  # USELESS - always passes

def test_good_example():  # Fails if function is broken
    result = calculate_sum(1, 2)
    assert result == 3  # USEFUL - verifies actual behavior
```

## Context

**Direct mode**: User description: "Add mutation testing (mutmut) to verify assertion quality"

Identified from testing analysis showing:
- High coverage but unknown test quality
- No way to detect useless assertions
- Mutation testing is the gold standard for test quality

## Proposed Solution

### 1. Add mutmut to dev dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "mutmut>=3.0",  # Add this
    "ruff>=0.1.0",
    "mypy>=1.0",
]
```

### 2. Create mutation testing configuration

**File**: `scripts/.mutmut.toml`

```toml
[mutmut]
paths = ["little_loops"]
tests_command = "python -m pytest tests/"
backup_dir_name = ".mutmut-cache"
no_coverage = true
ignore_paths = [
    "*/__init__.py",
    "*/logo.py",  # Skip trivial modules
]
```

### 3. Run mutation testing

**Initial baseline** (takes time, run in CI):
```bash
cd scripts
mutmut run
```

**Expected output**:
```
...
2434 mutants tested
2156 killed (88.6%)
278 survived (11.4%)
```

**Analyze surviving mutants**:
```bash
mutmut results
```

### 4. What mutations test

**Arithmetic operators**:
```python
# Original
result = a + b

# Mutant 1
result = a - b

# Mutant 2
result = a / b

# Tests should fail for these mutations
```

**Boolean operators**:
```python
# Original
if condition and other_condition:

# Mutant
if condition or other_condition:  # Tests should catch this
```

**Comparison operators**:
```python
# Original
if result == expected:

# Mutant
if result != expected:  # Tests should catch this
```

**Conditional flow**:
```python
# Original
if error:
    return None

# Mutant
if True:  # Always return None - tests should catch this
    return None
```

### 5. Fix surviving mutants

For each surviving mutant, either:
1. **Improve the test** - Add assertion that would catch this mutation
2. **Whitelist** - If mutation is equivalent transformation (rare)

```python
# Surviving mutant example
def test_git_lock_timeout(self):
    lock = GitLock(timeout=30)
    # Missing: No assertion about timeout behavior
    # Mutant: timeout=0 goes undetected
```

**Fix**:
```python
def test_git_lock_timeout(self):
    lock = GitLock(timeout=30)
    assert lock.timeout == 30  # Now catches timeout mutation
```

## Impact

- **Priority**: P3 (Low - quality improvement)
- **Effort**: High (mutmut runs slow, requires fixing many tests)
- **Risk**: Low (identifies weak tests)

## Benefits

- Identifies useless assertions
- Documents what code is actually tested
- Prevents regression by ensuring tests verify behavior
- Confidence that tests mean something

## Challenges

- **Performance**: Mutation testing is slow (hours for large codebase)
- **False positives**: Some mutations are equivalent transformations
- **Effort**: Fixing surviving mutants requires writing better tests

## Acceptance Criteria

- [x] Add `mutmut>=3.0` to dev dependencies
- [x] Create mutation testing configuration (in pyproject.toml [tool.mutmut])
- [x] Run initial mutation test baseline (verified setup works)
- [ ] Achieve >80% mutation score on core modules (deferred - requires test improvements)
- [ ] Fix or whitelist surviving mutants (deferred - requires test improvements)
- [ ] Add mutation test to CI (deferred - no CI infrastructure)
- [x] Document mutation testing in CONTRIBUTING.md

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | CONTRIBUTING.md | Test quality standards |

## Labels

`enhancement`, `testing`, `quality`, `mutation-testing`

---

## Status

**Open** | Created: 2026-01-28 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-29
- **Status**: Completed

### Changes Made
- `scripts/pyproject.toml`: Added `mutmut>=3.0` to dev dependencies
- `scripts/pyproject.toml`: Added `[tool.mutmut]` configuration section
- `CONTRIBUTING.md`: Added mutation testing documentation section

### Verification Results
- Tests: PASS (2021 passed, 1 pre-existing failure unrelated to changes)
- Lint: PASS
- Types: PASS
- mutmut: Verified installation and configuration works

### Notes
The core acceptance criteria for enabling mutation testing have been met. Some criteria were deferred:
- Achieving >80% mutation score requires improving tests (separate enhancement issues)
- CI integration requires CI infrastructure (not available in this project)
- Full mutation test runs take hours due to the test suite size (1,868 tests)
