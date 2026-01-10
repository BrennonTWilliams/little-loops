"""State persistence for little-loops automation.

Provides state management for resume capability during automated processing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from little_loops.logger import Logger


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
            completed_issues=data.get("completed_issues", []),
            failed_issues=data.get("failed_issues", {}),
            attempted_issues=set(data.get("attempted_issues", [])),
            timing=data.get("timing", {}),
            corrections=data.get("corrections", {}),
        )


class StateManager:
    """Manages persistence of processing state.

    Handles loading, saving, and cleanup of state files for
    automated issue processing with resume capability.
    """

    def __init__(self, state_file: Path, logger: Logger) -> None:
        """Initialize state manager.

        Args:
            state_file: Path to the state file
            logger: Logger instance for output
        """
        self.state_file = state_file
        self.logger = logger
        self._state: ProcessingState | None = None

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
        """Save current state to file."""
        try:
            self.state.timestamp = datetime.now().isoformat()
            self.state_file.write_text(json.dumps(self.state.to_dict(), indent=2))
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

    def mark_failed(self, issue_id: str, reason: str) -> None:
        """Mark an issue as failed.

        Args:
            issue_id: Issue identifier
            reason: Failure reason
        """
        self.state.failed_issues[issue_id] = reason
        self.save()

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
