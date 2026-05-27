"""Doc-wiring regression tests for FEAT-1757: design tokens /ll:configure area and show-output wiring.

Asserts that:
1. skills/configure/SKILL.md contains design_tokens in the area mapping table
2. skills/configure/SKILL.md contains design-tokens in the arguments list
3. skills/configure/areas.md contains ## Area: design_tokens
4. skills/configure/show-output.md contains ## design_tokens --show
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CONFIGURE_SKILL = PROJECT_ROOT / "skills" / "configure" / "SKILL.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"
CONFIGURE_SHOW = PROJECT_ROOT / "skills" / "configure" / "show-output.md"


class TestConfigureSkillMd:
    """skills/configure/SKILL.md must reference design_tokens in area mapping and arguments."""

    def test_area_mapping_table_has_design_tokens(self) -> None:
        content = CONFIGURE_SKILL.read_text()
        assert "design_tokens" in content or "design-tokens" in content, (
            "skills/configure/SKILL.md area mapping table must include 'design_tokens' or 'design-tokens'"
        )

    def test_arguments_list_has_design_tokens(self) -> None:
        content = CONFIGURE_SKILL.read_text()
        assert "design-tokens" in content, (
            "skills/configure/SKILL.md ## Arguments list must include 'design-tokens'"
        )


class TestConfigureAreasMd:
    """skills/configure/areas.md must contain the ## Area: design_tokens section."""

    def test_area_section_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "## Area: design_tokens" in content, (
            "skills/configure/areas.md must contain '## Area: design_tokens' section"
        )

    def test_all_six_fields_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        for field in ("enabled", "path", "primitives_file", "semantic_file", "themes_dir", "active_theme"):
            assert f"design_tokens.{field}" in content, (
                f"skills/configure/areas.md design_tokens area must reference config field '{field}'"
            )


class TestConfigureShowOutputMd:
    """skills/configure/show-output.md must contain the ## design_tokens --show section."""

    def test_show_section_present(self) -> None:
        content = CONFIGURE_SHOW.read_text()
        assert "## design_tokens --show" in content, (
            "skills/configure/show-output.md must contain '## design_tokens --show' section"
        )

    def test_show_section_has_all_six_fields(self) -> None:
        content = CONFIGURE_SHOW.read_text()
        for field in ("enabled", "path", "primitives_file", "semantic_file", "themes_dir", "active_theme"):
            assert f"design_tokens.{field}" in content, (
                f"skills/configure/show-output.md design_tokens --show must reference config field '{field}'"
            )
