"""Tests for little_loops.cli.issues.show module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from little_loops.cli.issues.show import (
    _ljust,
    _parse_card_fields,
    _render_card,
    _resolve_issue_id,
    _source_label,
)


# =============================================================================
# _source_label
# =============================================================================


class TestSourceLabel:
    """Tests for _source_label()."""

    def test_none_returns_em_dash(self) -> None:
        assert _source_label(None) == "—"

    def test_empty_string_returns_em_dash(self) -> None:
        assert _source_label("") == "—"

    def test_known_alias_capture_issue(self) -> None:
        assert _source_label("/ll:capture-issue") == "capture"

    def test_known_alias_scan_codebase(self) -> None:
        assert _source_label("/ll:scan-codebase") == "scan"

    def test_unknown_long_string_truncated_to_7(self) -> None:
        result = _source_label("unknown-source-label")
        assert result == "unknown"
        assert len(result) == 7

    def test_unknown_short_string_returned_as_is(self) -> None:
        assert _source_label("short") == "short"

    def test_unknown_exactly_7_chars(self) -> None:
        assert _source_label("1234567") == "1234567"


# =============================================================================
# _resolve_issue_id
# =============================================================================


def _make_config(tmp_path: Path, categories: dict[str, Any]) -> Any:
    """Create a BRConfig backed by a temp project with the given categories."""
    from little_loops.config import BRConfig

    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    cfg: dict[str, Any] = {
        "project": {"name": "test"},
        "issues": {
            "base_dir": ".issues",
            "categories": categories,
        },
    }
    (ll_dir / "ll-config.json").write_text(json.dumps(cfg))
    for cat_key, cat_val in categories.items():
        dir_name = cat_val.get("dir", cat_key) if isinstance(cat_val, dict) else cat_key
        (tmp_path / ".issues" / dir_name).mkdir(parents=True, exist_ok=True)
    return BRConfig(tmp_path)


class TestResolveIssueId:
    """Tests for _resolve_issue_id()."""

    def _make_config_with_file(
        self, tmp_path: Path, filename: str
    ) -> tuple[Any, Path]:
        """Create a config with one issue file and return (config, file_path)."""
        categories = {
            "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "implement"},
            "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
        }
        config = _make_config(tmp_path, categories)
        enh_dir = tmp_path / ".issues" / "enhancements"
        issue_file = enh_dir / filename
        issue_file.write_text("---\nstatus: open\n---\n# ENH-2001: Test issue\n")
        return config, issue_file

    def test_full_format_p_type_nnn(self, tmp_path: Path) -> None:
        """P3-ENH-2001 resolves to the matching file."""
        config, issue_file = self._make_config_with_file(
            tmp_path, "P3-ENH-2001-test-issue.md"
        )
        result = _resolve_issue_id(config, "P3-ENH-2001")
        assert result == issue_file

    def test_type_nnn_format(self, tmp_path: Path) -> None:
        """ENH-2001 resolves to the matching file."""
        config, issue_file = self._make_config_with_file(
            tmp_path, "P3-ENH-2001-test-issue.md"
        )
        result = _resolve_issue_id(config, "ENH-2001")
        assert result == issue_file

    def test_numeric_only_format(self, tmp_path: Path) -> None:
        """Bare numeric '2001' resolves to the matching file."""
        config, issue_file = self._make_config_with_file(
            tmp_path, "P3-ENH-2001-test-issue.md"
        )
        result = _resolve_issue_id(config, "2001")
        assert result == issue_file

    def test_nonexistent_numeric_returns_none(self, tmp_path: Path) -> None:
        """A numeric ID with no matching file returns None."""
        config, _ = self._make_config_with_file(tmp_path, "P3-ENH-2001-test-issue.md")
        result = _resolve_issue_id(config, "9999")
        assert result is None

    def test_stale_type_prefix_falls_back_to_numeric(self, tmp_path: Path) -> None:
        """FEAT-2001 resolves to ENH-2001 file via numeric fallback (BUG-2003)."""
        config, issue_file = self._make_config_with_file(
            tmp_path, "P3-ENH-2001-test-issue.md"
        )
        result = _resolve_issue_id(config, "FEAT-2001")
        assert result == issue_file

    def test_priority_hint_breaks_tie(self, tmp_path: Path) -> None:
        """P3-ENH-2001 prefers the P3-prefixed file when two share the number."""
        categories = {
            "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "implement"},
        }
        config = _make_config(tmp_path, categories)
        enh_dir = tmp_path / ".issues" / "enhancements"
        p2_file = enh_dir / "P2-ENH-2001-old.md"
        p3_file = enh_dir / "P3-ENH-2001-new.md"
        p2_file.write_text("---\nstatus: open\n---\n")
        p3_file.write_text("---\nstatus: open\n---\n")

        result = _resolve_issue_id(config, "P3-ENH-2001")
        assert result == p3_file

    def test_invalid_input_returns_none(self, tmp_path: Path) -> None:
        """Non-parseable input returns None."""
        config, _ = self._make_config_with_file(tmp_path, "P3-ENH-2001-test-issue.md")
        result = _resolve_issue_id(config, "not-an-issue-id")
        assert result is None


# =============================================================================
# _parse_card_fields
# =============================================================================


class TestParseCardFields:
    """Tests for _parse_card_fields()."""

    def _write_issue(self, tmp_path: Path, content: str, filename: str) -> tuple[Path, Any]:
        """Write an issue file and return (path, config)."""
        categories = {
            "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "implement"},
        }
        config = _make_config(tmp_path, categories)
        enh_dir = tmp_path / ".issues" / "enhancements"
        path = enh_dir / filename
        path.write_text(content)
        return path, config

    def test_no_headings_uses_stem_as_title(self, tmp_path: Path) -> None:
        """When content has no # headings, title falls back to file stem."""
        path, config = self._write_issue(
            tmp_path,
            "---\nstatus: open\n---\nJust plain text, no headers.\n",
            "P3-ENH-5001-plain.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["title"] == "P3-ENH-5001-plain"

    def test_empty_summary_section_is_none(self, tmp_path: Path) -> None:
        """A ## Summary section with no body text produces summary=None.

        The regex greedily consumes trailing newlines after the heading, so the
        empty-body case is represented by a Summary section at EOF (or followed
        only by whitespace before the next heading).
        """
        path, config = self._write_issue(
            tmp_path,
            "---\nstatus: open\n---\n# ENH-5002: Thing\n\n## Summary\n\n",
            "P3-ENH-5002-thing.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["summary"] is None

    def test_labels_as_yaml_list(self, tmp_path: Path) -> None:
        """labels: [a, b] in frontmatter → 'a, b'."""
        path, config = self._write_issue(
            tmp_path,
            "---\nstatus: open\nlabels:\n- testing\n- coverage\n---\n# ENH-5003: T\n",
            "P3-ENH-5003-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["labels"] == "testing, coverage"

    def test_labels_as_comma_string(self, tmp_path: Path) -> None:
        """labels: 'foo, bar' in frontmatter → 'foo, bar'."""
        path, config = self._write_issue(
            tmp_path,
            "---\nstatus: open\nlabels: 'foo, bar'\n---\n# ENH-5004: T\n",
            "P3-ENH-5004-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["labels"] == "foo, bar"

    def test_learning_tests_as_list(self, tmp_path: Path) -> None:
        """learning_tests_required as a list produces comma-joined string."""
        path, config = self._write_issue(
            tmp_path,
            "---\nstatus: open\nlearning_tests_required:\n- pytest\n- hypothesis\n---\n# ENH-5005: T\n",
            "P3-ENH-5005-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["learning_tests_required"] == "pytest, hypothesis"

    def test_no_learning_tests_is_none(self, tmp_path: Path) -> None:
        """Absent learning_tests_required → None."""
        path, config = self._write_issue(
            tmp_path,
            "---\nstatus: open\n---\n# ENH-5006: T\n",
            "P3-ENH-5006-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["learning_tests_required"] is None

    def test_status_display_mapping(self, tmp_path: Path) -> None:
        """status: done → 'Completed' in display fields."""
        path, config = self._write_issue(
            tmp_path,
            "---\nstatus: done\n---\n# ENH-5007: T\n",
            "P3-ENH-5007-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["status"] == "Completed"


# =============================================================================
# _ljust
# =============================================================================


class TestLjust:
    """Tests for _ljust()."""

    def test_ansi_colored_text_padded_by_visible_width(self) -> None:
        """ANSI escape codes are invisible; padding is based on visible character width."""
        colored = "\033[32mhello\033[0m"  # "hello" in green — 5 visible chars
        result = _ljust(colored, 10)
        # Visible: 5, pad to 10 → 5 spaces of padding
        assert result.endswith(" " * 5)
        assert result.startswith(colored)

    def test_plain_text_padded_correctly(self) -> None:
        """Plain text is padded to the requested width."""
        result = _ljust("abc", 6)
        assert result == "abc   "

    def test_text_longer_than_width_not_truncated(self) -> None:
        """Text longer than width is returned without padding (no truncation)."""
        result = _ljust("hello world", 5)
        assert result == "hello world"

    def test_exact_width_no_padding_added(self) -> None:
        """Text exactly at the requested width gets zero padding."""
        result = _ljust("abc", 3)
        assert result == "abc"


# =============================================================================
# _render_card
# =============================================================================


class TestRenderCard:
    """Tests for _render_card()."""

    def test_minimal_card_uses_fallback_defaults(
        self, stable_snapshot_env: None
    ) -> None:
        """Empty fields dict renders with '???' and 'Untitled' fallbacks."""
        card = _render_card({})
        assert "???" in card
        assert "Untitled" in card

    def test_card_contains_issue_id_and_title(
        self, stable_snapshot_env: None
    ) -> None:
        """Card body includes the issue_id and title."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-9999",
            "title": "My Test Enhancement",
            "priority": None,
            "status": None,
            "path": ".issues/enhancements/P3-ENH-9999-my-test.md",
        }
        card = _render_card(fields)
        assert "ENH-9999" in card
        assert "My Test Enhancement" in card

    def test_card_has_box_drawing_borders(
        self, stable_snapshot_env: None
    ) -> None:
        """Rendered card uses box-drawing characters for borders."""
        card = _render_card({"issue_id": "BUG-1", "title": "Test"})
        assert "┌" in card  # ┌ top-left
        assert "┘" in card  # ┘ bottom-right

    def test_long_unbreakable_word_extends_box(
        self, stable_snapshot_env: None
    ) -> None:
        """A very long single token in summary extends the card box past structural width."""
        long_word = "x" * 120
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "Short",
            "summary": long_word,
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        # The long word should appear in the card
        assert long_word in card
