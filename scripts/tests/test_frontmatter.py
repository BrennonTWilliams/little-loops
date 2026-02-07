"""Tests for shared frontmatter parsing utility."""

from __future__ import annotations

from little_loops.frontmatter import parse_frontmatter


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
