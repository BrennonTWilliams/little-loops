"""Automation and execution configuration dataclasses.

Covers automation scripts, parallel execution, confidence gates,
command behavior, and dependency analysis configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    ready_command: str = "ready-issue {{issue_id}}"
    manage_command: str = "manage-issue {{issue_type}} {{action}} {{issue_id}}"
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
            ready_command=data.get("ready_command", "ready-issue {{issue_id}}"),
            manage_command=data.get(
                "manage_command", "manage-issue {{issue_type}} {{action}} {{issue_id}}"
            ),
            worktree_copy_files=data.get(
                "worktree_copy_files", [".claude/settings.local.json", ".env"]
            ),
            require_code_changes=data.get("require_code_changes", True),
        )


@dataclass
class ConfidenceGateConfig:
    """Confidence score gate configuration for manage-issue."""

    enabled: bool = False
    threshold: int = 85

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfidenceGateConfig:
        """Create ConfidenceGateConfig from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            threshold=data.get("threshold", 85),
        )


@dataclass
class CommandsConfig:
    """Command customization configuration."""

    pre_implement: str | None = None
    post_implement: str | None = None
    custom_verification: list[str] = field(default_factory=list)
    confidence_gate: ConfidenceGateConfig = field(default_factory=ConfidenceGateConfig)
    tdd_mode: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommandsConfig:
        """Create CommandsConfig from dictionary."""
        return cls(
            pre_implement=data.get("pre_implement"),
            post_implement=data.get("post_implement"),
            custom_verification=data.get("custom_verification", []),
            confidence_gate=ConfidenceGateConfig.from_dict(data.get("confidence_gate", {})),
            tdd_mode=data.get("tdd_mode", False),
        )


@dataclass
class ScoringWeightsConfig:
    """Scoring weights for semantic conflict analysis.

    Weights for the three signals used in compute_conflict_score().
    Should sum to 1.0 for normalized scoring.

    Attributes:
        semantic: Weight for semantic target overlap (component/function names)
        section: Weight for section mention overlap (UI regions)
        type: Weight for modification type match
    """

    semantic: float = 0.5
    section: float = 0.3
    type: float = 0.2

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScoringWeightsConfig:
        """Create ScoringWeightsConfig from dictionary."""
        return cls(
            semantic=data.get("semantic", 0.5),
            section=data.get("section", 0.3),
            type=data.get("type", 0.2),
        )


@dataclass
class DependencyMappingConfig:
    """Dependency mapping threshold configuration.

    Controls overlap detection sensitivity and conflict scoring thresholds.
    Default values match the previously hardcoded constants for backwards
    compatibility.

    Attributes:
        overlap_min_files: Minimum overlapping files to trigger overlap
        overlap_min_ratio: Minimum ratio of overlapping files to smaller set
        min_directory_depth: Minimum path segments for directory overlap
        conflict_threshold: Below = parallel-safe, above = dependency proposed
        high_conflict_threshold: Above = HIGH conflict label
        confidence_modifier: Applied when dependency direction is ambiguous
        scoring_weights: Weights for semantic/section/type signals
        exclude_common_files: Infrastructure files excluded from overlap detection
    """

    overlap_min_files: int = 2
    overlap_min_ratio: float = 0.25
    min_directory_depth: int = 2
    conflict_threshold: float = 0.4
    high_conflict_threshold: float = 0.7
    confidence_modifier: float = 0.5
    scoring_weights: ScoringWeightsConfig = field(default_factory=ScoringWeightsConfig)
    exclude_common_files: list[str] = field(
        default_factory=lambda: [
            "__init__.py",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "CHANGELOG.md",
            "README.md",
            "conftest.py",
        ]
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DependencyMappingConfig:
        """Create DependencyMappingConfig from dictionary."""
        return cls(
            overlap_min_files=data.get("overlap_min_files", 2),
            overlap_min_ratio=data.get("overlap_min_ratio", 0.25),
            min_directory_depth=data.get("min_directory_depth", 2),
            conflict_threshold=data.get("conflict_threshold", 0.4),
            high_conflict_threshold=data.get("high_conflict_threshold", 0.7),
            confidence_modifier=data.get("confidence_modifier", 0.5),
            scoring_weights=ScoringWeightsConfig.from_dict(data.get("scoring_weights", {})),
            exclude_common_files=data.get(
                "exclude_common_files",
                [
                    "__init__.py",
                    "pyproject.toml",
                    "setup.py",
                    "setup.cfg",
                    "CHANGELOG.md",
                    "README.md",
                    "conftest.py",
                ],
            ),
        )
