"""Tests for little_loops.init.install_check — detect_installation, check_version,
fetch_latest_pypi, and fetch_latest_plugin."""

from __future__ import annotations

import importlib.metadata
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from little_loops.init.install_check import (
    InstallStatus,
    check_version,
    detect_installation,
    fetch_latest_plugin,
    fetch_latest_pypi,
)


class TestCheckVersion:
    """check_version(installed, latest) compares installed vs external-latest."""

    def test_matching_versions_returns_up_to_date(self) -> None:
        assert check_version("1.0.0", "1.0.0") == InstallStatus.UpToDate

    def test_different_versions_returns_out_of_date(self) -> None:
        # installed is behind PyPI latest
        assert check_version("1.0.0", "1.1.0") == InstallStatus.OutOfDate

    def test_installed_ahead_returns_out_of_date(self) -> None:
        # installed is ahead of known latest (pre-release / downgrade scenario)
        assert check_version("2.0.0", "1.0.0") == InstallStatus.OutOfDate


class TestDetectInstallation:
    def test_no_installation_returns_none_none(self, tmp_path: Path) -> None:
        with (
            patch(
                "little_loops.init.install_check.importlib.metadata.version",
                side_effect=importlib.metadata.PackageNotFoundError("little-loops"),
            ),
            patch("little_loops.init.install_check.shutil.which", return_value=None),
        ):
            source, version, install_path = detect_installation(tmp_path)
        assert source is None
        assert version is None
        assert install_path is None

    def test_local_editable_installation_detected(self, tmp_path: Path) -> None:
        pip_show_out = (
            "Name: little-loops\nVersion: 1.2.3\n"
            "Editable project location: /home/dev/little-loops/scripts\n"
        )
        with (
            patch(
                "little_loops.init.install_check.importlib.metadata.version",
                return_value="1.2.3",
            ),
            patch("little_loops.init.install_check.shutil.which", return_value=None),
            patch("little_loops.init.install_check.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=pip_show_out)
            source, version, install_path = detect_installation(tmp_path)
        assert source == "local-editable"
        assert version == "1.2.3"
        assert install_path is None

    def test_pypi_installation_detected(self, tmp_path: Path) -> None:
        pip_show_out = "Name: little-loops\nVersion: 1.2.3\n"  # No Editable line
        with (
            patch(
                "little_loops.init.install_check.importlib.metadata.version",
                return_value="1.2.3",
            ),
            patch("little_loops.init.install_check.shutil.which", return_value=None),
            patch("little_loops.init.install_check.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=pip_show_out)
            source, version, install_path = detect_installation(tmp_path)
        assert source == "pypi"
        assert version == "1.2.3"
        assert install_path is None

    def test_global_claude_code_installation_detected(self, tmp_path: Path) -> None:
        plugin_json = '[{"name": "ll@little-loops", "version": "1.129.0", "scope": "user"}, {"name": "other", "version": "1.0.0"}]'
        with (
            patch(
                "little_loops.init.install_check.importlib.metadata.version",
                side_effect=importlib.metadata.PackageNotFoundError("little-loops"),
            ),
            patch(
                "little_loops.init.install_check.shutil.which",
                return_value="/usr/bin/claude",
            ),
            patch("little_loops.init.install_check.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=plugin_json)
            source, version, install_path = detect_installation(tmp_path)
        assert source == "global-claude-code"
        assert version == "1.129.0"  # populated from plugin list --json
        assert install_path is None

    def test_global_not_registered_returns_none_none(self, tmp_path: Path) -> None:
        # JSON response with no ll@little-loops entry
        plugin_json = '[{"name": "some-other-plugin", "version": "1.0.0"}]'
        with (
            patch(
                "little_loops.init.install_check.importlib.metadata.version",
                side_effect=importlib.metadata.PackageNotFoundError("little-loops"),
            ),
            patch(
                "little_loops.init.install_check.shutil.which",
                return_value="/usr/bin/claude",
            ),
            patch("little_loops.init.install_check.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=plugin_json)
            source, version, install_path = detect_installation(tmp_path)
        assert source is None
        assert version is None
        assert install_path is None

    def test_local_takes_precedence_over_global(self, tmp_path: Path) -> None:
        pip_show_out = (
            "Name: little-loops\nVersion: 1.2.3\n"
            "Editable project location: /home/dev/little-loops/scripts\n"
        )
        with (
            patch(
                "little_loops.init.install_check.importlib.metadata.version",
                return_value="1.2.3",
            ),
            patch(
                "little_loops.init.install_check.shutil.which",
                return_value="/usr/bin/claude",
            ),
            patch("little_loops.init.install_check.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=pip_show_out)
            source, version, install_path = detect_installation(tmp_path)
        assert source == "local-editable"
        assert version == "1.2.3"
        assert install_path is None

    def test_global_cmd_timeout_returns_none_none(self, tmp_path: Path) -> None:
        with (
            patch(
                "little_loops.init.install_check.importlib.metadata.version",
                side_effect=importlib.metadata.PackageNotFoundError("little-loops"),
            ),
            patch(
                "little_loops.init.install_check.shutil.which",
                return_value="/usr/bin/claude",
            ),
            patch(
                "little_loops.init.install_check.subprocess.run",
                side_effect=subprocess.TimeoutExpired("claude", 10),
            ),
        ):
            source, version, install_path = detect_installation(tmp_path)
        assert source is None
        assert version is None
        assert install_path is None

    def test_global_cmd_nonzero_returncode_returns_none_none(self, tmp_path: Path) -> None:
        with (
            patch(
                "little_loops.init.install_check.importlib.metadata.version",
                side_effect=importlib.metadata.PackageNotFoundError("little-loops"),
            ),
            patch(
                "little_loops.init.install_check.shutil.which",
                return_value="/usr/bin/claude",
            ),
            patch("little_loops.init.install_check.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            source, version, install_path = detect_installation(tmp_path)
        assert source is None
        assert version is None
        assert install_path is None

    def test_pip_show_timeout_falls_back_to_pypi_source(self, tmp_path: Path) -> None:
        """If pip show times out, default source to 'pypi' (cannot confirm editable)."""
        with (
            patch(
                "little_loops.init.install_check.importlib.metadata.version",
                return_value="1.2.3",
            ),
            patch("little_loops.init.install_check.shutil.which", return_value=None),
            patch(
                "little_loops.init.install_check.subprocess.run",
                side_effect=subprocess.TimeoutExpired("pip", 10),
            ),
        ):
            source, version, install_path = detect_installation(tmp_path)
        assert source == "pypi"
        assert version == "1.2.3"
        assert install_path is None

    def test_project_claude_code_installation_detected(self, tmp_path: Path) -> None:
        """scope: project in plugin JSON → source must be project-claude-code."""
        plugin_json = (
            '[{"name": "ll@little-loops", "version": "1.129.0",'
            ' "scope": "project", "installPath": "/proj/.claude/plugins/ll"}]'
        )
        with (
            patch(
                "little_loops.init.install_check.importlib.metadata.version",
                side_effect=importlib.metadata.PackageNotFoundError("little-loops"),
            ),
            patch(
                "little_loops.init.install_check.shutil.which",
                return_value="/usr/bin/claude",
            ),
            patch("little_loops.init.install_check.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=plugin_json)
            source, version, install_path = detect_installation(tmp_path)
        assert source == "project-claude-code"
        assert version == "1.129.0"
        assert install_path == "/proj/.claude/plugins/ll"


class TestFetchLatestPypi:
    def test_success_returns_version(self) -> None:
        stdout = (
            "WARNING: pip index is experimental\n"
            "little-loops (1.130.0)\n"
            "Available versions: 1.130.0, 1.129.0\n"
            "LATEST: 1.130.0\n"
        )
        with patch("little_loops.init.install_check.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=stdout)
            result = fetch_latest_pypi()
        assert result == "1.130.0"

    def test_offline_timeout_returns_none(self) -> None:
        with patch(
            "little_loops.init.install_check.subprocess.run",
            side_effect=subprocess.TimeoutExpired("pip", 10),
        ):
            result = fetch_latest_pypi()
        assert result is None

    def test_bad_output_no_latest_returns_none(self) -> None:
        with patch("little_loops.init.install_check.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="No packages found\n")
            result = fetch_latest_pypi()
        assert result is None

    def test_oserror_returns_none(self) -> None:
        with patch(
            "little_loops.init.install_check.subprocess.run",
            side_effect=OSError("not found"),
        ):
            result = fetch_latest_pypi()
        assert result is None

    def test_nonzero_returncode_returns_none(self) -> None:
        with patch("little_loops.init.install_check.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = fetch_latest_pypi()
        assert result is None


class TestFetchLatestPlugin:
    def _make_runner_mock(self, binary: str = "claude") -> MagicMock:
        invocation = MagicMock()
        invocation.binary = binary
        runner = MagicMock()
        runner.build_version_check.return_value = invocation
        return runner

    def test_success_returns_version(self) -> None:
        plugin_json = '[{"name": "ll@little-loops", "version": "1.130.0"}]'
        with (
            patch("little_loops.init.install_check.resolve_host") as mock_rh,
            patch("little_loops.init.install_check.subprocess.run") as mock_run,
        ):
            mock_rh.return_value = self._make_runner_mock("claude")
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=""),  # marketplace update
                MagicMock(returncode=0, stdout=plugin_json),  # plugin list --available
            ]
            result = fetch_latest_plugin()
        assert result == "1.130.0"

    def test_offline_timeout_returns_none(self) -> None:
        with (
            patch("little_loops.init.install_check.resolve_host") as mock_rh,
            patch(
                "little_loops.init.install_check.subprocess.run",
                side_effect=subprocess.TimeoutExpired("claude", 10),
            ),
        ):
            mock_rh.return_value = self._make_runner_mock("claude")
            result = fetch_latest_plugin()
        assert result is None

    def test_no_host_returns_none(self) -> None:
        from little_loops.host_runner import HostNotConfigured

        with patch(
            "little_loops.init.install_check.resolve_host",
            side_effect=HostNotConfigured("no host"),
        ):
            result = fetch_latest_plugin()
        assert result is None

    def test_plugin_not_in_list_returns_none(self) -> None:
        plugin_json = '[{"name": "some-other-plugin", "version": "1.0.0"}]'
        with (
            patch("little_loops.init.install_check.resolve_host") as mock_rh,
            patch("little_loops.init.install_check.subprocess.run") as mock_run,
        ):
            mock_rh.return_value = self._make_runner_mock("claude")
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout=plugin_json),
            ]
            result = fetch_latest_plugin()
        assert result is None

    def test_uses_resolve_host_not_hardcoded_claude(self) -> None:
        """resolve_host() must be invoked — binary name must not be hardcoded."""
        with (
            patch("little_loops.init.install_check.resolve_host") as mock_rh,
            patch(
                "little_loops.init.install_check.subprocess.run",
                side_effect=subprocess.TimeoutExpired("any", 10),
            ),
        ):
            mock_rh.return_value = self._make_runner_mock("myhost")
            fetch_latest_plugin()
        mock_rh.assert_called_once()

    def test_marketplace_update_failure_does_not_abort(self) -> None:
        """A marketplace update failure is ignored; the list still runs."""
        plugin_json = '[{"name": "ll@little-loops", "version": "1.130.0"}]'
        with (
            patch("little_loops.init.install_check.resolve_host") as mock_rh,
            patch("little_loops.init.install_check.subprocess.run") as mock_run,
        ):
            mock_rh.return_value = self._make_runner_mock("claude")
            mock_run.side_effect = [
                subprocess.TimeoutExpired("claude", 10),  # marketplace update fails
                MagicMock(returncode=0, stdout=plugin_json),  # list still succeeds
            ]
            result = fetch_latest_plugin()
        assert result == "1.130.0"
