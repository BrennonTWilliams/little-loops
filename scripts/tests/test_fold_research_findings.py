"""Unit tests for the findings-fold primitive (ENH-2993).

Modeled on ``test_session_log.py::TestAppendSessionLogEntry`` — the closest
existing "find the existing header, insert beneath it, assert the header count
stays 1" shape in the repo.

Note what is deliberately *not* asserted: bullet-set idempotency. ENH-2993's
§ Scope Boundaries forbids dedup, so folding the same bullets twice yields them
twice, by design. The invariants under test are the **heading count** (exactly
one per H2 after any call) and **provenance-line conservation** (M lines in,
M+1 out).
"""

from __future__ import annotations

import pytest

from little_loops.issue_parser import count_enumerable_options
from little_loops.issues.fold_research_findings import (
    DEFAULT_MARKER,
    SUB_HEADING,
    dated_marker,
    ensure_section,
    find_subsections,
    fold_research_findings,
)

MARKER_PREFIX = "_Added by `/ll:refine-issue`"


def _count_headings(content: str, heading: str = SUB_HEADING) -> int:
    return content.count(f"### {heading}")


def _count_provenance(content: str) -> int:
    return content.count(MARKER_PREFIX)


def _count_bullets(content: str) -> int:
    return sum(1 for line in content.splitlines() if line.startswith("- "))


ONE_BLOCK = """# ENH-1: Sample

## Proposed Solution

Do the thing.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-01-01 — based on codebase analysis:_

- first finding

## Impact

- **Priority**: P3
"""

THREE_BLOCKS = """# ENH-1: Sample

## Integration Map

### Files to Modify
- `a.py` — change it

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-01-01 — based on codebase analysis:_

- finding one

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-01-02 — based on codebase analysis:_

- finding two

### Documentation
- `docs/x.md`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-01-03 — based on codebase analysis:_

- finding three

## Impact

- **Priority**: P3
"""

NO_BLOCK = """# ENH-1: Sample

## Integration Map

### Files to Modify
- `a.py` — change it

### Configuration
- N/A

## Impact

- **Priority**: P3
"""


class TestFindSubsections:
    """`find_subsections()` returns *every* match, scoped to one H2."""

    def test_absent_parent_returns_empty(self) -> None:
        assert find_subsections(ONE_BLOCK, "Nonexistent Section", SUB_HEADING) == []

    def test_absent_subheading_returns_empty(self) -> None:
        assert find_subsections(NO_BLOCK, "Integration Map", SUB_HEADING) == []

    def test_single_match(self) -> None:
        spans = find_subsections(ONE_BLOCK, "Proposed Solution", SUB_HEADING)
        assert len(spans) == 1
        body, start, end = spans[0]
        assert "first finding" in body
        # start points at the `###` heading line, end is exclusive.
        assert ONE_BLOCK[start:].startswith(f"### {SUB_HEADING}")
        assert ONE_BLOCK[end:].startswith("## Impact")

    def test_returns_all_matches_in_document_order(self) -> None:
        spans = find_subsections(THREE_BLOCKS, "Integration Map", SUB_HEADING)
        assert len(spans) == 3
        assert [s[1] for s in spans] == sorted(s[1] for s in spans)
        assert "finding one" in spans[0][0]
        assert "finding two" in spans[1][0]
        assert "finding three" in spans[2][0]

    def test_end_boundary_stops_at_sibling_h3(self) -> None:
        """A findings block followed by a sibling H3 must not swallow it."""
        spans = find_subsections(THREE_BLOCKS, "Integration Map", SUB_HEADING)
        assert "### Documentation" not in spans[1][0]
        assert THREE_BLOCKS[spans[1][2] :].startswith("### Documentation")

    def test_scoped_to_named_h2_only(self) -> None:
        content = ONE_BLOCK.replace(
            "## Impact", "## Other\n\n### Codebase Research Findings\n\n- x\n\n## Impact"
        )
        assert len(find_subsections(content, "Proposed Solution", SUB_HEADING)) == 1
        assert len(find_subsections(content, "Other", SUB_HEADING)) == 1

    def test_heading_match_is_case_insensitive_and_stripped(self) -> None:
        assert len(find_subsections(ONE_BLOCK, "proposed solution ", SUB_HEADING)) == 1


