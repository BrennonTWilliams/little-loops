"""Tests for little_loops.cli.issues.show module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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

    def _make_config_with_file(self, tmp_path: Path, filename: str) -> tuple[Any, Path]:
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
        config, issue_file = self._make_config_with_file(tmp_path, "P3-ENH-2001-test-issue.md")
        result = _resolve_issue_id(config, "P3-ENH-2001")
        assert result == issue_file

    def test_type_nnn_format(self, tmp_path: Path) -> None:
        """ENH-2001 resolves to the matching file."""
        config, issue_file = self._make_config_with_file(tmp_path, "P3-ENH-2001-test-issue.md")
        result = _resolve_issue_id(config, "ENH-2001")
        assert result == issue_file

    def test_numeric_only_format(self, tmp_path: Path) -> None:
        """Bare numeric '2001' resolves to the matching file."""
        config, issue_file = self._make_config_with_file(tmp_path, "P3-ENH-2001-test-issue.md")
        result = _resolve_issue_id(config, "2001")
        assert result == issue_file

    def test_nonexistent_numeric_returns_none(self, tmp_path: Path) -> None:
        """A numeric ID with no matching file returns None."""
        config, _ = self._make_config_with_file(tmp_path, "P3-ENH-2001-test-issue.md")
        result = _resolve_issue_id(config, "9999")
        assert result is None

    def test_stale_type_prefix_falls_back_to_numeric(self, tmp_path: Path) -> None:
        """FEAT-2001 resolves to ENH-2001 file via numeric fallback (BUG-2003)."""
        config, issue_file = self._make_config_with_file(tmp_path, "P3-ENH-2001-test-issue.md")
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

    def test_spike_flags_surfaced_as_bool_strings(self, tmp_path: Path) -> None:
        """ENH-2640: spike_needed/spike_attempted/spike_completed surface as
        lowercased boolean strings for autodev's check_spike_needed gate."""
        path, config = self._write_issue(
            tmp_path,
            "---\nstatus: open\nspike_needed: true\nspike_attempted: true\n"
            "spike_completed: false\n---\n# ENH-5099: T\n",
            "P3-ENH-5099-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["spike_needed"] == "true"
        assert fields["spike_attempted"] == "true"
        assert fields["spike_completed"] == "false"

    def test_spike_flags_absent_are_none(self, tmp_path: Path) -> None:
        """ENH-2640: absent spike flags surface as None (predicate reads != 'true')."""
        path, config = self._write_issue(
            tmp_path,
            "---\nstatus: open\n---\n# ENH-5100: T\n",
            "P3-ENH-5100-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["spike_needed"] is None
        assert fields["spike_attempted"] is None
        assert fields["spike_completed"] is None

    def test_reconcile_attempted_surfaced_as_bool_string(self, tmp_path: Path) -> None:
        """ENH-2689: reconcile_attempted surfaces as a lowercased boolean string
        for autodev's check_reconcile_needed one-shot guard."""
        path, config = self._write_issue(
            tmp_path,
            "---\nstatus: open\nreconcile_attempted: true\n---\n# ENH-5101: T\n",
            "P3-ENH-5101-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["reconcile_attempted"] == "true"

    def test_reconcile_attempted_absent_is_none(self, tmp_path: Path) -> None:
        """ENH-2689: absent reconcile_attempted surfaces as None (guard reads != 'true')."""
        path, config = self._write_issue(
            tmp_path,
            "---\nstatus: open\n---\n# ENH-5102: T\n",
            "P3-ENH-5102-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["reconcile_attempted"] is None

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

    def test_closure_fields_extracted(self, tmp_path: Path) -> None:
        """closing_note, closed_by, closed_at are surfaced into fields dict (ENH-2535)."""
        path, config = self._write_issue(
            tmp_path,
            (
                "---\nstatus: done\n"
                "closing_note: Fixed via X\n"
                "closed_by: implement\n"
                "closed_at: '2026-07-01T12:00:00Z'\n"
                "---\n# ENH-5101: T\n"
            ),
            "P3-ENH-5101-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["closing_note"] == "Fixed via X"
        assert fields["closed_by"] == "implement"
        assert fields["closed_at"] == "2026-07-01T12:00:00Z"

    def test_relationships_fields_extracted(self, tmp_path: Path) -> None:
        """parent / relates_to / depends_on / blocked_by / blocks are surfaced."""
        path, config = self._write_issue(
            tmp_path,
            (
                "---\nstatus: open\n"
                "parent: EPIC-1234\n"
                "relates_to:\n- BUG-1\n- BUG-2\n"
                "depends_on: FEAT-9\n"
                "blocked_by:\n- BUG-1\n"
                "blocks: [BUG-3, BUG-4]\n"
                "---\n# ENH-5102: T\n"
            ),
            "P3-ENH-5102-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["parent"] == "EPIC-1234"
        assert fields["relates_to"] == "BUG-1, BUG-2"
        assert fields["depends_on"] == "FEAT-9"
        assert fields["blocked_by"] == "BUG-1"
        assert fields["blocks"] == "BUG-3, BUG-4"

    def test_discovery_fields_extracted(self, tmp_path: Path) -> None:
        """discovered_date / discovered_commit / discovered_branch are surfaced."""
        path, config = self._write_issue(
            tmp_path,
            (
                "---\nstatus: open\n"
                "discovered_date: '2026-06-30'\n"
                "discovered_commit: abc1234567890def\n"
                "discovered_branch: feat/foo\n"
                "---\n# ENH-5103: T\n"
            ),
            "P3-ENH-5103-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["discovered_date"] == "2026-06-30"
        assert fields["discovered_commit"] == "abc1234567890def"
        assert fields["discovered_branch"] == "feat/foo"

    def test_decision_ref_extracted(self, tmp_path: Path) -> None:
        """decision_ref surfaced alongside decision_needed."""
        path, config = self._write_issue(
            tmp_path,
            (
                "---\nstatus: open\n"
                "decision_needed: true\n"
                "decision_ref: ARCHITECTURE-049\n"
                "---\n# ENH-5104: T\n"
            ),
            "P3-ENH-5104-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["decision_needed"] == "true"
        assert fields["decision_ref"] == "ARCHITECTURE-049"

    def test_learning_tests_required_renders_with_count(self, tmp_path: Path) -> None:
        """learning_tests_required list renders as '(n targets: a, b, c)'."""
        path, config = self._write_issue(
            tmp_path,
            (
                "---\nstatus: open\n"
                "learning_tests_required:\n- pytest\n- hypothesis\n"
                "---\n# ENH-5105: T\n"
            ),
            "P3-ENH-5105-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["learning_tests_required"] == "pytest, hypothesis"

    def test_missing_artifacts_as_list_renders_count(self, tmp_path: Path) -> None:
        """missing_artifacts list → comma-joined string."""
        path, config = self._write_issue(
            tmp_path,
            (
                "---\nstatus: open\n"
                "missing_artifacts:\n- docs/REF.md\n- src/foo.py\n"
                "---\n# ENH-5106: T\n"
            ),
            "P3-ENH-5106-t.md",
        )
        fields = _parse_card_fields(path, config)
        assert fields["missing_artifacts"] == "docs/REF.md, src/foo.py"

    def test_regression_no_new_fields_renders_identically(self, tmp_path: Path) -> None:
        """Issue with NO new fields extracts identically to pre-change baseline.

        Critical regression guard (ENH-2535 AC #2): issues lacking any of the new
        fields render exactly as they did before this enhancement.
        """
        path, config = self._write_issue(
            tmp_path,
            (
                "---\nstatus: open\n"
                "confidence_score: 80\n"
                "outcome_confidence: 75\n"
                "labels: [a, b]\n"
                "---\n# ENH-5107: T\n"
            ),
            "P3-ENH-5107-t.md",
        )
        fields = _parse_card_fields(path, config)
        # New closure / discovery / relationship / decision_ref keys must be None
        for k in (
            "closing_note",
            "closed_by",
            "closed_at",
            "cancelled_reason",
            "deferred_reason",
            "deferred_date",
            "discovered_date",
            "discovered_commit",
            "discovered_branch",
            "discovered_source",
            "discovered_external_repo",
            "parent",
            "relates_to",
            "depends_on",
            "blocked_by",
            "blocks",
            "supersedes",
            "decomposed_into",
            "decision_ref",
            "affects",
            "focus_area",
        ):
            assert fields.get(k) is None, f"{k} should be None for a baseline issue"


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

    def test_minimal_card_uses_fallback_defaults(self, stable_snapshot_env: None) -> None:
        """Empty fields dict renders with '???' and 'Untitled' fallbacks."""
        card = _render_card({})
        assert "???" in card
        assert "Untitled" in card

    def test_card_contains_issue_id_and_title(self, stable_snapshot_env: None) -> None:
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

    def test_card_has_box_drawing_borders(self, stable_snapshot_env: None) -> None:
        """Rendered card uses box-drawing characters for borders."""
        card = _render_card({"issue_id": "BUG-1", "title": "Test"})
        assert "┌" in card  # ┌ top-left
        assert "┘" in card  # ┘ bottom-right

    def test_long_unbreakable_word_truncated_not_extended(self, stable_snapshot_env: None) -> None:
        """A very long single token in summary is truncated, not left to bleed
        past the right border (ENH-2574 AC #7)."""
        long_word = "x" * 120
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "Short",
            "summary": long_word,
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        # The full unbreakable token must NOT bleed into the card...
        assert long_word not in card
        # ...but a truncated, ellipsis-terminated prefix of it should.
        assert "x…" in card

    # -- ENH-2535 closure block rendering --

    def test_closure_block_present_for_done_status(self, stable_snapshot_env: None) -> None:
        """Closure block renders when status: done and closing_note is set."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "status": "Completed",
            "raw_status": "done",
            "closure_text": "Fixed via X",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        assert "Closing note: Fixed via X" in card

    def test_closure_block_absent_for_open_status(self, stable_snapshot_env: None) -> None:
        """Closure block is NOT rendered when status: Open even if closing_note is set."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "status": "Open",
            "raw_status": "open",
            "closure_text": "premature",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        assert "Closing note:" not in card

    # -- ENH-2535 relationships block rendering --

    def test_relationships_block_renders_blocked_by(self, stable_snapshot_env: None) -> None:
        """Relationships block renders blocked_by line when populated."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "blocked_by": "BUG-9",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        assert "Blocked by: BUG-9" in card

    def test_blocked_status_includes_blocked_by_name(self, stable_snapshot_env: None) -> None:
        """Status: Blocked + blocked_by → card names the blocker."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "status": "Blocked",
            "blocked_by": "BUG-9, BUG-10",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        assert "Blocked by: BUG-9, BUG-10" in card

    # -- ENH-2535 discovery block rendering --

    def test_discovery_block_renders_discovered_date(self, stable_snapshot_env: None) -> None:
        """Discovery block renders discovered_date distinct from captured_at."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "captured_at": "2026-07-01T00:00:00Z",
            "discovered_date": "2026-06-15",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        assert "Discovered: 2026-06-15" in card
        # Dates render date-only (ENH-2574 item 5) — the time component is dropped.
        assert "Captured at: 2026-07-01" in card
        assert "Captured at: 2026-07-01T00:00:00Z" not in card

    def test_discovered_commit_shortened(self, stable_snapshot_env: None) -> None:
        """Full discovered_commit SHA is shortened to 7 chars in the card."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "discovered_commit": "abc1234567890def",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        assert "Discovered commit: abc1234" in card
        # Full SHA must NOT bleed into the rendered line (only the 7-char prefix)
        assert "abc1234567890def" not in card

    # -- ENH-2535 decision coupling --

    def test_decision_coupling_with_ref(self, stable_snapshot_env: None) -> None:
        """decision_needed: true + decision_ref renders 'Decision needed → <ref>'."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "decision_needed": "true",
            "decision_ref": "ARCHITECTURE-049",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        assert "Decision needed → ARCHITECTURE-049" in card

    def test_decision_explicit_no_when_false(self, stable_snapshot_env: None) -> None:
        """decision_needed: false renders 'Decision needed: no' explicitly."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "decision_needed": "false",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        assert "Decision needed: no" in card

    def test_decision_ref_alone_renders_explicit(self, stable_snapshot_env: None) -> None:
        """decision_ref without decision_needed renders 'Decision ref: <value>'."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "decision_ref": "ARCHITECTURE-049",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        assert "Decision ref: ARCHITECTURE-049" in card

    # -- ENH-2574 summary reflow (item 1) --

    def test_summary_reflow_no_orphan_lines(self, stable_snapshot_env: None) -> None:
        """Hard line breaks within a paragraph are reflowed together instead of
        surviving as separate wrapped lines with 1-2 word orphans."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "summary": "First sentence here.\nSecond sentence here.\nThird sentence here.",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        assert "First sentence here. Second sentence here." in card

    def test_summary_reflow_preserves_blank_line_paragraphs(
        self, stable_snapshot_env: None
    ) -> None:
        """Blank-line-separated paragraphs remain distinct (only in-paragraph
        hard breaks are reflowed)."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "summary": "Paragraph one.\n\nParagraph two.",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        lines = card.splitlines()
        p1_idx = next(i for i, ln in enumerate(lines) if "Paragraph one." in ln)
        p2_idx = next(i for i, ln in enumerate(lines) if "Paragraph two." in ln)
        assert p2_idx > p1_idx + 1  # a blank content row separates the two

    # -- ENH-2574 status coloring (item 3) --

    def test_status_colors_applied_per_state(self, monkeypatch: Any) -> None:
        """Each non-Open, non-Completed status gets its own SGR color code."""
        monkeypatch.setattr("little_loops.cli.output._USE_COLOR", True, raising=False)
        monkeypatch.setattr("little_loops.cli.output.terminal_width", lambda **_kw: 80)
        for status, code in (
            ("In Progress", "33"),
            ("Blocked", "31"),
            ("Deferred", "2"),
            ("Cancelled", "2"),
        ):
            fields: dict[str, str | None] = {
                "issue_id": "ENH-1",
                "title": "T",
                "status": status,
                "path": ".issues/enhancements/P3-ENH-1.md",
            }
            card = _render_card(fields)
            assert f"\033[{code}m{status}\033[0m" in card

    # -- ENH-2574 card width scaling (item 2) --

    def test_width_scales_up_on_wide_terminal(self, monkeypatch: Any) -> None:
        """Card targets ~100 cols on a wide terminal instead of staying pinned
        to the (narrow) metadata width."""
        monkeypatch.setattr("little_loops.cli.output._USE_COLOR", False, raising=False)
        monkeypatch.setattr("little_loops.cli.issues.show.terminal_width", lambda **_kw: 200)
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        top_border_len = len(card.splitlines()[0])
        assert top_border_len >= 98  # ~100-col target, +2 border chars

    def test_width_never_exceeds_terminal_minus_four(self, monkeypatch: Any) -> None:
        """Card width is always capped at terminal_width() - 4."""
        monkeypatch.setattr("little_loops.cli.output._USE_COLOR", False, raising=False)
        monkeypatch.setattr("little_loops.cli.issues.show.terminal_width", lambda **_kw: 200)
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        top_border_len = len(card.splitlines()[0])
        assert top_border_len <= 196  # terminal_width() - 4

    # -- ENH-2574 metadata column alignment (item 6) --

    def test_column_alignment_with_four_plus_rows(self, stable_snapshot_env: None) -> None:
        """Detail-block keys right-pad into a column once there are >= 4 rows."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "blocked_by": "BUG-1",
            "discovered_date": "2026-01-01",
            "discovered_branch": "main",
            "history": "capture",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        # "Discovered branch:" is the longest label; shorter labels ("History:")
        # pad out to match, so both lines' values start at the same column.
        history_line = next(ln for ln in card.splitlines() if "History:" in ln)
        branch_line = next(ln for ln in card.splitlines() if "Discovered branch:" in ln)
        history_col = history_line.index("capture")
        branch_col = branch_line.index("main")
        assert history_col == branch_col

    def test_no_column_alignment_below_four_rows(self, stable_snapshot_env: None) -> None:
        """Fewer than 4 detail rows: no padding is inserted between the label
        and its value."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "blocked_by": "BUG-9",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        assert "Blocked by: BUG-9" in card

    # -- ENH-2574 low-signal row pruning (item 5) --

    def test_source_manual_hidden(self, stable_snapshot_env: None) -> None:
        """'Source: manual' (the default case) is hidden from the card."""
        fields: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "source": "manual",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card = _render_card(fields)
        assert "Source:" not in card

    def test_needs_formatting_shown_only_when_fmt_missing(self, stable_snapshot_env: None) -> None:
        """'Needs: formatting' renders only when fmt is ✗; nothing renders when
        formatting is already present."""
        fields_missing: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "fmt": "✗",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        assert "Needs: formatting" in _render_card(fields_missing)

        fields_ok: dict[str, str | None] = {
            "issue_id": "ENH-1",
            "title": "T",
            "fmt": "✓",
            "path": ".issues/enhancements/P3-ENH-1.md",
        }
        card_ok = _render_card(fields_ok)
        assert "Needs:" not in card_ok
        assert "Norm:" not in card_ok
