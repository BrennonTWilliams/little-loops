"""Doc-wiring regression tests for FEAT-1758: design tokens documentation.

Asserts that:
1. docs/reference/CONFIGURATION.md contains the design_tokens section header and full-example block
2. docs/reference/API.md contains the DesignTokensConfig sub-section
3. docs/ARCHITECTURE.md mentions design tokens in the configuration-flow section
4. README.md lists design tokens as a feature
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CONFIGURATION_MD = PROJECT_ROOT / "docs" / "reference" / "CONFIGURATION.md"
API_MD = PROJECT_ROOT / "docs" / "reference" / "API.md"
ARCHITECTURE_MD = PROJECT_ROOT / "docs" / "ARCHITECTURE.md"
README_MD = PROJECT_ROOT / "README.md"


class TestConfigurationMd:
    """docs/reference/CONFIGURATION.md must document all six design_tokens config fields."""

    def test_design_tokens_section_header(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "### `design_tokens`" in content, (
            "CONFIGURATION.md must include a ### `design_tokens` section header"
        )

    def test_design_tokens_in_full_example_json(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert '"design_tokens"' in content, (
            'CONFIGURATION.md full-example JSON must include a "design_tokens" block'
        )

    def test_enabled_field_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "`enabled`" in content and "bool" in content, (
            "CONFIGURATION.md design_tokens section must document the `enabled` field with bool type"
        )

    def test_path_field_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert ".ll/design-tokens" in content, (
            "CONFIGURATION.md design_tokens section must document the default path '.ll/design-tokens'"
        )

    def test_primitives_file_field_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "primitives_file" in content, (
            "CONFIGURATION.md design_tokens section must document the primitives_file field"
        )

    def test_semantic_file_field_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "semantic_file" in content, (
            "CONFIGURATION.md design_tokens section must document the semantic_file field"
        )

    def test_themes_dir_field_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "themes_dir" in content, (
            "CONFIGURATION.md design_tokens section must document the themes_dir field"
        )

    def test_active_theme_field_present(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "active_theme" in content, (
            "CONFIGURATION.md design_tokens section must document the active_theme field"
        )


class TestApiMd:
    """docs/reference/API.md must have a DesignTokensConfig sub-section."""

    def test_design_tokens_config_subsection(self) -> None:
        content = API_MD.read_text()
        assert "#### DesignTokensConfig" in content, (
            "API.md must include a '#### DesignTokensConfig' sub-section"
        )

    def test_design_tokens_config_row_in_brconfig_table(self) -> None:
        content = API_MD.read_text()
        assert "DesignTokensConfig" in content and "design_tokens" in content, (
            "API.md BRConfig table must include the design_tokens | DesignTokensConfig row"
        )


class TestArchitectureMd:
    """docs/ARCHITECTURE.md must mention design tokens as a cross-cutting config input."""

    def test_design_tokens_cross_cutting_note(self) -> None:
        content = ARCHITECTURE_MD.read_text()
        assert "DesignTokensConfig" in content or "design_token" in content.lower(), (
            "ARCHITECTURE.md must mention design tokens as a cross-cutting config input"
        )


class TestReadmeMd:
    """README.md must list design tokens as a feature."""

    def test_design_tokens_feature_mention(self) -> None:
        content = README_MD.read_text()
        assert "design token" in content.lower() or "design-token" in content.lower(), (
            "README.md must mention design tokens in the feature list"
        )
