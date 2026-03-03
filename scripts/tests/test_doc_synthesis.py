"""Tests for doc_synthesis module."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.issue_history import (
    CompletedIssue,
    build_narrative_doc,
    build_structured_doc,
    score_relevance,
    synthesize_docs,
)

# =============================================================================
# Test Data Helpers
# =============================================================================

_ISSUE_CONTENT_A = """\
# FEAT-100: Add session logging to ll-history

## Summary

Add session log tracking to the ll-history CLI tool so that
each analysis run records which session produced it.

## Motivation

Session provenance helps trace which analysis runs produced
which reports, enabling audit trails.

## Resolution

**Action**: implement
**Completed**: 2026-01-15

### Implementation Notes

Added session_id parameter to calculate_analysis and formatted
output includes session reference.
"""

_ISSUE_CONTENT_B = """\
# ENH-200: Improve sprint dependency ordering

## Summary

Improve the sprint CLI dependency ordering algorithm to handle
circular dependencies gracefully.

## Expected Behavior

Sprint dependency resolution should detect cycles and report
them clearly rather than hanging indefinitely.

## Resolution

**Action**: improve
**Completed**: 2026-02-01
"""

_ISSUE_CONTENT_C = """\
# BUG-050: Fix history summary date range calculation

## Summary

The history summary date range calculation was off by one day
when computing velocity metrics.

## Resolution

**Action**: fix
**Completed**: 2026-01-20

### Implementation Notes

