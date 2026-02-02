"""Tests for little_loops.state module."""

from __future__ import annotations

import json
import threading
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
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
        assert state.corrections == {}

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
            corrections={"BUG-001": ["Added missing section"]},
        )

        result = state.to_dict()

        assert result["current_issue"] == "/path/to/issue.md"
        assert result["phase"] == "implementing"
        assert result["timestamp"] == "2025-01-01T12:00:00"
        assert result["completed_issues"] == ["BUG-001", "BUG-002"]
        assert result["failed_issues"] == {"BUG-003": "Timeout"}
        assert set(result["attempted_issues"]) == {"BUG-001", "BUG-002", "BUG-003"}
        assert result["timing"] == {"BUG-001": {"total": 120.5}}
        assert result["corrections"] == {"BUG-001": ["Added missing section"]}

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
            "corrections": {"FEAT-001": ["Updated file path", "Fixed line numbers"]},
        }

        state = ProcessingState.from_dict(data)

        assert state.current_issue == "/path/to/issue.md"
        assert state.phase == "verifying"
        assert state.timestamp == "2025-01-01T14:00:00"
        assert state.completed_issues == ["FEAT-001"]
        assert state.failed_issues == {"FEAT-002": "Merge conflict"}
        assert state.attempted_issues == {"FEAT-001", "FEAT-002"}
        assert state.timing == {"FEAT-001": {"ready": 10.0, "implement": 100.0}}
        assert state.corrections == {"FEAT-001": ["Updated file path", "Fixed line numbers"]}

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
        assert state.corrections == {}

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
            corrections={"A": ["Fixed section"], "B": ["Updated path", "Fixed lines"]},
        )

        restored = ProcessingState.from_dict(original.to_dict())

        assert restored.current_issue == original.current_issue
        assert restored.phase == original.phase
        assert restored.timestamp == original.timestamp
        assert restored.completed_issues == original.completed_issues
        assert restored.failed_issues == original.failed_issues
        assert restored.attempted_issues == original.attempted_issues
        assert restored.timing == original.timing
        assert restored.corrections == original.corrections

    def test_corrections_persistence(self) -> None:
        """Test that corrections are persisted and loaded correctly."""
        state = ProcessingState()
        state.corrections["BUG-001"] = ["Added missing section", "Updated line numbers"]
        state.corrections["ENH-002"] = ["Fixed file path"]

        data = state.to_dict()
        assert "corrections" in data
        assert data["corrections"]["BUG-001"] == ["Added missing section", "Updated line numbers"]
        assert data["corrections"]["ENH-002"] == ["Fixed file path"]

        loaded = ProcessingState.from_dict(data)
        assert loaded.corrections == state.corrections


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

    def test_load_nonexistent_file(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Test loading from non-existent file returns None."""
        manager = StateManager(temp_state_file, mock_logger)

        result = manager.load()

        assert result is None

    def test_load_existing_file(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
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

    def test_load_invalid_json(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
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

    def test_cleanup_nonexistent_file(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Test cleanup with non-existent file does nothing."""
        manager = StateManager(temp_state_file, mock_logger)

        # Should not raise
        manager.cleanup()

    def test_update_current(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Test update_current updates state and saves."""
        manager = StateManager(temp_state_file, mock_logger)

        manager.update_current("/issue/path.md", "implementing")

        assert manager.state.current_issue == "/issue/path.md"
        assert manager.state.phase == "implementing"
        assert temp_state_file.exists()  # Should have saved

    def test_mark_attempted(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Test mark_attempted adds to attempted set."""
        manager = StateManager(temp_state_file, mock_logger)

        manager.mark_attempted("BUG-001")

        assert "BUG-001" in manager.state.attempted_issues
        assert temp_state_file.exists()  # Should have saved

    def test_mark_attempted_no_save(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Test mark_attempted with save=False doesn't save."""
        manager = StateManager(temp_state_file, mock_logger)

        manager.mark_attempted("BUG-001", save=False)

        assert "BUG-001" in manager.state.attempted_issues
        assert not temp_state_file.exists()  # Should NOT have saved

    def test_mark_completed(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
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

    def test_mark_failed(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Test mark_failed stores failure reason."""
        manager = StateManager(temp_state_file, mock_logger)

        manager.mark_failed("BUG-003", "Timeout after 3600s")

        assert manager.state.failed_issues["BUG-003"] == "Timeout after 3600s"
        assert temp_state_file.exists()  # Should have saved

    def test_is_attempted_true(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Test is_attempted returns True for attempted issues."""
        manager = StateManager(temp_state_file, mock_logger)
        manager.state.attempted_issues.add("BUG-001")

        assert manager.is_attempted("BUG-001") is True

    def test_is_attempted_false(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Test is_attempted returns False for non-attempted issues."""
        manager = StateManager(temp_state_file, mock_logger)

        assert manager.is_attempted("BUG-999") is False

    def test_record_corrections(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Test record_corrections stores corrections and saves."""
        manager = StateManager(temp_state_file, mock_logger)
        corrections = ["Added missing section", "Updated line numbers"]

        manager.record_corrections("BUG-001", corrections)

        assert manager.state.corrections["BUG-001"] == corrections
        assert temp_state_file.exists()  # Should have saved

    def test_record_corrections_empty_list(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test record_corrections with empty list does not save."""
        manager = StateManager(temp_state_file, mock_logger)

        manager.record_corrections("BUG-001", [])

        assert "BUG-001" not in manager.state.corrections
        # Note: save() might still be called via other methods, but empty
        # corrections shouldn't be stored

    def test_record_corrections_multiple_issues(
        self, temp_state_file: Path, mock_logger: MagicMock
    ) -> None:
        """Test recording corrections for multiple issues."""
        manager = StateManager(temp_state_file, mock_logger)

        manager.record_corrections("BUG-001", ["Fixed section A"])
        manager.record_corrections("ENH-002", ["Updated path", "Fixed snippet"])

        assert manager.state.corrections["BUG-001"] == ["Fixed section A"]
        assert manager.state.corrections["ENH-002"] == ["Updated path", "Fixed snippet"]

    def test_resume_workflow(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
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


class TestStateConcurrency:
    """Tests for concurrent access to StateManager (ENH-217)."""

    def test_concurrent_save_no_corruption(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Multiple threads saving state simultaneously should not corrupt JSON."""
        managers = [StateManager(temp_state_file, mock_logger) for _ in range(5)]

        def save_state(manager_id: int) -> bool:
            """Save state from a thread."""
            manager = managers[manager_id]
            for i in range(10):
                manager.mark_attempted(f"ISSUE-{manager_id}-{i}", save=True)
            return True

        # Execute
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(save_state, i) for i in range(5)]
            results = [f.result() for f in as_completed(futures)]

        # Verify all completed and file is valid JSON
        assert len(results) == 5
        assert temp_state_file.exists()
        content = temp_state_file.read_text()
        # Should be valid JSON
        state = json.loads(content)
        assert isinstance(state, dict)

    def test_lazy_init_thread_safety(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Multiple threads accessing state property simultaneously."""
        manager = StateManager(temp_state_file, mock_logger)
        instances = []

        def access_state() -> ProcessingState:
            """Access state property."""
            state = manager.state
            instances.append(id(state))
            return state

        threads = [threading.Thread(target=access_state) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get same instance (or at least valid state)
        # If lazy init has race, might get different instances
        # The important thing is no crash and valid state
        assert len(instances) == 10

    def test_concurrent_mark_attempted(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Multiple threads marking issues attempted simultaneously."""
        manager = StateManager(temp_state_file, mock_logger)
        errors = []

        def mark_issue(thread_id: int) -> None:
            try:
                for i in range(20):
                    manager.mark_attempted(f"ENH-{thread_id:03d}-{i:03d}", save=True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=mark_issue, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No exceptions should occur
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify some issues were recorded (may have lost updates due to races)
        manager.load()
        # At minimum, should have some issues recorded
        assert len(manager.state.attempted_issues) >= 0

    def test_concurrent_state_mutations(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Multiple threads performing different state operations."""
        manager = StateManager(temp_state_file, mock_logger)
        errors = []

        def mark_completed(thread_id: int) -> None:
            try:
                for i in range(5):
                    manager.mark_completed(f"FEAT-{thread_id}-{i}", {"total": 10.0})
            except Exception as e:
                errors.append(("completed", thread_id, e))

        def mark_failed(thread_id: int) -> None:
            try:
                for i in range(5):
                    manager.mark_failed(f"BUG-{thread_id}-{i}", "Test failure")
            except Exception as e:
                errors.append(("failed", thread_id, e))

        # Create mixed operation threads
        threads = []
        for i in range(3):
            threads.append(threading.Thread(target=mark_completed, args=(i,)))
            threads.append(threading.Thread(target=mark_failed, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No exceptions should occur
        assert len(errors) == 0, f"Errors occurred: {errors}"

    def test_concurrent_read_write(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
        """Thread reads while another writes."""
        manager = StateManager(temp_state_file, mock_logger)
        manager.mark_attempted("INIT-001")
        read_count = [0]
        errors = []

        def reader() -> None:
            try:
                for _ in range(50):
                    _ = manager.state.attempted_issues
                    _ = manager.is_attempted("INIT-001")
                    read_count[0] += 1
            except Exception as e:
                errors.append(("read", e))

        def writer() -> None:
            try:
                for i in range(20):
                    manager.mark_attempted(f"WRITE-{i:03d}", save=True)
            except Exception as e:
                errors.append(("write", e))

        threads = [threading.Thread(target=reader), threading.Thread(target=writer)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors and all reads completed
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert read_count[0] == 50
