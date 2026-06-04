"""Tests for FEAT-1447: verify-issue-loop skill wiring and doc count updates.

Asserts that documentation files reflect the new skill count (30) and that the
verify-issue-loop skill is wired into the user-facing surfaces (CONTRIBUTING
skill tree, commands/help.md, docs/ARCHITECTURE.md count lines).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

README = PROJECT_ROOT / "README.md"
CONTRIBUTING = PROJECT_ROOT / "CONTRIBUTING.md"
ARCHITECTURE = PROJECT_ROOT / "docs" / "ARCHITECTURE.md"
HELP_CMD = PROJECT_ROOT / "commands" / "help.md"
SKILL_VERIFY_ISSUE_LOOP = PROJECT_ROOT / "skills" / "verify-issue-loop" / "SKILL.md"


class TestVerifyIssueLoopSkillExists:
    """skills/verify-issue-loop/SKILL.md must exist (FEAT-1446 prerequisite)."""

    def test_skill_file_exists(self) -> None:
        assert SKILL_VERIFY_ISSUE_LOOP.exists(), (
            "skills/verify-issue-loop/SKILL.md must exist (created in FEAT-1446)"
        )


class TestReadmeSkillCount:
    """README.md hero page must reflect 63 skills."""

    def test_skill_count_updated(self) -> None:
        content = README.read_text()
        assert "63 skills" in content, "README.md must show '63 skills'"


class TestContributingWiring:
    """CONTRIBUTING.md must reflect 63 skills and list verify-issue-loop/ in the skills tree."""

    def test_skill_count_updated(self) -> None:
        content = CONTRIBUTING.read_text()
        assert "63 skill definitions" in content, (
            "CONTRIBUTING.md skill count line must show '63 skill definitions'"
        )

    def test_verify_issue_loop_in_skills_tree(self) -> None:
        content = CONTRIBUTING.read_text()
        assert "verify-issue-loop/" in content, (
            "CONTRIBUTING.md skills tree must include 'verify-issue-loop/'"
        )


class TestArchitectureSkillCount:
    """docs/ARCHITECTURE.md must reflect 63 skills in both the Mermaid node and tree."""

    def test_mermaid_skill_count_updated(self) -> None:
        content = ARCHITECTURE.read_text()
        assert "63 composable skills" in content, (
            "ARCHITECTURE.md Mermaid node must show '63 composable skills'"
        )

    def test_tree_skill_count_updated(self) -> None:
        content = ARCHITECTURE.read_text()
        assert "# 63 skill definitions" in content, (
            "ARCHITECTURE.md directory tree must show '# 63 skill definitions'"
        )


class TestHelpCommandWiring:
    """commands/help.md must list /ll:verify-issue-loop in the command reference and quick table."""

    def test_verify_issue_loop_command_listed(self) -> None:
        content = HELP_CMD.read_text()
        assert "/ll:verify-issue-loop" in content, (
            "commands/help.md must include /ll:verify-issue-loop in the command reference"
        )

    def test_verify_issue_loop_in_quick_reference(self) -> None:
        content = HELP_CMD.read_text()
        assert "verify-issue-loop" in content, (
            "commands/help.md quick-reference Automation & Loops list must include verify-issue-loop"
        )
