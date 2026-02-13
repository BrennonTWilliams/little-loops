"""Tests for GitHub Issues sync functionality."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.config import BRConfig
from little_loops.frontmatter import parse_frontmatter
from little_loops.logger import Logger
from little_loops.sync import (
    GitHubSyncManager,
    SyncResult,
    SyncStatus,
    _check_gh_auth,
    _get_issue_body,
    _get_repo_name,
    _parse_issue_title,
    _update_issue_frontmatter,
)


class TestSyncDataclasses:
    """Tests for sync dataclasses."""

    def test_sync_result_to_dict(self) -> None:
        """SyncResult converts to dictionary correctly."""
        result = SyncResult(
            action="push",
            success=True,
            created=["BUG-1 → #1"],
            updated=["BUG-2 → #2"],
        )
        d = result.to_dict()
        assert d["action"] == "push"
        assert d["success"] is True
        assert d["created"] == ["BUG-1 → #1"]
        assert d["updated"] == ["BUG-2 → #2"]

    def test_sync_result_defaults(self) -> None:
        """SyncResult has correct defaults."""
        result = SyncResult(action="pull", success=False)
        assert result.created == []
        assert result.updated == []
        assert result.skipped == []
        assert result.failed == []
        assert result.errors == []

    def test_sync_status_to_dict(self) -> None:
        """SyncStatus converts to dictionary correctly."""
        status = SyncStatus(
            provider="github",
            repo="owner/repo",
            local_total=10,
            local_synced=5,
            local_unsynced=5,
            github_total=12,
            github_only=2,
        )
        d = status.to_dict()
        assert d["provider"] == "github"
        assert d["repo"] == "owner/repo"
        assert d["local_total"] == 10
        assert d["local_synced"] == 5
        assert d["github_only"] == 2


class TestFrontmatterParsing:
    """Tests for frontmatter parsing utilities."""

    def test_parse_empty_content(self) -> None:
        """Empty content returns empty dict."""
        assert parse_frontmatter("") == {}

    def test_parse_no_frontmatter(self) -> None:
        """Content without frontmatter returns empty dict."""
        assert parse_frontmatter("# Title\n\nBody") == {}

    def test_parse_simple_frontmatter(self) -> None:
        """Simple key:value frontmatter is parsed."""
        content = """---
github_issue: 123
github_url: https://example.com
---

# Title
"""
        result = parse_frontmatter(content, coerce_types=True)
        assert result["github_issue"] == 123
        assert result["github_url"] == "https://example.com"

    def test_parse_null_values(self) -> None:
        """Null and empty values are handled."""
        content = """---
field1: null
field2: ~
field3:
---
"""
        result = parse_frontmatter(content)
        assert result["field1"] is None
        assert result["field2"] is None
        assert result["field3"] is None

    def test_parse_integer_values(self) -> None:
        """Integer values are parsed as int."""
        content = """---
github_issue: 42
priority: 1
---
"""
        result = parse_frontmatter(content, coerce_types=True)
        assert result["github_issue"] == 42
        assert isinstance(result["github_issue"], int)

    def test_parse_malformed_frontmatter(self) -> None:
        """Malformed frontmatter (no closing ---) returns empty."""
        content = """---
key: value
# No closing delimiter
"""
        assert parse_frontmatter(content) == {}


class TestFrontmatterUpdating:
    """Tests for frontmatter updating utilities."""

    def test_update_existing_frontmatter(self) -> None:
        """Updates are merged into existing frontmatter."""
        content = """---
existing: value
discovered_by: test
---

# Title
"""
        updates: dict[str, str | int] = {"github_issue": 42}
        result = _update_issue_frontmatter(content, updates)

        assert "existing: value" in result
        assert "discovered_by: test" in result
        assert "github_issue: 42" in result
        assert "# Title" in result

    def test_update_creates_frontmatter(self) -> None:
        """Frontmatter is created if missing."""
        content = "# Title\n\nBody"
        updates: dict[str, str | int] = {"github_issue": 42}
        result = _update_issue_frontmatter(content, updates)

        assert result.startswith("---")
        assert "github_issue: 42" in result
        assert "# Title" in result

    def test_update_overwrites_existing_field(self) -> None:
        """Existing field is overwritten with new value."""
        content = """---
github_issue: 1
---

# Title
"""
        updates: dict[str, str | int] = {"github_issue": 99}
        result = _update_issue_frontmatter(content, updates)

        assert "github_issue: 99" in result
        # Old value should not be present
        assert result.count("github_issue") == 1

    def test_update_preserves_body(self) -> None:
        """Body content is preserved after frontmatter update."""
        content = """---
