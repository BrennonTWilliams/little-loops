"""Refuted-option marker parsing and eligibility (BUG-3592)."""

from __future__ import annotations

from little_loops.issue_parser import (
    count_open_questions_in_sections,
    locate_enumerable_options,
    locate_unresolved_decisions,
    refuted_option_labels,
)

MARKER = (
    "1. **Refuted option**: Option A — /ll:spike 2026-09-24: `assert x`. "
    "Which remaining option replaces it?"
)


def _issue(options: str, marker: str = MARKER) -> str:
    return (
        "# T\n\n## Proposed Solution\n\n"
        f"{options}\n\n## Open Questions\n\n{marker}\n\n## Status\n\nOpen\n"
    )


TWO = "### Option A: refuted\n1. step one\n2. step two\n\n### Option B: alt\nbody\n"
ONE = "### Option A: refuted\n1. step one\n2. step two\n"


def test_labels_match_resolved_and_unresolved() -> None:
    assert refuted_option_labels(_issue(TWO)) == {"option a"}
    resolved = MARKER + " ✅ RESOLVED (2026-09-24 by /ll:decide-issue: Option B)"
    assert refuted_option_labels(_issue(TWO, resolved)) == {"option a"}


def test_no_marker_no_labels() -> None:
    assert refuted_option_labels("## Open Questions\n\n- Which one?\n") == set()


def test_eligible_false_for_named_label() -> None:
    located = locate_enumerable_options(_issue(TWO))
    assert located.pattern == "section_header"
    assert located.count == 2
    assert located.eligible_count == 1
    assert [o.eligible for o in located.options] == [False, True]
    assert located.to_dict()["eligible_count"] == 1


def test_numbered_steps_do_not_become_options_with_headers() -> None:
    located = locate_enumerable_options(_issue(ONE))
    assert located.pattern == "section_header"
    assert located.count == 1
    assert located.eligible_count == 0


def test_all_refuted_group_stays_unresolved() -> None:
    groups = locate_unresolved_decisions(_issue(ONE), include_approximate_tiers=True)
    assert len(groups) == 1
    assert groups[0].all_refuted is True
    assert groups[0].to_dict()["all_refuted"] is True


def test_group_with_alternative_is_not_all_refuted() -> None:
    groups = locate_unresolved_decisions(_issue(TWO), include_approximate_tiers=True)
    assert len(groups) == 1
    assert groups[0].all_refuted is False
    assert [o.eligible for o in groups[0].options] == [False, True]


def test_unresolved_marker_counts_as_open_question_resolved_does_not() -> None:
    assert count_open_questions_in_sections(_issue(TWO)) == 1
    resolved = MARKER + " ✅ RESOLVED (2026-09-24 by /ll:decide-issue: Option B)"
    assert count_open_questions_in_sections(_issue(TWO, resolved)) == 0


# --- BUG-3574: a refuted selection no longer counts as a resolved decision ---

DECIDED = (
    "### Option A: refuted\n> **Selected:** Option A: refuted — simplest\n1. step\n\n"
    "### Option B: alt\nbody\n\n### Decision Rationale\n\nA won.\n"
)


def test_decided_group_without_marker_is_resolved() -> None:
    content = _issue(DECIDED, "- Unrelated question?")
    assert locate_unresolved_decisions(content, include_approximate_tiers=True) == []


def test_callout_on_refuted_option_reopens_group() -> None:
    groups = locate_unresolved_decisions(_issue(DECIDED), include_approximate_tiers=True)
    assert len(groups) == 1


def test_callout_on_eligible_option_alongside_refuted_is_resolved() -> None:
    decided_b = DECIDED.replace("> **Selected:** Option A: refuted — simplest\n", "").replace(
        "body\n", "> **Selected:** Option B: alt\nbody\n", 1
    )
    assert locate_unresolved_decisions(_issue(decided_b), include_approximate_tiers=True) == []


def test_rationale_with_refuted_member_and_no_eligible_callout_is_unresolved() -> None:
    no_callouts = DECIDED.replace("> **Selected:** Option A: refuted — simplest\n", "")
    groups = locate_unresolved_decisions(_issue(no_callouts), include_approximate_tiers=True)
    assert len(groups) == 1
