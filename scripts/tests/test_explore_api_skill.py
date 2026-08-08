"""Structural tests for the explore-api skill's AUTO_MODE fix (BUG-3100).

Verifies that skills/explore-api/SKILL.md documents automation detection
(AUTO_MODE / LL_NON_INTERACTIVE / DANGEROUSLY_SKIP_PERMISSIONS / --auto) and
that the "record exists" branch does not ask an AskUserQuestion-style
question when AUTO_MODE is true. Mirrors the structural-assertion pattern
used by test_decide_issue_skill.py for the identical BUG-1416 fix shape.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "explore-api" / "SKILL.md"


class TestExploreApiSkillExists:
    def test_skill_file_exists(self) -> None:
        assert SKILL_FILE.exists(), "skills/explore-api/SKILL.md not found"


class TestAutoModeDetection:
    """SKILL.md must document the AUTO_MODE convention shared by other skills."""

    def _arguments_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("## Arguments")
        end = content.index("## Compute Slug")
        return content[start:end]

    def test_auto_mode_variable_documented(self) -> None:
        text = self._arguments_text()
        assert "AUTO_MODE" in text, "Arguments section must define AUTO_MODE"

    def test_ll_non_interactive_documented(self) -> None:
        text = self._arguments_text()
        assert "LL_NON_INTERACTIVE" in text, (
            "Arguments section must check LL_NON_INTERACTIVE, matching the "
            "convention used by 10+ other skills"
        )

    def test_dangerously_skip_permissions_documented(self) -> None:
        text = self._arguments_text()
        assert "DANGEROUSLY_SKIP_PERMISSIONS" in text

    def test_auto_flag_documented(self) -> None:
        text = self._arguments_text()
        assert "--auto" in text


class TestRecordExistsBranchNeverAsks:
    """The 'record exists' (exit 0) branch must not block on a question under AUTO_MODE."""

    def _phase1_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("## Phase 1: Ingest")
        end = content.index("## Phase 2: Hypothesize")
        return content[start:end]

    def test_auto_mode_branch_present(self) -> None:
        text = self._phase1_text()
        assert "AUTO_MODE` is true" in text, (
            "Phase 1 must branch on AUTO_MODE for the exit-0 (record exists) case"
        )

    def test_auto_mode_branch_does_not_ask(self) -> None:
        text = self._phase1_text()
        auto_start = text.index("AUTO_MODE` is true")
        human_start = text.index("AUTO_MODE` is false")
        auto_branch = text[auto_start:human_start]
        assert "ask whether" not in auto_branch, (
            "AUTO_MODE branch must not block on the reuse-vs-fresh question"
        )
        assert "do NOT ask a question" in auto_branch

    def test_human_branch_retains_question(self) -> None:
        text = self._phase1_text()
        human_start = text.index("AUTO_MODE` is false")
        human_branch = text[human_start:]
        assert "ask whether" in human_branch, (
            "Interactive (non-AUTO_MODE) branch must retain the reuse-vs-fresh question"
        )
