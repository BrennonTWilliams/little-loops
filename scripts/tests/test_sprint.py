"""Tests for sprint module."""

from pathlib import Path

import yaml

from little_loops.sprint import Sprint, SprintManager, SprintOptions


class TestSprintOptions:
    """Tests for SprintOptions dataclass."""

    def test_default_values(self) -> None:
        """Default values are correct."""
        options = SprintOptions()
        assert options.max_iterations == 100
        assert options.timeout == 3600
        assert options.max_workers == 4

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
        assert options.max_workers == 4


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
        assert sprint.options.max_workers == 4

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
