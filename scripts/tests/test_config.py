"""Tests for little_loops.config module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from little_loops.config import (
    DEFAULT_CATEGORIES,
    REQUIRED_CATEGORIES,
    AutomationConfig,
    BRConfig,
    CategoryConfig,
    CommandsConfig,
    GitHubSyncConfig,
    IssuesConfig,
    ParallelAutomationConfig,
    ProjectConfig,
    ScanConfig,
    SprintsConfig,
    SyncConfig,
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
        # User specified bugs, required categories (features, enhancements) are auto-added
        assert len(config.categories) == 3
        assert config.categories["bugs"].prefix == "BUG"
        assert "features" in config.categories
        assert "enhancements" in config.categories
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


class TestSprintsConfig:
    """Tests for SprintsConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating SprintsConfig with all fields."""
        data = {
            "sprints_dir": "custom-sprints/",
            "default_timeout": 7200,
            "default_max_workers": 8,
        }
        config = SprintsConfig.from_dict(data)

        assert config.sprints_dir == "custom-sprints/"
        assert config.default_timeout == 7200
        assert config.default_max_workers == 8

    def test_from_dict_with_defaults(self) -> None:
        """Test creating SprintsConfig with default values."""
        config = SprintsConfig.from_dict({})

        assert config.sprints_dir == ".sprints"
        assert config.default_timeout == 3600
        assert config.default_max_workers == 2


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

    def test_project_name_defaults_to_directory_name(self, temp_project_dir: Path) -> None:
        """Test that project name defaults to directory name."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps({"project": {}}))

        config = BRConfig(temp_project_dir)

        assert config.project.name == temp_project_dir.name

    def test_get_issue_dir(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
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

    def test_get_completed_dir(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
        """Test get_completed_dir returns correct path."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        completed = config.get_completed_dir()
        assert completed.resolve() == (temp_project_dir / ".issues" / "completed").resolve()

    def test_get_issue_prefix(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
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

    def test_get_src_path(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
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

    def test_to_dict(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
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

    def test_resolve_variable(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
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

    def test_create_parallel_config_with_overrides(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test create_parallel_config with overrides."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        parallel_config = config.create_parallel_config(
            max_workers=8,
            dry_run=True,
            max_issues=10,
        )

        assert parallel_config.max_workers == 8
        assert parallel_config.dry_run is True
        assert parallel_config.max_issues == 10


class TestBRConfigAliases:
    """Tests for backwards compatibility aliases."""

    def test_clconfig_alias(self) -> None:
        """Test CLConfig is an alias for BRConfig."""
        from little_loops.config import CLConfig

        assert CLConfig is BRConfig


class TestCategoryConstants:
    """Tests for REQUIRED_CATEGORIES and DEFAULT_CATEGORIES constants."""

    def test_required_categories_contains_core_types(self) -> None:
        """Test that REQUIRED_CATEGORIES has bugs, features, enhancements."""
        assert "bugs" in REQUIRED_CATEGORIES
        assert "features" in REQUIRED_CATEGORIES
        assert "enhancements" in REQUIRED_CATEGORIES
        assert REQUIRED_CATEGORIES["bugs"]["prefix"] == "BUG"
        assert REQUIRED_CATEGORIES["features"]["prefix"] == "FEAT"
        assert REQUIRED_CATEGORIES["enhancements"]["prefix"] == "ENH"

    def test_default_categories_includes_required(self) -> None:
        """Test that DEFAULT_CATEGORIES includes all required categories."""
        for key in REQUIRED_CATEGORIES:
            assert key in DEFAULT_CATEGORIES


class TestIssuesConfigValidation:
    """Tests for required category validation."""

    def test_required_categories_always_present_empty_config(self) -> None:
        """Test that required categories exist with empty config."""
        config = IssuesConfig.from_dict({})

        assert "bugs" in config.categories
        assert "features" in config.categories
        assert "enhancements" in config.categories

    def test_required_categories_merged_with_custom(self) -> None:
        """Test that custom categories are merged with required."""
        data = {
            "categories": {
                "documentation": {"prefix": "DOC", "dir": "docs", "action": "document"},
            }
        }
        config = IssuesConfig.from_dict(data)

        # Custom category present
        assert "documentation" in config.categories
        assert config.categories["documentation"].prefix == "DOC"

        # Required categories also present
        assert "bugs" in config.categories
        assert "features" in config.categories
        assert "enhancements" in config.categories

    def test_user_can_override_required_category_settings(self) -> None:
        """Test that user can customize required category settings."""
        data = {
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bug-reports", "action": "resolve"},
            }
        }
        config = IssuesConfig.from_dict(data)

        # User's customization applied
        assert config.categories["bugs"].dir == "bug-reports"
        assert config.categories["bugs"].action == "resolve"

        # Other required categories still present
        assert "features" in config.categories
        assert "enhancements" in config.categories


class TestIssuesConfigHelperMethods:
    """Tests for IssuesConfig helper methods."""

    def test_get_category_by_prefix_found(self) -> None:
        """Test get_category_by_prefix returns category when found."""
        config = IssuesConfig.from_dict({})

        result = config.get_category_by_prefix("BUG")

        assert result is not None
        assert result.prefix == "BUG"
        assert result.dir == "bugs"

    def test_get_category_by_prefix_not_found(self) -> None:
        """Test get_category_by_prefix returns None when not found."""
        config = IssuesConfig.from_dict({})

        result = config.get_category_by_prefix("UNKNOWN")

        assert result is None

    def test_get_category_by_dir_found(self) -> None:
        """Test get_category_by_dir returns category when found."""
        config = IssuesConfig.from_dict({})

        result = config.get_category_by_dir("features")

        assert result is not None
        assert result.prefix == "FEAT"
        assert result.dir == "features"

    def test_get_category_by_dir_not_found(self) -> None:
        """Test get_category_by_dir returns None when not found."""
        config = IssuesConfig.from_dict({})

        result = config.get_category_by_dir("unknown")

        assert result is None

    def test_get_all_prefixes(self) -> None:
        """Test get_all_prefixes returns all configured prefixes."""
        config = IssuesConfig.from_dict({})

        prefixes = config.get_all_prefixes()

        assert "BUG" in prefixes
        assert "FEAT" in prefixes
        assert "ENH" in prefixes

    def test_get_all_dirs(self) -> None:
        """Test get_all_dirs returns all configured directories."""
        config = IssuesConfig.from_dict({})

        dirs = config.get_all_dirs()

        assert "bugs" in dirs
        assert "features" in dirs
        assert "enhancements" in dirs

    def test_get_all_prefixes_with_custom_category(self) -> None:
        """Test get_all_prefixes includes custom categories."""
        data = {
            "categories": {
                "documentation": {"prefix": "DOC", "dir": "docs", "action": "document"},
            }
        }
        config = IssuesConfig.from_dict(data)

        prefixes = config.get_all_prefixes()

        assert "DOC" in prefixes
        # Required categories also present
        assert "BUG" in prefixes
        assert "FEAT" in prefixes
        assert "ENH" in prefixes


class TestGitHubSyncConfig:
    """Tests for GitHubSyncConfig dataclass."""

    def test_from_dict_with_defaults(self) -> None:
        """Test creating GitHubSyncConfig with default values."""
        config = GitHubSyncConfig.from_dict({})

        assert config.repo is None
        assert config.label_mapping == {"BUG": "bug", "FEAT": "enhancement", "ENH": "enhancement"}
        assert config.priority_labels is True
        assert config.sync_completed is False
        assert config.state_file == ".claude/ll-sync-state.json"

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating GitHubSyncConfig with all fields specified."""
        data = {
            "repo": "owner/repo",
            "label_mapping": {"BUG": "defect", "FEAT": "feature"},
            "priority_labels": False,
            "sync_completed": True,
            "state_file": "custom-sync-state.json",
        }
        config = GitHubSyncConfig.from_dict(data)

        assert config.repo == "owner/repo"
        assert config.label_mapping == {"BUG": "defect", "FEAT": "feature"}
        assert config.priority_labels is False
        assert config.sync_completed is True
        assert config.state_file == "custom-sync-state.json"

    def test_from_dict_partial_label_mapping(self) -> None:
        """Test that partial label_mapping replaces default entirely."""
        data = {"label_mapping": {"BUG": "defect"}}
        config = GitHubSyncConfig.from_dict(data)

        # Partial mapping replaces default (doesn't merge)
        assert config.label_mapping == {"BUG": "defect"}


class TestSyncConfig:
    """Tests for SyncConfig dataclass."""

    def test_from_dict_with_defaults(self) -> None:
        """Test creating SyncConfig with default values."""
        config = SyncConfig.from_dict({})

        assert config.enabled is False
        assert config.provider == "github"
        assert isinstance(config.github, GitHubSyncConfig)
        assert config.github.repo is None

    def test_from_dict_enabled(self) -> None:
        """Test creating SyncConfig with enabled flag."""
        config = SyncConfig.from_dict({"enabled": True})

        assert config.enabled is True
        assert config.provider == "github"

    def test_from_dict_with_github_settings(self) -> None:
        """Test creating SyncConfig with GitHub settings."""
        data = {
            "enabled": True,
            "github": {
                "repo": "myorg/myrepo",
                "priority_labels": False,
            },
        }
        config = SyncConfig.from_dict(data)

        assert config.enabled is True
        assert config.github.repo == "myorg/myrepo"
        assert config.github.priority_labels is False
        # Other github defaults preserved
        assert config.github.sync_completed is False

    def test_from_dict_alternative_provider(self) -> None:
        """Test creating SyncConfig with different provider value."""
        config = SyncConfig.from_dict({"provider": "github"})

        assert config.provider == "github"


class TestBRConfigSyncIntegration:
    """Tests for BRConfig sync property integration."""

    def test_sync_property_exists(self, temp_project_dir: Path) -> None:
        """Test that BRConfig has sync property."""
        config = BRConfig(temp_project_dir)

        assert hasattr(config, "sync")
        assert isinstance(config.sync, SyncConfig)

    def test_sync_property_with_defaults(self, temp_project_dir: Path) -> None:
        """Test sync property returns defaults when not configured."""
        config = BRConfig(temp_project_dir)

        assert config.sync.enabled is False
        assert config.sync.provider == "github"
        assert config.sync.github.repo is None

    def test_sync_property_loads_from_config(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test sync property loads from config file."""
        sample_config["sync"] = {
            "enabled": True,
            "github": {
                "repo": "test/repo",
                "priority_labels": True,
            },
        }
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.sync.enabled is True
        assert config.sync.github.repo == "test/repo"

    def test_sync_in_to_dict(self, temp_project_dir: Path) -> None:
        """Test sync config appears in to_dict output."""
        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        assert "sync" in result
        assert "enabled" in result["sync"]
        assert "provider" in result["sync"]
        assert "github" in result["sync"]
        assert "repo" in result["sync"]["github"]
        assert "label_mapping" in result["sync"]["github"]

    def test_sync_to_dict_serializable(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test that sync config in to_dict is JSON serializable."""
        sample_config["sync"] = {
            "enabled": True,
            "github": {
                "repo": "owner/repo",
                "label_mapping": {"BUG": "bug", "FEAT": "feature"},
            },
        }
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        # Should not raise
        json.dumps(result)

    def test_resolve_variable_sync(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test resolve_variable works for sync config paths."""
        sample_config["sync"] = {"enabled": True}
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.resolve_variable("sync.enabled") == "True"
        assert config.resolve_variable("sync.provider") == "github"
