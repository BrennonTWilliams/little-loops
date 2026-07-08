"""Unit tests for the coverage-aware unresolved-option/open-question probes (ENH-2446).

Mirrors the test_decide_issue_skill.py pattern: pure-Python tests against
fixture content (string-in / int-out), no subprocess or filesystem. The
fixture-driven golden tests live in test_decide_issue_skill.py's
TestFEAT2339MixedShapeSnapshot.
"""

from __future__ import annotations

FIXTURE_PATH = (
    __import__("pathlib").Path(__file__).parent
    / "fixtures"
    / "issues"
    / "FEAT-2339-mixed-resolved-unresolved.md"
)


class TestCountUnresolvedOptions:
    """count_unresolved_options distinguishes resolved vs. unresolved option blocks (ENH-2446)."""

    def test_zero_options_when_section_absent(self) -> None:
        from little_loops.issue_parser import count_unresolved_options

        content = "## Summary\n\nNo options here.\n"
        assert count_unresolved_options(content) == 0

    def test_zero_when_all_options_resolved(self) -> None:
        from little_loops.issue_parser import count_unresolved_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "### Option A\n"
            "Do X.\n"
            "\n"
            "> **Selected:** A\n"
            "\n"
            "### Option B\n"
            "Do Y.\n"
            "\n"
            "### Decision Rationale\n"
            "We picked A.\n"
        )
        assert count_unresolved_options(content) == 0

    def test_counts_unresolved_option(self) -> None:
        from little_loops.issue_parser import count_unresolved_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "### Option A\n"
            "Do X.\n"
            "\n"
            "> **Selected:** A\n"
            "\n"
            "### Option B\n"
            "Do Y.\n"
            "\n"
            "### Option C\n"
            "Do Z.\n"
        )
        assert count_unresolved_options(content) == 2

    def test_decision_rationale_marks_resolved(self) -> None:
        """A ### Decision Rationale subsection (without Selected:) is sufficient."""
        from little_loops.issue_parser import count_unresolved_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "### Option A\n"
            "Do X.\n"
            "\n"
            "### Decision Rationale\n"
            "Picked A.\n"
            "\n"
            "### Option B\n"
            "Do Y.\n"
        )
        assert count_unresolved_options(content) == 1

    def test_bold_option_label_format(self) -> None:
        """Pattern 2: bold Option A: labels are recognized."""
        from little_loops.issue_parser import count_unresolved_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A: Inline rewriting.**\n"
            "First approach.\n"
            "\n"
            "**Option B: Adapter wrapper.**\n"
            "Second approach.\n"
        )
        assert count_unresolved_options(content) == 2

    def test_falls_back_to_codebase_research_when_proposed_empty(self) -> None:
        from little_loops.issue_parser import count_unresolved_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "Some narrative.\n"
            "\n"
            "## Codebase Research Findings\n"
            "\n"
            "### Option X\n"
            "Approach one.\n"
        )
        assert count_unresolved_options(content) == 1

    def test_fixture_mixed_shape(self) -> None:
        """FEAT-2339 fixture: 2 options, both resolved -> 0 unresolved options."""
        from little_loops.issue_parser import count_unresolved_options

        content = FIXTURE_PATH.read_text()
        assert count_unresolved_options(content) == 0


class TestCountOpenQuestionsInSections:
    """count_open_questions_in_sections scans Edge Cases / Confidence Check Notes / Open Questions (ENH-2446)."""

    def test_no_sections_returns_zero(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Summary\n\nJust text.\n"
        assert count_open_questions_in_sections(content) == 0

    def test_edge_cases_section_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Edge Cases\n"
            "\n"
            "- Q: How to handle malformed JSON? Open question.\n"
            "- Q: What if upstream is down? Needs decision.\n"
        )
        assert count_open_questions_in_sections(content) == 2

    def test_resolved_marker_excluded(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Open Questions\n"
            "\n"
            "- **Fork vs. flag.** ✅ **RESOLVED** (2026-06-04).\n"
            "- **Backoff strategy.** Open question.\n"
        )
        assert count_open_questions_in_sections(content) == 1

    def test_all_marker_variants_excluded(self) -> None:
        """✅ RESOLVED, ✔ RESOLVED, **RESOLVED**, > **RESOLVED** all exclude."""
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Open Questions\n"
            "\n"
            "- **Q1.** ✅ RESOLVED.\n"
            "- **Q2.** ✔ RESOLVED.\n"
            "- **Q3.** **RESOLVED**.\n"
            "- **Q4.** > **RESOLVED**.\n"
            "- **Q5.** Open.\n"
        )
        assert count_open_questions_in_sections(content) == 1

    def test_confidence_check_notes_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Confidence Check Notes\n"
            "\n"
            '- `confidence-check` flagged: "open question: retry policy" — decision needed.\n'
        )
        assert count_open_questions_in_sections(content) == 1

    def test_empty_section_returns_zero(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Edge Cases\n\n_(empty)_\n"
        assert count_open_questions_in_sections(content) == 0

    def test_fixture_mixed_shape(self) -> None:
        """FEAT-2339 fixture: 2 open questions in Edge Cases + 2 in Confidence Check Notes."""
        from little_loops.issue_parser import count_open_questions_in_sections

        content = FIXTURE_PATH.read_text()
        # 3 in Edge Cases + 2 in Confidence Check Notes = 5
        assert count_open_questions_in_sections(content) == 5


class TestQuestionGaps:
    """QuestionGaps dataclass mirrors FormatGaps shape (ENH-2446)."""

    def test_default_construction_has_gaps_false(self) -> None:
        from little_loops.issue_parser import QuestionGaps

        gaps = QuestionGaps()
        assert gaps.unresolved_options == []
        assert gaps.open_questions == []
        assert gaps.has_gaps is False

    def test_unresolved_options_only(self) -> None:
        from little_loops.issue_parser import QuestionGaps

        gaps = QuestionGaps(unresolved_options=["### Option C"])
        assert gaps.has_gaps is True
        assert gaps.open_questions == []

    def test_to_dict(self) -> None:
        from little_loops.issue_parser import QuestionGaps

        gaps = QuestionGaps(unresolved_options=["a"], open_questions=["b", "c"])
        d = gaps.to_dict()
        assert d == {"unresolved_options": ["a"], "open_questions": ["b", "c"]}


class TestCoverageAwareSurface:
    """Integration: count_unresolved_options + count_open_questions_in_sections together (ENH-2446)."""

    def test_clean_issue_no_unresolved_surface(self) -> None:
        from little_loops.issue_parser import (
            count_open_questions_in_sections,
            count_unresolved_options,
        )

        content = (
            "## Proposed Solution\n"
            "\n"
            "### Option A\n"
            "Do X.\n"
            "\n"
            "> **Selected:** A\n"
            "\n"
            "## Edge Cases\n"
            "\n"
            "- All handled.\n"
            "\n"
            "## Confidence Check Notes\n"
            "\n"
            "- All clear.\n"
        )
        assert count_unresolved_options(content) == 0
        assert count_open_questions_in_sections(content) == 0

    def test_mixed_fixture_has_unresolved_surface(self) -> None:
        """FEAT-2339: 0 unresolved options BUT 5 open questions -> NOT decidable."""
        from little_loops.issue_parser import (
            count_open_questions_in_sections,
            count_unresolved_options,
        )

        content = FIXTURE_PATH.read_text()
        assert count_unresolved_options(content) == 0
        assert count_open_questions_in_sections(content) > 0
