"""Core configuration dataclasses and the root BRConfig aggregator.

ProjectConfig holds project-level settings. BRConfig is the single entry
point that loads ll-config.json and exposes all domain configs via properties.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from little_loops.config.automation import (
    AutomationConfig,
    CommandsConfig,
    DependencyMappingConfig,
    ParallelAutomationConfig,
)
from little_loops.config.cli import CliConfig, RefineStatusConfig
from little_loops.config.features import (
    IssuesConfig,
    LoopsConfig,
    ScanConfig,
    SprintsConfig,
    SyncConfig,
)
from little_loops.parallel.types import ParallelConfig


@dataclass
class ProjectConfig:
    """Project-level configuration."""

    name: str = ""
    src_dir: str = "src/"
    test_dir: str = "tests"
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
            test_dir=data.get("test_dir", "tests"),
            test_cmd=data.get("test_cmd", "pytest"),
            lint_cmd=data.get("lint_cmd", "ruff check ."),
            type_cmd=data.get("type_cmd", "mypy"),
            format_cmd=data.get("format_cmd", "ruff format ."),
            build_cmd=data.get("build_cmd"),
            run_cmd=data.get("run_cmd"),
        )


class BRConfig:
    """Main configuration class for little-loops.

    Loads configuration from .ll/ll-config.json and merges with defaults.
    Provides convenient property access to all configuration values.

    Example:
        config = BRConfig(Path.cwd())
        print(config.project.src_dir)  # "src/"
        print(config.issues.base_dir)  # ".issues"
        print(config.get_issue_dir("bugs"))  # Path(".issues/bugs")
    """

    CONFIG_FILENAME = "ll-config.json"
    CONFIG_DIR = ".ll"

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
        self._dependency_mapping = DependencyMappingConfig.from_dict(
            self._raw_config.get("dependency_mapping", {})
        )
        self._cli = CliConfig.from_dict(self._raw_config.get("cli", {}))
        self._refine_status = RefineStatusConfig.from_dict(
            self._raw_config.get("refine_status", {})
        )

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
    def dependency_mapping(self) -> DependencyMappingConfig:
        """Get dependency mapping configuration."""
        return self._dependency_mapping

    @property
    def cli(self) -> CliConfig:
        """Get CLI output configuration."""
        return self._cli

    @property
    def refine_status(self) -> RefineStatusConfig:
        """Get refine-status display configuration."""
        return self._refine_status

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

    def get_deferred_dir(self) -> Path:
        """Get the path to the deferred issues directory."""
        return self.project_root / self._issues.base_dir / self._issues.deferred_dir

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
        idle_timeout_per_issue: int | None = None,
        stream_output: bool | None = None,
        show_model: bool | None = None,
        only_ids: set[str] | None = None,
        skip_ids: set[str] | None = None,
        type_prefixes: set[str] | None = None,
        merge_pending: bool = False,
        clean_start: bool = False,
        ignore_pending: bool = False,
        overlap_detection: bool = False,
        serialize_overlapping: bool = True,
        base_branch: str = "main",
        remote_name: str | None = None,
    ) -> ParallelConfig:
        """Create a ParallelConfig from BRConfig settings with optional overrides.

        Args:
            max_workers: Override max_workers (default: from config)
            priority_filter: Override priority filter (default: from issues config)
            max_issues: Maximum issues to process (default: 0 = unlimited)
            dry_run: Preview mode (default: False)
            timeout_seconds: Per-issue timeout (default: from config)
            idle_timeout_per_issue: Kill worker if no output for N seconds (0 to disable, default: 0)
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
            idle_timeout_per_issue=idle_timeout_per_issue
            if idle_timeout_per_issue is not None
            else 0,
            stream_subprocess_output=(
                stream_output if stream_output is not None else self._parallel.base.stream_output
            ),
            show_model=show_model if show_model is not None else False,
            command_prefix=self._parallel.command_prefix,
            ready_command=self._parallel.ready_command,
            manage_command=self._parallel.manage_command,
            only_ids=only_ids,
            skip_ids=skip_ids,
            type_prefixes=type_prefixes,
            worktree_copy_files=self._parallel.worktree_copy_files,
            require_code_changes=self._parallel.require_code_changes,
            use_feature_branches=self._parallel.use_feature_branches,
            merge_pending=merge_pending,
            clean_start=clean_start,
            ignore_pending=ignore_pending,
            overlap_detection=overlap_detection,
            serialize_overlapping=serialize_overlapping,
            base_branch=base_branch,
            remote_name=remote_name if remote_name is not None else self._parallel.remote_name,
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
                "test_dir": self._project.test_dir,
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
                "deferred_dir": self._issues.deferred_dir,
                "priorities": self._issues.priorities,
                "templates_dir": self._issues.templates_dir,
                "capture_template": self._issues.capture_template,
            },
            "automation": {
                "timeout_seconds": self._automation.timeout_seconds,
                "idle_timeout_seconds": self._automation.idle_timeout_seconds,
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
                "timeout_per_issue": self._parallel.base.timeout_seconds,
                "max_merge_retries": self._parallel.max_merge_retries,
                "stream_subprocess_output": self._parallel.base.stream_output,
                "command_prefix": self._parallel.command_prefix,
                "ready_command": self._parallel.ready_command,
                "manage_command": self._parallel.manage_command,
                "worktree_copy_files": self._parallel.worktree_copy_files,
                "require_code_changes": self._parallel.require_code_changes,
                "use_feature_branches": self._parallel.use_feature_branches,
                "remote_name": self._parallel.remote_name,
            },
            "commands": {
                "pre_implement": self._commands.pre_implement,
                "post_implement": self._commands.post_implement,
                "custom_verification": self._commands.custom_verification,
                "confidence_gate": {
                    "enabled": self._commands.confidence_gate.enabled,
                    "readiness_threshold": self._commands.confidence_gate.readiness_threshold,
                    "outcome_threshold": self._commands.confidence_gate.outcome_threshold,
                },
                "tdd_mode": self._commands.tdd_mode,
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
                "glyphs": self._loops.glyphs.to_dict(),
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
                    "pull_template": self._sync.github.pull_template,
                },
            },
            "dependency_mapping": {
                "overlap_min_files": self._dependency_mapping.overlap_min_files,
                "overlap_min_ratio": self._dependency_mapping.overlap_min_ratio,
                "min_directory_depth": self._dependency_mapping.min_directory_depth,
                "conflict_threshold": self._dependency_mapping.conflict_threshold,
                "high_conflict_threshold": self._dependency_mapping.high_conflict_threshold,
                "confidence_modifier": self._dependency_mapping.confidence_modifier,
                "scoring_weights": {
                    "semantic": self._dependency_mapping.scoring_weights.semantic,
                    "section": self._dependency_mapping.scoring_weights.section,
                    "type": self._dependency_mapping.scoring_weights.type,
                },
                "exclude_common_files": self._dependency_mapping.exclude_common_files,
            },
            "cli": {
                "color": self._cli.color,
                "colors": {
                    "logger": {
                        "info": self._cli.colors.logger.info,
                        "success": self._cli.colors.logger.success,
                        "warning": self._cli.colors.logger.warning,
                        "error": self._cli.colors.logger.error,
                    },
                    "priority": {
                        "P0": self._cli.colors.priority.P0,
                        "P1": self._cli.colors.priority.P1,
                        "P2": self._cli.colors.priority.P2,
                        "P3": self._cli.colors.priority.P3,
                        "P4": self._cli.colors.priority.P4,
                        "P5": self._cli.colors.priority.P5,
                    },
                    "type": {
                        "BUG": self._cli.colors.type.BUG,
                        "FEAT": self._cli.colors.type.FEAT,
                        "ENH": self._cli.colors.type.ENH,
                    },
                    "fsm_active_state": self._cli.colors.fsm_active_state,
                    "fsm_edge_labels": {
                        "yes": self._cli.colors.fsm_edge_labels.yes,
                        "no": self._cli.colors.fsm_edge_labels.no,
                        "error": self._cli.colors.fsm_edge_labels.error,
                        "partial": self._cli.colors.fsm_edge_labels.partial,
                        "next": self._cli.colors.fsm_edge_labels.next,
                        "default": self._cli.colors.fsm_edge_labels.default,
                        "blocked": self._cli.colors.fsm_edge_labels.blocked,
                        "retry_exhausted": self._cli.colors.fsm_edge_labels.retry_exhausted,
                    },
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