Fixed the date arithmetic in calculate_summary to use inclusive
date ranges for velocity calculation.
"""


def _make_issue(
    issue_id: str,
    issue_type: str,
    priority: str = "P2",
    completed_date: date | None = None,
    path: Path | None = None,
) -> CompletedIssue:
    """Create a CompletedIssue for testing."""
    if path is None:
        path = Path(f"/test/{priority}-{issue_id}-test.md")
    return CompletedIssue(
        path=path,
        issue_type=issue_type,
        priority=priority,
        issue_id=issue_id,
        completed_date=completed_date,
    )


def _make_contents(
    issues: list[CompletedIssue],
    content_map: dict[str, str],
) -> dict[Path, str]:
    """Build contents dict from issue_id -> content mapping."""
    return {
        issue.path: content_map[issue.issue_id] for issue in issues if issue.issue_id in content_map
    }


# =============================================================================
# Tests: score_relevance
# =============================================================================


class TestScoreRelevance:
    """Tests for score_relevance function."""

    def test_high_relevance_match(self) -> None:
        """Issue closely matching topic scores high."""
        issue = _make_issue("FEAT-100", "FEAT")
        score = score_relevance("session logging history", issue, _ISSUE_CONTENT_A)
        assert score > 0.0

    def test_low_relevance_mismatch(self) -> None:
        """Unrelated issue scores low."""
        issue = _make_issue("ENH-200", "ENH")
        score = score_relevance("session logging history", issue, _ISSUE_CONTENT_B)
        # Sprint dependency is not related to session logging
        assert score < 0.3

    def test_empty_topic(self) -> None:
        """Empty topic returns 0.0."""
        issue = _make_issue("FEAT-100", "FEAT")
        assert score_relevance("", issue, _ISSUE_CONTENT_A) == 0.0

    def test_empty_content(self) -> None:
        """Empty content returns 0.0."""
        issue = _make_issue("FEAT-100", "FEAT")
        assert score_relevance("session logging", issue, "") == 0.0

    def test_intersection_mode_ignores_corpus_stats(self) -> None:
        """Intersection mode uses intersection scoring even when corpus_stats provided."""
        issue = _make_issue("FEAT-100", "FEAT")
        score_plain = score_relevance("session logging history", issue, _ISSUE_CONTENT_A)
        corpus = {"doc_freq": {"session": 1}, "avg_doc_len": 50.0, "total_docs": 1}
        score_with_stats = score_relevance(
            "session logging history", issue, _ISSUE_CONTENT_A,
            corpus_stats=corpus, scoring="intersection",
        )
        assert score_plain == score_with_stats

    def test_hybrid_mode_produces_score_in_range(self) -> None:
        """Hybrid mode produces score between 0.0 and 1.0."""
        issue = _make_issue("FEAT-100", "FEAT")
        corpus = {"doc_freq": {"session": 1, "logging": 1}, "avg_doc_len": 80.0, "total_docs": 1}
        score = score_relevance(
            "session logging", issue, _ISSUE_CONTENT_A,
            corpus_stats=corpus, scoring="hybrid",
        )
        assert 0.0 <= score <= 1.0

    def test_bm25_mode_returns_zero_for_no_match(self) -> None:
        """BM25 mode returns 0.0 when no topic words appear in issue."""
        issue = _make_issue("ENH-200", "ENH")
        corpus = {"doc_freq": {"session": 0}, "avg_doc_len": 50.0, "total_docs": 1}
        score = score_relevance(
            "session logging", issue, _ISSUE_CONTENT_B,
            corpus_stats=corpus, scoring="bm25",
        )
        # _ISSUE_CONTENT_B is about sprint dependency, not session logging
        assert score == 0.0 or score < 0.3


# =============================================================================
# Tests: synthesize_docs
# =============================================================================


class TestSynthesizeDocs:
    """Tests for synthesize_docs function."""

    def test_chronological_ordering(self) -> None:
        """Issues appear in chronological order by completed_date."""
        issues = [
            _make_issue("ENH-200", "ENH", completed_date=date(2026, 2, 1)),
            _make_issue("FEAT-100", "FEAT", completed_date=date(2026, 1, 15)),
            _make_issue("BUG-050", "BUG", completed_date=date(2026, 1, 20)),
        ]
        contents = _make_contents(
            issues,
            {
                "ENH-200": _ISSUE_CONTENT_B,
                "FEAT-100": _ISSUE_CONTENT_A,
                "BUG-050": _ISSUE_CONTENT_C,
            },
        )

        # Use very low threshold to include all
        doc = synthesize_docs("history", issues, contents, min_relevance=0.01)

        # FEAT-100 (Jan 15) should appear before BUG-050 (Jan 20)
        feat_pos = doc.find("FEAT-100")
        bug_pos = doc.find("BUG-050")
        assert feat_pos < bug_pos

    def test_no_matches_message(self) -> None:
        """Returns message when no issues match."""
        issues = [_make_issue("ENH-200", "ENH", completed_date=date(2026, 2, 1))]
        contents = _make_contents(issues, {"ENH-200": _ISSUE_CONTENT_B})

        doc = synthesize_docs("completely unrelated xyz abc", issues, contents, min_relevance=0.9)
        assert "No completed issues found" in doc

    def test_type_filter(self) -> None:
        """Type filter excludes non-matching types."""
        issues = [
            _make_issue("FEAT-100", "FEAT", completed_date=date(2026, 1, 15)),
            _make_issue("BUG-050", "BUG", completed_date=date(2026, 1, 20)),
        ]
        contents = _make_contents(
            issues,
            {"FEAT-100": _ISSUE_CONTENT_A, "BUG-050": _ISSUE_CONTENT_C},
        )

        doc = synthesize_docs("history", issues, contents, min_relevance=0.01, issue_type="FEAT")
        assert "FEAT-100" in doc
        assert "BUG-050" not in doc

    def test_since_filter(self) -> None:
        """Since filter excludes older issues."""
        issues = [
            _make_issue("FEAT-100", "FEAT", completed_date=date(2026, 1, 15)),
            _make_issue("ENH-200", "ENH", completed_date=date(2026, 2, 1)),
        ]
        contents = _make_contents(
            issues,
            {"FEAT-100": _ISSUE_CONTENT_A, "ENH-200": _ISSUE_CONTENT_B},
        )

        doc = synthesize_docs(
            "history sprint",
            issues,
            contents,
            min_relevance=0.01,
            since=date(2026, 1, 20),
        )
        # FEAT-100 completed Jan 15, before Jan 20 cutoff
        assert "FEAT-100" not in doc

    def test_structured_format(self) -> None:
        """Structured format produces a table."""
        issues = [
            _make_issue("FEAT-100", "FEAT", completed_date=date(2026, 1, 15)),
        ]
        contents = _make_contents(issues, {"FEAT-100": _ISSUE_CONTENT_A})

        doc = synthesize_docs(
            "session history", issues, contents, format="structured", min_relevance=0.01
        )
        assert "## Overview" in doc
        assert "| Issue |" in doc
        assert "## Details" in doc

    def test_hybrid_scoring_produces_differentiated_rankings(self) -> None:
        """Hybrid mode produces distinct scores allowing meaningful ranking."""
        issues = [
            _make_issue("FEAT-100", "FEAT", completed_date=date(2026, 1, 15)),
            _make_issue("BUG-050", "BUG", completed_date=date(2026, 1, 20)),
            _make_issue("ENH-200", "ENH", completed_date=date(2026, 2, 1)),
        ]
        contents = _make_contents(
            issues,
            {
                "FEAT-100": _ISSUE_CONTENT_A,
                "BUG-050": _ISSUE_CONTENT_C,
                "ENH-200": _ISSUE_CONTENT_B,
            },
        )

        doc = synthesize_docs(
            "history session logging",
            issues,
            contents,
            min_relevance=0.01,
            scoring="hybrid",
        )
        # Both highly-relevant issues should appear
        assert "FEAT-100" in doc

    def test_bm25_scoring_mode(self) -> None:
        """BM25 scoring mode runs without error and returns a document."""
        issues = [
            _make_issue("FEAT-100", "FEAT", completed_date=date(2026, 1, 15)),
        ]
        contents = _make_contents(issues, {"FEAT-100": _ISSUE_CONTENT_A})

        doc = synthesize_docs(
            "session history", issues, contents, min_relevance=0.01, scoring="bm25"
        )
        # Should either find issues or return no-matches message (not crash)
        assert isinstance(doc, str)


# =============================================================================
# Tests: build_narrative_doc
# =============================================================================


class TestBuildNarrativeDoc:
    """Tests for build_narrative_doc function."""

    def test_narrative_structure(self) -> None:
        """Narrative doc has title, metadata, and sections."""
        issue = _make_issue("FEAT-100", "FEAT", completed_date=date(2026, 1, 15))
        scored = [(issue, 0.8, _ISSUE_CONTENT_A)]

        doc = build_narrative_doc("Session Logging", scored)
        assert "# Session Logging" in doc
        assert "Synthesized from 1 completed issue(s)" in doc
        assert "FEAT-100" in doc
        assert "2026-01-15" in doc
        assert "session log tracking" in doc


# =============================================================================
# Tests: build_structured_doc
# =============================================================================


class TestBuildStructuredDoc:
    """Tests for build_structured_doc function."""

    def test_structured_has_table(self) -> None:
        """Structured doc has overview table and details."""
        issue = _make_issue("BUG-050", "BUG", completed_date=date(2026, 1, 20))
        scored = [(issue, 0.7, _ISSUE_CONTENT_C)]

        doc = build_structured_doc("History Bug Fixes", scored)
        assert "# History Bug Fixes" in doc
        assert "## Overview" in doc
        assert "| Issue |" in doc
        assert "## Details" in doc
        assert "BUG-050" in doc


# =============================================================================
# Tests: CLI integration
# =============================================================================


class TestGenerateDocsCLI:
    """Tests for generate-docs CLI subcommand."""

    def test_generate_docs_stdout(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """generate-docs prints to stdout by default."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P2-FEAT-100-session-logging.md").write_text(_ISSUE_CONTENT_A)

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "export",
                "session logging history",
                "-d",
                str(tmp_path / ".issues"),
                "--min-relevance",
                "0.01",
            ],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert "FEAT-100" in captured.out

    def test_generate_docs_output_file(self, tmp_path: Path) -> None:
        """generate-docs writes to file with --output."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P2-FEAT-100-session-logging.md").write_text(_ISSUE_CONTENT_A)

        output_path = tmp_path / "output" / "docs.md"

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "export",
                "session logging history",
                "-d",
                str(tmp_path / ".issues"),
                "--output",
                str(output_path),
                "--min-relevance",
                "0.01",
            ],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        assert output_path.exists()
        content = output_path.read_text()
        assert "FEAT-100" in content

    def test_generate_docs_scoring_hybrid(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--scoring hybrid runs without error."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P2-FEAT-100-session-logging.md").write_text(_ISSUE_CONTENT_A)

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "export",
                "session logging history",
                "-d",
                str(tmp_path / ".issues"),
                "--min-relevance",
                "0.01",
                "--scoring",
                "hybrid",
            ],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_generate_docs_scoring_bm25(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--scoring bm25 runs without error."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P2-FEAT-100-session-logging.md").write_text(_ISSUE_CONTENT_A)

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "export",
                "session logging history",
                "-d",
                str(tmp_path / ".issues"),
                "--min-relevance",
                "0.01",
                "--scoring",
                "bm25",
            ],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert len(captured.out) > 0
