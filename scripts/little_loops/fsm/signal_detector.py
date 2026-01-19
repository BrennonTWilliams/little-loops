"""Signal detection for FSM loop execution output.

This module provides pattern-based signal detection for interpreting
special markers in action output, such as CONTEXT_HANDOFF:, FATAL_ERROR:, etc.

The signal detection layer enables the FSM executor to respond to signals
emitted by commands without coupling the executor to specific signal formats.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class DetectedSignal:
    """A signal detected in command output.

    Attributes:
        signal_type: Type of signal (e.g., "handoff", "error", "stop")
        payload: Captured content after the signal marker
        raw_match: The full matched string
    """

    signal_type: str
    payload: str | None
    raw_match: str


class SignalPattern:
    """Configurable signal pattern for detection.

    Signal patterns use regex to match markers in command output.
    A capture group can be used to extract a payload.

    Example:
        pattern = SignalPattern("handoff", r"CONTEXT_HANDOFF:\\s*(.+)")
        signal = pattern.search("CONTEXT_HANDOFF: Ready for fresh session")
        # signal.payload == "Ready for fresh session"
    """

    def __init__(self, name: str, pattern: str) -> None:
        """Initialize signal pattern.

        Args:
            name: Signal type name (e.g., "handoff")
            pattern: Regex pattern with optional capture group for payload
        """
        self.name = name
        self.regex = re.compile(pattern, re.MULTILINE)

    def search(self, output: str) -> DetectedSignal | None:
        """Search for this signal pattern in output.

        Args:
            output: Command output to search

        Returns:
            DetectedSignal if found, None otherwise
        """
        match = self.regex.search(output)
        if match:
            payload = match.group(1).strip() if match.groups() else None
            return DetectedSignal(
                signal_type=self.name,
                payload=payload,
                raw_match=match.group(0),
            )
        return None


# Built-in signal patterns
HANDOFF_SIGNAL = SignalPattern("handoff", r"CONTEXT_HANDOFF:\s*(.+)")
ERROR_SIGNAL = SignalPattern("error", r"FATAL_ERROR:\s*(.+)")
STOP_SIGNAL = SignalPattern("stop", r"LOOP_STOP:\s*(.*)")


class SignalDetector:
    """Detect signals in command output.

    Provides pattern-based signal detection with extensibility
    for custom signal types. The default patterns detect:

    - CONTEXT_HANDOFF: - Signals context exhaustion, payload is continuation info
    - FATAL_ERROR: - Signals unrecoverable error, payload is error message
    - LOOP_STOP: - Signals explicit loop termination request

    Example:
        detector = SignalDetector()
        signal = detector.detect_first("Some output\\nCONTEXT_HANDOFF: Continue")
        if signal and signal.signal_type == "handoff":
            # Handle handoff...
    """

    def __init__(self, patterns: list[SignalPattern] | None = None) -> None:
        """Initialize detector with patterns.

        Args:
            patterns: List of signal patterns to detect.
                     Defaults to built-in patterns (handoff, error, stop).
        """
        self.patterns = patterns or [HANDOFF_SIGNAL, ERROR_SIGNAL, STOP_SIGNAL]

    def detect(self, output: str) -> list[DetectedSignal]:
        """Detect all signals in output.

        Args:
            output: Command output to scan

        Returns:
            List of all detected signals
        """
        return [
            signal
            for pattern in self.patterns
            if (signal := pattern.search(output)) is not None
        ]

    def detect_first(self, output: str) -> DetectedSignal | None:
        """Detect first matching signal in output.

        Patterns are checked in order, so the first pattern in the list
        has highest priority.

        Args:
            output: Command output to scan

        Returns:
            First detected signal, or None if no signals found
        """
        for pattern in self.patterns:
            if signal := pattern.search(output):
                return signal
        return None
