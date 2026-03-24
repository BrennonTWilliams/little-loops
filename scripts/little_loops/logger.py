"""Logging utilities for little-loops.

Provides colorized console output with timestamps for automation tools.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import CliColorsConfig


class Logger:
    """Simple logger with timestamps and colors.

    Provides info, success, warning, and error logging methods with
    optional colorized output for terminal display.

    Attributes:
        verbose: Whether to output messages (False silences all output)
        use_color: Whether to use ANSI color codes
    """

    # ANSI color codes (defaults; may be overridden per-instance via colors param)
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    ORANGE = "\033[38;5;208m"  # 256-color orange (replaces red for errors)
    RED = "\033[38;5;208m"  # alias kept for backwards compatibility
    MAGENTA = "\033[35m"
    GRAY = "\033[90m"
    RESET = "\033[0m"

    def __init__(
        self,
        verbose: bool = True,
        use_color: bool | None = None,
        colors: CliColorsConfig | None = None,
    ) -> None:
        """Initialize logger.

        Args:
            verbose: Whether to output messages
            use_color: Whether to use ANSI color codes. Defaults to True unless
                the NO_COLOR environment variable is set.
            colors: Optional CliColorsConfig to override default color codes.
        """
        self.verbose = verbose
        if use_color is None:
            use_color = os.environ.get("NO_COLOR", "") == ""
        self.use_color = use_color

        # Apply color overrides from config
        if colors is not None:
            self.CYAN = f"\033[{colors.logger.info}m"
            self.GREEN = f"\033[{colors.logger.success}m"
            self.YELLOW = f"\033[{colors.logger.warning}m"
            self.ORANGE = f"\033[{colors.logger.error}m"
            self.RED = self.ORANGE  # keep alias in sync

    def _timestamp(self) -> str:
        """Get current timestamp string."""
        return datetime.now().strftime("%H:%M:%S")

    def _format(self, color: str, msg: str) -> str:
        """Format message with timestamp and optional color."""
        ts = self._timestamp()
        if self.use_color:
            return f"{color}[{ts}]{self.RESET} {msg}"
        return f"[{ts}] {msg}"

    def info(self, msg: str) -> None:
        """Log an info message."""
        if self.verbose:
            print(self._format(self.CYAN, msg), flush=True)

    def debug(self, msg: str) -> None:
        """Log a debug message (gray/dim)."""
        if self.verbose:
            print(self._format(self.GRAY, msg), flush=True)

    def success(self, msg: str) -> None:
        """Log a success message."""
        if self.verbose:
            print(self._format(self.GREEN, msg), flush=True)

    def warning(self, msg: str) -> None:
        """Log a warning message."""
        if self.verbose:
            print(self._format(self.YELLOW, msg), flush=True)

    def error(self, msg: str) -> None:
        """Log an error message to stderr."""
        if self.verbose:
            print(self._format(self.RED, msg), file=sys.stderr, flush=True)

    def timing(self, msg: str) -> None:
        """Log timing information."""
        if self.verbose:
            print(self._format(self.MAGENTA, msg), flush=True)

    def header(self, msg: str, char: str = "=", width: int = 60) -> None:
        """Log a header with separators."""
        if self.verbose:
            line = char * width
            print(line, flush=True)
            print(msg, flush=True)
            print(line, flush=True)


def format_duration(seconds: float) -> str:
    """Format duration in human-readable form.

    Args:
        seconds: Duration in seconds

    Returns:
        Human-readable string like "5.2 seconds" or "3.5 minutes"
    """
    if seconds >= 60:
        return f"{seconds / 60:.1f} minutes"
    return f"{seconds:.1f} seconds"
