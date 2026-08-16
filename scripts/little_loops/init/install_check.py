"""Installation detection and version comparison for ll-init."""

from __future__ import annotations

import importlib.metadata
import json
import re
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


def installed_package_version(pkg_name: str = "little-loops") -> str | None:
    """Return the installed version of *pkg_name*, or None if not installed.

    Thin wrapper over :func:`importlib.metadata.version` used as the single
    source of truth for the adapter gen-version stamp (write side in
    ``install_codex_adapter``), the warn-only staleness comparison
    (``cli._warn_adapter_staleness``), and — since ENH-3125 — version-drift
    detection for learning-test records
    (``learning_tests.gate.resolve_target_version``).

    The ``"little-loops"`` default is load-bearing: three call sites
    (``init/writers.py``, ``init/cli.py``) invoke this with no arguments.
    """
    try:
        return importlib.metadata.version(pkg_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _is_editable_install() -> bool:
    """Return True if little-loops is installed as an editable (dev) install."""
    try:
        # ll-no-project: pip introspection probe, not a host CLI/task spawn (ENH-3184 AC2)
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

    # Plugin check — resolve the host binary via resolve_host() rather than
    # hardcoding "claude" (CLAUDE.md host-abstraction rule). Mirrors
    # fetch_latest_plugin; only meaningful when the active host is claude-code.
    try:
        binary: str | None = resolve_host().build_version_check().binary
    except HostNotConfigured:
        binary = None
    if binary:
        try:
            # ll-no-project: detection probe, no task payload (ENH-3184 AC2)
            result = subprocess.run(
                [binary, "plugin", "list", "--json"],
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
        # ll-no-project: pip introspection probe, not a host CLI/task spawn (ENH-3184 AC2)
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
        # ll-no-project: maintenance probe (marketplace index update), no task payload (ENH-3184 AC2)
        subprocess.run(
            [binary, "plugin", "marketplace", "update", "little-loops"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    try:
        # ll-no-project: detection probe, no task payload (ENH-3184 AC2)
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
        UpToDate if installed >= latest, OutOfDate if installed < latest.

    Tolerates real-world version strings: non-numeric segments ("1.2.0rc1",
    "1.2.0.dev0", "2024.10") never raise, and unequal segment counts compare
    numerically ("1.2" == "1.2.0", not OutOfDate). A segment carrying a
    non-numeric suffix sorts before the same segment without one, matching
    semver's prerelease ordering ("1.2.0rc1" < "1.2.0").
    """
    installed_key, latest_key = _pad_version_keys(_version_key(installed), _version_key(latest))
    if installed_key >= latest_key:
        return InstallStatus.UpToDate
    return InstallStatus.OutOfDate


# Leading digits of a dot-separated version segment; the remainder (rc1,
# dev0, …) is carried along as a suffix rather than raising.
_SEGMENT_RE = re.compile(r"^(\d*)(.*)$")

# Release-rank half of a segment key: a segment WITHOUT a suffix (plain
# release) sorts after the same segment WITH one (prerelease).
_RELEASE = (1, "")


def _version_key(version: str) -> tuple[tuple[int, int, str], ...]:
    """Return a comparable key for *version*, padding-safe across lengths.

    Each dot-separated segment becomes ``(numeric_prefix, release_rank,
    suffix)``. Trailing empty segments compare equal to zero ("1.2" vs
    "1.2.0"): the shorter key is padded with release-zero segments.
    """
    # PEP 440 build metadata ("+local") carries no precedence — strip it.
    version = version.strip().split("+", 1)[0]
    parts: list[tuple[int, int, str]] = []
    for segment in version.split("."):
        match = _SEGMENT_RE.match(segment)
        digits = match.group(1) if match else ""
        suffix = match.group(2) if match else segment
        rank, rank_suffix = _RELEASE if not suffix else (0, suffix)
        parts.append((int(digits) if digits else 0, rank, rank_suffix))

    if not parts:
        parts.append((0, *_RELEASE))
    return tuple(parts)


def _pad_version_keys(
    a: tuple[tuple[int, int, str], ...], b: tuple[tuple[int, int, str], ...]
) -> tuple[tuple[tuple[int, int, str], ...], tuple[tuple[int, int, str], ...]]:
    """Pad the shorter of two version keys with release-zero segments."""
    pad = ((0, *_RELEASE),) * abs(len(a) - len(b))
    if len(a) < len(b):
        return a + pad, b
    return a, b + pad
