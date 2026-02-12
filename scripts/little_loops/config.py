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

__all__ = [
    "BRConfig",
    "CLConfig",
    "CategoryConfig",
    "ProjectConfig",
    "IssuesConfig",
    "AutomationConfig",
    "ParallelAutomationConfig",
    "CommandsConfig",
    "ScanConfig",
    "SprintsConfig",
    "LoopsConfig",
    "GitHubSyncConfig",
    "SyncConfig",
    "REQUIRED_CATEGORIES",
    "DEFAULT_CATEGORIES",
]

# Required categories that must always exist (cannot be removed by user config)
REQUIRED_CATEGORIES: dict[str, dict[str, str]] = {
    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
    "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
}

# Default categories (same as required by default, could include optional defaults)
DEFAULT_CATEGORIES: dict[str, dict[str, str]] = {
    **REQUIRED_CATEGORIES,
}


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
    run_cmd: str | None = None

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
            run_cmd=data.get("run_cmd"),
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
        """Create IssuesConfig from dictionary.

        Required categories (bugs, features, enhancements) are automatically
        included if not specified in user config.
        """
        # Start with user categories or empty dict
        categories_data = dict(data.get("categories", {}))

        # Ensure required categories exist (merge with defaults)
        for key, defaults in REQUIRED_CATEGORIES.items():
            if key not in categories_data:
                categories_data[key] = defaults

        categories = {
            key: CategoryConfig.from_dict(key, value) for key, value in categories_data.items()
        }
        return cls(
            base_dir=data.get("base_dir", ".issues"),
            categories=categories,
            completed_dir=data.get("completed_dir", "completed"),
            priorities=data.get("priorities", ["P0", "P1", "P2", "P3", "P4", "P5"]),
            templates_dir=data.get("templates_dir"),
        )

    def get_category_by_prefix(self, prefix: str) -> CategoryConfig | None:
        """Get category config by prefix (e.g., 'BUG', 'FEAT').

        Args:
            prefix: Issue type prefix to look up

        Returns:
            CategoryConfig if found, None otherwise
        """
        for category in self.categories.values():
            if category.prefix == prefix:
                return category
        return None

    def get_category_by_dir(self, dir_name: str) -> CategoryConfig | None:
        """Get category config by directory name.

        Args:
            dir_name: Directory name to look up

        Returns:
            CategoryConfig if found, None otherwise
        """
        for category in self.categories.values():
            if category.dir == dir_name:
                return category
        return None

    def get_all_prefixes(self) -> list[str]:
        """Get all configured issue type prefixes.

        Returns:
            List of prefixes (e.g., ['BUG', 'FEAT', 'ENH'])
        """
        return [cat.prefix for cat in self.categories.values()]

    def get_all_dirs(self) -> list[str]:
        """Get all configured issue directory names.

        Returns:
            List of directory names (e.g., ['bugs', 'features', 'enhancements'])
        """
        return [cat.dir for cat in self.categories.values()]


@dataclass
class AutomationConfig:
    """Automation script configuration."""

    timeout_seconds: int = 3600
    idle_timeout_seconds: int = 0  # Kill if no output for N seconds (0 to disable)
    state_file: str = ".auto-manage-state.json"
    worktree_base: str = ".worktrees"
    max_workers: int = 2
    stream_output: bool = True
    max_continuations: int = 3  # Max session restarts on context handoff

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutomationConfig:
        """Create AutomationConfig from dictionary."""
        return cls(
            timeout_seconds=data.get("timeout_seconds", 3600),
            idle_timeout_seconds=data.get("idle_timeout_seconds", 0),
            state_file=data.get("state_file", ".auto-manage-state.json"),
            worktree_base=data.get("worktree_base", ".worktrees"),
            max_workers=data.get("max_workers", 2),
            stream_output=data.get("stream_output", True),
            max_continuations=data.get("max_continuations", 3),
        )


