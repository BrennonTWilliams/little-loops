"""Tests for little_loops.state module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest

from little_loops.state import ProcessingState, StateManager


class TestProcessingState:
    """Tests for ProcessingState dataclass."""

    def test_default_values(self) -> None:
        """Test default values for ProcessingState."""
        state = ProcessingState()

        assert state.current_issue == ""
        assert state.phase == "idle"
        assert state.timestamp == ""
        assert state.completed_issues == []
        assert state.failed_issues == {}
        assert state.attempted_issues == set()
        assert state.timing == {}

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        state = ProcessingState(
            current_issue="/path/to/issue.md",
            phase="implementing",
            timestamp="2025-01-01T12:00:00",
            completed_issues=["BUG-001", "BUG-002"],
            failed_issues={"BUG-003": "Timeout"},
            attempted_issues={"BUG-001", "BUG-002", "BUG-003"},
            timing={"BUG-001": {"total": 120.5}},
        )

        result = state.to_dict()

        assert result["current_issue"] == "/path/to/issue.md"
        assert result["phase"] == "implementing"
        assert result["timestamp"] == "2025-01-01T12:00:00"
        assert result["completed_issues"] == ["BUG-001", "BUG-002"]
        assert result["failed_issues"] == {"BUG-003": "Timeout"}
        assert set(result["attempted_issues"]) == {"BUG-001", "BUG-002", "BUG-003"}
        assert result["timing"] == {"BUG-001": {"total": 120.5}}

    def test_to_dict_json_serializable(self) -> None:
        """Test that to_dict output is JSON serializable."""
        state = ProcessingState(
            current_issue="/issue.md",
            phase="test",
            attempted_issues={"ID1", "ID2"},
        )

        result = state.to_dict()
        # Should not raise
        json.dumps(result)

    def test_from_dict(self) -> None:
        """Test deserialization from dictionary."""
        data = {
            "current_issue": "/path/to/issue.md",
            "phase": "verifying",
            "timestamp": "2025-01-01T14:00:00",
            "completed_issues": ["FEAT-001"],
            "failed_issues": {"FEAT-002": "Merge conflict"},
            "attempted_issues": ["FEAT-001", "FEAT-002"],
            "timing": {"FEAT-001": {"ready": 10.0, "implement": 100.0}},
        }

        state = ProcessingState.from_dict(data)

        assert state.current_issue == "/path/to/issue.md"
        assert state.phase == "verifying"
        assert state.timestamp == "2025-01-01T14:00:00"
        assert state.completed_issues == ["FEAT-001"]
        assert state.failed_issues == {"FEAT-002": "Merge conflict"}
        assert state.attempted_issues == {"FEAT-001", "FEAT-002"}
        assert state.timing == {"FEAT-001": {"ready": 10.0, "implement": 100.0}}

    def test_from_dict_with_defaults(self) -> None:
        """Test from_dict with missing keys uses defaults."""
        data = {"phase": "processing"}

        state = ProcessingState.from_dict(data)

        assert state.current_issue == ""
        assert state.phase == "processing"
        assert state.timestamp == ""
        assert state.completed_issues == []
        assert state.failed_issues == {}
        assert state.attempted_issues == set()
        assert state.timing == {}

    def test_roundtrip_serialization(self) -> None:
        """Test roundtrip through to_dict and from_dict."""
        original = ProcessingState(
            current_issue="/test/path.md",
            phase="testing",
            timestamp="2025-01-01T00:00:00",
            completed_issues=["A", "B"],
            failed_issues={"C": "error"},
            attempted_issues={"A", "B", "C"},
            timing={"A": {"total": 50.0}},
        )

        restored = ProcessingState.from_dict(original.to_dict())

        assert restored.current_issue == original.current_issue
        assert restored.phase == original.phase
        assert restored.timestamp == original.timestamp
        assert restored.completed_issues == original.completed_issues
        assert restored.failed_issues == original.failed_issues
        assert restored.attempted_issues == original.attempted_issues
        assert restored.timing == original.timing


@pytest.fixture
def mock_logger() -> MagicMock:
    """Create a mock logger."""
    logger = MagicMock()
    return logger


@pytest.fixture
def temp_state_file(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary state file path."""
    yield tmp_path / "test-state.json"


