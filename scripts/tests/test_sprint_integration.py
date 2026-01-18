"""Integration tests for sprint execution."""

import json
from pathlib import Path

import pytest

from little_loops.config import BRConfig
from little_loops.sprint import SprintManager


@pytest.fixture
def sprint_project(tmp_path: Path) -> BRConfig:
    """Create a test project with issues and config."""
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

    # Create sample issues
    (issues_dir / "bugs" / "P1-BUG-001-test-bug.md").write_text(
        "# BUG-001: Test Bug\n\nFix this bug."
    )
    (issues_dir / "features" / "P2-FEAT-010-test-feature.md").write_text(
        "# FEAT-010: Test Feature\n\nImplement this feature."
    )

    return BRConfig(tmp_path)


def test_sprint_lifecycle(sprint_project: BRConfig, tmp_path: Path) -> None:
    """Test full sprint lifecycle: create, list, show, delete."""
    manager = SprintManager(sprints_dir=tmp_path, config=sprint_project)

    # Create sprint
    sprint = manager.create(
        name="test-sprint",
        issues=["BUG-001", "FEAT-010"],
        description="Test sprint",
    )

    assert sprint.name == "test-sprint"
    assert len(sprint.issues) == 2

    # List sprints
    sprints = manager.list_all()
    assert len(sprints) == 1
    assert sprints[0].name == "test-sprint"

    # Show sprint
    loaded = manager.load("test-sprint")
    assert loaded is not None
    assert loaded.issues == ["BUG-001", "FEAT-010"]

    # Validate issues
    valid = manager.validate_issues(loaded.issues)
    assert "BUG-001" in valid
    assert "FEAT-010" in valid

    # Delete sprint
    result = manager.delete("test-sprint")
    assert result is True

    # Verify deleted
    sprints = manager.list_all()
    assert len(sprints) == 0


def test_sprint_validation_invalid_issues(sprint_project: BRConfig, tmp_path: Path) -> None:
    """Test sprint validation with invalid issue IDs."""
    manager = SprintManager(sprints_dir=tmp_path, config=sprint_project)

    # Create sprint with mix of valid and invalid issues
    sprint = manager.create(
        name="test-sprint",
        issues=["BUG-001", "NONEXISTENT", "FEAT-010"],
    )

    # Validate
    valid = manager.validate_issues(sprint.issues)

    # Only BUG-001 and FEAT-010 should be valid
    assert "BUG-001" in valid
    assert "FEAT-010" in valid
    assert "NONEXISTENT" not in valid


def test_sprint_yaml_format(sprint_project: BRConfig, tmp_path: Path) -> None:
    """Test sprint YAML file format matches specification."""
    import yaml

    manager = SprintManager(sprints_dir=tmp_path, config=sprint_project)

    manager.create(
        name="test-sprint",
        issues=["BUG-001"],
        description="Test sprint",
    )

    # Read YAML file
    yaml_path = tmp_path / "test-sprint.yaml"
    content = yaml_path.read_text()

    # Verify structure
    assert "name: test-sprint" in content
    assert "description: Test sprint" in content
    assert "issues:" in content
    assert "- BUG-001" in content
    assert "created:" in content

    # Parse and verify
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    assert data["name"] == "test-sprint"
    assert data["description"] == "Test sprint"
    assert data["issues"] == ["BUG-001"]
    assert "created" in data
