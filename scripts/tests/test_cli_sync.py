"""Tests for cli/sync.py - ll-sync CLI entry point."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from little_loops.cli.sync import _print_sync_result, _print_sync_status, main_sync
from little_loops.sync import SyncResult, SyncStatus


class TestMainSyncNoAction:
    """Tests for main_sync when no action is provided."""

    def test_no_action_returns_1(self) -> None:
        """Returns 1 and prints help when no action given."""
        with patch("sys.argv", ["ll-sync"]):
            result = main_sync()
        assert result == 1


class TestMainSyncStatus:
    """Tests for main_sync status subcommand."""

    def test_status_returns_0(self) -> None:
        """Status action returns 0 on success."""
        mock_config = MagicMock()
        mock_config.sync.enabled = True

        mock_status = SyncStatus(
            provider="github",
            repo="owner/repo",
            local_total=10,
            local_synced=8,
            local_unsynced=2,
            github_total=9,
            github_only=1,
        )

        with (
            patch("sys.argv", ["ll-sync", "status"]),
            patch("little_loops.cli.sync.BRConfig", return_value=mock_config),
            patch("little_loops.cli.sync.GitHubSyncManager") as mock_manager_cls,
        ):
            mock_manager_cls.return_value.get_status.return_value = mock_status
            result = main_sync()

        assert result == 0

    def test_status_sync_disabled_returns_1(self) -> None:
        """Returns 1 when sync is not enabled in config."""
        mock_config = MagicMock()
        mock_config.sync.enabled = False

        with (
            patch("sys.argv", ["ll-sync", "status"]),
            patch("little_loops.cli.sync.BRConfig", return_value=mock_config),
        ):
            result = main_sync()

        assert result == 1


class TestMainSyncPush:
    """Tests for main_sync push subcommand."""

    def test_push_success(self) -> None:
        """Push returns 0 on success."""
        mock_config = MagicMock()
        mock_config.sync.enabled = True

        mock_result = SyncResult(
            action="push",
            success=True,
            created=["BUG-001"],
        )

        with (
            patch("sys.argv", ["ll-sync", "push"]),
            patch("little_loops.cli.sync.BRConfig", return_value=mock_config),
            patch("little_loops.cli.sync.GitHubSyncManager") as mock_manager_cls,
        ):
            mock_manager_cls.return_value.push_issues.return_value = mock_result
            result = main_sync()

        assert result == 0

    def test_push_failure_returns_1(self) -> None:
        """Push returns 1 when result is not successful."""
        mock_config = MagicMock()
        mock_config.sync.enabled = True

        mock_result = SyncResult(
            action="push",
            success=False,
            failed=[("BUG-001", "API error")],
        )

        with (
            patch("sys.argv", ["ll-sync", "push"]),
            patch("little_loops.cli.sync.BRConfig", return_value=mock_config),
            patch("little_loops.cli.sync.GitHubSyncManager") as mock_manager_cls,
        ):
            mock_manager_cls.return_value.push_issues.return_value = mock_result
            result = main_sync()

        assert result == 1

    def test_push_with_issue_ids(self) -> None:
        """Push passes specific issue IDs to manager."""
        mock_config = MagicMock()
        mock_config.sync.enabled = True

        mock_result = SyncResult(action="push", success=True)

        with (
            patch("sys.argv", ["ll-sync", "push", "BUG-001", "FEAT-002"]),
            patch("little_loops.cli.sync.BRConfig", return_value=mock_config),
            patch("little_loops.cli.sync.GitHubSyncManager") as mock_manager_cls,
        ):
            mock_manager_cls.return_value.push_issues.return_value = mock_result
            main_sync()

        mock_manager_cls.return_value.push_issues.assert_called_once_with(["BUG-001", "FEAT-002"])

    def test_push_dry_run(self) -> None:
        """Push with --dry-run creates manager with dry_run=True."""
        mock_config = MagicMock()
        mock_config.sync.enabled = True

        mock_result = SyncResult(action="push", success=True)

        with (
            patch("sys.argv", ["ll-sync", "--dry-run", "push"]),
            patch("little_loops.cli.sync.BRConfig", return_value=mock_config),
            patch("little_loops.cli.sync.GitHubSyncManager") as mock_manager_cls,
        ):
            mock_manager_cls.return_value.push_issues.return_value = mock_result
            main_sync()

        # Verify dry_run=True was passed to constructor
        call_kwargs = mock_manager_cls.call_args
        assert call_kwargs[1]["dry_run"] is True


class TestMainSyncPull:
    """Tests for main_sync pull subcommand."""

    def test_pull_success(self) -> None:
        """Pull returns 0 on success."""
        mock_config = MagicMock()
        mock_config.sync.enabled = True

        mock_result = SyncResult(
            action="pull",
            success=True,
            created=["BUG-005"],
        )

        with (
            patch("sys.argv", ["ll-sync", "pull"]),
            patch("little_loops.cli.sync.BRConfig", return_value=mock_config),
            patch("little_loops.cli.sync.GitHubSyncManager") as mock_manager_cls,
        ):
            mock_manager_cls.return_value.pull_issues.return_value = mock_result
            result = main_sync()

        assert result == 0

    def test_pull_with_labels(self) -> None:
        """Pull passes parsed labels to manager."""
        mock_config = MagicMock()
        mock_config.sync.enabled = True

        mock_result = SyncResult(action="pull", success=True)

        with (
            patch("sys.argv", ["ll-sync", "pull", "--labels", "bug,enhancement"]),
            patch("little_loops.cli.sync.BRConfig", return_value=mock_config),
            patch("little_loops.cli.sync.GitHubSyncManager") as mock_manager_cls,
        ):
            mock_manager_cls.return_value.pull_issues.return_value = mock_result
            main_sync()

        mock_manager_cls.return_value.pull_issues.assert_called_once_with(["bug", "enhancement"])

    def test_pull_without_labels(self) -> None:
        """Pull passes None labels when not specified."""
        mock_config = MagicMock()
        mock_config.sync.enabled = True

        mock_result = SyncResult(action="pull", success=True)

        with (
            patch("sys.argv", ["ll-sync", "pull"]),
            patch("little_loops.cli.sync.BRConfig", return_value=mock_config),
            patch("little_loops.cli.sync.GitHubSyncManager") as mock_manager_cls,
        ):
            mock_manager_cls.return_value.pull_issues.return_value = mock_result
            main_sync()

        mock_manager_cls.return_value.pull_issues.assert_called_once_with(None)

    def test_pull_failure_returns_1(self) -> None:
        """Pull returns 1 when result is not successful."""
        mock_config = MagicMock()
        mock_config.sync.enabled = True

        mock_result = SyncResult(action="pull", success=False)

        with (
            patch("sys.argv", ["ll-sync", "pull"]),
            patch("little_loops.cli.sync.BRConfig", return_value=mock_config),
            patch("little_loops.cli.sync.GitHubSyncManager") as mock_manager_cls,
        ):
            mock_manager_cls.return_value.pull_issues.return_value = mock_result
            result = main_sync()

        assert result == 1


class TestPrintSyncStatus:
    """Tests for _print_sync_status helper."""

    def test_basic_status_output(self) -> None:
        """Prints formatted status with counts."""
        logger = MagicMock()
        status = SyncStatus(
            provider="github",
            repo="owner/repo",
            local_total=10,
            local_synced=8,
            local_unsynced=2,
            github_total=9,
            github_only=1,
        )

        _print_sync_status(status, logger)

        # Verify key info was logged
        info_calls = [str(c) for c in logger.info.call_args_list]
        info_text = " ".join(info_calls)
        assert "github" in info_text
        assert "owner/repo" in info_text

    def test_status_with_github_error(self) -> None:
        """Prints warning when github_error is set."""
        logger = MagicMock()
        status = SyncStatus(
            provider="github",
            repo="owner/repo",
            github_error="Rate limit exceeded",
        )

        _print_sync_status(status, logger)

        logger.warning.assert_called_once()
        warning_text = str(logger.warning.call_args)
        assert "Rate limit" in warning_text

    def test_status_without_github_error(self) -> None:
        """Does not print warning when no github_error."""
        logger = MagicMock()
        status = SyncStatus(
            provider="github",
            repo="owner/repo",
        )

        _print_sync_status(status, logger)

        logger.warning.assert_not_called()


class TestPrintSyncResult:
    """Tests for _print_sync_result helper."""

    def test_successful_result_with_created(self) -> None:
        """Prints created items."""
        logger = MagicMock()
        result = SyncResult(
            action="push",
            success=True,
            created=["BUG-001", "FEAT-002"],
        )

        _print_sync_result(result, logger)

        info_text = " ".join(str(c) for c in logger.info.call_args_list)
        assert "COMPLETE" in info_text
        assert "BUG-001" in info_text

    def test_failed_result_with_errors(self) -> None:
        """Prints errors section when errors present."""
        logger = MagicMock()
        result = SyncResult(
            action="push",
            success=False,
            failed=[("BUG-001", "API error")],
            errors=["Connection timeout"],
        )

        _print_sync_result(result, logger)

        info_text = " ".join(str(c) for c in logger.info.call_args_list)
        assert "FAILED" in info_text
        error_text = " ".join(str(c) for c in logger.error.call_args_list)
        assert "API error" in error_text
        assert "Connection timeout" in error_text

    def test_result_with_updated_items(self) -> None:
        """Prints updated items section."""
        logger = MagicMock()
        result = SyncResult(
            action="pull",
            success=True,
            updated=["BUG-003"],
        )

        _print_sync_result(result, logger)

        info_text = " ".join(str(c) for c in logger.info.call_args_list)
        assert "BUG-003" in info_text

    def test_result_with_no_items(self) -> None:
        """Prints summary even with no items."""
        logger = MagicMock()
        result = SyncResult(
            action="push",
            success=True,
        )

        _print_sync_result(result, logger)

        info_text = " ".join(str(c) for c in logger.info.call_args_list)
        assert "Created: 0" in info_text
        assert "Updated: 0" in info_text
