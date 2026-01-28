---
discovered_date: 2026-01-28
discovered_by: capture_issue
---

# ENH-169: Add property-based tests for parsers using Hypothesis

## Summary

Current parser tests use hand-picked examples, which may miss edge cases. Property-based testing with Hypothesis would generate thousands of random inputs to verify parser invariants hold true across all valid inputs.

## Current State

**Affected modules**:
- `scripts/little_loops/issue_parser.py` (574 lines) - Parses issue markdown files
- `scripts/little_loops/fsm/compilers.py` - Compiles YAML to FSM definitions
- `scripts/little_loops/workflow_sequence_analyzer.py` - Parses workflow sequences

**Existing tests**:
- `scripts/tests/test_issue_parser.py` (1062 lines) - Comprehensive but example-based
- `scripts/tests/test_fsm_compilers.py` - Example-based tests

## Context

**Direct mode**: User description: "Add Property-based tests for parsers using Hypothesis"

Identified from testing analysis showing:
- Parsers are critical for data ingestion
- Edge cases in markdown parsing can cause bugs
- Property-based testing excels at finding parser edge cases

## Proposed Solution

### Add Hypothesis to dev dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "hypothesis>=6.0",  # Add this
    "ruff>=0.1.0",
    "mypy>=1.0",
]
```

### Property Tests for Issue Parser

**File**: `scripts/tests/test_issue_parser_properties.py`

Properties to verify:

1. **Round-trip property**: Parse → serialize → parse yields same result
   ```python
   @given(issue_content())
   def test_round_trip_parse(issue_content):
       info = parser.parse_file(StringIO(issue_content))
       serialized = info.to_markdown()
       info2 = parser.parse_file(StringIO(serialized))
       assert info == info2
   ```

2. **Dependency uniqueness**: Dependencies listed in BlockedBy exist as files
   ```python
   @given(issue_content(), dependencies())
   def test_blocked_by_dependencies_valid(content, deps):
       # All referenced issues should follow naming pattern
       for dep in deps:
           assert re.match(r'^[A-Z]+-\d+$', dep)
   ```

3. **Markdown bold parsing**: Bold markers don't break dependency parsing
   ```python
   @given(bold_text(), dependencies())
   def test_bold_dependencies_parsed_correctly(text, deps):
       content = f"**Blocked By:** {text}, {deps[0]}, **{deps[1]}**"
       info = parser.parse_file(StringIO(content))
       assert set(info.blocked_by) == set(deps[:2])
   ```

### Property Tests for YAML Compiler

**File**: `scripts/tests/test_fsm_compiler_properties.py`

Properties to verify:

1. **Valid YAML produces valid FSM**: Any valid YAML compiles without error
   ```python
   @given(valid_fsm_yaml())
   def test_valid_yaml_compiles(yaml_content):
       result = compile_yaml(yaml_content)
       assert result.is_valid
   ```

2. **State references exist**: All transition targets reference defined states
   ```python
   @given(valid_fsm_yaml())
   def test_all_transitions_valid(yaml_content):
       result = compile_yaml(yaml_content)
       defined_states = set(result.states.keys())
       for state in result.states.values():
           for transition in state.transitions:
               assert transition.target in defined_states
   ```

### Custom Strategies

Create generators for test data:

```python
from hypothesis import strategies as st

@st.composite
def issue_content(draw):
    return draw(st.text(
        alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')),
        min_size=0,
        max_size=5000
    ))

@st.composite
def valid_fsm_yaml(draw):
    states = draw(st.dictionaries(
        st.from_regex(r'[a-z_]+'),
        state_definition(),
        min_size=1,
        max_size=10
    ))
    # Build valid YAML structure
    ...
```

## Impact

- **Priority**: P3 (Low/Medium - quality improvement)
- **Effort**: Medium (requires learning Hypothesis)
- **Risk**: Low (adding tests only)

## Benefits

- Catches edge cases hand-picked tests miss
- Documents parser invariants explicitly
- Provides confidence in refactoring
- Finds bugs in handling malformed input

## Acceptance Criteria

- [ ] Add `hypothesis>=6.0` to dev dependencies
- [ ] Create `test_issue_parser_properties.py` with 3+ properties
- [ ] Create `test_fsm_compiler_properties.py` with 2+ properties
- [ ] All tests pass with `hypothesis` database generation
- [ ] At least one previously unknown bug found (optional)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | CONTRIBUTING.md | Development setup and test running |

## Labels

`enhancement`, `testing`, `property-based`, `parsers`

---

## Status

**Open** | Created: 2026-01-28 | Priority: P3
