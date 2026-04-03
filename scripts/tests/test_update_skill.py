"""Tests for the /ll:update skill (FEAT-892).

These are structural/content tests verifying the skill file exists with
required content, and that marketplace.json is in sync with plugin.json.
"""

from __future__ import annotations

import json
from pathlib import Path

# Root of the project relative to this test file
PROJECT_ROOT = Path(__file__).parent.parent.parent

SKILL_FILE = PROJECT_ROOT / "skills" / "update" / "SKILL.md"
PLUGIN_JSON = PROJECT_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = PROJECT_ROOT / ".claude-plugin" / "marketplace.json"


class TestUpdateSkillExists:
    """Verify the skill file is created with required structure."""

    def test_skill_file_exists(self) -> None:
        """skills/update/SKILL.md must exist after implementation."""
        assert SKILL_FILE.exists(), (
            f"Skill file not found: {SKILL_FILE}\n"
            "Create skills/update/SKILL.md to implement FEAT-892."
        )

    def test_skill_has_marketplace_flag(self) -> None:
        """Skill must document --marketplace flag."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "--marketplace" in content, "Skill must include --marketplace flag"

    def test_skill_has_plugin_flag(self) -> None:
        """Skill must document --plugin flag."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "--plugin" in content, "Skill must include --plugin flag"

    def test_skill_has_package_flag(self) -> None:
        """Skill must document --package flag."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "--package" in content, "Skill must include --package flag"

    def test_skill_has_dry_run_flag(self) -> None:
        """Skill must document --dry-run flag."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "--dry-run" in content, "Skill must include --dry-run flag"

    def test_skill_has_all_flag(self) -> None:
        """Skill must document --all flag."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "--all" in content, "Skill must include --all flag"

    def test_skill_has_plugin_version_comment(self) -> None:
        """Skill must include PLUGIN_VERSION comment for version tracking."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "PLUGIN_VERSION:" in content, (
            "Skill must include <!-- PLUGIN_VERSION: X.Y.Z --> comment"
        )

    def test_skill_references_plugin_json(self) -> None:
        """Skill must reference plugin.json for version reading."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "plugin.json" in content, "Skill must read version from plugin.json"

    def test_skill_references_marketplace_json(self) -> None:
        """Skill must reference marketplace.json as update target."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "marketplace.json" in content, "Skill must target marketplace.json"

    def test_skill_references_claude_plugin_update(self) -> None:
        """Skill must use 'claude plugin update ll@little-loops' for plugin step."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "claude plugin update ll@little-loops" in content, (
            "Skill must run 'claude plugin update ll@little-loops' for --plugin step"
        )

    def test_skill_has_summary_report(self) -> None:
        """Skill must produce a summary report."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "PASS" in content, "Skill must include [PASS] status in summary"
        assert "FAIL" in content, "Skill must include [FAIL] status in summary"
        assert "SKIP" in content, "Skill must include [SKIP] status in summary"
        assert "DRY-RUN" in content, "Skill must include [DRY-RUN] status in summary"


