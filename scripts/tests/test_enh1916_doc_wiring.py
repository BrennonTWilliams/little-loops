"""Doc-wiring regression tests for ENH-1916: history config discoverability + EPIC-1707 backlinks.

Asserts that:
1. EPIC-1707 relates_to includes ENH-1909 and ENH-1911
2. skills/configure/SKILL.md contains history in area mapping table and arguments list
3. skills/configure/areas.md contains ## Area: history and all history.* key names
4. skills/configure/show-output.md contains ## history --show and key fields
5. docs/reference/CONFIGURATION.md contains ### `history` header and all key groups
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

EPIC_1707 = PROJECT_ROOT / ".issues" / "epics" / "P2-EPIC-1707-history-db-as-agent-context-layer.md"
CONFIGURE_SKILL = PROJECT_ROOT / "skills" / "configure" / "SKILL.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"
CONFIGURE_SHOW = PROJECT_ROOT / "skills" / "configure" / "show-output.md"
CONFIGURATION_MD = PROJECT_ROOT / "docs" / "reference" / "CONFIGURATION.md"


class TestEpic1707Frontmatter:
    """EPIC-1707 relates_to must include all child issue IDs."""

    def test_enh1909_present(self) -> None:
        content = EPIC_1707.read_text()
        assert "ENH-1909" in content, "EPIC-1707 relates_to must include ENH-1909"

    def test_enh1911_present(self) -> None:
        content = EPIC_1707.read_text()
        assert "ENH-1911" in content, "EPIC-1707 relates_to must include ENH-1911"

    def test_enh1913_present(self) -> None:
        content = EPIC_1707.read_text()
        assert "ENH-1913" in content, "EPIC-1707 relates_to must include ENH-1913"

    def test_enh1914_present(self) -> None:
        content = EPIC_1707.read_text()
        assert "ENH-1914" in content, "EPIC-1707 relates_to must include ENH-1914"

    def test_enh1916_present(self) -> None:
        content = EPIC_1707.read_text()
        assert "ENH-1916" in content, "EPIC-1707 relates_to must include ENH-1916"


class TestConfigureSkillMd:
    """skills/configure/SKILL.md must reference history in area mapping and arguments."""

    def test_area_mapping_table_has_history(self) -> None:
        content = CONFIGURE_SKILL.read_text()
        assert "| `history` |" in content, (
            "skills/configure/SKILL.md area mapping table must include '| `history` |'"
        )

    def test_arguments_list_has_history(self) -> None:
        content = CONFIGURE_SKILL.read_text()
        assert "`history`" in content, (
            "skills/configure/SKILL.md ## Arguments list must include '`history`'"
        )

    def test_list_block_has_history(self) -> None:
        content = CONFIGURE_SKILL.read_text()
        assert "history" in content, (
            "skills/configure/SKILL.md --list output block must mention history"
        )


class TestConfigureAreasMd:
    """skills/configure/areas.md must contain the ## Area: history section with all key names."""

    def test_area_section_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "## Area: history" in content, (
            "skills/configure/areas.md must contain '## Area: history' section"
        )

    def test_session_digest_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "session_digest.enabled" in content, (
            "skills/configure/areas.md history area must reference 'session_digest.enabled'"
        )

    def test_velocity_window_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "velocity_window" in content, (
            "skills/configure/areas.md history area must reference 'velocity_window'"
        )

    def test_max_age_days_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "max_age_days" in content, (
            "skills/configure/areas.md history area must reference 'max_age_days'"
        )

    def test_planning_skills_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "planning_skills" in content, (
            "skills/configure/areas.md history area must reference 'planning_skills'"
        )


class TestConfigureShowOutputMd:
    """skills/configure/show-output.md must contain ## history --show and all key fields."""

    def test_show_section_present(self) -> None:
        content = CONFIGURE_SHOW.read_text()
        assert "## history --show" in content, (
            "skills/configure/show-output.md must contain '## history --show' section"
        )

    def test_velocity_window_field(self) -> None:
        content = CONFIGURE_SHOW.read_text()
        assert "history.velocity_window" in content, (
            "skills/configure/show-output.md history --show must reference 'history.velocity_window'"
        )

    def test_session_digest_enabled_field(self) -> None:
        content = CONFIGURE_SHOW.read_text()
        assert "history.session_digest.enabled" in content, (
            "skills/configure/show-output.md history --show must reference 'history.session_digest.enabled'"
        )

    def test_go_no_go_field(self) -> None:
        content = CONFIGURE_SHOW.read_text()
        assert "history.go_no_go" in content, (
            "skills/configure/show-output.md history --show must reference 'history.go_no_go'"
        )

    def test_capture_issue_field(self) -> None:
        content = CONFIGURE_SHOW.read_text()
        assert "history.capture_issue" in content, (
            "skills/configure/show-output.md history --show must reference 'history.capture_issue'"
        )


class TestConfigurationMd:
    """docs/reference/CONFIGURATION.md must contain a ### `history` section with all key groups."""

    def test_history_header_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "### `history`" in content, (
            "docs/reference/CONFIGURATION.md must contain '### `history`' section header"
        )

    def test_velocity_window_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "velocity_window" in content, (
            "docs/reference/CONFIGURATION.md history section must document 'velocity_window'"
        )

    def test_max_age_days_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "max_age_days" in content, (
            "docs/reference/CONFIGURATION.md history section must document 'max_age_days'"
        )

    def test_session_digest_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "session_digest" in content, (
            "docs/reference/CONFIGURATION.md history section must document 'session_digest'"
        )

    def test_evolution_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "evolution" in content, (
            "docs/reference/CONFIGURATION.md history section must document 'evolution'"
        )

    def test_go_no_go_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "go_no_go" in content, (
            "docs/reference/CONFIGURATION.md history section must document 'go_no_go'"
        )

    def test_capture_issue_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "capture_issue" in content, (
            "docs/reference/CONFIGURATION.md history section must document 'capture_issue'"
        )

    def test_orphan_section_removed(self) -> None:
        content = CONFIGURATION_MD.read_text()
        # The old orphan entry in ## Manual Configuration must be removed; only
        # the canonical ### `history` section should document session_digest.
        manual_config_idx = content.find("## Manual Configuration")
        assert manual_config_idx != -1, "## Manual Configuration section must still exist"
        manual_section = content[manual_config_idx:]
        assert "### `history.session_digest`" not in manual_section, (
            "The orphan '### `history.session_digest`' entry must be removed from "
            "## Manual Configuration now that the full ### `history` section exists"
        )
