"""State persistence for little-loops automation.

Provides state management for resume capability during automated processing.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.events import EventBus
from little_loops.logger import Logger


def _iso_now() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()


@dataclass
class ProcessingState:
    """Persistent state for automated issue processing.

    Enables resume capability after interruption by tracking:
    - Currently processing issue
    - Completed issues
    - Failed issues with reasons
    - Timing information
    - Auto-corrections made during validation

    Attributes:
        current_issue: Path to currently processing issue file
        phase: Current processing phase
        timestamp: Last update timestamp
        completed_issues: List of completed issue IDs
        failed_issues: Mapping of issue ID to failure reason
        attempted_issues: Set of issues already attempted
        timing: Per-issue timing breakdown
        corrections: Mapping of issue ID to list of corrections made
    """

    current_issue: str = ""
    phase: str = "idle"
    timestamp: str = ""
    completed_issues: list[str] = field(default_factory=list)
    failed_issues: dict[str, str] = field(default_factory=dict)
    attempted_issues: set[str] = field(default_factory=set)
    timing: dict[str, dict[str, float]] = field(default_factory=dict)
    corrections: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary for JSON serialization."""
        return {
            "current_issue": self.current_issue,
            "phase": self.phase,
            "timestamp": self.timestamp,
            "completed_issues": self.completed_issues,
            "failed_issues": self.failed_issues,
            "attempted_issues": list(self.attempted_issues),
            "timing": self.timing,
            "corrections": self.corrections,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProcessingState:
        """Create state from dictionary (JSON deserialization)."""
        return cls(
            current_issue=data.get("current_issue", ""),
            phase=data.get("phase", "idle"),
            timestamp=data.get("timestamp", ""),
            completed_issues=list(data.get("completed_issues", [])),
            failed_issues=dict(data.get("failed_issues", {})),
            attempted_issues=set(data.get("attempted_issues", [])),
            timing=dict(data.get("timing", {})),
            corrections=dict(data.get("corrections", {})),
        )


class StateManager:
    """Manages persistence of processing state.

    Handles loading, saving, and cleanup of state files for
    automated issue processing with resume capability.
    """

    def __init__(self, state_file: Path, logger: Logger, event_bus: EventBus | None = None) -> None:
        """Initialize state manager.

        Args:
            state_file: Path to the state file
            logger: Logger instance for output
            event_bus: Optional EventBus for emitting state transition events
        """
        self.state_file = state_file
        self.logger = logger
        self._event_bus = event_bus
        self._state: ProcessingState | None = None

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Emit an event via the EventBus if available."""
        if self._event_bus:
            self._event_bus.emit({"event": event_type, "ts": _iso_now(), **payload})

    @property
    def state(self) -> ProcessingState:
        """Get current state, creating new if needed."""
        if self._state is None:
            self._state = ProcessingState(timestamp=datetime.now().isoformat())
        return self._state

    def load(self) -> ProcessingState | None:
        """Load state from file.

        Returns:
            Loaded state or None if file doesn't exist
        """
        try:
            if self.state_file.exists():
                data = json.loads(self.state_file.read_text())
                self._state = ProcessingState.from_dict(data)
                self.logger.info(f"State loaded from {self.state_file}")
                return self._state
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse state file: {e}")
        except Exception as e:
            self.logger.error(f"Failed to load state: {e}")
        return None

    def save(self) -> None:
        """Save current state to file using an atomic write.

        Writes to a temporary file in the same directory, then renames it over
        the target path via os.replace.  This ensures the state file is always
        either the previous valid version or the new valid version — never an
        empty or partially-written file.
        """
        try:
            self.state.timestamp = datetime.now().isoformat()
            data = json.dumps(self.state.to_dict(), indent=2)
            tmp_fd, tmp_path = tempfile.mkstemp(dir=self.state_file.parent, suffix=".tmp")
            try:
                with os.fdopen(tmp_fd, "w") as f:
                    f.write(data)
                os.replace(tmp_path, self.state_file)
            except Exception:
                os.unlink(tmp_path)
                raise
            self.logger.info(f"State saved to {self.state_file}")
        except Exception as e:
            self.logger.error(f"Failed to save state: {e}")

    def cleanup(self) -> None:
        """Remove state file."""
        try:
            if self.state_file.exists():
                self.state_file.unlink()
                self.logger.info("State file cleaned up")
        except Exception as e:
            self.logger.error(f"Failed to cleanup state file: {e}")

    def update_current(self, issue_path: str, phase: str) -> None:
        """Update current issue and phase.

        Args:
            issue_path: Path to current issue file
            phase: Current processing phase
        """
        self.state.current_issue = issue_path
        self.state.phase = phase
        self.save()

    def mark_attempted(self, issue_id: str, *, save: bool = True) -> None:
        """Mark an issue as attempted.

        Args:
            issue_id: Issue identifier
            save: Whether to persist state immediately (default True)
        """
        self.state.attempted_issues.add(issue_id)
        if save:
            self.save()

    def mark_completed(self, issue_id: str, timing: dict[str, float] | None = None) -> None:
        """Mark an issue as completed.

        Args:
            issue_id: Issue identifier
            timing: Optional timing breakdown
        """
        self.state.completed_issues.append(issue_id)
        if timing:
            self.state.timing[issue_id] = timing
        self.state.current_issue = ""
        self.state.phase = "idle"
        self.save()
        self._emit("state.issue_completed", {"issue_id": issue_id, "status": "completed"})

    def mark_failed(self, issue_id: str, reason: str) -> None:
        """Mark an issue as failed.

        Args:
            issue_id: Issue identifier
            reason: Failure reason
        """
        self.state.failed_issues[issue_id] = reason
        self.save()
        self._emit(
            "state.issue_failed", {"issue_id": issue_id, "reason": reason, "status": "failed"}
        )

    def is_attempted(self, issue_id: str) -> bool:
        """Check if an issue has been attempted.

        Args:
            issue_id: Issue identifier

        Returns:
            True if issue was already attempted
        """
        return issue_id in self.state.attempted_issues

    def record_corrections(self, issue_id: str, corrections: list[str]) -> None:
        """Record corrections made to an issue.

        Args:
            issue_id: Issue identifier
            corrections: List of correction descriptions
        """
        if corrections:
            self.state.corrections[issue_id] = corrections
            self.save()
