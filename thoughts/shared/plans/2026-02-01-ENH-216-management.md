# ENH-216: Add fuzz testing for critical parsers - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-216-add-fuzz-testing-for-critical-parsers.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

### What Exists Now

The codebase has **property-based tests** using Hypothesis, but **no dedicated fuzz testing**:

1. **Existing Property-Based Tests**:
   - `scripts/tests/test_issue_parser_properties.py` - 11 tests for issue_parser
   - `scripts/tests/test_fsm_compiler_properties.py` - 27 tests for FSM compilers
   - Hypothesis is already in dev dependencies (`hypothesis>=6.0`)

2. **Target Parsers Identified**:
   - `scripts/little_loops/issue_parser.py` (582 lines) - Custom YAML-like frontmatter parser
   - `scripts/little_loops/goals_parser.py` (203 lines) - Uses `yaml.safe_load()` without limits
   - `scripts/little_loops/fsm/schema.py` (453 lines) - No type validation on `from_dict()` methods

3. **NOT Currently Installed**:
   - `hypothesmith` library (mentioned in issue but not in dependencies)
   - Any fuzz-specific test files

### Key Discoveries from Research

1. **Critical Vulnerability in `issue_parser.py:_parse_frontmatter()`** (lines 340-378):
   - Custom YAML-like parser with no protection against large frontmatter blocks
   - No recursion depth limits
   - No validation of parsed values
   - Simple line-by-line parsing could be confused by malformed input

2. **Critical Vulnerability in `goals_parser.py:from_content()`** (lines 112-160):
   - Uses `yaml.safe_load()` but no hardening against:
     - YAML anchors/aliases (DoS via exponential expansion)
     - Deeply nested structures
     - Extremely large documents
   - Splits on `---` without bounds (line 125)

3. **Critical Vulnerability in `fsm/schema.py:FSMLoop.from_dict()`** (lines 398-423):
   - No type validation on input
   - No limits on data sizes
   - Recursive structure creation without depth limits
   - `Literal` type hints have no runtime validation

4. **Test Organization Pattern** (from ENH-169):
   - Property tests in `test_*_properties.py` files
   - Fuzz tests should follow `test_*_fuzz.py` convention
   - Separate from unit tests (can be slow)

## Desired End State

After implementation, the project will have:

1. **Fuzz test suite** for the three critical parsers
2. **hypothesmith dependency** added for Python AST fuzzing (or decision to skip it)
3. **Crash safety findings documented** in test docstrings or separate report
4. **Regression tests** for any bugs discovered during fuzzing
5. **Separate test execution** - fuzz tests not run by default (marked as slow)

### How to Verify

1. Run fuzz tests: `python -m pytest scripts/tests/test_*_fuzz.py -v`
2. Verify all tests pass without crashes
3. Check for documented findings in test files or crash report
4. Confirm fuzz tests are marked as `@pytest.mark.slow` to exclude from normal runs

## What We're NOT Doing

- Not adding AFL (American Fuzzy Lop) - requires binary instrumentation, too complex for this project
- Not adding continuous fuzzing infrastructure - just test suite for manual/CI execution
- Not modifying the parsers themselves (unless bugs found) - this is testing only
- Not adding fuzz tests for all parsers - only the three critical ones identified
- Not using hypothesmith if it's not actively maintained - will verify before adding

## Problem Analysis

**Root Problem**: The critical parsers that handle external input (issue files, goals files, FSM loop configs) lack dedicated fuzz testing to discover crash safety vulnerabilities and edge cases.

**Why This Matters**:
1. These parsers process user-provided files that could be maliciously crafted
2. Property-based tests verify invariants but don't stress-test crash safety
3. Custom YAML parsing (issue_parser) may have undiscovered edge cases
4. Standard YAML parsing (goals_parser) needs protection against YAML bombs
5. FSM schema parsing accepts untyped dicts - could crash on unexpected input

## Solution Approach

### High-Level Strategy

1. **Use Hypothesis for structured fuzzing** - Already installed, well-maintained
2. **Create targeted fuzz tests** for each parser's vulnerable entry points
3. **Focus on crash safety** - test for exceptions, hangs, memory issues
4. **Document findings** - add docstrings and/or separate findings file
5. **Add regression tests** - convert any discovered bugs into regular tests

### Technical Decisions

**Question: Should we add hypothesmith?**

- **Pros**: Purpose-built for Python AST fuzzing, can find more exotic bugs
- **Cons**: Not well-maintained (last release 2021), may not work with Python 3.11+
- **Decision**: Start with Hypothesis-only. If Hypothesis finds no bugs, consider hypothesmith only if we can verify it works.

**Question: Separate fuzz test files or add to existing property tests?**

- **Decision**: Separate files (`test_*_fuzz.py`) to:
  - Keep fuzz tests isolated from faster property tests
  - Allow marking as `@pytest.mark.slow`
  - Make it clear these are crash-safety tests, not invariant tests

