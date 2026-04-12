"""Tests for the /ll:update skill and /ll:publish command.

Structural/content tests verifying the skill and command files exist with
required content, and that marketplace.json is in sync with plugin.json.
"""

from __future__ import annotations

import json
from pathlib import Path

# Root of the project relative to this test file
PROJECT_ROOT = Path(__file__).parent.parent.parent

SKILL_FILE = PROJECT_ROOT / "skills" / "update" / "SKILL.md"
PUBLISH_CMD_FILE = PROJECT_ROOT / ".claude" / "commands" / "publish.md"
CONFIGURE_SKILL_FILE = PROJECT_ROOT / "skills" / "configure" / "SKILL.md"
PLUGIN_JSON = PROJECT_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = PROJECT_ROOT / ".claude-plugin" / "marketplace.json"


class TestUpdateSkillExists:
    """Verify the skill file exists with required consumer-first structure."""

    def test_skill_file_exists(self) -> None:
        """skills/update/SKILL.md must exist."""
        assert SKILL_FILE.exists(), (
            f"Skill file not found: {SKILL_FILE}\n"
            "Create skills/update/SKILL.md to implement FEAT-892."
        )

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
        assert "WARN" in content, "Skill must include [WARN] status in summary"

    def test_skill_does_not_reference_marketplace(self) -> None:
        """Consumer update skill must NOT reference marketplace.json (moved to /ll:publish)."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "marketplace.json" not in content, (
            "marketplace.json reference must move to commands/publish.md — "
            "the update skill is consumer-first and does not manage marketplace sync"
        )

    def test_skill_does_not_have_marketplace_flag(self) -> None:
        """Consumer update skill must NOT have --marketplace flag (moved to /ll:publish)."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "--marketplace" not in content, (
            "--marketplace flag must move to commands/publish.md — "
            "the consumer update skill only manages plugin + package"
        )


class TestUpdateSkillConsumerPath:
    """Tests for the consumer-first update flow."""

    def test_plugin_step_reads_installed_version(self) -> None:
        """Plugin step must read installed plugin version via 'claude plugin list'."""
        content = SKILL_FILE.read_text()
        assert "INSTALLED_PLUGIN_VERSION" in content, (
            "Plugin step must read installed plugin version into INSTALLED_PLUGIN_VERSION"
        )
        assert "claude plugin list" in content, (
            "Plugin step must use 'claude plugin list' to detect installed plugin version"
        )

    def test_package_step_uses_editable_detection(self) -> None:
        """Package step must detect dev installs via pip show, not ./scripts/ directory check."""
        content = SKILL_FILE.read_text()
        assert "Editable project location" in content, (
            "Package step must detect editable installs via "
            "'pip show little-loops | grep -E \"^Editable project location:\"' — "
            'not via [ -d "./scripts" ] which incorrectly triggers in consumer repos'
        )

    def test_package_step_does_not_use_scripts_dir_check(self) -> None:
        """Package step must NOT use [ -d './scripts' ] for dev-install detection."""
        content = SKILL_FILE.read_text()
        # The old buggy pattern should be gone
        assert '[ -d "./scripts" ]' not in content and "[ -d './scripts' ]" not in content, (
            "[ -d './scripts' ] must be removed — it incorrectly detects consumer repos "
            "that happen to have a scripts/ directory as dev installs"
        )


