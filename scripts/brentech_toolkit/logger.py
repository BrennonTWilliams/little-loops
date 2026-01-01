"""Logging utilities for brentech-toolkit.

Provides colorized console output with timestamps for automation tools.
"""

from __future__ import annotations

import sys
from datetime import datetime


class Logger:
    """Simple logger with timestamps and colors.

    Provides info, success, warning, and error logging methods with
    optional colorized output for terminal display.

    Attributes:
        verbose: Whether to output messages (False silences all output)
        use_color: Whether to use ANSI color codes
    """

    # ANSI color codes
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"
    RESET = "\033[0m"

    def __init__(self, verbose: bool = True, use_color: bool = True) -> None:
        """Initialize logger.

        Args:
            verbose: Whether to output messages
            use_color: Whether to use ANSI color codes
        """
        self.verbose = verbose
        self.use_color = use_color

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
            print(self._format(self.CYAN, msg))

    def success(self, msg: str) -> None:
        """Log a success message."""
        if self.verbose:
            print(self._format(self.GREEN, msg))

    def warning(self, msg: str) -> None:
        """Log a warning message."""
        if self.verbose:
            print(self._format(self.YELLOW, msg))

    def error(self, msg: str) -> None:
        """Log an error message to stderr."""
        if self.verbose:
            print(self._format(self.RED, msg), file=sys.stderr)

    def timing(self, msg: str) -> None:
        """Log timing information."""
        if self.verbose:
            print(self._format(self.MAGENTA, msg))

    def header(self, msg: str, char: str = "=", width: int = 60) -> None:
        """Log a header with separators."""
        if self.verbose:
            line = char * width
            print(line)
            print(msg)
            print(line)


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
