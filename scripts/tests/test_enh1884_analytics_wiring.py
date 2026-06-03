"""Doc-wiring regression tests for ENH-1884: analytics in /ll:init and /ll:configure.

Asserts that:
1. skills/init/interactive.md contains a Round 9 for analytics
2. skills/init/interactive.md has TOTAL = 10
3. skills/init/SKILL.md references analytics in the materialization step
4. skills/init/SKILL.md says "9–10 rounds"
5. skills/configure/SKILL.md contains analytics in the area mapping table
6. skills/configure/areas.md contains ## Area: analytics
7. skills/configure/show-output.md contains ## analytics --show
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

INIT_INTERACTIVE = PROJECT_ROOT / "skills" / "init" / "interactive.md"
INIT_SKILL = PROJECT_ROOT / "skills" / "init" / "SKILL.md"
CONFIGURE_SKILL = PROJECT_ROOT / "skills" / "configure" / "SKILL.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"
CONFIGURE_SHOW = PROJECT_ROOT / "skills" / "configure" / "show-output.md"


class TestEnh1884InitWiring:
    """skills/init must include a Round 9 analytics prompt and updated round counts."""

    def test_round_9_analytics_present(self) -> None:
        content = INIT_INTERACTIVE.read_text()
        assert "## Round 9: Analytics" in content, (
            "skills/init/interactive.md must contain '## Round 9: Analytics' "
            "for the analytics setup step"
        )

    def test_total_is_ten(self) -> None:
        content = INIT_INTERACTIVE.read_text()
        assert "TOTAL = 10" in content, (
            "skills/init/interactive.md must set TOTAL = 10 after adding "
            "the mandatory analytics round"
        )

    def test_skill_md_references_analytics(self) -> None:
        content = INIT_SKILL.read_text()
        assert "analytics" in content, (
            "skills/init/SKILL.md must reference 'analytics' "
            "in the configuration or display summary step"
        )

    def test_skill_md_round_count_updated(self) -> None:
        content = INIT_SKILL.read_text()
        assert "9–10 rounds" in content, (
            "skills/init/SKILL.md must say '9–10 rounds' (not '8–9 rounds') "
            "after adding the mandatory analytics round"
        )


class TestEnh1884ConfigureSkillMd:
    """skills/configure/SKILL.md must reference analytics in area mapping and arguments."""

    def test_area_mapping_table_has_analytics(self) -> None:
        content = CONFIGURE_SKILL.read_text()
        assert "analytics" in content, (
            "skills/configure/SKILL.md area mapping table must include 'analytics'"
        )

    def test_arguments_list_has_analytics(self) -> None:
        content = CONFIGURE_SKILL.read_text()
        assert "analytics" in content, (
            "skills/configure/SKILL.md ## Arguments list must include 'analytics'"
        )


class TestEnh1884ConfigureAreasMd:
    """skills/configure/areas.md must contain the ## Area: analytics section."""

    def test_area_section_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "## Area: analytics" in content, (
            "skills/configure/areas.md must contain '## Area: analytics' section"
        )

    def test_fields_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        for field in ("enabled", "capture.skills", "capture.corrections", "capture.file_events"):
            assert f"analytics.{field}" in content or field in content, (
                f"skills/configure/areas.md analytics area must reference config field '{field}'"
            )


class TestEnh1884ConfigureShowOutputMd:
    """skills/configure/show-output.md must contain the ## analytics --show section."""

    def test_show_section_present(self) -> None:
        content = CONFIGURE_SHOW.read_text()
        assert "## analytics --show" in content, (
            "skills/configure/show-output.md must contain '## analytics --show' section"
        )

    def test_show_section_has_fields(self) -> None:
        content = CONFIGURE_SHOW.read_text()
        for field in ("enabled", "capture.skills", "capture.corrections", "capture.file_events"):
            assert f"analytics.{field}" in content, (
                f"skills/configure/show-output.md analytics --show must reference config field '{field}'"
            )
