# ENH-171: Extract complex test data to fixtures directory - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-171-extract-test-fixtures-to-files.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

Test files in `scripts/tests/` currently embed test data inline as multi-line strings. There is no `fixtures/` directory.

### Key Discoveries
- `conftest.py:14-174` has shared fixtures but only 4 of them (temp_project_dir, sample_config, config_file, issues_dir, and 3 verdict output strings)
- `test_issue_parser.py:397-1017` has 20+ embedded markdown strings for issue parsing tests
- `test_fsm_schema.py:1040-1190` has 10+ embedded YAML strings for FSM validation tests
- `test_goals_parser.py:63-98` has class-level fixtures with YAML frontmatter strings
- `test_ll_loop.py:280-310` has YAML loop definition fixtures

### Patterns Found
- Fixtures return `str` content that is written to temp files via `Path.write_text()`
- Tests use `tempfile.NamedTemporaryFile` or `tmp_path` for file-based tests
- Class-level fixtures with `self` parameter for scoped test data

## Desired End State

A `scripts/tests/fixtures/` directory with:
- Issue markdown fixtures for various parsing scenarios
- FSM YAML fixtures for validation tests
- Helper functions in `conftest.py` for loading fixtures by path

### How to Verify
- All existing tests pass without modification to assertions
- New fixture files are readable and well-organized
- Tests are more concise after refactoring

## What We're NOT Doing

- Not refactoring ALL embedded data - focusing on issue and FSM fixtures (5+ each as per acceptance criteria)
- Not changing test logic or assertions - only how data is loaded
- Not creating fixtures for simple one-line test data
- Not refactoring tests that use Python dict structures (test_fsm_compilers.py, test_user_messages.py) - deferring to separate enhancement
- Not adding new test cases - only extracting existing data

## Solution Approach

1. Create fixture directory structure
2. Add helper fixtures to `conftest.py` for loading fixture files
3. Extract issue markdown fixtures from `test_issue_parser.py`
4. Extract FSM YAML fixtures from `test_fsm_schema.py`
5. Update tests to use fixture file loading instead of inline strings
6. Verify all tests still pass

## Implementation Phases

### Phase 1: Create Fixture Infrastructure

#### Overview
Create the fixtures directory structure and add helper fixtures to conftest.py.

#### Changes Required

**Directory**: `scripts/tests/fixtures/`
Create subdirectories:
```
scripts/tests/fixtures/
├── issues/
│   └── (issue markdown files)
└── fsm/
    └── (FSM YAML files)
```

**File**: `scripts/tests/conftest.py`
**Changes**: Add fixture helper functions

```python
@pytest.fixture
def fixtures_dir() -> Path:
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def issue_fixtures(fixtures_dir: Path) -> Path:
    """Path to issue fixture files."""
    return fixtures_dir / "issues"


@pytest.fixture
def fsm_fixtures(fixtures_dir: Path) -> Path:
    """Path to FSM fixture files."""
    return fixtures_dir / "fsm"


def load_fixture(fixtures_dir: Path, *path_parts: str) -> str:
    """Load fixture file content by path parts."""
    fixture_path = fixtures_dir.joinpath(*path_parts)
    return fixture_path.read_text()
```

#### Success Criteria

**Automated Verification**:
- [ ] Directory exists: `test -d scripts/tests/fixtures/issues && test -d scripts/tests/fixtures/fsm`
- [ ] Tests pass: `python -m pytest scripts/tests/conftest.py -v` (imports work)

---

### Phase 2: Extract Issue Fixtures

#### Overview
Create issue markdown fixture files from embedded strings in `test_issue_parser.py`.

#### Changes Required

**File**: `scripts/tests/fixtures/issues/bug-with-frontmatter.md`
```markdown
---
discovered_commit: abc123
discovered_branch: main
discovered_date: 2026-01-20
discovered_by: scan_codebase
---

# BUG-001: Test Issue

## Summary
Test description.
```

**File**: `scripts/tests/fixtures/issues/bug-no-frontmatter.md`
```markdown
# BUG-001: Test Issue

## Summary
Test description.
```

**File**: `scripts/tests/fixtures/issues/bug-null-discovered-by.md`
```markdown
---
discovered_commit: abc123
discovered_by: null
---

# BUG-001: Test Issue

## Summary
Test.
```

**File**: `scripts/tests/fixtures/issues/bug-with-blocked-by.md`
```markdown
# BUG-001: Test Issue

## Summary
Test description.

## Blocked By
- FEAT-001

## Labels
bug
```

**File**: `scripts/tests/fixtures/issues/bug-with-multiple-blockers.md`
```markdown
# BUG-002: Test Issue

## Blocked By
- FEAT-001
- FEAT-002
- ENH-003

## Blocks
- BUG-010
```