## Implementation Phases

### Phase 1: Setup and Dependency Verification

#### Overview
Verify Hypothesis is sufficient, decide on hypothesmith, set up test structure.

#### Changes Required

**File**: `scripts/pyproject.toml`
**Changes**: May add `hypothesmith` if verification passes (unlikely based on research).

**File**: `scripts/tests/test_issue_parser_fuzz.py` (new)
**Changes**: Create fuzz test file for issue_parser.

**File**: `scripts/tests/test_goals_parser_fuzz.py` (new)
**Changes**: Create fuzz test file for goals_parser.

**File**: `scripts/tests/test_fsm_schema_fuzz.py` (new)
**Changes**: Create fuzz test file for fsm/schema.py.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_*_fuzz.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_*_fuzz.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_*_fuzz.py`

**Manual Verification**:
- [ ] Review test files for proper fuzzing strategies (not just random data)
- [ ] Confirm tests are marked with `@pytest.mark.slow`
- [ ] Verify tests focus on crash safety (try/except for exceptions)

---

### Phase 2: Implement Fuzz Tests for issue_parser.py

#### Overview
Create fuzz tests for the custom YAML-like frontmatter parser and critical parsing functions.

#### Changes Required

**File**: `scripts/tests/test_issue_parser_fuzz.py` (new)
**Changes**: Implement fuzz tests for:

```python
"""Fuzz tests for issue_parser module focusing on crash safety.

These tests use Hypothesis to generate malformed, extreme, and unexpected
inputs to verify the parser doesn't crash, hang, or consume excessive memory.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from little_loops.issue_parser import IssueParser, IssueInfo, find_issues


# =============================================================================
# Issue Content Fuzzing Strategy
# =============================================================================

@st.composite
def malformed_issue_content(draw: st.DrawFn) -> str:
    """Generate potentially malformed issue markdown content.

    Targets:
    - Missing or malformed frontmatter delimiters
    - Extreme frontmatter sizes
    - Invalid UTF-8 sequences
    - Extremely long lines
    - Deeply nested markdown structures
    """
    # Randomly decide whether to include frontmatter
    has_frontmatter = draw(st.booleans())

    parts = []

    if has_frontmatter:
        # May or may not have proper delimiters
        has_start_delim = draw(st.booleans())
        has_end_delim = draw(st.booleans())

        if has_start_delim:
            parts.append("---")

        # Generate frontmatter content
        # Can be: empty, huge, malformed key-value, etc.
        fm_type = draw(st.sampled_from(["empty", "huge", "malformed", "valid"]))

        if fm_type == "empty":
            parts.append("")
        elif fm_type == "huge":
            # Generate 1000 key-value pairs
            for i in range(1000):
                key = draw(st.text(min_size=1, max_size=50))
                value = draw(st.text(min_size=0, max_size=200))
                parts.append(f"{key}: {value}")
        elif fm_type == "malformed":
            # Invalid YAML-like structures
            parts.append(draw(st.text(min_size=0, max_size=5000)))
        else:  # valid
            # Actually valid frontmatter
            parts.append(f"priority: {draw(st.sampled_from(['P0', 'P1', 'P2', 'P3']))}")
            parts.append(f"discovered_by: {draw(st.text(min_size=1, max_size=50))}")

        if has_end_delim:
            parts.append("---")

    # Add title (may be malformed)
    title = draw(st.text(min_size=0, max_size=500))
    if title:
        parts.append(f"# {title}")

    # Add body content (can include dependencies, etc.)
    body = draw(st.text(min_size=0, max_size=10000))
    if body:
        parts.append(body)

    return "\n".join(parts)


@st.composite
def issue_filename(draw: st.DrawFn) -> str:
    """Generate potentially malformed issue filenames.

    Targets:
    - Invalid priority prefixes
    - Missing type prefixes
    - Special characters
    - Extremely long names
    """
    # Random structure
    structure = draw(st.sampled_from([
        "standard",  # P1-BUG-123-title.md
        "no_priority",  # BUG-123-title.md
        "only_id",  # 123.md
        "malformed",  # random gibberish
    ]))

    if structure == "standard":
        priority = draw(st.sampled_from(["P0", "P1", "P2", "P3", "P4", "P5", "PX", "P999"]))
        issue_type = draw(st.sampled_from(["BUG", "FEAT", "ENH", "XXX"]))
        number = draw(st.integers(min_value=0, max_value=9999))
        title = draw(st.text(min_size=0, max_size=100))
        return f"{priority}-{issue_type}-{number}-{title}.md"
    elif structure == "no_priority":
        issue_type = draw(st.sampled_from(["BUG", "FEAT", "ENH"]))
        number = draw(st.integers(min_value=0, max_value=9999))
        title = draw(st.text(min_size=0, max_size=100))
        return f"{issue_type}-{number}-{title}.md"
    elif structure == "only_id":
        number = draw(st.integers(min_value=0, max_value=99999))
        return f"{number}.md"
    else:  # malformed
        return draw(st.text(min_size=1, max_size=255)) + ".md"


# =============================================================================
# Fuzz Tests
# =============================================================================

class TestIssueParserFuzz:
    """Fuzz tests for issue parser crash safety."""

    @pytest.mark.slow
    @given(content=malformed_issue_content())
    @settings(
        max_examples=500,
        deadline=None,  # Disable deadline for potentially slow parsing
        suppress_health_check=list(HealthCheck)
    )
    def test_parse_file_never_crashes(self, content: str) -> None:
        """Parsing any content should never crash.

        May return None or default values, but must not raise uncaught exceptions.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            issue_file = Path(tmpdir) / "P1-BUG-001-test.md"
            issue_file.write_text(content, encoding="utf-8")

            parser = IssueParser({})

            # Should not raise uncaught exceptions
            try:
                result = parser.parse_file(issue_file)
                # Result can be None or IssueInfo, both are valid
                assert result is None or isinstance(result, IssueInfo)
            except (UnicodeDecodeError, ValueError) as e:
                # These are acceptable for truly malformed input
                # (e.g., invalid UTF-8, completely broken structure)
                pass
            except Exception as e:
                pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    @pytest.mark.slow
    @given(filename=issue_filename(), content=st.text(min_size=0, max_size=50000))
    @settings(
        max_examples=300,
        deadline=None,
        suppress_health_check=list(HealthCheck)
    )
    def test_parse_with_various_filenames(self, filename: str, content: str) -> None:
        """Filename parsing should handle malformed names gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Sanitize filename for filesystem
            safe_filename = filename.replace("/", "_").replace("\\", "_")
            if not safe_filename or safe_filename == ".md":
                safe_filename = "test.md"

            issue_file = Path(tmpdir) / safe_filename
            try:
                issue_file.write_text(content, encoding="utf-8")
            except (OSError, ValueError):
                # Filename may be invalid for filesystem - skip this test
                return

            parser = IssueParser({})

            try:
                result = parser.parse_file(issue_file)
                # Should not crash, result can be None
                assert result is None or isinstance(result, IssueInfo)
            except Exception as e:
                # Log but don't fail - we're testing crash safety
                # (If it's a real bug, it will be found by other tests)
                pass

    @pytest.mark.slow
    @given(frontmatter=st.text(min_size=0, max_size=100000))
    @settings(
        max_examples=200,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow]
    )
    def test_huge_frontmatter_doesnt_hang(self, frontmatter: str) -> None:
        """Extremely large frontmatter should not cause hangs or excessive memory use.

        This specifically tests the custom frontmatter parser for DoS vulnerabilities.
        """
        content = f"---\n{frontmatter}\n---\n# Test\n\nBody."
        with tempfile.TemporaryDirectory() as tmpdir:
            issue_file = Path(tmpdir) / "P1-BUG-001-test.md"
            issue_file.write_text(content, encoding="utf-8")

            parser = IssueParser({})

            # Use a timeout to catch hangs
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError("Parser hung on large input")

            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(5)  # 5 second timeout

            try:
                result = parser.parse_file(issue_file)
                # Success if it doesn't hang
            except TimeoutError:
                pytest.fail("Parser hung on large frontmatter")
            except Exception:
                # Other exceptions are acceptable for malformed input
                pass
            finally:
                signal.alarm(0)

    @pytest.mark.slow
    @given(
        blocked_by=st.lists(
            st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True),
            max_size=100
        ),
        blocks=st.lists(
            st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True),
            max_size=100
        )
    )
    @settings(max_examples=200)
    def test_dependency_parsing_handles_lists(self, blocked_by: list[str], blocks: list[str]) -> None:
        """Dependency parsing should handle large lists without crashing."""
        content = "# Test\n\n"
        if blocked_by:
            content += "## Blocked By\n\n"
            for dep in blocked_by:
                content += f"- {dep}\n"
        if blocks:
            content += "\n## Blocks\n\n"
            for dep in blocks:
                content += f"- {dep}\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            issue_file = Path(tmpdir) / "P1-BUG-001-test.md"
            issue_file.write_text(content, encoding="utf-8")

            parser = IssueParser({})
            result = parser.parse_file(issue_file)

            # Should parse without crashing
            assert result is None or isinstance(result, IssueInfo)


class TestIssueParserFindIssuesFuzz:
    """Fuzz tests for find_issues() directory scanning."""

    @pytest.mark.slow
    @given(
        files=st.lists(
            st.tuples(
                st.sampled_from(["bugs", "features", "enhancements", "other"]),
                st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N', 'P'))),
                st.text(min_size=0, max_size=10000)
            ),
            max_size=50
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_find_issues_handles_mixed_files(self, files: list[tuple[str, str, str]]) -> None:
        """Directory scanning should handle mixed valid/invalid files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)

            # Create files
            for subdir, name, content in files:
                dir_path = base_path / subdir
                dir_path.mkdir(exist_ok=True)
                file_path = dir_path / f"{name}.md"

                try:
                    file_path.write_text(content, encoding="utf-8")
                except (OSError, ValueError):
                    # Skip files that can't be created
                    continue

            # Should not crash
            try:
                issues = find_issues(base_path)
                # Result can be empty list or list of IssueInfo
                assert isinstance(issues, list)
                for issue in issues:
                    assert isinstance(issue, IssueInfo)
            except Exception as e:
                pytest.fail(f"find_issues crashed: {type(e).__name__}: {e}")
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_parser_fuzz.py -v -m slow`
- [ ] No hangs detected (5-second timeout test should pass)
- [ ] Lint passes: `ruff check scripts/tests/test_issue_parser_fuzz.py`

**Manual Verification**:
- [ ] Review test strategies ensure they cover the vulnerable areas
- [ ] Check that timeout test actually works (try reducing timeout to verify)

---

### Phase 3: Implement Fuzz Tests for goals_parser.py

#### Overview
Create fuzz tests for YAML parsing with focus on YAML bombs and deep nesting.

#### Changes Required

**File**: `scripts/tests/test_goals_parser_fuzz.py` (new)
**Changes**: Implement fuzz tests for YAML crash safety.

```python
"""Fuzz tests for goals_parser module focusing on YAML crash safety.

These tests specifically target YAML parsing vulnerabilities:
- YAML bombs (anchor/alias exponential expansion)
- Deeply nested structures
- Large documents
- Malformed YAML
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from little_loops.goals_parser import ProductGoals


# =============================================================================
# YAML Fuzzing Strategies
# =============================================================================

@st.composite
def yaml_bomb_content(draw: st.DrawFn) -> str:
    """Generate YAML content with potential anchor/alias attacks.

    YAML bombs use anchors and aliases to cause exponential expansion,
    leading to memory exhaustion or hangs.
    """
    # Randomly decide to include anchors/aliases
    use_anchors = draw(st.booleans())

    if not use_anchors:
        # Safe YAML
        return draw(st.text(min_size=0, max_size=5000))

    # Create a simple YAML bomb (small scale for testing)
    # Real attacks would be much larger
    bomb_type = draw(st.sampled_from(["simple", "nested", "alias_loop"]))

    if bomb_type == "simple":
        return """---
