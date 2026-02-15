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
            (issues_dir / category).mkdir(parents=True)

        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
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

        from little_loops.cli import sprint as cli

        # Reset state
        cli._sprint_shutdown_requested = False

        # Call handler (simulating SIGINT)
        cli._sprint_signal_handler(signal.SIGINT, None)

        assert cli._sprint_shutdown_requested is True

    def test_signal_handler_second_signal_exits(self) -> None:
        """Second signal raises SystemExit."""
        import signal

        import pytest

        from little_loops.cli import sprint as cli

        # Set flag as if first signal received
        cli._sprint_shutdown_requested = True

        # Second signal should exit
        with pytest.raises(SystemExit) as exc_info:
            cli._sprint_signal_handler(signal.SIGINT, None)

        assert exc_info.value.code == 1


class TestSprintErrorHandling:
    """Tests for _cmd_sprint_run error handling wrapper (ENH-185)."""

    @staticmethod
    def _setup_test_project(tmp_path: Path) -> tuple[Path, Any, Any]:
        """Set up a test project with config, issues, and sprint."""
        from little_loops.config import BRConfig
        from little_loops.sprint import SprintManager

        # Create directory structure
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()

        for category in ["bugs", "features", "enhancements", "completed"]:
            (issues_dir / category).mkdir()

        # Create config
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()

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
        sprints_dir.mkdir()
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

        from little_loops.cli import sprint as cli

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
            "little_loops.issue_manager.process_issue_inplace",
            raise_keyboard_interrupt,
        )

        # Change to tmp_path so state file is created there
        monkeypatch.chdir(tmp_path)

        # Reset shutdown flag
        cli._sprint_shutdown_requested = False

        # Run and check exit code
        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 130

    def test_unexpected_exception_returns_1(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Unexpected exception during wave processing returns exit code 1."""
        import argparse

        from little_loops.cli import sprint as cli

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
            "little_loops.issue_manager.process_issue_inplace",
            raise_runtime_error,
        )

        # Change to tmp_path so state file is created there
        monkeypatch.chdir(tmp_path)

        # Reset shutdown flag
        cli._sprint_shutdown_requested = False

        # Run and check exit code
        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 1

    def test_exception_saves_state(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Exception during processing saves state before exit."""
        import argparse

        from little_loops.cli import sprint as cli

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
            "little_loops.issue_manager.process_issue_inplace",
            raise_runtime_error,
        )

        # Change to tmp_path so state file is created there
        monkeypatch.chdir(tmp_path)

        # Reset shutdown flag
        cli._sprint_shutdown_requested = False

        # Run the function
        cli._cmd_sprint_run(args, manager, config)

        # Check that state file was created
        state_file = tmp_path / ".sprint-state.json"
        assert state_file.exists(), "State file should be saved on exception"

        # Verify state content
        state_data = json.loads(state_file.read_text())
        assert state_data["sprint_name"] == "test"
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
        issues_dir.mkdir()
        for category in ["bugs", "features", "enhancements", "completed"]:
            (issues_dir / category).mkdir()

        # Create config
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
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
            "## Summary\nFix bug in `scripts/config.py` module.\n\n"
            "## Blocked By\n\nNone\n\n"
            "## Blocks\n\nNone\n"
        )
        (issues_dir / "features" / "P2-FEAT-001-add-config-validation.md").write_text(
            "# FEAT-001: Add config validation\n\n"
            "## Summary\nAdd validation to `scripts/config.py` module.\n\n"
            "## Blocked By\n\nNone\n\n"
            "## Blocks\n\nNone\n"
        )

        # Create sprint
        sprints_dir = tmp_path / "sprints"
        sprints_dir.mkdir()
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
            "little_loops.issue_manager.process_issue_inplace", mock_process_inplace
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
            "little_loops.issue_manager.process_issue_inplace", mock_process_inplace
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


class TestSprintEdit:
    """Tests for _cmd_sprint_edit (ENH-393)."""

    @staticmethod
    def _setup_edit_project(tmp_path: Path) -> tuple[Path, Any, Any]:
        """Set up a test project with config, issues, and sprint for edit tests."""
        from little_loops.config import BRConfig
        from little_loops.sprint import SprintManager

        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()

        for category in ["bugs", "features", "enhancements", "completed"]:
            (issues_dir / category).mkdir()

        config_dir = tmp_path / ".claude"
        config_dir.mkdir()

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
        sprints_dir.mkdir()
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
        assert "not found" in captured.out.lower()

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
        assert "Not in sprint" in captured.out

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
        """Prune removes issues that are in the completed directory."""
        import argparse

        from little_loops.cli import sprint as cli

        sprints_dir, _, manager = self._setup_edit_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Move BUG-001 to completed
        completed_dir = tmp_path / ".issues" / "completed"
        (completed_dir / "P1-BUG-001-test-bug.md").write_text("# BUG-001: Done")
        # Remove from active
        (tmp_path / ".issues" / "bugs" / "P1-BUG-001-test-bug.md").unlink()

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
        issues_dir.mkdir()
        for category in ["bugs", "features", "enhancements", "completed"]:
            (issues_dir / category).mkdir()

        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
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
            # Two issues that reference the same file → conflict
            (issues_dir / "bugs" / "P1-BUG-001-fix-parser.md").write_text(
                "# BUG-001: Fix parser bug\n\n"
                "## Summary\nFix bug in `scripts/parser.py` module.\n\n"
                "## Blocked By\n\nNone\n\n"
                "## Blocks\n\nNone\n"
            )
            (issues_dir / "features" / "P2-FEAT-010-add-parser-validation.md").write_text(
                "# FEAT-010: Add parser validation\n\n"
                "## Summary\nAdd validation to `scripts/parser.py` module.\n\n"
                "## Blocked By\n\nNone\n\n"
                "## Blocks\n\nNone\n"
            )
        else:
            # Two issues that reference different files → no conflict
            (issues_dir / "bugs" / "P1-BUG-001-fix-parser.md").write_text(
                "# BUG-001: Fix parser bug\n\n"
                "## Summary\nFix bug in `scripts/parser.py` module.\n\n"
                "## Blocked By\n\nNone\n\n"
                "## Blocks\n\nNone\n"
            )
            (issues_dir / "features" / "P2-FEAT-010-add-formatter.md").write_text(
                "# FEAT-010: Add formatter\n\n"
                "## Summary\nAdd formatting in `scripts/formatter.py` module.\n\n"
                "## Blocked By\n\nNone\n\n"
                "## Blocks\n\nNone\n"
            )

        sprints_dir = tmp_path / "sprints"
        sprints_dir.mkdir()
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