class TestPublishCommandExists:
    """Verify commands/publish.md exists with required source-repo-only structure."""

    def test_publish_command_exists(self) -> None:
        """commands/publish.md must exist for source-repo publishing operations."""
        assert PUBLISH_CMD_FILE.exists(), (
            f"Publish command not found: {PUBLISH_CMD_FILE}\n"
            "Create commands/publish.md with source-repo-only version bump logic."
        )

    def test_publish_has_source_repo_guard(self) -> None:
        """Publish command must guard against running outside the little-loops source repo."""
        content = PUBLISH_CMD_FILE.read_text()
        assert '! -f ".claude-plugin/plugin.json"' in content, (
            "Publish command must include source-repo guard: "
            'if [ ! -f ".claude-plugin/plugin.json" ]; then exit 1; fi'
        )

    def test_publish_references_plugin_json(self) -> None:
        """Publish command must reference plugin.json for version bumping."""
        content = PUBLISH_CMD_FILE.read_text()
        assert "plugin.json" in content, (
            "Publish command must reference .claude-plugin/plugin.json for version bump"
        )

    def test_publish_references_marketplace_json(self) -> None:
        """Publish command must reference marketplace.json for version sync."""
        content = PUBLISH_CMD_FILE.read_text()
        assert "marketplace.json" in content, (
            "Publish command must reference .claude-plugin/marketplace.json for version sync"
        )

    def test_publish_references_pyproject_toml(self) -> None:
        """Publish command must bump version in scripts/pyproject.toml."""
        content = PUBLISH_CMD_FILE.read_text()
        assert "pyproject.toml" in content, (
            "Publish command must reference scripts/pyproject.toml for version bump"
        )

    def test_publish_supports_bump_levels(self) -> None:
        """Publish command must support patch/minor/major bump levels."""
        content = PUBLISH_CMD_FILE.read_text()
        assert "patch" in content, "Publish command must support 'patch' bump level"
        assert "minor" in content, "Publish command must support 'minor' bump level"
        assert "major" in content, "Publish command must support 'major' bump level"

    def test_publish_supports_dry_run(self) -> None:
        """Publish command must support --dry-run flag."""
        content = PUBLISH_CMD_FILE.read_text()
        assert "--dry-run" in content, "Publish command must support --dry-run flag"


class TestUpdateSkillHealthCheck:
    def test_has_health_check_step(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Step 6" in content
        assert "Config Health Check" in content
        assert "[PASS] ll-config.json is valid" in content
        assert "WARN" in content


class TestConfigureSkillDevInstallFix:
    """Verify configure skill uses correct editable install detection."""

    def test_configure_skill_does_not_use_scripts_dir_check(self) -> None:
        """Configure skill must NOT use [ -d './scripts' ] for dev-install detection."""
        content = CONFIGURE_SKILL_FILE.read_text()
        assert '[ -d "./scripts" ]' not in content and "[ -d './scripts' ]" not in content, (
            "[ -d './scripts' ] must be removed from configure skill — it incorrectly "
            "triggers in consumer repos that have a scripts/ directory"
        )

    def test_configure_skill_uses_editable_detection(self) -> None:
        """Configure skill must detect dev installs via pip show editable check."""
        content = CONFIGURE_SKILL_FILE.read_text()
        assert "Editable project location" in content, (
            "Configure skill must use 'pip show little-loops | grep -E \"^Editable project location:\"' "
            "to detect editable installs, not [ -d './scripts' ]"
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

        The /ll:publish command syncs these two files. After a publish run,
        the versions should be identical.
        """
        plugin_data = json.loads(PLUGIN_JSON.read_text())
        marketplace_data = json.loads(MARKETPLACE_JSON.read_text())

        plugin_version = plugin_data["version"]
        marketplace_version = marketplace_data["version"]

        assert marketplace_version == plugin_version, (
            f"marketplace.json top-level version ({marketplace_version!r}) "
            f"!= plugin.json version ({plugin_version!r}). "
            "Run /ll:publish patch (or the appropriate bump) to sync versions."
        )

    def test_marketplace_plugin_entry_version_matches_plugin(self) -> None:
        """marketplace.json plugins[0].version must match plugin.json version.

        Both version fields in marketplace.json must be updated by /ll:publish.
        """
        plugin_data = json.loads(PLUGIN_JSON.read_text())
        marketplace_data = json.loads(MARKETPLACE_JSON.read_text())

        plugin_version = plugin_data["version"]
        plugin_entry_version = marketplace_data["plugins"][0]["version"]

        assert plugin_entry_version == plugin_version, (
            f"marketplace.json plugins[0].version ({plugin_entry_version!r}) "
            f"!= plugin.json version ({plugin_version!r}). "
            "Both version fields must be updated by /ll:publish."
        )
