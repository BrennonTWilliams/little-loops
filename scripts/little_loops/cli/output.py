"""Shared CLI output utilities: terminal width, text wrapping, and ANSI color."""

from __future__ import annotations

import os
import shutil
import sys
import textwrap


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
    "P0": "31;1",
    "P1": "31",
    "P2": "33",
    "P3": "0",
    "P4": "2",
    "P5": "2",
}
TYPE_COLOR: dict[str, str] = {
    "BUG": "31",
    "FEAT": "32",
    "ENH": "34",
}


def colorize(text: str, code: str) -> str:
    """Wrap *text* in the given ANSI escape *code*, or return it unchanged."""
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"
