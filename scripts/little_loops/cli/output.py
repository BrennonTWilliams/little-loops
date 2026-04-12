"""Shared CLI output utilities: terminal width, text wrapping, and ANSI color."""

from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config import CliConfig


def terminal_width(default: int = 80) -> int:
    """Return the current terminal column width, falling back to *default*."""
    return shutil.get_terminal_size((default, 24)).columns


def wrap_text(text: str, indent: str = "  ", width: int | None = None) -> str:
    """Wrap *text* at terminal width with consistent *indent* on every line."""
    w = width or terminal_width()
    return textwrap.fill(text, width=w, initial_indent=indent, subsequent_indent=indent)


# ---------------------------------------------------------------------------
# ANSI color helpers — suppressed when NO_COLOR=1 or stdout is not a TTY
# ---------------------------------------------------------------------------

_USE_COLOR: bool = sys.stdout.isatty() and os.environ.get("NO_COLOR", "") == ""

PRIORITY_COLOR: dict[str, str] = {
    "P0": "38;5;208;1",
    "P1": "38;5;208",
    "P2": "33",
    "P3": "0",
    "P4": "2",
    "P5": "2",
}
TYPE_COLOR: dict[str, str] = {
    "BUG": "38;5;208",
    "FEAT": "32",
    "ENH": "34",
}


def configure_output(config: CliConfig | None = None) -> None:
    """Apply CLI color configuration to module-level color state.

    Call this once at startup after loading BRConfig. Updates _USE_COLOR,
    PRIORITY_COLOR, and TYPE_COLOR based on config and NO_COLOR env var.

    Args:
        config: CliConfig from BRConfig.cli, or None for defaults.
    """
    global _USE_COLOR, PRIORITY_COLOR, TYPE_COLOR

    # NO_COLOR env var always takes precedence (industry convention)
    no_color_env = os.environ.get("NO_COLOR", "") != ""

    if config is None:
        _USE_COLOR = sys.stdout.isatty() and not no_color_env
        return

    _USE_COLOR = config.color and sys.stdout.isatty() and not no_color_env

    # Merge custom priority colors
    PRIORITY_COLOR.update(
        {
            "P0": config.colors.priority.P0,
            "P1": config.colors.priority.P1,
            "P2": config.colors.priority.P2,
            "P3": config.colors.priority.P3,
            "P4": config.colors.priority.P4,
            "P5": config.colors.priority.P5,
        }
    )

    # Merge custom type colors
    TYPE_COLOR.update(
        {
            "BUG": config.colors.type.BUG,
            "FEAT": config.colors.type.FEAT,
            "ENH": config.colors.type.ENH,
        }
    )


def use_color_enabled() -> bool:
    """Return the current module-level color state set by configure_output()."""
    return _USE_COLOR


def colorize(text: str, code: str) -> str:
    """Wrap *text* in the given ANSI escape *code*, or return it unchanged."""
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def print_json(data: Any) -> None:
    """Print *data* as formatted JSON to stdout."""
    print(json.dumps(data, indent=2))


def format_relative_time(seconds: float) -> str:
    """Format seconds as a human-readable relative time string (e.g., '3m ago')."""
    total = int(seconds)
    if total < 60:
        return f"{total}s ago"
    if total < 3600:
        m, s = divmod(total, 60)
        return f"{m}m ago" if s == 0 else f"{m}m {s}s ago"
    if total < 86400:
        h, rem = divmod(total, 3600)
        m = rem // 60
        return f"{h}h ago" if m == 0 else f"{h}h {m}m ago"
    d, rem = divmod(total, 86400)
    h = rem // 3600
    return f"{d}d ago" if h == 0 else f"{d}d {h}h ago"