class TestStateManager:
    """Tests for StateManager class."""

    def test_init(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Test StateManager initialization."""
        manager = StateManager(temp_state_file, mock_logger)

        assert manager.state_file == temp_state_file
        assert manager.logger == mock_logger
        assert manager._state is None

    def test_state_property_creates_default(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test state property creates default state when None."""
        manager = StateManager(temp_state_file, mock_logger)

        state = manager.state

        assert state is not None
        assert state.phase == "idle"
        assert state.timestamp != ""  # Should have a timestamp

    def test_load_nonexistent_file(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test loading from non-existent file returns None."""
        manager = StateManager(temp_state_file, mock_logger)

        result = manager.load()

        assert result is None

    def test_load_existing_file(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test loading from existing state file."""
        state_data = {
            "current_issue": "/test.md",
            "phase": "implementing",
            "timestamp": "2025-01-01T00:00:00",
            "completed_issues": ["BUG-001"],
            "failed_issues": {},
            "attempted_issues": ["BUG-001"],
            "timing": {},
        }
        temp_state_file.write_text(json.dumps(state_data))

        manager = StateManager(temp_state_file, mock_logger)
        result = manager.load()

        assert result is not None
        assert result.current_issue == "/test.md"
        assert result.phase == "implementing"
        assert result.completed_issues == ["BUG-001"]
        mock_logger.info.assert_called()

    def test_load_invalid_json(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test loading from corrupted JSON file."""
        temp_state_file.write_text("{ invalid json }")

        manager = StateManager(temp_state_file, mock_logger)
        result = manager.load()

        assert result is None
        mock_logger.error.assert_called()

    def test_save(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Test saving state to file."""
        manager = StateManager(temp_state_file, mock_logger)
        manager.state.current_issue = "/test.md"
        manager.state.phase = "processing"
        manager.state.completed_issues.append("BUG-001")

        manager.save()

        assert temp_state_file.exists()
        saved_data = json.loads(temp_state_file.read_text())
        assert saved_data["current_issue"] == "/test.md"
        assert saved_data["phase"] == "processing"
        assert "BUG-001" in saved_data["completed_issues"]
        assert saved_data["timestamp"] != ""  # Should be updated

    def test_cleanup(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Test cleanup removes state file."""
        temp_state_file.write_text("{}")
        assert temp_state_file.exists()

        manager = StateManager(temp_state_file, mock_logger)
        manager.cleanup()

        assert not temp_state_file.exists()
        mock_logger.info.assert_called()

    def test_cleanup_nonexistent_file(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test cleanup with non-existent file does nothing."""
        manager = StateManager(temp_state_file, mock_logger)

        # Should not raise
        manager.cleanup()

    def test_update_current(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test update_current updates state and saves."""
        manager = StateManager(temp_state_file, mock_logger)

        manager.update_current("/issue/path.md", "implementing")

        assert manager.state.current_issue == "/issue/path.md"
        assert manager.state.phase == "implementing"
        assert temp_state_file.exists()  # Should have saved

    def test_mark_attempted(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test mark_attempted adds to attempted set."""
        manager = StateManager(temp_state_file, mock_logger)

        manager.mark_attempted("BUG-001")

        assert "BUG-001" in manager.state.attempted_issues
        assert temp_state_file.exists()  # Should have saved

    def test_mark_attempted_no_save(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test mark_attempted with save=False doesn't save."""
        manager = StateManager(temp_state_file, mock_logger)

        manager.mark_attempted("BUG-001", save=False)

        assert "BUG-001" in manager.state.attempted_issues
        assert not temp_state_file.exists()  # Should NOT have saved

    def test_mark_completed(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test mark_completed updates state."""
        manager = StateManager(temp_state_file, mock_logger)
        manager.state.current_issue = "/current.md"
        manager.state.phase = "implementing"

        manager.mark_completed("BUG-001")

        assert "BUG-001" in manager.state.completed_issues
        assert manager.state.current_issue == ""
        assert manager.state.phase == "idle"

    def test_mark_completed_with_timing(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test mark_completed stores timing information."""
        manager = StateManager(temp_state_file, mock_logger)
        timing = {"ready": 10.0, "implement": 100.0, "verify": 20.0, "total": 130.0}

        manager.mark_completed("BUG-002", timing)

        assert manager.state.timing["BUG-002"] == timing

    def test_mark_failed(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test mark_failed stores failure reason."""
        manager = StateManager(temp_state_file, mock_logger)

        manager.mark_failed("BUG-003", "Timeout after 3600s")

        assert manager.state.failed_issues["BUG-003"] == "Timeout after 3600s"
        assert temp_state_file.exists()  # Should have saved

    def test_is_attempted_true(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test is_attempted returns True for attempted issues."""
        manager = StateManager(temp_state_file, mock_logger)
        manager.state.attempted_issues.add("BUG-001")

        assert manager.is_attempted("BUG-001") is True

    def test_is_attempted_false(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test is_attempted returns False for non-attempted issues."""
        manager = StateManager(temp_state_file, mock_logger)

        assert manager.is_attempted("BUG-999") is False

    def test_resume_workflow(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test typical resume workflow: save, reload, continue."""
        # Initial processing
        manager1 = StateManager(temp_state_file, mock_logger)
        manager1.mark_attempted("BUG-001")
        manager1.mark_completed("BUG-001", {"total": 60.0})
        manager1.mark_attempted("BUG-002")
        manager1.update_current("/bugs/BUG-002.md", "implementing")

        # Simulate crash/restart - new manager
        manager2 = StateManager(temp_state_file, mock_logger)
        restored = manager2.load()

        assert restored is not None
        assert "BUG-001" in restored.completed_issues
        assert "BUG-001" in restored.attempted_issues
        assert "BUG-002" in restored.attempted_issues
        assert restored.current_issue == "/bugs/BUG-002.md"
        assert restored.phase == "implementing"
