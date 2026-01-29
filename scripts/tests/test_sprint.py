"""Tests for sprint module."""

import json
from pathlib import Path

import yaml

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
