"""Tests for little_loops.init.install_check — detect_installation and check_version."""

from __future__ import annotations

import importlib.metadata
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from little_loops.init.install_check import InstallStatus, check_version, detect_installation


class TestCheckVersion:
    def test_matching_versions_returns_up_to_date(self) -> None:
        assert check_version("1.0.0", "1.0.0") == InstallStatus.UpToDate

    def test_different_versions_returns_out_of_date(self) -> None:
        assert check_version("1.0.0", "1.1.0") == InstallStatus.OutOfDate

    def test_installed_ahead_returns_out_of_date(self) -> None:
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
            source, version = detect_installation(tmp_path)
        assert source is None
        assert version is None

    def test_local_installation_detected(self, tmp_path: Path) -> None:
        with (
            patch(
                "little_loops.init.install_check.importlib.metadata.version",
                return_value="1.2.3",
            ),
            patch("little_loops.init.install_check.shutil.which", return_value=None),
        ):
            source, version = detect_installation(tmp_path)
        assert source == "local-editable"
        assert version == "1.2.3"

    def test_global_claude_code_installation_detected(self, tmp_path: Path) -> None:
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
            mock_run.return_value = MagicMock(returncode=0, stdout="ll@little-loops\nother-plugin")
            source, version = detect_installation(tmp_path)
        assert source == "global-claude-code"
        assert version is None  # version not determinable from plugin list

    def test_global_not_registered_returns_none_none(self, tmp_path: Path) -> None:
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
            mock_run.return_value = MagicMock(returncode=0, stdout="some-other-plugin")
            source, version = detect_installation(tmp_path)
        assert source is None
        assert version is None

    def test_local_takes_precedence_over_global(self, tmp_path: Path) -> None:
        with (
            patch(
                "little_loops.init.install_check.importlib.metadata.version",
                return_value="1.2.3",
            ),
            patch(
                "little_loops.init.install_check.shutil.which",
                return_value="/usr/bin/claude",
            ),
        ):
            source, version = detect_installation(tmp_path)
        assert source == "local-editable"
        assert version == "1.2.3"

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
            source, version = detect_installation(tmp_path)
        assert source is None
        assert version is None

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
            source, version = detect_installation(tmp_path)
        assert source is None
        assert version is None