**File**: `scripts/tests/fixtures/issues/bug-with-none-blockers.md`
```markdown
# BUG-004: Test Issue

## Blocked By

None

## Blocks

None - this is standalone
```

**File**: `scripts/tests/fixtures/issues/feature-with-blocks-section.md`
```markdown
# FEAT-001: Foundation Feature

## Summary
This feature enables other work.

## Blocks
- FEAT-002
- FEAT-003
- ENH-001
```

**File**: `scripts/tests/fixtures/issues/feature-with-code-fence.md`
```markdown
# FEAT-005: Test Feature

## Summary

Example format:

```markdown
## Blocked By
- FAKE-001
- FAKE-002
```

## Blocked By

- REAL-001

## Blocks

- REAL-002
```

**File**: `scripts/tests/fixtures/issues/bug-with-bold-deps.md`
```markdown
# ENH-001: Test Issue

## Summary
Test description.

## Blocked By
- **ENH-1000**: Must be completed before this enhancement can proceed.
- **FEAT-002**: Another dependency

## Labels
enhancement
```

#### Success Criteria

**Automated Verification**:
- [ ] Fixture files exist: `ls scripts/tests/fixtures/issues/*.md | wc -l` shows 9+ files
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_parser.py -v`

---

### Phase 3: Extract FSM Fixtures

#### Overview
Create FSM YAML fixture files from embedded strings in `test_fsm_schema.py`.

#### Changes Required

**File**: `scripts/tests/fixtures/fsm/valid-loop.yaml`
```yaml
name: test-loop
initial: check
states:
  check:
    action: pytest
    on_success: done
    on_failure: done
  done:
    terminal: true
```

**File**: `scripts/tests/fixtures/fsm/incomplete-loop.yaml`
```yaml
name: incomplete
# missing initial and states
```

**File**: `scripts/tests/fixtures/fsm/invalid-initial-state.yaml`
```yaml
name: invalid-loop
initial: nonexistent
states:
  done:
    terminal: true
```

**File**: `scripts/tests/fixtures/fsm/invalid-yaml-syntax.yaml`
```yaml
name: test
initial: [unclosed bracket
states:
  done:
    terminal: true
```

**File**: `scripts/tests/fixtures/fsm/loop-with-unreachable-state.yaml`
```yaml
name: test-loop
initial: start
states:
  start:
    action: test
    on_success: done
    on_failure: done
  done:
    terminal: true
  orphan:
    action: unreachable
    next: done
```

**File**: `scripts/tests/fixtures/fsm/missing-name.yaml`
```yaml
initial: start
states:
  start:
    terminal: true
```

#### Success Criteria

**Automated Verification**:
- [ ] Fixture files exist: `ls scripts/tests/fixtures/fsm/*.yaml | wc -l` shows 6+ files
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_schema.py -v`

---

### Phase 4: Update Tests to Use Fixtures

#### Overview
Refactor test methods to load fixtures from files instead of inline strings.

#### Changes Required

**File**: `scripts/tests/test_issue_parser.py`
**Changes**: Update `TestIssueParserDiscoveredBy` and `TestDependencyParsing` classes to use fixtures

Example transformation:
```python
# Before
issue_file.write_text("""---
discovered_commit: abc123
...
""")

# After
fixture_content = load_fixture(fixtures_dir, "issues", "bug-with-frontmatter.md")
issue_file.write_text(fixture_content)
```

**File**: `scripts/tests/test_fsm_schema.py`
**Changes**: Update `TestLoadAndValidate` class to use fixtures

Example transformation:
```python
# Before
yaml_content = """
name: test-loop
...
"""
with tempfile.NamedTemporaryFile(...) as f:
    f.write(yaml_content)

# After
fixture_path = fsm_fixtures / "valid-loop.yaml"
fsm = load_and_validate(fixture_path)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_parser.py scripts/tests/test_fsm_schema.py -v`
- [ ] Lint passes: `ruff check scripts/tests/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 5: Final Verification

#### Overview
Run full test suite and verify all acceptance criteria are met.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Fixture count: 5+ issue fixtures, 5+ FSM fixtures
- [ ] Updated tests: 10+ tests refactored to use fixtures

**Manual Verification**:
- [ ] Fixture files are readable and self-documenting
- [ ] Test code is more concise than before
- [ ] Directory structure matches proposed layout

## Testing Strategy

### Unit Tests
- No new tests needed - this is a refactoring
- All existing tests must continue to pass

### Integration Tests
- Full pytest run validates integration
- Fixture loading works correctly across test files

## References

- Original issue: `.issues/enhancements/P3-ENH-171-extract-test-fixtures-to-files.md`
- Existing fixtures: `scripts/tests/conftest.py:14-174`
- Issue parser tests: `scripts/tests/test_issue_parser.py:390-1020`
- FSM schema tests: `scripts/tests/test_fsm_schema.py:1040-1190`
