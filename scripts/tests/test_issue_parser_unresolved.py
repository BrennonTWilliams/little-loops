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
            "residual_directive": None,
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

    def test_decision_rules_numbered_pattern_name(self) -> None:
        """BUG-3293: bold-numbered items under Program Design -> Decision Rules."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Program Design\n\n"
            "### Decision Rules\n\n"
            "1. **Identifier shape.** The identifier is not `[A-Za-z0-9]+` alone.\n"
            "2. **Title extent.** Whether a title may span more than one line.\n"
        )
        located = locate_enumerable_options(content)
        assert located.pattern == "decision_rules_numbered"
        assert located.heading == "Program Design"
        assert len(located.options) == 2

    def test_provisional_e_matches_program_design_versus_phrasing(self) -> None:
        """BUG-3293: "must be made before implementation ... versus ... versus" in
        Program Design is the exact un-numbered shape this issue itself used."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Program Design\n\n"
            "### Decision Rules\n\n"
            "One decision, and it must be made before implementation: route A "
            "versus route B versus both.\n"
        )
        located = locate_enumerable_options(content)
        assert located.pattern == "provisional_e"
        assert located.heading == "Program Design"


class TestDirectiveNotPreempted:
    """BUG-3287 defect 1: a tier match must not hide a co-located Pattern E
    directive — the directive is attached as ``residual_directive`` rather than
    silently dropped. Settled Option B: ``count``/``pattern``/``heading`` stay
    byte-identical to the tier-only result."""

    FIXTURE_PATH = (
        __import__("pathlib").Path(__file__).parent
        / "fixtures"
        / "issues"
        / "BUG-9301-tier-match-preempts-directive.md"
    )

    def test_tier_match_reports_residual_directive(self) -> None:
        from little_loops.issue_parser import locate_enumerable_options

        content = self.FIXTURE_PATH.read_text()
        located = locate_enumerable_options(content)
        assert located.pattern == "bold_label"
        assert located.heading == "Proposed Solution"
        assert located.count == 2
        assert located.residual_directive is not None
        assert located.residual_directive.heading == "Scope Boundaries"

    def test_residual_directive_is_nested_container_shape(self) -> None:
        """The field is LocatedOptions, not a bare LocatedOption — count==2 with
        exactly one option span, per _locate_directive_alternatives's contract."""
        from little_loops.issue_parser import locate_enumerable_options

        content = self.FIXTURE_PATH.read_text()
        located = locate_enumerable_options(content)
        rd = located.residual_directive
        assert rd is not None
        assert rd.pattern == "provisional_e"
        assert rd.count == 2
        assert len(rd.options) == 1

    def test_residual_directive_never_nests_further(self) -> None:
        from little_loops.issue_parser import locate_enumerable_options

        content = self.FIXTURE_PATH.read_text()
        located = locate_enumerable_options(content)
        rd = located.residual_directive
        assert rd is not None
        assert rd.residual_directive is None

    def test_no_directive_leaves_residual_directive_none(self) -> None:
        from little_loops.issue_parser import locate_enumerable_options

        content = "## Proposed Solution\n\n**Option A**: Do X.\n\n**Option B**: Do Y.\n"
        located = locate_enumerable_options(content)
        assert located.pattern == "bold_label"
        assert located.residual_directive is None

    def test_decision_rules_numbered_sets_residual_directive_none_explicitly(self) -> None:
        """BUG-3287 § Scope boundary — decision_rules_numbered is out of scope for
        the directive probe; the field must be explicitly None, not merely unset."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Program Design\n\n"
            "### Decision Rules\n\n"
            "1. **Identifier shape.** The identifier is not `[A-Za-z0-9]+` alone.\n"
            "2. **Title extent.** Whether a title may span more than one line.\n"
        )
        located = locate_enumerable_options(content)
        assert located.pattern == "decision_rules_numbered"
        assert located.residual_directive is None


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
        """A ### Decision Rationale heading resolves every option block in its section.

        BUG-3279 Rule 3: resolution via `### Decision Rationale` is section-scope,
        not block-scope. Option A's own span no longer absorbs the Decision
        Rationale block (it now stops at that heading, a qualifying boundary),
        but the section still carries the heading, so both Option A and the
        non-last-decided Option B read resolved -- this is the fix's "119-issue"
        direction: a winner that is not the last option no longer leaves earlier
        blocks reporting falsely unresolved.
        """
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
        assert count_unresolved_options(content) == 0

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

    def test_mixed_shape_depth_heading_and_bold_blocks_in_same_section(self) -> None:
        """BUG-3279 Rule 2 (sibling functions): a ### Option block keeps its own
        #### subheading while a **-shaped block in the same section terminates at
        a ### heading -- depth is decided per-match, not per-call, in the two
        _OPTION_HEADING_RE-based sibling functions."""
        from little_loops.issue_parser import count_unresolved_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "### Option A\n"
            "Do X.\n"
            "\n"
            "#### Decision 2 — legitimate nested detail\n"
            "More about A.\n"
            "\n"
            "> **Selected:** A\n"
            "\n"
            "**Option B: alt approach**\n"
            "Do Y.\n"
            "\n"
            "### Some unrelated heading\n"
            "Not part of Option B.\n"
        )
        assert count_unresolved_options(content) == 1

    def test_two_option_groups_under_one_decision_rationale_is_blunt(self) -> None:
        """BUG-3279 Rule 3 caveat: section scope is blunt -- one ### Decision
        Rationale resolves every option block in the section, even a second,
        genuinely-undecided group (FEAT-2478 shape). Pinned as the accepted
        trade-off, not a bug: count_unresolved_options reports 0 even though
        Decision 2 is still open."""
        from little_loops.issue_parser import count_unresolved_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "#### Decision 1\n"
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
            "Picked A for Decision 1.\n"
            "\n"
            "#### Decision 2\n"
            "\n"
            "### Option C\n"
            "Do Z.\n"
            "\n"
            "### Option D\n"
            "Do W.\n"
        )
        assert count_unresolved_options(content) == 0

    def test_whole_document_fallback_scope_is_the_h2_span_not_the_document(self) -> None:
        """BUG-3279 Rule 3: in the whole-document fallback, section-scope resolution
        is per-H2-span -- a Decision Rationale in one H2 must not resolve options
        under an unrelated second H2."""
        from little_loops.issue_parser import locate_unresolved_options

        content = (
            "## Some Unrelated Section\n"
            "\n"
            "### Option A\n"
            "Do X.\n"
            "\n"
            "### Decision Rationale\n"
            "Picked A.\n"
            "\n"
            "### Option B\n"
            "Do Y.\n"
            "\n"
            "## Another Unrelated Section\n"
            "\n"
            "### Option C\n"
            "Do Z.\n"
            "\n"
            "### Option D\n"
            "Do W.\n"
        )
        # Whole-document fallback returns on the *first* H2 section carrying any
        # option block (Some Unrelated Section) -- that section is fully resolved
        # by its own Decision Rationale.
        unresolved, heading = locate_unresolved_options(content)
        assert heading == "Some Unrelated Section"
        assert unresolved == 0


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


class TestCountOpenQuestionsWidenedSections:
    """ENH-3031: sections/vocabulary widened past the original three sections."""

    def test_integration_map_section_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Integration Map\n\n### Tests\n- Worth confirming whether this guard belongs here.\n"
        )
        assert count_open_questions_in_sections(content) == 1

    def test_codebase_research_findings_section_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        # ENH-3244: `\bTBD\b` moved out of the hedge scan into the
        # `template_placeholders` structural gap; this fixture now uses
        # `to be determined`, still a genuine prose hedge alternative.
        content = (
            "## Codebase Research Findings\n\n"
            "- To be determined whether this path is actually hit.\n"
        )
        assert count_open_questions_in_sections(content) == 1

    def test_suggested_fix_direction_section_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Suggested Fix Direction\n\n- This needs confirmation before implementation.\n"
        assert count_open_questions_in_sections(content) == 1

    def test_program_design_section_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Program Design\n\n- Worth deciding which module owns this.\n"
        assert count_open_questions_in_sections(content) == 1

    def test_hedge_vocabulary_worth_checking(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Open Questions\n\n- Worth checking whether this regresses.\n"
        assert count_open_questions_in_sections(content) == 1

    def test_hedge_vocabulary_should_be_considered(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Open Questions\n\n- An alternate approach should be considered.\n"
        assert count_open_questions_in_sections(content) == 1

    def test_hedge_vocabulary_to_be_determined(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Open Questions\n\n- Rollout timing: to be determined.\n"
        assert count_open_questions_in_sections(content) == 1

    def test_hedge_vocabulary_worth_a_decision(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Open Questions\n\n- Config default is worth a decision later.\n"
        assert count_open_questions_in_sections(content) == 1


class TestNumberedOpenQuestionCitations:
    """BUG-3169: a citation of a numbered question is not itself an open question.

    Verbatim shapes from the FEAT-3168 refine-to-ready-issue stall, where
    /ll:refine-issue --gap-analysis deposited ANSWERS that referenced
    "Open Question 1" and thereby kept check_hedges permanently red.
    """

    def test_answer_citing_numbered_question_not_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Open Questions\n"
            "\n"
            "- On Open Question 1: option (c) is confirmed not free. A grep/import\n"
            "  sweep of `scripts/little_loops/mcp_server/` found no `ContextVar` usage.\n"
        )
        assert count_open_questions_in_sections(content) == 0

    def test_possessive_citation_not_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Program Design\n"
            "\n"
            "- **Existing factory-closure precedent** (relevant to Open Question 1's\n"
            "  option (a)): `resource_index = build_resource_index(config)`.\n"
        )
        assert count_open_questions_in_sections(content) == 0

    def test_plural_numbered_citation_not_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Open Questions\n\n- Open Questions 2 and 3 were folded into the plan.\n"
        assert count_open_questions_in_sections(content) == 0

    def test_hash_prefixed_citation_not_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Edge Cases\n\n- Superseded by the answer to Open Question #2.\n"
        assert count_open_questions_in_sections(content) == 0

    def test_unnumbered_prose_hedge_still_counted(self) -> None:
        """The ENH-2446 case the phrase was added for must survive the narrowing."""
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Open Questions\n\n- Backoff strategy remains an open question.\n"
        assert count_open_questions_in_sections(content) == 1

    def test_numbered_question_ending_in_question_mark_still_counted(self) -> None:
        """Safety net 1: the canonical numbered-question shape ends in `?`."""
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Open Questions\n"
            "\n"
            "- **Open Question 1:** Should the policy be enforced at build time?\n"
        )
        assert count_open_questions_in_sections(content) == 1

    def test_numbered_question_with_hedge_vocabulary_still_counted(self) -> None:
        """Safety net 2: hedge vocabulary matches independently of the phrase."""
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Open Questions\n\n- Open Question 2: needs decision on transport.\n"
        assert count_open_questions_in_sections(content) == 1

    def test_item_leading_declaration_with_wrapped_continuation_counted(self) -> None:
        """The `\\?\\s*$` safety net cannot carry this shape.

        ``_count_unresolved_items_in_text`` joins continuation lines before
        matching (ENH-3031), so the `?` is no longer at the end of the item as
        soon as the question carries any context under it — the ordinary shape
        refine deposits. Only the item-leading declaration alternative sees it.
        """
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Open Questions\n"
            "\n"
            "- **Open Question 2:** Should the policy be enforced at build time?\n"
            "  Context: the builder currently runs at import time.\n"
        )
        assert count_open_questions_in_sections(content) == 1

    def test_item_leading_declaration_without_question_mark_counted(self) -> None:
        """A declaration phrased as an imperative carries no `?` and no hedge vocabulary."""
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Open Questions\n"
            "\n"
            "- **Open Question 3:** Decide the default transport before implementing.\n"
        )
        assert count_open_questions_in_sections(content) == 1

    def test_declaration_boundary_variants_counted(self) -> None:
        """`.` / em-dash / bold-close / numbered-list-marker declaration shapes."""
        from little_loops.issue_parser import count_open_questions_in_sections

        for item in (
            "- Open Question 4. Should we pin the signature.",
            "- Open Question 5 — transport default still unpicked.",
            "- **Open Question 1**: Should we gate at build time.",
            "1. Open Question 6: pick the default.",
        ):
            content = f"## Open Questions\n\n{item}\n"
            assert count_open_questions_in_sections(content) == 1, item

    def test_item_leading_citation_not_counted(self) -> None:
        """Item-leading is not sufficient — a citation continues into a verb phrase."""
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Open Questions\n\n- Open Question 2 was answered by the grep sweep.\n"
        assert count_open_questions_in_sections(content) == 0

    def test_hedge_split_across_wrapped_lines_is_detected(self) -> None:
        """The BUG-3025 hedge line wraps 'Worth' / 'confirming' across lines."""
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Integration Map\n"
            "\n"
            "### Tests\n"
            "- `scripts/tests/test_logo.py` — existing logo unit tests; checked and\n"
            "  contains no substring assertions, so it is unaffected. Worth\n"
            "  confirming whether the marker guard belongs here rather than\n"
            "  in the integration file.\n"
        )
        assert count_open_questions_in_sections(content) == 1

    def test_bug_3025_pre_review_fixture_detects_hedge(self) -> None:
        """Regression fixture pinned to bf80f3df (BUG-3025's original revision)."""
        from little_loops.issue_parser import count_open_questions_in_sections

        fixture = (
            __import__("pathlib").Path(__file__).parent
            / "fixtures"
            / "issues"
            / "BUG-3025-pre-review-original.md"
        )
        assert count_open_questions_in_sections(fixture.read_text()) >= 1

    def test_bug_3025_reviewed_fixture_has_no_hedges(self) -> None:
        """Regression fixture pinned to d85f49b5 — the reviewer already resolved the hedge."""
        from little_loops.issue_parser import count_open_questions_in_sections

        fixture = (
            __import__("pathlib").Path(__file__).parent
            / "fixtures"
            / "issues"
            / "BUG-3025-reviewed-uncorrected.md"
        )
        assert count_open_questions_in_sections(fixture.read_text()) == 0

    def test_fixture_mixed_shape(self) -> None:
        """FEAT-2339 fixture: 2 open questions in Edge Cases + 2 in Confidence Check Notes."""
        from little_loops.issue_parser import count_open_questions_in_sections

        content = FIXTURE_PATH.read_text()
        # 3 in Edge Cases + 2 in Confidence Check Notes = 5
        assert count_open_questions_in_sections(content) == 5

    # BUG-3296: a citation of an open question (points at one) is not a
    # declaration of one (asks one). Verbatim shapes from the corpus differential.

    def test_section_symbol_citation_not_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Integration Map\n"
            "\n"
            "- `scripts/little_loops/issue_parser.py` — convergence decision,"
            " § *Open question*; details below.\n"
        )
        assert count_open_questions_in_sections(content) == 0

    def test_see_citation_not_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Program Design\n"
            "\n"
            '- `severity: str` — `"error"` / `"warn"` (see Open Question)\n'
        )
        assert count_open_questions_in_sections(content) == 0

    def test_possessive_this_issue_citation_not_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Edge Cases\n"
            "\n"
            "- `docs/guides/DECISIONS_LOG_GUIDE.md` (`:198`) — description"
            " (per this issue's Open Question)\n"
        )
        assert count_open_questions_in_sections(content) == 0

    def test_quoted_phrase_in_code_span_not_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Open Questions\n"
            "\n"
            '- The vocabulary `"open question"` appears in the constant name.\n'
        )
        assert count_open_questions_in_sections(content) == 0

    def test_section_heading_in_code_span_not_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Integration Map\n"
            "\n"
            "- The heading is `## Open Questions` in every issue file.\n"
        )
        assert count_open_questions_in_sections(content) == 0

    def test_double_backtick_span_citation_not_counted(self) -> None:
        """A `` `## Open Questions` ``-style span must mask fully, not mis-pair."""
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Integration Map\n"
            "\n"
            "- Cite the heading using `` `## Open Questions` ``.\n"
        )
        assert count_open_questions_in_sections(content) == 0

    def test_item_leading_declaration_survivor_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Open Questions\n\n- Open question: does X need Y?\n"
        assert count_open_questions_in_sections(content) == 1

    def test_bold_item_leading_declaration_survivor_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Open Questions\n"
            "\n"
            "- **Open question: DSL task file format** — the issue does not"
            " specify the schema\n"
        )
        assert count_open_questions_in_sections(content) == 1

    def test_prose_hedge_survivor_counted(self) -> None:
        from little_loops.issue_parser import count_open_questions_in_sections

        content = (
            "## Open Questions\n\n- Minor open question on hook warning treatment"
            " — needs follow-up.\n"
        )
        assert count_open_questions_in_sections(content) == 1

    def test_word_boundary_survivor_wrapper_counted(self) -> None:
        """An unanchored `per` alternation would falsely mask inside 'wrapper'."""
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Open Questions\n\n- The wrapper open question: does X need Y?\n"
        assert count_open_questions_in_sections(content) == 1

    def test_word_boundary_survivor_proper_counted(self) -> None:
        """An unanchored `per` alternation would falsely mask inside 'Proper'."""
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Open Questions\n\n- Proper open questions handling is missing\n"
        assert count_open_questions_in_sections(content) == 1

    def test_word_boundary_survivor_deeper_counted(self) -> None:
        """An unanchored `per` alternation would falsely mask inside 'deeper'."""
        from little_loops.issue_parser import count_open_questions_in_sections

        content = "## Open Questions\n\n- A deeper open question remains\n"
        assert count_open_questions_in_sections(content) == 1


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

    def test_ordinary_implementation_steps_bold_numbered_list_not_matched(self) -> None:
        """BUG-3293: an ordinary bold-led numbered step list — this repo's dominant
        list convention — must not be misread as a decision block. Measured against
        the live corpus: a naive unscoped widening of the `numbered` tier to match
        any bold-numbered item hits 889/3197 files via exactly this shape."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Implementation Steps\n\n"
            "1. **Measure both routes before choosing.** Apply each candidate independently.\n"
            "2. **Land the corpus differential test first.** Before either change.\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 0
        assert located.heading is None

    def test_program_design_bold_numbered_outside_decision_rules_not_matched(self) -> None:
        """BUG-3293: a bold-numbered list under Program Design but NOT under the
        Decision Rules subsection (e.g. under Signatures) is not a decision block."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Program Design\n\n"
            "### Signatures\n\n"
            "1. **`locate_enumerable_options(content: str) -> LocatedOptions`**\n"
            "2. **`_locate_directive_alternatives(content: str) -> LocatedOptions | None`**\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 0
        assert located.heading is None

    def test_single_decision_rules_numbered_item_not_matched(self) -> None:
        """BUG-3293: a single bold-numbered item is never itself a "pick one of
        these" decision — the discriminator requires >= 2 matches."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Program Design\n\n"
            "### Decision Rules\n\n"
            "1. **Do not delete the filename fallback.** It is the only source of truth.\n"
        )
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


class TestLastOptionSpanBoundary:
    """BUG-3279: the last option's span ends at the first qualifying heading
    after it, not at the section end -- the absorption-of-trailing-prose fix."""

    def test_last_option_stops_at_trailing_subsection(self) -> None:
        """A trailing ### subsection after the last option is excluded from its text."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "### Option A\n"
            "Do X.\n"
            "\n"
            "### Option B\n"
            "Do Y.\n"
            "\n"
            "### Codebase Research Findings\n"
            "Unrelated analysis prose that belongs to no option.\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 2
        last = located.options[-1]
        assert "Codebase Research Findings" not in last.text
        assert "Unrelated analysis prose" not in last.text
        assert last.text.strip() == "### Option B\nDo Y."

    def test_option_list_as_section_tail_still_runs_to_section_end(self) -> None:
        """No trailing subsection -- the section-end fallback is preserved."""
        from little_loops.issue_parser import locate_enumerable_options

        content = "## Proposed Solution\n\n### Option A\nDo X.\n\n### Option B\nDo Y.\n"
        located = locate_enumerable_options(content)
        assert located.count == 2
        assert located.options[-1].text.strip() == "### Option B\nDo Y."

    def test_prior_decision_rationale_excluded_from_last_option_text(self) -> None:
        """A previously-appended ### Decision Rationale block appears in no option's text."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "### Option A\n"
            "Do X.\n"
            "\n"
            "### Option B\n"
            "Do Y.\n"
            "\n"
            "### Decision Rationale\n"
            "> **Selected:** Option A\n"
            "\n"
            "Picked A because reasons.\n"
        )
        located = locate_enumerable_options(content)
        for option in located.options:
            assert "Decision Rationale" not in option.text
            assert "Picked A" not in option.text

    def test_fence_aware_boundary_ignores_shell_comment_in_fence(self) -> None:
        """Rule 1: a `#`-shaped shell comment inside a fenced block is not a boundary."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A**: Do X.\n"
            "\n"
            "```bash\n"
            "# Build the slash-command string exactly as listed\n"
            "echo hi\n"
            "```\n"
            "\n"
            "More description of Option A.\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 1
        assert "echo hi" in located.options[0].text
        assert "More description of Option A." in located.options[0].text

    def test_section_header_tier_keeps_own_subheading(self) -> None:
        """Rule 2: a ### Option block's own #### subheading is not a boundary."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "### Option A\n"
            "Do X.\n"
            "\n"
            "#### Decision 2 — a legitimate nested subheading\n"
            "More detail on Option A.\n"
            "\n"
            "### Option B\n"
            "Do Y.\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 2
        assert "#### Decision 2" in located.options[0].text
        assert "More detail on Option A." in located.options[0].text

    def test_bold_label_tier_terminates_at_any_depth_heading(self) -> None:
        """Rule 2: a non-heading-shaped (bold_label) option stops at any-depth heading."""
        from little_loops.issue_parser import locate_enumerable_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A**: Do X.\n"
            "\n"
            "#### Some subheading\n"
            "This does not belong to Option A.\n"
        )
        located = locate_enumerable_options(content)
        assert located.count == 1
        assert "Some subheading" not in located.options[0].text
        assert "does not belong" not in located.options[0].text


class TestDecisionGroups:
    """DecisionGroup / _iter_decision_groups / is_group_resolved /
    locate_unresolved_decisions (BUG-3278): the unit of resolution is the
    decision *group* (one decision point), not the option block — Phase 7a
    marks only the winning option, so a per-block gate would read every
    loser as unresolved and never clear a correctly-decided single-decision
    issue."""

    def test_selected_on_one_option_resolves_the_whole_group(self) -> None:
        """Three Option A/B/C blocks with a callout on A -> one group,
        resolved — B and C must not report as residual (the per-block
        spec's failure mode)."""
        from little_loops.issue_parser import _iter_decision_groups, is_group_resolved

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A**: do the thing\n"
            "> **Selected:** Option A\n"
            "\n"
            "**Option B**: do the other thing\n"
            "\n"
            "**Option C**: do a third thing\n"
        )
        groups = _iter_decision_groups(content)
        assert len(groups) == 1
        assert groups[0].tier == "bold_label"
        assert len(groups[0].options) == 3
        assert is_group_resolved(content, groups[0]) is True

    def test_no_marker_anywhere_is_one_unresolved_group(self) -> None:
        from little_loops.issue_parser import _iter_decision_groups, is_group_resolved

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A**: do the thing\n"
            "\n"
            "**Option B**: do the other thing\n"
            "\n"
            "**Option C**: do a third thing\n"
        )
        groups = _iter_decision_groups(content)
        assert len(groups) == 1
        assert is_group_resolved(content, groups[0]) is False

    def test_section_level_rationale_single_group_resolves(self) -> None:
        """A section-level `### Decision Rationale` with the callout at the
        top of the section, not on any option line, resolves the section's
        one group (this issue's own shape)."""
        from little_loops.issue_parser import _iter_decision_groups, is_group_resolved

        content = (
            "## Proposed Solution\n"
            "\n"
            "### Decision Rationale\n"
            "> **Selected:** the shim.\n"
            "\n"
            "**Option A**: do the thing\n"
            "\n"
            "**Option B**: do the other thing\n"
        )
        groups = _iter_decision_groups(content)
        assert len(groups) == 1
        assert is_group_resolved(content, groups[0]) is True

    def test_section_level_rationale_two_groups_only_marked_one_resolves(self) -> None:
        """Assertion (c2) — the single-group restriction. An unrestricted
        section-level rule would resolve group B by side effect once group A
        is decided; that is this issue's own failure mode reproduced through
        the fix."""
        from little_loops.issue_parser import _iter_decision_groups, is_group_resolved

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A**: do the thing\n"
            "> **Selected:** Option A\n"
            "\n"
            "### Decision Rationale\n"
            "Chose Option A because reasons.\n"
            "\n"
            "- **(a) approach one**\n"
            "- **(b) approach two**\n"
        )
        groups = _iter_decision_groups(content, include_approximate_tiers=True)
        assert [g.tier for g in groups] == ["bold_label", "bullet"]
        assert is_group_resolved(content, groups[0]) is True
        assert is_group_resolved(content, groups[1]) is False

    def test_two_groups_co_located_in_one_section(self) -> None:
        """`**Option A/B/C**` plus a separate `- (a)/(b)` pair below it in the
        same `## Proposed Solution` -> two independently resolvable groups —
        the shape from the issue's own Steps to Reproduce."""
        from little_loops.issue_parser import _iter_decision_groups

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A**: do the thing\n"
            "\n"
            "**Option B**: do the other thing\n"
            "\n"
            "**Option C**: do a third thing\n"
            "\n"
            "- **(a) approach one**\n"
            "- **(b) approach two**\n"
        )
        groups = _iter_decision_groups(content, include_approximate_tiers=True)
        assert [g.tier for g in groups] == ["bold_label", "bullet"]
        assert len(groups[0].options) == 3
        assert len(groups[1].options) == 2
        # default (opt-out) mode must not see the bullet-tier group at all —
        # the ENH-2446 conservatism regression guard.
        default_groups = _iter_decision_groups(content)
        assert [g.tier for g in default_groups] == ["bold_label"]

    def test_directive_splits_a_same_tier_run_into_two_groups(self) -> None:
        """A tier run split by an intervening `**DECISION — pick one:**`
        directive is two groups, not one — the tier differs across the
        directive only in the sense that the directive itself intervenes."""
        from little_loops.issue_parser import _iter_decision_groups

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A**: do the thing\n"
            "\n"
            "**DECISION — pick one before step 4 touches this file: use A or B.**\n"
            "\n"
            "**Option B**: do the other thing\n"
        )
        groups = _iter_decision_groups(content, include_approximate_tiers=True)
        bold_groups = [g for g in groups if g.tier == "bold_label"]
        assert len(bold_groups) == 2

    def test_mid_group_callout_does_not_split_the_group(self) -> None:
        """Span rule: a `> **Selected:**` callout inserted mid-group does not
        split the group in two."""
        from little_loops.issue_parser import _iter_decision_groups, is_group_resolved

        content = (
            "## Proposed Solution\n"
            "\n"
            "- **(a) approach one**\n"
            "> **Selected:** (a) — per the stated recommendation\n"
            "- **(b) approach two**\n"
        )
        groups = _iter_decision_groups(content, include_approximate_tiers=True)
        assert len(groups) == 1
        assert len(groups[0].options) == 2
        assert is_group_resolved(content, groups[0]) is True

    def test_bold_prose_phantom_does_not_merge_into_real_group(self) -> None:
        """Scope Boundary guard: a bold-prose phantom block
        (`**Option A evidence**:`, the ENH-2967/BUG-1484 shape) must not be
        matched at all, and therefore cannot merge into or break a real
        group's contiguous-run — the shared `_BOLD_OPTION_MARKER` fragment
        prevents the match; this pins the grouping rule against it too."""
        from little_loops.issue_parser import _iter_decision_groups

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A evidence**: shows it works.\n"
            "\n"
            "**Option A**: do the thing\n"
            "\n"
            "**Option B**: do the other thing\n"
        )
        groups = _iter_decision_groups(content)
        assert len(groups) == 1
        assert len(groups[0].options) == 2

    def test_common_path_regression_guard(self) -> None:
        """Assertion (c) — a single-decision fixture with three options where
        one is decided reports zero unresolved groups, so the flag still
        clears in one run. The per-block filter fails here: losing options B
        and C would read as unresolved and the flag would never clear."""
        from little_loops.issue_parser import locate_unresolved_decisions

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A**: do the thing\n"
            "> **Selected:** Option A\n"
            "\n"
            "**Option B**: do the other thing\n"
            "\n"
            "**Option C**: do a third thing\n"
        )
        assert locate_unresolved_decisions(content) == []

    def test_two_decision_points_one_decided_leaves_one_unresolved(self) -> None:
        """Assertion (a) — two decision points, one decided, must still
        report exactly one surviving group."""
        from little_loops.issue_parser import locate_unresolved_decisions

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A**: do the thing\n"
            "> **Selected:** Option A\n"
            "\n"
            "**Option B**: do the other thing\n"
            "\n"
            "**Option C**: do a third thing\n"
            "\n"
            "- **(a) approach one**\n"
            "- **(b) approach two**\n"
        )
        unresolved = locate_unresolved_decisions(content, include_approximate_tiers=True)
        assert len(unresolved) == 1
        assert unresolved[0].tier == "bullet"

    def test_both_groups_marked_resolved_converges_to_zero(self) -> None:
        """Assertion (b) — convergence: with both groups marked resolved,
        the probe reports zero, so a second interactive run's clear is
        reachable."""
        from little_loops.issue_parser import locate_unresolved_decisions

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A**: do the thing\n"
            "> **Selected:** Option A\n"
            "\n"
            "**Option B**: do the other thing\n"
            "\n"
            "**Option C**: do a third thing\n"
            "\n"
            "- **(a) approach one**\n"
            "> **Selected:** (a) — per the stated recommendation\n"
            "- **(b) approach two**\n"
        )
        assert locate_unresolved_decisions(content, include_approximate_tiers=True) == []

    def test_provisional_e_unresolved_until_retired_by_prefix(self) -> None:
        """Assertion (c6) — a prose `pick one` directive reports exit-worthy
        residual (one unresolved group); the same fixture with a bare
        `**RESOLVED**` prefix on the directive line reports zero, because the
        group is no longer emitted (retirement is probe suppression, not
        `is_group_resolved`)."""
        from little_loops.issue_parser import locate_unresolved_decisions

        unresolved_content = (
            "## Proposed Solution\n"
            "\n"
            "**DECISION — pick one before step 4 touches this file: use the "
            "shim or rewrite the caller.**\n"
        )
        assert (
            len(locate_unresolved_decisions(unresolved_content, include_approximate_tiers=True))
            == 1
        )

        retired_content = (
            "## Proposed Solution\n"
            "\n"
            "**RESOLVED** — the shim. **DECISION — pick one before step 4 "
            "touches this file: use the shim or rewrite the caller.**\n"
        )
        assert locate_unresolved_decisions(retired_content, include_approximate_tiers=True) == []

    def test_decorated_resolved_prefix_does_not_suppress(self) -> None:
        """Guard against "simplifying" the retirement rule back into a
        permanent stall: the bold run must close immediately at `RESOLVED` —
        a decorated `**RESOLVED — the shim.**` matches nothing and the
        directive group keeps re-emitting."""
        from little_loops.issue_parser import locate_unresolved_decisions

        content = (
            "## Proposed Solution\n"
            "\n"
            "**RESOLVED — the shim.** **DECISION — pick one before step 4 "
            "touches this file: use the shim or rewrite the caller.**\n"
        )
        assert len(locate_unresolved_decisions(content, include_approximate_tiers=True)) == 1

    def test_appended_selected_callout_does_not_mark_directive_resolved_via_callout_re(
        self,
    ) -> None:
        """The appended `> **Selected:**` form does suppress the Pattern E
        probe (via `_PREFERENCE_MARKER_RE`), but is not itself a valid
        `_SELECTED_CALLOUT_RE` match — pinning why the prefix form, not the
        appended callout, is the prescribed retirement marker."""
        from little_loops.issue_parser import _SELECTED_CALLOUT_RE, locate_unresolved_decisions

        content = (
            "## Proposed Solution\n"
            "\n"
            "**DECISION — pick one before step 4 touches this file: use the "
            "shim or rewrite the caller.** > **Selected:** the shim.\n"
        )
        assert locate_unresolved_decisions(content, include_approximate_tiers=True) == []
        assert _SELECTED_CALLOUT_RE.search(content) is None

    def test_decision_rules_numbered_is_not_emitted_as_a_group(self) -> None:
        """Assertion (c7) — a `## Program Design` -> `### Decision Rules`
        bold-numbered block is `check-decidable`'s own decidable surface
        (`pattern == "decision_rules_numbered"`, count 2) but must not be
        emitted as a decision group: design rulings are not mutually
        exclusive alternatives, and emitting them would exit 1 on nearly
        every refined issue in this repo."""
        from little_loops.issue_parser import locate_enumerable_options, locate_unresolved_decisions

        content = (
            "## Program Design\n\n"
            "### Decision Rules\n\n"
            "1. **Identifier shape.** Use backticked spans.\n"
            "2. **Title extent.** Keep titles short.\n"
        )
        located = locate_enumerable_options(content)
        assert located.pattern == "decision_rules_numbered"
        assert located.count == 2
        assert locate_unresolved_decisions(content, include_approximate_tiers=True) == []

    def test_settled_decision_with_open_free_form_question_still_clears(self) -> None:
        """Assertion (d) — an issue with a settled decision but open
        free-form questions elsewhere still clears via this probe, proving
        it is narrower than `check-open-questions`."""
        from little_loops.issue_parser import locate_unresolved_decisions

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A**: do the thing\n"
            "> **Selected:** Option A\n"
            "\n"
            "**Option B**: do the other thing\n"
            "\n"
            "## Edge Cases\n"
            "\n"
            "- What happens on empty input?\n"
        )
        assert locate_unresolved_decisions(content) == []

    def test_locate_unresolved_options_unchanged_by_this_module(self) -> None:
        """Assertion (e) — `locate_unresolved_options`'s `(count, heading)`
        output is untouched by the decision-group model; it still counts
        every losing option block as unresolved (the behavior this issue's
        group model exists to correct only for the flag-clearing gate)."""
        from little_loops.issue_parser import locate_unresolved_options

        content = (
            "## Proposed Solution\n"
            "\n"
            "**Option A**: do the thing\n"
            "> **Selected:** Option A\n"
            "\n"
            "**Option B**: do the other thing\n"
            "\n"
            "**Option C**: do a third thing\n"
        )
        assert locate_unresolved_options(content) == (2, "Proposed Solution")
