"""Logo display utilities for little-loops CLI.

Provides functions to read and display the ASCII art logo.
"""

from __future__ import annotations

from pathlib import Path


def get_logo(variant: str = "full") -> str | None:
    """Read the CLI logo from assets.

    Args:
        variant: "full" for the splash logo, "small" for the compact one-liner.

    Returns:
        Logo text content, or None if file not found.
    """
    name = "ll-cli-logo.txt" if variant == "full" else "ll-cli-logo-small.txt"
    logo_path = Path(__file__).parent / "assets" / name
    if logo_path.exists():
        return logo_path.read_text()
    return None


def print_logo(variant: str = "full") -> None:
    """Print the CLI logo if available.

    Silent no-op if logo file is not found.
    """
    if logo := get_logo(variant):
        print()
        print(logo)
        print()