class TestUpdateSkillSkipLogic:
    """Tests for ENH-905: skip logic when components are already at current version."""

    def test_step2_condition_includes_do_plugin(self) -> None:
        """Step 2 must read PLUGIN_VERSION when DO_PLUGIN is true, not only DO_MARKETPLACE."""
        content = SKILL_FILE.read_text()
        assert (
            '"$DO_MARKETPLACE" == true ]] || [[ "$DO_PLUGIN" == true' in content
            or '"$DO_PLUGIN" == true ]] || [[ "$DO_MARKETPLACE" == true' in content
        ), (
            "Step 2 condition must read PLUGIN_VERSION when either DO_MARKETPLACE or "
            "DO_PLUGIN is true. Change the condition from "
            "'if [[ \"$DO_MARKETPLACE\" == true ]]' to include DO_PLUGIN."
        )

    def test_plugin_step_reads_installed_version(self) -> None:
        """Step 4 must read installed plugin version via 'claude plugin list'."""
        content = SKILL_FILE.read_text()
        assert "INSTALLED_PLUGIN_VERSION" in content, (
            "Step 4 must read installed plugin version into INSTALLED_PLUGIN_VERSION"
        )
        assert "claude plugin list" in content, (
            "Step 4 must use 'claude plugin list' to detect installed plugin version"
        )

    def test_plugin_step_has_skip_result(self) -> None:
        """Step 4 must set PLUGIN_RESULT to SKIP when plugin is already current."""
        content = SKILL_FILE.read_text()
        assert 'PLUGIN_RESULT="SKIP (already at $PLUGIN_VERSION)"' in content, (
            'Step 4 must set PLUGIN_RESULT="SKIP (already at $PLUGIN_VERSION)" '
            "when the installed plugin version matches the current version"
        )

    def test_package_step_reads_src_version(self) -> None:
        """Step 5 must read source version from pyproject.toml for dev-repo installs."""
        content = SKILL_FILE.read_text()
        assert "SRC_VERSION" in content, (
            "Step 5 must read source version into SRC_VERSION for dev-repo installs"
        )

    def test_package_step_has_skip_result(self) -> None:
        """Step 5 must set PACKAGE_RESULT to SKIP when dev-repo package is already current."""
        content = SKILL_FILE.read_text()
        assert 'PACKAGE_RESULT="SKIP (already at $PKG_BEFORE)"' in content, (
            'Step 5 must set PACKAGE_RESULT="SKIP (already at $PKG_BEFORE)" '
            "when the installed package version matches the source version"
        )

    def test_plugin_version_read_has_error_guard(self) -> None:
        """PLUGIN_VERSION read must use error guard to fail gracefully outside repo (BUG-941)."""
        content = SKILL_FILE.read_text()
        lines = [l for l in content.split("\n") if "PLUGIN_VERSION=$(python3" in l]
        assert lines, "PLUGIN_VERSION=$(python3 ...) assignment not found in skill"
        assert all("2>/dev/null" in l for l in lines), (
            "PLUGIN_VERSION read (Step 2) must include '2>/dev/null || echo \"N/A\"' "
            "to handle missing .claude-plugin/ outside the little-loops repo. See BUG-941."
        )


class TestMarketplaceVersionSync:
    """Verify marketplace.json is in sync with plugin.json."""

    def test_plugin_json_exists(self) -> None:
        """plugin.json must exist."""
        assert PLUGIN_JSON.exists(), f"plugin.json not found: {PLUGIN_JSON}"

    def test_marketplace_json_exists(self) -> None:
        """marketplace.json must exist."""
        assert MARKETPLACE_JSON.exists(), f"marketplace.json not found: {MARKETPLACE_JSON}"

    def test_marketplace_top_level_version_matches_plugin(self) -> None:
        """marketplace.json top-level version must match plugin.json version.

        The --marketplace step syncs these two files. After implementation,
        the versions should be identical.
        """
        plugin_data = json.loads(PLUGIN_JSON.read_text())
        marketplace_data = json.loads(MARKETPLACE_JSON.read_text())

        plugin_version = plugin_data["version"]
        marketplace_version = marketplace_data["version"]

        assert marketplace_version == plugin_version, (
            f"marketplace.json top-level version ({marketplace_version!r}) "
            f"!= plugin.json version ({plugin_version!r}). "
            "Run /ll:update --marketplace or update marketplace.json manually."
        )

    def test_marketplace_plugin_entry_version_matches_plugin(self) -> None:
        """marketplace.json plugins[0].version must match plugin.json version.

        Both version fields in marketplace.json must be updated by --marketplace.
        """
        plugin_data = json.loads(PLUGIN_JSON.read_text())
        marketplace_data = json.loads(MARKETPLACE_JSON.read_text())

        plugin_version = plugin_data["version"]
        plugin_entry_version = marketplace_data["plugins"][0]["version"]

        assert plugin_entry_version == plugin_version, (
            f"marketplace.json plugins[0].version ({plugin_entry_version!r}) "
            f"!= plugin.json version ({plugin_version!r}). "
            "Both version fields must be updated by --marketplace step."
        )