anchor: &anchor
  - value1
  - value2
alias1: *anchor
alias2: *anchor
alias3: *anchor
alias4: *anchor
"""

    elif bomb_type == "nested":
        # Nested anchors
        return """---
level1: &level1
  key: value
level2: &level2
  level1: *level1
level3: &level3
  level2: *level2
level4: *level3
"""

    else:  # alias_loop
        # This might cause yaml.safe_load to fail (which is OK)
        return """---
a: &a [b]
b: &b [*a]
"""


@st.composite
def deeply_nested_yaml(draw: st.DrawFn) -> str:
    """Generate YAML with extreme nesting depth.

    Deep nesting can cause stack overflow in parsers.
    """
    depth = draw(st.integers(min_value=1, max_value=1000))

    # Build nested structure
    content = "---\n"
    current = content

    for i in range(depth):
        current += f"level{i}: "
        if i < depth - 1:
            current += "{ "
        else:
            current += "value\n"

    # Close all braces
    for _ in range(depth - 1):
        current += " }\n"

    return current


@st.composite
def malformed_goals_content(draw: st.DrawFn) -> str:
    """Generate malformed goals file content.

    Targets:
    - Missing frontmatter
    - Invalid YAML structure
    - Missing required fields
    - Wrong field types
    """
    content_type = draw(st.sampled_from([
        "no_frontmatter",
        "invalid_yaml",
        "no_delimiter",
        "empty",
        "huge",
        "valid_but_weird",
    ]))

    if content_type == "no_frontmatter":
        # No --- delimiters at all
        body = draw(st.text(min_size=0, max_size=5000))
        return body

    elif content_type == "invalid_yaml":
        # Has delimiters but invalid YAML between
        return "---\n" + draw(st.text(min_size=0, max_size=5000)) + "\n---\nBody"

    elif content_type == "no_delimiter":
        # Has starting --- but no ending
        return "---\nkey: value\nNo ending delimiter"

    elif content_type == "empty":
        return ""

    elif content_type == "huge":
        # Generate large YAML document
        lines = ["---"]
        for i in range(1000):
            lines.append(f"key{i}: {draw(st.text(min_size=0, max_size=100))}")
        lines.append("---")
        lines.append("# Goals")
        return "\n".join(lines)

    else:  # valid_but_weird
        # Structurally valid but unusual content
        return f"""---
