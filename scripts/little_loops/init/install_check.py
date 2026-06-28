"""Installation detection and version comparison for ll-init."""

from __future__ import annotations

import importlib.metadata
import json
import shutil
import subprocess
import sys
from enum import Enum
from pathlib import Path

from little_loops.host_runner import HostNotConfigured, resolve_host


class InstallStatus(Enum):
    UpToDate = "up_to_date"
    OutOfDate = "out_of_date"
    NotInstalled = "not_installed"
    Unknown = "unknown"


def _is_editable_install() -> bool:
    """Return True if little-loops is installed as an editable (dev) install."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "little-loops"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return any(
            line.startswith("Editable project location:") for line in result.stdout.splitlines()
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def detect_installation(
    project_root: Path,
) -> tuple[str | None, str | None, str | None]:
    """Detect local or global little-loops installation.

    Returns:
        (install_source, installed_version, install_path) where install_source is one of
        "local-editable", "pypi", "global-claude-code", "project-claude-code", or None
        (not found).  installed_version is the pip version string for pip-based installs,
        or the plugin version string for claude-code plugin installs.  install_path is the
        installPath from the plugin JSON (claude-code installs only), or None otherwise.
    """
    # Check pip metadata first.
    try:
        installed = importlib.metadata.version("little-loops")
        source = "local-editable" if _is_editable_install() else "pypi"
        return source, installed, None
    except importlib.metadata.PackageNotFoundError:
        pass

    # Global claude plugin check — use --json to retrieve version and scope.
    if shutil.which("claude"):
        try:
            result = subprocess.run(
                ["claude", "plugin", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                try:
                    plugins = json.loads(result.stdout)
                    for plugin in plugins:
                        if isinstance(plugin, dict) and plugin.get("name") == "ll@little-loops":
                            scope = plugin.get("scope", "user")
                            source = (
                                "project-claude-code"
                                if scope == "project"
                                else "global-claude-code"
                            )
                            return source, plugin.get("version"), plugin.get("installPath")
                except (json.JSONDecodeError, TypeError, AttributeError):
                    # Older CLI without --json: fall back to plain-text presence check.
                    if "ll@little-loops" in result.stdout:
                        return "global-claude-code", None, None
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    return None, None, None


def fetch_latest_pypi(timeout: float = 10.0) -> str | None:
    """Fetch the latest little-loops version from PyPI.

    Uses ``pip index versions`` and parses the ``LATEST:`` line.

    Returns:
        Latest version string, or None on any failure (offline, timeout, etc.).
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "index", "versions", "little-loops"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        for line in result.stdout.splitlines():
            if line.startswith("LATEST:"):
                return line.split(":", 1)[1].strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def fetch_latest_plugin(timeout: float = 10.0) -> str | None:
    """Fetch the latest ll@little-loops plugin version from the marketplace.

    Uses ``resolve_host()`` so the binary name is never hardcoded.

    Returns:
        Latest version string, or None on any failure (offline, no host, etc.).
        Only meaningful when the claude-code host is active.
    """
    try:
        runner = resolve_host()
        invocation = runner.build_version_check()
        binary = invocation.binary
    except HostNotConfigured:
        return None

    try:
        # Update marketplace index (best-effort — ignore failure).
        subprocess.run(
            [binary, "plugin", "marketplace", "update", "little-loops"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    try:
        result = subprocess.run(
            [binary, "plugin", "list", "--available", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            plugins = json.loads(result.stdout)
            for plugin in plugins:
                if isinstance(plugin, dict) and plugin.get("name") == "ll@little-loops":
                    return plugin.get("version")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, json.JSONDecodeError):
        pass
    return None


def check_version(installed: str, latest: str) -> InstallStatus:
    """Compare installed version against the latest available version.

    Args:
        installed: Version string from the installed pip package or plugin.
        latest: Version string from the latest available release (PyPI or marketplace).

    Returns:
        UpToDate if installed >= latest (semver), OutOfDate if installed < latest.
    """

    def _parse(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.split("."))

    if _parse(installed) >= _parse(latest):
        return InstallStatus.UpToDate
    return InstallStatus.OutOfDate