key: value
---

# Title

Body paragraph.
"""
        updates: dict[str, str | int] = {"new_key": "new_value"}
        result = _update_issue_frontmatter(content, updates)

        assert "# Title" in result
        assert "Body paragraph." in result


class TestTitleParsing:
    """Tests for title parsing."""

    def test_parse_title_with_issue_id(self) -> None:
        """Title with issue ID prefix is parsed correctly."""
        content = """---
key: value
---

# BUG-123: Fix the bug
"""
        assert _parse_issue_title(content) == "Fix the bug"

    def test_parse_title_without_issue_id(self) -> None:
        """Title without issue ID is returned as-is."""
        content = "# Simple Title\n"
        assert _parse_issue_title(content) == "Simple Title"

    def test_parse_title_with_feat_id(self) -> None:
        """FEAT-prefixed titles are parsed correctly."""
        content = "# FEAT-42: New feature\n"
        assert _parse_issue_title(content) == "New feature"

    def test_parse_title_no_heading(self) -> None:
        """Returns empty string when no heading found."""
        content = "Just some text without a heading."
        assert _parse_issue_title(content) == ""


class TestBodyParsing:
    """Tests for body extraction."""

    def test_get_body_skips_frontmatter_and_title(self) -> None:
        """Body extraction skips frontmatter and title."""
        content = """---
key: value
---

# BUG-123: Title

This is the body.
"""
        body = _get_issue_body(content)
        assert body == "This is the body."

    def test_get_body_no_frontmatter(self) -> None:
        """Body extraction works without frontmatter."""
        content = """# Title

Body content here.
"""
        body = _get_issue_body(content)
        assert body == "Body content here."

    def test_get_body_multiline(self) -> None:
        """Multi-line body is extracted correctly."""
        content = """# Title

Paragraph one.

