"""Tests for little_loops.issues.prose_deps.extract_prose_deps (FEAT-2849)."""

from __future__ import annotations

import pytest

from little_loops.issues.prose_deps import extract_prose_deps


def test_depends_on_phrase() -> None:
    assert extract_prose_deps("Depends on FEAT-1 for the shared helper.") == {"FEAT-1"}


def test_blocked_by_phrase() -> None:
    assert extract_prose_deps("Blocked by BUG-42 until the fix lands.") == {"BUG-42"}


def test_requires_phrase() -> None:
    assert extract_prose_deps("Requires ENH-10 to be merged first.") == {"ENH-10"}


@pytest.mark.parametrize(
    "phrase",
    [
        "Blocked on",
        "Gated on",
        "Waiting on",
        "Contingent on",
        "Predicated on",
        "Depends upon",
    ],
)
def test_unambiguous_blocker_synonyms(phrase: str) -> None:
    assert extract_prose_deps(f"{phrase} BUG-3028 landing first.") == {"BUG-3028"}


@pytest.mark.parametrize(
    "body",
    [
        "Landed after BUG-3028 shipped.",
        "Cleanup once FEAT-500 is merged.",
        "Still pending ENH-10.",
        "This needs BUG-42 for context.",
    ],
)
def test_temporal_phrasings_not_treated_as_dependencies(body: str) -> None:
    # "after"/"once"/"pending"/"needs" are dominated by narrative history in
    # real issue bodies; matching them would inject wrong blocked_by edges.
    assert extract_prose_deps(body) == set()


def test_priority_prefixed_id_normalized() -> None:
    assert extract_prose_deps("Depends on P2-FEAT-109 for context.") == {"FEAT-109"}


def test_case_insensitive_phrase() -> None:
    assert extract_prose_deps("depends on feat-5 for setup.") == {"FEAT-5"}


def test_blocked_by_section_body() -> None:
    body = "\n".join(
        [
            "## Blocked By",
            "- FEAT-200",
            "- BUG-201",
            "",
            "## Impact",
            "Some other content.",
        ]
    )
    assert extract_prose_deps(body) == {"FEAT-200", "BUG-201"}


def test_blocked_by_section_stops_at_next_heading() -> None:
    body = "\n".join(
        [
            "## Blocked By",
            "- FEAT-300",
            "",
            "## Related",
            "See also ENH-301 for background.",
        ]
    )
    assert extract_prose_deps(body) == {"FEAT-300"}


def test_ignores_ids_in_fenced_code() -> None:
    body = "\n".join(
        [
            "Some text.",
            "```",
            "Depends on FEAT-999",
            "```",
            "No real dependency here.",
        ]
    )
    assert extract_prose_deps(body) == set()


def test_blocked_by_section_ignores_fenced_ids() -> None:
    body = "\n".join(
        [
            "## Blocked By",
            "```",
            "FEAT-999",
            "```",
            "",
            "## Impact",
        ]
    )
    assert extract_prose_deps(body) == set()


def test_ignores_ids_in_inline_code() -> None:
    body = "\n".join(
        [
            "Some text.",
            "An example: `Depends on FEAT-999`.",
            "No real dependency here.",
        ]
    )
    assert extract_prose_deps(body) == set()


def test_blocked_by_section_ignores_inline_code_ids() -> None:
    body = "\n".join(
        [
            "## Blocked By",
            "Example: `FEAT-999`",
            "",
            "## Impact",
        ]
    )
    assert extract_prose_deps(body) == set()


def test_no_phrase_no_match() -> None:
    assert extract_prose_deps("See FEAT-5 for related discussion.") == set()


def test_ids_inside_link_targets_ignored_without_trigger_phrase() -> None:
    body = "See [related work](.issues/features/P2-FEAT-500-foo.md) for background."
    assert extract_prose_deps(body) == set()


def test_self_reference_extracted_like_any_other_id() -> None:
    # Caller (check_format_gaps) is responsible for excluding the issue's own
    # ID from the result; the extractor itself has no notion of "self".
    assert extract_prose_deps("Depends on FEAT-7 (this very issue).") == {"FEAT-7"}


def test_empty_body() -> None:
    assert extract_prose_deps("") == set()


def test_multiple_phrases_combined() -> None:
    body = "Depends on FEAT-1. Blocked by BUG-2. Requires ENH-3."
    assert extract_prose_deps(body) == {"FEAT-1", "BUG-2", "ENH-3"}


class TestSubjectAttribution:
    """BUG-3057: a phrase describes the subject of its own sentence/list item.

    Without ``host_id`` the extractor is unchanged, so every pre-existing
    caller and test above keeps its old semantics.
    """

    def test_epic_children_list_attributes_to_the_child(self) -> None:
        """The exact shape that turned the repo-wide drift gate red."""
        body = (
            "## Children\n\n"
            "- **FEAT-3042** - Advisor transport: shared helper\n"
            "- **FEAT-3044** - Advisor core: `ll-advise` CLI, capability floor, and\n"
            "  `ll-doctor` check (depends on FEAT-3042, FEAT-3043)\n"
        )
        assert extract_prose_deps(body, host_id="EPIC-3041") == set()

    def test_narration_about_another_issue_is_attributed_to_it(self) -> None:
        body = "Repointed both edges (FEAT-3044 already correctly depends on FEAT-3042)."
        assert extract_prose_deps(body, host_id="EPIC-3041") == set()

    def test_host_own_dependency_still_extracted(self) -> None:
        assert extract_prose_deps("Depends on FEAT-1 for the helper.", host_id="ENH-9") == {
            "FEAT-1"
        }

    def test_prior_sentence_subject_does_not_suppress(self) -> None:
        """Scope is the sentence, not the paragraph -- BUG-5 is not the subject."""
        body = "This work builds on BUG-5. Depends on FEAT-109 for the shared helper."
        assert extract_prose_deps(body, host_id="ENH-9") == {"FEAT-109"}

    def test_host_named_as_its_own_subject_still_extracted(self) -> None:
        body = "- **ENH-9** - the thing (depends on FEAT-1)\n"
        assert extract_prose_deps(body, host_id="ENH-9") == {"FEAT-1"}

    def test_host_id_matching_is_case_insensitive(self) -> None:
        body = "- **ENH-9** - the thing (depends on FEAT-1)\n"
        assert extract_prose_deps(body, host_id="enh-9") == {"FEAT-1"}

    def test_new_list_item_resets_scope(self) -> None:
        """A bullet starts a new subject even with no sentence terminator."""
        body = "- **FEAT-2** - some prior item\n- Depends on FEAT-1 for the helper\n"
        assert extract_prose_deps(body, host_id="ENH-9") == {"FEAT-1"}

    def test_omitting_host_id_preserves_legacy_behavior(self) -> None:
        body = "- **FEAT-3044** - core (depends on FEAT-3042)\n"
        assert extract_prose_deps(body) == {"FEAT-3042"}