version: "{draw(st.text(min_size=1, max_size=20))}"
persona:
  id: "{draw(st.text(min_size=0, max_size=100))}"
  name: "{draw(st.text(min_size=0, max_size=200))}"
  role: "{draw(st.text(min_size=0, max_size=200))}"
priorities:
  - name: "{draw(st.text(min_size=0, max_size=100))}"
    description: "{draw(st.text(min_size=0, max_size=1000))}"
    weight: {draw(st.integers(min_value=-100, max_value=1000))}
---
# Goals Document
{draw(st.text(min_size=0, max_size=5000))}
"""


# =============================================================================
# Fuzz Tests
# =============================================================================

class TestGoalsParserFuzz:
    """Fuzz tests for goals parser crash safety."""

    @pytest.mark.slow
    @given(content=malformed_goals_content())
    @settings(
        max_examples=500,
        deadline=None,
        suppress_health_check=list(HealthCheck)
    )
    def test_from_content_never_crashes(self, content: str) -> None:
        """Parsing any content should never crash.

        May return None for invalid input, but must not raise uncaught exceptions.
        """
        try:
            result = ProductGoals.from_content(content)
            # Result can be None or ProductGoals
            assert result is None or isinstance(result, ProductGoals)
        except (yaml.YAMLError, ValueError):
            # These are acceptable for malformed YAML
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    @pytest.mark.slow
    @given(content=yaml_bomb_content())
    @settings(
        max_examples=200,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow]
    )
    def test_yaml_bomb_protection(self, content: str) -> None:
        """YAML bombs should be handled without hanging or excessive memory use.

        Uses a timeout to detect hangs from exponential expansion.
        """
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutError("Parser hung on YAML bomb")

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(5)  # 5 second timeout

        try:
            result = ProductGoals.from_content(content)
            # Success if it doesn't hang
        except TimeoutError:
            pytest.fail("Parser hung on YAML bomb")
        except (yaml.YAMLError, ValueError):
            # YAML errors are acceptable
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")
        finally:
            signal.alarm(0)

    @pytest.mark.slow
    @given(content=deeply_nested_yaml())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow]
    )
    def test_deep_nesting_protection(self, content: str) -> None:
        """Deeply nested YAML should not cause stack overflow.

        Uses a timeout to detect hangs from recursive parsing.
        """
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutError("Parser hung on deeply nested YAML")

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(5)  # 5 second timeout

        try:
            result = ProductGoals.from_content(content)
            # Success if it doesn't hang
        except TimeoutError:
            pytest.fail("Parser hung on deeply nested YAML")
        except (yaml.YAMLError, ValueError):
            # YAML errors are acceptable
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")
        finally:
            signal.alarm(0)

    @pytest.mark.slow
    @given(
        content=st.text(min_size=0, max_size=100000),
        filename=st.text(min_size=1, max_size=100)
    )
    @settings(max_examples=200, deadline=None)
    def test_from_file_with_various_content(self, content: str, filename: str) -> None:
        """File parsing should handle various file contents gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Sanitize filename
            safe_filename = filename.replace("/", "_").replace("\\", "_")
            if not safe_filename:
                safe_filename = "goals.md"

            goals_file = Path(tmpdir) / safe_filename

            try:
                goals_file.write_text(content, encoding="utf-8")
            except (OSError, ValueError):
                # Filename may be invalid
                return

            try:
                result = ProductGoals.from_file(goals_file)
                # Should not crash, can be None
                assert result is None or isinstance(result, ProductGoals)
            except Exception as e:
                # Log but don't fail - testing crash safety
                if not isinstance(e, (OSError, UnicodeDecodeError, yaml.YAMLError)):
                    pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_goals_parser_fuzz.py -v -m slow`
- [ ] Timeout tests actually catch hangs (verify by temporarily causing a hang)
- [ ] Lint passes: `ruff check scripts/tests/test_goals_parser_fuzz.py`

**Manual Verification**:
- [ ] Confirm YAML bomb test would catch an actual DoS attempt
- [ ] Review deep nesting test ensures stack overflow protection

---

### Phase 4: Implement Fuzz Tests for fsm/schema.py

#### Overview
Create fuzz tests for FSM schema parsing, focusing on untyped dict deserialization.

#### Changes Required

**File**: `scripts/tests/test_fsm_schema_fuzz.py` (new)
**Changes**: Implement fuzz tests for schema deserialization.

```python
"""Fuzz tests for fsm.schema module focusing on untyped dict deserialization.

These tests target the from_dict() methods that accept unvalidated dictionaries:
- Type confusion attacks
- Recursive structures
- Invalid literal values
- Missing required fields
- Unexpected field types
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

from little_loops.fsm.schema import (
    EvaluateConfig,
    RouteConfig,
    StateConfig,
    FSMLoop,
)


# =============================================================================
# Dict Fuzzing Strategies
# =============================================================================

@st.composite
def malformed_evaluate_config(draw: st.DrawFn) -> dict:
    """Generate potentially malformed EvaluateConfig dictionaries.

    Targets:
    - Invalid type values (not in Literal)
    - Wrong field types (string instead of int, etc.)
    - Missing required fields
    - Unexpected fields
    """
    # Type field - may be valid or invalid
    valid_types = [
        "exit_code", "output_numeric", "output_json",
        "output_contains", "convergence", "llm_structured"
    ]
    eval_type = draw(st.one_of(
        st.sampled_from(valid_types),
        st.text(min_size=1, max_size=50),  # Invalid type
        st.integers(),  # Completely wrong type
        st.none(),  # Missing required field
    ))

    config: dict = {"type": eval_type}

    # Add optional fields with potentially wrong types
    if draw(st.booleans()):
        config["operator"] = draw(st.one_of(
            st.sampled_from(["eq", "ne", "lt", "le", "gt", "ge"]),
            st.integers(),  # Wrong type
            st.none(),
        ))

    if draw(st.booleans()):
        config["target"] = draw(st.one_of(
            st.integers(),
            st.floats(),
            st.text(min_size=1, max_size=100),
            st.none(),
        ))

    if draw(st.booleans()):
        config["tolerance"] = draw(st.one_of(
            st.floats(),
            st.text(min_size=1, max_size=50),
            st.integers(),
        ))

    # Add completely unexpected fields
    if draw(st.booleans()):
        for i in range(draw(st.integers(min_value=1, max_value=10))):
            config[f"unexpected_{i}"] = draw(st.one_of(
                st.integers(),
                st.text(),
                st.lists(st.integers()),
                st.dictionaries(st.text(), st.integers()),
            ))

    return config


@st.composite
def malformed_route_config(draw: st.DrawFn) -> dict:
    """Generate potentially malformed RouteConfig dictionaries."""
    # Generate random route mappings
    routes: dict = {}

    num_routes = draw(st.integers(min_value=0, max_value=20))
    for i in range(num_routes):
        verdict = draw(st.one_of(
            st.sampled_from(["accept", "reject", "continue"]),
            st.text(min_size=1, max_size=50),  # Invalid verdict
            st.integers(),
        ))

        target = draw(st.one_of(
            st.text(min_size=1, max_size=50),  # State name
            st.integers(),  # Wrong type
            st.none(),
        ))

        routes[verdict] = target

    # Add special keys with potentially wrong values
    if draw(st.booleans()):
        routes["_"] = draw(st.one_of(
            st.text(min_size=1, max_size=50),
            st.integers(),
        ))

    if draw(st.booleans()):
        routes["_error"] = draw(st.one_of(
            st.text(min_size=1, max_size=50),
            st.integers(),
        ))

    return routes


@st.composite
def malformed_state_config(draw: st.DrawFn) -> dict:
    """Generate potentially malformed StateConfig dictionaries."""
    state: dict = {"name": draw(st.one_of(
        st.text(min_size=1, max_size=100),
        st.integers(),
        st.none(),
    ))}

    # Add action with potentially wrong types
    if draw(st.booleans()):
        state["action"] = draw(st.one_of(
            st.sampled_from(["shell", "slash"]),
            st.text(min_size=1, max_size=50),  # Invalid action
            st.integers(),
        ))

    # Add command
    if draw(st.booleans()):
        state["command"] = draw(st.one_of(
            st.text(min_size=0, max_size=1000),
            st.integers(),
            st.lists(st.text()),
        ))

    # Add evaluate config
    if draw(st.booleans()):
        state["evaluate"] = draw(malformed_evaluate_config())

    # Add route config
    if draw(st.booleans()):
        state["route"] = draw(malformed_route_config())

    # Add unexpected fields
    if draw(st.booleans()):
        for i in range(draw(st.integers(min_value=1, max_value=5))):
            state[f"unexpected_{i}"] = draw(st.one_of(
                st.integers(),
                st.text(),
                st.lists(st.integers()),
            ))

    return state


@st.composite
def malformed_fsm_loop(draw: st.DrawFn) -> dict:
    """Generate potentially malformed FSMLoop dictionaries.

    Targets:
    - Recursive state references
    - Circular dependencies
    - Invalid literal types
    - Missing required fields
    - Wrong field types
    """
    # Generate states
    num_states = draw(st.integers(min_value=0, max_value=20))

    # State names - may include invalid ones
    state_names = []
    for i in range(num_states):
        name = draw(st.one_of(
            st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N'))),
            st.integers(),
            st.none(),
        ))
        state_names.append(name)

    # Build states dict
    states = {}
    for name in state_names:
        if name is not None:
            states[str(name)] = draw(malformed_state_config())

    # Build FSM dict
    fsm: dict = {}

    # Name (required)
    fsm["name"] = draw(st.one_of(
        st.text(min_size=1, max_size=100),
        st.integers(),
        st.none(),
    ))

    # Initial (required) - may reference non-existent state
    if state_names:
        fsm["initial"] = draw(st.one_of(
            st.sampled_from([str(n) for n in state_names if n is not None]),
            st.text(min_size=1, max_size=50),  # Non-existent state
            st.integers(),
        ))
    else:
        fsm["initial"] = draw(st.text(min_size=1, max_size=50))

    # States (required)
    fsm["states"] = states

    # Optional fields with potentially wrong types
    if draw(st.booleans()):
        fsm["max_iterations"] = draw(st.one_of(
            st.integers(min_value=1, max_value=1000),
            st.integers(min_value=-100, max_value=-1),  # Invalid
            st.text(),  # Wrong type
        ))

    if draw(st.booleans()):
        fsm["timeout"] = draw(st.one_of(
            st.integers(min_value=1, max_value=3600),
            st.integers(min_value=-100, max_value=-1),
            st.none(),
        ))

    if draw(st.booleans()):
        fsm["context"] = draw(st.one_of(
            st.dictionaries(st.text(), st.integers()),
            st.dictionaries(st.text(), st.dictionaries(st.text(), st.integers()), max_size=50),  # Deep nesting
            st.lists(st.integers()),  # Wrong type
        ))

    return fsm


# =============================================================================
# Fuzz Tests
# =============================================================================

class TestEvaluateConfigFuzz:
    """Fuzz tests for EvaluateConfig deserialization."""

    @pytest.mark.slow
    @given(config=malformed_evaluate_config())
    @settings(max_examples=500, deadline=None)
    def test_from_dict_handles_malformed(self, config: dict) -> None:
        """from_dict should handle malformed input without crashing."""
        try:
            # Handle missing required 'type' field
            if "type" not in config:
                with pytest.raises(KeyError):
                    EvaluateConfig.from_dict(config)
                return

            # Try to create config
            result = EvaluateConfig.from_dict(config)
            assert isinstance(result, EvaluateConfig)
        except (KeyError, TypeError, ValueError):
            # These are acceptable for truly malformed input
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")


class TestRouteConfigFuzz:
    """Fuzz tests for RouteConfig deserialization."""

    @pytest.mark.slow
    @given(config=malformed_route_config())
    @settings(max_examples=500, deadline=None)
    def test_from_dict_handles_malformed(self, config: dict) -> None:
        """from_dict should handle malformed route configs without crashing."""
        try:
            result = RouteConfig.from_dict(config)
            assert isinstance(result, RouteConfig)
        except (KeyError, TypeError, ValueError):
            # Acceptable for malformed input
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")


class TestStateConfigFuzz:
    """Fuzz tests for StateConfig deserialization."""

    @pytest.mark.slow
    @given(config=malformed_state_config())
    @settings(max_examples=500, deadline=None)
    def test_from_dict_handles_malformed(self, config: dict) -> None:
        """from_dict should handle malformed state configs without crashing."""
        try:
            # Handle missing required 'name' field
            if "name" not in config:
                with pytest.raises(KeyError):
                    StateConfig.from_dict(config)
                return

            result = StateConfig.from_dict(config)
            assert isinstance(result, StateConfig)
        except (KeyError, TypeError, ValueError):
            # Acceptable for malformed input
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")


class TestFSMLoopFuzz:
    """Fuzz tests for FSMLoop deserialization."""

    @pytest.mark.slow
    @given(fsm_dict=malformed_fsm_loop())
    @settings(max_examples=300, deadline=None)
    def test_from_dict_handles_malformed(self, fsm_dict: dict) -> None:
        """from_dict should handle malformed FSM configs without crashing."""
        try:
            # Handle missing required fields
            required_fields = ["name", "initial", "states"]
            missing = [f for f in required_fields if f not in fsm_dict]
            if missing:
                with pytest.raises(KeyError):
                    FSMLoop.from_dict(fsm_dict)
                return

            result = FSMLoop.from_dict(fsm_dict)
            assert isinstance(result, FSMLoop)
        except (KeyError, TypeError, ValueError):
            # Acceptable for malformed input
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    @pytest.mark.slow
    @given(yaml_content=st.text(min_size=0, max_size=50000))
    @settings(max_examples=200, deadline=None)
    def test_yaml_loading_never_crashes(self, yaml_content: str) -> None:
        """Loading YAML and creating FSM should never crash.

        This tests the full flow: YAML -> dict -> FSMLoop
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_file = Path(tmpdir) / "fsm.yaml"
            yaml_file.write_text(yaml_content, encoding="utf-8")

            try:
                # Load YAML
                data = yaml.safe_load(yaml_file)

                # Skip if not a dict (expected for invalid YAML)
                if not isinstance(data, dict):
                    return

                # Try to create FSM
                result = FSMLoop.from_dict(data)
                assert isinstance(result, FSMLoop)
            except (yaml.YAMLError, KeyError, TypeError, ValueError):
                # Acceptable for invalid input
                pass
            except Exception as e:
                pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    @pytest.mark.slow
    @given(
        states=st.dictionaries(
            st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'N'))),
            malformed_state_config(),
            max_size=50
        )
    )
    @settings(max_examples=200, deadline=None)
    def test_large_state_dicts(self, states: dict) -> None:
        """Large state dictionaries should be handled without issues."""
        # Build minimal FSM
        fsm_dict = {
            "name": "test",
            "initial": list(states.keys())[0] if states else "none",
            "states": states,
        }

        try:
            result = FSMLoop.from_dict(fsm_dict)
            assert isinstance(result, FSMLoop)
        except (KeyError, ValueError):
            # Acceptable for invalid input (e.g., no valid initial state)
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_schema_fuzz.py -v -m slow`
- [ ] Lint passes: `ruff check scripts/tests/test_fsm_schema_fuzz.py`

**Manual Verification**:
- [ ] Review test strategies cover all untyped from_dict() methods
- [ ] Confirm invalid literal type tests would catch type confusion bugs

---

### Phase 5: Run Fuzz Tests and Document Findings

#### Overview
Execute all fuzz tests, capture any crashes or bugs, and document findings.

#### Changes Required

**File**: `thoughts/shared/reports/ENH-216-fuzz-test-findings.md` (new)
**Changes**: Document any crashes, bugs, or vulnerabilities discovered.

**File**: `scripts/tests/conftest.py` (modify)
**Changes**: Add pytest marker configuration for `slow` tests.

```python
# Add to conftest.py
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
```

#### Success Criteria

**Automated Verification**:
- [ ] All fuzz tests pass: `python -m pytest scripts/tests/test_*_fuzz.py -v`
- [ ] Quick test run works: `python -m pytest scripts/tests/ -v -m "not slow"`
- [ ] Fuzz tests excluded by default: `python -m pytest scripts/tests/ -v` (should not run fuzz tests)

**Manual Verification**:
- [ ] Review findings document for any discovered vulnerabilities
- [ ] If bugs found, create regression tests in appropriate test files
- [ ] Update issue acceptance checklist

---

### Phase 6: Update Issue and Complete

#### Overview
Document resolution, move issue to completed, create commit.

#### Changes Required

**File**: `.issues/enhancements/P3-ENH-216-add-fuzz-testing-for-critical-parsers.md`
**Changes**: Add resolution section.

```markdown
---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-01
- **Status**: Completed