class TestFoldCreate:
    """0 existing spans — create the block at the end of the H2 slice."""

    def test_creates_block_when_absent(self) -> None:
        out = fold_research_findings(NO_BLOCK, "Integration Map", "- brand new")
        assert _count_headings(out) == 1
        assert "- brand new" in out
        assert DEFAULT_MARKER in out

    def test_created_block_sits_at_end_of_h2_slice(self) -> None:
        out = fold_research_findings(NO_BLOCK, "Integration Map", "- brand new")
        # After the last nested H3 of the section, before the next H2.
        assert out.index("### Configuration") < out.index(f"### {SUB_HEADING}")
        assert out.index(f"### {SUB_HEADING}") < out.index("## Impact")

    def test_absent_parent_returns_content_unchanged(self) -> None:
        assert fold_research_findings(NO_BLOCK, "Nope", "- x") == NO_BLOCK


class TestFoldAppend:
    """1 existing span — append beneath it, no sibling heading created."""

    def test_appends_under_existing_heading(self) -> None:
        out = fold_research_findings(ONE_BLOCK, "Proposed Solution", "- second finding")
        assert _count_headings(out) == 1
        assert "- first finding" in out
        assert "- second finding" in out
        assert out.index("- first finding") < out.index("- second finding")

    def test_provenance_line_added_per_batch(self) -> None:
        out = fold_research_findings(ONE_BLOCK, "Proposed Solution", "- second finding")
        assert _count_provenance(out) == _count_provenance(ONE_BLOCK) + 1

    def test_heading_count_invariant_across_n_calls(self) -> None:
        out = ONE_BLOCK
        for _ in range(4):
            out = fold_research_findings(out, "Proposed Solution", "- repeated finding")
        assert _count_headings(out) == 1
        # Dedup is explicitly out of scope — repeated bullets are the contract.
        assert out.count("- repeated finding") == 4
        assert _count_provenance(out) == _count_provenance(ONE_BLOCK) + 4

    def test_following_h2_is_not_swallowed(self) -> None:
        out = fold_research_findings(ONE_BLOCK, "Proposed Solution", "- second finding")
        assert "## Impact" in out
        assert "- **Priority**: P3" in out


class TestFoldOnTouchCollapse:
    """N>1 spans — collapse into the first span's position (ENH-2993 § Decisions)."""

    def test_collapses_to_one_heading(self) -> None:
        out = fold_research_findings(THREE_BLOCKS, "Integration Map", "- brand new")
        assert _count_headings(out) == 1

    def test_conserves_every_bullet_in_document_order(self) -> None:
        out = fold_research_findings(THREE_BLOCKS, "Integration Map", "- brand new")
        for text in ("finding one", "finding two", "finding three", "brand new"):
            assert text in out
        order = [out.index(t) for t in ("finding one", "finding two", "finding three", "brand new")]
        assert order == sorted(order)
        assert _count_bullets(out) == _count_bullets(THREE_BLOCKS) + 1

    def test_conserves_provenance_lines(self) -> None:
        out = fold_research_findings(THREE_BLOCKS, "Integration Map", "- brand new")
        assert _count_provenance(out) == 4

    def test_lands_at_first_blocks_position(self) -> None:
        out = fold_research_findings(THREE_BLOCKS, "Integration Map", "- brand new")
        assert out.index("### Files to Modify") < out.index(f"### {SUB_HEADING}")
        assert out.index(f"### {SUB_HEADING}") < out.index("### Documentation")

    def test_preserves_unrelated_sibling_h3s(self) -> None:
        out = fold_research_findings(THREE_BLOCKS, "Integration Map", "- brand new")
        assert out.count("### Files to Modify") == 1
        assert out.count("### Documentation") == 1
        assert "- `docs/x.md`" in out
        assert "- `a.py` — change it" in out