@dataclass
class ParallelAutomationConfig:
    """Parallel automation configuration using composition.

    Uses AutomationConfig for shared settings (max_workers, worktree_base,
    state_file, timeout_seconds, stream_output) plus parallel-specific fields.
    """

    base: AutomationConfig
    p0_sequential: bool = True
    max_merge_retries: int = 2
    command_prefix: str = "/ll:"
    ready_command: str = "ready_issue {{issue_id}}"
    manage_command: str = "manage_issue {{issue_type}} {{action}} {{issue_id}}"
    worktree_copy_files: list[str] = field(
        default_factory=lambda: [".claude/settings.local.json", ".env"]
    )
    require_code_changes: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParallelAutomationConfig:
        """Create ParallelAutomationConfig from dictionary.

        Shared fields use parallel-specific defaults:
        - state_file: ".parallel-manage-state.json"
        - stream_output: False
        """
        base = AutomationConfig(
            timeout_seconds=data.get("timeout_seconds", 3600),
            state_file=data.get("state_file", ".parallel-manage-state.json"),
            worktree_base=data.get("worktree_base", ".worktrees"),
            max_workers=data.get("max_workers", 2),
            stream_output=data.get("stream_output", False),
        )
        return cls(
            base=base,
            p0_sequential=data.get("p0_sequential", True),
            max_merge_retries=data.get("max_merge_retries", 2),
            command_prefix=data.get("command_prefix", "/ll:"),
            ready_command=data.get("ready_command", "ready_issue {{issue_id}}"),
            manage_command=data.get(
                "manage_command", "manage_issue {{issue_type}} {{action}} {{issue_id}}"
            ),
            worktree_copy_files=data.get(
                "worktree_copy_files", [".claude/settings.local.json", ".env"]
            ),
            require_code_changes=data.get("require_code_changes", True),
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


@dataclass
class SprintsConfig:
    """Sprint management configuration."""

    sprints_dir: str = ".sprints"
    default_timeout: int = 3600
    default_max_workers: int = 2

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SprintsConfig:
        """Create SprintsConfig from dictionary."""
        return cls(
            sprints_dir=data.get("sprints_dir", ".sprints"),
            default_timeout=data.get("default_timeout", 3600),
            default_max_workers=data.get("default_max_workers", 2),
        )


@dataclass
class LoopsConfig:
    """FSM loop configuration."""

    loops_dir: str = ".loops"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopsConfig:
        """Create LoopsConfig from dictionary."""
        return cls(
            loops_dir=data.get("loops_dir", ".loops"),
        )


@dataclass
class GitHubSyncConfig:
    """GitHub-specific sync configuration."""

    repo: str | None = None
    label_mapping: dict[str, str] = field(
        default_factory=lambda: {"BUG": "bug", "FEAT": "enhancement", "ENH": "enhancement"}
    )
    priority_labels: bool = True
    sync_completed: bool = False
    state_file: str = ".claude/ll-sync-state.json"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GitHubSyncConfig:
        """Create GitHubSyncConfig from dictionary."""
        return cls(
            repo=data.get("repo"),
            label_mapping=data.get(
                "label_mapping", {"BUG": "bug", "FEAT": "enhancement", "ENH": "enhancement"}
            ),
            priority_labels=data.get("priority_labels", True),
            sync_completed=data.get("sync_completed", False),
            state_file=data.get("state_file", ".claude/ll-sync-state.json"),
        )


@dataclass
class SyncConfig:
    """Issue sync configuration."""

    enabled: bool = False
    provider: str = "github"
    github: GitHubSyncConfig = field(default_factory=GitHubSyncConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SyncConfig:
        """Create SyncConfig from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            provider=data.get("provider", "github"),
            github=GitHubSyncConfig.from_dict(data.get("github", {})),
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
        self._parallel = ParallelAutomationConfig.from_dict(self._raw_config.get("parallel", {}))
        self._commands = CommandsConfig.from_dict(self._raw_config.get("commands", {}))
        self._scan = ScanConfig.from_dict(self._raw_config.get("scan", {}))
        self._sprints = SprintsConfig.from_dict(self._raw_config.get("sprints", {}))
        self._loops = LoopsConfig.from_dict(self._raw_config.get("loops", {}))
        self._sync = SyncConfig.from_dict(self._raw_config.get("sync", {}))

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

    @property
    def sprints(self) -> SprintsConfig:
        """Get sprints configuration."""
        return self._sprints

    @property
    def loops(self) -> LoopsConfig:
        """Get loops configuration."""
        return self._loops

    @property
    def sync(self) -> SyncConfig:
        """Get sync configuration."""
        return self._sync

    @property
    def repo_path(self) -> Path:
        """Get the repository root path."""
        return self.project_root

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

    def get_loops_dir(self) -> Path:
        """Get the loops directory path."""
        return self.project_root / self._loops.loops_dir

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
        return self.project_root / self._parallel.base.state_file

    def create_parallel_config(
        self,
        *,
        max_workers: int | None = None,
        priority_filter: list[str] | None = None,
        max_issues: int = 0,
        dry_run: bool = False,
        timeout_seconds: int | None = None,
        stream_output: bool | None = None,
        show_model: bool | None = None,
        only_ids: set[str] | None = None,
        skip_ids: set[str] | None = None,
        merge_pending: bool = False,
        clean_start: bool = False,
        ignore_pending: bool = False,
        overlap_detection: bool = False,
        serialize_overlapping: bool = True,
    ) -> ParallelConfig:
        """Create a ParallelConfig from BRConfig settings with optional overrides.

        Args:
            max_workers: Override max_workers (default: from config)
            priority_filter: Override priority filter (default: from issues config)
            max_issues: Maximum issues to process (default: 0 = unlimited)
            dry_run: Preview mode (default: False)
            timeout_seconds: Per-issue timeout (default: from config)
            stream_output: Stream output (default: from config)
            show_model: Make API call to verify model (default: False)
            only_ids: If provided, only process these issue IDs
            skip_ids: Issue IDs to skip (in addition to completed/failed)
            merge_pending: Attempt to merge pending worktrees (default: False)
            clean_start: Remove all worktrees without checking (default: False)
            ignore_pending: Report pending work but continue (default: False)
            overlap_detection: Enable pre-flight overlap detection (default: False)
            serialize_overlapping: If True, defer overlapping issues; if False, just warn

        Returns:
            ParallelConfig configured from BRConfig
        """
        from little_loops.parallel.types import ParallelConfig

        return ParallelConfig(
            max_workers=max_workers or self._parallel.base.max_workers,
            p0_sequential=self._parallel.p0_sequential,
            worktree_base=Path(self._parallel.base.worktree_base),
            state_file=Path(self._parallel.base.state_file),
            max_merge_retries=self._parallel.max_merge_retries,
            priority_filter=priority_filter or self._issues.priorities,
            max_issues=max_issues,
            dry_run=dry_run,
            timeout_per_issue=timeout_seconds or self._parallel.base.timeout_seconds,
            stream_subprocess_output=(
                stream_output if stream_output is not None else self._parallel.base.stream_output
            ),
            show_model=show_model if show_model is not None else False,
            command_prefix=self._parallel.command_prefix,
            ready_command=self._parallel.ready_command,
            manage_command=self._parallel.manage_command,
            only_ids=only_ids,
            skip_ids=skip_ids,
            worktree_copy_files=self._parallel.worktree_copy_files,
            require_code_changes=self._parallel.require_code_changes,
            merge_pending=merge_pending,
            clean_start=clean_start,
            ignore_pending=ignore_pending,
            overlap_detection=overlap_detection,
            serialize_overlapping=serialize_overlapping,
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
                "run_cmd": self._project.run_cmd,
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
                "max_continuations": self._automation.max_continuations,
            },
            "parallel": {
                "max_workers": self._parallel.base.max_workers,
                "p0_sequential": self._parallel.p0_sequential,
                "worktree_base": self._parallel.base.worktree_base,
                "state_file": self._parallel.base.state_file,
                "timeout_seconds": self._parallel.base.timeout_seconds,
                "max_merge_retries": self._parallel.max_merge_retries,
                "stream_output": self._parallel.base.stream_output,
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
            "sprints": {
                "sprints_dir": self._sprints.sprints_dir,
                "default_timeout": self._sprints.default_timeout,
                "default_max_workers": self._sprints.default_max_workers,
            },
            "loops": {
                "loops_dir": self._loops.loops_dir,
            },
            "sync": {
                "enabled": self._sync.enabled,
                "provider": self._sync.provider,
                "github": {
                    "repo": self._sync.github.repo,
                    "label_mapping": self._sync.github.label_mapping,
                    "priority_labels": self._sync.github.priority_labels,
                    "sync_completed": self._sync.github.sync_completed,
                    "state_file": self._sync.github.state_file,
                },
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
