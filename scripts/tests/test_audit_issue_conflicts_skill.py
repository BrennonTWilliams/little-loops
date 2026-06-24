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

    def test_phase1_filters_by_status(self) -> None:
        """Phase 1 must filter to open|in_progress|blocked via awk, not bare find (BUG-1799)."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "awk '/^---$/{n++; next} n==1 && /^status:/" in content
        assert "open|in_progress|blocked)" in content
        assert "TERMINAL_COUNT" in content
        assert "excluded $TERMINAL_COUNT terminal issues" in content

    def test_phase5_stages_only_modified_files(self) -> None:
        """Phase 5 must stage only Phase 4b-tracked files, not sweep untracked (BUG-1800)."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "MODIFIED_FILES=()" in content
        assert "MODIFIED_FILES+=(" in content
        assert 'for f in "${MODIFIED_FILES[@]}"; do' in content
        assert "git add {{config.issues.base_dir}}/" not in content

    def test_phase2b_cross_theme_header_present(self) -> None:
        """Phase 2b cross-theme section must be present in the skill (ENH-1801)."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "Phase 2b" in content
        assert "--cross-theme" in content

    def test_phase2b_uses_fingerprint_subcommand(self) -> None:
        """Phase 2b must reference the ll-issues fingerprint subcommand (ENH-1801)."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "ll-issues fingerprint" in content

    def test_phase4b_idempotency_guard_present(self) -> None:
        """Phase 4b must document idempotency rule for Scope Boundary/Addition/Resolution (ENH-1802)."""
        content = SKILL_FILE.read_text()
        phase4b_start = content.index("## Phase 4b")
        phase5_start = content.index("## Phase 5")
        phase4b_text = content[phase4b_start:phase5_start]
        assert "idempotent" in phase4b_text.lower(), (
            "Phase 4b must document idempotency pre-check for audit-authored section appends"
        )

    def test_phase4b_write_side_guard_present(self) -> None:
        """Phase 4b must guard writes to non-active targets (BUG-2264)."""
        content = SKILL_FILE.read_text()
        phase4b_start = content.index("## Phase 4b")
        phase5_start = content.index("## Phase 5")
        phase4b_text = content[phase4b_start:phase5_start]
        assert "ISSUE_FILES" in phase4b_text, "Phase 4b must reference ISSUE_FILES membership"
        assert "open|in_progress|blocked" in phase4b_text, "Phase 4b must re-check status"
        assert "not in active set" in phase4b_text, "Phase 4b must log skip reason"

    def test_phase6_skipped_inactive_count_reported(self) -> None:
        """Phase 6 must report SKIPPED_INACTIVE_COUNT for write-side guard skips (BUG-2264)."""
        content = SKILL_FILE.read_text()
        phase6_start = content.index("## Phase 6")
        phase6_text = content[phase6_start:]
        assert "SKIPPED_INACTIVE_COUNT" in phase6_text, "Phase 6 must tally skipped inactive writes"
        assert "Skipped (target not active)" in phase6_text, "Phase 6 must label the skip category"