class TestVerbatimPayload:
    """stdin/`new_content` is an opaque markdown block, never a parsed bullet list."""

    def test_shell_metacharacters_and_wrapping_survive(self) -> None:
        payload = (
            "- `re.finditer($1)` costs $5 — really! see `x.py:12`\n"
            "  continuation line two with `backticks`\n"
            "  continuation line three\n"
            "- second bullet"
        )
        out = fold_research_findings(ONE_BLOCK, "Proposed Solution", payload)
        assert payload in out

    def test_option_block_at_column_zero_survives(self) -> None:
        """The § 5a payload has no `- ` bullets at all; it must land byte-identical."""
        payload = (
            "**Option A**: keep the existing regex\n\n"
            "**Option B**: switch to a parser\n\n"
            "**Recommended**: Option A — cheaper"
        )
        out = fold_research_findings(NO_BLOCK, "Integration Map", payload)
        assert payload in out

    def test_option_block_remains_countable(self) -> None:
        payload = (
            "**Option A**: keep the existing regex\n\n"
            "**Option B**: switch to a parser\n\n"
            "**Recommended**: Option A — cheaper"
        )
        content = NO_BLOCK.replace("## Impact", "## Proposed Solution\n\nTBD\n\n## Impact")
        out = fold_research_findings(content, "Proposed Solution", payload)
        assert count_enumerable_options(out) == 2

    def test_no_suffix_decoration_on_generated_heading(self) -> None:
        out = fold_research_findings(NO_BLOCK, "Integration Map", "- x")
        assert f"### {SUB_HEADING}\n" in out
        assert f"### {SUB_HEADING} —" not in out


class TestParameterization:
    """`sub_heading`/`marker` are parameterized so wire-issue becomes a caller."""

    def test_alternate_sub_heading_and_marker(self) -> None:
        out = fold_research_findings(
            NO_BLOCK,
            "Integration Map",
            "- wired",
            sub_heading="Wiring Phase",
            marker="_Wiring pass added by `/ll:wire-issue`:_",
        )
        assert "### Wiring Phase" in out
        assert "_Wiring pass added by `/ll:wire-issue`:_" in out
        assert SUB_HEADING not in out


class TestEmptyPayloadIsLazy:
    """A whitespace-only batch contributes nothing — no marker, no stub (BUG-3245).

    Required by the step-1 gate regardless of routing decisions: the library
    itself must be unable to represent a content-free stub.
    """

    def test_no_block_and_empty_payload_is_a_true_no_op(self) -> None:
        out = fold_research_findings(NO_BLOCK, "Integration Map", "   \n\n  ")
        assert out == NO_BLOCK
        assert _count_headings(out) == 0

    def test_one_block_and_empty_payload_adds_no_marker(self) -> None:
        out = fold_research_findings(ONE_BLOCK, "Proposed Solution", "")
        assert out == ONE_BLOCK
        assert _count_provenance(out) == _count_provenance(ONE_BLOCK)

    def test_n_successive_empty_calls_add_zero_markers(self) -> None:
        out = ONE_BLOCK
        for _ in range(5):
            out = fold_research_findings(out, "Proposed Solution", "\n  \n")
        assert out == ONE_BLOCK

    def test_mixed_sequence_yields_no_adjacent_empty_pair(self) -> None:
        out = fold_research_findings(ONE_BLOCK, "Proposed Solution", "- second finding")
        out = fold_research_findings(out, "Proposed Solution", "   ")
        out = fold_research_findings(out, "Proposed Solution", "- third finding")
        assert _count_provenance(out) == 3
        assert MARKER_PREFIX + "\n\n\n\n" + MARKER_PREFIX not in out
        assert "- second finding" in out
        assert "- third finding" in out

    def test_duplicate_headings_still_collapse_with_empty_payload(self) -> None:
        """N>1 spans: dedup existing headings even when this pass has no new findings."""
        out = fold_research_findings(THREE_BLOCKS, "Integration Map", "")
        assert _count_headings(out) == 1
        for text in ("finding one", "finding two", "finding three"):
            assert text in out
        assert _count_provenance(out) == 3

    def test_dated_marker_shape(self) -> None:
        assert dated_marker("2026-08-02") == (
            "_Added by `/ll:refine-issue` — 2026-08-02 — based on codebase analysis:_"
        )


