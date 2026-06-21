"""Installation detection and version comparison for ll-init."""

from __future__ import annotations

import importlib.metadata
import shutil
import subprocess
from enum import Enum
from pathlib import Path


class InstallStatus(Enum):
    UpToDate = "up_to_date"
    OutOfDate = "out_of_date"
    NotInstalled = "not_installed"
    Unknown = "unknown"


def detect_installation(project_root: Path) -> tuple[str | None, str | None]:
    """Detect local or global little-loops installation.

    Returns:
        (install_source, installed_version) where install_source is one of
        "local-editable", "global-claude-code", or None (not found).
        installed_version is the pip version string for local installs, None
        for global installs (version not determinable from plugin list).
    """
    # Local dev install takes precedence — check pip metadata first.
    try:
        installed = importlib.metadata.version("little-loops")
        return "local-editable", installed
    except importlib.metadata.PackageNotFoundError:
        pass

    # Global claude plugin check.
    if shutil.which("claude"):
        try:
            result = subprocess.run(
                ["claude", "plugin", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and "ll@little-loops" in result.stdout:
                return "global-claude-code", None
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    return None, None


def check_version(installed: str, current: str) -> InstallStatus:
    """Compare installed version against the expected current version.

    Args:
        installed: Version string from the installed pip package.
        current: Version string from the running plugin.

    Returns:
        UpToDate if versions match, OutOfDate otherwise.
    """
    if installed == current:
        return InstallStatus.UpToDate
    return InstallStatus.OutOfDate
