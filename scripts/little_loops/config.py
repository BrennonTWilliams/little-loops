"""Configuration management for little-loops.

Provides the BRConfig class for loading, merging, and accessing project configuration.
Configuration is read from .claude/ll-config.json and merged with sensible defaults.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from little_loops.parallel.types import ParallelConfig


@dataclass
class CategoryConfig:
    """Configuration for an issue category."""

    prefix: str
    dir: str
    action: str = "fix"

    @classmethod
    def from_dict(cls, key: str, data: dict[str, Any]) -> CategoryConfig:
        """Create CategoryConfig from dictionary."""
        return cls(
            prefix=data.get("prefix", key.upper()[:3]),
            dir=data.get("dir", key),
            action=data.get("action", "fix"),
        )


@dataclass
class ProjectConfig:
    """Project-level configuration."""

    name: str = ""
    src_dir: str = "src/"
    test_cmd: str = "pytest"
    lint_cmd: str = "ruff check ."
    type_cmd: str | None = "mypy"
    format_cmd: str | None = "ruff format ."
    build_cmd: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectConfig:
        """Create ProjectConfig from dictionary."""
        return cls(
            name=data.get("name", ""),
            src_dir=data.get("src_dir", "src/"),
            test_cmd=data.get("test_cmd", "pytest"),
            lint_cmd=data.get("lint_cmd", "ruff check ."),
            type_cmd=data.get("type_cmd", "mypy"),
            format_cmd=data.get("format_cmd", "ruff format ."),
            build_cmd=data.get("build_cmd"),
        )


@dataclass
class IssuesConfig:
    """Issue management configuration."""

    base_dir: str = ".issues"
    categories: dict[str, CategoryConfig] = field(default_factory=dict)
    completed_dir: str = "completed"
    priorities: list[str] = field(default_factory=lambda: ["P0", "P1", "P2", "P3", "P4", "P5"])
    templates_dir: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IssuesConfig:
        """Create IssuesConfig from dictionary."""
        categories_data = data.get("categories", {
            "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
            "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
            "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
        })
        categories = {
            key: CategoryConfig.from_dict(key, value)
            for key, value in categories_data.items()
        }
        return cls(
            base_dir=data.get("base_dir", ".issues"),
            categories=categories,
            completed_dir=data.get("completed_dir", "completed"),
            priorities=data.get("priorities", ["P0", "P1", "P2", "P3", "P4", "P5"]),
            templates_dir=data.get("templates_dir"),
        )


@dataclass
class AutomationConfig:
    """Automation script configuration."""

    timeout_seconds: int = 3600
    state_file: str = ".auto-manage-state.json"
    worktree_base: str = ".worktrees"
    max_workers: int = 2
    stream_output: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutomationConfig:
        """Create AutomationConfig from dictionary."""
        return cls(
            timeout_seconds=data.get("timeout_seconds", 3600),
            state_file=data.get("state_file", ".auto-manage-state.json"),
            worktree_base=data.get("worktree_base", ".worktrees"),
            max_workers=data.get("max_workers", 2),
            stream_output=data.get("stream_output", True),
        )


@dataclass
class ParallelAutomationConfig:
    """Parallel automation configuration.

    Extends AutomationConfig with parallel-specific settings.
    """

    max_workers: int = 2
    p0_sequential: bool = True
    worktree_base: str = ".worktrees"
    state_file: str = ".parallel-manage-state.json"
    timeout_per_issue: int = 3600
    max_merge_retries: int = 2
    include_p0: bool = False
    stream_subprocess_output: bool = False
    command_prefix: str = "/ll:"
    ready_command: str = "ready_issue {{issue_id}}"
    manage_command: str = "manage_issue {{issue_type}} {{action}} {{issue_id}}"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParallelAutomationConfig:
        """Create ParallelAutomationConfig from dictionary."""
        return cls(
            max_workers=data.get("max_workers", 2),
            p0_sequential=data.get("p0_sequential", True),
            worktree_base=data.get("worktree_base", ".worktrees"),
            state_file=data.get("state_file", ".parallel-manage-state.json"),
            timeout_per_issue=data.get("timeout_per_issue", 3600),
            max_merge_retries=data.get("max_merge_retries", 2),
            include_p0=data.get("include_p0", False),
            stream_subprocess_output=data.get("stream_subprocess_output", False),
            command_prefix=data.get("command_prefix", "/ll:"),
            ready_command=data.get("ready_command", "ready_issue {{issue_id}}"),
            manage_command=data.get(
                "manage_command", "manage_issue {{issue_type}} {{action}} {{issue_id}}"
            ),
        )


@dataclass
class CommandsConfig:
    """Command customization configuration."""

    pre_implement: str | None = None
    post_implement: str | None = None
    custom_verification: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommandsConfig:
        """Create CommandsConfig from dictionary."""
        return cls(
            pre_implement=data.get("pre_implement"),
            post_implement=data.get("post_implement"),
            custom_verification=data.get("custom_verification", []),
        )


@dataclass
class ScanConfig:
    """Codebase scanning configuration."""

    focus_dirs: list[str] = field(default_factory=lambda: ["src/", "tests/"])
    exclude_patterns: list[str] = field(
        default_factory=lambda: ["**/node_modules/**", "**/__pycache__/**", "**/.git/**"]
    )
    custom_agents: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScanConfig:
        """Create ScanConfig from dictionary."""
        return cls(
            focus_dirs=data.get("focus_dirs", ["src/", "tests/"]),
            exclude_patterns=data.get(
                "exclude_patterns",
                ["**/node_modules/**", "**/__pycache__/**", "**/.git/**"],
            ),
            custom_agents=data.get("custom_agents", []),
        )


class BRConfig:
    """Main configuration class for little-loops.

    Loads configuration from .claude/ll-config.json and merges with defaults.
    Provides convenient property access to all configuration values.

    Example:
        config = BRConfig(Path.cwd())
        print(config.project.src_dir)  # "src/"
        print(config.issues.base_dir)  # ".issues"
        print(config.get_issue_dir("bugs"))  # Path(".issues/bugs")
    """

    CONFIG_FILENAME = "ll-config.json"
    CONFIG_DIR = ".claude"

    def __init__(self, project_root: Path) -> None:
        """Initialize configuration from project root.

        Args:
            project_root: Path to the project root directory
        """
        self.project_root = project_root.resolve()
        self._raw_config = self._load_config()
        self._parse_config()

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from file."""
        config_path = self.project_root / self.CONFIG_DIR / self.CONFIG_FILENAME
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                return cast(dict[str, Any], json.load(f))
        return {}

    def _parse_config(self) -> None:
        """Parse raw config into typed dataclasses."""
        self._project = ProjectConfig.from_dict(self._raw_config.get("project", {}))
        if not self._project.name:
            self._project.name = self.project_root.name

        self._issues = IssuesConfig.from_dict(self._raw_config.get("issues", {}))
        self._automation = AutomationConfig.from_dict(self._raw_config.get("automation", {}))
        self._parallel = ParallelAutomationConfig.from_dict(
            self._raw_config.get("parallel", {})
        )
        self._commands = CommandsConfig.from_dict(self._raw_config.get("commands", {}))
        self._scan = ScanConfig.from_dict(self._raw_config.get("scan", {}))

    @property
    def project(self) -> ProjectConfig:
        """Get project configuration."""
        return self._project

    @property
    def issues(self) -> IssuesConfig:
        """Get issues configuration."""
        return self._issues

    @property
    def automation(self) -> AutomationConfig:
        """Get automation configuration."""
        return self._automation

    @property
    def parallel(self) -> ParallelAutomationConfig:
        """Get parallel automation configuration."""
        return self._parallel

    @property
    def commands(self) -> CommandsConfig:
        """Get commands configuration."""
        return self._commands

    @property
    def scan(self) -> ScanConfig:
        """Get scan configuration."""
        return self._scan

    # Convenience methods for common operations

    def get_issue_dir(self, category: str) -> Path:
        """Get the directory path for an issue category.

        Args:
            category: Category key (e.g., "bugs", "features")

        Returns:
            Path to the issue category directory
        """
        if category in self._issues.categories:
            dir_name = self._issues.categories[category].dir
        else:
            dir_name = category
        return self.project_root / self._issues.base_dir / dir_name

    def get_completed_dir(self) -> Path:
        """Get the path to the completed issues directory."""
        return self.project_root / self._issues.base_dir / self._issues.completed_dir

    def get_issue_prefix(self, category: str) -> str:
        """Get the issue ID prefix for a category.

        Args:
            category: Category key (e.g., "bugs", "features")

        Returns:
            Issue prefix (e.g., "BUG", "FEAT")
        """
        if category in self._issues.categories:
            return self._issues.categories[category].prefix
        return category.upper()[:3]

    def get_category_action(self, category: str) -> str:
        """Get the default action for a category.

        Args:
            category: Category key (e.g., "bugs", "features")

        Returns:
            Action verb (e.g., "fix", "implement")
        """
        if category in self._issues.categories:
            return self._issues.categories[category].action
        return "fix"

    def get_src_path(self) -> Path:
        """Get the source directory path."""
        return self.project_root / self._project.src_dir

    def get_worktree_base(self) -> Path:
        """Get the worktree base directory path."""
        return self.project_root / self._automation.worktree_base

    def get_state_file(self) -> Path:
        """Get the state file path."""
        return self.project_root / self._automation.state_file

    def get_parallel_state_file(self) -> Path:
        """Get the parallel state file path."""
        return self.project_root / self._parallel.state_file

    def create_parallel_config(
        self,
        *,
        max_workers: int | None = None,
        priority_filter: list[str] | None = None,
        max_issues: int = 0,
        dry_run: bool = False,
        include_p0: bool | None = None,
        timeout_per_issue: int | None = None,
        stream_subprocess_output: bool | None = None,
        show_model: bool | None = None,
    ) -> ParallelConfig:
        """Create a ParallelConfig from BRConfig settings with optional overrides.

        Args:
            max_workers: Override max_workers (default: from config)
            priority_filter: Override priority filter (default: from issues config)
            max_issues: Maximum issues to process (default: 0 = unlimited)
            dry_run: Preview mode (default: False)
            include_p0: Include P0 in parallel (default: from config)
            timeout_per_issue: Per-issue timeout (default: from config)
            stream_subprocess_output: Stream output (default: from config)
            show_model: Make API call to verify model (default: False)

        Returns:
            ParallelConfig configured from BRConfig
        """
        from little_loops.parallel.types import ParallelConfig

        return ParallelConfig(
            max_workers=max_workers or self._parallel.max_workers,
            p0_sequential=self._parallel.p0_sequential,
            worktree_base=Path(self._parallel.worktree_base),
            state_file=Path(self._parallel.state_file),
            max_merge_retries=self._parallel.max_merge_retries,
            priority_filter=priority_filter or self._issues.priorities,
            max_issues=max_issues,
            dry_run=dry_run,
            timeout_per_issue=timeout_per_issue or self._parallel.timeout_per_issue,
            include_p0=include_p0 if include_p0 is not None else self._parallel.include_p0,
            stream_subprocess_output=(
                stream_subprocess_output
                if stream_subprocess_output is not None
                else self._parallel.stream_subprocess_output
            ),
            show_model=show_model if show_model is not None else False,
            command_prefix=self._parallel.command_prefix,
            ready_command=self._parallel.ready_command,
            manage_command=self._parallel.manage_command,
        )

    @property
    def issue_categories(self) -> list[str]:
        """Get list of configured issue category names."""
        return list(self._issues.categories.keys())

    @property
    def issue_priorities(self) -> list[str]:
        """Get list of valid priority prefixes."""
        return self._issues.priorities

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.

        Useful for variable substitution in command templates.
        """
        return {
            "project": {
                "name": self._project.name,
                "src_dir": self._project.src_dir,
                "test_cmd": self._project.test_cmd,
                "lint_cmd": self._project.lint_cmd,
                "type_cmd": self._project.type_cmd,
                "format_cmd": self._project.format_cmd,
                "build_cmd": self._project.build_cmd,
            },
            "issues": {
                "base_dir": self._issues.base_dir,
                "categories": {
                    k: {"prefix": v.prefix, "dir": v.dir, "action": v.action}
                    for k, v in self._issues.categories.items()
                },
                "completed_dir": self._issues.completed_dir,
                "priorities": self._issues.priorities,
                "templates_dir": self._issues.templates_dir,
            },
            "automation": {
                "timeout_seconds": self._automation.timeout_seconds,
                "state_file": self._automation.state_file,
                "worktree_base": self._automation.worktree_base,
                "max_workers": self._automation.max_workers,
                "stream_output": self._automation.stream_output,
            },
            "parallel": {
                "max_workers": self._parallel.max_workers,
                "p0_sequential": self._parallel.p0_sequential,
                "worktree_base": self._parallel.worktree_base,
                "state_file": self._parallel.state_file,
                "timeout_per_issue": self._parallel.timeout_per_issue,
                "max_merge_retries": self._parallel.max_merge_retries,
                "include_p0": self._parallel.include_p0,
                "stream_subprocess_output": self._parallel.stream_subprocess_output,
                "command_prefix": self._parallel.command_prefix,
                "ready_command": self._parallel.ready_command,
                "manage_command": self._parallel.manage_command,
            },
            "commands": {
                "pre_implement": self._commands.pre_implement,
                "post_implement": self._commands.post_implement,
                "custom_verification": self._commands.custom_verification,
            },
            "scan": {
                "focus_dirs": self._scan.focus_dirs,
                "exclude_patterns": self._scan.exclude_patterns,
                "custom_agents": self._scan.custom_agents,
            },
        }

    def resolve_variable(self, var_path: str) -> str | None:
        """Resolve a variable path like 'project.src_dir' to its value.

        Args:
            var_path: Dot-separated path to configuration value

        Returns:
            The resolved value as a string, or None if not found
        """
        parts = var_path.split(".")
        value: Any = self.to_dict()

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None

        if value is None:
            return None
        if isinstance(value, list):
            return " ".join(str(v) for v in value)
        return str(value)


# Backwards compatibility alias
CLConfig = BRConfig
