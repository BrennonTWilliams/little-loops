"""Wiring tests for ENH-3250: proposal-vs-code consequence check in /ll:verify-issues.

Every LLM state in refine-to-ready-issue.yaml evaluated *descriptive* content —
what the issue says about the code. None evaluated *prescriptive* content —
what happens if the Proposed Solution is implemented as written. This asserts
the new §B6 sub-check's presence, its precondition (skip on absent/boilerplate
Proposed Solution), its three named defect classes, the new PROPOSAL_UNSOUND
verdict, and the §2.5 persistence carve-out that keeps it distinct from the
blanket NON_VALID collapse.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

VERIFY_CMD = PROJECT_ROOT / "commands" / "verify-issues.md"


def _body(path: Path) -> str:
    content = path.read_text()
    end = content.index("---", 3)
    return content[end + 3 :]


class TestProposalVsCodeConsequenceCheck:
    """§B must gain a proposal-vs-code consequence sub-check (B1)."""

    def test_rule_present(self) -> None:
        flat = " ".join(_body(VERIFY_CMD).split())
        assert "Proposal-vs-code consequence check" in flat, (
            "commands/verify-issues.md must define a proposal-vs-code "
            "consequence check in §B (ENH-3250)"
        )

    def test_rule_sits_inside_section_b(self) -> None:
        body = _body(VERIFY_CMD)
        section_b_start = body.index("#### B. Verify Against Codebase")
        section_c_start = body.index("#### C. Determine Verdict")
        rule_start = body.index("Proposal-vs-code consequence check")
        assert section_b_start < rule_start < section_c_start, (
            "the proposal-vs-code consequence check must sit inside §B, before §C's verdict table"
        )

    def test_rule_has_skip_precondition(self) -> None:
        flat = " ".join(_body(VERIFY_CMD).split())
        assert "skip entirely if" in flat and "template boilerplate" in flat, (
            "the check must be preconditioned on a present, non-boilerplate "
            "Proposed Solution — otherwise every batch /ll:verify-issues run "
            "pays the added cost on issues with nothing prescriptive to check"
        )

    def test_rule_names_three_defect_classes(self) -> None:
        flat = " ".join(_body(VERIFY_CMD).split())
        for phrase in (
            "Exception-handler compatibility",
            "Test-fixture invalidation",
            "AC coverage of identified integration points",
        ):
            assert phrase in flat, (
                f"the proposal-vs-code check must name the defect class {phrase!r} "
                "(the three classes BUG-3243's manual review found)"
            )

    def test_rule_states_claim_verdict_wins_on_conflict(self) -> None:
        flat = " ".join(_body(VERIFY_CMD).split())
        assert "claim-verdict wins" in flat, (
            "when both a claim defect and a proposal defect exist, the "
            "existing claim verdict must win so refine_followup repairs the "
            "research the proposal check itself depends on"
        )


class TestProposalUnsoundVerdict:
    """§C's verdict table and §2.5's persistence must carry PROPOSAL_UNSOUND (B2)."""

    def test_verdict_table_has_proposal_unsound(self) -> None:
        flat = " ".join(_body(VERIFY_CMD).split())
        assert "PROPOSAL_UNSOUND" in flat, (
            "§C's verdict table must define PROPOSAL_UNSOUND (ENH-3250)"
        )

    def test_persistence_carves_out_proposal_unsound(self) -> None:
        body = _body(VERIFY_CMD)
        persist_start = body.index("Persist the verdict to frontmatter")
        approval_start = body.index("### 3. Request User Approval")
        persist_section = " ".join(body[persist_start:approval_start].split())
        assert "verify_verdict: PROPOSAL_UNSOUND" in persist_section, (
            "the §2.5 persistence step must write verify_verdict: "
            "PROPOSAL_UNSOUND as its own value, not collapse it into "
            "verify_verdict: NON_VALID — the split is what lets "
            "check_proposal_unsound route it to reconcile_issue"
        )
        assert (
            "not** collapsed into" in persist_section or "not collapsed into" in persist_section
        ), (
            "the persistence step must explicitly say PROPOSAL_UNSOUND is not "
            "collapsed into NON_VALID"
        )

    def test_persistence_still_exits_1_in_check_mode(self) -> None:
        body = _body(VERIFY_CMD)
        persist_start = body.index("Persist the verdict to frontmatter")
        approval_start = body.index("### 3. Request User Approval")
        persist_section = body[persist_start:approval_start]
        assert "exit 1" in persist_section, (
            "PROPOSAL_UNSOUND must still be documented as a nonzero/exit 1 "
            "outcome in --check mode — the split is in the persisted verdict, "
            "not the exit-code contract"
        )
