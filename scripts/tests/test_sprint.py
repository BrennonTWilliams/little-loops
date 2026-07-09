"""Tests for sprint module."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from little_loops.config import BRConfig
from little_loops.sprint import Sprint, SprintManager, SprintOptions, SprintState


class TestSprintOptions:
    """Tests for SprintOptions dataclass."""

    def test_default_values(self) -> None:
        """Default values are correct."""
        options = SprintOptions()
        assert options.max_iterations == 100
        assert options.timeout == 3600
        assert options.max_workers == 2

    def test_custom_values(self) -> None:
        """Custom values are set correctly."""
        options = SprintOptions(
            max_iterations=200,
            timeout=7200,
            max_workers=8,
        )
        assert options.max_iterations == 200
        assert options.timeout == 7200
        assert options.max_workers == 8

    def test_to_dict(self) -> None:
        """Serialization to dict works."""
        options = SprintOptions(max_workers=8)
        data = options.to_dict()
        assert data == {
            "max_iterations": 100,
            "timeout": 3600,
            "max_workers": 8,
        }

    def test_from_dict(self) -> None:
        """Deserialization from dict works."""
        data = {
            "max_iterations": 200,
            "timeout": 7200,
            "max_workers": 8,
        }
        options = SprintOptions.from_dict(data)
        assert options.max_iterations == 200
        assert options.timeout == 7200
        assert options.max_workers == 8

    def test_from_dict_none(self) -> None:
        """None input returns defaults."""
        options = SprintOptions.from_dict(None)
        assert options.max_workers == 2


class TestSprint:
    """Tests for Sprint dataclass."""

    def test_creation(self) -> None:
        """Sprint can be created with required fields."""
        sprint = Sprint(
            name="test-sprint",
            description="Test sprint",
            issues=["BUG-001", "FEAT-010"],
            created="2026-01-14T00:00:00Z",
        )
        assert sprint.name == "test-sprint"
        assert sprint.description == "Test sprint"
        assert sprint.issues == ["BUG-001", "FEAT-010"]
        assert sprint.options is None

    def test_with_options(self) -> None:
        """Sprint can include options."""
        options = SprintOptions(max_workers=8)
        sprint = Sprint(
            name="test-sprint",
            description="Test sprint",
            issues=["BUG-001"],
            created="2026-01-14T00:00:00Z",
            options=options,
        )
        assert sprint.options is not None
        assert sprint.options.max_workers == 8

    def test_to_dict(self) -> None:
        """Serialization includes all fields."""
        options = SprintOptions(max_workers=8)
        sprint = Sprint(
            name="test-sprint",
            description="Test",
            issues=["BUG-001"],
            created="2026-01-14T00:00:00Z",
            options=options,
        )
        data = sprint.to_dict()
        assert data["name"] == "test-sprint"
        assert data["description"] == "Test"
        assert data["issues"] == ["BUG-001"]
        assert data["options"]["max_workers"] == 8

    def test_to_dict_no_options(self) -> None:
        """Serialization without options omits options key."""
        sprint = Sprint(
            name="test-sprint",
            description="Test",
            issues=["BUG-001"],
            created="2026-01-14T00:00:00Z",
        )
        data = sprint.to_dict()
        assert "options" not in data

    def test_from_dict(self) -> None:
        """Deserialization from dict works."""
        data = {
            "name": "test-sprint",
            "description": "Test sprint",
            "issues": ["BUG-001", "FEAT-010"],
            "created": "2026-01-14T00:00:00Z",
            "options": {
                "max_workers": 8,
            },
        }
        sprint = Sprint.from_dict(data)
        assert sprint.name == "test-sprint"
        assert sprint.issues == ["BUG-001", "FEAT-010"]
        assert sprint.options is not None
        assert sprint.options.max_workers == 8

    def test_from_dict_defaults(self) -> None:
        """Deserialization fills in missing fields."""
        data = {
            "name": "test-sprint",
            "issues": ["BUG-001"],
        }
        sprint = Sprint.from_dict(data)
        assert sprint.name == "test-sprint"
        assert sprint.description == ""
        assert sprint.issues == ["BUG-001"]
        # When no options provided, defaults are applied
        assert sprint.options is not None
        assert sprint.options.max_workers == 2

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Save and load round-trip works."""
        sprint = Sprint(
            name="test-sprint",
            description="Test sprint",
            issues=["BUG-001", "FEAT-010"],
            created="2026-01-14T00:00:00Z",
            options=SprintOptions(max_workers=8),
        )

        # Save
        saved_path = sprint.save(tmp_path)
        assert saved_path.exists()
        assert saved_path.name == "test-sprint.yaml"

        # Load
        loaded = Sprint.load(tmp_path, "test-sprint")
        assert loaded is not None
        assert loaded.name == "test-sprint"
        assert loaded.issues == ["BUG-001", "FEAT-010"]
        assert loaded.options is not None
        assert loaded.options.max_workers == 8

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        """Loading non-existent sprint returns None."""
        loaded = Sprint.load(tmp_path, "nonexistent")
        assert loaded is None


