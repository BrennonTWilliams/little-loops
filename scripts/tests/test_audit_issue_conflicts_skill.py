"""Structural tests for the audit-issue-conflicts skill (FEAT-1031)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "audit-issue-conflicts" / "SKILL.md"


class TestAuditIssueConflictsSkillExists:
    """Verify the audit-issue-conflicts skill file is present and well-formed."""

    def test_skill_file_exists(self) -> None:
        """Skill file must be present."""
        assert SKILL_FILE.exists(), "Skill file not found"

    def test_dry_run_flag(self) -> None:
        """Skill must document --dry-run flag."""
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "--dry-run" in SKILL_FILE.read_text()

    def test_auto_flag(self) -> None:
        """Skill must document --auto flag."""
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "--auto" in SKILL_FILE.read_text()

    def test_severity_labels(self) -> None:
        """Skill must reference high, medium, and low severity labels."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        for label in ("high", "medium", "low"):
            assert label in content

    def test_conflict_types(self) -> None:
        """Skill must reference all four conflict type tokens."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        for ctype in ("requirement", "objective", "architecture", "scope"):
            assert ctype in content

    def test_no_conflicts_path(self) -> None:
        """Skill must document the no-conflicts output path."""
        assert SKILL_FILE.exists(), "Skill file not found"
        # NOTE: SKILL.md uses "No conflicts detected" (not "No conflicts found")
        assert "No conflicts detected" in SKILL_FILE.read_text()

    def test_config_issues_base_dir_glob(self) -> None:
        """Skill must reference the config.issues.base_dir glob pattern."""
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "{{config.issues.base_dir}}" in SKILL_FILE.read_text()