Paragraph two.
"""
        body = _get_issue_body(content)
        assert "Paragraph one." in body
        assert "Paragraph two." in body


class TestGitHubHelpers:
    """Tests for GitHub CLI helper functions."""

    def test_check_gh_auth_success(self) -> None:
        """Returns True when gh auth status succeeds."""
        mock_logger = MagicMock(spec=Logger)
        with patch("little_loops.sync._run_gh_command") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            assert _check_gh_auth(mock_logger) is True

    def test_check_gh_auth_failure(self) -> None:
        """Returns False when gh auth status fails."""
        mock_logger = MagicMock(spec=Logger)
        with patch("little_loops.sync._run_gh_command") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            assert _check_gh_auth(mock_logger) is False

    def test_check_gh_auth_not_installed(self) -> None:
        """Returns False when gh is not installed."""
        mock_logger = MagicMock(spec=Logger)
        with patch("little_loops.sync._run_gh_command") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            assert _check_gh_auth(mock_logger) is False

    def test_get_repo_name_success(self) -> None:
        """Returns repo name when gh repo view succeeds."""
        mock_logger = MagicMock(spec=Logger)
        with patch("little_loops.sync._run_gh_command") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="owner/repo\n", stderr=""
            )
            assert _get_repo_name(mock_logger) == "owner/repo"

    def test_get_repo_name_failure(self) -> None:
        """Returns None when gh repo view fails."""
        mock_logger = MagicMock(spec=Logger)
        with patch("little_loops.sync._run_gh_command") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            assert _get_repo_name(mock_logger) is None


class TestGitHubSyncManager:
    """Tests for GitHubSyncManager."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> BRConfig:
        """Create a mock BRConfig with test directories."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        config_file = claude_dir / "ll-config.json"
        config_file.write_text(
            json.dumps(
                {
                    "sync": {
                        "enabled": True,
                        "github": {
                            "repo": "test/repo",
                            "label_mapping": {"BUG": "bug", "FEAT": "enhancement"},
                            "priority_labels": True,
                        },
                    },
                    "issues": {
                        "base_dir": ".issues",
                    },
                }
            )
        )

        # Create issue directories
        issues_dir = tmp_path / ".issues"
        (issues_dir / "bugs").mkdir(parents=True)
        (issues_dir / "features").mkdir(parents=True)
        (issues_dir / "enhancements").mkdir(parents=True)
        (issues_dir / "completed").mkdir(parents=True)

        return BRConfig(tmp_path)

    @pytest.fixture
    def mock_logger(self) -> MagicMock:
        """Create a mock logger."""
        return MagicMock(spec=Logger)

    def test_extract_issue_id_bug(self, mock_config: BRConfig, mock_logger: MagicMock) -> None:
        """Issue ID is extracted from BUG filename."""
        manager = GitHubSyncManager(mock_config, mock_logger)
        assert manager._extract_issue_id("P1-BUG-123-description.md") == "BUG-123"

    def test_extract_issue_id_feat(self, mock_config: BRConfig, mock_logger: MagicMock) -> None:
        """Issue ID is extracted from FEAT filename."""
        manager = GitHubSyncManager(mock_config, mock_logger)
        assert manager._extract_issue_id("P2-FEAT-42-new-feature.md") == "FEAT-42"

    def test_extract_issue_id_invalid(self, mock_config: BRConfig, mock_logger: MagicMock) -> None:
        """Empty string for invalid filename."""
        manager = GitHubSyncManager(mock_config, mock_logger)
        assert manager._extract_issue_id("invalid.md") == ""

    def test_get_labels_for_issue(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Labels are generated from issue type and priority."""
        manager = GitHubSyncManager(mock_config, mock_logger)
        issue_path = tmp_path / ".issues" / "bugs" / "P1-BUG-123-test.md"
        issue_path.write_text("# BUG-123: Test")

        labels = manager._get_labels_for_issue(issue_path)
        assert "bug" in labels
        assert "p1" in labels

    def test_get_labels_for_feature(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Labels use correct mapping for features."""
        manager = GitHubSyncManager(mock_config, mock_logger)
        issue_path = tmp_path / ".issues" / "features" / "P2-FEAT-42-feature.md"
        issue_path.write_text("# FEAT-42: Feature")

        labels = manager._get_labels_for_issue(issue_path)
        assert "enhancement" in labels
        assert "p2" in labels

    def test_push_checks_auth(self, mock_config: BRConfig, mock_logger: MagicMock) -> None:
        """Push returns error if gh is not authenticated."""
        manager = GitHubSyncManager(mock_config, mock_logger)

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = False
            result = manager.push_issues()

        assert not result.success
        assert "not authenticated" in result.errors[0]

    def test_pull_checks_auth(self, mock_config: BRConfig, mock_logger: MagicMock) -> None:
        """Pull returns error if gh is not authenticated."""
        manager = GitHubSyncManager(mock_config, mock_logger)

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = False
            result = manager.pull_issues()

        assert not result.success
        assert "not authenticated" in result.errors[0]

    def test_pull_with_labels_filters_gh_command(
        self, mock_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """Pull with labels passes --label flags to gh issue list."""
        manager = GitHubSyncManager(mock_config, mock_logger)

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = True
            with patch("little_loops.sync._run_gh_command") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="[]", stderr=""
                )
                manager.pull_issues(["bug", "enhancement"])

        mock_run.assert_called_once()
        gh_args = mock_run.call_args[0][0]
        assert "--label" in gh_args
        # Should have --label bug --label enhancement
        label_indices = [i for i, a in enumerate(gh_args) if a == "--label"]
        assert len(label_indices) == 2
        assert gh_args[label_indices[0] + 1] == "bug"
        assert gh_args[label_indices[1] + 1] == "enhancement"

    def test_pull_without_labels_no_filter(
        self, mock_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """Pull without labels does not include --label flags."""
        manager = GitHubSyncManager(mock_config, mock_logger)

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = True
            with patch("little_loops.sync._run_gh_command") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="[]", stderr=""
                )
                manager.pull_issues()

        mock_run.assert_called_once()
        gh_args = mock_run.call_args[0][0]
        assert "--label" not in gh_args

    def test_get_status(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Status counts local and GitHub issues."""
        # Create a local issue with github_issue
        issue_file = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        issue_file.write_text(
            """---
github_issue: 1
---

# BUG-001: Test
"""
        )

        # Create another local issue without github_issue
        issue_file2 = tmp_path / ".issues" / "bugs" / "P2-BUG-002-unsynced.md"
        issue_file2.write_text("# BUG-002: Unsynced")

        manager = GitHubSyncManager(mock_config, mock_logger)

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = True
            with patch("little_loops.sync._run_gh_command") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout='[{"number": 1}, {"number": 2}]',
                    stderr="",
                )
                status = manager.get_status()

        assert status.local_total == 2
        assert status.local_synced == 1
        assert status.local_unsynced == 1
        assert status.github_total == 2
        assert status.github_only == 1  # Issue #2 is not tracked locally
        assert status.github_error is None

    def test_get_status_github_error(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Status reports error when GitHub query fails."""
        manager = GitHubSyncManager(mock_config, mock_logger)

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = True
            with patch("little_loops.sync._run_gh_command") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(1, "gh", stderr="API error")
                status = manager.get_status()

        assert status.github_total == 0
        assert status.github_only == 0
        assert status.github_error is not None
        assert "Failed to query GitHub" in status.github_error
        mock_logger.warning.assert_called()

    def test_get_local_issues_excludes_completed(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Completed issues are excluded unless configured."""
        # Create active issue
        issue_file = tmp_path / ".issues" / "bugs" / "P1-BUG-001-active.md"
        issue_file.write_text("# BUG-001: Active")

        # Create completed issue
        completed_file = tmp_path / ".issues" / "completed" / "P1-BUG-002-done.md"
        completed_file.write_text("# BUG-002: Done")

        manager = GitHubSyncManager(mock_config, mock_logger)
        issues = manager._get_local_issues()

        # Should only include active issue
        issue_names = [p.name for p in issues]
        assert "P1-BUG-001-active.md" in issue_names
        assert "P1-BUG-002-done.md" not in issue_names

    def test_determine_issue_type_bug(self, mock_config: BRConfig, mock_logger: MagicMock) -> None:
        """Bug label maps to BUG type."""
        manager = GitHubSyncManager(mock_config, mock_logger)
        assert manager._determine_issue_type(["bug", "p1"]) == "BUG"

    def test_determine_issue_type_enhancement(
        self, mock_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """Enhancement label maps to FEAT type (based on default mapping)."""
        manager = GitHubSyncManager(mock_config, mock_logger)
        # Note: Both FEAT and ENH map to "enhancement", so either could match
        result = manager._determine_issue_type(["enhancement"])
        assert result in ("FEAT", "ENH")

    def test_determine_issue_type_unknown(
        self, mock_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """Unknown labels return None."""
        manager = GitHubSyncManager(mock_config, mock_logger)
        assert manager._determine_issue_type(["documentation"]) is None

    def test_create_local_issue_avoids_completed_collision(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Pulled issues do not collide with completed issue numbers."""
        # BUG-042 exists in completed, active bugs only go up to 005
        (tmp_path / ".issues" / "bugs" / "P2-BUG-005-active.md").write_text("# BUG-005")
        (tmp_path / ".issues" / "completed" / "P1-BUG-042-done.md").write_text("# BUG-042")

        manager = GitHubSyncManager(mock_config, mock_logger)
        result = SyncResult(action="pull", success=True)
        gh_issue = {
            "number": 99,
            "title": "Test collision",
            "body": "body",
            "url": "https://github.com/test/repo/issues/99",
            "labels": [{"name": "bug"}],
        }

        manager._create_local_issue(gh_issue, "BUG", result)

        # Should get number 43 (not 6, which would collide with completed BUG-042)
        created_files = list((tmp_path / ".issues" / "bugs").glob("*BUG-43*"))
        assert len(created_files) == 1, (
            f"Expected BUG-43, got: {list((tmp_path / '.issues' / 'bugs').glob('*.md'))}"
        )

    def test_push_single_issue_creates_new(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Push creates new GitHub issue for unsynced local issue."""
        issue_file = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        issue_file.write_text(
            """---
discovered_by: test
---

# BUG-001: Test Bug

This is the body.
"""
        )

        manager = GitHubSyncManager(mock_config, mock_logger)
        result = SyncResult(action="push", success=True)

        with patch("little_loops.sync._run_gh_command") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="https://github.com/test/repo/issues/42\n",
                stderr="",
            )
            manager._push_single_issue(issue_file, "BUG-001", result)

        assert len(result.created) == 1
        assert "BUG-001 → #42" in result.created[0]

        # Check frontmatter was updated
        updated_content = issue_file.read_text()
        assert "github_issue: 42" in updated_content
        assert "github_url:" in updated_content
        assert "last_synced:" in updated_content


class TestDryRun:
    """Tests for dry-run mode in GitHubSyncManager."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> BRConfig:
        """Create a mock BRConfig with test directories."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        config_file = claude_dir / "ll-config.json"
        config_file.write_text(
            json.dumps(
                {
                    "sync": {
                        "enabled": True,
                        "github": {
                            "repo": "test/repo",
                            "label_mapping": {"BUG": "bug", "FEAT": "enhancement"},
                            "priority_labels": True,
                        },
                    },
                    "issues": {
                        "base_dir": ".issues",
                    },
                }
            )
        )

        # Create issue directories
        issues_dir = tmp_path / ".issues"
        (issues_dir / "bugs").mkdir(parents=True)
        (issues_dir / "features").mkdir(parents=True)
        (issues_dir / "enhancements").mkdir(parents=True)
        (issues_dir / "completed").mkdir(parents=True)

        return BRConfig(tmp_path)

    @pytest.fixture
    def mock_logger(self) -> MagicMock:
        """Create a mock logger."""
        return MagicMock(spec=Logger)

    def test_push_dry_run_does_not_call_gh_create(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Push dry-run does not create GitHub issues."""
        issue_file = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        issue_file.write_text(
            """---
discovered_by: test
---

# BUG-001: Test Bug

Body text.
"""
        )

        manager = GitHubSyncManager(mock_config, mock_logger, dry_run=True)

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = True
            with patch("little_loops.sync._run_gh_command") as mock_run:
                result = manager.push_issues()

        # _run_gh_command should not be called for issue create/edit
        mock_run.assert_not_called()
        assert result.success is True

    def test_push_dry_run_does_not_call_gh_edit(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Push dry-run does not edit existing GitHub issues."""
        issue_file = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        issue_file.write_text(
            """---
github_issue: 42
discovered_by: test
---

# BUG-001: Test Bug

Body text.
"""
        )

        manager = GitHubSyncManager(mock_config, mock_logger, dry_run=True)

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = True
            with patch("little_loops.sync._run_gh_command") as mock_run:
                result = manager.push_issues()

        mock_run.assert_not_called()
        assert result.success is True

    def test_push_dry_run_does_not_write_frontmatter(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Push dry-run does not modify local issue files."""
        issue_file = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        original_content = """---
discovered_by: test
---

# BUG-001: Test Bug

Body text.
"""
        issue_file.write_text(original_content)

        manager = GitHubSyncManager(mock_config, mock_logger, dry_run=True)

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = True
            with patch("little_loops.sync._run_gh_command"):
                manager.push_issues()

        # File should be unchanged
        assert issue_file.read_text() == original_content

    def test_push_dry_run_populates_result(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Push dry-run populates created and updated lists in result."""
        # Unsynced issue (would create)
        issue1 = tmp_path / ".issues" / "bugs" / "P1-BUG-001-new.md"
        issue1.write_text(
            """---
discovered_by: test
---

# BUG-001: New Bug
"""
        )

        # Synced issue (would update)
        issue2 = tmp_path / ".issues" / "bugs" / "P2-BUG-002-existing.md"
        issue2.write_text(
            """---
github_issue: 10
discovered_by: test
---

# BUG-002: Existing Bug
"""
        )

        manager = GitHubSyncManager(mock_config, mock_logger, dry_run=True)

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = True
            with patch("little_loops.sync._run_gh_command"):
                result = manager.push_issues()

        assert len(result.created) == 1
        assert "would create" in result.created[0]
        assert "BUG-001" in result.created[0]
        assert len(result.updated) == 1
        assert "would update" in result.updated[0]
        assert "BUG-002" in result.updated[0]

    def test_pull_dry_run_does_not_write_files(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Pull dry-run does not create local issue files."""
        manager = GitHubSyncManager(mock_config, mock_logger, dry_run=True)

        github_issues = [
            {
                "number": 99,
                "title": "Remote Bug",
                "body": "body",
                "url": "https://github.com/test/repo/issues/99",
                "labels": [{"name": "bug"}],
                "state": "OPEN",
            }
        ]

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = True
            with patch("little_loops.sync._run_gh_command") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=json.dumps(github_issues), stderr=""
                )
                result = manager.pull_issues()

        # No new files should exist
        bug_files = list((tmp_path / ".issues" / "bugs").glob("*.md"))
        assert len(bug_files) == 0
        assert result.success is True

    def test_pull_dry_run_populates_result(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Pull dry-run populates created list with preview entries."""
        manager = GitHubSyncManager(mock_config, mock_logger, dry_run=True)

        github_issues = [
            {
                "number": 99,
                "title": "Remote Bug",
                "body": "body",
                "url": "https://github.com/test/repo/issues/99",
                "labels": [{"name": "bug"}],
                "state": "OPEN",
            }
        ]

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = True
            with patch("little_loops.sync._run_gh_command") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=json.dumps(github_issues), stderr=""
                )
                result = manager.pull_issues()

        assert len(result.created) == 1
        assert "would create" in result.created[0]
        assert "#99" in result.created[0]
        assert "Remote Bug" in result.created[0]
