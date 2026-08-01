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


class TestLocatedOptionsDataclass:
    """LocatedOption/LocatedOptions dataclass shape and to_dict() (ENH-2950)."""

    def test_located_option_to_dict(self) -> None:
        from little_loops.issue_parser import LocatedOption

        option = LocatedOption(
            label="Option A", text="**Option A**\nDo X.", start_line=3, end_line=4
        )
        assert option.to_dict() == {
            "label": "Option A",
            "text": "**Option A**\nDo X.",
            "start_line": 3,
            "end_line": 4,
        }

    def test_located_options_to_dict_nests_options(self) -> None:
        from little_loops.issue_parser import LocatedOption, LocatedOptions

        option = LocatedOption(
            label="Option A", text="**Option A**\nDo X.", start_line=3, end_line=4
        )
        located = LocatedOptions(
            count=1, pattern="bold_label", heading="Proposed Solution", options=[option]
        )
        assert located.to_dict() == {
            "count": 1,
            "pattern": "bold_label",
            "heading": "Proposed Solution",
            "options": [option.to_dict()],
        }

    def test_located_options_defaults_to_empty_options_list(self) -> None:
        from little_loops.issue_parser import LocatedOptions

        located = LocatedOptions(count=0, pattern=None, heading=None)
        assert located.options == []
        assert located.to_dict()["options"] == []


class TestLocatedOptionsPatternNames:
    """LocatedOptions.pattern names each _OPTION_PATTERNS tier by name (ENH-2950)."""

    def test_section_header_pattern_name(self) -> None:
        from little_loops.issue_parser import locate_enumerable_options

        content = "## Proposed Solution\n\n### Option A\nDo X.\n\n### Option B\nDo Y.\n"
        located = locate_enumerable_options(content)
        assert located.pattern == "section_header"
        assert len(located.options) == 2

    def test_bold_label_pattern_name(self) -> None:
        from little_loops.issue_parser import locate_enumerable_options

        content = "## Proposed Solution\n\n**Option A**: Do X.\n\n**Option B**: Do Y.\n"
        located = locate_enumerable_options(content)
        assert located.pattern == "bold_label"
        assert len(located.options) == 2

    def test_numbered_pattern_name(self) -> None:
        from little_loops.issue_parser import locate_enumerable_options

        content = "## Proposed Solution\n\n1. **Option A**: Do X.\n2. **Option B**: Do Y.\n"
        located = locate_enumerable_options(content)
        assert located.pattern == "numbered"
        assert len(located.options) == 2

    def test_bullet_pattern_name(self) -> None:
        from little_loops.issue_parser import locate_enumerable_options

        content = "## Proposed Solution\n\n- (a) Do X.\n- (b) Do Y.\n"
        located = locate_enumerable_options(content)
        assert located.pattern == "bullet"
        assert len(located.options) == 2

    def test_provisional_e_pattern_name(self) -> None:
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Scope Boundaries\n\n"
            "- stamp it or move it to Out of scope with a stated reason — do not "
            "leave it unaddressed\n"
        )
        located = locate_enumerable_options(content)
        assert located.pattern == "provisional_e"


