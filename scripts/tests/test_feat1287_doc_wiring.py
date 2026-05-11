"""Tests for FEAT-1287: ll:explore-api skill and Learning Test Registry doc wiring.

Asserts that the new skill file exists with required phase headers and that the
documentation files this issue owns have been updated (skill counts, skills
tree entry, CLI tools list entry, ARCHITECTURE registry section, help.md skill
listing).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

SKILL_EXPLORE_API = PROJECT_ROOT / "skills" / "explore-api" / "SKILL.md"
README = PROJECT_ROOT / "README.md"
CONTRIBUTING = PROJECT_ROOT / "CONTRIBUTING.md"
CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"
ARCHITECTURE = PROJECT_ROOT / "docs" / "ARCHITECTURE.md"
HELP_CMD = PROJECT_ROOT / "commands" / "help.md"


class TestExploreApiSkillExists:
    """skills/explore-api/SKILL.md must exist with the four-phase structure."""

    def test_skill_file_exists(self) -> None:
        assert SKILL_EXPLORE_API.exists(), "skills/explore-api/SKILL.md must be created"

    def test_frontmatter_has_description(self) -> None:
        content = SKILL_EXPLORE_API.read_text()
        assert content.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
        assert "description:" in content, "SKILL.md frontmatter must declare description"
        assert "argument-hint:" in content, "SKILL.md frontmatter must declare argument-hint"

    def test_four_phase_headers_present(self) -> None:
        content = SKILL_EXPLORE_API.read_text()
        for phase in (
            "## Phase 1: Ingest",
            "## Phase 2: Hypothesize",
            "## Phase 3: Execute",
            "## Phase 4: Refine",
        ):
            assert phase in content, f"SKILL.md must contain '{phase}' header"

    def test_invokes_learning_tests_cli(self) -> None:
        content = SKILL_EXPLORE_API.read_text()
        assert "ll-learning-tests" in content, (
            "SKILL.md must reference ll-learning-tests CLI for Phase 1 registry check"
        )

    def test_assume_flag_documented(self) -> None:
        content = SKILL_EXPLORE_API.read_text()
        assert "--assume" in content, "SKILL.md must document the --assume flag"


class TestReadmeSkillCount:
    """README.md hero page must reflect 30 skills."""

    def test_skill_count_updated(self) -> None:
        content = README.read_text()
        assert "30 skills" in content, "README.md must show '30 skills'"
        assert "29 skills" not in content, "README.md must not still show '29 skills'"


class TestContributingWiring:
    """CONTRIBUTING.md must reflect 30 skills and list explore-api/ in the skills tree."""

    def test_skill_count_updated(self) -> None:
        content = CONTRIBUTING.read_text()
        assert "30 skill definitions" in content, (
            "CONTRIBUTING.md skill count line must show '30 skill definitions'"
        )

    def test_explore_api_in_skills_tree(self) -> None:
        content = CONTRIBUTING.read_text()
        assert "explore-api/" in content, (
            "CONTRIBUTING.md skills tree must include 'explore-api/'"
        )


class TestClaudeMdWiring:
    """.claude/CLAUDE.md must reflect 30 skills and list ll-learning-tests as a CLI tool."""

    def test_skill_count_updated(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "(30 skills)" in content, "CLAUDE.md must show '(30 skills)'"

    def test_ll_learning_tests_in_cli_list(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "ll-learning-tests" in content, (
            "CLAUDE.md CLI tools list must include ll-learning-tests"
        )


class TestArchitectureRegistrySection:
    """docs/ARCHITECTURE.md must document the Learning Test Registry."""

    def test_registry_section_present(self) -> None:
        content = ARCHITECTURE.read_text()
        assert "## Learning Test Registry" in content, (
            "ARCHITECTURE.md must contain a Learning Test Registry section"
        )

    def test_schema_documented(self) -> None:
        content = ARCHITECTURE.read_text()
        assert "LearnTestRecord" in content, (
            "ARCHITECTURE.md registry section must reference LearnTestRecord"
        )

    def test_cli_surface_documented(self) -> None:
        content = ARCHITECTURE.read_text()
        for subcommand in ("check", "list", "mark-stale"):
            assert subcommand in content, (
                f"ARCHITECTURE.md registry section must document '{subcommand}' subcommand"
            )


class TestHelpCommandWiring:
    """commands/help.md must list /ll:explore-api in the command reference and quick table."""

    def test_explore_api_command_listed(self) -> None:
        content = HELP_CMD.read_text()
        assert "/ll:explore-api" in content, (
            "commands/help.md must include /ll:explore-api in the command reference"
        )

    def test_explore_api_in_quick_reference(self) -> None:
        content = HELP_CMD.read_text()
        assert "`explore-api`" in content, (
            "commands/help.md Quick Reference Table must include `explore-api`"
        )