class TestEnsureSection:
    """Missing parent H2 is created in v2.0 template order, not an error."""

    ORDER = [
        "Summary",
        "Current Behavior",
        "Expected Behavior",
        "Proposed Solution",
        "Integration Map",
        "Program Design",
        "Implementation Steps",
        "Impact",
        "Session Log",
        "Status",
    ]

    def test_existing_section_untouched(self) -> None:
        assert ensure_section(NO_BLOCK, "Integration Map", self.ORDER) == NO_BLOCK

    def test_inserts_in_template_order(self) -> None:
        out = ensure_section(NO_BLOCK, "Program Design", self.ORDER)
        assert "## Program Design" in out
        assert out.index("## Integration Map") < out.index("## Program Design")
        assert out.index("## Program Design") < out.index("## Impact")

    def test_appends_when_no_later_anchor_exists(self) -> None:
        out = ensure_section(NO_BLOCK, "Status", self.ORDER)
        assert "## Status" in out
        assert out.index("## Impact") < out.index("## Status")

    def test_inserts_before_horizontal_rule_footer(self) -> None:
        content = "# T\n\n## Summary\n\nx\n\n---\n\n## Status\n\n- **Status**: open\n"
        out = ensure_section(content, "Impact", self.ORDER)
        assert out.index("## Impact") < out.index("---")

    def test_fold_into_created_section(self) -> None:
        out = ensure_section(NO_BLOCK, "Program Design", self.ORDER)
        out = fold_research_findings(out, "Program Design", "- designed")
        assert _count_headings(out) == 1
        assert out.index("## Program Design") < out.index(f"### {SUB_HEADING}")
        assert out.index(f"### {SUB_HEADING}") < out.index("## Impact")


@pytest.mark.parametrize("body", [ONE_BLOCK, THREE_BLOCKS, NO_BLOCK])
def test_frontmatter_and_trailing_content_never_lost(body: str) -> None:
    out = fold_research_findings(body, "Integration Map", "- x")
    out = fold_research_findings(out, "Proposed Solution", "- y")
    assert out.startswith("# ENH-1: Sample")
    assert out.rstrip().endswith("- **Priority**: P3")


class TestDownstreamReaders:
    """Folding must not change what the consumers of these blocks see."""

    def test_reconcile_style_bullet_read_is_unchanged(self) -> None:
        """`commands/reconcile-issue.md` reads "every bullet" with no block count.

        After a collapse it reads one block with more bullets instead of N
        blocks with fewer — the same bullet set, in the same order.
        """
        from little_loops.issue_parser import _heading_bodies

        before = [
            line
            for body in _heading_bodies(THREE_BLOCKS, SUB_HEADING)
            for line in body.splitlines()
            if line.startswith("- ")
        ]
        out = fold_research_findings(THREE_BLOCKS, "Integration Map", "- brand new")
        after = [
            line
            for body in _heading_bodies(out, SUB_HEADING)
            for line in body.splitlines()
            if line.startswith("- ")
        ]
        assert after == [*before, "- brand new"]

    def test_pass_boundaries_survive_for_the_enh_2995_carve_out(self) -> None:
        """ENH-2995's "this pass's findings only" rule keys on batch boundaries.

        Once the headings collapse, the per-batch provenance line is the only
        remaining discriminator — so the newest batch must still be isolable as
        the text following the last provenance line.
        """
        out = fold_research_findings(ONE_BLOCK, "Proposed Solution", "- older batch")
        out = fold_research_findings(out, "Proposed Solution", "- newest batch")

        assert _count_headings(out) == 1
        assert _count_provenance(out) == 3
        current = out[out.rindex(MARKER_PREFIX) :]
        assert "- newest batch" in current
        assert "- older batch" not in current
        assert "- first finding" not in current
