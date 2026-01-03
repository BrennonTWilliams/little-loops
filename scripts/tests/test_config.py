"""Tests for little_loops.config module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from little_loops.config import (
    AutomationConfig,
    BRConfig,
    CategoryConfig,
    CommandsConfig,
    IssuesConfig,
    ParallelAutomationConfig,
    ProjectConfig,
    ScanConfig,
)


class TestCategoryConfig:
    """Tests for CategoryConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating CategoryConfig with all fields specified."""
        data = {"prefix": "TST", "dir": "test-issues", "action": "verify"}
        config = CategoryConfig.from_dict("tests", data)

        assert config.prefix == "TST"
        assert config.dir == "test-issues"
        assert config.action == "verify"

    def test_from_dict_with_defaults(self) -> None:
        """Test creating CategoryConfig with default values."""
        config = CategoryConfig.from_dict("mytype", {})

        assert config.prefix == "MYT"  # First 3 chars of key uppercased
        assert config.dir == "mytype"
        assert config.action == "fix"

    def test_from_dict_partial_data(self) -> None:
        """Test creating CategoryConfig with partial data."""
        data = {"prefix": "CUSTOM"}
        config = CategoryConfig.from_dict("bugs", data)

        assert config.prefix == "CUSTOM"
        assert config.dir == "bugs"
        assert config.action == "fix"


class TestProjectConfig:
    """Tests for ProjectConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating ProjectConfig with all fields specified."""
        data = {
            "name": "my-project",
            "src_dir": "lib/",
            "test_cmd": "npm test",
            "lint_cmd": "eslint .",
            "type_cmd": "tsc --noEmit",
            "format_cmd": "prettier --write .",
            "build_cmd": "npm run build",
        }
        config = ProjectConfig.from_dict(data)

        assert config.name == "my-project"
        assert config.src_dir == "lib/"
        assert config.test_cmd == "npm test"
        assert config.lint_cmd == "eslint ."
        assert config.type_cmd == "tsc --noEmit"
        assert config.format_cmd == "prettier --write ."
        assert config.build_cmd == "npm run build"

    def test_from_dict_with_defaults(self) -> None:
        """Test creating ProjectConfig with default values."""
        config = ProjectConfig.from_dict({})

        assert config.name == ""
        assert config.src_dir == "src/"
        assert config.test_cmd == "pytest"
        assert config.lint_cmd == "ruff check ."
        assert config.type_cmd == "mypy"
        assert config.format_cmd == "ruff format ."
        assert config.build_cmd is None


class TestIssuesConfig:
    """Tests for IssuesConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating IssuesConfig with all fields."""
        data = {
            "base_dir": "issues/",
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
            },
            "completed_dir": "done",
            "priorities": ["P0", "P1"],
            "templates_dir": "templates/",
        }
        config = IssuesConfig.from_dict(data)

        assert config.base_dir == "issues/"
        assert len(config.categories) == 1
        assert config.categories["bugs"].prefix == "BUG"
        assert config.completed_dir == "done"
        assert config.priorities == ["P0", "P1"]
        assert config.templates_dir == "templates/"

    def test_from_dict_with_defaults(self) -> None:
        """Test creating IssuesConfig with default values."""
        config = IssuesConfig.from_dict({})

        assert config.base_dir == ".issues"
        assert len(config.categories) == 3  # bugs, features, enhancements
        assert "bugs" in config.categories
        assert "features" in config.categories
        assert "enhancements" in config.categories
        assert config.completed_dir == "completed"
        assert config.priorities == ["P0", "P1", "P2", "P3", "P4", "P5"]
        assert config.templates_dir is None


class TestAutomationConfig:
    """Tests for AutomationConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating AutomationConfig with all fields."""
        data = {
            "timeout_seconds": 7200,
            "state_file": "custom-state.json",
            "worktree_base": "wt/",
            "max_workers": 4,
            "stream_output": False,
        }
        config = AutomationConfig.from_dict(data)

        assert config.timeout_seconds == 7200
        assert config.state_file == "custom-state.json"
        assert config.worktree_base == "wt/"
        assert config.max_workers == 4
        assert config.stream_output is False

    def test_from_dict_with_defaults(self) -> None:
        """Test creating AutomationConfig with default values."""
        config = AutomationConfig.from_dict({})

        assert config.timeout_seconds == 3600
        assert config.state_file == ".auto-manage-state.json"
        assert config.worktree_base == ".worktrees"
        assert config.max_workers == 2
        assert config.stream_output is True


class TestParallelAutomationConfig:
    """Tests for ParallelAutomationConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating ParallelAutomationConfig with all fields."""
        data = {
            "max_workers": 5,
            "p0_sequential": False,
            "worktree_base": "parallel-wt/",
            "state_file": "parallel.json",
            "timeout_seconds": 900,
            "max_merge_retries": 5,
            "include_p0": True,
            "stream_output": True,
            "command_prefix": "/custom:",
            "ready_command": "check {{issue_id}}",
            "manage_command": "process {{issue_type}} {{action}} {{issue_id}}",
        }
        config = ParallelAutomationConfig.from_dict(data)

        # Base config fields (shared via composition)
        assert config.base.max_workers == 5
        assert config.base.worktree_base == "parallel-wt/"
        assert config.base.state_file == "parallel.json"
        assert config.base.timeout_seconds == 900
        assert config.base.stream_output is True
        # Parallel-specific fields
        assert config.p0_sequential is False
        assert config.max_merge_retries == 5
        assert config.include_p0 is True
        assert config.command_prefix == "/custom:"
        assert config.ready_command == "check {{issue_id}}"

    def test_from_dict_with_defaults(self) -> None:
        """Test creating ParallelAutomationConfig with default values."""
        config = ParallelAutomationConfig.from_dict({})

        # Base config defaults (parallel-specific defaults differ from AutomationConfig)
        assert config.base.max_workers == 2
        assert config.base.state_file == ".parallel-manage-state.json"
        assert config.base.stream_output is False  # Different from AutomationConfig default
        # Parallel-specific defaults
        assert config.p0_sequential is True
        assert config.include_p0 is False
        assert config.command_prefix == "/ll:"


class TestCommandsConfig:
    """Tests for CommandsConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating CommandsConfig with all fields."""
        data = {
            "pre_implement": "npm run lint",
            "post_implement": "npm run build",
            "custom_verification": ["npm test", "npm run e2e"],
        }
        config = CommandsConfig.from_dict(data)

        assert config.pre_implement == "npm run lint"
        assert config.post_implement == "npm run build"
        assert config.custom_verification == ["npm test", "npm run e2e"]

    def test_from_dict_with_defaults(self) -> None:
        """Test creating CommandsConfig with default values."""
        config = CommandsConfig.from_dict({})

        assert config.pre_implement is None
        assert config.post_implement is None
        assert config.custom_verification == []


class TestScanConfig:
    """Tests for ScanConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating ScanConfig with all fields."""
        data = {
            "focus_dirs": ["lib/", "app/"],
            "exclude_patterns": ["**/vendor/**"],
            "custom_agents": ["security-scanner"],
        }
        config = ScanConfig.from_dict(data)

        assert config.focus_dirs == ["lib/", "app/"]
        assert config.exclude_patterns == ["**/vendor/**"]
        assert config.custom_agents == ["security-scanner"]

    def test_from_dict_with_defaults(self) -> None:
        """Test creating ScanConfig with default values."""
        config = ScanConfig.from_dict({})

        assert config.focus_dirs == ["src/", "tests/"]
        assert "**/node_modules/**" in config.exclude_patterns
        assert "**/__pycache__/**" in config.exclude_patterns
        assert config.custom_agents == []


class TestBRConfig:
    """Tests for the main BRConfig class."""

    def test_load_config_from_file(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test loading configuration from file."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.project.name == "test-project"
        assert config.project.src_dir == "src/"
        assert config.issues.base_dir == ".issues"
        assert config.automation.timeout_seconds == 1800
        assert config.parallel.base.max_workers == 3

    def test_load_config_without_file(self, temp_project_dir: Path) -> None:
        """Test loading configuration when no file exists (uses defaults)."""
        config = BRConfig(temp_project_dir)

        # Should use defaults
        assert config.project.name == temp_project_dir.name
        assert config.project.src_dir == "src/"
        assert config.issues.base_dir == ".issues"
        assert len(config.issues.categories) == 3

    def test_project_name_defaults_to_directory_name(
        self, temp_project_dir: Path
    ) -> None:
        """Test that project name defaults to directory name."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps({"project": {}}))

        config = BRConfig(temp_project_dir)

        assert config.project.name == temp_project_dir.name

    def test_get_issue_dir(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test get_issue_dir returns correct path."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        bugs_dir = config.get_issue_dir("bugs")
        # Use resolve() to handle macOS /var -> /private/var symlinks
        assert bugs_dir.resolve() == (temp_project_dir / ".issues" / "bugs").resolve()

        features_dir = config.get_issue_dir("features")
        assert features_dir.resolve() == (temp_project_dir / ".issues" / "features").resolve()

    def test_get_issue_dir_unknown_category(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test get_issue_dir with unknown category uses category as dir name."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        unknown_dir = config.get_issue_dir("unknown")
        assert unknown_dir.resolve() == (temp_project_dir / ".issues" / "unknown").resolve()

    def test_get_completed_dir(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test get_completed_dir returns correct path."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        completed = config.get_completed_dir()
        assert completed.resolve() == (temp_project_dir / ".issues" / "completed").resolve()

    def test_get_issue_prefix(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test get_issue_prefix returns correct prefix."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.get_issue_prefix("bugs") == "BUG"
        assert config.get_issue_prefix("features") == "FEAT"
        assert config.get_issue_prefix("unknown") == "UNK"  # First 3 chars

    def test_get_category_action(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test get_category_action returns correct action."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.get_category_action("bugs") == "fix"
        assert config.get_category_action("features") == "implement"
        assert config.get_category_action("unknown") == "fix"  # Default

    def test_get_src_path(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test get_src_path returns correct path."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        # Use resolve() to handle macOS /var -> /private/var symlinks
        assert config.get_src_path().resolve() == (temp_project_dir / "src/").resolve()

    def test_issue_categories_property(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test issue_categories property returns category names."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        categories = config.issue_categories
        assert "bugs" in categories
        assert "features" in categories

    def test_issue_priorities_property(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test issue_priorities property returns priorities."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        priorities = config.issue_priorities
        assert priorities == ["P0", "P1", "P2", "P3"]

    def test_to_dict(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test to_dict returns serializable dictionary."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        assert result["project"]["name"] == "test-project"
        assert result["issues"]["base_dir"] == ".issues"
        assert result["automation"]["timeout_seconds"] == 1800
        assert result["parallel"]["max_workers"] == 3

        # Should be JSON serializable
        json.dumps(result)

    def test_resolve_variable(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test resolve_variable resolves config paths."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.resolve_variable("project.name") == "test-project"
        assert config.resolve_variable("project.src_dir") == "src/"
        assert config.resolve_variable("issues.base_dir") == ".issues"
        assert config.resolve_variable("automation.timeout_seconds") == "1800"

    def test_resolve_variable_not_found(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test resolve_variable returns None for unknown paths."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.resolve_variable("nonexistent.path") is None
        assert config.resolve_variable("project.nonexistent") is None

    def test_resolve_variable_list(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test resolve_variable joins list values with spaces."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        result = config.resolve_variable("issues.priorities")
        assert result == "P0 P1 P2 P3"

    def test_create_parallel_config(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test create_parallel_config creates ParallelConfig."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        parallel_config = config.create_parallel_config()

        assert parallel_config.max_workers == 3
        assert parallel_config.p0_sequential is True
        assert parallel_config.include_p0 is False

    def test_create_parallel_config_with_overrides(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test create_parallel_config with overrides."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        parallel_config = config.create_parallel_config(
            max_workers=8,
            include_p0=True,
            dry_run=True,
            max_issues=10,
        )

        assert parallel_config.max_workers == 8
        assert parallel_config.include_p0 is True
        assert parallel_config.dry_run is True
        assert parallel_config.max_issues == 10


class TestBRConfigAliases:
    """Tests for backwards compatibility aliases."""

    def test_clconfig_alias(self) -> None:
        """Test CLConfig is an alias for BRConfig."""
        from little_loops.config import CLConfig

        assert CLConfig is BRConfig