class TestCountEnumerableOptions:
    """count_enumerable_options/locate_enumerable_options widen to a whole-document
    fallback scan when the scoped sections yield nothing (ENH-2821)."""

    def test_zero_when_no_options_anywhere(self) -> None:
        from little_loops.issue_parser import count_enumerable_options

        content = "## Summary\n\nNo options here.\n"
        assert count_enumerable_options(content) == 0

    def test_finds_options_in_proposed_solution(self) -> None:
        from little_loops.issue_parser import locate_enumerable_options

        content = "## Proposed Solution\n\n### Option A\nDo X.\n\n### Option B\nDo Y.\n"
        located = locate_enumerable_options(content)
        assert located.count == 2
        assert located.heading == "Proposed Solution"

    def test_finds_options_nested_under_h3_in_unrelated_h2(self) -> None:
        """FEAT-2817 shape: options nested under an H3 inside ## Open Questions,
        a section not in the scoped/fallback list, are found by the whole-document scan."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\nSome unrelated prose, no options here.\n\n"
            "## Open Questions\n\n"
            "### Codebase Research Findings — delegation architecture decision\n\n"
            "**Option A**: Do X.\n\n"
            "**Option B**: Do Y.\n\n"
            "**Recommended**: Option A\n\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 2
        assert located.heading == "Open Questions"

    def test_finds_options_under_decorated_fallback_heading(self) -> None:
        """A fallback heading decorated with a suffix still resolves via the
        whole-document scan (the exact-H2 scoped lookup alone would miss it)."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Proposed Solution\n\nNo options here.\n\n"
            "## Codebase Research Findings — delegation architecture decision\n\n"
            "### Option A\nDo X.\n\n### Option B\nDo Y.\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 2
        assert located.heading == "Codebase Research Findings — delegation architecture decision"


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


class TestPatternEDirectiveAlternatives:
    """_locate_directive_alternatives / locate_enumerable_options Pattern E tier
    (ENH-2936): an imperative decide-marker co-occurring with 2+ named alternatives
    and no stated preference, scanned over Scope Boundaries / Proposed Change /
    Proposed Solution / Open Questions."""

    def test_scope_boundaries_directive_is_decidable(self) -> None:
        """ENH-2866 shape: imperative marker + alternatives, no preference."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Scope Boundaries\n"
            "\n"
            "- stamp it or move it to Out of scope with a stated reason — do not "
            "leave it unaddressed\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 2
        assert located.heading == "Scope Boundaries"

    def test_bare_or_prose_without_imperative_marker_not_decidable(self) -> None:
        """Guardrail: bare 'X or Y' prose with no imperative marker must NOT match —
        that is the settled-informal-list case automation must not re-litigate."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Scope Boundaries\n\n- stamp it or move it to Out of scope with a stated reason\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 0
        assert located.heading is None

    def test_stated_preference_disqualifies_pattern_e(self) -> None:
        """A stated preference is Pattern D's job, not Pattern E's — the passage
        must not double-count as an un-preferenced directive."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Scope Boundaries\n"
            "\n"
            "- stamp it or move it to Out of scope — do not leave it unaddressed. "
            "**Recommended**: stamp it.\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 0
        assert located.heading is None

    def test_resolved_marker_disqualifies_pattern_e(self) -> None:
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Open Questions\n"
            "\n"
            "- Fork vs. flag — decide before implementation, X or Y. "
            "✅ RESOLVED (2026-06-04).\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 0
        assert located.heading is None

    def test_out_of_scan_scope_section_not_matched(self) -> None:
        """Pattern E's scan scope is narrower than Patterns A-D's whole-document
        scan — a directive sitting in an unrelated section is not picked up."""
        from little_loops.issue_parser import locate_enumerable_options

        content = "## Motivation\n\n- pick one: X or Y — must be decided before implementation.\n"
        located = locate_enumerable_options(content)
        assert located.count == 0
        assert located.heading is None

    def test_proposed_solution_directive_is_decidable(self) -> None:
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "Either extend the existing CLI or add a new subcommand — this must "
            "be decided before implementation.\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 2
        assert located.heading == "Proposed Solution"

    def test_line_wrapped_marker_still_matches(self) -> None:
        """Regression: markdown line-wraps at ~80 chars split an imperative marker
        across lines (e.g. 'do not leave\\n  it unaddressed') — the heuristic must
        normalize whitespace within its window, not search line-by-line only."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Scope Boundaries\n"
            "\n"
            "- **In scope**: stamp it or move it to Out of scope with a stated "
            "reason — do not leave\n"
            "  it unaddressed.\n"
            "- **Out of scope**: nothing else.\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 2
        assert located.heading == "Scope Boundaries"
