"""Tests for the /ll:improve-claude-md skill (FEAT-949).

Structural/content tests verifying the skill file and algorithm sidecar
exist with required content, following the test_update_skill.py pattern.
"""

from __future__ import annotations

from pathlib import Path

# Root of the project relative to this test file
PROJECT_ROOT = Path(__file__).parent.parent.parent

SKILL_FILE = PROJECT_ROOT / "skills" / "improve-claude-md" / "SKILL.md"
ALGORITHM_FILE = PROJECT_ROOT / "skills" / "improve-claude-md" / "algorithm.md"
PLUGIN_JSON = PROJECT_ROOT / ".claude-plugin" / "plugin.json"


class TestImproveClaudeMdSkillExists:
    """Verify the skill file is created with required structure."""

    def test_skill_file_exists(self) -> None:
        """skills/improve-claude-md/SKILL.md must exist after implementation."""
        assert SKILL_FILE.exists(), (
            f"Skill file not found: {SKILL_FILE}\n"
            "Create skills/improve-claude-md/SKILL.md to implement FEAT-949."
        )

    def test_algorithm_file_exists(self) -> None:
        """skills/improve-claude-md/algorithm.md sidecar must exist."""
        assert ALGORITHM_FILE.exists(), (
            f"Algorithm sidecar not found: {ALGORITHM_FILE}\n"
            "Create skills/improve-claude-md/algorithm.md with condition examples and step detail."
        )

    def test_skill_has_dry_run_flag(self) -> None:
        """Skill must document --dry-run flag."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "--dry-run" in content, "Skill must include --dry-run flag"

    def test_skill_has_file_flag(self) -> None:
        """Skill must document --file flag."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "--file" in content, "Skill must include --file flag"

    def test_skill_references_important_if(self) -> None:
        """Skill must use <important if> XML blocks as the core mechanism."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "<important if" in content, (
            "Skill must reference <important if> blocks — the core rewrite mechanism"
        )

    def test_skill_has_9_steps(self) -> None:
        """Skill must implement the 9-step rewrite algorithm."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        # All 9 steps must be referenced
        for step_num in range(1, 10):
            assert f"Step {step_num}" in content or f"{step_num}." in content, (
                f"Skill must include step {step_num} of the 9-step rewrite algorithm"
            )

    def test_skill_preserves_commands_constraint(self) -> None:
        """Skill must document the hard constraint: never drop commands."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "command" in content.lower(), (
            "Skill must document the commands preservation constraint"
        )

    def test_skill_mentions_foundational_context(self) -> None:
        """Skill must document that foundational context stays bare (not wrapped)."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "bare" in content, (
            "Skill must explain foundational context (project identity, directory map, "
            "tech stack) stays bare and is not wrapped in <important if> blocks"
        )

    def test_skill_has_diff_output(self) -> None:
        """Skill must produce a diff summary of changes."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        # Should use -/+ diff convention per audit-claude-config pattern
        assert "diff" in content.lower() or "+" in content, (
            "Skill must produce a diff summary of changes made"
        )

    def test_skill_resolves_default_claude_md(self) -> None:
        """Skill must resolve .claude/CLAUDE.md as default target."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert ".claude/CLAUDE.md" in content, (
            "Skill must default to .claude/CLAUDE.md as the target file"
        )


class TestImproveClaudeMdAlgorithmSidecar:
    """Verify the algorithm sidecar has required condition examples."""

    def test_algorithm_has_condition_examples(self) -> None:
        """algorithm.md must contain condition examples for <important if> blocks."""
        assert ALGORITHM_FILE.exists(), "Algorithm file not found"
        content = ALGORITHM_FILE.read_text()
        assert "<important if" in content, (
            "algorithm.md must include <important if> condition examples"
        )

    def test_algorithm_covers_all_9_steps(self) -> None:
        """algorithm.md must cover all 9 rewrite steps."""
        assert ALGORITHM_FILE.exists(), "Algorithm file not found"
        content = ALGORITHM_FILE.read_text()
        for step_num in range(1, 10):
            assert str(step_num) in content, f"algorithm.md must cover step {step_num}"

    def test_algorithm_documents_narrow_conditions(self) -> None:
        """algorithm.md must document narrow vs broad condition guidance."""
        assert ALGORITHM_FILE.exists(), "Algorithm file not found"
        content = ALGORITHM_FILE.read_text()
        assert "narrow" in content.lower() or "specific" in content.lower(), (
            "algorithm.md must document that conditions must be narrow and specific"
        )
