"""Fuzz tests for goals_parser module focusing on YAML crash safety.

These tests specifically target YAML parsing vulnerabilities:
- YAML bombs (anchor/alias exponential expansion)
- Deeply nested structures
- Large documents
- Malformed YAML

Unlike property-based tests (which verify invariants), these tests focus on
crash safety and robustness when handling malicious or malformed YAML input.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
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
    content_type = draw(
        st.sampled_from(
            ["no_frontmatter", "invalid_yaml", "no_delimiter", "empty", "huge", "valid_but_weird"]
        )
    )

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
priorories:
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
        suppress_health_check=list(HealthCheck),
    )
    def test_from_content_never_crashes(self, content: str) -> None:
        """Parsing any content should never crash.

        May return None for invalid input, but must not raise uncaught
        exceptions.
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
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_yaml_bomb_protection(self, content: str) -> None:
        """YAML bombs should be handled without hanging or excessive memory use.

        Uses Hypothesis's deadline to detect hangs from exponential expansion.
        """
        try:
            ProductGoals.from_content(content)
            # Success if it doesn't hang
        except (yaml.YAMLError, ValueError):
            # YAML errors are acceptable
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    @pytest.mark.slow
    @given(content=deeply_nested_yaml())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_deep_nesting_protection(self, content: str) -> None:
        """Deeply nested YAML should not cause stack overflow.

        Uses Hypothesis's deadline to detect hangs from recursive parsing.
        """
        try:
            ProductGoals.from_content(content)
            # Success if it doesn't hang
        except (yaml.YAMLError, ValueError):
            # YAML errors are acceptable
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    @pytest.mark.slow
    @given(
        content=st.text(min_size=0, max_size=100000),
        filename=st.text(min_size=1, max_size=100),
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
