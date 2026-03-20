"""Tests for shared frontmatter parsing utility."""

from __future__ import annotations

import pytest

from little_loops.frontmatter import parse_frontmatter, strip_frontmatter


class TestParseFrontmatter:
    """Tests for parse_frontmatter function."""

    def test_empty_content(self) -> None:
        assert parse_frontmatter("") == {}

    def test_no_frontmatter(self) -> None:
        assert parse_frontmatter("# Title\n\nBody") == {}

    def test_simple_frontmatter(self) -> None:
        content = "---\nkey: value\n---\n\n# Title\n"
        result = parse_frontmatter(content)
        assert result == {"key": "value"}

    def test_multiple_fields(self) -> None:
        content = "---\nfoo: bar\nbaz: qux\n---\n\nBody\n"
        result = parse_frontmatter(content)
        assert result == {"foo": "bar", "baz": "qux"}

    def test_null_values(self) -> None:
        content = "---\nfield1: null\nfield2: ~\nfield3:\n---\n\n"
        result = parse_frontmatter(content)
        assert result["field1"] is None
        assert result["field2"] is None
        assert result["field3"] is None

    def test_comment_lines_skipped(self) -> None:
        content = "---\n# comment\nkey: value\n---\n\n"
        result = parse_frontmatter(content)
        assert result == {"key": "value"}

    def test_empty_lines_skipped(self) -> None:
        content = "---\nkey1: val1\n\nkey2: val2\n---\n\n"
        result = parse_frontmatter(content)
        assert result == {"key1": "val1", "key2": "val2"}

    def test_malformed_no_closing_delimiter(self) -> None:
        content = "---\nkey: value\n# No closing\n"
        assert parse_frontmatter(content) == {}

    def test_colon_in_value(self) -> None:
        content = "---\nurl: https://example.com\n---\n\n"
        result = parse_frontmatter(content)
        assert result["url"] == "https://example.com"

    def test_no_coerce_types_default(self) -> None:
        """Without coerce_types, digit strings remain strings."""
        content = "---\ncount: 42\n---\n\n"
        result = parse_frontmatter(content)
        assert result["count"] == "42"
        assert isinstance(result["count"], str)

    def test_coerce_types_integers(self) -> None:
        """With coerce_types=True, digit strings become int."""
        content = "---\ncount: 42\npriority: 1\n---\n\n"
        result = parse_frontmatter(content, coerce_types=True)
        assert result["count"] == 42
        assert isinstance(result["count"], int)
        assert result["priority"] == 1
        assert isinstance(result["priority"], int)

    def test_coerce_types_non_digit_unchanged(self) -> None:
        """With coerce_types=True, non-digit strings stay as strings."""
        content = "---\nname: alice\nversion: 1.2.3\n---\n\n"
        result = parse_frontmatter(content, coerce_types=True)
        assert result["name"] == "alice"
        assert result["version"] == "1.2.3"

    def test_coerce_types_null_still_none(self) -> None:
        """With coerce_types=True, null values still become None."""
        content = "---\nfield: null\n---\n\n"
        result = parse_frontmatter(content, coerce_types=True)
        assert result["field"] is None

    def test_whitespace_around_delimiter(self) -> None:
        content = "---\nkey: value\n---   \n\nBody\n"
        result = parse_frontmatter(content)
        assert result == {"key": "value"}

    def test_list_item_emits_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """List-item lines should emit a warning and be skipped."""
        content = "---\nkey: value\n- item\n---\n\n"
        with caplog.at_level("WARNING", logger="little_loops.frontmatter"):
            result = parse_frontmatter(content)
        assert result == {"key": "value"}
        assert "Unsupported YAML list syntax" in caplog.text

    def test_block_scalar_pipe_emits_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Block scalar '|' values should emit a warning and store None."""
        content = "---\ndescription: |\n  line one\nkey: value\n---\n\n"
        with caplog.at_level("WARNING", logger="little_loops.frontmatter"):
            result = parse_frontmatter(content)
        assert result["description"] is None
        assert result["key"] == "value"
        assert "Unsupported YAML block scalar" in caplog.text

    def test_block_scalar_folded_emits_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Block scalar '>' values should emit a warning and store None."""
        content = "---\ndescription: >\n  folded\nkey: value\n---\n\n"
        with caplog.at_level("WARNING", logger="little_loops.frontmatter"):
            result = parse_frontmatter(content)
        assert result["description"] is None
        assert result["key"] == "value"
        assert "Unsupported YAML block scalar" in caplog.text

    def test_block_sequence_parsed_as_list(self) -> None:
        """Block sequence syntax parses correctly as a list."""
        content = "---\nrelated_issues:\n  - P1-BUG-8743\n  - P2-ENH-8762\n---\n\n"
        result = parse_frontmatter(content)
        assert result == {"related_issues": ["P1-BUG-8743", "P2-ENH-8762"]}

    def test_empty_value_no_items_is_none(self) -> None:
        """Empty key with no list items following is None."""
        content = "---\nkey:\nnext: value\n---\n\n"
        result = parse_frontmatter(content)
        assert result["key"] is None
        assert result["next"] == "value"

    def test_block_sequence_followed_by_scalar(self) -> None:
        """List key followed by a scalar key both parse correctly."""
        content = "---\ntags:\n  - foo\n  - bar\nauthor: alice\n---\n\n"
        result = parse_frontmatter(content)
        assert result["tags"] == ["foo", "bar"]
        assert result["author"] == "alice"

    def test_orphaned_list_item_still_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """List item after a scalar-valued key still emits a warning."""
        content = "---\nkey: value\n- orphan\n---\n\n"
        with caplog.at_level("WARNING", logger="little_loops.frontmatter"):
            result = parse_frontmatter(content)
        assert result == {"key": "value"}
        assert "Unsupported YAML list syntax" in caplog.text


class TestStripFrontmatter:
    """Tests for strip_frontmatter function."""

    def test_empty_content(self) -> None:
        assert strip_frontmatter("") == ""

    def test_no_frontmatter(self) -> None:
        content = "# Title\n\nBody"
        assert strip_frontmatter(content) == content

    def test_strips_frontmatter(self) -> None:
        content = "---\nkey: value\n---\n\n# Title\n"
        assert strip_frontmatter(content) == "# Title\n"

    def test_preserves_body(self) -> None:
        content = "---\nfoo: bar\n---\n\nParagraph one.\n\nParagraph two.\n"
        result = strip_frontmatter(content)
        assert "Paragraph one." in result
        assert "Paragraph two." in result
        assert "foo: bar" not in result

    def test_no_closing_delimiter(self) -> None:
        content = "---\nkey: value\n# No closing\n"
        assert strip_frontmatter(content) == content

    def test_whitespace_around_closing_delimiter(self) -> None:
        content = "---\nkey: value\n---   \n\nBody\n"
        assert strip_frontmatter(content) == "Body\n"
