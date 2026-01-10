"""Logo display utilities for little-loops CLI.

Provides functions to read and display the ASCII art logo.
"""

from __future__ import annotations

from pathlib import Path


def get_logo() -> str | None:
    """Read the CLI logo from assets.

    Returns:
        Logo text content, or None if file not found.
    """
    logo_path = Path(__file__).parent.parent.parent / "assets" / "ll-cli-logo.txt"
    if logo_path.exists():
        return logo_path.read_text()
    return None


def print_logo() -> None:
    """Print the CLI logo if available.

    Silent no-op if logo file is not found.
    """
    if logo := get_logo():
        print(logo)
