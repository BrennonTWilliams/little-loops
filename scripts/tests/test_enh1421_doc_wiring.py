"""Doc-wiring tests for ENH-1421: Decouple Issue Status — Commands, Skills, and Docs.

Asserts that the key files in scope have been updated to use frontmatter `status:`
rather than directory paths (completed/, deferred/) for issue lifecycle operations.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

MANAGE_RELEASE = PROJECT_ROOT / "commands" / "manage-release.md"
MANAGE_ISSUE_SKILL = PROJECT_ROOT / "skills" / "manage-issue" / "SKILL.md"
ISSUE_MGMT_GUIDE = PROJECT_ROOT / "docs" / "guides" / "ISSUE_MANAGEMENT_GUIDE.md"
ARCHITECTURE = PROJECT_ROOT / "docs" / "ARCHITECTURE.md"
INIT_SKILL = PROJECT_ROOT / "skills" / "init" / "SKILL.md"
INIT_INTERACTIVE = PROJECT_ROOT / "skills" / "init" / "interactive.md"
FEAT1172_TEST = PROJECT_ROOT / "scripts" / "tests" / "test_feat1172_doc_wiring.py"


class TestManageReleaseDecoupled:
    """commands/manage-release.md must use frontmatter status for release detection."""

    def test_file_exists(self) -> None:
        assert MANAGE_RELEASE.exists()

    def test_uses_status_done(self) -> None:
        content = MANAGE_RELEASE.read_text()
        assert "status: done" in content, (
            "commands/manage-release.md must detect completed issues via frontmatter 'status: done'"
        )

    def test_uses_completed_at_range(self) -> None:
        content = MANAGE_RELEASE.read_text()
        assert "completed_at" in content, (
            "commands/manage-release.md must use completed_at date range for release detection"
        )

    def test_no_git_log_difffilter_completed_dir(self) -> None:
        content = MANAGE_RELEASE.read_text()
        bad_lines = [
            line for line in content.splitlines()
            if "git log --diff-filter=A" in line and ".issues/completed/" in line
        ]
        assert not bad_lines, (
            "commands/manage-release.md must not use 'git log --diff-filter=A ... .issues/completed/' "
            "for release detection — use frontmatter status: done + completed_at range instead"
        )


class TestManageIssueSkillDecoupled:
    """skills/manage-issue/SKILL.md must use frontmatter update instead of git mv."""

    def test_file_exists(self) -> None:
        assert MANAGE_ISSUE_SKILL.exists()

    def test_no_git_mv_to_completed(self) -> None:
        content = MANAGE_ISSUE_SKILL.read_text()
        assert not re.search(r"git mv .+completed/", content), (
            "skills/manage-issue/SKILL.md must not instruct 'git mv … completed/' — "
            "use frontmatter status: done instead"
        )

    def test_uses_status_done(self) -> None:
        content = MANAGE_ISSUE_SKILL.read_text()
        assert "status: done" in content, (
            "skills/manage-issue/SKILL.md must instruct setting 'status: done' in frontmatter "
            "when completing an issue"
        )


class TestIssueManagementGuideDecoupled:
    """docs/guides/ISSUE_MANAGEMENT_GUIDE.md must describe frontmatter-based lifecycle."""

    def test_file_exists(self) -> None:
        assert ISSUE_MGMT_GUIDE.exists()

    def test_lifecycle_references_status_field(self) -> None:
        content = ISSUE_MGMT_GUIDE.read_text()
        assert "status:" in content, (
            "docs/guides/ISSUE_MANAGEMENT_GUIDE.md must reference the 'status:' frontmatter field "
            "in its lifecycle description"
        )

    def test_no_directory_location_determines(self) -> None:
        content = ISSUE_MGMT_GUIDE.read_text()
        assert "Directory location determines" not in content, (
            "docs/guides/ISSUE_MANAGEMENT_GUIDE.md must not state 'Directory location determines' — "
            "status is now determined by frontmatter, not directory"
        )


class TestArchitectureDecoupled:
    """docs/ARCHITECTURE.md must not show completed/ as a routing directory in state diagrams."""

    def test_file_exists(self) -> None:
        assert ARCHITECTURE.exists()

    def test_no_completed_mermaid_node(self) -> None:
        content = ARCHITECTURE.read_text()
        assert "COMPLETED[.issues/completed/]" not in content, (
            "docs/ARCHITECTURE.md must not show 'COMPLETED[.issues/completed/]' mermaid node "
            "— remove state-directory nodes from the diagram"
        )

    def test_no_move_to_completed_in_diagram(self) -> None:
        content = ARCHITECTURE.read_text()
        # State transition arrows to completed/ are the routing-pattern concern
        assert "Move issue to completed/" not in content, (
            "docs/ARCHITECTURE.md state diagram must not describe 'Move issue to completed/' "
            "— describe frontmatter status update instead"
        )


class TestInitSkillDecoupled:
    """skills/init/SKILL.md must not generate completed_dir or deferred_dir in config."""

    def test_file_exists(self) -> None:
        assert INIT_SKILL.exists()

    def test_no_completed_dir(self) -> None:
        content = INIT_SKILL.read_text()
        assert "completed_dir" not in content, (
            "skills/init/SKILL.md must not generate 'completed_dir' in config — field is deprecated"
        )

    def test_no_deferred_dir(self) -> None:
        content = INIT_SKILL.read_text()
        assert "deferred_dir" not in content, (
            "skills/init/SKILL.md must not generate 'deferred_dir' in config — field is deprecated"
        )


class TestInitInteractiveDecoupled:
    """skills/init/interactive.md must not reference completed_dir or deferred_dir."""

    def test_file_exists(self) -> None:
        assert INIT_INTERACTIVE.exists()

    def test_no_completed_dir(self) -> None:
        content = INIT_INTERACTIVE.read_text()
        assert "completed_dir" not in content, (
            "skills/init/interactive.md must not reference 'completed_dir' — field is deprecated"
        )

    def test_no_deferred_dir(self) -> None:
        content = INIT_INTERACTIVE.read_text()
        assert "deferred_dir" not in content, (
            "skills/init/interactive.md must not reference 'deferred_dir' — field is deprecated"
        )


class TestFeat1172AssertionUpdated:
    """test_feat1172_doc_wiring.py must use the updated completed_at assertion."""

    def test_test_file_exists(self) -> None:
        assert FEAT1172_TEST.exists()

    def test_assertion_uses_status_or_frontmatter(self) -> None:
        content = FEAT1172_TEST.read_text()
        assert '"status" in row.lower() or "frontmatter" in row.lower()' in content, (
            "test_feat1172_doc_wiring.py must check that the completed_at doc row references "
            "'status' or 'frontmatter' (not the completed/ directory path)"
        )
