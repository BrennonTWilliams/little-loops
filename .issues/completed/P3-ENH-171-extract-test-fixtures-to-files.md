---
discovered_date: 2026-01-28
discovered_by: capture_issue
---

# ENH-171: Extract complex test data to fixtures directory

## Summary

Complex test data (YAML configs, issue markdown content, workflow examples) is currently embedded directly in test files. This makes tests verbose and hard to maintain. Extracting to fixture files would improve readability and reusability.

## Current State

**Test data patterns observed**:
- Large YAML strings embedded in test methods
- Multi-line markdown content for issue parsing
- Complex FSM loop definitions in test code

**Example from current tests**:
```python
def test_parse_with_bold_dependencies(self):
    content = """
---
discovered_date: 2024-01-01
---

# BUG-001: Test Issue

## Blocked By
**ENH-1000**, **FEAT-002**, and another thing
"""
    parser = IssueParser(config)
    info = parser.parse_file(StringIO(content))
    ...
```

## Context

**Direct mode**: User description: "Extract complex test data to tests/fixtures/ files"

Identified from testing analysis showing:
- Test files contain large data literals
- Hard to modify test data without reading test code
- Data can't be reused across test files
- Verbose test methods

## Proposed Solution

### 1. Create fixtures directory structure

```
scripts/tests/
├── fixtures/
│   ├── issues/
│   │   ├── minimal-bug.md
│   │   ├── bug-with-dependencies.md
│   │   ├── feature-with-bold-deps.md
│   │   ├── enhancement-with-steps.md
│   │   └── malformed/
│   │       ├── missing-frontmatter.md
│   │       └── invalid-dependencies.md
│   ├── fsm/
│   │   ├── minimal-loop.yaml
│   │   ├── linear-workflow.yaml
│   │   ├── branching-loop.yaml
│   │   ├── interpolation-example.yaml
│   │   └── invalid/
│   │       ├── missing-initial.yaml
│   │       └── circular-states.yaml
│   ├── workflows/
│   │   └── sample-sequences.yaml
│   └── config/
│       ├── minimal-config.json
│       └── full-config.json
└── conftest.py
```

### 2. Add fixture helpers in conftest.py

```python
from pathlib import Path

import pytest

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
```

### 3. Update tests to use fixtures

**Before**:
```python
def test_parse_with_bold_dependencies(self):
    content = """
---
discovered_date: 2024-01-01
---

# BUG-001: Test Issue

## Blocked By
**ENH-1000**, **FEAT-002**, and another thing
"""
    parser = IssueParser(config)
    info = parser.parse_file(StringIO(content))
```

**After**:
```python
def test_parse_with_bold_dependencies(self, issue_fixtures: Path):
    fixture_path = issue_fixtures / "bug-with-bold-deps.md"
    parser = IssueParser(config)
    info = parser.parse_file(fixture_path)
    assert info.blocked_by == ["ENH-1000", "FEAT-002"]
```

### 4. Fixture file examples

**`scripts/tests/fixtures/issues/bug-with-bold-deps.md`**:
```markdown
---
discovered_date: 2024-01-01
discovered_by: test
---

# BUG-001: Test Issue

## Summary
Test issue for verifying bold markdown dependency parsing.

## Blocked By
**ENH-1000**, **FEAT-002**, and ENH-003
```

**`scripts/tests/fixtures/fsm/linear-workflow.yaml`**:
```yaml
initial: analyze
states:
  analyze:
    transitions:
      - target: implement
        when: "'changes_needed' in captures"
  implement:
    transitions:
      - target: verify
        when: true
  verify:
    terminal: true
```

## Impact

- **Priority**: P3 (Low - refactoring)
- **Effort**: Medium (requires creating files and updating tests)
- **Risk**: Low (refactoring only, behavior unchanged)

## Benefits

- More readable test code
- Test data visible for documentation
- Reusable fixtures across test files
- Easier to add test cases (just add new fixture)
- Version control diffs focus on data, not code

## Acceptance Criteria

- [x] Create `scripts/tests/fixtures/` directory structure
- [x] Add fixture helper functions to conftest.py
- [x] Extract 5+ complex issue fixtures (13 created)
- [x] Extract 5+ complex FSM fixtures (8 created)
- [x] Update 10+ tests to use fixtures (22 tests updated)
- [x] All tests still pass after refactoring
- [x] Tests are more readable than before

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | CONTRIBUTING.md | Test structure conventions |

## Labels

`enhancement`, `testing`, `refactoring`, `infrastructure`

---

## Status

**Completed** | Created: 2026-01-28 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-29
- **Status**: Completed

### Changes Made
- `scripts/tests/fixtures/issues/` - Created 13 issue markdown fixture files
- `scripts/tests/fixtures/fsm/` - Created 8 FSM YAML fixture files
- `scripts/tests/conftest.py` - Added fixture helper functions (fixtures_dir, issue_fixtures, fsm_fixtures, load_fixture)
- `scripts/tests/test_issue_parser.py` - Updated 14 tests to use fixtures
- `scripts/tests/test_fsm_schema.py` - Updated 8 tests to use fixtures

### Verification Results
- Tests: PASS (135 passed)
- Lint: PASS
- Types: PASS