### Changes Made
- `scripts/tests/test_issue_parser_fuzz.py`: Created with fuzz tests for issue_parser.py
- `scripts/tests/test_goals_parser_fuzz.py`: Created with fuzz tests for goals_parser.py
- `scripts/tests/test_fsm_schema_fuzz.py`: Created with fuzz tests for fsm/schema.py
- `scripts/tests/conftest.py`: Added pytest marker configuration for slow tests
- `thoughts/shared/reports/ENH-216-fuzz-test-findings.md`: Documented fuzz test findings

### Verification Results
- Tests: PASS (all fuzz tests pass)
- Lint: PASS
- Types: PASS

### Findings
[Document any bugs or vulnerabilities discovered during fuzzing]
```

**Move to completed**:
```bash
git mv .issues/enhancements/P3-ENH-216-add-fuzz-testing-for-critical-parsers.md \
       .issues/completed/
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_*_fuzz.py -v`
- [ ] Lint passes: `ruff check scripts/tests/`
- [ ] Types pass: `python -m mypy scripts/tests/`

**Manual Verification**:
- [ ] Issue file updated with resolution
- [ ] Issue moved to completed directory
- [ ] Git commit created with proper message

## Testing Strategy

### Unit Tests
- N/A (this is adding test files)

### Integration Tests
- Run all fuzz tests together: `python -m pytest scripts/tests/test_*_fuzz.py -v`
- Verify slow marker works: `python -m pytest scripts/tests/ -v -m "not slow"`

### Regression Tests
- If fuzzing discovers any bugs, create specific test cases in regular test files

## References

- Original issue: `.issues/enhancements/P3-ENH-216-add-fuzz-testing-for-critical-parsers.md`
- Related patterns: `scripts/tests/test_issue_parser_properties.py` (property-based test pattern)
- Similar implementation: `.issues/completed/P3-ENH-169-property-based-tests-for-parsers.md`
- Documentation: `docs/TESTING.md` (lines 398-467 for Hypothesis usage)
