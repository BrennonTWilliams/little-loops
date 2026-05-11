"""Doc-wiring tests for ENH-1402: Fix product-analyzer output schema inconsistencies.

Asserts that skills/product-analyzer/SKILL.md has been updated to:
- Include Bash(date:*) in allowed-tools frontmatter
- Include goal_alignment_rating in Section 4 (ux_improvement) and Section 5 (business_value) templates
- Use product.goals_file config path in Section 2 instead of hardcoded .ll/ll-goals.md
- Consolidate skipped_reason enum to only not_enabled
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

SKILL_FILE = PROJECT_ROOT / "skills" / "product-analyzer" / "SKILL.md"


def _frontmatter(content: str) -> str:
    """Extract frontmatter block (between first and second ---)."""
    frontmatter_end = content.index("---", 3)
    return content[:frontmatter_end]


def _section(content: str, heading: str) -> str:
    """Extract content from a section heading to the next same-level heading."""
    start = content.index(heading)
    try:
        end = content.index("\n### ", start + len(heading))
    except ValueError:
        end = len(content)
    return content[start:end]


class TestProductAnalyzerSkillExists:
    def test_file_exists(self) -> None:
        assert SKILL_FILE.exists()


class TestBashDateInAllowedTools:
    """Frontmatter must include Bash(date:*) so the model can run date without hallucinating."""

    def test_bash_date_in_frontmatter(self) -> None:
        content = SKILL_FILE.read_text()
        fm = _frontmatter(content)
        assert "Bash(date" in fm, (
            "skills/product-analyzer/SKILL.md frontmatter must include 'Bash(date:*)' "
            "in allowed-tools so the model can populate analysis_timestamp without hallucinating"
        )


class TestAnalysisTimestampInstruction:
    """Output Format section must instruct the model to run date -u to get the timestamp."""

    def test_date_command_instruction_present(self) -> None:
        content = SKILL_FILE.read_text()
        output_section_start = content.index("## Output Format")
        output_section = content[output_section_start:]
        assert 'date -u +"%Y-%m-%dT%H:%M:%SZ"' in output_section, (
            "skills/product-analyzer/SKILL.md Output Format section must instruct "
            'the model to run `date -u +"%Y-%m-%dT%H:%M:%SZ"` for analysis_timestamp'
        )


class TestGoalAlignmentRatingInAllSections:
    """All three finding types must include goal_alignment_rating for consistent summary counts."""

    def test_feature_gap_has_goal_alignment_rating(self) -> None:
        content = SKILL_FILE.read_text()
        section = _section(content, "### 3. Goal-Gap Analysis")
        assert "goal_alignment_rating" in section, (
            "Section 3 (feature_gap) must include goal_alignment_rating in output structure"
        )

    def test_ux_improvement_has_goal_alignment_rating(self) -> None:
        content = SKILL_FILE.read_text()
        section = _section(content, "### 4. Persona Journey Analysis")
        assert "goal_alignment_rating" in section, (
            "Section 4 (ux_improvement) must include goal_alignment_rating in output structure "
            "so by_goal_alignment summary counts are accurate for all finding types"
        )

    def test_business_value_has_goal_alignment_rating(self) -> None:
        content = SKILL_FILE.read_text()
        section = _section(content, "### 5. Business Value Opportunities")
        assert "goal_alignment_rating" in section, (
            "Section 5 (business_value) must include goal_alignment_rating in output structure "
            "so by_goal_alignment summary counts are accurate for all finding types"
        )


class TestSkippedReasonEnum:
    """skipped_reason must only contain not_enabled after ENH-1400 removed goals_file_missing."""

    def test_goals_file_missing_absent_from_skipped_reason(self) -> None:
        content = SKILL_FILE.read_text()
        config_check_section = _section(content, "### 1. Configuration Check")
        assert "goals_file_missing" not in config_check_section, (
            "skipped_reason enum must not include 'goals_file_missing' — "
            "ENH-1400 made missing goals file trigger discovery, not a terminal skip"
        )

    def test_enabled_missing_absent_from_skipped_reason(self) -> None:
        content = SKILL_FILE.read_text()
        config_check_section = _section(content, "### 1. Configuration Check")
        assert "enabled_missing" not in config_check_section, (
            "skipped_reason enum must not include 'enabled_missing' — "
            "it is semantically equivalent to 'not_enabled' and creates ambiguity"
        )

    def test_not_enabled_is_sole_skipped_reason(self) -> None:
        content = SKILL_FILE.read_text()
        config_check_section = _section(content, "### 1. Configuration Check")
        assert "not_enabled" in config_check_section, (
            "skipped_reason must include 'not_enabled' as the sole valid value"
        )


class TestGoalsFilePathFromConfig:
    """Section 2 must use product.goals_file from config, not a hardcoded path."""

    def test_section2_references_product_goals_file_config(self) -> None:
        content = SKILL_FILE.read_text()
        section = _section(content, "### 2. Load Product Goals")
        assert "product.goals_file" in section, (
            "Section 2 must reference 'product.goals_file' config key "
            "instead of hardcoding '.ll/ll-goals.md' as the goals file path"
        )
