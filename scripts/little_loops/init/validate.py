"""Dependency validation for headless ll-init."""

from __future__ import annotations

import importlib.metadata
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DepWarning:
    """A non-blocking dependency warning from validate_deps()."""

    message: str
    install_hint: str | None = None


def _check_jq() -> DepWarning | None:
    """Check that jq is on PATH (required by all Claude Code hook adapters)."""
    if shutil.which("jq") is None:
        return DepWarning(
            message=(
                "'jq' not found in PATH — Claude Code hook adapters "
                "(hooks/adapters/claude-code/*.sh) will fail silently. "
                "Adapters parse the host JSON envelope with jq before invoking "
                "the Python handlers in little_loops.hooks."
            ),
            install_hint="https://stedolan.github.io/jq/download/",
        )
    return None


def _check_python3() -> DepWarning | None:
    """Check that python3 is on PATH (required by the SessionStart adapter)."""
    if shutil.which("python3") is None:
        return DepWarning(
            message="'python3' not found in PATH — SessionStart adapter will fail silently",
        )
    return None


def _check_pyyaml() -> DepWarning | None:
    """Check that pyyaml is importable (required for ll.local.md parsing)."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import yaml"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            return DepWarning(
                message=(
                    "'pyyaml' not installed — SessionStart config merge will fail silently "
                    "(little_loops.hooks.session_start uses yaml to parse .ll/ll.local.md)"
                ),
                install_hint="pip install pyyaml",
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _check_little_loops_version(plugin_version: str, project_root: Path) -> DepWarning | None:
    """Check that the installed little-loops pip package matches *plugin_version*."""
    try:
        installed = importlib.metadata.version("little-loops")
    except importlib.metadata.PackageNotFoundError:
        scripts_dir = project_root / "scripts"
        hint = (
            f"pip install -e '{scripts_dir}'"
            if scripts_dir.exists()
            else "pip install little-loops"
        )
        return DepWarning(
            message=(
                "'little-loops' pip package not installed — ll-* CLI tools unavailable."
            ),
            install_hint=hint,
        )

    if installed != plugin_version:
        scripts_dir = project_root / "scripts"
        hint = (
            f"pip install -e '{scripts_dir}'"
            if scripts_dir.exists()
            else "pip install --upgrade little-loops"
        )
        return DepWarning(
            message=(
                f"little-loops version mismatch: installed {installed!r}, "
                f"plugin expects {plugin_version!r}."
            ),
            install_hint=hint,
        )

    return None


def _check_tool_commands(config: dict[str, Any]) -> list[DepWarning]:
    """Check PATH availability of base commands in test/lint/type/format_cmd.

    Ports Step 7.5 of the skill: extracts the first token of each configured
    command, deduplicates, and warns for any not found on PATH.
    """
    project = config.get("project", {})
    cmd_fields = ["test_cmd", "lint_cmd", "type_cmd", "format_cmd"]
    base_commands: dict[str, str] = {}  # base_cmd → first source field

    for field in cmd_fields:
        value = project.get(field)
        if not value:
            continue
        base = value.strip().split()[0] if value.strip() else None
        if base and base not in base_commands:
            base_commands[base] = field

    warnings: list[DepWarning] = []
    for base_cmd, source_field in base_commands.items():
        if shutil.which(base_cmd) is None:
            skill_hint = "/ll:run-tests" if source_field == "test_cmd" else "/ll:check-code"
            warnings.append(
                DepWarning(
                    message=(
                        f"'{base_cmd}' not found in PATH — install it before "
                        f"running {skill_hint}"
                    ),
                )
            )

    return warnings


def validate_deps(
    config: dict[str, Any] | None = None,
    plugin_version: str | None = None,
    project_root: Path | None = None,
) -> list[DepWarning]:
    """Validate runtime dependencies and pip package version alignment.

    Combines Step 7.5 (tool command PATH checks) and Step 9.5 (hook
    dependencies + pip package check) from the /ll:init skill.

    All checks are non-blocking: every warning is collected and returned
    regardless of whether earlier checks failed.

    Args:
        config: ll-config.json dict (used for tool command PATH checks).
        plugin_version: Expected little-loops version string; skipped if None.
        project_root: Project root for scripts/ dir resolution; skipped if None.

    Returns:
        List of DepWarning instances (may be empty).
    """
    warnings: list[DepWarning] = []

    if config:
        warnings.extend(_check_tool_commands(config))

    w = _check_jq()
    if w:
        warnings.append(w)

    w = _check_python3()
    if w:
        warnings.append(w)

    w = _check_pyyaml()
    if w:
        warnings.append(w)

    if plugin_version is not None and project_root is not None:
        w = _check_little_loops_version(plugin_version, project_root)
        if w:
            warnings.append(w)

    return warnings