class TestSprintManager:
    """Tests for SprintManager."""

    def test_init_default_dir(self, tmp_path: Path) -> None:
        """Default initialization creates .sprints directory."""
        manager = SprintManager(sprints_dir=tmp_path / ".sprints")
        assert manager.sprints_dir.exists()
        assert manager.sprints_dir.is_dir()

    def test_create_sprint(self, tmp_path: Path) -> None:
        """Creating a sprint writes YAML file."""
        manager = SprintManager(sprints_dir=tmp_path)
        sprint = manager.create(
            name="test-sprint",
            issues=["BUG-001", "FEAT-010"],
            description="Test sprint",
        )

        assert sprint.name == "test-sprint"
        assert sprint.issues == ["BUG-001", "FEAT-010"]

        # Verify file exists
        sprint_path = tmp_path / "test-sprint.yaml"
        assert sprint_path.exists()

    def test_load_sprint(self, tmp_path: Path) -> None:
        """Loading a sprint reads YAML file."""
        manager = SprintManager(sprints_dir=tmp_path)

        # Create first
        manager.create(
            name="test-sprint",
            issues=["BUG-001"],
            description="Test",
        )

        # Then load
        loaded = manager.load("test-sprint")
        assert loaded is not None
        assert loaded.name == "test-sprint"
        assert loaded.issues == ["BUG-001"]

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        """Loading non-existent sprint returns None."""
        manager = SprintManager(sprints_dir=tmp_path)
        loaded = manager.load("nonexistent")
        assert loaded is None

    def test_list_empty(self, tmp_path: Path) -> None:
        """Listing empty directory returns empty list."""
        manager = SprintManager(sprints_dir=tmp_path)
        sprints = manager.list_all()
        assert sprints == []

    def test_list_multiple(self, tmp_path: Path) -> None:
        """Listing returns all sprints sorted by name."""
        manager = SprintManager(sprints_dir=tmp_path)

        manager.create(name="zebra", issues=["BUG-003"])
        manager.create(name="alpha", issues=["BUG-001"])
        manager.create(name="beta", issues=["BUG-002"])

        sprints = manager.list_all()
        assert [s.name for s in sprints] == ["alpha", "beta", "zebra"]

    def test_delete_sprint(self, tmp_path: Path) -> None:
        """Deleting a sprint removes the file."""
        manager = SprintManager(sprints_dir=tmp_path)

        manager.create(name="test-sprint", issues=["BUG-001"])
        assert (tmp_path / "test-sprint.yaml").exists()

        result = manager.delete("test-sprint")
        assert result is True
        assert not (tmp_path / "test-sprint.yaml").exists()

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        """Deleting non-existent sprint returns False."""
        manager = SprintManager(sprints_dir=tmp_path)
        result = manager.delete("nonexistent")
        assert result is False

    def test_create_normalizes_issue_ids(self, tmp_path: Path) -> None:
        """Issue IDs are normalized to uppercase."""
        manager = SprintManager(sprints_dir=tmp_path)
        sprint = manager.create(
            name="test",
            issues=["bug-001", "FeAt-010"],  # Mixed case
        )
        assert sprint.issues == ["BUG-001", "FEAT-010"]

    def test_validate_issues_without_config(self, tmp_path: Path) -> None:
        """Validation without config returns empty dict."""
        manager = SprintManager(sprints_dir=tmp_path, config=None)
        valid = manager.validate_issues(["BUG-001", "FEAT-010"])
        assert valid == {}

    def test_load_issue_infos_without_config(self, tmp_path: Path) -> None:
        """Loading issue infos without config returns empty list."""
        manager = SprintManager(sprints_dir=tmp_path, config=None)
        infos = manager.load_issue_infos(["BUG-001", "FEAT-010"])
        assert infos == []

    def test_load_issue_infos_logs_warning_on_parse_failure(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Unparseable issue files are logged as warnings instead of silently dropped."""
        from unittest.mock import patch

        # Set up project structure with config
        issues_dir = tmp_path / ".issues"
        for category in ["bugs", "features", "enhancements", "completed"]:
            (issues_dir / category).mkdir(parents=True, exist_ok=True)

        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "ll-config.json"
        config_data = {
            "project": {"name": "test-project", "src_dir": "src/"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    "enhancements": {
                        "prefix": "ENH",
                        "dir": "enhancements",
                        "action": "improve",
                    },
                },
                "completed_dir": "completed",
            },
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Create an issue file that exists on disk (so glob finds it)
        issue_file = issues_dir / "bugs" / "P3-BUG-999-corrupted.md"
        issue_file.write_text("# BUG-999: Test\n")

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=tmp_path, config=config)

        # Mock parse_file to raise, simulating a corrupted/unparseable file
        with (
            patch(
                "little_loops.issue_parser.IssueParser.parse_file",
                side_effect=ValueError("corrupted file"),
            ),
            caplog.at_level("WARNING", logger="little_loops.sprint"),
        ):
            infos = manager.load_issue_infos(["BUG-999"])

        assert infos == []
        assert "Failed to parse issue file" in caplog.text
        assert "corrupted file" in caplog.text

    def test_validate_issues_respects_custom_categories(self, tmp_path: Path) -> None:
        """validate_issues finds issues in custom category directories."""
        issues_dir = tmp_path / ".issues"
        for category in ["bugs", "tasks", "completed"]:
            (issues_dir / category).mkdir(parents=True, exist_ok=True)

        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
        config_data = {
            "project": {"name": "test-project", "src_dir": "src/"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "tasks": {"prefix": "TASK", "dir": "tasks", "action": "implement"},
                },
                "completed_dir": "completed",
            },
        }
        (config_dir / "ll-config.json").write_text(json.dumps(config_data))

        # Issue in custom category "tasks"
        (issues_dir / "tasks" / "P3-TASK-001-my-task.md").write_text("# TASK-001: My Task\n")

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=tmp_path, config=config)

        valid = manager.validate_issues(["TASK-001"])
        assert "TASK-001" in valid

    def test_load_issue_infos_respects_custom_categories(self, tmp_path: Path) -> None:
        """load_issue_infos finds and parses issues in custom category directories."""
        issues_dir = tmp_path / ".issues"
        for category in ["bugs", "tasks", "completed"]:
            (issues_dir / category).mkdir(parents=True, exist_ok=True)

        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
        config_data = {
            "project": {"name": "test-project", "src_dir": "src/"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "tasks": {"prefix": "TASK", "dir": "tasks", "action": "implement"},
                },
                "completed_dir": "completed",
            },
        }
        (config_dir / "ll-config.json").write_text(json.dumps(config_data))

        # Issue in custom category "tasks"
        (issues_dir / "tasks" / "P3-TASK-001-my-task.md").write_text(
            "# TASK-001: My Task\n\n## Summary\nA task to complete.\n"
        )

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=tmp_path, config=config)

        infos = manager.load_issue_infos(["TASK-001"])
        assert len(infos) == 1
        assert infos[0].issue_id == "TASK-001"


class TestSprintYAMLFormat:
    """Tests for YAML file format."""

    def test_yaml_format_matches_spec(self, tmp_path: Path) -> None:
        """YAML output matches specification format."""
        manager = SprintManager(sprints_dir=tmp_path)

        manager.create(
            name="sprint-1",
            issues=["BUG-001", "BUG-002"],
            description="Q1 Performance and Security Improvements",
        )

        yaml_path = tmp_path / "sprint-1.yaml"
        content = yaml_path.read_text()

        # Verify structure matches spec
        assert "name: sprint-1" in content
        assert "description: Q1 Performance and Security Improvements" in content
        assert "issues:" in content
        assert "- BUG-001" in content
        assert "- BUG-002" in content
        assert "created:" in content

        # Parse and verify structure
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        assert data["name"] == "sprint-1"
        assert data["description"] == "Q1 Performance and Security Improvements"
        assert data["issues"] == ["BUG-001", "BUG-002"]
        assert "created" in data

    def test_yaml_with_options(self, tmp_path: Path) -> None:
        """YAML with options includes options section."""
        manager = SprintManager(sprints_dir=tmp_path)

        options = SprintOptions(max_workers=8)
        manager.create(
            name="sprint-1",
            issues=["BUG-001"],
            options=options,
        )

        yaml_path = tmp_path / "sprint-1.yaml"
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        assert "options" in data
        assert data["options"]["max_workers"] == 8


class TestSprintState:
    """Tests for SprintState dataclass."""

    def test_default_values(self) -> None:
        """SprintState has correct default values."""
        state = SprintState()

        assert state.sprint_name == ""
        assert state.current_wave == 0
        assert state.completed_issues == []
        assert state.failed_issues == {}
        assert state.timing == {}
        assert state.started_at == ""
        assert state.last_checkpoint == ""

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        state = SprintState(
            sprint_name="test-sprint",
            current_wave=2,
            completed_issues=["BUG-001", "FEAT-002"],
            failed_issues={"BUG-003": "Timeout"},
            timing={"BUG-001": {"total": 120.5}},
            started_at="2026-01-29T10:00:00",
            last_checkpoint="2026-01-29T10:30:00",
        )

        result = state.to_dict()

        assert result["sprint_name"] == "test-sprint"
        assert result["current_wave"] == 2
        assert result["completed_issues"] == ["BUG-001", "FEAT-002"]
        assert result["failed_issues"] == {"BUG-003": "Timeout"}
        assert result["timing"] == {"BUG-001": {"total": 120.5}}
        assert result["started_at"] == "2026-01-29T10:00:00"
        assert result["last_checkpoint"] == "2026-01-29T10:30:00"

    def test_to_dict_json_serializable(self) -> None:
        """Test that to_dict output is JSON serializable."""
        state = SprintState(
            sprint_name="test",
            current_wave=1,
            completed_issues=["A"],
        )

        result = state.to_dict()
        # Should not raise
        json.dumps(result)

    def test_from_dict(self) -> None:
        """Test deserialization from dictionary."""
        data = {
            "sprint_name": "my-sprint",
            "current_wave": 3,
            "completed_issues": ["FEAT-001"],
            "failed_issues": {"FEAT-002": "Error"},
            "timing": {"FEAT-001": {"ready": 10.0}},
            "started_at": "2026-01-29T09:00:00",
            "last_checkpoint": "2026-01-29T09:45:00",
        }

        state = SprintState.from_dict(data)

        assert state.sprint_name == "my-sprint"
        assert state.current_wave == 3
        assert state.completed_issues == ["FEAT-001"]
        assert state.failed_issues == {"FEAT-002": "Error"}
        assert state.timing == {"FEAT-001": {"ready": 10.0}}
        assert state.started_at == "2026-01-29T09:00:00"
        assert state.last_checkpoint == "2026-01-29T09:45:00"

    def test_from_dict_with_defaults(self) -> None:
        """Test from_dict with missing keys uses defaults."""
        data = {"sprint_name": "partial"}

        state = SprintState.from_dict(data)

        assert state.sprint_name == "partial"
        assert state.current_wave == 0
        assert state.completed_issues == []
        assert state.failed_issues == {}
        assert state.timing == {}
        assert state.started_at == ""
        assert state.last_checkpoint == ""

    def test_roundtrip_serialization(self) -> None:
        """Test roundtrip through to_dict and from_dict."""
        original = SprintState(
            sprint_name="roundtrip-test",
            current_wave=2,
            completed_issues=["A", "B"],
            failed_issues={"C": "error"},
            timing={"A": {"total": 50.0}},
            started_at="2026-01-29T08:00:00",
            last_checkpoint="2026-01-29T08:30:00",
        )

        restored = SprintState.from_dict(original.to_dict())

        assert restored.sprint_name == original.sprint_name
        assert restored.current_wave == original.current_wave
        assert restored.completed_issues == original.completed_issues
        assert restored.failed_issues == original.failed_issues
        assert restored.timing == original.timing
        assert restored.started_at == original.started_at
        assert restored.last_checkpoint == original.last_checkpoint

    def test_file_roundtrip(self, tmp_path: Path) -> None:
        """Test roundtrip through JSON file."""
        state = SprintState(
            sprint_name="file-test",
            current_wave=1,
            completed_issues=["BUG-001"],
            failed_issues={"BUG-002": "Failed"},
            timing={"BUG-001": {"total": 100.0}},
            started_at="2026-01-29T10:00:00",
            last_checkpoint="2026-01-29T10:05:00",
        )

        # Write to file
        state_file = tmp_path / ".sprint-state.json"
        state_file.write_text(json.dumps(state.to_dict(), indent=2))

        # Read back
        data = json.loads(state_file.read_text())
        restored = SprintState.from_dict(data)

        assert restored.sprint_name == state.sprint_name
        assert restored.current_wave == state.current_wave
        assert restored.completed_issues == state.completed_issues
        assert restored.failed_issues == state.failed_issues


class TestSprintSignalHandler:
    """Tests for sprint signal handling (ENH-183)."""

    def test_signal_handler_sets_flag(self) -> None:
        """First signal sets shutdown flag."""
        import signal

        import little_loops.cli.sprint.run as sprint_run

        # Reset state
        sprint_run._sprint_shutdown_requested = False

        # Call handler (simulating SIGINT)
        sprint_run._sprint_signal_handler(signal.SIGINT, None)

        assert sprint_run._sprint_shutdown_requested is True

    def test_signal_handler_second_signal_exits(self) -> None:
        """Second signal raises SystemExit."""
        import signal

        import pytest

        import little_loops.cli.sprint.run as sprint_run

        # Set flag as if first signal received
        sprint_run._sprint_shutdown_requested = True

        # Second signal should exit
        with pytest.raises(SystemExit) as exc_info:
            sprint_run._sprint_signal_handler(signal.SIGINT, None)

        assert exc_info.value.code == 1

    def test_signal_handler_uses_logger_when_set(self) -> None:
        """Signal handler routes output through _sprint_logger when available."""
        import signal
        from unittest.mock import MagicMock

        import little_loops.cli.sprint.run as sprint_run

        mock_logger = MagicMock()
        sprint_run._sprint_shutdown_requested = False
        sprint_run._sprint_logger = mock_logger

        try:
            sprint_run._sprint_signal_handler(signal.SIGINT, None)
        finally:
            sprint_run._sprint_logger = None

        mock_logger.warning.assert_called_once()
        assert sprint_run._sprint_shutdown_requested is True

    def test_signal_handler_falls_back_to_print_when_no_logger(self, capsys: Any) -> None:
        """Signal handler falls back to print() when _sprint_logger is None."""
        import signal

        import little_loops.cli.sprint.run as sprint_run

        sprint_run._sprint_shutdown_requested = False
        sprint_run._sprint_logger = None

        sprint_run._sprint_signal_handler(signal.SIGINT, None)

        captured = capsys.readouterr()
        assert "Shutdown requested" in captured.err


class TestSprintErrorHandling:
    """Tests for _cmd_sprint_run error handling wrapper (ENH-185)."""

    @staticmethod
    def _setup_test_project(tmp_path: Path) -> tuple[Path, Any, Any]:
        """Set up a test project with config, issues, and sprint."""
        from little_loops.config import BRConfig
        from little_loops.sprint import SprintManager

        # Create directory structure
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)

        for category in ["bugs", "features", "enhancements", "completed"]:
            (issues_dir / category).mkdir(exist_ok=True)

        # Create config
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)

        config_file = config_dir / "ll-config.json"
        config_data = {
            "project": {
                "name": "test-project",
                "src_dir": "src/",
                "test_cmd": "pytest",
                "lint_cmd": "ruff check",
            },
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
                },
                "completed_dir": "completed",
            },
        }

        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Create sample issue
        (issues_dir / "bugs" / "P1-BUG-001-test-bug.md").write_text(
            "# BUG-001: Test Bug\n\n## Summary\nFix this bug."
        )

        # Create sprint file
        sprints_dir = tmp_path / "sprints"
        sprints_dir.mkdir(exist_ok=True)
        sprint_file = sprints_dir / "test.yaml"
        sprint_file.write_text(
            """name: test-sprint
issues:
  - BUG-001
"""
        )

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)

        return sprints_dir, config, manager

    def test_keyboard_interrupt_returns_130(self, tmp_path: Path, monkeypatch: Any) -> None:
        """KeyboardInterrupt during wave processing returns exit code 130."""
        import argparse

        import little_loops.cli.sprint.run as sprint_run

        sprints_dir, config, manager = self._setup_test_project(tmp_path)

        args = argparse.Namespace(
            sprint="test",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=1,
            quiet=False,
        )

        # Mock process_issue_inplace to raise KeyboardInterrupt
        def raise_keyboard_interrupt(*args: Any, **kwargs: Any) -> None:
            raise KeyboardInterrupt()

        monkeypatch.setattr(
            "little_loops.cli.sprint.run.process_issue_inplace",
            raise_keyboard_interrupt,
        )

        # Change to tmp_path so state file is created there
        monkeypatch.chdir(tmp_path)

        # Reset shutdown flag
        sprint_run._sprint_shutdown_requested = False

        # Run and check exit code
        result = sprint_run._cmd_sprint_run(args, manager, config)
        assert result == 130

    def test_unexpected_exception_returns_1(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Unexpected exception during wave processing returns exit code 1."""
        import argparse

        import little_loops.cli.sprint.run as sprint_run

        sprints_dir, config, manager = self._setup_test_project(tmp_path)

        args = argparse.Namespace(
            sprint="test",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=1,
            quiet=False,
        )

        # Mock process_issue_inplace to raise RuntimeError
        def raise_runtime_error(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Unexpected test error")

        monkeypatch.setattr(
            "little_loops.cli.sprint.run.process_issue_inplace",
            raise_runtime_error,
        )

        # Change to tmp_path so state file is created there
        monkeypatch.chdir(tmp_path)

        # Reset shutdown flag
        sprint_run._sprint_shutdown_requested = False

        # Run and check exit code
        result = sprint_run._cmd_sprint_run(args, manager, config)
        assert result == 1

    def test_exception_saves_state(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Exception during processing saves state before exit."""
        import argparse

        import little_loops.cli.sprint.run as sprint_run

        sprints_dir, config, manager = self._setup_test_project(tmp_path)

        args = argparse.Namespace(
            sprint="test",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=1,
            quiet=False,
        )

        # Mock process_issue_inplace to raise RuntimeError
        def raise_runtime_error(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Test error for state save")

        monkeypatch.setattr(
            "little_loops.cli.sprint.run.process_issue_inplace",
            raise_runtime_error,
        )

        # Change to tmp_path so state file is created there
        monkeypatch.chdir(tmp_path)

        # Reset shutdown flag
        sprint_run._sprint_shutdown_requested = False

        # Run the function
        sprint_run._cmd_sprint_run(args, manager, config)

        # Check that state file was created
        state_file = tmp_path / ".sprint-state.json"
        assert state_file.exists(), "State file should be saved on exception"

        # Verify state content — sprint_name matches sprint.name (canonical), not args.sprint
        state_data = json.loads(state_file.read_text())
        assert state_data["sprint_name"] == "test-sprint"
        assert "last_checkpoint" in state_data


class TestSprintDependencyAnalysis:
    """Tests for dependency analysis integration in sprint commands (ENH-301)."""

    @staticmethod
    def _setup_overlapping_issues(tmp_path: Path) -> tuple[Any, Any, Any]:
        """Create two issues that reference the same file."""
        from little_loops.config import BRConfig
        from little_loops.sprint import SprintManager

        # Create directory structure
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)
        for category in ["bugs", "features", "enhancements", "completed"]:
            (issues_dir / category).mkdir(exist_ok=True)

        # Create config
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "ll-config.json"
        config_data = {
            "project": {
                "name": "test-project",
                "src_dir": "src/",
                "test_cmd": "pytest",
                "lint_cmd": "ruff check",
            },
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {
                        "prefix": "FEAT",
                        "dir": "features",
                        "action": "implement",
                    },
                    "enhancements": {
                        "prefix": "ENH",
                        "dir": "enhancements",
                        "action": "improve",
                    },
                },
                "completed_dir": "completed",
            },
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Create two issues that reference the same file
        (issues_dir / "bugs" / "P1-BUG-001-fix-config.md").write_text(
            "# BUG-001: Fix config parsing\n\n"
            "## Summary\nFix bug in config module.\n\n"
            "### Files to Modify\n- `scripts/config.py`\n\n"
            "## Blocked By\n\nNone\n\n"
            "## Blocks\n\nNone\n"
        )
        (issues_dir / "features" / "P2-FEAT-001-add-config-validation.md").write_text(
            "# FEAT-001: Add config validation\n\n"
            "## Summary\nAdd validation to config module.\n\n"
            "### Files to Modify\n- `scripts/config.py`\n\n"
            "## Blocked By\n\nNone\n\n"
            "## Blocks\n\nNone\n"
        )

        # Create sprint
        sprints_dir = tmp_path / "sprints"
        sprints_dir.mkdir(exist_ok=True)
        sprint_file = sprints_dir / "overlap-test.yaml"
        sprint_file.write_text("name: overlap-test\nissues:\n  - BUG-001\n  - FEAT-001\n")

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)
        return sprints_dir, config, manager

    def test_run_shows_dependency_analysis(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """Sprint run displays dependency analysis when issues have file overlaps."""
        import argparse

        from little_loops.cli import sprint as cli
        from little_loops.issue_manager import IssueProcessingResult

        _, config, manager = self._setup_overlapping_issues(tmp_path)

        def mock_process_inplace(info: Any, **kwargs: Any) -> IssueProcessingResult:
            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        monkeypatch.setattr(
            "little_loops.cli.sprint.run.process_issue_inplace", mock_process_inplace
        )
        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="overlap-test",
            dry_run=True,
            resume=False,
            skip=None,
            max_workers=1,
            quiet=False,
            skip_analysis=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 0

        captured = capsys.readouterr()
        # The analysis ran (whether it found proposals depends on content,
        # but the code path was exercised without error)
        assert "Dry run mode" in captured.out

    def test_run_skip_analysis_flag(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Sprint run with --skip-analysis skips dependency analysis."""
        import argparse

        from little_loops.cli import sprint as cli
        from little_loops.issue_manager import IssueProcessingResult

        _, config, manager = self._setup_overlapping_issues(tmp_path)

        def mock_process_inplace(info: Any, **kwargs: Any) -> IssueProcessingResult:
            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        monkeypatch.setattr(
            "little_loops.cli.sprint.run.process_issue_inplace", mock_process_inplace
        )
        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="overlap-test",
            dry_run=True,
            resume=False,
            skip=None,
            max_workers=1,
            quiet=False,
            skip_analysis=True,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 0

        captured = capsys.readouterr()
        # Analysis section should NOT appear when skipped
        assert "Dependency Analysis" not in captured.out

    def test_show_includes_dependency_analysis(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """Sprint show runs dependency analysis."""
        import argparse

        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_overlapping_issues(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="overlap-test",
            config=None,
            skip_analysis=False,
        )

        result = cli._cmd_sprint_show(args, manager)
        assert result == 0

        captured = capsys.readouterr()
        assert "Sprint: overlap-test" in captured.out

    def test_show_skip_analysis_flag(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Sprint show with --skip-analysis skips dependency analysis."""
        import argparse

        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_overlapping_issues(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="overlap-test",
            config=None,
            skip_analysis=True,
        )

        result = cli._cmd_sprint_show(args, manager)
        assert result == 0

        captured = capsys.readouterr()
        assert "Sprint: overlap-test" in captured.out
        assert "Dependency Analysis" not in captured.out

    def test_show_color_output(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Sprint show output contains ANSI codes when _USE_COLOR is True."""
        import argparse
        from unittest.mock import patch

        import little_loops.cli.output as output_mod
        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_overlapping_issues(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="overlap-test",
            config=None,
            skip_analysis=True,
        )

        with patch.object(output_mod, "_USE_COLOR", True):
            result = cli._cmd_sprint_show(args, manager)

        assert result == 0
        captured = capsys.readouterr()
        assert "\033[" in captured.out

    def test_show_no_color_output(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Sprint show output contains no ANSI codes when _USE_COLOR is False."""
        import argparse
        from unittest.mock import patch

        import little_loops.cli.output as output_mod
        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_overlapping_issues(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="overlap-test",
            config=None,
            skip_analysis=True,
        )

        with patch.object(output_mod, "_USE_COLOR", False):
            result = cli._cmd_sprint_show(args, manager)

        assert result == 0
        captured = capsys.readouterr()
        assert "\033[" not in captured.out

    def test_show_omits_empty_description(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """Sprint show omits Description line when description is empty."""
        import argparse
        from unittest.mock import patch

        import little_loops.cli.output as output_mod
        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_overlapping_issues(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="overlap-test",
            config=None,
            skip_analysis=True,
        )

        with patch.object(output_mod, "_USE_COLOR", False):
            result = cli._cmd_sprint_show(args, manager)

        assert result == 0
        captured = capsys.readouterr()
        assert "Sprint: overlap-test" in captured.out
        assert "Description:" not in captured.out

    def test_show_human_friendly_timestamp(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """Sprint show formats timestamps in human-friendly form."""
        import argparse
        from unittest.mock import patch

        import little_loops.cli.output as output_mod
        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_overlapping_issues(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="overlap-test",
            config=None,
            skip_analysis=True,
        )

        with patch.object(output_mod, "_USE_COLOR", False):
            result = cli._cmd_sprint_show(args, manager)

        assert result == 0
        captured = capsys.readouterr()
        # Should contain formatted date (YYYY-MM-DD HH:MM UTC) rather than raw ISO with microseconds
        assert "Created:" in captured.out
        # Raw ISO with microseconds or +00:00 should NOT appear
        created_line = [line for line in captured.out.splitlines() if "Created:" in line][0]
        assert "+00:00" not in created_line or "UTC" in created_line

    def test_show_composition_line(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Sprint show displays composition breakdown after health summary."""
        import argparse
        from unittest.mock import patch

        import little_loops.cli.output as output_mod
        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_overlapping_issues(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="overlap-test",
            config=None,
            skip_analysis=True,
        )

        with patch.object(output_mod, "_USE_COLOR", False):
            result = cli._cmd_sprint_show(args, manager)

        assert result == 0
        captured = capsys.readouterr()
        assert "Composition:" in captured.out

    def test_show_lighter_separators(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Sprint show uses lighter ── separators instead of === banners."""
        import argparse
        from unittest.mock import patch

        import little_loops.cli.output as output_mod
        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_overlapping_issues(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="overlap-test",
            config=None,
            skip_analysis=True,
        )

        with patch.object(output_mod, "_USE_COLOR", False):
            result = cli._cmd_sprint_show(args, manager)

        assert result == 0
        captured = capsys.readouterr()
        assert "===" not in captured.out
        assert "\u2500\u2500" in captured.out  # ── chars present

    def test_show_wider_title(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Sprint show does not truncate titles at 45 chars when terminal is wide."""
        import argparse
        from unittest.mock import patch

        import little_loops.cli.output as output_mod
        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_overlapping_issues(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Replace a title with a long one (> 45 chars)
        long_title = "A" * 55
        issue_file = tmp_path / ".issues" / "bugs" / "P1-BUG-001-fix-config.md"
        issue_file.write_text(
            f"# BUG-001: {long_title}\n\n"
            "## Summary\nFix bug in config module.\n\n"
            "### Files to Modify\n- `scripts/config.py`\n\n"
            "## Blocked By\n\nNone\n\n"
            "## Blocks\n\nNone\n"
        )

        args = argparse.Namespace(
            sprint="overlap-test",
            config=None,
            skip_analysis=True,
        )

        with (
            patch.object(output_mod, "_USE_COLOR", False),
            patch("little_loops.cli.output.terminal_width", return_value=120),
            patch("little_loops.cli.sprint._helpers.terminal_width", return_value=120),
        ):
            result = cli._cmd_sprint_show(args, manager)

        assert result == 0
        captured = capsys.readouterr()
        # With terminal width 120, title should NOT be truncated to 42+...
        assert "..." not in captured.out or long_title[:50] in captured.out

    def test_show_issue_file_paths(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Sprint show displays file paths for each issue."""
        import argparse
        from unittest.mock import patch

        import little_loops.cli.output as output_mod
        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_overlapping_issues(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="overlap-test",
            config=None,
            skip_analysis=True,
        )

        with patch.object(output_mod, "_USE_COLOR", False):
            result = cli._cmd_sprint_show(args, manager)

        assert result == 0
        captured = capsys.readouterr()
        # Should show issue file paths
        assert "P1-BUG-001-fix-config.md" in captured.out
        assert "P2-FEAT-001-add-config-validation.md" in captured.out

    def test_show_readiness_scores(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Sprint show displays readiness and confidence scores per issue."""
        import argparse
        from unittest.mock import patch

        import little_loops.cli.output as output_mod
        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_overlapping_issues(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Add confidence scores to an issue
        issue_file = tmp_path / ".issues" / "bugs" / "P1-BUG-001-fix-config.md"
        issue_file.write_text(
            "---\nconfidence_score: 85\noutcome_confidence: 72\n---\n"
            "# BUG-001: Fix config parsing\n\n"
            "## Summary\nFix bug in config module.\n\n"
            "### Files to Modify\n- `scripts/config.py`\n\n"
            "## Blocked By\n\nNone\n\n"
            "## Blocks\n\nNone\n"
        )

        args = argparse.Namespace(
            sprint="overlap-test",
            config=None,
            skip_analysis=True,
        )

        with patch.object(output_mod, "_USE_COLOR", False):
            result = cli._cmd_sprint_show(args, manager)

        assert result == 0
        captured = capsys.readouterr()
        # Scores should appear in output
        assert "85" in captured.out
        assert "72" in captured.out

    def test_show_json_output(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Sprint show --json produces valid JSON output."""
        import argparse
        import json as json_mod
        from unittest.mock import patch

        import little_loops.cli.output as output_mod
        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_overlapping_issues(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="overlap-test",
            config=None,
            skip_analysis=True,
            json=True,
        )

        with patch.object(output_mod, "_USE_COLOR", False):
            result = cli._cmd_sprint_show(args, manager)

        assert result == 0
        captured = capsys.readouterr()
        data = json_mod.loads(captured.out)
        assert data["name"] == "overlap-test"
        assert "issues" in data
        assert isinstance(data["issues"], list)

    def test_show_sprint_run_state(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Sprint show displays last run state when .sprint-state.json exists."""
        import argparse
        import json as json_mod
        from unittest.mock import patch

        import little_loops.cli.output as output_mod
        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_overlapping_issues(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Create .sprint-state.json
        state_data = {
            "sprint_name": "overlap-test",
            "current_wave": 2,
            "completed_issues": ["BUG-001"],
            "failed_issues": {"FEAT-001": "timeout"},
            "skipped_blocked_issues": {},
            "timing": {},
            "started_at": "2026-04-01T10:00:00+00:00",
            "last_checkpoint": "2026-04-01T10:30:00+00:00",
        }
        (tmp_path / ".sprint-state.json").write_text(json_mod.dumps(state_data))

        args = argparse.Namespace(
            sprint="overlap-test",
            config=None,
            skip_analysis=True,
        )

        with patch.object(output_mod, "_USE_COLOR", False):
            result = cli._cmd_sprint_show(args, manager)

        assert result == 0
        captured = capsys.readouterr()
        assert "Last run:" in captured.out
        assert "1 completed" in captured.out or "BUG-001" in captured.out

    def test_show_surfaces_contention_thresholds(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """Sprint show includes bracket suffix and tuning hint when config has dependency_mapping."""
        import argparse
        from unittest.mock import patch

        import little_loops.cli.output as output_mod
        from little_loops.cli import sprint as cli
        from little_loops.config import BRConfig
        from little_loops.sprint import SprintManager

        # Create directory structure
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)
        for category in ["bugs", "features", "enhancements", "completed"]:
            (issues_dir / category).mkdir(exist_ok=True)

        # Create config with custom dependency_mapping thresholds
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "ll-config.json"
        config_data = {
            "project": {
                "name": "test-project",
                "src_dir": "src/",
                "test_cmd": "pytest",
                "lint_cmd": "ruff check",
            },
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    "enhancements": {
                        "prefix": "ENH",
                        "dir": "enhancements",
                        "action": "improve",
                    },
                },
                "completed_dir": "completed",
            },
            "dependency_mapping": {
                "overlap_min_files": 3,
                "overlap_min_ratio": 0.5,
            },
        }
        import json as json_mod

        with open(config_file, "w") as f:
            json_mod.dump(config_data, f)

        # Create two issues sharing the same file (triggers contention)
        (issues_dir / "bugs" / "P1-BUG-001-fix-config.md").write_text(
            "# BUG-001: Fix config parsing\n\n"
            "## Summary\nFix bug in config module.\n\n"
            "### Files to Modify\n- `scripts/config.py`\n- `scripts/helpers.py`\n- `scripts/utils.py`\n\n"
            "## Blocked By\n\nNone\n\n"
            "## Blocks\n\nNone\n"
        )
        (issues_dir / "features" / "P2-FEAT-001-add-config-validation.md").write_text(
            "# FEAT-001: Add config validation\n\n"
            "## Summary\nAdd validation to config module.\n\n"
            "### Files to Modify\n- `scripts/config.py`\n- `scripts/helpers.py`\n- `scripts/utils.py`\n\n"
            "## Blocked By\n\nNone\n\n"
            "## Blocks\n\nNone\n"
        )

        sprints_dir = tmp_path / "sprints"
        sprints_dir.mkdir(exist_ok=True)
        (sprints_dir / "threshold-test.yaml").write_text(
            "name: threshold-test\nissues:\n  - BUG-001\n  - FEAT-001\n"
        )

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="threshold-test",
            config=None,
            skip_analysis=True,
        )

        with patch.object(output_mod, "_USE_COLOR", False):
            result = cli._cmd_sprint_show(args, manager)

        assert result == 0
        captured = capsys.readouterr()
        # Bracket suffix with effective threshold values should appear in wave header
        assert "[min_files=3, ratio=0.5]" in captured.out
        # Tuning hint should appear beneath Contended files line
        assert (
            "Tune: dependency_mapping.overlap_min_files / overlap_min_ratio in ll-config.json"
            in captured.out
        )


class TestSprintEdit:
    """Tests for _cmd_sprint_edit (ENH-393)."""

    @staticmethod
    def _setup_edit_project(tmp_path: Path) -> tuple[Path, Any, Any]:
        """Set up a test project with config, issues, and sprint for edit tests."""
        from little_loops.config import BRConfig
        from little_loops.sprint import SprintManager

        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)

        for category in ["bugs", "features", "enhancements", "epics", "completed"]:
            (issues_dir / category).mkdir(exist_ok=True)

        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)

        config_file = config_dir / "ll-config.json"
        config_data = {
            "project": {
                "name": "test-project",
                "src_dir": "src/",
                "test_cmd": "pytest",
                "lint_cmd": "ruff check",
            },
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    "enhancements": {
                        "prefix": "ENH",
                        "dir": "enhancements",
                        "action": "improve",
                    },
                    "epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"},
                },
                "completed_dir": "completed",
            },
        }

        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Create sample issues
        (issues_dir / "bugs" / "P1-BUG-001-test-bug.md").write_text(
            "# BUG-001: Test Bug\n\n## Summary\nFix this bug."
        )
        (issues_dir / "features" / "P2-FEAT-010-test-feature.md").write_text(
            "# FEAT-010: Test Feature\n\n## Summary\nImplement this."
        )
        (issues_dir / "enhancements" / "P3-ENH-020-test-enh.md").write_text(
            "# ENH-020: Test Enhancement\n\n## Summary\nImprove this."
        )

        # Create sprint with BUG-001 and FEAT-010
        sprints_dir = tmp_path / "sprints"
        sprints_dir.mkdir(exist_ok=True)
        sprint_data = {
            "name": "test-sprint",
            "description": "Test sprint",
            "created": "2026-01-01T00:00:00Z",
            "issues": ["BUG-001", "FEAT-010"],
        }
        with open(sprints_dir / "test-sprint.yaml", "w") as f:
            yaml.dump(sprint_data, f, default_flow_style=False, sort_keys=False)

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)

        return sprints_dir, config, manager

    def test_edit_add_issues(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Adding issues to a sprint updates the YAML file."""
        import argparse

        from little_loops.cli import sprint as cli

        sprints_dir, _, manager = self._setup_edit_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="test-sprint",
            add="ENH-020",
            remove=None,
            prune=False,
            revalidate=False,
            config=None,
        )

        result = cli._cmd_sprint_edit(args, manager)
        assert result == 0

        sprint = manager.load("test-sprint")
        assert sprint is not None
        assert "ENH-020" in sprint.issues
        assert len(sprint.issues) == 3

    def test_edit_remove_issues(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Removing issues from a sprint updates the YAML file."""
        import argparse

        from little_loops.cli import sprint as cli

        sprints_dir, _, manager = self._setup_edit_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="test-sprint",
            add=None,
            remove="BUG-001",
            prune=False,
            revalidate=False,
            config=None,
        )

        result = cli._cmd_sprint_edit(args, manager)
        assert result == 0

        sprint = manager.load("test-sprint")
        assert sprint is not None
        assert "BUG-001" not in sprint.issues
        assert sprint.issues == ["FEAT-010"]

    def test_edit_add_validates_existence(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """Adding non-existent issue IDs warns and skips them."""
        import argparse

        from little_loops.cli import sprint as cli

        sprints_dir, _, manager = self._setup_edit_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="test-sprint",
            add="FAKE-999",
            remove=None,
            prune=False,
            revalidate=False,
            config=None,
        )

        result = cli._cmd_sprint_edit(args, manager)
        assert result == 0

        # Sprint unchanged
        sprint = manager.load("test-sprint")
        assert sprint is not None
        assert len(sprint.issues) == 2

        captured = capsys.readouterr()
        assert "not found" in captured.err.lower()

    def test_edit_add_skips_duplicates(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Adding an already-present issue warns about duplicate."""
        import argparse

        from little_loops.cli import sprint as cli

        sprints_dir, _, manager = self._setup_edit_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="test-sprint",
            add="BUG-001",
            remove=None,
            prune=False,
            revalidate=False,
            config=None,
        )

        result = cli._cmd_sprint_edit(args, manager)
        assert result == 0

        sprint = manager.load("test-sprint")
        assert sprint is not None
        assert sprint.issues.count("BUG-001") == 1

        captured = capsys.readouterr()
        assert "Already in sprint" in captured.out

    def test_edit_remove_nonexistent_warns(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """Removing an ID not in the sprint warns."""
        import argparse

        from little_loops.cli import sprint as cli

        sprints_dir, _, manager = self._setup_edit_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="test-sprint",
            add=None,
            remove="ENH-999",
            prune=False,
            revalidate=False,
            config=None,
        )

        result = cli._cmd_sprint_edit(args, manager)
        assert result == 0

        captured = capsys.readouterr()
        assert "Not in sprint" in captured.err

    def test_edit_prune_removes_invalid(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Prune removes issues whose files don't exist."""
        import argparse

        from little_loops.cli import sprint as cli

        sprints_dir, _, manager = self._setup_edit_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Add a non-existent issue directly to the YAML
        sprint = manager.load("test-sprint")
        assert sprint is not None
        sprint.issues.append("BUG-999")
        sprint.save(sprints_dir)

        args = argparse.Namespace(
            sprint="test-sprint",
            add=None,
            remove=None,
            prune=True,
            revalidate=False,
            config=None,
        )

        result = cli._cmd_sprint_edit(args, manager)
        assert result == 0

        sprint = manager.load("test-sprint")
        assert sprint is not None
        assert "BUG-999" not in sprint.issues
        assert "BUG-001" in sprint.issues
        assert "FEAT-010" in sprint.issues

    def test_edit_prune_removes_completed(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """Prune removes issues with status: done frontmatter."""
        import argparse

        from little_loops.cli import sprint as cli

        sprints_dir, _, manager = self._setup_edit_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        # BUG-001 marked done via frontmatter (stays in bugs/ dir)
        (tmp_path / ".issues" / "bugs" / "P1-BUG-001-test-bug.md").write_text(
            "---\nstatus: done\n---\n\n# BUG-001: Done"
        )

        args = argparse.Namespace(
            sprint="test-sprint",
            add=None,
            remove=None,
            prune=True,
            revalidate=False,
            config=None,
        )

        result = cli._cmd_sprint_edit(args, manager)
        assert result == 0

        sprint = manager.load("test-sprint")
        assert sprint is not None
        assert "BUG-001" not in sprint.issues
        assert "FEAT-010" in sprint.issues

        captured = capsys.readouterr()
        output = captured.out.lower()
        assert "pruned" in output or "prune" in output

    def test_edit_prune_recognizes_epic_in_completed(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """Prune removes an EPIC issue with status: done frontmatter."""
        import argparse

        from little_loops.cli import sprint as cli

        sprints_dir, _, manager = self._setup_edit_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Rewrite the sprint YAML to include EPIC-005
        sprint_data = {
            "name": "test-sprint",
            "description": "Test sprint",
            "created": "2026-01-01T00:00:00Z",
            "issues": ["BUG-001", "FEAT-010", "EPIC-005"],
        }
        with open(sprints_dir / "test-sprint.yaml", "w") as f:
            yaml.dump(sprint_data, f, default_flow_style=False, sort_keys=False)

        # EPIC-005 in epics/ with status: done frontmatter
        epics_dir = tmp_path / ".issues" / "epics"
        epics_dir.mkdir(exist_ok=True)
        (epics_dir / "P2-EPIC-005-test-epic.md").write_text(
            "---\nstatus: done\n---\n\n# EPIC-005: Done"
        )

        args = argparse.Namespace(
            sprint="test-sprint",
            add=None,
            remove=None,
            prune=True,
            revalidate=False,
            config=None,
        )

        result = cli._cmd_sprint_edit(args, manager)
        assert result == 0

        updated = manager.load("test-sprint")
        assert updated is not None
        assert "EPIC-005" not in updated.issues

    def test_edit_prune_nothing_to_prune(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """Prune with all-valid sprint reports nothing to prune."""
        import argparse

        from little_loops.cli import sprint as cli

        sprints_dir, _, manager = self._setup_edit_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="test-sprint",
            add=None,
            remove=None,
            prune=True,
            revalidate=False,
            config=None,
        )

        result = cli._cmd_sprint_edit(args, manager)
        assert result == 0

        captured = capsys.readouterr()
        assert "Nothing to prune" in captured.out

    def test_edit_no_flags_returns_error(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """Returns error when no edit flags are specified."""
        import argparse

        from little_loops.cli import sprint as cli

        sprints_dir, _, manager = self._setup_edit_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="test-sprint",
            add=None,
            remove=None,
            prune=False,
            revalidate=False,
            config=None,
        )

        result = cli._cmd_sprint_edit(args, manager)
        assert result == 1

        captured = capsys.readouterr()
        assert "No edit flags specified" in captured.err

    def test_edit_sprint_not_found(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Returns error for nonexistent sprint."""
        import argparse

        from little_loops.cli import sprint as cli

        sprints_dir, _, manager = self._setup_edit_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            sprint="nonexistent",
            add="BUG-001",
            remove=None,
            prune=False,
            revalidate=False,
            config=None,
        )

        result = cli._cmd_sprint_edit(args, manager)
        assert result == 1

    def test_edit_combined_flags(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Combining --add, --remove, and --prune works together."""
        import argparse

        from little_loops.cli import sprint as cli

        sprints_dir, _, manager = self._setup_edit_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Add a non-existent issue to the sprint for pruning
        sprint = manager.load("test-sprint")
        assert sprint is not None
        sprint.issues.append("BUG-999")
        sprint.save(sprints_dir)

        args = argparse.Namespace(
            sprint="test-sprint",
            add="ENH-020",
            remove="FEAT-010",
            prune=True,
            revalidate=False,
            config=None,
        )

        result = cli._cmd_sprint_edit(args, manager)
        assert result == 0

        sprint = manager.load("test-sprint")
        assert sprint is not None
        assert "ENH-020" in sprint.issues
        assert "FEAT-010" not in sprint.issues
        assert "BUG-999" not in sprint.issues
        assert "BUG-001" in sprint.issues


class TestSprintAnalyze:
    """Tests for _cmd_sprint_analyze (FEAT-433)."""

    @staticmethod
    def _setup_analyze_project(
        tmp_path: Path,
        overlapping: bool = True,
    ) -> tuple[Path, Any, Any]:
        """Set up a test project for analyze tests.

        Args:
            tmp_path: Pytest temporary directory
            overlapping: If True, issues reference the same file (conflict).
                         If False, issues reference different files (no conflict).
        """
        from little_loops.config import BRConfig
        from little_loops.sprint import SprintManager

        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)
        for category in ["bugs", "features", "enhancements", "completed"]:
            (issues_dir / category).mkdir(exist_ok=True)

        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "ll-config.json"
        config_data = {
            "project": {
                "name": "test-project",
                "src_dir": "src/",
                "test_cmd": "pytest",
                "lint_cmd": "ruff check",
            },
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    "enhancements": {
                        "prefix": "ENH",
                        "dir": "enhancements",
                        "action": "improve",
                    },
                },
                "completed_dir": "completed",
            },
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        if overlapping:
            # Two issues that reference 2 shared files → conflict under AND logic
            (issues_dir / "bugs" / "P1-BUG-001-fix-parser.md").write_text(
                "# BUG-001: Fix parser bug\n\n"
                "## Summary\nFix bug in parser module.\n\n"
                "### Files to Modify\n- `scripts/parser.py`\n- `scripts/tokenizer.py`\n\n"
                "## Blocked By\n\nNone\n\n"
                "## Blocks\n\nNone\n"
            )
            (issues_dir / "features" / "P2-FEAT-010-add-parser-validation.md").write_text(
                "# FEAT-010: Add parser validation\n\n"
                "## Summary\nAdd validation to parser module.\n\n"
                "### Files to Modify\n- `scripts/parser.py`\n- `scripts/tokenizer.py`\n\n"
                "## Blocked By\n\nNone\n\n"
                "## Blocks\n\nNone\n"
            )
        else:
            # Two issues that reference different files → no conflict
            (issues_dir / "bugs" / "P1-BUG-001-fix-parser.md").write_text(
                "# BUG-001: Fix parser bug\n\n"
                "## Summary\nFix bug in parser module.\n\n"
                "### Files to Modify\n- `scripts/parser.py`\n\n"
                "## Blocked By\n\nNone\n\n"
                "## Blocks\n\nNone\n"
            )
            (issues_dir / "features" / "P2-FEAT-010-add-formatter.md").write_text(
                "# FEAT-010: Add formatter\n\n"
                "## Summary\nAdd formatting to formatter module.\n\n"
                "### Files to Modify\n- `scripts/formatter.py`\n\n"
                "## Blocked By\n\nNone\n\n"
                "## Blocks\n\nNone\n"
            )

        sprints_dir = tmp_path / "sprints"
        sprints_dir.mkdir(exist_ok=True)
        sprint_file = sprints_dir / "test-sprint.yaml"
        sprint_file.write_text("name: test-sprint\nissues:\n  - BUG-001\n  - FEAT-010\n")

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)
        return sprints_dir, config, manager

    def test_analyze_with_conflicts(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Analyze detects file conflicts and returns exit code 1."""
        import argparse

        from little_loops.cli import sprint as cli

        _, _, manager = self._setup_analyze_project(tmp_path, overlapping=True)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(sprint="test-sprint", format="text", config=None)
        result = cli._cmd_sprint_analyze(args, manager)
        assert result == 1

        captured = capsys.readouterr()
        assert "CONFLICT ANALYSIS" in captured.out
        assert "Conflicts found: 1 pair(s)" in captured.out
        assert "BUG-001" in captured.out
        assert "FEAT-010" in captured.out
        assert "scripts/parser.py" in captured.out

    def test_analyze_no_conflicts(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """Analyze with no conflicts returns exit code 0."""
        import argparse

        from little_loops.cli import sprint as cli

        _, _, manager = self._setup_analyze_project(tmp_path, overlapping=False)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(sprint="test-sprint", format="text", config=None)
        result = cli._cmd_sprint_analyze(args, manager)
        assert result == 0

        captured = capsys.readouterr()
        assert "CONFLICT ANALYSIS" in captured.out
        assert "No file conflicts detected" in captured.out

    def test_analyze_sprint_not_found(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Returns error for nonexistent sprint."""
        import argparse

        from little_loops.cli import sprint as cli

        _, _, manager = self._setup_analyze_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(sprint="nonexistent", format="text", config=None)
        result = cli._cmd_sprint_analyze(args, manager)
        assert result == 1

    def test_analyze_json_format(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """JSON format outputs valid structured data."""
        import argparse

        from little_loops.cli import sprint as cli

        _, _, manager = self._setup_analyze_project(tmp_path, overlapping=True)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(sprint="test-sprint", format="json", config=None)
        result = cli._cmd_sprint_analyze(args, manager)
        assert result == 1

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["sprint"] == "test-sprint"
        assert data["issue_count"] == 2
        assert data["has_conflicts"] is True
        assert len(data["conflicts"]) == 1
        assert data["conflicts"][0]["issue_a"] == "BUG-001"
        assert data["conflicts"][0]["issue_b"] == "FEAT-010"
        assert "scripts/parser.py" in data["conflicts"][0]["overlapping_files"]
        assert isinstance(data["waves"], list)
        assert isinstance(data["parallel_safe_groups"], list)

    def test_analyze_json_no_conflicts(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """JSON format with no conflicts."""
        import argparse

        from little_loops.cli import sprint as cli

        _, _, manager = self._setup_analyze_project(tmp_path, overlapping=False)
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(sprint="test-sprint", format="json", config=None)
        result = cli._cmd_sprint_analyze(args, manager)
        assert result == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["has_conflicts"] is False
        assert len(data["conflicts"]) == 0


class TestSprintOnlyFlag:
    """Tests for --only flag in ll-sprint run (FEAT-490)."""

    def _setup_multi_issue_sprint(self, tmp_path: Path) -> tuple[Any, Any]:
        """Create a project with two issues and a sprint containing both."""
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "ll-config.json"
        config_data = {
            "project": {
                "name": "test-project",
                "src_dir": "src/",
                "test_cmd": "pytest",
                "lint_cmd": "ruff check",
            },
            "issues": {
                "base_dir": ".issues",
                "completed_dir": "completed",
            },
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        issues_dir = tmp_path / ".issues"
        (issues_dir / "bugs").mkdir(parents=True, exist_ok=True)
        (issues_dir / "features").mkdir(parents=True, exist_ok=True)
        (issues_dir / "bugs" / "P1-BUG-001-first-bug.md").write_text(
            "# BUG-001: First Bug\n\n## Summary\nFix this."
        )
        (issues_dir / "features" / "P2-FEAT-002-new-feature.md").write_text(
            "# FEAT-002: New Feature\n\n## Summary\nImplement this."
        )

        sprints_dir = tmp_path / "sprints"
        sprints_dir.mkdir(exist_ok=True)
        sprint_file = sprints_dir / "multi.yaml"
        sprint_file.write_text("name: multi\nissues:\n  - BUG-001\n  - FEAT-002\n")

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)
        return config, manager

    def test_only_flag_filters_to_specified_issues(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """--only restricts processing to the specified issue IDs."""
        import argparse

        from little_loops.cli import sprint as cli
        from little_loops.issue_manager import IssueProcessingResult

        config, manager = self._setup_multi_issue_sprint(tmp_path)

        processed: list[str] = []

        def mock_process_inplace(info: Any, **kwargs: Any) -> IssueProcessingResult:
            processed.append(info.issue_id)
            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        monkeypatch.setattr(
            "little_loops.cli.sprint.run.process_issue_inplace", mock_process_inplace
        )
        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="multi",
            dry_run=False,
            resume=False,
            skip=None,
            only="BUG-001",
            max_workers=1,
            quiet=False,
            skip_analysis=True,
            type=None,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 0
        assert "BUG-001" in processed
        assert "FEAT-002" not in processed

    def test_only_flag_error_on_unknown_id(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """--only returns error when specified ID is not in the sprint definition."""
        import argparse

        from little_loops.cli import sprint as cli

        config, manager = self._setup_multi_issue_sprint(tmp_path)
        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="multi",
            dry_run=False,
            resume=False,
            skip=None,
            only="BUG-999",
            max_workers=1,
            quiet=False,
            skip_analysis=True,
            type=None,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 1

        captured = capsys.readouterr()
        assert "BUG-999" in captured.out or "BUG-999" in captured.err

    def test_only_none_processes_all_issues(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any
    ) -> None:
        """Without --only, all sprint issues are processed."""
        import argparse

        from little_loops.cli import sprint as cli
        from little_loops.issue_manager import IssueProcessingResult

        config, manager = self._setup_multi_issue_sprint(tmp_path)

        processed: list[str] = []

        def mock_process_inplace(info: Any, **kwargs: Any) -> IssueProcessingResult:
            processed.append(info.issue_id)
            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        monkeypatch.setattr(
            "little_loops.cli.sprint.run.process_issue_inplace", mock_process_inplace
        )
        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="multi",
            dry_run=False,
            resume=False,
            skip=None,
            only=None,
            max_workers=1,
            quiet=False,
            skip_analysis=True,
            type=None,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 0
        assert "BUG-001" in processed
        assert "FEAT-002" in processed

    def test_only_flag_in_help(self) -> None:
        """--only flag is registered on the sprint run parser."""
        import argparse

        from little_loops.cli_args import add_only_arg

        parser = argparse.ArgumentParser()
        add_only_arg(parser)
        help_text = parser.format_help()
        assert "--only" in help_text


class TestSprintWaveCleanStart:
    """Tests that wave parallel config passes clean_start=True (BUG-615)."""

    def _setup_multi_issue_sprint(self, tmp_path: Path) -> tuple[Any, Any]:
        """Create a project with two issues and a sprint containing both."""
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "ll-config.json"
        config_data = {
            "project": {
                "name": "test-project",
                "src_dir": "src/",
                "test_cmd": "pytest",
                "lint_cmd": "ruff check",
            },
            "issues": {
                "base_dir": ".issues",
                "completed_dir": "completed",
            },
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        issues_dir = tmp_path / ".issues"
        (issues_dir / "bugs").mkdir(parents=True, exist_ok=True)
        (issues_dir / "features").mkdir(parents=True, exist_ok=True)
        # Non-overlapping file hints so the wave splitter keeps both issues parallel.
        (issues_dir / "bugs" / "P1-BUG-001-first-bug.md").write_text(
            "# BUG-001: First Bug\n\n## Summary\nFix this.\n\n"
            "## Implementation Plan\n\n### Files to Modify\n- src/bug001.py\n"
        )
        (issues_dir / "features" / "P2-FEAT-002-new-feature.md").write_text(
            "# FEAT-002: New Feature\n\n## Summary\nImplement this.\n\n"
            "## Implementation Plan\n\n### Files to Modify\n- src/feat002.py\n"
        )

        sprints_dir = tmp_path / "sprints"
        sprints_dir.mkdir(exist_ok=True)
        sprint_file = sprints_dir / "multi.yaml"
        sprint_file.write_text("name: multi\nissues:\n  - BUG-001\n  - FEAT-002\n")

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)
        return config, manager

    def test_wave_parallel_config_passes_clean_start(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Wave create_parallel_config call passes clean_start=True (BUG-615)."""
        import argparse
        from unittest.mock import MagicMock, patch

        from little_loops.cli import sprint as cli
        from little_loops.parallel.types import ParallelConfig

        config, manager = self._setup_multi_issue_sprint(tmp_path)
        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        captured_kwargs: dict[str, Any] = {}

        original_create = config.create_parallel_config

        def capturing_create(**kwargs: Any) -> ParallelConfig:
            captured_kwargs.update(kwargs)
            return original_create(**kwargs)

        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = 0
        mock_orchestrator.execution_duration = 0.0
        mock_orchestrator.queue.completed_ids = ["BUG-001", "FEAT-002"]
        mock_orchestrator.queue.failed_ids = []

        args = argparse.Namespace(
            sprint="multi",
            dry_run=False,
            resume=False,
            skip=None,
            only=None,
            max_workers=2,
            quiet=False,
            skip_analysis=True,
            type=None,
        )

        with (
            patch.object(config, "create_parallel_config", side_effect=capturing_create),
            patch(
                "little_loops.cli.sprint.run.ParallelOrchestrator",
                return_value=mock_orchestrator,
            ),
        ):
            cli._cmd_sprint_run(args, manager, config)

        assert captured_kwargs.get("clean_start") is True, (
            "Wave create_parallel_config must pass clean_start=True to avoid loading stale orchestrator state"
        )


class TestSprintManagerLoadOrResolve:
    """Tests for SprintManager.load_or_resolve() (FEAT-1737)."""

    @pytest.fixture
    def epic_project(self, tmp_path: Path) -> BRConfig:
        """Project with epics category and sample issues."""
        issues_dir = tmp_path / ".issues"
        for category in ["bugs", "features", "enhancements", "epics", "completed"]:
            (issues_dir / category).mkdir(parents=True, exist_ok=True)

        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
        config_data = {
            "project": {"name": "test-project", "src_dir": "src/"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
                    "epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"},
                },
                "completed_dir": "completed",
            },
        }
        (config_dir / "ll-config.json").write_text(json.dumps(config_data))
        return BRConfig(tmp_path)

    def test_load_or_resolve_sprint_name(self, tmp_path: Path, epic_project: BRConfig) -> None:
        """Non-EPIC arg falls through to file-based load()."""
        sprints_dir = tmp_path / ".sprints"
        manager = SprintManager(sprints_dir=sprints_dir, config=epic_project)
        manager.create(name="my-sprint", issues=["BUG-001"])

        result = manager.load_or_resolve("my-sprint")
        assert result is not None
        assert result.name == "my-sprint"
        assert result.issues == ["BUG-001"]

    def test_load_or_resolve_nonexistent_sprint_name(
        self, tmp_path: Path, epic_project: BRConfig
    ) -> None:
        """Non-EPIC arg that doesn't exist returns None from load()."""
        manager = SprintManager(sprints_dir=tmp_path, config=epic_project)
        result = manager.load_or_resolve("nonexistent-sprint")
        assert result is None

    def test_load_or_resolve_epic_id_forward_lookup(
        self, tmp_path: Path, epic_project: BRConfig
    ) -> None:
        """EPIC ID with relates_to includes those issues via forward lookup."""
        issues_dir = tmp_path / ".issues"
        (issues_dir / "epics" / "P1-EPIC-100-test-epic.md").write_text(
            "---\nid: EPIC-100\nstatus: open\nrelates_to:\n  - BUG-001\n---\n# EPIC-100: Test Epic\n"
        )
        (issues_dir / "bugs" / "P1-BUG-001-test-bug.md").write_text(
            "# BUG-001: Test Bug\n\n## Summary\nFix this.\n"
        )

        manager = SprintManager(sprints_dir=tmp_path / ".sprints", config=epic_project)
        result = manager.load_or_resolve("EPIC-100")

        assert result is not None
        assert result.name == "epic-100"
        assert "BUG-001" in result.issues

    def test_load_or_resolve_epic_id_backward_lookup(
        self, tmp_path: Path, epic_project: BRConfig
    ) -> None:
        """EPIC ID without relates_to finds children via parent: field scan."""
        issues_dir = tmp_path / ".issues"
        (issues_dir / "epics" / "P1-EPIC-200-test-epic.md").write_text(
            "---\nid: EPIC-200\nstatus: open\n---\n# EPIC-200: Test Epic\n"
        )
        (issues_dir / "features" / "P2-FEAT-010-test-feature.md").write_text(
            "---\nparent: EPIC-200\n---\n# FEAT-010: Test Feature\n\n## Summary\nImplement this.\n"
        )

        manager = SprintManager(sprints_dir=tmp_path / ".sprints", config=epic_project)
        result = manager.load_or_resolve("EPIC-200")

        assert result is not None
        assert result.name == "epic-200"
        assert "FEAT-010" in result.issues

    def test_load_or_resolve_epic_id_union_dedup(
        self, tmp_path: Path, epic_project: BRConfig
    ) -> None:
        """Forward and backward lookups are merged and deduplicated."""
        issues_dir = tmp_path / ".issues"
        # EPIC has BUG-001 in relates_to and FEAT-010 has parent: EPIC-300
        # BUG-001 also has parent: EPIC-300 (appears in both → deduplicated)
        (issues_dir / "epics" / "P1-EPIC-300-test-epic.md").write_text(
            "---\nid: EPIC-300\nstatus: open\nrelates_to:\n  - BUG-001\n---\n# EPIC-300: Test Epic\n"
        )
        (issues_dir / "bugs" / "P1-BUG-001-test-bug.md").write_text(
            "---\nparent: EPIC-300\n---\n# BUG-001: Test Bug\n\n## Summary\nFix this.\n"
        )
        (issues_dir / "features" / "P2-FEAT-010-test-feature.md").write_text(
            "---\nparent: EPIC-300\n---\n# FEAT-010: Test Feature\n\n## Summary\nImplement this.\n"
        )

        manager = SprintManager(sprints_dir=tmp_path / ".sprints", config=epic_project)
        result = manager.load_or_resolve("EPIC-300")

        assert result is not None
        assert result.name == "epic-300"
        issue_ids = result.issues
        assert "BUG-001" in issue_ids
        assert "FEAT-010" in issue_ids
        # Deduplicated: BUG-001 should appear exactly once
        assert issue_ids.count("BUG-001") == 1

    def test_load_or_resolve_filters_inactive_statuses(
        self, tmp_path: Path, epic_project: BRConfig
    ) -> None:
        """Done/cancelled children are excluded from the resolved sprint."""
        issues_dir = tmp_path / ".issues"
        (issues_dir / "epics" / "P1-EPIC-400-test-epic.md").write_text(
            "---\nid: EPIC-400\nstatus: open\nrelates_to:\n  - BUG-001\n  - FEAT-010\n---\n# EPIC-400\n"
        )
        (issues_dir / "bugs" / "P1-BUG-001-test-bug.md").write_text(
            "# BUG-001: Active Bug\n\n## Summary\nFix this.\n"
        )
        (issues_dir / "features" / "P2-FEAT-010-done-feature.md").write_text(
            "---\nstatus: done\n---\n# FEAT-010: Done Feature\n"
        )

        manager = SprintManager(sprints_dir=tmp_path / ".sprints", config=epic_project)
        result = manager.load_or_resolve("EPIC-400")

        assert result is not None
        assert "BUG-001" in result.issues
        assert "FEAT-010" not in result.issues

    def test_load_or_resolve_pending_children_included(
        self, tmp_path: Path, epic_project: BRConfig
    ) -> None:
        """Pending children are coerced to open (active) and must be included.

        ``pending`` is a non-canonical status coerced to ``open`` on read via
        STATUS_SYNONYMS, so it falls within the active set EPIC resolution uses.
        Contrast with test_load_or_resolve_filters_inactive_statuses (done-out).
        """
        issues_dir = tmp_path / ".issues"
        (issues_dir / "epics" / "P1-EPIC-450-test-epic.md").write_text(
            "---\nid: EPIC-450\nstatus: open\n---\n# EPIC-450\n"
        )
        (issues_dir / "features" / "P2-FEAT-020-pending-feature.md").write_text(
            "---\nparent: EPIC-450\nstatus: pending\n---\n# FEAT-020: Pending Feature\n"
        )

        manager = SprintManager(sprints_dir=tmp_path / ".sprints", config=epic_project)
        result = manager.load_or_resolve("EPIC-450")

        assert result is not None
        assert "FEAT-020" in result.issues

    def test_load_or_resolve_epic_not_found(self, tmp_path: Path, epic_project: BRConfig) -> None:
        """EPIC ID that doesn't exist returns None."""
        manager = SprintManager(sprints_dir=tmp_path / ".sprints", config=epic_project)
        result = manager.load_or_resolve("EPIC-999")
        assert result is None

    def test_load_or_resolve_epic_no_active_children(
        self, tmp_path: Path, epic_project: BRConfig
    ) -> None:
        """EPIC with no active children returns Sprint with empty issues list."""
        issues_dir = tmp_path / ".issues"
        (issues_dir / "epics" / "P1-EPIC-500-empty-epic.md").write_text(
            "---\nid: EPIC-500\nstatus: open\n---\n# EPIC-500: Empty Epic\n"
        )

        manager = SprintManager(sprints_dir=tmp_path / ".sprints", config=epic_project)
        result = manager.load_or_resolve("EPIC-500")

        assert result is not None
        assert result.name == "epic-500"
        assert result.issues == []

    def test_load_or_resolve_epic_id_case_insensitive(
        self, tmp_path: Path, epic_project: BRConfig
    ) -> None:
        """EPIC ID is recognized and normalized regardless of input case."""
        issues_dir = tmp_path / ".issues"
        (issues_dir / "epics" / "P1-EPIC-600-test-epic.md").write_text(
            "---\nid: EPIC-600\nstatus: open\nrelates_to:\n  - BUG-001\n---\n# EPIC-600: Test Epic\n"
        )
        (issues_dir / "bugs" / "P1-BUG-001-test-bug.md").write_text(
            "# BUG-001: Test Bug\n\n## Summary\nFix this.\n"
        )

        manager = SprintManager(sprints_dir=tmp_path / ".sprints", config=epic_project)
        # lowercase input
        result = manager.load_or_resolve("epic-600")
        assert result is not None
        assert result.name == "epic-600"
        assert "BUG-001" in result.issues

    def test_save_flag_materializes_yaml(self, tmp_path: Path, epic_project: BRConfig) -> None:
        """Saving an EPIC-resolved Sprint writes a YAML file."""
        issues_dir = tmp_path / ".issues"
        (issues_dir / "epics" / "P1-EPIC-700-test-epic.md").write_text(
            "---\nid: EPIC-700\nstatus: open\nrelates_to:\n  - BUG-001\n---\n# EPIC-700: Test Epic\n"
        )
        (issues_dir / "bugs" / "P1-BUG-001-test-bug.md").write_text(
            "# BUG-001: Test Bug\n\n## Summary\nFix this.\n"
        )

        sprints_dir = tmp_path / ".sprints"
        manager = SprintManager(sprints_dir=sprints_dir, config=epic_project)
        sprint = manager.load_or_resolve("EPIC-700")

        assert sprint is not None
        saved_path = sprint.save(manager.sprints_dir)
        assert saved_path.exists()
        assert saved_path.name == "epic-700.yaml"

        with open(saved_path) as f:
            data = yaml.safe_load(f)
        assert data["name"] == "epic-700"
        assert "BUG-001" in data["issues"]

    def test_load_or_resolve_nested_epic_grandchild_depth_mismatch(
        self, tmp_path: Path, epic_project: BRConfig
    ) -> None:
        """FEAT-2449: sprint resolution is direct-only; a grandchild reached via
        an intermediate sub-EPIC is NOT included by ``load_or_resolve`` (which
        does ``info.parent == epic_id`` at sprint.py:326), while
        ``compute_epic_progress`` walks transitively and DOES include it. This
        documents the run-construction vs. completion-gate depth mismatch the
        EPIC-completion trigger relies on.
        """
        issues_dir = tmp_path / ".issues"
        (issues_dir / "epics" / "P1-EPIC-800-top.md").write_text(
            "---\nid: EPIC-800\nstatus: in_progress\n---\n# EPIC-800: Top\n"
        )
        (issues_dir / "epics" / "P1-EPIC-801-sub.md").write_text(
            "---\nid: EPIC-801\nstatus: open\nparent: EPIC-800\n---\n# EPIC-801: Sub\n"
        )
        (issues_dir / "features" / "P2-FEAT-030-grandchild.md").write_text(
            "---\nid: FEAT-030\nstatus: open\nparent: EPIC-801\n---\n"
            "# FEAT-030: Grandchild\n\n## Summary\nImplement this.\n"
        )

        manager = SprintManager(sprints_dir=tmp_path / ".sprints", config=epic_project)
        result = manager.load_or_resolve("EPIC-800")

        assert result is not None
        # Direct-only backward lookup: the sub-EPIC is a direct child of EPIC-800,
        # but the grandchild (parent == EPIC-801) is one hop too deep.
        assert "EPIC-801" in result.issues
        assert "FEAT-030" not in result.issues

        # compute_epic_progress walks the parent chain transitively → the
        # grandchild IS resolved as a child of EPIC-800 (the semantics the
        # completion gate uses).
        from little_loops.issue_parser import find_issues
        from little_loops.issue_progress import compute_epic_progress

        all_issues = find_issues(
            epic_project,
            status_filter={
                "open",
                "in_progress",
                "blocked",
                "done",
                "cancelled",
                "deferred",
            },
        )
        prog = compute_epic_progress("EPIC-800", all_issues)
        assert prog is not None
        child_ids = {c.issue_id for c in prog.children}
        assert "FEAT-030" in child_ids
        assert "EPIC-801" in child_ids


class TestSprintListJsonShortForm:
    """-j short form for --json in ll-sprint list subcommand (ENH-909)."""

    def test_list_json_short_form(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """-j is accepted by ll-sprint list and sets json=True."""
        import sys
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir(exist_ok=True)

        with (
            patch.object(sys, "argv", ["ll-sprint", "list", "-j"]),
            patch("little_loops.cli.sprint._cmd_sprint_list", return_value=0) as mock_list,
        ):
            from little_loops.cli import main_sprint

            result = main_sprint()

        assert result == 0
        mock_list.assert_called_once()
        list_args = mock_list.call_args[0][0]
        assert getattr(list_args, "json", False) is True
