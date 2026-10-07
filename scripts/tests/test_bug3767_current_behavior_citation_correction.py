"""Contract tests for BUG-3767: bounded Current Behavior citation-location correction.

A stale source citation inside Current Behavior used to fall to ``NON_VALID`` via the
section-wide premise exclusion, even when the cited assertion was still true. The
verifier now permits one narrow exception through the existing ``CLAIMS_OUTDATED`` /
``correct_claims`` route. These pin the prompt contract; model edit quality is
evaluated separately and loop routing is covered by the existing route tests.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

VERIFY_CMD = PROJECT_ROOT / "commands" / "verify-issues.md"


def _flat() -> str:
    content = VERIFY_CMD.read_text()
    end = content.index("---", 3)
    return " ".join(content[end + 3 :].split())


def _section(start: str, end: str) -> str:
    flat = _flat()
    return flat[flat.index(start) : flat.index(end)]


class TestCitationExceptionScope:
    def test_exception_defined_in_2c(self) -> None:
        scope = _section("#### C. Determine Verdict", "#### E. Validate Dependency References")
        assert "Current Behavior citation-location exception (BUG-3767)" in scope

    def test_edit_surface_is_numeric_span_only(self) -> None:
        scope = _section("**Current Behavior citation-location exception", "#### E. Validate")
        assert "numeric line/range suffix" in scope
        assert "exact-substring replacement" in scope
        assert "byte-identical" in scope
        assert "Never change the path or the asserted symbol" in scope

    def test_requires_unique_literal_and_unchanged_assertion(self) -> None:
        scope = _section("**Current Behavior citation-location exception", "#### E. Validate")
        assert "exactly once" in scope
        assert "present at the replacement range and absent at the old range" in scope
        assert "still holds verbatim" in scope
        assert "stays `NON_VALID`" in scope

    def test_resolve_anchor_is_not_eligibility(self) -> None:
        scope = _section("**Current Behavior citation-location exception", "#### E. Validate")
        assert "resolve_anchor" in scope
        assert "never establish eligibility" in scope

    def test_history_and_raw_decision_candidates_protected(self) -> None:
        scope = _section("**Current Behavior citation-location exception", "#### E. Validate")
        assert "Historical quotations" in scope
        assert "Raw `unapplied_decision` candidates never determine the verdict" in scope

    def test_other_premise_sections_keep_exclusion(self) -> None:
        flat = _flat()
        assert "with the single bounded exception below" in flat
        assert "`## Context` is in neither list above" in flat


class TestCitationExceptionLifecycle:
    def test_evidence_item_shape_documented(self) -> None:
        flat = _flat()
        assert "[context: '<unique local text>']" in flat
        assert "[anchor: '<literal>' in '<symbol>', support:" in flat

    def test_precedence_unchanged_with_directive_drift_note(self) -> None:
        flat = _flat()
        assert (
            "`NON_VALID` > `EVIDENCE_UNVERIFIED` > `CLAIMS_OUTDATED` > `PROPOSAL_UNSOUND` > "
            "`DIRECTIVE_DRIFT` > `VALID`"
        ) in flat
        assert "rediscovers any remaining drift" in flat

    def test_from_evidence_requires_current_verdict_and_revalidation(self) -> None:
        sec4 = _section("### 4. Update Issue Files", "### 4.1")
        assert "`verify_verdict` is `CLAIMS_OUTDATED`" in sec4
        assert "revalidate the original occurrence" in sec4
        assert "confers no edit authority" in sec4
        assert "own fresh `CLAIMS_OUTDATED` classification" in sec4

    def test_b8_remains_read_only(self) -> None:
        flat = _flat()
        assert "it never repairs citations" in flat
        assert "read-only, property-exact evidence consumer" in flat
