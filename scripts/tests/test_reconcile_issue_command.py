"""Structural tests for the /ll:reconcile-issue command + skill bridge (ENH-2689).

Verifies the command doc codifies the reconcile contract: it rewrites three
unconditional directive sections in place, plus one conditional case
(a Scope Boundaries claim contradicted by the issue's own findings, ENH-2937),
preserves human-authored prose, arms the reconcile_attempted one-shot guard,
and emits the [reconcile] CORRECTIONS_MADE ledger + VALIDATED_FILE +
session-log append. Mirrors the string-slice / anchor-heading style of
``test_refine_issue_command.py``.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMMAND_FILE = PROJECT_ROOT / "commands" / "reconcile-issue.md"
SKILL_FILE = PROJECT_ROOT / "skills" / "ll-reconcile-issue" / "SKILL.md"
CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"


class TestReconcileCommandExists:
    def test_command_file_exists(self) -> None:
        assert COMMAND_FILE.exists(), "commands/reconcile-issue.md not found"

    def test_skill_bridge_exists(self) -> None:
        assert SKILL_FILE.exists(), "skills/ll-reconcile-issue/SKILL.md not found"

    def test_disable_model_invocation(self) -> None:
        """Reconcile must be explicitly invoked (by the loop or user), never auto-fired."""
        assert "disable-model-invocation: true" in COMMAND_FILE.read_text()
        assert "disable-model-invocation: true" in SKILL_FILE.read_text()


class TestReconcileContract:
    """The binding contract: rewrite three unconditional directive sections in
    place, plus one conditional case (a contradicted Scope Boundaries claim,
    ENH-2937)."""

    def test_names_the_three_directive_sections(self) -> None:
        content = COMMAND_FILE.read_text()
        for section in ("Implementation Steps", "Acceptance Criteria", "Files to Modify"):
            assert section in content, f"command must name the '{section}' directive section"

    def test_preserves_human_prose(self) -> None:
        content = COMMAND_FILE.read_text().lower()
        assert "proposed solution" in content, "must call out preserving Proposed Solution prose"
        assert "preserve" in content, "must state that other sections are preserved"

    def test_in_place_not_append(self) -> None:
        content = COMMAND_FILE.read_text().lower()
        assert "in place" in content or "in-place" in content
        # The whole point: it must NOT be another appended finding.
        assert "append" in content, "must contrast against the append-only refine behavior"

    def test_sources_from_own_findings(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "Codebase Research Findings" in content, (
            "reconcile must draw from the issue's own accumulated findings"
        )


class TestReconcileGuardAndOutput:
    def test_arms_reconcile_attempted_guard(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "reconcile_attempted" in content, (
            "command must set reconcile_attempted for the autodev one-shot guard"
        )

    def test_reconcile_correction_category(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "[reconcile]" in content, "CORRECTIONS_MADE must define the [reconcile] category"

    def test_validated_file_required(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "## VALIDATED_FILE" in content, "VALIDATED_FILE section is required for automation"

    def test_appends_session_log(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "ll-issues append-log" in content
        assert "/ll:reconcile-issue" in content


class TestReconcileRegistered:
    def test_registered_in_claude_md(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "reconcile-issue" in content, (
            ".claude/CLAUDE.md command catalog must list reconcile-issue"
        )


class TestReconcileScopeBoundariesEligibility:
    """ENH-2937: Scope Boundaries is conditionally rewrite-eligible — ONLY for
    a claim whose stated justification is directly contradicted by a recorded
    finding in the same issue. Slices on the Contract heading through the next
    Process heading, mirroring TestPattern3bDirectiveAlternatives's
    section-scoped helper (test_decide_issue_skill.py)."""

    def _contract_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("## Contract (read this first")
        end = content.index("\n## Process", start)
        return content[start:end]

    def test_scope_boundaries_conditionally_eligible(self) -> None:
        text = self._contract_text()
        assert "Scope Boundaries" in text, (
            "Contract must name Scope Boundaries as conditionally rewrite-eligible"
        )
        assert "conditionally" in text.lower(), (
            "the carve-out must be described as conditional, not unconditional"
        )

    def test_not_a_general_rewrite_addition(self) -> None:
        text = self._contract_text()
        assert "narrow" in text.lower(), (
            "the carve-out must be described as narrow, not a general addition "
            "to the rewrite list"
        )
        assert "Preserve untouched" in text, (
            "unrefuted Scope Boundaries prose must still be listed under Preserve untouched"
        )

    def test_tracing_requirement_carve_out_for_decision_directive(self) -> None:
        text = self._contract_text()
        assert "does not need a tracing finding" in text or "carved out" in text, (
            "the 'every rewritten claim must trace to an existing finding' rule "
            "must explicitly exempt the decision-directive branch (2b)"
        )

    def test_contradiction_check_step_documented(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "4a. Detect contradicted Scope Boundaries claims" in content, (
            "command must add a step 4a contradiction-detection pass for "
            "Scope Boundaries claims"
        )

    def test_factual_mismatch_and_open_scope_call_branches(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "factual mismatch" in content
        assert "open scope call" in content

    def test_decision_directive_sets_decision_needed(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "decision_needed: true" in content, (
            "the open-scope-call branch must set decision_needed: true so "
            "/ll:decide-issue picks up the rewritten directive (model after "
            "test_decide_issue_skill.py's string-presence assertion style)"
        )

    def test_sections_rewritten_includes_scope_boundaries(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "Scope Boundaries: [rewritten" in content, (
            "Output Format's SECTIONS_REWRITTEN checklist must include a "
            "Scope Boundaries line"
        )


class TestReconcileCheckModeCoverage:
    """--check mode (step 7) must report a contradicted Scope Boundaries claim
    as a stale section, not just the three unconditional sections."""

    def _check_mode_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("### 7. Check Mode Behavior")
        end = content.index("\n## Output Format", start)
        return content[start:end]

    def test_check_mode_documented(self) -> None:
        text = self._check_mode_text()
        assert "CHECK_MODE" in text
        assert "NEEDED" in text
        assert "CLEAN" in text

    def test_check_mode_includes_scope_boundaries_contradiction(self) -> None:
        text = self._check_mode_text()
        assert "Scope Boundaries" in text and "contradicted" in text, (
            "--check mode must extend its staleness verdict to a contradicted "
            "Scope Boundaries claim, not just the three unconditional sections"
        )
