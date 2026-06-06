"""Configuration management for little-loops.

Provides the BRConfig class for loading, merging, and accessing project configuration.
Configuration is read from .ll/ll-config.json and merged with sensible defaults.

This package is organized into domain-specific modules:
  core.py       — ProjectConfig, BRConfig (root aggregator)
  cli.py        — CLI color and display configuration
  features.py   — Issue tracking, scanning, sprints, loops, sync
  automation.py — Parallel execution, commands, dependency analysis
"""

from little_loops.config.automation import (
    AutomationConfig,
    CommandsConfig,
    ConfidenceGateConfig,
    DependencyMappingConfig,
    ParallelAutomationConfig,
    RateLimitsConfig,
    RecursiveRefineConfig,
    ScoringWeightsConfig,
)
from little_loops.config.cli import (
    CliColorsConfig,
    CliColorsEdgeLabelsConfig,
    CliColorsLoggerConfig,
    CliColorsPriorityConfig,
    CliColorsTypeConfig,
    CliConfig,
    RefineStatusConfig,
)
from little_loops.config.core import BRConfig, CLConfig, ProjectConfig

# Note: `resolve_config_path` (config.core) and `feature_enabled` (config.features)
# are intentionally NOT re-exported via __all__ — callers import them via direct
# submodule paths (e.g. `from little_loops.config.core import resolve_config_path`).
# This keeps the package-level surface focused on dataclass types and BRConfig.
from little_loops.config.features import (
    DEFAULT_CATEGORIES,
    REQUIRED_CATEGORIES,
    AnalyticsCaptureConfig,
    CaptureIssueConfig,
    CategoryConfig,
    CompactionConfig,
    DecisionsConfig,
    DesignTokensConfig,
    DuplicateDetectionConfig,
    EventsConfig,
    EvolutionConfig,
    GitHubSyncConfig,
    GoNoGoConfig,
    HistoryConfig,
    IssuesConfig,
    LearningTestsConfig,
    LoopsConfig,
    LoopsGlyphsConfig,
    NextIssueConfig,
    NextIssueSortKey,
    OTelEventsConfig,
    ScanConfig,
    SessionDigestConfig,
    SocketEventsConfig,
    SprintsConfig,
    SyncConfig,
    WebhookEventsConfig,
)
from little_loops.config.orchestration import (
    ComposerAdaptiveConfig,
    ComposerConfig,
    OrchestrationConfig,
)

__all__ = [
    "BRConfig",
    "CLConfig",
    "ComposerAdaptiveConfig",
    "ComposerConfig",
    "OrchestrationConfig",
    "AnalyticsCaptureConfig",
    "CategoryConfig",
    "ProjectConfig",
    "IssuesConfig",
    "LearningTestsConfig",
    "DecisionsConfig",
    "DesignTokensConfig",
    "AutomationConfig",
    "ParallelAutomationConfig",
    "CommandsConfig",
    "ScanConfig",
    "SprintsConfig",
    "LoopsConfig",
    "LoopsGlyphsConfig",
    "GitHubSyncConfig",
    "ConfidenceGateConfig",
    "RateLimitsConfig",
    "RecursiveRefineConfig",
    "SyncConfig",
    "EventsConfig",
    "OTelEventsConfig",
    "SocketEventsConfig",
    "WebhookEventsConfig",
    "ScoringWeightsConfig",
    "DependencyMappingConfig",
    "DuplicateDetectionConfig",
    "NextIssueConfig",
    "NextIssueSortKey",
    "CliColorsEdgeLabelsConfig",
    "CliColorsLoggerConfig",
    "CliColorsPriorityConfig",
    "CliColorsTypeConfig",
    "CliColorsConfig",
    "CliConfig",
    "RefineStatusConfig",
    "REQUIRED_CATEGORIES",
    "DEFAULT_CATEGORIES",
    "CaptureIssueConfig",
    "CompactionConfig",
    "EvolutionConfig",
    "GoNoGoConfig",
    "HistoryConfig",
    "SessionDigestConfig",
]
