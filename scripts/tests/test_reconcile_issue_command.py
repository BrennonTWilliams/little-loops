"""Structural tests for the /ll:reconcile-issue command + skill bridge (ENH-2689).

Verifies the command doc codifies the reconcile contract: it rewrites ONLY the
three directive sections in place, preserves human-authored prose, arms the
reconcile_attempted one-shot guard, and emits the [reconcile] CORRECTIONS_MADE
ledger + VALIDATED_FILE + session-log append. Mirrors the string-slice /
anchor-heading style of ``test_refine_issue_command.py``.
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
    """The binding contract: rewrite exactly three directive sections in place."""

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
